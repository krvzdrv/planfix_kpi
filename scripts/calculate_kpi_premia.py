import os
import sys
import logging
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
import math
import requests
from config import MANAGERS_KPI
from planfix_utils import (
    check_required_env_vars,
    get_supabase_connection
)

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

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

# Список всех возможных KPI показателей в нужном порядке
ALL_KPI_METRICS = [
    'NWI', 'WTR', 'PSK',
    'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL',
    'OFW', 'ZAM', 'PRC'
]

def _check_env_vars():
    """Checks for required environment variables and logs errors if any are missing."""
    required_env_vars = {
        'SUPABASE_HOST': PG_HOST,
        'SUPABASE_DB': PG_DB,
        'SUPABASE_USER': PG_USER,
        'SUPABASE_PASSWORD': PG_PASSWORD,
        'SUPABASE_PORT': PG_PORT,
        'TELEGRAM_BOT_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': CHAT_ID
    }
    missing_vars = [var for var, value in required_env_vars.items() if not value]
    if missing_vars:
        error_msg = f"Missing environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    if not MANAGERS_KPI:
        error_msg = "MANAGERS_KPI list in config.py is empty. Cannot generate KPI report."
        logger.error(error_msg)
        raise ValueError(error_msg)

def _execute_query(query: str, params: tuple, description: str) -> list:
    """Helper function to connect, execute query, and close connection."""
    conn = None
    try:
        conn = psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT)
        cur = conn.cursor()
        logger.info(f"Executing query for: {description} with params: {params}")
        cur.execute(query, params)
        rows = cur.fetchall()
        logger.info(f"Query for {description} returned {len(rows)} rows.")
        return rows
    except psycopg2.Error as e:
        logger.error(f"Database error during query for {description}: {e}")
        raise
    finally:
        if conn:
            conn.close()

def get_active_kpi_metrics(conn, month, year):
    """Получение активных KPI метрик для текущего месяца"""
    cur = conn.cursor()
    try:
        # Преобразуем месяц в строку с ведущим нулем
        month_str = f"{month:02d}"
        
        cur.execute("""
            SELECT 
                nwi, wtr, psk, wdm, prz, zkl, spt, ofw, ttl,
                revenue_plan
            FROM kpi_metrics
            WHERE year = %s
            AND month = %s
            ORDER BY id
        """, (year, month_str))
        
        results = cur.fetchall()
        active_metrics = {}
        
        # Создаем одинаковые метрики для всех менеджеров
        for manager in [m['planfix_user_name'] for m in MANAGERS_KPI]:
            active_metrics[manager] = []
            for row in results:
                # Добавляем все метрики из строки
                metrics = {
                    'NWI': row[0],  # nwi
                    'WTR': row[1],  # wtr
                    'PSK': row[2],  # psk
                    'WDM': row[3],  # wdm
                    'PRZ': row[4],  # prz
                    'ZKL': row[5],  # zkl
                    'SPT': row[6],  # spt
                    'OFW': row[7],  # ofw
                    'TTL': row[8],  # ttl
                }
                
                # Добавляем каждую метрику в список
                for metric_name, planned_value in metrics.items():
                    if planned_value is not None:  # Добавляем только если значение не NULL
                        active_metrics[manager].append({
                            'metric_name': metric_name,
                            'planned_value': planned_value
                        })
                
                # Добавляем план по выручке
                if row[9] is not None:  # revenue_plan
                    active_metrics[manager].append({
                        'metric_name': 'REVENUE',
                        'planned_value': row[9]
                    })
        
        return active_metrics
    finally:
        cur.close()

def get_actual_kpi_values(conn, month, year):
    """Получение фактических значений KPI"""
    cur = conn.cursor()
    try:
        # Подготавливаем списки имен и ID менеджеров
        PLANFIX_USER_NAMES = tuple(m['planfix_user_name'] for m in MANAGERS_KPI)
        PLANFIX_USER_IDS = tuple(m['planfix_user_id'] for m in MANAGERS_KPI)
        
        # Формируем даты для фильтрации
        first_day = datetime(year, month, 1)
        last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        first_day_str = first_day.strftime('%Y-%m-%d')
        last_day_str = last_day.strftime('%Y-%m-%d')
        
        # SQL запрос для получения данных по заказам
        order_query = """
            SELECT 
                menedzher,
                COUNT(*) as total_orders,
                COUNT(CASE WHEN status = 1 THEN 1 END) as completed_orders,
                COUNT(CASE WHEN status = 2 THEN 1 END) as cancelled_orders,
                COUNT(CASE WHEN status = 1 AND data_realizacji IS NOT NULL THEN 1 END) as on_time_orders,
                COUNT(CASE WHEN status = 1 AND data_realizacji IS NULL THEN 1 END) as late_orders,
                COUNT(CASE WHEN status = 1 AND data_realizacji IS NOT NULL 
                    AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') <= %s THEN 1 END) as on_time_orders_with_date
            FROM planfix_orders
            WHERE 
                EXTRACT(YEAR FROM TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI')) = %s
                AND EXTRACT(MONTH FROM TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI')) = %s
                AND menedzher IN %s
            GROUP BY menedzher
        """
        
        cur.execute(order_query, (last_day_str, year, month, PLANFIX_USER_NAMES))
        order_results = cur.fetchall()
        
        # Запрос для получения дополнительных премий
        premia_query = """
            SELECT 
                menedzher as manager,
                COALESCE(SUM(NULLIF(REPLACE(REPLACE(laczna_prowizja_pln, ' ', ''), ',', '.'), '')::DECIMAL(10,2)), 0) as total_premia
            FROM planfix_orders
            WHERE TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
            AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') <= %s::timestamp
            AND menedzher IN %s
            AND is_deleted = false
            GROUP BY menedzher
        """
        
        cur.execute(premia_query, (first_day_str, last_day_str, PLANFIX_USER_NAMES))
        premia_results = cur.fetchall()
        
        # Обработка результатов
        actual_values = {}
        for row in order_results:
            manager = row[0]
            total_orders = row[1]
            completed_orders = row[2]
            cancelled_orders = row[3]
            on_time_orders = row[4]
            late_orders = row[5]
            on_time_orders_with_date = row[6]
            
            if manager not in actual_values:
                actual_values[manager] = {
                    'OFW': 0,
                    'ZAM': 0,
                    'PRC': 0,
                    'premia': 0
                }
            
            actual_values[manager]['OFW'] = completed_orders
            actual_values[manager]['ZAM'] = cancelled_orders
            actual_values[manager]['PRC'] = completed_orders
        
        # Добавляем премии
        for row in premia_results:
            manager = row[0]
            premia = row[1]
            
            if manager not in actual_values:
                actual_values[manager] = {
                    'OFW': 0,
                    'ZAM': 0,
                    'PRC': 0,
                    'premia': 0
                }
            
            actual_values[manager]['premia'] = premia
        
        return actual_values
    finally:
        cur.close()

