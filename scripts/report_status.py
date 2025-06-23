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

# Статусы клиентов и их порядок в отчёте
CLIENT_STATUSES = ['NWI', 'WTR', 'PSK', 'PIZ', 'STL', 'NAK', 'REZ']

# Сопоставление для статусов, чья логика НЕ зависит от дат (кроме STL)
STATUS_MAPPING = {
    'Nowi': 'NWI',
    'W trakcie': 'WTR',
    'Perspektywiczni': 'PSK',
    'Pierwsze zamówienie': 'PIZ',
    'Stali klienci': 'STL',
    'Rezygnacja': 'REZ'
}

# Сопоставление статусов с их полем даты для расчета ПРИТОКА
STATUS_INFLOW_DATE_COLS = {
    'NWI': 'data_dodania_do_nowi',
    'WTR': 'data_dodania_do_w_trakcie',
    'PSK': 'data_dodania_do_perspektywiczni',
    'PIZ': 'data_pierwszego_zamowienia',
    'REZ': 'data_dodania_do_rezygnacja',
}

def _execute_query(conn, query: str, params: tuple = (), description: str = "") -> list:
    """Выполняет запрос с использованием существующего соединения."""
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            return rows
    except psycopg2.Error as e:
        logger.error(f"Database error during query for {description}: {e}")
        raise

def create_history_table_if_not_exists(conn):
    """Создает таблицу для хранения истории ТОЛЬКО для STL и NAK."""
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
            logger.info(f"Checking/Creating history table for STL/NAK: {HISTORY_TABLE_NAME}...")
            cur.execute(query)
            conn.commit()
            logger.info(f"Table {HISTORY_TABLE_NAME} is ready.")
    except psycopg2.Error as e:
        logger.error(f"Error creating history table: {e}")
        conn.rollback()
        raise

def save_statuses_to_history(conn, report_date: date, manager: str, statuses: dict):
    """Сохраняет дневной срез статусов STL и NAK в таблицу истории."""
    query = f"""
    INSERT INTO {HISTORY_TABLE_NAME} (report_date, manager, status, count)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (report_date, manager, status) DO UPDATE SET
        count = EXCLUDED.count;
    """
    records = [(report_date, manager, status, count) for status, count in statuses.items() if status in ['STL', 'NAK']]
    if not records:
        return
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, records)
            conn.commit()
            logger.info(f"Saved {len(records)} STL/NAK records to history for {manager} on {report_date}.")
    except psycopg2.Error as e:
        logger.error(f"Error saving statuses to history for {manager}: {e}")
        conn.rollback()
        raise

def get_statuses_from_history(conn, report_date: date, manager: str) -> dict:
    """Получает статусы STL и NAK из таблицы истории за определенную дату."""
    query = f"SELECT status, count FROM {HISTORY_TABLE_NAME} WHERE report_date = %s AND manager = %s AND status IN ('STL', 'NAK');"
    params = (report_date, manager)
    results = _execute_query(conn, query, params, f"STL/NAK history for {manager} on {report_date}")
    statuses = {'STL': 0, 'NAK': 0}
    for status, count in results:
        if status in statuses:
            statuses[status] = count
    return statuses

def get_current_statuses_and_inflow(conn, manager: str, today: date) -> (dict, dict):
    """
    Возвращает два словаря:
    1. Абсолютное количество клиентов в каждом статусе на сегодня.
    2. Дневной приток клиентов (для статусов с датой входа).
    """
    # 1. Рассчитываем АБСОЛЮТНЫЕ значения на сегодня
    query = "SELECT status_wspolpracy, data_ostatniego_zamowienia FROM planfix_clients WHERE menedzer = %s AND is_deleted = false AND status_wspolpracy IS NOT NULL AND status_wspolpracy != ''"
    params = (manager,)
    results = _execute_query(conn, query, params, f"current statuses for {manager}")

    current_totals = {status: 0 for status in CLIENT_STATUSES}
    for full_status, last_order_date in results:
        short_status = ''
        if full_status == 'Stali klienci':
            days_diff = float('inf')
            if last_order_date and last_order_date != '':
                try:
                    days_diff = (today - datetime.strptime(last_order_date[:10], '%d-%m-%Y').date()).days
                except (ValueError, TypeError): pass
            short_status = 'STL' if days_diff <= 30 else 'NAK'
        else:
            short_status = STATUS_MAPPING.get(full_status)

        if short_status and short_status in current_totals:
            current_totals[short_status] += 1
            
    # 2. Рассчитываем ДНЕВНОЙ ПРИТОК
    daily_inflow = {status: 0 for status in CLIENT_STATUSES}
    for status, col_name in STATUS_INFLOW_DATE_COLS.items():
        query = f"SELECT COUNT(*) FROM planfix_clients WHERE menedzer = %s AND {col_name} IS NOT NULL AND {col_name} != '' AND TO_DATE({col_name}, 'DD-MM-YYYY') = %s AND is_deleted = false"
        params_inflow = (manager, today)
        (count,) = _execute_query(conn, query, params_inflow, f"inflow for {status}")[0]
        daily_inflow[status] = count

    return current_totals, daily_inflow

