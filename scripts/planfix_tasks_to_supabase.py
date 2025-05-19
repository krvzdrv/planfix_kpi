import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import psycopg2
import json
import os

# --- Настройки Planfix ---
API_URL = "https://api.planfix.com/xml/"
API_KEY = os.environ.get('PLANFIX_API_KEY')
TOKEN = os.environ.get('PLANFIX_TOKEN')
ACCOUNT = os.environ.get('PLANFIX_ACCOUNT')

# --- Настройки базы данных ---
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# Проверка наличия всех необходимых переменных окружения
required_env_vars = {
    'PLANFIX_API_KEY': API_KEY,
    'PLANFIX_TOKEN': TOKEN,
    'PLANFIX_ACCOUNT': ACCOUNT,
    'SUPABASE_HOST': PG_HOST,
    'SUPABASE_DB': PG_DB,
    'SUPABASE_USER': PG_USER,
    'SUPABASE_PASSWORD': PG_PASSWORD,
    'SUPABASE_PORT': PG_PORT
}

missing_vars = [var for var, value in required_env_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Отсутствуют следующие переменные окружения: {', '.join(missing_vars)}")

def get_planfix_tasks(page):
    TEMPLATE_ID = 2465239
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<request method="task.getList">'
        f'<account>{ACCOUNT}</account>'
        f'<pageCurrent>{page}</pageCurrent>'
        f'<pageSize>100</pageSize>'
        '<filters>'
        '  <filter>'
        '    <type>51</type>'
        '    <operator>equal</operator>'
        f'    <value>{TEMPLATE_ID}</value>'
        '  </filter>'
        '</filters>'
        '</request>'
    )
    response = requests.post(
        API_URL,
        data=body.encode('utf-8'),
        headers=headers,
        auth=(API_KEY, TOKEN)
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
        print(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    tasks = []
    for task in root.findall('.//task'):
        def get_custom(name):
            for cv in task.findall('.//customValue'):
                field = cv.find('field/name')
                if field is not None and field.text == name:
                    return cv.find('value').text if cv.find('value') is not None else None
            return None

        def get_text(tag):
            el = task.find(tag)
            return el.text if el is not None else None

        tasks.append({
            "planfix_id": int(get_text('id')),
            "title": get_text('title'),
            "description": get_text('description'),
            "status": int(get_text('status')) if get_text('status') else None,
            "status_set": int(get_text('statusSet')) if get_text('statusSet') else None,
            "type": get_text('type'),
            "owner_id": int(get_text('owner/id')) if get_text('owner/id') else None,
            "owner_name": get_text('owner/name'),
            "client_id": int(get_text('client/id')) if get_text('client/id') else None,
            "client_name": get_text('client/name'),
            "begin_datetime": parse_date(get_text('beginDateTime')),
            "end_time": parse_date(get_text('endTime')),
            "created_at": parse_date(get_custom("Data utworzenia zadania")),
            "closed_at": parse_date(get_custom("Data zakończenia zadania")),
            "result": get_custom("Wynik"),
            "comment": get_custom("Оstatni комментарий"),
            "comment_author": get_custom("Автор комментария"),
        })
    return tasks

def upsert_tasks(tasks):
    if not tasks:
        return []
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    actual_ids = []
    for t in tasks:
        actual_ids.append(t["planfix_id"])
        t["is_deleted"] = False
        cur.execute("""
            INSERT INTO planfix_tasks (
                planfix_id, title, description, status, status_set, type,
                owner_id, owner_name, client_id, client_name,
                begin_datetime, end_time, created_at, closed_at,
                result, comment, comment_author, updated_at, is_deleted
            ) VALUES (
                %(planfix_id)s, %(title)s, %(description)s, %(status)s, %(status_set)s, %(type)s,
                %(owner_id)s, %(owner_name)s, %(client_id)s, %(client_name)s,
                %(begin_datetime)s, %(end_time)s, %(created_at)s, %(closed_at)s,
                %(result)s, %(comment)s, %(comment_author)s, NOW(), %(is_deleted)s
            )
            ON CONFLICT (planfix_id) DO UPDATE SET
                title=EXCLUDED.title,
                description=EXCLUDED.description,
                status=EXCLUDED.status,
                status_set=EXCLUDED.status_set,
                type=EXCLUDED.type,
                owner_id=EXCLUDED.owner_id,
                owner_name=EXCLUDED.owner_name,
                client_id=EXCLUDED.client_id,
                client_name=EXCLUDED.client_name,
                begin_datetime=EXCLUDED.begin_datetime,
                end_time=EXCLUDED.end_time,
                created_at=EXCLUDED.created_at,
                closed_at=EXCLUDED.closed_at,
                result=EXCLUDED.result,
                comment=EXCLUDED.comment,
                comment_author=EXCLUDED.comment_author,
                updated_at=NOW(),
                is_deleted=FALSE
        """, t)
    conn.commit()
    cur.close()
    conn.close()
    return actual_ids

def mark_deleted_tasks(actual_ids):
    if not actual_ids:
        return
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    # Пометить как удалённые все задачи, которых нет в актуальном списке
    cur.execute("""
        UPDATE planfix_tasks
        SET is_deleted = TRUE
        WHERE planfix_id NOT IN %s
    """, (tuple(actual_ids),))
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    all_tasks = []
    all_ids = []
    page = 1
    while True:
        xml = get_planfix_tasks(page)
        if page == 1:
            print("----- XML-ответ первой страницы -----")
            print(xml[:2000])
            print("----- Конец XML-ответа -----")
        tasks = parse_tasks(xml)
        if not tasks:
            break
        ids = upsert_tasks(tasks)
        all_tasks.extend(tasks)
        all_ids.extend(ids)
        print(f"Загружено задач на странице {page}: {len(tasks)}")
        if len(tasks) < 100:
            break
        page += 1
    print(f"Всего загружено задач: {len(all_tasks)}")
    mark_deleted_tasks(all_ids)
    print("Удалённые задачи помечены.")