def get_additional_premia(start_date_str: str, end_date_str: str) -> list:
    """Получает данные о дополнительных премиях за период."""
    query = """
        SELECT 
            menedzher,
            COALESCE(SUM(NULLIF(REPLACE(REPLACE(laczna_prowizja_pln, ' ', ''), ',', '.'), '')::DECIMAL(10,2)), 0) as total_premia
        FROM planfix_orders
        WHERE data_realizacji IS NOT NULL 
            AND data_realizacji != ''
            AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
            AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') < %s::timestamp
            AND is_deleted = false
        GROUP BY menedzher;
    """
    results = _execute_kpi_query(query, (start_date_str, end_date_str), "additional premia")
    logger.info(f"Additional premia results: {results}")
    return results

def calculate_kpi_premia(conn):
    """Расчет премий по KPI"""
    # Получаем текущую дату
    today = datetime.now()
    month = today.month
    year = today.year
    
    # Формируем строки дат для SQL запросов
    first_day = datetime(year, month, 1)
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    
    first_day_str = first_day.strftime('%d-%m-%Y %H:%M')
    last_day_str = last_day.strftime('%d-%m-%Y %H:%M')
    
    logger.info(f"Calculating KPI premiums for period: {first_day_str} to {last_day_str}")
    
    # Получаем метрики KPI
    kpi_metrics = get_active_kpi_metrics(conn, month, year)
    
    # Получаем фактические значения KPI
    actual_values = get_actual_kpi_values(conn, month, year)
    
    # Получаем дополнительные премии
    additional_premia = get_additional_premia(first_day_str, last_day_str)
    
    # Рассчитываем премии
    premium_data = []
    
    for manager in MANAGERS_KPI:
        manager_name = manager['planfix_user_name']
        manager_metrics = kpi_metrics.get(manager_name, {})
        manager_actual = actual_values.get(manager_name, {})
        
        # Рассчитываем премию по KPI
        kpi_premium = 0
        for metric_name, planned_value in manager_metrics.items():
            actual_value = manager_actual.get(metric_name, 0)
            if actual_value >= planned_value:
                kpi_premium += 1000  # Базовая премия за достижение плана
        
        # Получаем дополнительную премию
        additional = additional_premia.get(manager_name, 0)
        
        premium_data.append({
            'manager': manager_name,
            'kpi_premium': kpi_premium,
            'additional_premium': additional,
            'total_premium': kpi_premium + additional
        })
    
    return premium_data

def generate_premium_report(premium_data, month, year):
    """Генерирует отчет по премиям."""
    report = []
    report.append(f"PREMIA {month:02d}.{year}")
    report.append("═" * 21)
    
    # Заголовок с именами менеджеров
    header = "KPI |"
    for manager in MANAGERS_KPI:
        header += f" {manager['planfix_user_name']:>8} |"
    report.append(header)
    report.append("─" * (len(header) + 2))
    
    # Показатели в нужном порядке
    for metric in ALL_KPI_METRICS:
        line = f"{metric:3} |"
        for manager in MANAGERS_KPI:
            if manager in premium_data and metric in premium_data[manager]:
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
    return "\n".join(report)

def send_to_telegram(message: str):
    """Отправляет сообщение в Telegram."""
    try:
        # Get Telegram configuration from environment variables
        telegram_token = os.getenv('TELEGRAM_TOKEN')
        telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not telegram_token or not telegram_chat_id:
            logger.error("Telegram configuration is missing")
            return
        
        # Send message to Telegram
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        data = {
            "chat_id": telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, data=data)
        response.raise_for_status()
        
    except Exception as e:
        logger.error(f"Error sending message to Telegram: {str(e)}")
        raise

def main():
    """Основная функция."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting KPI premium calculation...")
    
    try:
        _check_env_vars()
        
        # Connect to Supabase
        conn = get_supabase_connection()
        
        # Calculate premiums
        premium_data = calculate_kpi_premia(conn)
        
        # Generate report
        report = generate_premium_report(premium_data, datetime.now().month, datetime.now().year)
        
        # Send report to Telegram
        send_to_telegram(report)
        
        logger.info("KPI premia report sent successfully")
        
    except Exception as e:
        logger.error(f"Error calculating KPI premiums: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()
            logger.info("Supabase connection closed.")
        logger.info("KPI premium calculation finished.")

if __name__ == "__main__":
    main() 