import psycopg2
import psycopg2.extras
import requests
from datetime import datetime, date, timedelta
import os
import logging
from dotenv import load_dotenv
import sys
sys.path.insert(0, os.path.dirname(__file__))
from config import MANAGERS_KPI

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID_CLIENTS', '-1001866680518')  # Специальный чат для отчёта по клиентам

HISTORY_TABLE_NAME = "report_clients_status_history"
logger = logging.getLogger(__name__)

# Статусы клиентов и их порядок в отчёте (сокращённые названия)
CLIENT_STATUSES = ['NWI', 'WTR', 'PSK', 'PIZ', 'STL', 'NAK', 'REZ']

# Сопоставление полных названий статусов с сокращёнными
STATUS_MAPPING = {
    'Nowi': 'NWI',
    'W trakcie': 'WTR',
    'Perspektywiczni': 'PSK',
    'Pierwsze zamówienie': 'PIZ',
    'Stali klienci': 'STL', # Важно - полное имя для сопоставления
    'Rezygnacja': 'REZ'
}

def _execute_query(conn, query: str, params: tuple, description: str) -> list:
    """Выполняет запрос с использованием существующего соединения."""
    try:
        with conn.cursor() as cur:
            # logger.info(f"Executing query for: {description} with params: {params}")
            cur.execute(query, params)
            rows = cur.fetchall()
            # logger.info(f"Query for {description} returned {len(rows)} rows.")
            return rows
    except psycopg2.Error as e:
        logger.error(f"Database error during query for {description}: {e}")
        raise

def create_history_table_if_not_exists(conn):
    """Создает таблицу для хранения истории статусов, если она не существует."""
    query = f"""
    CREATE TABLE IF NOT EXISTS {HISTORY_TABLE_NAME} (
        report_date DATE NOT NULL,
        manager TEXT NOT NULL,
        status TEXT NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY (report_date, manager, status)
    );
    """
    try:
        with conn.cursor() as cur:
            logger.info(f"Checking/Creating history table: {HISTORY_TABLE_NAME}...")
            cur.execute(query)
            conn.commit()
            logger.info(f"Table {HISTORY_TABLE_NAME} is ready.")
    except psycopg2.Error as e:
        logger.error(f"Error creating history table: {e}")
        conn.rollback()
        raise

def save_statuses_to_history(conn, report_date: date, manager: str, statuses: dict):
    """Сохраняет дневной срез статусов в таблицу истории."""
    query = f"""
    INSERT INTO {HISTORY_TABLE_NAME} (report_date, manager, status, count)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (report_date, manager, status) DO UPDATE SET
        count = EXCLUDED.count;
    """
    records = [(report_date, manager, status, count) for status, count in statuses.items()]
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, records)
            conn.commit()
            logger.info(f"Saved {len(records)} records to history for {manager} on {report_date}.")
    except psycopg2.Error as e:
        logger.error(f"Error saving statuses to history for {manager}: {e}")
        conn.rollback()
        raise

def get_statuses_from_history(conn, report_date: date, manager: str) -> dict:
    """Получает статусы из таблицы истории за определенную дату."""
    query = f"SELECT status, count FROM {HISTORY_TABLE_NAME} WHERE report_date = %s AND manager = %s;"
    params = (report_date, manager)
    
    results = _execute_query(conn, query, params, f"history for {manager} on {report_date}")

    statuses = {status: 0 for status in CLIENT_STATUSES}
    for status, count in results:
        if status in statuses:
            statuses[status] = count
    return statuses


def get_client_statuses(conn, manager: str, current_date: date) -> dict:
    """Получить текущие статусы клиентов для менеджера."""
    query = """
    SELECT
        status_wspolpracy as status,
        data_ostatniego_zamowienia
    FROM planfix_clients
    WHERE menedzer = %s AND is_deleted = false AND status_wspolpracy IS NOT NULL AND status_wspolpracy != ''
    """
    params = (manager,)
    results = _execute_query(conn, query, params, f"current statuses for {manager}")

    status_counts = {status: 0 for status in CLIENT_STATUSES}

    for full_status, last_order_date in results:
        short_status = ''
        if full_status == 'Stali klienci':
            days_diff = None
            if last_order_date and last_order_date != '':
                try:
                    if len(last_order_date) >= 10:
                        order_date = datetime.strptime(last_order_date[:10], '%d-%m-%Y').date()
                        days_diff = (current_date - order_date).days
                except (ValueError, TypeError):
                    pass
            
            if days_diff is not None and days_diff <= 30:
                short_status = 'STL'
            else:
                short_status = 'NAK'
        else:
            short_status = STATUS_MAPPING.get(full_status, full_status)

        if short_status in status_counts:
            status_counts[short_status] += 1
    
    return status_counts

