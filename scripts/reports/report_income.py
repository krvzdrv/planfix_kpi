import os
import sys
import logging
from datetime import datetime, timedelta
import psycopg2
from decimal import Decimal
import requests
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.config import MANAGERS_KPI
from core.kpi_utils import math_round

# --- Database Settings ---
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# --- Telegram Settings ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def generate_progress_bar(percentage):
    """
    Generate a visual progress bar.
    """
    bar_length = 20
    filled_length = int(bar_length * percentage / 100)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    return f"[{bar}] {percentage:.1f}%"

def format_currency(amount):
    """
    Format amount as currency.
    """
    return f"{amount:,.2f} PLN"

def format_int_currency(value):
    return f'{int(value):,}'.replace(',', ' ')

def format_percent(val):
    # Округляем до целых значений и форматируем как (XX%)
    return f"({math_round(float(val), 0)}%)"

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
            # Проверяем всех менеджеров в базе
            cur.execute("""
                SELECT DISTINCT menedzher 
                FROM planfix_orders 
                WHERE is_deleted = false
            """)
            all_managers = [row[0] for row in cur.fetchall()]
            logger.info(f"All managers in database: {all_managers}")

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
            logger.info(f"Fakt data: {fakt_data}")

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
            logger.info(f"Dlug data: {dlug_data}")

        # После получения данных из БД фильтруем по нулю
        for d in [fakt_data, dlug_data]:
            for k in list(d.keys()):
                if d[k] is None or d[k] == Decimal('0'):
                    d[k] = Decimal('0')

        # Объединяем данные
        income_data = {}
        all_managers = set(list(fakt_data.keys()) + list(dlug_data.keys()))
        logger.info(f"Combined managers: {all_managers}")
        
        for manager in all_managers:
            fakt = fakt_data.get(manager, Decimal('0'))
            dlug = dlug_data.get(manager, Decimal('0'))
            brak = max(Decimal('0'), revenue_plan - fakt - dlug)  # Brak = Plan - Fakt - Dlug (если положительное)
            
            income_data[manager] = {
                'fakt': fakt,
                'dlug': dlug,
                'brak': brak,
                'plan': revenue_plan
            }
            logger.info(f"Manager {manager} data: {income_data[manager]}")

        return income_data
    except Exception as e:
        logger.error(f"Error getting income data: {e}")
        return {}

