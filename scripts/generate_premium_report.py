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
    """Получает данные KPI из базы данных."""
    kpi_data = {}
    
    # Получаем плановые значения выручки
    revenue_plans = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT manager, revenue_plan 
            FROM kpi_metrics 
            WHERE year = %s AND month = %s
        """, (year, month))
        for row in cur.fetchall():
            revenue_plans[row[0]] = row[1]
    
    # Получаем данные по задачам
    with conn.cursor() as cur:
        cur.execute("""
            WITH task_counts AS (
                SELECT 
                    t.manager,
                    COUNT(*) FILTER (WHERE t.status = 'TTL') as ttl_count,
                    COUNT(*) FILTER (WHERE t.status = 'NWI') as nwi_count,
                    COUNT(*) FILTER (WHERE t.status = 'PSK') as psk_count,
                    COUNT(*) FILTER (WHERE t.status = 'PRZ') as prz_count,
                    COUNT(*) FILTER (WHERE t.status = 'ZKL') as zkl_count
                FROM tasks t
                WHERE EXTRACT(MONTH FROM t.date) = %s 
                AND EXTRACT(YEAR FROM t.date) = %s
                GROUP BY t.manager
            ),
            client_status AS (
                SELECT 
                    t.manager,
                    SUM(CASE WHEN c.status = 'Fakt' THEN c.amount ELSE 0 END) as fakt_amount,
                    SUM(CASE WHEN c.status = 'Dług' THEN c.amount ELSE 0 END) as dlug_amount,
                    SUM(CASE WHEN c.status = 'Brak' THEN c.amount ELSE 0 END) as brak_amount
                FROM tasks t
                JOIN clients c ON t.client_id = c.id
                WHERE EXTRACT(MONTH FROM t.date) = %s 
                AND EXTRACT(YEAR FROM t.date) = %s
                GROUP BY t.manager
            )
            SELECT 
                tc.manager,
                tc.ttl_count,
                tc.nwi_count,
                tc.psk_count,
                tc.prz_count,
                tc.zkl_count,
                COALESCE(cs.fakt_amount, 0) as fakt_amount,
                COALESCE(cs.dlug_amount, 0) as dlug_amount,
                COALESCE(cs.brak_amount, 0) as brak_amount
            FROM task_counts tc
            LEFT JOIN client_status cs ON tc.manager = cs.manager
        """, (month, year, month, year))
        
        for row in cur.fetchall():
            manager = row[0]
            kpi_data[manager] = {
                'TTL': row[1],
                'NWI': row[2],
                'PSK': row[3],
                'PRZ': row[4],
                'ZKL': row[5],
                'fakt_amount': row[6],
                'dlug_amount': row[7],
                'brak_amount': row[8],
                'revenue_plan': revenue_plans.get(manager, 0)
            }
            
    return kpi_data

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
    """Генерирует отчет по премиям."""
    # Получаем текущий месяц и год
    now = datetime.now()
    month = now.month
    year = now.year
    
    # Получаем данные KPI
    kpi_data = get_kpi_data(conn, month, year)
    
    # Рассчитываем премии
    premium_data = calculate_premium(kpi_data)
    
    # Форматируем отчет
    report = []
    report.append(f"PREMIA {month:02d}.{year}")
    report.append("═" * 21)
    
    # Заголовок с именами менеджеров
    header = "KPI |"
    for manager in MANAGERS_KPI:
        header += f" {manager:>8} |"
    report.append(header)
    report.append("─" * (len(header) + 2))
    
    # Показатели
    metrics = ['TTL', 'NWI', 'PSK', 'PRZ', 'ZKL']
    for metric in metrics:
        line = f"{metric:3} |"
        for manager in MANAGERS_KPI:
            if manager in premium_data:
                line += f" {premium_data[manager][metric]:>8.2f} |"
            else:
                line += f" {'0.00':>8} |"
        report.append(line)
    
    report.append("─" * (len(header) + 2))
    
    # Сумма и премия
    summary_metrics = ['SUM', 'FND', 'PRK', 'PRW', 'TOT']
    for metric in summary_metrics:
        line = f"{metric:3} |"
        for manager in MANAGERS_KPI:
            if manager in premium_data:
                if metric in ['PRK', 'PRW', 'TOT']:
                    line += f" {premium_data[manager][metric]:>8.0f} |"
                else:
                    line += f" {premium_data[manager][metric]:>8.2f} |"
            else:
                line += f" {'0.00':>8} |"
        report.append(line)
        if metric == 'FND':
            report.append("─" * (len(header) + 2))
    
    report.append("═" * 21)
    
    # Добавляем информацию о выручке
    report.append(f"\nPRZYCHODY {month}/{year}\n")
    
    for manager in MANAGERS_KPI:
        if manager in kpi_data:
            data = kpi_data[manager]
            total = data['fakt_amount'] + data['dlug_amount'] + data['brak_amount']
            
            # Рассчитываем проценты
            fakt_percent = (data['fakt_amount'] / total * 100) if total > 0 else 0
            dlug_percent = (data['dlug_amount'] / total * 100) if total > 0 else 0
            brak_percent = (data['brak_amount'] / total * 100) if total > 0 else 0
            
            # Создаем прогресс-бар
            fakt_bars = int(fakt_percent / 5)
            dlug_bars = int(dlug_percent / 5)
            brak_bars = int(brak_percent / 5)
            
            progress = "█" * fakt_bars + "▒" * dlug_bars + "░" * brak_bars
            progress = progress.ljust(20)
            
            report.append(f"{manager}:")
            report.append(f"[{progress}]")
            report.append(f" █  Fakt: {data['fakt_amount']:>6.0f} PLN ({fakt_percent:>4.1f}%)")
            report.append(f" ▒  Dług: {data['dlug_amount']:>6.0f} PLN ({dlug_percent:>4.1f}%)")
            report.append(f" ░  Brak: {data['brak_amount']:>6.0f} PLN ({brak_percent:>4.1f}%)")
            report.append(f"    Fakt: {data['fakt_amount']:>6.0f} PLN")
            report.append(f"    Plan: {data['revenue_plan']:>6.0f} PLN")
            report.append("")
    
    return "\n".join(report)

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