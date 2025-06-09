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

def format_float(value):
    """Format float value with 2 decimal places."""
    return f"{value:.2f}"

def get_kpi_data(conn, month, year):
    """Получает данные о KPI из Supabase."""
    try:
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
            # Получаем данные по задачам
            cur.execute("""
                WITH task_counts AS (
                    SELECT
                        owner_name AS manager,
                        CASE 
                            WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Nawiązać pierwszy kontakt' THEN 'TTL'
                            WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną' THEN 'PRZ'
                            WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Zadzwonić do klienta' THEN 'ZKL'
                            ELSE NULL
                        END AS task_type,
                        COUNT(*) AS task_count
                    FROM planfix_tasks
                    WHERE
                        data_zakonczenia_zadania IS NOT NULL
                        AND data_zakonczenia_zadania >= %s::timestamp
                        AND data_zakonczenia_zadania < %s::timestamp
                        AND owner_name IN %s
                        AND is_deleted = false
                    GROUP BY
                        owner_name,
                        CASE 
                            WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Nawiązać pierwszy kontakt' THEN 'TTL'
                            WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną' THEN 'PRZ'
                            WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Zadzwonić do klienta' THEN 'ZKL'
                            ELSE NULL
                        END
                )
                SELECT manager, task_type, task_count
                FROM task_counts
                WHERE task_type IS NOT NULL
                ORDER BY manager, task_type;
            """, (first_day_str, last_day_str, tuple(m['planfix_user_name'] for m in MANAGERS_KPI)))
            task_data = cur.fetchall()
            logger.info(f"Task data: {task_data}")

            # Получаем данные по клиентам
            cur.execute("""
                WITH client_statuses AS (
                    SELECT menedzer AS manager, 'NWI' as status, COUNT(*) as count
                    FROM planfix_clients
                    WHERE data_dodania_do_nowi IS NOT NULL AND data_dodania_do_nowi != ''
                        AND TO_DATE(data_dodania_do_nowi, 'DD-MM-YYYY') >= %s::date
                        AND TO_DATE(data_dodania_do_nowi, 'DD-MM-YYYY') < %s::date
                        AND menedzer IN %s
                        AND is_deleted = false
                    GROUP BY menedzer
                    UNION ALL
                    SELECT menedzer AS manager, 'PSK' as status, COUNT(*) as count
                    FROM planfix_clients
                    WHERE data_dodania_do_perspektywiczni IS NOT NULL AND data_dodania_do_perspektywiczni != ''
                        AND TO_DATE(data_dodania_do_perspektywiczni, 'DD-MM-YYYY') >= %s::date
                        AND TO_DATE(data_dodania_do_perspektywiczni, 'DD-MM-YYYY') < %s::date
                        AND menedzer IN %s
                        AND is_deleted = false
                    GROUP BY menedzer
                )
                SELECT manager, status, count FROM client_statuses ORDER BY manager, status;
            """, (
                first_day_str.split(' ')[0], last_day_str.split(' ')[0], tuple(m['planfix_user_name'] for m in MANAGERS_KPI),
                first_day_str.split(' ')[0], last_day_str.split(' ')[0], tuple(m['planfix_user_name'] for m in MANAGERS_KPI)
            ))
            client_data = cur.fetchall()
            logger.info(f"Client data: {client_data}")

        # Объединяем данные
        kpi_data = {}
        for manager in [m['planfix_user_name'] for m in MANAGERS_KPI]:
            kpi_data[manager] = {
                'TTL': 0, 'NWI': 0, 'PSK': 0, 'PRZ': 0, 'ZKL': 0
            }

        # Заполняем данные по задачам
        for row in task_data:
            manager, task_type, count = row
            if manager in kpi_data and task_type in kpi_data[manager]:
                kpi_data[manager][task_type] = count

        # Заполняем данные по клиентам
        for row in client_data:
            manager, status, count = row
            if manager in kpi_data and status in kpi_data[manager]:
                kpi_data[manager][status] = count

        return kpi_data
    except Exception as e:
        logger.error(f"Error getting KPI data: {e}")
        return {}

