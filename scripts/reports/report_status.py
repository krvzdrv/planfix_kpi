import psycopg2
import psycopg2.extras
import requests
from datetime import datetime, date, timedelta
import os
import logging
from dotenv import load_dotenv
import sys
from functools import lru_cache
import hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.config import MANAGERS_KPI
from core.kpi_utils import math_round

# Load environment variables from .env file
load_dotenv()

def count_workdays(start_date, end_date):
    """
    Подсчитывает количество рабочих дней между двумя датами (исключая выходные).
    
    Args:
        start_date: дата начала (date)
        end_date: дата окончания (date)
    
    Returns:
        int: количество рабочих дней
    """
    if start_date > end_date:
        return 0
    
    workdays = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Понедельник = 0, Воскресенье = 6
        if current_date.weekday() < 5:  # 0-4 = понедельник-пятница
            workdays += 1
        current_date += timedelta(days=1)
    
    return workdays

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
    # 1. Рассчитываем АБСОЛЮТНЫЕ значения на сегодня (ВОЗВРАЩАЕМ СТАРУЮ ЛОГИКУ)
    query = "SELECT status_wspolpracy, data_ostatniego_zamowienia FROM planfix_clients WHERE menedzer = %s AND is_deleted = false AND status_wspolpracy IS NOT NULL AND status_wspolpracy != ''"
    params = (manager,)
    results = _execute_query(conn, query, params, f"current statuses for {manager}")

    current_totals = {status: 0 for status in CLIENT_STATUSES}
    for full_status, last_order_date in results:
        status_clean = full_status.strip()
        if status_clean == 'Stali klienci':
            workdays_diff = float('inf')
            if last_order_date and last_order_date.strip():
                try:
                    order_date = datetime.strptime(last_order_date.strip()[:10], '%d-%m-%Y').date()
                    workdays_diff = count_workdays(order_date, today)
                except (ValueError, TypeError):
                    pass
            short_status = 'STL' if workdays_diff <= 30 else 'NAK'
        else:
            short_status = STATUS_MAPPING.get(status_clean)

        if short_status and short_status in current_totals:
            current_totals[short_status] += 1
            
    # 2. Рассчитываем ДНЕВНОЙ ПРИТОК по реальным переходам
    daily_inflow = {status: 0 for status in CLIENT_STATUSES}
    yesterday = today - timedelta(days=1)
    
    # Получаем списки клиентов по статусам на вчера и сегодня
    yesterday_clients = get_clients_by_status_for_date(conn, manager, yesterday)
    today_clients = get_clients_by_status_for_date(conn, manager, today)
    
    # Рассчитываем приток как количество клиентов, которые пришли в статус
    for status in CLIENT_STATUSES:
        yesterday_set = yesterday_clients.get(status, set())
        today_set = today_clients.get(status, set())
        
        # Приток = клиенты, которые НЕ были в статусе вчера, но в статусе сегодня
        inflow_clients = today_set - yesterday_set
        daily_inflow[status] = len(inflow_clients)

    # 3. Рассчитываем ДНЕВНОЙ ОТТОК по правильной логике
    daily_outflow = {status: 0 for status in CLIENT_STATUSES}
    
    # Рассчитываем отток как количество клиентов, которые покинули статус
    for status in CLIENT_STATUSES:
        yesterday_set = yesterday_clients.get(status, set())
        today_set = today_clients.get(status, set())
        
        # Отток = клиенты, которые были в статусе вчера, но НЕ в статусе сегодня
        outflow_clients = yesterday_set - today_set
        daily_outflow[status] = len(outflow_clients)
        
        # Отладочная информация для WTR
        if status == 'WTR' and len(outflow_clients) > 0:
            logger.info(f"WTR outflow clients: {outflow_clients}")
        if status == 'WTR' and daily_inflow[status] > 0:
            logger.info(f"WTR inflow clients: {today_set - yesterday_set}")
            
    # Дополнительная отладочная информация для понимания переходов
    if manager == 'Stukalo Nazarii':
        logger.info(f"=== DEBUG INFO for {manager} ===")
        logger.info(f"WTR inflow: {daily_inflow['WTR']} clients")
        logger.info(f"WTR outflow: {daily_outflow['WTR']} clients")
        logger.info(f"NWI inflow: {daily_inflow['NWI']} clients")
        logger.info(f"NWI outflow: {daily_outflow['NWI']} clients")
        logger.info("=== END DEBUG ===")

    return current_totals, daily_inflow, daily_outflow

