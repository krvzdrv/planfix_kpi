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
            
    # 2. Рассчитываем ДНЕВНОЙ ПРИТОК и ОТТОК 
    # Комбинированная логика:
    # - Для клиентов с переходами СЕГОДНЯ: считаем все переходы
    # - Для остальных клиентов: сравниваем с последним рабочим днем
    daily_inflow = {status: 0 for status in CLIENT_STATUSES}
    daily_outflow = {status: 0 for status in CLIENT_STATUSES}
    
    # Определяем последний рабочий день для сравнения
    # Понедельник (0) → сравниваем с пятницей (-3 дня)
    # Вторник-пятница (1-4) → сравниваем со вчера (-1 день)
    # Суббота/воскресенье (5-6) → показываем данные за пятницу
    is_weekend_report = False
    report_date = today
    
    if today.weekday() == 0:  # Понедельник
        last_workday = today - timedelta(days=3)  # Пятница
    elif today.weekday() >= 5:  # Суббота или воскресенье
        # В выходные показываем отчет за пятницу
        is_weekend_report = True
        days_since_friday = today.weekday() - 4
        report_date = today - timedelta(days=days_since_friday)  # Пятница
        last_workday = report_date - timedelta(days=1)  # Четверг
        logger.info(f"⚠️ Weekend report: showing data for Friday {report_date} (comparing with Thursday {last_workday})")
    else:  # Вторник-пятница
        last_workday = today - timedelta(days=1)
    
    if not is_weekend_report:
        logger.info(f"Comparing {today} (weekday={today.weekday()}) with last workday: {last_workday}")
    
    # Получаем списки клиентов по статусам на последний рабочий день и report_date
    # В выходные report_date = пятница, в остальные дни = today
    yesterday_clients = get_clients_by_status_for_date(conn, manager, last_workday)
    today_clients = get_clients_by_status_for_date(conn, manager, report_date)
    
    # Находим всех активных клиентов (вчера или сегодня)
    all_active_clients = set()
    for status_set in today_clients.values():
        all_active_clients.update(status_set)
    for status_set in yesterday_clients.values():
        all_active_clients.update(status_set)
    
    # Для каждого активного клиента проверяем его переходы
    for client_id in all_active_clients:
        # Получаем все переходы клиента за report_date (сегодня или пятница в выходные)
        transitions = get_daily_transitions_for_client(conn, manager, client_id, report_date)
        
        # Находим где клиент был вчера и где сегодня
        yesterday_status = None
        today_status = None
        
        for status in CLIENT_STATUSES:
            if client_id in yesterday_clients.get(status, set()):
                yesterday_status = status
            if client_id in today_clients.get(status, set()):
                today_status = status
        
        # Проверяем, новый ли это клиент в системе
        was_in_system_yesterday = yesterday_status is not None
        is_new_client = not was_in_system_yesterday and today_status is not None
        
        # Если это новый клиент, ВСЕГДА добавляем его в первый статус
        if is_new_client:
            # Получаем данные клиента из базы для поиска первого статуса
            query_first_status = """
            SELECT data_dodania_do_nowi, data_dodania_do_w_trakcie,
                   data_dodania_do_perspektywiczni, data_pierwszego_zamowienia
            FROM planfix_clients WHERE id = %s
            """
            result = _execute_query(conn, query_first_status, (client_id,), "first status")
            
            if result:
                dates = result[0]
                status_dates = {
                    'NWI': dates[0],
                    'WTR': dates[1],
                    'PSK': dates[2],
                    'PIZ': dates[3]
                }
                
                # Ищем самую раннюю дату (первый статус)
                earliest_status = None
                earliest_date = None
                
                for status, date_str in status_dates.items():
                    if date_str and date_str.strip():
                        try:
                            date_obj = datetime.strptime(date_str.strip()[:10], '%d-%m-%Y').date()
                            if earliest_date is None or date_obj < earliest_date:
                                earliest_date = date_obj
                                earliest_status = status
                        except:
                            continue
                
                # Добавляем inflow в первый статус, если он не в transitions
                if earliest_status and earliest_status not in transitions:
                    daily_inflow[earliest_status] += 1
                    # Outflow только если первый статус != текущий статус
                    if earliest_status != today_status:
                        daily_outflow[earliest_status] += 1
        
        if transitions:
            # Если есть переходы сегодня, считаем inflow по всей цепочке
            for i, status in enumerate(transitions):
                daily_inflow[status] += 1
                # Outflow для всех кроме последнего в цепочке
                if i < len(transitions) - 1:
                    daily_outflow[status] += 1
        else:
            # Если нет переходов сегодня и не новый клиент
            if not is_new_client:
                # Если статус изменился - считаем inflow
                if yesterday_status != today_status and today_status:
                    daily_inflow[today_status] += 1
                    
                    # Debug для переходов в STL/NAK
                    if yesterday_status in ['STL', 'NAK', 'PIZ'] or today_status in ['STL', 'NAK']:
                        logger.info(f"[DEBUG] Client {client_id} inflow: {yesterday_status} → {today_status}")
        
        # OUTFLOW считаем ВСЕГДА по сравнению вчера/сегодня
        if yesterday_status and yesterday_status != today_status:
            # Только если клиент НЕ в цепочке переходов (чтобы не дублировать)
            if not transitions or yesterday_status not in transitions:
                daily_outflow[yesterday_status] += 1
                
                # Debug для переходов с STL/NAK
                if yesterday_status in ['STL', 'NAK'] or today_status in ['STL', 'NAK']:
                    logger.info(f"[DEBUG] Client {client_id}: {yesterday_status} → {today_status}")


    return current_totals, daily_inflow, daily_outflow

