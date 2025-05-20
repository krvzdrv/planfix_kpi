import os
import sys
import logging
from datetime import datetime
import xml.etree.ElementTree as ET
import psycopg2
import requests

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.planfix_utils as planfix_utils

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
        f'<request method="task.getList">'
        f'<account>{planfix_utils.PLANFIX_ACCOUNT}</account>'
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
        '  <field>project</field>'
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
        planfix_utils.PLANFIX_API_URL,
        data=body.encode('utf-8'),
        headers=headers,
        auth=(planfix_utils.PLANFIX_API_KEY, planfix_utils.PLANFIX_TOKEN)
    )
    response.raise_for_status()
    return response.text

def parse_tasks(xml_text):
    root = ET.fromstring(xml_text)
    if root.attrib.get("status") == "error":
        code = root.findtext("code")
        message = root.findtext("message")
        logger.error(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    tasks = []
    for task in root.findall('.//task'):
        def get_text(tag):
            el = task.find(tag)
            return el.text if el is not None else None

        tasks.append({
            "planfix_id": int(get_text('id')) if get_text('id') else None,
            "title": get_text('title'),
            "description": get_text('description'),
            "status": get_text('statusName') or get_text('status'),
            "project_id": int(get_text('project/id')) if get_text('project/id') else None,
            "project_title": get_text('project/title'),
            "assigner_id": int(get_text('assigner/id')) if get_text('assigner/id') else None,
            "assigner_name": get_text('assigner/name'),
            "owner_id": int(get_text('owner/id')) if get_text('owner/id') else None,
            "owner_name": get_text('owner/name'),
            "date_created": planfix_utils.parse_planfix_date_string(get_text('dateCreate')),
            "start_date": planfix_utils.parse_planfix_date_string(get_text('dateStart')),
            "due_date": planfix_utils.parse_planfix_date_string(get_text('dateEnd')),
            "date_completed": planfix_utils.parse_planfix_date_string(get_text('dateComplete')),
            "last_update_date": planfix_utils.parse_planfix_date_string(get_text('lastUpdateDate')),
            "updated_at": datetime.now(),
            "is_deleted": False
        })
    return tasks

def upsert_tasks(tasks, supabase_conn):
    if not tasks:
        return
    first_item_keys = tasks[0].keys()
    all_column_names = list(first_item_keys)
    planfix_utils.upsert_data_to_supabase(
        supabase_conn,
        TASKS_TABLE_NAME,
        TASKS_PK_COLUMN,
        all_column_names,
        tasks
    )
    logger.info(f"Upserted {len(tasks)} tasks.")

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
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_TOKEN': planfix_utils.PLANFIX_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
        'SUPABASE_CONNECTION_STRING': planfix_utils.SUPABASE_CONNECTION_STRING
    }
    try:
        planfix_utils.check_required_env_vars(required_env_vars)
    except ValueError as e:
        logger.critical(f"Stopping script due to missing environment variables: {e}")
        return

    supabase_conn = None
    try:
        supabase_conn = planfix_utils.get_supabase_connection()
        all_tasks = []
        all_ids = []
        page = 1
        while True:
            logger.info(f"Fetching page {page} of tasks...")
            xml = get_planfix_tasks(page)
            if page == 1:
                logger.debug("----- XML-ответ первой страницы -----")
                logger.debug(xml[:2000])
                logger.debug("----- Конец XML-ответа -----")
            tasks = parse_tasks(xml)
            if not tasks:
                break
            upsert_tasks(tasks, supabase_conn)
            all_tasks.extend(tasks)
            all_ids.extend([t[TASKS_PK_COLUMN] for t in tasks if t[TASKS_PK_COLUMN] is not None])
            logger.info(f"Загружено задач на странице {page}: {len(tasks)}")
            if len(tasks) < 100:
                break
            page += 1
        logger.info(f"Всего загружено задач: {len(all_tasks)}")
        # Можно добавить пометку удалённых, если нужно
    except psycopg2.Error as e:
        logger.critical(f"Supabase connection error: {e}")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred in main task sync: {e}")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Task synchronization finished.")

if __name__ == "__main__":
    main()