def calculate_premium(kpi_data):
    """Рассчитывает премию на основе KPI данных."""
    premium_data = {}
    for manager, data in kpi_data.items():
        # Рассчитываем показатели без округления
        ttl = data['TTL'] / 100 if data['TTL'] > 0 else 0
        nwi = data['NWI'] / 100 if data['NWI'] > 0 else 0
        psk = data['PSK'] / 100 if data['PSK'] > 0 else 0
        prz = data['PRZ'] / 100 if data['PRZ'] > 0 else 0
        zkl = data['ZKL'] / 100 if data['ZKL'] > 0 else 0

        # Сначала суммируем все показатели
        total = ttl + nwi + psk + prz + zkl

        # Затем округляем все значения до 2 знаков после запятой
        ttl = round(ttl, 2)
        nwi = round(nwi, 2)
        psk = round(psk, 2)
        prz = round(prz, 2)
        zkl = round(zkl, 2)
        total = round(total, 2)

        # Базовая премия
        base = 2000

        # Рассчитываем премию
        premium = round(total * base, 0)

        premium_data[manager] = {
            'TTL': ttl,
            'NWI': nwi,
            'PSK': psk,
            'PRZ': prz,
            'ZKL': zkl,
            'SUM': total,
            'FND': base,
            'PRK': premium,
            'PRW': round(premium * 0.08, 0),  # 8% от премии
            'TOT': round(premium * 1.08, 0)   # Премия + 8%
        }

    return premium_data

def generate_premium_report(conn):
    """
    Generate premium report for all managers in MANAGERS_KPI.
    """
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    kpi_data = get_kpi_data(conn, current_month, current_year)
    premium_data = calculate_premium(kpi_data)
    
    # Формируем отчет
    report = []
    report.append(f"PREMIA {current_month:02d}.{current_year}")
    report.append("═══════════════════════")
    report.append("KPI |   Kozik | Stukalo")
    report.append("───────────────────────")
    
    # Добавляем показатели
    indicators = ['TTL', 'NWI', 'PSK', 'PRZ', 'ZKL']
    for indicator in indicators:
        kozik_value = premium_data['Kozik Andrzej'][indicator]
        stukalo_value = premium_data['Stukalo Nazarii'][indicator]
        report.append(f"{indicator:3} | {format_float(kozik_value):>7} | {format_float(stukalo_value):>7}")
    
    report.append("───────────────────────")
    
    # Добавляем сумму
    kozik_sum = premium_data['Kozik Andrzej']['SUM']
    stukalo_sum = premium_data['Stukalo Nazarii']['SUM']
    report.append(f"SUM | {format_float(kozik_sum):>7} | {format_float(stukalo_sum):>7}")
    
    # Добавляем базовую премию
    kozik_fnd = premium_data['Kozik Andrzej']['FND']
    stukalo_fnd = premium_data['Stukalo Nazarii']['FND']
    report.append(f"FND | {kozik_fnd:>7} | {stukalo_fnd:>7}")
    
    report.append("───────────────────────")
    
    # Добавляем премию и итоги
    kozik_prk = premium_data['Kozik Andrzej']['PRK']
    stukalo_prk = premium_data['Stukalo Nazarii']['PRK']
    report.append(f"PRK | {kozik_prk:>7} | {stukalo_prk:>7}")
    
    kozik_prw = premium_data['Kozik Andrzej']['PRW']
    stukalo_prw = premium_data['Stukalo Nazarii']['PRW']
    report.append(f"PRW | {kozik_prw:>7} | {stukalo_prw:>7}")
    
    kozik_tot = premium_data['Kozik Andrzej']['TOT']
    stukalo_tot = premium_data['Stukalo Nazarii']['TOT']
    report.append(f"TOT | {kozik_tot:>7} | {stukalo_tot:>7}")
    
    report.append("═══════════════════════")
    
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
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Message sent successfully to Telegram")
            return True
        else:
            logger.error(f"Failed to send message to Telegram: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending to Telegram: {str(e)}")
        return False

def main():
    """
    Main function to generate and send premium report.
    """
    logger.info("Starting premium report generation...")
    
    # Check environment variables
    check_required_env_vars()
    
    try:
        # Connect to Supabase
        conn = get_supabase_connection()
        
        # Generate report
        report = generate_premium_report(conn)
        
        # Send to Telegram
        if send_to_telegram(report):
            logger.info("Report sent to Telegram successfully")
        else:
            logger.error("Failed to send report to Telegram")
        
        # Close connection
        conn.close()
        logger.info("Supabase connection closed.")
        
    except Exception as e:
        logger.error(f"Error generating premium report: {str(e)}")
        raise
    finally:
        logger.info("Premium report generation finished.")

if __name__ == "__main__":
    main() 