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
    """Получает список активных KPI показателей и их плановые значения."""
    active_metrics = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                manager,
                metrics_for_calculation,
                revenue_plan,
                kpi_base
            FROM kpi_metrics 
            WHERE year = %s AND month = %s
        """, (year, month))
        
        for row in cur.fetchall():
            manager = row[0]
            metrics = row[1].split(',') if row[1] else []
            revenue_plan = row[2]
            kpi_base = row[3]
            
            active_metrics[manager] = {
                'metrics': metrics,
                'revenue_plan': revenue_plan,
                'kpi_base': kpi_base
            }
    
    return active_metrics

def get_actual_kpi_values(conn, month, year):
    """Получает фактические значения KPI показателей."""
    actual_values = {}
    
    # Получаем первый и последний день месяца
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # Форматируем даты
    first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
    last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')
    
    with conn.cursor() as cur:
        # Получаем значения для клиентских статусов
        client_query = """
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
                SELECT menedzer AS manager, 'WTR' as status, COUNT(*) as count
                FROM planfix_clients
                WHERE data_dodania_do_w_trakcie IS NOT NULL AND data_dodania_do_w_trakcie != ''
                    AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') >= %s::date
                    AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') < %s::date
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
            SELECT manager, status, count FROM client_statuses;
        """
        
        # Получаем значения для задач
        task_query = """
            WITH task_counts AS (
                SELECT
                    owner_name AS manager,
                    CASE 
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Nawiązać pierwszy kontakt' THEN 'WDM'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną' THEN 'PRZ'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Zadzwonić do klienta' THEN 'ZKL'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Przeprowadzić spotkanie' THEN 'SPT'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Wysłać materiały' THEN 'MAT'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Odpowiedzieć na pytanie techniczne' THEN 'TPY'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Zapisać na media społecznościowe' THEN 'MSP'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Opowiedzieć o nowościach' THEN 'NOW'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Zebrać opinie' THEN 'OPI'
                        WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Przywrócić klienta' THEN 'WRK'
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
                GROUP BY owner_name, task_type
            ),
            kzi_counts AS (
                SELECT
                    owner_name AS manager,
                    'KZI' AS task_type,
                    COUNT(*) AS task_count
                FROM planfix_tasks
                WHERE
                    data_zakonczenia_zadania IS NOT NULL
                    AND data_zakonczenia_zadania >= %s::timestamp
                    AND data_zakonczenia_zadania < %s::timestamp
                    AND owner_name IN %s
                    AND is_deleted = false
                    AND TRIM(SPLIT_PART(title, ' /', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną'
                    AND wynik = 'Klient jest zainteresowany'
                GROUP BY owner_name
            ),
            ttl_counts AS (
                SELECT
                    owner_name AS manager,
                    'TTL' AS task_type,
                    COUNT(*) AS task_count
                FROM planfix_tasks
                WHERE
                    data_zakonczenia_zadania IS NOT NULL
                    AND data_zakonczenia_zadania >= %s::timestamp
                    AND data_zakonczenia_zadania < %s::timestamp
                    AND owner_name IN %s
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
                GROUP BY owner_name
            )
            SELECT 
                manager,
                task_type,
                task_count
            FROM (
                SELECT * FROM task_counts
                UNION ALL
                SELECT * FROM kzi_counts
                UNION ALL
                SELECT * FROM ttl_counts
            ) combined_results
            WHERE task_type IS NOT NULL;
        """
        
        # Получаем значения для заказов
        order_query = """
            SELECT 
                menedzher,
                status,
                COUNT(*) as count
            FROM planfix_orders
            WHERE 
                TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp 
                AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') <= %s::timestamp
                AND status IN ('OFW', 'ZAM', 'PRC')
                AND is_deleted = false
            GROUP BY menedzher, status
        """
        
        # Выполняем запросы
        PLANFIX_USER_NAMES = tuple(m['planfix_user_name'] for m in MANAGERS_KPI)
        
        # Получаем значения клиентских статусов
        cur.execute(client_query, (
            first_day.date(), last_day.date(), PLANFIX_USER_NAMES,
            first_day.date(), last_day.date(), PLANFIX_USER_NAMES,
            first_day.date(), last_day.date(), PLANFIX_USER_NAMES
        ))
        
        for row in cur.fetchall():
            manager, status, count = row
            if manager not in actual_values:
                actual_values[manager] = {}
            actual_values[manager][status] = count
        
        # Получаем значения задач
        cur.execute(task_query, (
            first_day_str, last_day_str, PLANFIX_USER_NAMES,
            first_day_str, last_day_str, PLANFIX_USER_NAMES,
            first_day_str, last_day_str, PLANFIX_USER_NAMES
        ))
        
        for row in cur.fetchall():
            manager, task_type, count = row
            if manager not in actual_values:
                actual_values[manager] = {}
            actual_values[manager][task_type] = count
        
        # Получаем значения заказов
        cur.execute(order_query, (first_day_str, last_day_str))
        
        for row in cur.fetchall():
            manager, status, count = row
            if manager not in actual_values:
                actual_values[manager] = {}
            actual_values[manager][status] = count
    
    return actual_values

def get_additional_premia(conn, month, year):
    """Получает дополнительные премии (PRW) из таблицы planfix_orders."""
    # Получаем первый и последний день месяца
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # Форматируем даты
    first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
    last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')
    
    additional_premia = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                menedzher,
                COALESCE(SUM(NULLIF(REPLACE(REPLACE(laczna_prowizja_pln, ' ', ''), ',', '.'), '')::DECIMAL(10,2)), 0) as total_premia
            FROM planfix_orders
            WHERE 
                data_realizacji IS NOT NULL 
                AND data_realizacji != ''
                AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
                AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') <= %s::timestamp
                AND menedzher IN %s
                AND is_deleted = false
            GROUP BY menedzher
        """, (first_day_str, last_day_str, tuple(m['planfix_user_name'] for m in MANAGERS_KPI)))
        
        for row in cur.fetchall():
            manager = row[0]
            premia = float(row[1]) if row[1] is not None else 0
            additional_premia[manager] = round(premia, 0)
    
    return additional_premia

def calculate_kpi_premia(conn):
    """Рассчитывает премии на основе KPI показателей."""
    # Получаем текущий месяц и год
    now = datetime.now()
    month = now.month
    year = now.year
    
    # Получаем активные KPI показатели
    active_metrics = get_active_kpi_metrics(conn, month, year)
    
    # Получаем фактические значения
    actual_values = get_actual_kpi_values(conn, month, year)
    
    # Получаем дополнительные премии
    additional_premia = get_additional_premia(conn, month, year)
    
    # Рассчитываем премии
    premium_data = {}
    
    for manager, data in active_metrics.items():
        metrics = data['metrics']
        if not metrics:
            continue
            
        # Вычисляем вес каждого показателя
        weight = 1.0 / len(metrics)
        
        # Рассчитываем KPI для каждого показателя
        kpi_values = {}
        total_kpi = 0
        
        for metric in metrics:
            actual = actual_values.get(manager, {}).get(metric, 0)
            plan = data.get('revenue_plan', 0)
            
            if plan > 0:
                kpi = (actual / plan) * weight
                kpi = math.floor(kpi * 100 + 0.5) / 100  # Математическое округление до 2 знаков
                kpi_values[metric] = kpi
                total_kpi += kpi
        
        # Рассчитываем премию
        base = data.get('kpi_base', 2000)  # По умолчанию 2000
        premium = round(total_kpi * base, 0)
        
        premium_data[manager] = {
            **kpi_values,
            'SUM': math.floor(total_kpi * 100 + 0.5) / 100,  # Математическое округление до 2 знаков
            'FND': base,
            'PRK': premium,
            'PRW': additional_premia.get(manager, 0),
            'TOT': premium + additional_premia.get(manager, 0)
        }
    
    return premium_data

def generate_premium_report(premium_data, month, year):
    """Генерирует отчет по премиям."""
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