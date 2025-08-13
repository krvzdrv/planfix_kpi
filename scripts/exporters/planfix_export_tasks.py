import os
import sys
import logging
from datetime import datetime
import xml.etree.ElementTree as ET
import psycopg2
import requests
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.planfix_utils import (
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
        '  <field>type</field>'
        '  <field>template</field>'
        '  <field>customData</field>'
        '</fields>'
        '</request>'
    )
    response = requests.post(
        os.environ.get("PLANFIX_API_URL", "https://api.planfix.com/xml/"),
        data=body.encode('utf-8'),
        headers=headers,
        auth=(os.environ.get("PLANFIX_API_KEY"), os.environ.get("PLANFIX_TOKEN"))
    )
    response.raise_for_status()
    return response.text

def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.isoformat()  # Convert to ISO format for Supabase
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
    custom_fields = {
        "Zadanie powiązane": "zadanie_powiazane",
        "Kontakt": "kontakt",
        "Następne zadanie": "nastepne_zadanie",
        "Wynik": "wynik",
        "Prywatna notatka": "prywatna_notatka",
        "Zmień nazwę zadania": "zmien_nazwe_zadania",
        "Ostatni komentarz": "ostatni_komentarz",
        "Autor komentarza": "autor_komentarza",
        "Data utworzenia zadania": "data_utworzenia_zadania",
        "Data zakończenia zadania": "data_zakonczenia_zadania",
        "Запустить сценарий \"Обновить данные в KPI\"": "zapustit_scenarij_obnovit_dannye_v_kpi"
    }
    for task in root.findall('.//task'):
        template_id = task.findtext('template/id')
        if str(template_id) != str(TASK_TEMPLATE_ID):
            continue
        def get_text(tag):
            el = task.find(tag)
            return el.text if el is not None else None
        title = get_text('title')
        task_type = None
        if title and '/' in title:
            task_type = title.split('/')[0].strip()
        # Парсим customData
        custom_data = {}
        custom_result = {v: None for v in custom_fields.values()}
        custom_data_root = task.find('customData')
        if custom_data_root is not None:
            for cv in custom_data_root.findall('customValue'):
                field = cv.find('field/name')
                value = cv.find('value')
                text = cv.find('text')
                if field is not None:
                    field_name = field.text
                    if field_name in custom_fields:
                        # Для дат парсим value как дату, если это дата
                        if field_name in ["Data utworzenia zadania", "Data zakończenia zadania"]:
                            custom_result[custom_fields[field_name]] = parse_date(value.text) if value is not None else None
                        else:
                            custom_result[custom_fields[field_name]] = value.text if value is not None else text.text if text is not None else None
                    custom_data[field_name] = {
                        "value": value.text if value is not None else None,
                        "text": text.text if text is not None else None
                    }
        tasks.append({
            "planfix_id": int(get_text('id')) if get_text('id') else None,
            "title": title,
            "description": get_text('description'),
            "importance": get_text('importance'),
            "status": get_text('status'),
            "status_set": int(get_text('statusSet')) if get_text('statusSet') else None,
            "check_result": get_text('checkResult') == '1',
            "type": get_text('type'),
            "additional_description_data": get_text('additionalDescriptionData'),
            "owner_id": int(get_text('owner/id')) if get_text('owner/id') else None,
            "owner_name": get_text('owner/name'),
            "parent_id": int(get_text('parent/id')) if get_text('parent/id') else None,
            "template_id": int(get_text('template/id')) if get_text('template/id') else None,
            "project_id": int(get_text('project/id')) if get_text('project/id') else None,
            "project_title": get_text('project/title'),
            "client_id": int(get_text('client/id')) if get_text('client/id') else None,
            "client_name": get_text('client/name'),
            "begin_datetime": parse_date(get_text('beginDateTime')),
            "end_time": parse_date(get_text('endTime')),
            "general": int(get_text('general')) if get_text('general') else None,
            "is_overdued": get_text('isOverdued') == '1',
            "is_close_to_deadline": get_text('isCloseToDeadline') == '1',
            "is_not_accepted_in_time": get_text('isNotAcceptedInTime') == '1',
            "is_summary": get_text('isSummary') == '1',
            "starred": get_text('starred') == '1',
            # Пользовательские поля
            **custom_result,
            # Всё customData в JSON
            "custom_data": json.dumps(custom_data) if custom_data else None,
            "workers": None,  # Можно доработать если появятся исполнители
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
        'PLANFIX_TOKEN': os.environ.get('PLANFIX_TOKEN'),
        'PLANFIX_ACCOUNT': os.environ.get('PLANFIX_ACCOUNT'),
        'SUPABASE_CONNECTION_STRING': os.environ.get('SUPABASE_CONNECTION_STRING'),
        'SUPABASE_HOST': os.environ.get('SUPABASE_HOST'),
        'SUPABASE_DB': os.environ.get('SUPABASE_DB'),
        'SUPABASE_USER': os.environ.get('SUPABASE_USER'),
        'SUPABASE_PASSWORD': os.environ.get('SUPABASE_PASSWORD'),
        'SUPABASE_PORT': os.environ.get('SUPABASE_PORT')
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
