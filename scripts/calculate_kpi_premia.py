import psycopg2
import requests
from datetime import datetime, date
import os
import logging
from dotenv import load_dotenv
from config import MANAGERS_KPI
import planfix_utils

# Load environment variables from .env file
load_dotenv()

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

def get_kpi_metrics(current_month: int, current_year: int) -> dict:
    """Get KPI metrics and their weights for the current month."""
    query = """
        SELECT 
            month,
            year,
            premia_kpi,
            nwi,
            wtr,
            psk,
            wdm,
            prz,
            zkl,
            spt,
            ofw,
            ttl
        FROM kpi_metrics
        WHERE month = %s AND year = %s
    """
    results = _execute_query(query, (f"{current_month:02d}", current_year), "KPI metrics")
    
    if not results:
        logger.warning(f"No KPI metrics found for {current_month}/{current_year}")
        return {}
    
    # Get the first (and should be only) row
    row = results[0]
    
    # Create a dictionary of KPI codes and their plans
    metrics = {
        'NWI': {'plan': row[3], 'weight': 0},  # nwi
        'WTR': {'plan': row[4], 'weight': 0},  # wtr
        'PSK': {'plan': row[5], 'weight': 0},  # psk
        'WDM': {'plan': row[6], 'weight': 0},  # wdm
        'PRZ': {'plan': row[7], 'weight': 0},  # prz
        'ZKL': {'plan': row[8], 'weight': 0},  # zkl
        'SPT': {'plan': row[9], 'weight': 0},  # spt
        'OFW': {'plan': row[10], 'weight': 0}, # ofw
        'TTL': {'plan': row[11], 'weight': 0}  # ttl
    }
    
    # Calculate weight based on number of active KPIs (non-null plans)
    active_kpis = sum(1 for metric in metrics.values() if metric['plan'] is not None)
    if active_kpis > 0:
        weight = 1.0 / active_kpis
        for metric in metrics.values():
            if metric['plan'] is not None:
                metric['weight'] = weight
    
    # Add premia value
    metrics['premia'] = row[2]  # premia_kpi
    
    return metrics

def get_actual_kpi_values(start_date: str, end_date: str) -> dict:
    """Get actual KPI values for the period."""
    # Get task counts
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
    
    # Get client status counts
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
    
    PLANFIX_USER_NAMES = tuple(m['planfix_user_name'] for m in MANAGERS_KPI)
    
    task_results = _execute_query(task_query, (
        start_date, end_date, PLANFIX_USER_NAMES,
        start_date, end_date, PLANFIX_USER_NAMES,
        start_date, end_date, PLANFIX_USER_NAMES
    ), "task counts")
    
    client_results = _execute_query(client_query, (
        start_date.split(' ')[0], end_date.split(' ')[0], PLANFIX_USER_NAMES,
        start_date.split(' ')[0], end_date.split(' ')[0], PLANFIX_USER_NAMES,
        start_date.split(' ')[0], end_date.split(' ')[0], PLANFIX_USER_NAMES
    ), "client statuses")
    
    # Combine results into a single dictionary
    actual_values = {
        'Kozik Andrzej': {},
        'Stukalo Nazarii': {}
    }
    
    for row in task_results:
        manager, metric, value = row
        actual_values[manager][metric] = value
    
    for row in client_results:
        manager, metric, value = row
        actual_values[manager][metric] = value
    
    return actual_values

def calculate_kpi_coefficients(metrics: dict, actual_values: dict) -> dict:
    """Calculate KPI coefficients for each manager."""
    results = {
        'Kozik Andrzej': {'coefficients': {}, 'total': 0, 'premia': 0},
        'Stukalo Nazarii': {'coefficients': {}, 'total': 0, 'premia': 0}
    }
    
    # Set premia value for both managers
    premia = metrics.get('premia', 0)
    results['Kozik Andrzej']['premia'] = premia
    results['Stukalo Nazarii']['premia'] = premia
    
    # Calculate coefficients for each KPI
    for kpi_code, metric_data in metrics.items():
        if kpi_code == 'premia':
            continue
            
        plan = metric_data['plan']
        weight = metric_data['weight']
        
        if plan is None or weight == 0:
            continue
            
        for manager in results.keys():
            actual = actual_values[manager].get(kpi_code, 0)
            
            # Calculate coefficient
            coefficient = min(1.0, actual / plan)
            
            # Store coefficient and weighted value
            results[manager]['coefficients'][kpi_code] = {
                'actual': actual,
                'plan': plan,
                'coefficient': coefficient,
                'weight': weight,
                'weighted': float(coefficient) * float(weight)
            }
            
            # Update total
            results[manager]['total'] += float(coefficient) * float(weight)
    
    return results