def get_global_max_count(managers_data: dict) -> int:
    """Получить глобальный максимум количества клиентов среди всех статусов и всех менеджеров."""
    global_max = 0
    if managers_data:
        for manager_data in managers_data.values():
            if manager_data:
                 max_val = max(manager_data.values())
                 if max_val > global_max:
                    global_max = max_val
    return global_max

def format_progress_bar(value: int, max_value: int, width: int = 14) -> str:
    """Форматировать прогресс-бар из символов █."""
    if max_value == 0:
        return ' ' * width
    filled = int(round(width * value / max_value)) if max_value > 0 else 0
    return '█' * filled + ' ' * (width - filled)

def format_client_status_report(manager: str, status_changes: dict, global_max: int) -> str:
    """Форматировать отчёт по статусам клиентов для одного менеджера."""
    total = sum(data['current'] for data in status_changes.values())
    
    lines = []
    lines.append(f"{manager} {date.today().strftime('%d.%m.%Y')}\n")
    
    for status in CLIENT_STATUSES:
        data = status_changes[status]
        current = data['current']
        change = data['change']
        direction = data['direction']
        percentage = (current / total * 100) if total > 0 else 0
        
        max_count = global_max
        
        if change > 0:
            change_str = f"{direction} +{change:2d}"
        elif change < 0:
            change_str = f"{direction} {change:3d}"
        else:
            change_str = f"{direction}     "
        
        status_line = f"{status} {format_progress_bar(current, max_count)}{current:3d} {change_str} ({percentage:2.0f}%)"
        lines.append(status_line)
    
    lines.append("─" * 32)
    lines.append(f"👥 Wszyscy klienci: {total:8d}")
    
    return "\n".join(lines)

def send_to_telegram(message: str):
    """Отправить сообщение в Telegram."""
    try:
        # logger.info(f"Attempting to send message to Telegram chat {CHAT_ID}")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': f"```\n{message}\n```",
            'parse_mode': 'Markdown'
        }
        # logger.info(f"Sending request to Telegram API...")
        response = requests.post(url, json=payload, timeout=10)
        # logger.info(f"Telegram API response status code: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Failed to send message to Telegram: {response.text}")
        else:
            logger.info("Message sent successfully to Telegram")
    except Exception as e:
        logger.error(f"Error sending to Telegram: {str(e)}")
        raise

def main():
    """Основная функция для генерации и отправки отчёта."""
    today = date.today()
    logger.info(f"Starting client status report generation for date: {today}")

    conn = None
    try:
        conn = psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT)
        create_history_table_if_not_exists(conn)

        all_managers_current_statuses = {}
        for manager in (m['planfix_user_name'] for m in MANAGERS_KPI):
            all_managers_current_statuses[manager] = get_client_statuses(conn, manager, today)

        global_max = get_global_max_count(all_managers_current_statuses)
        logger.info(f"Global max count for today is: {global_max}")

        yesterday = today - timedelta(days=1)

        for manager, current_statuses in all_managers_current_statuses.items():
            try:
                logger.info(f"Processing report for manager: {manager}")
                
                save_statuses_to_history(conn, today, manager, current_statuses)
                previous_statuses = get_statuses_from_history(conn, yesterday, manager)
                
                status_changes = {}
                for status in CLIENT_STATUSES:
                    curr_count = current_statuses.get(status, 0)
                    prev_count = previous_statuses.get(status, 0)
                    diff = curr_count - prev_count
                    
                    if diff > 0:
                        direction = "▲"
                    elif diff < 0:
                        direction = "▼"
                    else:
                        direction = "➖"
                        
                    status_changes[status] = {
                        'current': curr_count,
                        'change': diff,
                        'direction': direction
                    }
                
                logger.info(f"Got status changes for {manager}: {status_changes}")
                report = format_client_status_report(manager, status_changes, global_max)
                
                logger.info(f"Sending report for {manager} to Telegram")
                send_to_telegram(report)
            
            except Exception as e:
                logger.error(f"Error processing report for {manager}: {str(e)}")
                logger.exception("Full traceback:")

    except (psycopg2.Error, ValueError) as e:
        logger.critical(f"Database or configuration error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    logger.info("Client status report script started")
    main()
    logger.info("Client status report script finished") 