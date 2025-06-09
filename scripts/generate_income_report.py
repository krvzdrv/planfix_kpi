import os
import sys
import logging
from datetime import datetime, timedelta
import psycopg2
import requests
from dotenv import load_dotenv
from config import MANAGERS_KPI

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planfix_utils import (
    check_required_env_vars,
    get_supabase_connection
)

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
    # всегда 5 символов для числа: 3 для целой части, 1 для точки, 1 для дробной
    return f"({val:5.1f}%)"

def get_income_data(conn, month, year):
    """Получает данные о доходах из Supabase."""
    try:
        # Получаем первый и последний день месяца
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)

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
                    SUM(CAST(wartosc_netto_pln AS DECIMAL)) as fakt
                FROM planfix_orders
                WHERE 
                    data_realizacji >= %s 
                    AND data_realizacji <= %s
                    AND is_deleted = false
                GROUP BY menedzher
            """, (first_day, last_day))
            fakt_data = {row[0]: row[1] for row in cur.fetchall()}
            logger.info(f"Fakt data: {fakt_data}")

            # Получаем все заказы со статусом 140 (dlug)
            cur.execute("""
                SELECT 
                    menedzher,
                    SUM(CAST(wartosc_netto_pln AS DECIMAL)) as dlug
                FROM planfix_orders
                WHERE 
                    status = 140
                    AND is_deleted = false
                GROUP BY menedzher
            """)
            dlug_data = {row[0]: row[1] for row in cur.fetchall()}
            logger.info(f"Dlug data: {dlug_data}")

            # Получаем все заказы (brak)
            cur.execute("""
                SELECT 
                    menedzher,
                    SUM(CAST(wartosc_netto_pln AS DECIMAL)) as brak
                FROM planfix_orders
                WHERE 
                    is_deleted = false
                GROUP BY menedzher
            """)
            brak_data = {row[0]: row[1] for row in cur.fetchall()}
            logger.info(f"Brak data: {brak_data}")

        # Объединяем данные
        income_data = {}
        all_managers = set(list(fakt_data.keys()) + list(dlug_data.keys()) + list(brak_data.keys()))
        logger.info(f"Combined managers: {all_managers}")
        
        for manager in all_managers:
            income_data[manager] = {
                'fakt': fakt_data.get(manager, 0),
                'dlug': dlug_data.get(manager, 0),
                'brak': brak_data.get(manager, 0)
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
        display_name = manager['planfix_user_name']
        data = revenue_data.get(manager_id, {'fakt': 0.0, 'dlug': 0.0, 'brak': 0.0})
        fakt = round(data['fakt'])
        dlug = round(data['dlug'])
        brak = round(data['brak'])
        fakt_percent = (fakt / (fakt + dlug + brak)) * 100 if (fakt + dlug + brak) > 0 else 0
        dlug_percent = (dlug / (fakt + dlug + brak)) * 100 if (fakt + dlug + brak) > 0 else 0
        brak_percent = (brak / (fakt + dlug + brak)) * 100 if (fakt + dlug + brak) > 0 else 0
        all_lines.append({
            'manager': display_name,
            'fakt': fakt,
            'dlug': dlug,
            'brak': brak,
            'fakt_percent': fakt_percent,
            'dlug_percent': dlug_percent,
            'brak_percent': brak_percent
        })
    
    # Находим максимальную длину суммы для выравнивания по PLN
    max_sum_len = 0
    for l in all_lines:
        for key in ['fakt', 'dlug', 'brak']:
            max_sum_len = max(max_sum_len, len(format_int_currency(l[key])))
    
    # Длина бара = 31 символ
    bar_length = 31
    
    # Собираем все проценты в строковом виде для выравнивания
    percent_strs = []
    for l in all_lines:
        percent_strs.append(f"({l['fakt_percent']:4.1f}%)")
        percent_strs.append(f"({l['dlug_percent']:4.1f}%)")
        percent_strs.append(f"({l['brak_percent']:4.1f}%)")
    max_percent_len = max(len(s) for s in percent_strs)
    
    # Для выравнивания: после PLN добавляем столько пробелов, чтобы скобка с процентом начиналась на одной позиции
    def line_with_percent(label, value, percent):
        sum_str = format_int_currency(value).rjust(max_sum_len)
        # Форматируем процент с выравниванием по символу '%'
        percent_str = f"({percent:4.1f}%)"
        # позиция, где должна начинаться скобка
        after_pln_pos = max_sum_len + 8  # 8 = len(' PLN ') + 2 (дополнительные пробелы)
        line = f" {label} {sum_str} PLN "
        # Добавляем пробелы так, чтобы символ '%' был на одной позиции
        spaces = ' ' * (after_pln_pos - len(line))
        return f"{line}{spaces}{percent_str}"
    
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
    
    # Формируем отчет
    report = []
    report.append(f"PRZYCHODY {current_month}/{current_year}")
    report.append("")
    
    for l in all_lines:
        report.append(f"{l['manager']}:")
        
        # Генерируем пропорциональный бар
        progress_bar = generate_proportional_bar(
            l['fakt_percent'], 
            l['dlug_percent'], 
            l['brak_percent'], 
            bar_length
        )
        report.append(progress_bar)
        
        report.append(line_with_percent('█  Fakt:', l['fakt'], l['fakt_percent']))
        report.append(line_with_percent('▒  Dług:', l['dlug'], l['dlug_percent']))
        report.append(line_with_percent('░  Brak:', l['brak'], l['brak_percent']))
        fakt_sum = format_int_currency(l['fakt']).rjust(max_sum_len)
        report.append(f"    Fakt: {fakt_sum} PLN")
        report.append("")
    
    return "```\n" + "\n".join(report).rstrip() + "\n```"

def send_to_telegram(message):
    """
    Send message to Telegram.
    """
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
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
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting income report generation...")

    required_env_vars = {
        'SUPABASE_CONNECTION_STRING': os.environ.get('SUPABASE_CONNECTION_STRING'),
        'SUPABASE_HOST': os.environ.get('SUPABASE_HOST'),
        'SUPABASE_DB': os.environ.get('SUPABASE_DB'),
        'SUPABASE_USER': os.environ.get('SUPABASE_USER'),
        'SUPABASE_PASSWORD': os.environ.get('SUPABASE_PASSWORD'),
        'SUPABASE_PORT': os.environ.get('SUPABASE_PORT'),
        'TELEGRAM_BOT_TOKEN': os.environ.get('TELEGRAM_BOT_TOKEN'),
        'TELEGRAM_CHAT_ID': os.environ.get('TELEGRAM_CHAT_ID')
    }
    
    try:
        check_required_env_vars(required_env_vars)
    except ValueError as e:
        logger.critical(f"Stopping script due to missing environment variables: {e}")
        return

    supabase_conn = None
    try:
        supabase_conn = get_supabase_connection()
        report = generate_income_report(supabase_conn)
        
        # Save report to file
        with open('income_report.txt', 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Send report to Telegram
        if send_to_telegram(report):
            logger.info("Report sent to Telegram successfully")
        else:
            logger.error("Failed to send report to Telegram")
        
        # Print report to console
        print(report)
        
    except psycopg2.Error as e:
        logger.critical(f"Supabase connection error: {e}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Income report generation finished.")

if __name__ == "__main__":
    main() 