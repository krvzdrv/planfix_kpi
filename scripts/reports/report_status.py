import psycopg2
import psycopg2.extras
import requests
from datetime import datetime, date, timedelta
import os
import logging
from dotenv import load_dotenv
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.config import MANAGERS_KPI
from core.kpi_utils import math_round

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
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

HISTORY_TABLE_NAME = "report_clients_status_history"
logger = logging.getLogger(__name__)

# Статусы клиентов и их порядок в отчёте
CLIENT_STATUSES = ['NWI', 'WTR', 'PSK', 'PIZ', 'STL', 'NAK', 'REZ', 'BRK', 'ARC']

# Сопоставление для статусов, чья логика НЕ зависит от дат (кроме STL)
STATUS_MAPPING = {
    'Nowi': 'NWI',
    'W trakcie': 'WTR',
    'Perspektywiczni': 'PSK',
    'Pierwsze zamówienie': 'PIZ',
    'Stali klienci': 'STL',
    'Rezygnacja': 'REZ',
    'Brak kontaktu': 'BRK',
    'Archiwum': 'ARC'
}

# Сопоставление статусов с их полем даты для расчета ПРИТОКА
STATUS_INFLOW_DATE_COLS = {
    'NWI': 'data_dodania_do_nowi',
    'WTR': 'data_dodania_do_w_trakcie',
    'PSK': 'data_dodania_do_perspektywiczni',
    'PIZ': 'data_pierwszego_zamowienia',
    'REZ': 'data_dodania_do_rezygnacja',
    'BRK': 'data_dodania_do_brak_kontaktu',
    'ARC': 'data_dodania_do_archiwum',
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

def get_current_statuses_and_inflow(conn, manager: str, today: date) -> (dict, dict, dict):
    """
    Возвращает три словаря:
    1. Абсолютное количество клиентов в каждом статусе на сегодня.
    2. Дневной приток клиентов (для статусов с датой входа).
    3. Дневной отток клиентов (для статусов с датой выхода).
    """
    # 1. Рассчитываем АБСОЛЮТНЫЕ значения на сегодня
    query = "SELECT status_wspolpracy, data_ostatniego_zamowienia FROM planfix_clients WHERE menedzer = %s AND is_deleted = false AND status_wspolpracy IS NOT NULL AND status_wspolpracy != ''"
    params = (manager,)
    results = _execute_query(conn, query, params, f"current statuses for {manager}")

    current_totals = {status: 0 for status in CLIENT_STATUSES}
    for full_status, last_order_date in results:
        status_clean = full_status.strip()
        if status_clean == 'Stali klienci':
            days_diff = float('inf')
            if last_order_date and last_order_date.strip():
                try:
                    days_diff = (today - datetime.strptime(last_order_date.strip()[:10], '%d-%m-%Y').date()).days
                except (ValueError, TypeError):
                    pass
            short_status = 'STL' if days_diff <= 30 else 'NAK'
        else:
            short_status = STATUS_MAPPING.get(status_clean)

        if short_status and short_status in current_totals:
            current_totals[short_status] += 1
            
    # 2. Рассчитываем ДНЕВНОЙ ПРИТОК
    daily_inflow = {status: 0 for status in CLIENT_STATUSES}
    for status, col_name in STATUS_INFLOW_DATE_COLS.items():
        query = f"SELECT COUNT(*) FROM planfix_clients WHERE menedzer = %s AND {col_name} IS NOT NULL AND {col_name} != '' AND TO_DATE({col_name}, 'DD-MM-YYYY') = %s AND is_deleted = false"
        params_inflow = (manager, today)
        (count,) = _execute_query(conn, query, params_inflow, f"inflow for {status}")[0]
        daily_inflow[status] = count

    # 3. Рассчитываем ДНЕВНОЙ ОТТОК (для статусов с датой выхода)
    daily_outflow = {status: 0 for status in CLIENT_STATUSES}
    # Для STL/NAK отток рассчитывается как разница со вчерашним днем
    # Для остальных - количество клиентов, которые ушли из статуса сегодня
    for status, col_name in STATUS_INFLOW_DATE_COLS.items():
        # Считаем клиентов, которые были в этом статусе вчера, но не сегодня
        yesterday = today - timedelta(days=1)
        query = f"""
        SELECT COUNT(*) FROM planfix_clients 
        WHERE menedzer = %s 
          AND {col_name} IS NOT NULL 
          AND {col_name} != '' 
          AND TO_DATE({col_name}, 'DD-MM-YYYY') < %s 
          AND TO_DATE({col_name}, 'DD-MM-YYYY') >= %s
          AND is_deleted = false
        """
        params_outflow = (manager, today, yesterday)
        (count,) = _execute_query(conn, query, params_outflow, f"outflow for {status}")[0]
        daily_outflow[status] = count

    return current_totals, daily_inflow, daily_outflow

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
    """Форматировать отчёт по статусам клиентов с IN/OUT."""
    total_sum = sum(data['current'] for data in changes.values())
    if total_sum == 0: total_sum = 1

    # Собираем все данные для каждого столбца
    current_values = []
    change_values = []
    inout_values = []
    percent_values = []
    
    change_strings = {}
    inout_strings = {}
    percent_strings = {}
    
    for status in CLIENT_STATUSES:
        data = changes[status]
        current = data['current']
        change = data['net']
        inflow = data['inflow']
        outflow = data['outflow']
        
        # Текущее количество
        current_str = str(current)
        current_values.append(current_str)
        
        # Изменение
        change_str = f"+{change}" if change > 0 else (str(change) if change < 0 else "")
        change_strings[status] = change_str
        change_values.append(change_str)
        
        # IN/OUT
        inout_str = f"[+{inflow}/-{outflow}]"
        inout_strings[status] = inout_str
        inout_values.append(inout_str)
        
        # Проценты БЕЗ скобок
        percentage = math_round(float(current) / float(total_sum) * 100)
        percent_str = f"{percentage}%"  # Убираем скобки
        percent_strings[status] = percent_str
        percent_values.append(percent_str)

    # Используем фиксированные ширины столбцов для всех менеджеров
    max_current_len = 6   # Фиксированная ширина для текущего количества
    max_change_len = 4    # Фиксированная ширина для изменений
    max_inout_len = 12    # Фиксированная ширина для [IN/OUT]
    max_percent_len = 4   # Фиксированная ширина для процентов

    max_bar_len = 4  # Еще больше уменьшаем максимальную длину бара
    lines = []
    
    for status in CLIENT_STATUSES:
        data = changes[status]
        current = data['current']
        indicator = data['direction']
        change_str = change_strings[status]
        inout_str = inout_strings[status]
        percent_str = percent_strings[status]

        # Бар
        bar_len = max(1, math_round(float(current) / float(global_max) * max_bar_len)) if global_max > 0 and current > 0 else 0
        bar_str = '█' * bar_len

        # Левая часть: "KPI BAR" - фиксированная ширина
        kpi_bar_part = f"{status} {bar_str}"
        
        # Формируем строку с фиксированными отступами между столбцами
        # Каждый столбец имеет фиксированную позицию от левого края
        line = (
            f"{kpi_bar_part:<10}"  # KPI + бар (позиции 1-10)
            f"{current:>6}"        # Текущее количество (позиции 11-16)
            f"  {change_str:>4} {indicator}"  # Изменение + направление (позиции 17-21)
            f"      {inout_str:>12}"     # IN/OUT (позиции 22-33)
            f" {percent_str:>4}"    # Проценты (позиции 34-37)
        )
        
        lines.append(line)

    return "\n".join(lines)

def send_to_telegram(message: str):
    """Отправить сообщение в Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
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
        all_managers_outflow = {}
        
        for manager in (m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_name']):
            totals, inflow, outflow = get_current_statuses_and_inflow(conn, manager, today)
            all_managers_totals[manager] = totals
            all_managers_inflow[manager] = inflow
            all_managers_outflow[manager] = outflow
            save_statuses_to_history(conn, today, manager, totals)

        global_max = get_global_max_count(all_managers_totals)
        logger.info(f"Global max count for today is: {global_max}")

        yesterday = today - timedelta(days=1)
        
        # Используем фиксированные ширины для всех менеджеров
        global_max_current_len = 6   # Фиксированная ширина для текущего количества
        global_max_change_len = 4    # Фиксированная ширина для изменений
        
        all_reports = []
        for manager, current_totals in all_managers_totals.items():
            report_body = ""
            try:
                logger.info(f"Processing report for manager: {manager}")
                
                previous_stl_nak = get_statuses_from_history(conn, yesterday, manager)
                
                status_changes = {}
                for status in CLIENT_STATUSES:
                    curr_count = current_totals.get(status, 0)
                    inflow = all_managers_inflow[manager].get(status, 0)
                    outflow = all_managers_outflow[manager].get(status, 0)
                    
                    if status in ['STL', 'NAK']:
                        # Динамика для STL/NAK - чистая разница со вчера
                        prev_count = previous_stl_nak.get(status, 0)
                        diff = curr_count - prev_count
                    else:
                        # Динамика для остальных - дневной приток
                        diff = inflow

                    direction = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
                    status_changes[status] = {
                        'current': curr_count, 
                        'net': diff, 
                        'direction': direction,
                        'inflow': inflow,
                        'outflow': outflow
                    }
                
                logger.info(f"Got status changes for {manager}: {status_changes}")
                
                # Формируем тело отчета (строки с KPI)
                report_kpi_lines = format_client_status_report(status_changes, global_max)
                
                # Формируем полный текст сообщения для одного менеджера
                # Заголовок теперь будет общий, а здесь только имя менеджера
                manager_header = f"👤 {manager}:"
                separator = "──────────────────────────────────"
                total_sum = sum(data['current'] for data in status_changes.values())
                total_net = sum(data['net'] for data in status_changes.values())
                
                # Формируем итоговую строку с правильным выравниванием
                total_current_str = str(total_sum)
                total_change_str = f"+{total_net}" if total_net > 0 else (str(total_net) if total_net < 0 else "")
                
                # Используем уже рассчитанные глобальные максимальные длины
                
                footer = (
                    f"RZM{'':<7}"     # RZM (позиции 1-10, как KPI+бар)
                    f"{total_current_str:>6}"  # Текущее количество (позиции 11-16)
                    f"  {total_change_str:>4}"   # Изменение (позиции 17-20, без индикатора)
                )

                full_report_for_manager = f"{manager_header}\n\n{report_kpi_lines}\n{separator}\n{footer}"
                all_reports.append(full_report_for_manager)
                
                logger.info(f"Generated report for {manager}:\n{full_report_for_manager}")

            except Exception as e:
                logger.error(f"Failed to generate report for {manager}: {e}", exc_info=True)
                error_message = f"Error generating report for {manager}: {e}"
                all_reports.append(error_message)
        
        # Отправляем один общий отчет
        if all_reports:
            final_report_header = f"WORONKA_{today.strftime('%d.%m.%Y')}"
            final_report = f"```{final_report_header}\n\n" + "\n\n".join(all_reports) + "\n```"
            send_to_telegram(final_report)

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