def get_global_max_count(all_managers_data: dict) -> int:
    """Получить глобальный максимум из словаря {manager: {status: count}}."""
    global_max = 0
    if all_managers_data:
        for data in all_managers_data.values():
            if data and data.values():
                 max_val = max(data.values())
                 if max_val > global_max:
                    global_max = max_val
    return global_max if global_max > 0 else 1 # Избегаем деления на ноль

def format_client_status_report(changes: dict, global_max: int) -> str:
    """Форматировать отчёт по статусам клиентов в соответствии с ТЗ."""
    total_sum = sum(data['current'] for data in changes.values())
    if total_sum == 0: total_sum = 1

    max_change_str_len = 0
    change_strings = {}
    for status in CLIENT_STATUSES:
        change = changes[status]['change']
        s = f"+{change}" if change > 0 else (str(change) if change < 0 else "")
        change_strings[status] = s
        max_change_str_len = max(max_change_str_len, len(s))

    # Макс. длина бара = 9.
    # Левая часть будет 18 символов, правая 12.
    max_bar_len = 9

    lines = []
    for status in CLIENT_STATUSES:
        data = changes[status]
        current = data['current']
        indicator = data['direction']

        bar_len = max(1, round(current / global_max * max_bar_len)) if global_max > 0 and current > 0 else 0
        bar_str = '█' * bar_len

        # Левая часть: "KPI BAR  VALUE" - 18 символов.
        # Поле для KPI(3), пробела(1) и бара с отступом = 18 - 3(value) = 15.
        kpi_bar_part = f"{status} {bar_str}"
        left_part = f"{kpi_bar_part:<15}{current:>3}"

        # Правая часть: " INDICATOR CHANGE (PERCENT)" - 12 символов.
        change_str = change_strings[status]
        change_part = f" {indicator} {change_str}".ljust(3 + max_change_str_len)

        percentage = round(current / total_sum * 100)
        percent_str = f"({percentage}%)"

        padding_len = 12 - len(change_part) - len(percent_str)
        right_part = f"{change_part}{' ' * max(0, padding_len)}{percent_str}"

        lines.append(f"{left_part}{right_part}")

    return "\n".join(lines)

def send_to_telegram(message: str):
    """Отправить сообщение в Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        # Возвращаемся к HTML <pre> для корректного отображения моноширинного текста
        payload = {'chat_id': CHAT_ID, 'text': f"<pre>{message}</pre>", 'parse_mode': 'HTML'}
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Message sent successfully to Telegram")
        else:
            logger.error(f"Failed to send message to Telegram: {response.text}")
    except Exception as e:
        logger.error(f"Error sending to Telegram: {str(e)}")

def main():
    """Основная функция для генерации и отправки отчёта."""
    today = date.today()
    logger.info(f"Starting client status report generation for date: {today}")

    conn = None
    try:
        conn = psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT)
        create_history_table_if_not_exists(conn)

        all_managers_totals = {}
        all_managers_inflow = {}
        
        for manager in (m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_name']):
            totals, inflow = get_current_statuses_and_inflow(conn, manager, today)
            all_managers_totals[manager] = totals
            all_managers_inflow[manager] = inflow
            save_statuses_to_history(conn, today, manager, totals)

        global_max = get_global_max_count(all_managers_totals)
        logger.info(f"Global max count for today is: {global_max}")

        yesterday = today - timedelta(days=1)
        
        final_report_parts = []
        for manager, totals in all_managers_totals.items():
            yesterday_statuses = get_statuses_from_history(conn, yesterday, manager)
            changes = {}
            for s in CLIENT_STATUSES:
                current_val = totals.get(s, 0)
                prev_val = yesterday_statuses.get(s, 0)
                change = current_val - prev_val
                inflow_val = all_managers_inflow.get(manager, {}).get(s, 0)
                
                direction_symbol = '→' # без изменений
                if inflow_val > 0:
                    direction_symbol = '↗' # приток
                elif change < 0:
                    direction_symbol = '↘' # отток
                
                changes[s] = {'current': current_val, 'change': change, 'direction': direction_symbol}

            manager_name_for_report = manager.split()[0]
            report_for_manager = format_client_status_report(changes, global_max)
            final_report_parts.append(f"👨‍💻 {manager_name_for_report}\n{report_for_manager}")

        today_str = today.strftime('%d.%m.%Y')
        full_report = f"📊 STATUS_{today_str}\n\n" + "\n\n".join(final_report_parts)
        
        logger.info("Full report generated. Sending to Telegram.")
        send_to_telegram(full_report)

    except psycopg2.Error as e:
        logger.error(f"Database connection error: {e}", exc_info=True)
        send_to_telegram(f"Database connection error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        send_to_telegram(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    main()