def get_client_status_on_date(client_data, target_date):
    """Определяет, в каком статусе был клиент на определенную дату"""
    
    # Собираем все даты статусов (кроме STL/NAK)
    status_dates = {
        'NWI': client_data.get('data_dodania_do_nowi'),
        'WTR': client_data.get('data_dodania_do_w_trakcie'),
        'PSK': client_data.get('data_dodania_do_perspektywiczni'),
        'PIZ': client_data.get('data_pierwszego_zamowienia'),
        'REZ': client_data.get('data_dodania_do_rezygnacja'),
        'BRK': client_data.get('data_dodania_do_brak_kontaktu'),
        'ARC': client_data.get('data_dodania_do_archiwum')
    }
    
    # Находим самую последнюю дату, которая <= target_date
    latest_date = None
    status_on_date = None
    
    for status, date_str in status_dates.items():
        if date_str and date_str.strip():
            try:
                date_obj = datetime.strptime(date_str.strip()[:10], '%d-%m-%Y').date()
                
                # Берем только даты <= целевой даты
                if date_obj <= target_date:
                    if latest_date is None or date_obj > latest_date:
                        latest_date = date_obj
                        status_on_date = status
            except:
                continue
    
    # Для STL/NAK - особая логика (если нет других статусов или после PIZ)
    if status_on_date is None and client_data.get('status_wspolpracy') == 'Stali klienci':
        last_order_date = client_data.get('data_ostatniego_zamowienia')
        if last_order_date and last_order_date.strip():
            try:
                order_date = datetime.strptime(last_order_date.strip()[:10], '%d-%m-%Y').date()
                workdays_diff = count_workdays(order_date, target_date)
                status_on_date = 'STL' if workdays_diff <= 30 else 'NAK'
            except:
                status_on_date = 'NAK'
        else:
            status_on_date = 'NAK'
    
    # Если у клиента нет никаких дат, но он в статусе "Stali klienci"
    # это значит он был добавлен давно и перешел в STL/NAK
    if status_on_date is None and client_data.get('status_wspolpracy') == 'Stali klienci':
        status_on_date = 'NAK'  # По умолчанию NAK если нет даты заказа
    
    return status_on_date

def get_current_statuses_for_date(conn, manager: str, target_date: date) -> dict:
    """Получает статусы клиентов на определенную дату"""
    
    query = """
    SELECT id, status_wspolpracy, data_ostatniego_zamowienia,
           data_dodania_do_nowi, data_dodania_do_w_trakcie,
           data_dodania_do_perspektywiczni, data_pierwszego_zamowienia,
           data_dodania_do_rezygnacja, data_dodania_do_brak_kontaktu,
           data_dodania_do_archiwum
    FROM planfix_clients 
    WHERE menedzer = %s AND is_deleted = false
    """
    params = (manager,)
    results = _execute_query(conn, query, params, f"statuses for {manager} on {target_date}")

    current_totals = {status: 0 for status in CLIENT_STATUSES}
    
    for row in results:
        client_data = {
            'id': row[0],
            'status_wspolpracy': row[1],
            'data_ostatniego_zamowienia': row[2],
            'data_dodania_do_nowi': row[3],
            'data_dodania_do_w_trakcie': row[4],
            'data_dodania_do_perspektywiczni': row[5],
            'data_pierwszego_zamowienia': row[6],
            'data_dodania_do_rezygnacja': row[7],
            'data_dodania_do_brak_kontaktu': row[8],
            'data_dodania_do_archiwum': row[9]
        }
        
        # Определяем статус на целевую дату (по самой последней дате ≤ target_date)
        status_on_date = get_client_status_on_date(client_data, target_date)
        
        if status_on_date and status_on_date in current_totals:
            current_totals[status_on_date] += 1
    
    return current_totals

