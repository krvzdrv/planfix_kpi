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
                    COUNT(*) FILTER (WHERE t.status = 'NWI') as nwi_count,
                    COUNT(*) FILTER (WHERE t.status = 'WTR') as wtr_count,
                    COUNT(*) FILTER (WHERE t.status = 'PSK') as psk_count,
                    COUNT(*) FILTER (WHERE t.status = 'WDM') as wdm_count,
                    COUNT(*) FILTER (WHERE t.status = 'PRZ') as prz_count,
                    COUNT(*) FILTER (WHERE t.status = 'KZI') as kzi_count,
                    COUNT(*) FILTER (WHERE t.status = 'ZKL') as zkl_count,
                    COUNT(*) FILTER (WHERE t.status = 'SPT') as spt_count,
                    COUNT(*) FILTER (WHERE t.status = 'MAT') as mat_count,
                    COUNT(*) FILTER (WHERE t.status = 'TPY') as tpy_count,
                    COUNT(*) FILTER (WHERE t.status = 'MSP') as msp_count,
                    COUNT(*) FILTER (WHERE t.status = 'NOW') as now_count,
                    COUNT(*) FILTER (WHERE t.status = 'OPI') as opi_count,
                    COUNT(*) FILTER (WHERE t.status = 'WRK') as wrk_count,
                    COUNT(*) FILTER (WHERE t.status = 'TTL') as ttl_count,
                    COUNT(*) FILTER (WHERE t.status = 'OFW') as ofw_count,
                    COUNT(*) FILTER (WHERE t.status = 'ZAM') as zam_count,
                    COUNT(*) FILTER (WHERE t.status = 'PRC') as prc_count
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
                tc.nwi_count,
                tc.wtr_count,
                tc.psk_count,
                tc.wdm_count,
                tc.prz_count,
                tc.kzi_count,
                tc.zkl_count,
                tc.spt_count,
                tc.mat_count,
                tc.tpy_count,
                tc.msp_count,
                tc.now_count,
                tc.opi_count,
                tc.wrk_count,
                tc.ttl_count,
                tc.ofw_count,
                tc.zam_count,
                tc.prc_count,
                COALESCE(cs.fakt_amount, 0) as fakt_amount,
                COALESCE(cs.dlug_amount, 0) as dlug_amount,
                COALESCE(cs.brak_amount, 0) as brak_amount
            FROM task_counts tc
            LEFT JOIN client_status cs ON tc.manager = cs.manager
        """, (month, year, month, year))
        
        for row in cur.fetchall():
            manager = row[0]
            kpi_data[manager] = {
                'NWI': row[1],
                'WTR': row[2],
                'PSK': row[3],
                'WDM': row[4],
                'PRZ': row[5],
                'KZI': row[6],
                'ZKL': row[7],
                'SPT': row[8],
                'MAT': row[9],
                'TPY': row[10],
                'MSP': row[11],
                'NOW': row[12],
                'OPI': row[13],
                'WRK': row[14],
                'TTL': row[15],
                'OFW': row[16],
                'ZAM': row[17],
                'PRC': row[18],
                'fakt_amount': row[19],
                'dlug_amount': row[20],
                'brak_amount': row[21],
                'revenue_plan': revenue_plans.get(manager, 0)
            }
            
    return kpi_data

def calculate_premium(kpi_data):
    """Рассчитывает премию на основе KPI данных."""
    premium_data = {}
    for manager, data in kpi_data.items():
        # Рассчитываем показатели
        nwi = data['NWI'] / 100 if data['NWI'] > 0 else 0
        wtr = data['WTR'] / 100 if data['WTR'] > 0 else 0
        psk = data['PSK'] / 100 if data['PSK'] > 0 else 0
        wdm = data['WDM'] / 100 if data['WDM'] > 0 else 0
        prz = data['PRZ'] / 100 if data['PRZ'] > 0 else 0
        kzi = data['KZI'] / 100 if data['KZI'] > 0 else 0
        zkl = data['ZKL'] / 100 if data['ZKL'] > 0 else 0
        spt = data['SPT'] / 100 if data['SPT'] > 0 else 0
        mat = data['MAT'] / 100 if data['MAT'] > 0 else 0
        tpy = data['TPY'] / 100 if data['TPY'] > 0 else 0
        msp = data['MSP'] / 100 if data['MSP'] > 0 else 0
        now = data['NOW'] / 100 if data['NOW'] > 0 else 0
        opi = data['OPI'] / 100 if data['OPI'] > 0 else 0
        wrk = data['WRK'] / 100 if data['WRK'] > 0 else 0
        ttl = data['TTL'] / 100 if data['TTL'] > 0 else 0
        ofw = data['OFW'] / 100 if data['OFW'] > 0 else 0
        zam = data['ZAM'] / 100 if data['ZAM'] > 0 else 0
        prc = data['PRC'] / 100 if data['PRC'] > 0 else 0

        # Округляем каждый показатель до 2 знаков после запятой
        nwi = round(nwi, 2)
        wtr = round(wtr, 2)
        psk = round(psk, 2)
        wdm = round(wdm, 2)
        prz = round(prz, 2)
        kzi = round(kzi, 2)
        zkl = round(zkl, 2)
        spt = round(spt, 2)
        mat = round(mat, 2)
        tpy = round(tpy, 2)
        msp = round(msp, 2)
        now = round(now, 2)
        opi = round(opi, 2)
        wrk = round(wrk, 2)
        ttl = round(ttl, 2)
        ofw = round(ofw, 2)
        zam = round(zam, 2)
        prc = round(prc, 2)

        # Суммируем округленные показатели
        total = nwi + wtr + psk + wdm + prz + kzi + zkl + spt + mat + tpy + msp + now + opi + wrk + ttl + ofw + zam + prc

        # Базовая премия
        base = 2000

        # Рассчитываем премию
        premium = round(total * base, 0)

        premium_data[manager] = {
            'NWI': nwi,
            'WTR': wtr,
            'PSK': psk,
            'WDM': wdm,
            'PRZ': prz,
            'KZI': kzi,
            'ZKL': zkl,
            'SPT': spt,
            'MAT': mat,
            'TPY': tpy,
            'MSP': msp,
            'NOW': now,
            'OPI': opi,
            'WRK': wrk,
            'TTL': ttl,
            'OFW': ofw,
            'ZAM': zam,
            'PRC': prc,
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
    
    # Показатели в нужном порядке
    metrics = ['NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC']
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