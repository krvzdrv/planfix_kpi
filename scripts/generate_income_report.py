import os
import sys
import logging
from datetime import datetime
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

def get_revenue_data(conn, current_month, current_year):
    """
    Get revenue data from planfix_orders and kpi_metrics tables.
    """
    cursor = conn.cursor()
    
    # Debug query to check order A-10064
    cursor.execute("""
        SELECT 
            title,
            menedzher,
            data_realizacji,
            data_przekazania_do_weryfikacji,
            wartosc_netto_pln,
            TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') as parsed_realization_date,
            TO_TIMESTAMP(data_przekazania_do_weryfikacji, 'DD-MM-YYYY HH24:MI') as parsed_verification_date,
            CAST(REPLACE(REPLACE(wartosc_netto_pln, ' ', ''), ',', '.') AS NUMERIC) as parsed_netto
        FROM planfix_orders
        WHERE title = 'A-10064'
        LIMIT 1;
    """)
    debug_row = cursor.fetchone()
    if debug_row:
        logger.info("\nDebug - Order A-10064 details:")
        logger.info(f"Title: {debug_row[0]}")
        logger.info(f"Manager: {debug_row[1]}")
        logger.info(f"Realization Date: {debug_row[2]}")
        logger.info(f"Verification Date: {debug_row[3]}")
        logger.info(f"Netto (raw): {debug_row[4]}")
        logger.info(f"Parsed Realization Date: {debug_row[5]}")
        logger.info(f"Parsed Verification Date: {debug_row[6]}")
        logger.info(f"Parsed Netto: {debug_row[7]}")
    else:
        logger.info("Order A-10064 not found in the database.")
    
    # Get revenue plan (one value for all managers)
    cursor.execute("""
        SELECT revenue_plan
        FROM kpi_metrics
        WHERE month = %s AND year = %s
        LIMIT 1
    """, (str(current_month), str(current_year)))
    plan_row = cursor.fetchone()
    revenue_plan = float(plan_row[0]) if plan_row and plan_row[0] is not None else 40000.00
    
    # Get actual revenue data from planfix_orders
    cursor.execute("""
        WITH fakt_data AS (
            SELECT 
                menedzher,
                SUM(CAST(REPLACE(REPLACE(wartosc_netto_pln, ' ', ''), ',', '.') AS NUMERIC)) as total_fakt
            FROM planfix_orders
            WHERE is_deleted = false
              AND data_realizacji IS NOT NULL
              AND data_realizacji != ''
              AND (
                (EXTRACT(MONTH FROM TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI')) = %s AND EXTRACT(YEAR FROM TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI')) = %s)
                OR
                (EXTRACT(MONTH FROM TO_DATE(data_realizacji, 'DD-MM-YYYY')) = %s AND EXTRACT(YEAR FROM TO_DATE(data_realizacji, 'DD-MM-YYYY')) = %s)
              )
            GROUP BY menedzher
        ),
        dlug_data AS (
            SELECT 
                menedzher,
                SUM(CAST(REPLACE(REPLACE(wartosc_netto_pln, ' ', ''), ',', '.') AS NUMERIC)) as total_dlug
            FROM planfix_orders
            WHERE is_deleted = false
              AND data_przekazania_do_weryfikacji IS NOT NULL
              AND data_przekazania_do_weryfikacji != ''
              AND (data_realizacji IS NULL OR data_realizacji = '')
              AND (
                (EXTRACT(MONTH FROM TO_TIMESTAMP(data_przekazania_do_weryfikacji, 'DD-MM-YYYY HH24:MI')) = %s AND EXTRACT(YEAR FROM TO_TIMESTAMP(data_przekazania_do_weryfikacji, 'DD-MM-YYYY HH24:MI')) = %s)
                OR
                (EXTRACT(MONTH FROM TO_DATE(data_przekazania_do_weryfikacji, 'DD-MM-YYYY')) = %s AND EXTRACT(YEAR FROM TO_DATE(data_przekazania_do_weryfikacji, 'DD-MM-YYYY')) = %s)
              )
            GROUP BY menedzher
        )
        SELECT 
            f.menedzher,
            f.total_fakt,
            d.total_dlug
        FROM fakt_data f
        LEFT JOIN dlug_data d ON f.menedzher = d.menedzher
        UNION ALL
        SELECT 
            d.menedzher,
            0 as total_fakt,
            d.total_dlug
        FROM dlug_data d
        LEFT JOIN fakt_data f ON d.menedzher = f.menedzher
        WHERE f.menedzher IS NULL
    """, (current_month, current_year, current_month, current_year, current_month, current_year, current_month, current_year))
    
    revenue_data = {}
    for row in cursor.fetchall():
        manager_id = str(row[0]) if row[0] is not None else None
        total_fakt = float(row[1] or 0)
        total_dlug = float(row[2] or 0)
        if manager_id:
            revenue_data[manager_id] = {
                'plan': revenue_plan,
                'fakt': total_fakt,
                'dlug': total_dlug
            }
    
    return revenue_data

def generate_income_report(conn):
    """
    Generate income report for all managers in MANAGERS_KPI in Polish, code block, always show all managers.
    """
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    revenue_data = get_revenue_data(conn, current_month, current_year)
    
    # Сначала собираем все значения для выравнивания
    all_lines = []
    for manager in MANAGERS_KPI:
        manager_id = manager['planfix_user_id']
        display_name = manager['planfix_user_name']
        data = revenue_data.get(manager_id, {'plan': 40000.0, 'fakt': 0.0, 'dlug': 0.0})
        plan = round(data['plan'])
        fakt = round(data['fakt'])
        dlug = round(data['dlug'])
        brak = plan - fakt - dlug
        fakt_percent = (fakt / plan) * 100 if plan > 0 else 0
        dlug_percent = (dlug / plan) * 100 if plan > 0 else 0
        brak_percent = (brak / plan) * 100 if plan > 0 else 0
        all_lines.append({
            'manager': display_name,
            'plan': plan,
            'fakt': fakt,
            'dlug': dlug,
            'brak': brak,
            'fakt_percent': fakt_percent,
            'dlug_percent': dlug_percent,
            'brak_percent': brak_percent
        })
    # Находим максимальную длину суммы для выравнивания
    max_sum_len = 0
    for l in all_lines:
        for key in ['fakt', 'dlug', 'brak', 'plan']:
            max_sum_len = max(max_sum_len, len(format_int_currency(l[key])))
    # Формируем отчет
    report = []
    report.append(f"PRZYCHODY {current_month}/{current_year}\n")
    for l in all_lines:
        report.append(f"{l['manager']}:")
        progress_bar = generate_progress_bar(l['fakt_percent'])
        report.append(f"[{progress_bar}]")
        report.append(f" █  Fakt: {format_int_currency(l['fakt']).rjust(max_sum_len)} PLN  {format_percent(l['fakt_percent'])}")
        report.append(f" ▒  Dług: {format_int_currency(l['dlug']).rjust(max_sum_len)} PLN  {format_percent(l['dlug_percent'])}")
        report.append(f" ░  Brak: {format_int_currency(l['brak']).rjust(max_sum_len)} PLN {format_percent(l['brak_percent'])}")
        report.append(f"    Plan: {format_int_currency(l['plan']).rjust(max_sum_len)} PLN")
    return "```\n" + "\n".join(report) + "\n```"

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
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
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