def get_clients_by_status_for_date(conn, manager: str, target_date: date) -> dict:
    """Получает списки клиентов по статусам на определенную дату"""
    
    query = """
    SELECT id, status_wspolpracy, data_ostatniego_zamowienia,
           data_dodania_do_nowi, data_dodania_do_w_trakcie,
           data_dodania_do_perspektywiczni, data_pierwszego_zamowienia,
           data_dodania_do_rezygnacja, data_dodania_do_brak_kontaktu,
           data_dodania_do_archiwum
    FROM planfix_clients 
    WHERE menedzer = %s AND is_deleted = false
    """
    params = (manager,)
    results = _execute_query(conn, query, params, f"clients by status for {manager} on {target_date}")

    clients_by_status = {status: set() for status in CLIENT_STATUSES}
    
    for row in results:
        client_data = {
            'id': row[0],
            'status_wspolpracy': row[1],
            'data_ostatniego_zamowienia': row[2],
            'data_dodania_do_nowi': row[3],
            'data_dodania_do_w_trakcie': row[4],
            'data_dodania_do_perspektywiczni': row[5],
            'data_pierwszego_zamowienia': row[6],
            'data_dodania_do_rezygnacja': row[7],
            'data_dodania_do_brak_kontaktu': row[8],
            'data_dodania_do_archiwum': row[9]
        }
        
        # Определяем статус на целевую дату
        status_on_date = get_client_status_on_date(client_data, target_date)
        
        if status_on_date and status_on_date in clients_by_status:
            clients_by_status[status_on_date].add(row[0])  # Добавляем ID клиента
    
    return clients_by_status


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

def calculate_rzm_totals(status_changes):
    """Правильный расчет итоговых строк RZM"""
    
    # CURRENT = сумма всех текущих статусов
    total_current = sum(data['current'] for data in status_changes.values())
    
    # NET = сумма всех изменений
    total_net = sum(data['net'] for data in status_changes.values())
    
    return total_current, total_net

def validate_data_on_the_fly(conn, manager, today):
    """Валидация данных на лету без новых таблиц"""
    
    issues = []
    
    try:
        # 1. Проверка некорректных дат
        invalid_dates_check = """
        SELECT id, status_wspolpracy,
               data_dodania_do_nowi, data_dodania_do_w_trakcie,
               data_dodania_do_perspektywiczni, data_dodania_do_rezygnacja,
               data_dodania_do_brak_kontaktu, data_dodania_do_archiwum,
               data_pierwszego_zamowienia, data_ostatniego_zamowienia
        FROM planfix_clients 
        WHERE menedzer = %s AND is_deleted = false
          AND (
            (data_dodania_do_nowi IS NOT NULL AND data_dodania_do_nowi != '' 
             AND TO_DATE(data_dodania_do_nowi, 'DD-MM-YYYY') IS NULL)
            OR
            (data_dodania_do_w_trakcie IS NOT NULL AND data_dodania_do_w_trakcie != '' 
             AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') IS NULL)
            OR
            (data_dodania_do_perspektywiczni IS NOT NULL AND data_dodania_do_perspektywiczni != '' 
             AND TO_DATE(data_dodania_do_perspektywiczni, 'DD-MM-YYYY') IS NULL)
            OR
            (data_dodania_do_rezygnacja IS NOT NULL AND data_dodania_do_rezygnacja != '' 
             AND TO_DATE(data_dodania_do_rezygnacja, 'DD-MM-YYYY') IS NULL)
            OR
            (data_dodania_do_brak_kontaktu IS NOT NULL AND data_dodania_do_brak_kontaktu != '' 
             AND TO_DATE(data_dodania_do_brak_kontaktu, 'DD-MM-YYYY') IS NULL)
            OR
            (data_dodania_do_archiwum IS NOT NULL AND data_dodania_do_archiwum != '' 
             AND TO_DATE(data_dodania_do_archiwum, 'DD-MM-YYYY') IS NULL)
            OR
            (data_pierwszego_zamowienia IS NOT NULL AND data_pierwszego_zamowienia != '' 
             AND TO_DATE(data_pierwszego_zamowienia, 'DD-MM-YYYY') IS NULL)
            OR
            (data_ostatniego_zamowienia IS NOT NULL AND data_ostatniego_zamowienia != '' 
             AND TO_DATE(data_ostatniego_zamowienia, 'DD-MM-YYYY') IS NULL)
          )
        """
        
        results = _execute_query(conn, invalid_dates_check, (manager,), "validation: invalid_dates")
        if results:
            issues.append(f"Некорректные даты: {len(results)} записей")
            logger.warning(f"Data validation issues for {manager} - invalid_dates: {len(results)}")
    
    except Exception as e:
        logger.error(f"Validation check failed: {e}")
        issues.append(f"Ошибка валидации: {str(e)}")
    
    return issues