def get_client_status_on_date(client_data, target_date):
    """Определяет, в каком статусе был клиент на определенную дату"""
    
    # ПРИОРИТЕТ 1: STL/NAK (если status_wspolpracy = 'Stali klienci')
    # НО ТОЛЬКО если второй заказ был ДО target_date!
    if client_data.get('status_wspolpracy') == 'Stali klienci':
        last_order_date = client_data.get('data_ostatniego_zamowienia')
        if last_order_date and last_order_date.strip():
            try:
                order_date = datetime.strptime(last_order_date.strip()[:10], '%d-%m-%Y').date()
                # Если последний заказ ПОСЛЕ target_date → клиент ЕЩЕ НЕ БЫЛ в STL/NAK
                if order_date > target_date:
                    # Используем обычную логику по датам (PIZ и т.д.)
                    pass
                else:
                    # Последний заказ БЫЛ до target_date → клиент УЖЕ в STL/NAK
                    workdays_diff = count_workdays(order_date, target_date)
                    return 'STL' if workdays_diff <= 30 else 'NAK'
            except:
                return 'NAK'
        else:
            return 'NAK'
    
    # ПРИОРИТЕТ 2: Остальные статусы по датам
    # Порядок статусов в воронке (важно для случаев с одинаковыми датами)
    status_order = ['NWI', 'WTR', 'PSK', 'PIZ', 'REZ', 'BRK', 'ARC']
    
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
    # Если даты одинаковые, выбираем статус, который идет ПОЗЖЕ в воронке
    latest_date = None
    status_on_date = None
    
    for status, date_str in status_dates.items():
        if date_str and date_str.strip():
            try:
                date_obj = datetime.strptime(date_str.strip()[:10], '%d-%m-%Y').date()
                
                # Берем только даты <= целевой даты
                if date_obj <= target_date:
                    # Если дата новее, или дата та же, но статус позже в воронке
                    if latest_date is None or date_obj > latest_date:
                        latest_date = date_obj
                        status_on_date = status
                    elif date_obj == latest_date and status_on_date:
                        # Если даты одинаковые, выбираем статус, который позже в воронке
                        if status in status_order and status_on_date in status_order:
                            if status_order.index(status) > status_order.index(status_on_date):
                                status_on_date = status
            except:
                continue
    
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

