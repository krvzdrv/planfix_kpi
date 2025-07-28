import os
import sys
import logging
from datetime import datetime
import xml.etree.ElementTree as ET
import psycopg2
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.planfix_utils as planfix_utils

# Константы для скрипта
ANALYTICS_TABLE_NAME = "planfix_analytics"
ANALYTICS_PK_COLUMN = "id"

# Список ключей аналитик для получения данных
# Эти ключи нужно получить из action.get для конкретных действий
ANALYTIC_KEYS = [
    # Здесь нужно добавить ключи аналитик по продуктам
    # Например: 12345, 67890, etc.
]

logger = logging.getLogger(__name__)

def get_planfix_analytics_data(analytic_keys):
    """
    Получает данные аналитик из ПланФикса через API analitic.getData
    """
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    
    # Формируем XML для запроса analitic.getData
    analytic_keys_xml = ""
    for key in analytic_keys:
        analytic_keys_xml += f"<key>{key}</key>"
    
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<request method="analitic.getData">'
        f'<account>{planfix_utils.PLANFIX_ACCOUNT}</account>'
        '<auth>'
        f'<key>{planfix_utils.PLANFIX_API_KEY}</key>'
        f'<user_token>{planfix_utils.PLANFIX_TOKEN}</user_token>'
        '</auth>'
        '<analiticKeys>'
        f'{analytic_keys_xml}'
        '</analiticKeys>'
        '</request>'
    )
    
    response = requests.post(
        planfix_utils.PLANFIX_API_URL,
        data=body.encode('utf-8'),
        headers=headers
    )
    response.raise_for_status()
    return response.text

def parse_analytics_data(xml_text):
    """
    Парсит XML ответ от API analitic.getData
    """
    root = ET.fromstring(xml_text)
    if root.attrib.get("status") == "error":
        code = root.findtext("code")
        message = root.findtext("message")
        logger.error(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    
    analytics_data = []
    
    # Парсим analiticDatas
    for analitic_data in root.findall('.//analiticData'):
        key = analitic_data.findtext('key')
        if key is None:
            continue
            
        # Парсим itemData для каждой аналитики
        for item_data in analitic_data.findall('.//itemData'):
            item_id = item_data.findtext('id')
            name = item_data.findtext('name')
            value = item_data.findtext('value')
            value_id = item_data.findtext('valueId')
            
            analytics_data.append({
                "id": f"{key}_{item_id}" if item_id else f"{key}_{len(analytics_data)}",
                "analitic_key": int(key) if key else None,
                "item_id": int(item_id) if item_id else None,
                "name": name,
                "value": value,
                "value_id": value_id,
                "updated_at": datetime.now(),
                "is_deleted": False
            })
    
    return analytics_data

def get_create_table_sql(table_name, pk_column, columns_map):
    """
    Генерирует SQL для создания таблицы
    """
    column_definitions = [f'"{name}" {dtype}' for name, dtype in columns_map.items()]
    # Устанавливаем первичный ключ
    for i, col_def in enumerate(column_definitions):
        if col_def.startswith(f'"{pk_column}"'):
            column_definitions[i] = f'"{pk_column}" TEXT PRIMARY KEY'
            break
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(column_definitions)});'

def main():
    """
    Главная функция для экспорта аналитических данных из Planfix в Supabase
    """
    logger.info("--- Starting Planfix analytics export ---")
    
    # Проверяем обязательные переменные окружения
    planfix_utils.check_required_env_vars({
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_TOKEN': planfix_utils.PLANFIX_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
    })

    conn = None
    try:
        # Проверяем, есть ли ключи аналитик для обработки
        if not ANALYTIC_KEYS:
            logger.warning("No analytic keys defined. Please add ANALYTIC_KEYS to the script.")
            return

        logger.info(f"Fetching analytics data for keys: {ANALYTIC_KEYS}")
        
        # Получаем данные аналитик из ПланФикса
        xml_text = get_planfix_analytics_data(ANALYTIC_KEYS)
        analytics_data = parse_analytics_data(xml_text)
        
        logger.info(f"Total analytics records processed: {len(analytics_data)}")

        if not analytics_data:
            logger.info("No analytics data to update. Exiting.")
            return

        # Подключаемся к Supabase
        conn = planfix_utils.get_supabase_connection()

        # Определяем структуру таблицы
        columns_map = {
            "id": "TEXT",
            "analitic_key": "INTEGER",
            "item_id": "INTEGER", 
            "name": "TEXT",
            "value": "TEXT",
            "value_id": "TEXT",
            "updated_at": "TIMESTAMP",
            "is_deleted": "BOOLEAN"
        }

        # Создаем таблицу если она не существует
        create_sql = get_create_table_sql(ANALYTICS_TABLE_NAME, ANALYTICS_PK_COLUMN, columns_map)
        planfix_utils.create_table_if_not_exists(conn, create_sql)

        # Добавляем недостающие колонки
        planfix_utils.add_missing_columns(conn, ANALYTICS_TABLE_NAME, columns_map)

        # Получаем финальный список колонок из БД
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {ANALYTICS_TABLE_NAME} LIMIT 0")
            db_column_names = [desc[0] for desc in cur.description]

        # Обновляем данные в Supabase
        planfix_utils.upsert_data_to_supabase(
            conn,
            ANALYTICS_TABLE_NAME,
            ANALYTICS_PK_COLUMN,
            db_column_names,
            analytics_data
        )

        # Получаем список всех ID для пометки удаленных записей
        all_ids = [item["id"] for item in analytics_data if item.get("id")]
        
        # Помечаем записи как удаленные
        planfix_utils.mark_items_as_deleted_in_supabase(
            conn,
            ANALYTICS_TABLE_NAME,
            ANALYTICS_PK_COLUMN,
            all_ids
        )

        logger.info("--- Planfix analytics export finished successfully ---")

    except Exception as e:
        logger.critical(f"An error occurred in the main process: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            logger.info("Supabase connection closed.")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    main() 