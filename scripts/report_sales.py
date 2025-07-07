import os
import sys
import logging
from datetime import datetime, timedelta
import psycopg2
from decimal import Decimal
import requests
from dotenv import load_dotenv
from config import MANAGERS_KPI
from core.kpi_utils import math_round

# Load environment variables from .env file
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

# --- Database Settings ---
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# --- Telegram Settings ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SALES_CHAT_ID = "-1001866680518"  # ID группы для отчетов о продажах

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def format_currency(amount):
    """Format amount as currency."""
    return f"{amount:,.2f} PLN"

def format_int_currency(value):
    """Format integer currency value."""
    return f'{int(value):,}'.replace(',', ' ')

def format_percent(val):
    """Format percentage value."""
    return f"({math_round(float(val), 0)}%)"

def _parse_netto_pln(value):
    """Преобразует текстовое значение wartosc_netto_pln в float. Возвращает 0.0 при ошибке."""
    if value is None:
        return 0.0
    try:
        import re
        cleaned = re.sub(r'[^0-9,.-]', '', str(value)).replace(',', '.').replace(' ', '')
        return float(cleaned)
    except Exception:
        return 0.0

def get_income_data(conn, month, year):
    """Получает данные о доходах из Supabase."""
    try:
        # Получаем плановое значение выручки (общее для всех менеджеров)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT revenue_plan
                FROM kpi_metrics
                WHERE month = %s AND year = %s
                LIMIT 1
            """, (f"{month:02d}", year))
            result = cur.fetchone()
            revenue_plan = Decimal(str(result[0])) if result and result[0] is not None else Decimal('0')

        # Получаем первый и последний день месяца
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)

        # Форматируем даты в нужный формат для PostgreSQL
        first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
        last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')

        # Получаем все заказы за указанный месяц
        with conn.cursor() as cur:
            # Получаем все заказы с датой реализации в текущем месяце (fakt)
            cur.execute("""
                SELECT 
                    menedzher,
                    SUM(CAST(REPLACE(wartosc_netto_pln, ',', '.') AS DECIMAL)) as fakt
                FROM planfix_orders
                WHERE 
                    TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp 
                    AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') <= %s::timestamp
                    AND is_deleted = false
                GROUP BY menedzher
            """, (first_day_str, last_day_str))
            fakt_data = {row[0]: row[1] for row in cur.fetchall()}

            # Получаем все заказы со статусом 140 (dlug)
            cur.execute("""
                SELECT 
                    menedzher,
                    SUM(CAST(REPLACE(wartosc_netto_pln, ',', '.') AS DECIMAL)) as dlug
                FROM planfix_orders
                WHERE 
                    status = 140
                    AND is_deleted = false
                GROUP BY menedzher
            """)
            dlug_data = {row[0]: row[1] for row in cur.fetchall()}

            # Получаем все заказы (brak)
            cur.execute("""
                SELECT 
                    menedzher,
                    SUM(CAST(REPLACE(wartosc_netto_pln, ',', '.') AS DECIMAL)) as brak
                FROM planfix_orders
                WHERE 
                    is_deleted = false
                GROUP BY menedzher
            """)
            brak_data = {row[0]: row[1] for row in cur.fetchall()}

        # После получения данных из БД фильтруем по нулю
        for d in [fakt_data, dlug_data, brak_data]:
            for k in list(d.keys()):
                if d[k] is None or float(d[k]) == 0.0:
                    d[k] = 0.0

        # Объединяем данные
        income_data = {}
        all_managers = set(list(fakt_data.keys()) + list(dlug_data.keys()))
        
        for manager in all_managers:
            fakt = fakt_data.get(manager, Decimal('0'))
            dlug = dlug_data.get(manager, Decimal('0'))
            brak = max(0, revenue_plan - fakt - dlug)  # Brak = Plan - Fakt - Dlug (если положительное)
            
            income_data[manager] = {
                'fakt': fakt,
                'dlug': dlug,
                'brak': brak,
                'plan': revenue_plan
            }

        return income_data
    except Exception as e:
        logger.error(f"Error getting income data: {e}")
        return {}

def get_orders_data(conn, month, year):
    """Получает данные о заказах."""
    try:
        # Получаем первый и последний день месяца
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)

        first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
        last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')

        with conn.cursor() as cur:
            # Количество заказов по статусам
            cur.execute("""
                SELECT 
                    menedzher,
                    status,
                    COUNT(*) as count,
                    SUM(CAST(REPLACE(wartosc_netto_pln, ',', '.') AS DECIMAL)) as total_amount
                FROM planfix_orders
                WHERE 
                    TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp 
                    AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') <= %s::timestamp
                    AND is_deleted = false
                GROUP BY menedzher, status
            """, (first_day_str, last_day_str))
            
            orders_data = {}
            for row in cur.fetchall():
                manager = row[0]
                status = row[1]
                count = row[2]
                amount = row[3] if row[3] else 0
                
                if manager not in orders_data:
                    orders_data[manager] = {'counts': {}, 'amounts': {}}
                
                orders_data[manager]['counts'][status] = count
                orders_data[manager]['amounts'][status] = amount

        return orders_data
    except Exception as e:
        logger.error(f"Error getting orders data: {e}")
        return {}

def get_clients_data(conn, month, year):
    """Получает данные о клиентах."""
    try:
        # Получаем первый и последний день месяца
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)

        first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
        last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')

        with conn.cursor() as cur:
            # Количество клиентов по статусам
            cur.execute("""
                SELECT 
                    menedzer,
                    status_klienta,
                    COUNT(*) as count
                FROM planfix_clients
                WHERE 
                    data_dodania >= %s::timestamp 
                    AND data_dodania <= %s::timestamp
                    AND is_deleted = false
                GROUP BY menedzer, status_klienta
            """, (first_day_str, last_day_str))
            
            clients_data = {}
            for row in cur.fetchall():
                manager = row[0]
                status = row[1]
                count = row[2]
                
                if manager not in clients_data:
                    clients_data[manager] = {}
                
                clients_data[manager][status] = count

        return clients_data
    except Exception as e:
        logger.error(f"Error getting clients data: {e}")
        return {}

def get_tasks_data(conn, month, year):
    """Получает данные о задачах."""
    try:
        # Получаем первый и последний день месяца
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)

        first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
        last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')

        with conn.cursor() as cur:
            # Количество задач по типам
            cur.execute("""
                SELECT 
                    owner_name,
                    TRIM(SPLIT_PART(title, ' /', 1)) as task_type,
                    COUNT(*) as count
                FROM planfix_tasks
                WHERE 
                    data_zakonczenia_zadania >= %s::timestamp 
                    AND data_zakonczenia_zadania <= %s::timestamp
                    AND is_deleted = false
                    AND TRIM(SPLIT_PART(title, ' /', 1)) IN (
                        'Nawiązać pierwszy kontakt',
                        'Przeprowadzić pierwszą rozmowę telefoniczną',
                        'Zadzwonić do klienta',
                        'Przeprowadzić spotkanie',
                        'Wysłać materiały',
                        'Odpowiedzieć na pytanie techniczne',
                        'Zapisać na media społecznościowe',
                        'Opowiedzieć o nowościach',
                        'Zebrać opinie',
                        'Przywrócić klienta'
                    )
                GROUP BY owner_name, TRIM(SPLIT_PART(title, ' /', 1))
            """, (first_day_str, last_day_str))
            
            tasks_data = {}
            task_type_mapping = {
                'Nawiązać pierwszy kontakt': 'WDM',
                'Przeprowadzić pierwszą rozmowę telefoniczną': 'PRZ',
                'Zadzwonić do klienta': 'ZKL',
                'Przeprowadzić spotkanie': 'SPT',
                'Wysłać materiały': 'MAT',
                'Odpowiedzieć na pytanie techniczne': 'TPY',
                'Zapisać na media społecznościowe': 'MSP',
                'Opowiedzieć o nowościach': 'NOW',
                'Zebrać opinie': 'OPI',
                'Przywrócić klienta': 'WRK'
            }
            
            for row in cur.fetchall():
                manager = row[0]
                task_type = row[1]
                count = row[2]
                
                if manager not in tasks_data:
                    tasks_data[manager] = {}
                
                short_type = task_type_mapping.get(task_type, task_type)
                tasks_data[manager][short_type] = count

        return tasks_data
    except Exception as e:
        logger.error(f"Error getting tasks data: {e}")
        return {}

def generate_sales_report(conn):
    """Генерирует комплексный отчет о продажах."""
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    # Получаем все данные
    income_data = get_income_data(conn, current_month, current_year)
    orders_data = get_orders_data(conn, current_month, current_year)
    clients_data = get_clients_data(conn, current_month, current_year)
    tasks_data = get_tasks_data(conn, current_month, current_year)
    
    # Формируем отчет
    message = '```'
    message += f'RAPORT SPRZEDAŻY_{current_month:02d}.{current_year}\n'
    message += '═══════════════════════════════════════\n\n'
    
    # Секция доходов
    message += '📊 PRZYCHODY:\n'
    message += '─────────────────────────────────────\n'
    
    for manager in MANAGERS_KPI:
        manager_id = manager['planfix_user_id']
        manager_name = manager['planfix_user_name']
        data = income_data.get(manager_id)
        
        if data:
            fakt = math_round(float(data['fakt']))
            dlug = math_round(float(data['dlug']))
            brak = math_round(float(data['brak']))
            plan = math_round(float(data['plan']))
            total = fakt + dlug + brak
            
            fakt_percent = (fakt / total) * 100 if total > 0 else 0
            dlug_percent = (dlug / total) * 100 if total > 0 else 0
            brak_percent = (brak / total) * 100 if total > 0 else 0
            
            message += f'👤 {manager_name}:\n'
            message += f'   Plan: {format_int_currency(plan)} PLN\n'
            message += f'   Fakt: {format_int_currency(fakt)} PLN {format_percent(fakt_percent)}\n'
            message += f'   Dług: {format_int_currency(dlug)} PLN {format_percent(dlug_percent)}\n'
            message += f'   Brak: {format_int_currency(brak)} PLN {format_percent(brak_percent)}\n\n'
    
    # Секция заказов
    message += '📋 ZAMÓWIENIA:\n'
    message += '─────────────────────────────────────\n'
    
    for manager in MANAGERS_KPI:
        manager_id = manager['planfix_user_id']
        manager_name = manager['planfix_user_name']
        data = orders_data.get(manager_id, {})
        
        if data:
            message += f'👤 {manager_name}:\n'
            counts = data.get('counts', {})
            amounts = data.get('amounts', {})
            
            total_orders = sum(counts.values())
            total_amount = sum(amounts.values())
            
            message += f'   Łącznie: {total_orders} zamówień\n'
            message += f'   Wartość: {format_int_currency(total_amount)} PLN\n'
            
            # Детали по статусам
            for status, count in counts.items():
                amount = amounts.get(status, 0)
                message += f'   Status {status}: {count} ({format_int_currency(amount)} PLN)\n'
            message += '\n'
    
    # Секция клиентов
    message += '👥 KLIENCI:\n'
    message += '─────────────────────────────────────\n'
    
    for manager in MANAGERS_KPI:
        manager_id = manager['planfix_user_id']
        manager_name = manager['planfix_user_name']
        data = clients_data.get(manager_id, {})
        
        if data:
            message += f'👤 {manager_name}:\n'
            total_clients = sum(data.values())
            message += f'   Łącznie: {total_clients} klientów\n'
            
            for status, count in data.items():
                message += f'   Status {status}: {count}\n'
            message += '\n'
    
    # Секция задач
    message += '✅ ZADANIA:\n'
    message += '─────────────────────────────────────\n'
    
    for manager in MANAGERS_KPI:
        manager_id = manager['planfix_user_id']
        manager_name = manager['planfix_user_name']
        data = tasks_data.get(manager_name, {})
        
        if data:
            message += f'👤 {manager_name}:\n'
            total_tasks = sum(data.values())
            message += f'   Łącznie: {total_tasks} zadań\n'
            
            task_order = ['WDM', 'PRZ', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK']
            for task_type in task_order:
                if task_type in data and data[task_type] > 0:
                    message += f'   {task_type}: {data[task_type]}\n'
            message += '\n'
    
    message += '═══════════════════════════════════════\n'
    message += f'Raport wygenerowany: {current_date.strftime("%d.%m.%Y %H:%M")}\n'
    message += '```'
    
    return message

def send_to_telegram(message):
    """Отправляет сообщение в Telegram."""
    bot_token = TELEGRAM_TOKEN
    
    if not bot_token:
        logger.error("Missing Telegram configuration")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': SALES_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to send message to Telegram: {response.text}")
            return False
        else:
            logger.info("Message sent successfully to Telegram")
            return True
    except Exception as e:
        logger.error(f"Failed to send message to Telegram: {e}")
        return False

def main():
    """Основная функция для генерации и отправки отчета о продажах."""
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(
            host=PG_HOST,
            dbname=PG_DB,
            user=PG_USER,
            password=PG_PASSWORD,
            port=PG_PORT
        )
        
        # Генерируем отчет
        report = generate_sales_report(conn)
        
        # Отправляем в Telegram
        success = send_to_telegram(report)
        
        if success:
            logger.info("Sales report sent successfully")
        else:
            logger.error("Failed to send sales report")
        
        conn.close()
        
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting sales report generation...")
    main() 