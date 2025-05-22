import os
import sys
import logging
from datetime import datetime
import xml.etree.ElementTree as ET
import psycopg2
import requests

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planfix_utils import (
    check_required_env_vars,
    make_planfix_request,
    get_supabase_connection,
    mark_items_as_deleted_in_supabase,
    upsert_data_to_supabase
)

# Script-specific constants
TASK_TEMPLATE_ID = 2465239  # Planfix ID for "Tasks" general task template
TASKS_TABLE_NAME = "planfix_tasks"
TASKS_PK_COLUMN = "planfix_id" # Primary key in Supabase table
# No custom map for tasks in this example, but could be added if needed:
# TASK_CUSTOM_MAP = {} 

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def get_planfix_tasks(page):
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<request method="task.getList">'
        f'<account>{os.environ.get("PLANFIX_ACCOUNT")}</account>'
        f'<pageCurrent>{page}</pageCurrent>'
        f'<pageSize>100</pageSize>'
        '<filters>'
        '  <filter>'
        '    <type>51</type>'
        '    <operator>equal</operator>'
        f'    <value>{TASK_TEMPLATE_ID}</value>'
        '  </filter>'
        '</filters>'
        '<fields>'
        '  <field>id</field>'
        '  <field>title</field>'
        '  <field>description</field>'
        '  <field>status</field>'
        '  <field>statusName</field>'
        '  <field>assigner</field>'
        '  <field>owner</field>'
        '  <field>dateCreate</field>'
        '  <field>dateStart</field>'
        '  <field>dateEnd</field>'
        '  <field>dateComplete</field>'
        '  <field>lastUpdateDate</field>'
        '</fields>'
        '</request>'
    )
    response = requests.post(
        os.environ.get("PLANFIX_API_URL", "https://api.planfix.com/xml/"),
        data=body.encode('utf-8'),
        headers=headers,
        auth=(os.environ.get("PLANFIX_API_KEY"), os.environ.get("PLANFIX_USER_TOKEN"))
    )
    response.raise_for_status()
    return response.text

def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def parse_tasks(xml_text):
    root = ET.fromstring(xml_text)
    if root.attrib.get("status") == "error":
        code = root.findtext("code")
        message = root.findtext("message")
        logger.error(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    tasks = []
    for task in root.findall('.//task'):
        template_id = task.findtext('template/id')
        if str(template_id) != str(TASK_TEMPLATE_ID):
            continue
        def get_text(tag):
            el = task.find(tag)
            return el.text if el is not None else None
        tasks.append({
            "planfix_id": int(get_text('id')) if get_text('id') else None,
            "title": get_text('title'),
            "description": get_text('description'),
            "status": get_text('statusName') or get_text('status'),
            "assigner_id": int(get_text('assigner/id')) if get_text('assigner/id') else None,
            "assigner_name": get_text('assigner/name'),
            "owner_id": int(get_text('owner/id')) if get_text('owner/id') else None,
            "owner_name": get_text('owner/name'),
            "date_created": parse_date(get_text('dateCreate')),
            "start_date": parse_date(get_text('dateStart')),
            "due_date": parse_date(get_text('dateEnd')),
            "date_completed": parse_date(get_text('dateComplete')),
            "last_update_date": parse_date(get_text('lastUpdateDate')),
            "updated_at": datetime.now(),
            "is_deleted": False
        })
    return tasks

def main():
    """
    Main function to fetch tasks from Planfix and upsert to Supabase.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Planfix tasks to Supabase synchronization...")

    required_env_vars = {
        'PLANFIX_API_KEY': os.environ.get('PLANFIX_API_KEY'),
        'PLANFIX_USER_TOKEN': os.environ.get('PLANFIX_USER_TOKEN'),
        'PLANFIX_ACCOUNT': os.environ.get('PLANFIX_ACCOUNT'),
        'SUPABASE_CONNECTION_STRING': os.environ.get('SUPABASE_CONNECTION_STRING')
    }
    try:
        check_required_env_vars(required_env_vars)
    except ValueError as e:
        logger.critical(f"Stopping script due to missing environment variables: {e}")
        return

    supabase_conn = None
    try:
        supabase_conn = get_supabase_connection()
        current_page = 1
        all_processed_ids = []
        all_tasks = []
        while True:
            logger.info(f"Fetching page {current_page} of tasks...")
            try:
                xml = get_planfix_tasks(current_page)
                if current_page == 1:
                    with open('planfix_tasks_response_page1.xml', 'w', encoding='utf-8') as f:
                        f.write(xml)
                    logger.info('Сохранил XML-ответ первой страницы в planfix_tasks_response_page1.xml')
                tasks = parse_tasks(xml)
                all_tasks.extend(tasks)
                logger.info(f"На странице {current_page}: {len(tasks)} задач с шаблоном {TASK_TEMPLATE_ID}")
                if not tasks:
                    logger.info("No more tasks found. Exiting loop.")
                    break
                for t in tasks:
                    pk_value = t.get(TASKS_PK_COLUMN)
                    if pk_value:
                        try:
                            all_processed_ids.append(int(pk_value))
                        except ValueError:
                            logger.warning(f"Could not convert primary key '{pk_value}' to int for task ID. Skipping for deletion marking list.")
                root = ET.fromstring(xml)
                tasks_root = root.find('.//tasks')
                if tasks_root is not None and int(tasks_root.attrib.get('count', 0)) < 100:
                    break
                current_page += 1
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching data from Planfix API for tasks: {e}")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred processing page {current_page} of tasks: {e}")
                break
        if all_tasks:
            first_item_keys = all_tasks[0].keys()
            if TASKS_PK_COLUMN not in first_item_keys:
                logger.critical(f"Primary key '{TASKS_PK_COLUMN}' not found in processed data keys. Skipping upsert.")
            else:
                all_column_names = list(first_item_keys)
                upsert_data_to_supabase(
                    supabase_conn,
                    TASKS_TABLE_NAME,
                    TASKS_PK_COLUMN,
                    all_column_names,
                    all_tasks
                )
                logger.info(f"Upserted {len(all_tasks)} tasks.")
        else:
            logger.info(f"No data to upsert.")
        if supabase_conn:
            if not all_processed_ids and current_page == 1:
                logger.info("No tasks were found in Planfix. Marking all existing tasks in Supabase as deleted.")
                mark_items_as_deleted_in_supabase(
                    supabase_conn, TASKS_TABLE_NAME, TASKS_PK_COLUMN, []
                )
            elif all_processed_ids:
                logger.info(f"Total processed task IDs for deletion check: {len(all_processed_ids)}")
                mark_items_as_deleted_in_supabase(
                    supabase_conn, TASKS_TABLE_NAME, TASKS_PK_COLUMN, all_processed_ids
                )
                logger.info(f"Marked tasks not in the current batch as deleted.")
            else:
                logger.warning("No new task IDs were processed successfully. Skipping deletion marking to avoid data loss due to potential errors.")
    except psycopg2.Error as e:
        logger.critical(f"Supabase connection error: {e}")
    except ValueError as e:
        logger.critical(f"Configuration error (likely missing env vars, logged earlier): {e}")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred in main task sync: {e}")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Task synchronization finished.")

if __name__ == "__main__":
    main()