def get_daily_transitions_for_client(conn, manager: str, client_id: int, target_date: date) -> list:
    """Получает все переходы клиента за день"""
    
    query = """
    SELECT id, status_wspolpracy, data_ostatniego_zamowienia,
           data_dodania_do_nowi, data_dodania_do_w_trakcie,
           data_dodania_do_perspektywiczni, data_pierwszego_zamowienia,
           data_dodania_do_rezygnacja, data_dodania_do_brak_kontaktu,
           data_dodania_do_archiwum
    FROM planfix_clients 
    WHERE menedzer = %s AND id = %s AND is_deleted = false
    """
    params = (manager, client_id)
    results = _execute_query(conn, query, params, f"client {client_id} transitions for {manager} on {target_date}")
    
    if not results:
        return []
    
    row = results[0]
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
    
    # Собираем все даты статусов за день
    status_dates = {}
    for status, col_name in STATUS_INFLOW_DATE_COLS.items():
        date_str = client_data.get(col_name)
        if date_str and date_str.strip():
            try:
                date_obj = datetime.strptime(date_str.strip()[:10], '%d-%m-%Y').date()
                if date_obj == target_date:
                    status_dates[status] = date_obj
            except (ValueError, TypeError):
                pass
    
    # Добавляем STL/NAK если клиент был в статусе "Stali klienci"
    if client_data.get('status_wspolpracy') == 'Stali klienci':
        last_order_date = client_data.get('data_ostatniego_zamowienia')
        if last_order_date and last_order_date.strip():
            try:
                order_date = datetime.strptime(last_order_date.strip()[:10], '%d-%m-%Y').date()
                if order_date == target_date:
                    workdays_diff = count_workdays(order_date, target_date)
                    if workdays_diff <= 30:
                        status_dates['STL'] = order_date
                    else:
                        status_dates['NAK'] = order_date
            except (ValueError, TypeError):
                pass
    
    # Сортируем по времени (если есть время) или по порядку статусов
    status_order = ['NWI', 'WTR', 'PSK', 'PIZ', 'STL', 'NAK', 'REZ', 'BRK', 'ARC']
    transitions = []
    for status in status_order:
        if status in status_dates:
            transitions.append(status)
    
    return transitions


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

        # Определяем last_workday для получения истории STL/NAK
        if today.weekday() == 0:  # Понедельник
            last_workday = today - timedelta(days=3)  # Пятница
        elif today.weekday() >= 5:  # Суббота или воскресенье
            days_since_friday = today.weekday() - 4
            last_workday = today - timedelta(days=days_since_friday + 1)  # Четверг
        else:  # Вторник-пятница
            last_workday = today - timedelta(days=1)
        
        # Используем фиксированные ширины для всех менеджеров
        global_max_current_len = 6   # Фиксированная ширина для текущего количества
        global_max_change_len = 4    # Фиксированная ширина для изменений
        
        all_reports = []
        for manager, current_totals in all_managers_totals.items():
            report_body = ""
            try:
                logger.info(f"Processing report for manager: {manager}")
                
                # Получаем STL/NAK с последнего рабочего дня из истории
                previous_stl_nak = get_statuses_from_history(conn, last_workday, manager)
                logger.info(f"[DEBUG {manager}] STL/NAK history for {last_workday}: {previous_stl_nak}")
                
                status_changes = {}
                
                for status in CLIENT_STATUSES:
                    curr_count = current_totals.get(status, 0)
                    inflow = all_managers_inflow[manager].get(status, 0)
                    outflow = all_managers_outflow[manager].get(status, 0)
                    
                    # Debug для STL/NAK
                    if status in ['STL', 'NAK'] and (inflow > 0 or outflow > 0):
                        logger.info(f"[DEBUG {manager}] {status}: current={curr_count}, inflow={inflow}, outflow={outflow}")
                    
                    # Правильная логика Вариант 3:
                    # Net = inflow - outflow (результат движения)
                    # [Inflow/-Outflow] = движение через статус
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
                
                # RZM = сумма всех текущих и сумма всех изменений
                total_current = sum(data['current'] for data in status_changes.values())
                total_net = sum(data['net'] for data in status_changes.values())
                
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
            # Проверяем, выходной ли день
            is_weekend = today.weekday() >= 5
            
            if is_weekend:
                # В выходные показываем данные за пятницу
                days_since_friday = today.weekday() - 4
                friday = today - timedelta(days=days_since_friday)
                final_report_header = f"WORONKA_{friday.strftime('%d.%m.%Y')}"
                weekend_note = f"⚠️ Отчет за пятницу {friday.strftime('%d.%m.%Y')} (сегодня выходной)\n\n"
                final_report = f"```{final_report_header}\n\n{weekend_note}" + "\n\n".join(all_reports) + "\n```"
            else:
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