def get_additional_premia(start_date: str, end_date: str) -> dict:
    """Get additional premia (PRW) from planfix_orders table."""
    query = """
        SELECT 
            menedzher,
            COALESCE(SUM(NULLIF(REPLACE(REPLACE(laczna_prowizja_pln, ' ', ''), ',', '.'), '')::DECIMAL(10,2)), 0) as total_premia
        FROM planfix_orders
        WHERE 
            data_realizacji IS NOT NULL 
            AND data_realizacji != ''
            AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
            AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') < %s::timestamp
            AND menedzher IN %s
            AND is_deleted = false
        GROUP BY menedzher
    """
    
    PLANFIX_USER_IDS = tuple(m['planfix_user_id'] for m in MANAGERS_KPI)
    results = _execute_query(query, (start_date, end_date, PLANFIX_USER_IDS), "additional premia")
    
    # Initialize with zeros
    additional_premia = {
        'Kozik Andrzej': 0,
        'Stukalo Nazarii': 0
    }
    
    # Map results to manager names
    for row in results:
        manager_id = row[0]
        premia = float(row[1]) if row[1] is not None else 0
        
        # Find manager name by ID
        manager = next((m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_id'] == manager_id), None)
        if manager:
            additional_premia[manager] = premia
    
    return additional_premia

def format_premia_report(coefficients: dict, current_month: int, current_year: int, additional_premia: dict) -> str:
    """Format the premia report for Telegram."""
    message = "```\n"
    message += f"PREMIA {current_month:02d}.{current_year}\n"
    message += "═══════════════════════\n"
    message += "KPI |   Kozik | Stukalo\n"
    message += "───────────────────────\n"
    
    # Определяем порядок показателей
    kpi_order = [
        'TTL', 'KZI', 'KZP', 'KZN', 'KZK', 'KZT', 'KZR', 'KZS',
        'NWI', 'WTR', 'PSK',
        'WDM', 'PRZ', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK',
        'OFW', 'ZAM', 'PRC'
    ]
    
    # Display coefficients
    for kpi_code in kpi_order:
        kozik_coef = coefficients['Kozik Andrzej']['coefficients'].get(kpi_code, {}).get('weighted', 0)
        stukalo_coef = coefficients['Stukalo Nazarii']['coefficients'].get(kpi_code, {}).get('weighted', 0)
        
        if kozik_coef > 0 or stukalo_coef > 0:
            message += f"{kpi_code:3} | {kozik_coef:6.2f} | {stukalo_coef:6.2f}\n"
    
    # Display totals
    message += "───────────────────────\n"
    # Используем точные значения без округления
    kozik_sum = coefficients['Kozik Andrzej']['total']
    stukalo_sum = coefficients['Stukalo Nazarii']['total']
    message += f"SUM | {kozik_sum:6.2f} | {stukalo_sum:6.2f}\n"
    
    # FND берется из таблицы kpi_metrics и одинаково для обоих продавцов
    fnd = float(coefficients['Kozik Andrzej']['premia'])  # Значение из таблицы (2000)
    message += f"FND | {fnd:6.0f} | {fnd:6.0f}\n"
    message += "───────────────────────\n"
    
    # Calculate and display premia (PRK = SUM * FND)
    kozik_premia = int(kozik_sum * fnd)
    stukalo_premia = int(stukalo_sum * fnd)
    
    message += f"PRK | {kozik_premia:6.0f} | {stukalo_premia:6.0f}\n"
    
    # Display additional premia (PRW)
    message += f"PRW | {additional_premia['Kozik Andrzej']:6.0f} | {additional_premia['Stukalo Nazarii']:6.0f}\n"
    
    # Calculate and display total (TOT = PRK + PRW)
    message += f"TOT | {kozik_premia + additional_premia['Kozik Andrzej']:6.0f} | {stukalo_premia + additional_premia['Stukalo Nazarii']:6.0f}\n"
    message += "═══════════════════════\n"
    message += "```"
    
    return message

def send_to_telegram(message: str):
    """Send the premia report to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to send message to Telegram: {response.text}")
        else:
            logger.info("Message sent successfully to Telegram")
            
    except Exception as e:
        logger.error(f"Error sending to Telegram: {str(e)}")
        raise

def main():
    """Main function to calculate and send KPI premia report."""
    try:
        _check_env_vars()
        
        # Get current month and year
        today = date.today()
        current_month = today.month
        current_year = today.year
        
        # Get start and end dates for the current month
        start_date = datetime(current_year, current_month, 1).strftime('%Y-%m-%d %H:%M:%S')
        if current_month == 12:
            end_date = datetime(current_year + 1, 1, 1).strftime('%Y-%m-%d %H:%M:%S')
        else:
            end_date = datetime(current_year, current_month + 1, 1).strftime('%Y-%m-%d %H:%M:%S')
        
        # Get KPI metrics and their weights
        metrics = get_kpi_metrics(current_month, current_year)
        if not metrics:
            logger.error("No KPI metrics found for the current month")
            return
        
        # Get actual KPI values
        actual_values = get_actual_kpi_values(start_date, end_date)
        
        # Calculate KPI coefficients
        coefficients = calculate_kpi_coefficients(metrics, actual_values)
        
        # Get additional premia (PRW)
        additional_premia = get_additional_premia(start_date, end_date)
        
        # Format and send report
        message = format_premia_report(coefficients, current_month, current_year, additional_premia)
        send_to_telegram(message)
        
        logger.info("KPI premia report sent successfully")
        
    except Exception as e:
        logger.error(f"Error in KPI premia calculation: {str(e)}")
        raise

if __name__ == "__main__":
    main() 