def format_client_status_report(changes: dict, global_max: int) -> str:
    """Форматировать отчёт по статусам клиентов с IN/OUT."""
    total_sum = sum(data['current'] for data in changes.values())
    if total_sum == 0: total_sum = 1

    # Длина разделителя - максимальная ширина строки
    separator_length = 33  # "─────────────────────────────────"
    
    # Собираем все данные для каждого столбца
    change_strings = {}
    inout_strings = {}
    percent_strings = {}
    
    for status in CLIENT_STATUSES:
        data = changes[status]
        current = data['current']
        change = data['net']
        inflow = data['inflow']
        outflow = data['outflow']
        
        # Изменение
        change_str = f"+{change}" if change > 0 else (str(change) if change < 0 else "")
        change_strings[status] = change_str
        
        # IN/OUT
        inout_str = f"[+{inflow}/-{outflow}]"
        inout_strings[status] = inout_str
        
        # Проценты БЕЗ скобок
        percentage = math_round(float(current) / float(total_sum) * 100)
        percent_str = f"{percentage}%"
        percent_strings[status] = percent_str

    # Фиксированные длины столбцов как в примере
    max_current_len = 3   # Максимальная длина для текущего количества (3 цифры для больших значений)
    max_change_len = 3    # Максимальная длина для изменений (-99)
    max_inout_len = 9     # Максимальная длина для [IN/OUT] ([+99/-99])
    max_percent_len = 3   # Максимальная длина для процентов (100%)
    
    # Проверяем фактические максимальные длины
    for status in CLIENT_STATUSES:
        data = changes[status]
        current = data['current']
        change_str = change_strings[status]
        inout_str = inout_strings[status]
        percent_str = percent_strings[status]
        
        max_current_len = max(max_current_len, len(str(current)))
        max_change_len = max(max_change_len, len(change_str))
        max_inout_len = max(max_inout_len, len(inout_str))
        max_percent_len = max(max_percent_len, len(percent_str))

    # Фиксированная длина бара как в старой версии
    max_bar_len = 5  # Фиксированная длина бара для пропорционального отображения (уменьшено на 2)
    
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

        # Формируем строку точно как в примере
        line = (
            f"{status} {bar_str:<5} "
            f"{current:>{max_current_len}} "
            f"{change_str:>{max_change_len}} {indicator} "
            f"{inout_str:>{max_inout_len}} "
            f"{percent_str:>{max_percent_len}}"
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
        all_validation_issues = {}
        
        for manager in (m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_name']):
            # 1. Валидация данных
            validation_issues = validate_data_on_the_fly(conn, manager, today)
            all_validation_issues[manager] = validation_issues
            
            # 2. Получаем статусы и потоки
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
                    
                    # Новая логика: NET = INFLOW - OUTFLOW для всех статусов
                    diff = inflow - outflow

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
                separator = "─────────────────────────────────"
                
                # Используем новую функцию для расчета итогов
                total_current, total_net = calculate_rzm_totals(status_changes)
                
                # Формируем итоговую строку с правильным выравниванием
                total_current_str = str(total_current)
                total_change_str = f"+{total_net}" if total_net > 0 else (str(total_net) if total_net < 0 else "")
                
                # Используем те же максимальные длины что и в основном отчете
                max_current_len = max(3, len(total_current_str))
                max_change_len = max(3, len(total_change_str))
                
                # Формат итоговой строки: "RZM BAR CURRENT CHANGE IND"
                # Используем тот же формат что и в основных строках, но без INOUT и PERCENT
                # RZM (3) + " " (1) + BAR (5) + " " (1) + CURRENT + " " (1) + CHANGE + " " (1) + IND (1)
                footer = (
                    f"RZM {'':<5} "
                    f"{total_current_str:>{max_current_len}} "
                    f"{total_change_str:>{max_change_len}} "
                )

                # Добавляем информацию о валидации если есть проблемы
                validation_info = ""
                validation_issues = all_validation_issues.get(manager, [])
                if validation_issues:
                    validation_info = "\n\n⚠️ Проблемы с данными:\n"
                    for issue in validation_issues:
                        validation_info += f"• {issue}\n"

                full_report_for_manager = f"{manager_header}\n{separator}\n{report_kpi_lines}\n{separator}\n{footer}{validation_info}"
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