def generate_income_report(conn):
    """
    Generate income report for all managers in MANAGERS_KPI in Polish, code block, always show all managers.
    """
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    revenue_data = get_income_data(conn, current_month, current_year)
    
    # Сначала собираем все значения для выравнивания
    all_lines = []
    for manager in MANAGERS_KPI:
        manager_id = manager['planfix_user_id']
        manager_name = manager['planfix_user_name']
        
        # Ищем данные по ID менеджера в revenue_data
        data = None
        for key in revenue_data.keys():
            if str(key) == str(manager_id):
                data = revenue_data[key]
                break
        
        if not data or 'plan' not in data:
            logger.warning(f"No data found for manager {manager_name} (ID: {manager_id})")
            continue
            
        fakt = math_round(float(data['fakt']))
        dlug = math_round(float(data['dlug']))
        brak = math_round(float(data['brak']))
        plan = math_round(float(data['plan']))
        total = fakt + dlug + brak
        fakt_percent = (fakt / total) * 100 if total > 0 else 0
        dlug_percent = (dlug / total) * 100 if total > 0 else 0
        brak_percent = (brak / total) * 100 if total > 0 else 0
        all_lines.append({
            'manager': manager_name,
            'fakt': fakt,
            'dlug': dlug,
            'brak': brak,
            'plan': plan,
            'fakt_percent': fakt_percent,
            'dlug_percent': dlug_percent,
            'brak_percent': brak_percent
        })

    if not all_lines:
        return "Нет данных для отчёта"
    
    # Находим максимальную длину суммы для выравнивания по PLN
    max_sum_len = 0
    for l in all_lines:
        for key in ['fakt', 'dlug', 'brak']:
            max_sum_len = max(max_sum_len, len(format_int_currency(l[key])))
    
    # Длина бара = 31 символ (возвращаем как было)
    bar_length = 31
    
    # Собираем все проценты в строковом виде для выравнивания
    percent_strs = []
    for l in all_lines:
        percent_strs.append(format_percent(l['fakt_percent']))
        percent_strs.append(format_percent(l['dlug_percent']))
        percent_strs.append(format_percent(l['brak_percent']))
    max_percent_len = max(len(s) for s in percent_strs)
    
    # Для выравнивания: после PLN добавляем столько пробелов, чтобы скобка с процентом начиналась на одной позиции
    def line_with_percent(label, value, percent):
        sum_str = format_int_currency(value).rjust(max_sum_len)
        percent_str = format_percent(percent)
        
        # Левая часть: "LABEL VALUE PLN" - фиксированная ширина
        left_part = f" {label} {sum_str} PLN "
        
        # Правая часть: " PERCENT" - 6 символов (уменьшено с 12), процент по правому краю
        # Используем логику как в скрипте статусов
        padding_len = 6 - len(percent_str)
        right_part = f"{' ' * max(0, padding_len)}{percent_str}"
        
        return f"{left_part}{right_part}"
    
    def generate_proportional_bar(fakt_percent, dlug_percent, brak_percent, total_length):
        """
        Generate a proportional progress bar showing fakt, dlug, brak.
        """
        # Убираем 2 символа для квадратных скобок
        inner_length = total_length - 2
        
        fakt_blocks = int((fakt_percent / 100) * inner_length)
        dlug_blocks = int((dlug_percent / 100) * inner_length)
        # Остальное - brak
        brak_blocks = inner_length - fakt_blocks - dlug_blocks
        
        # Корректируем если есть остаток из-за округления
        if fakt_blocks + dlug_blocks + brak_blocks < inner_length:
            if brak_percent > 0:
                brak_blocks += inner_length - (fakt_blocks + dlug_blocks + brak_blocks)
            elif dlug_percent > 0:
                dlug_blocks += inner_length - (fakt_blocks + dlug_blocks + brak_blocks)
            else:
                fakt_blocks += inner_length - (fakt_blocks + dlug_blocks + brak_blocks)
        
        bar = '█' * fakt_blocks + '▒' * dlug_blocks + '░' * brak_blocks
        return f"[{bar}]"
    
    # Формируем отчет - КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ЗДЕСЬ
    # Начинаем с блока кода, а заголовок помещаем ВНУТРИ
    message = '```'
    message += f'PRZYCHODY_{current_month:02d}.{current_year}\n'
    
    for l in all_lines:
        message += f"👤 {l['manager']}:\n\n"
        
        # Генерируем пропорциональный бар
        progress_bar = generate_proportional_bar(
            l['fakt_percent'], 
            l['dlug_percent'], 
            l['brak_percent'], 
            bar_length
        )
        message += progress_bar + '\n'
        
        message += line_with_percent('█  Fakt:', l['fakt'], l['fakt_percent']) + '\n'
        message += line_with_percent('▒  Dług:', l['dlug'], l['dlug_percent']) + '\n'
        message += line_with_percent('░  Brak:', l['brak'], l['brak_percent']) + '\n'
        plan_sum = format_int_currency(l['plan']).rjust(max_sum_len)
        message += f"    Plan: {plan_sum} PLN\n"
        message += '\n'
    
    message += '```'
    return message

def send_to_telegram(message):
    """
    Send message to Telegram.
    """
    bot_token = TELEGRAM_TOKEN
    chat_id = CHAT_ID
    
    if not bot_token or not chat_id:
        logger.error("Missing Telegram configuration")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
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
    """
    Main function to generate and send income report.
    """
    try:
        # Подключение к базе напрямую через psycopg2
        conn = psycopg2.connect(
            host=PG_HOST,
            dbname=PG_DB,
            user=PG_USER,
            password=PG_PASSWORD,
            port=PG_PORT
        )
        report = generate_income_report(conn)
        send_to_telegram(report)
        conn.close()
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting income report generation...")
    main()