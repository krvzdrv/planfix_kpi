import psycopg2
import requests
from datetime import datetime, date, timedelta # Added timedelta
import os
import logging # Added logging
from dotenv import load_dotenv
from config import MANAGERS_KPI 
import planfix_utils

# Load environment variables from .env file
load_dotenv()

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

# Prepare manager lists for SQL queries
PLANFIX_USER_NAMES = tuple(m['planfix_user_name'] for m in MANAGERS_KPI) if MANAGERS_KPI else tuple()
PLANFIX_USER_IDS = tuple(m['planfix_user_id'] for m in MANAGERS_KPI) if MANAGERS_KPI else tuple()

def _check_env_vars():
    """Checks for required environment variables and logs errors if any are missing."""
    required_env_vars = {
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_USER_TOKEN': planfix_utils.PLANFIX_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
        'SUPABASE_CONNECTION_STRING': planfix_utils.SUPABASE_CONNECTION_STRING,
        'SUPABASE_HOST': planfix_utils.SUPABASE_HOST,
        'SUPABASE_DB': planfix_utils.SUPABASE_DB,
        'SUPABASE_USER': planfix_utils.SUPABASE_USER,
        'SUPABASE_PASSWORD': planfix_utils.SUPABASE_PASSWORD,
        'SUPABASE_PORT': planfix_utils.SUPABASE_PORT,
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

def _execute_kpi_query(query: str, params: tuple, description: str) -> list:
    """Helper function to connect, execute query, and close connection."""
    conn = None
    try:
        conn = psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT)
        cur = conn.cursor()
        logger.info(f"Executing KPI query for: {description} with params: {params}")
        cur.execute(query, params)
        rows = cur.fetchall()
        logger.info(f"Query for {description} returned {len(rows)} rows.")
        return rows
    except psycopg2.Error as e:
        logger.error(f"Database error during KPI query for {description}: {e}")
        # Optionally re-raise or return empty list depending on desired error handling
        raise # Re-raise to stop script if DB query fails
    finally:
        if conn:
            conn.close()


def count_tasks_by_type(start_date_str: str, end_date_str: str) -> list:
    if not PLANFIX_USER_NAMES: return []
    logger.info(f"\nDebug - Task query parameters:")
    logger.info(f"Start date: {start_date_str}")
    logger.info(f"End date: {end_date_str}")
    # Debug query to check task data format
    debug_query = """
        SELECT 
            owner_name,
            title,
            wynik,
            data_zakonczenia_zadania,
            TO_CHAR(data_zakonczenia_zadania, 'YYYY-MM-DD HH24:MI:SS') as formatted_date,
            is_deleted
        FROM planfix_tasks
        WHERE owner_name IN %s
        AND data_zakonczenia_zadania IS NOT NULL
        AND data_zakonczenia_zadania >= %s::timestamp
        AND data_zakonczenia_zadania < %s::timestamp
        AND is_deleted = false
        LIMIT 10;
    """
    debug_results = _execute_kpi_query(debug_query, (PLANFIX_USER_NAMES, start_date_str, end_date_str), "debug tasks")
    logger.info("\nDebug - Sample task data:")
    for row in debug_results:
        logger.info(f"Manager: {row[0]}, Title: {row[1]}, Wynik: {row[2]}, Date: {row[3]}, Formatted: {row[4]}, Deleted: {row[5]}")
    # Основной KPI-запрос
    query = f"""
        WITH task_counts AS (
            SELECT
                owner_name AS manager,
                TRIM(SPLIT_PART(title, '/', 1)) AS task_type,
                wynik,
                COUNT(*) AS task_count
            FROM planfix_tasks
            WHERE
                data_zakonczenia_zadania IS NOT NULL
                AND data_zakonczenia_zadania >= %s::timestamp
                AND data_zakonczenia_zadania < %s::timestamp
                AND owner_name IN %s
                AND is_deleted = false
            GROUP BY
                owner_name, TRIM(SPLIT_PART(title, '/', 1)), wynik
        )
        SELECT 
            manager,
            task_type,
            wynik,
            task_count
        FROM task_counts
        ORDER BY manager, task_type, wynik;
    """
    results = _execute_kpi_query(query, (start_date_str, end_date_str, PLANFIX_USER_NAMES), "tasks by type")
    logger.info(f"Task results: {results}")
    return results

def count_offers(start_date_str: str, end_date_str: str) -> list:
    if not PLANFIX_USER_IDS: return []
    
    logger.info(f"\nDebug - Offer query parameters:")
    logger.info(f"Start date: {start_date_str}")
    logger.info(f"End date: {end_date_str}")
    
    # Debug query to check offer data format
    debug_query = """
        SELECT 
            menedzher,
            data_wyslania_oferty,
            TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') as parsed_date
        FROM planfix_orders
        WHERE menedzher IN %s
        AND data_wyslania_oferty IS NOT NULL
        AND data_wyslania_oferty != ''
        LIMIT 5;
    """
    debug_results = _execute_kpi_query(debug_query, (PLANFIX_USER_IDS,), "debug offers")
    logger.info("\nDebug - Sample offer data:")
    for row in debug_results:
        logger.info(f"Manager: {row[0]}, Date: {row[1]}, Parsed: {row[2]}")
    
    query = f"""
        SELECT
            menedzher AS manager_id,
            COUNT(*) AS offer_count
        FROM
            planfix_orders
        WHERE
            data_wyslania_oferty IS NOT NULL
            AND data_wyslania_oferty != ''
            AND TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
            AND TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') < %s::timestamp
            AND menedzher IN %s
        GROUP BY
            menedzher;
    """
    results = _execute_kpi_query(query, (start_date_str, end_date_str, PLANFIX_USER_IDS), "offers sent")
    logger.info(f"Offer results: {results}")
    return results

def count_orders(start_date_str: str, end_date_str: str) -> list:
    if not PLANFIX_USER_IDS: return []
    
    logger.info(f"\nDebug - Order query parameters:")
    logger.info(f"Start date: {start_date_str}")
    logger.info(f"End date: {end_date_str}")
    
    # Debug query to check order data format
    debug_query = """
        SELECT 
            menedzher,
            data_potwierdzenia_zamowienia,
            data_realizacji,
            wartosc_netto_pln,
            TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') as parsed_confirmation_date,
            TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') as parsed_realization_date
        FROM planfix_orders
        WHERE menedzher IN %s
        AND (data_potwierdzenia_zamowienia IS NOT NULL OR data_realizacji IS NOT NULL)
        LIMIT 5;
    """
    debug_results = _execute_kpi_query(debug_query, (PLANFIX_USER_IDS,), "debug orders")
    logger.info("\nDebug - Sample order data:")
    for row in debug_results:
        logger.info(f"Manager: {row[0]}, Confirmation: {row[1]}, Realization: {row[2]}, Amount: {row[3]}")
        logger.info(f"Parsed dates - Confirmation: {row[4]}, Realization: {row[5]}")
    
    query = f"""
        WITH order_metrics AS (
            SELECT
                menedzher AS manager_id, COUNT(*) AS order_count, 0 AS total_amount
            FROM planfix_orders
            WHERE data_potwierdzenia_zamowienia IS NOT NULL AND data_potwierdzenia_zamowienia != ''
                AND TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
                AND TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') < %s::timestamp
                AND menedzher IN %s
                AND is_deleted = false
            GROUP BY menedzher
            UNION ALL
            SELECT
                menedzher AS manager_id, 0 AS order_count,
                COALESCE(SUM(NULLIF(REPLACE(REPLACE(wartosc_netto_pln, ' ', ''), ',', '.'), '')::DECIMAL(10,2)), 0) AS total_amount
            FROM planfix_orders
            WHERE data_realizacji IS NOT NULL AND data_realizacji != ''
                AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
                AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') < %s::timestamp
                AND menedzher IN %s
                AND is_deleted = false
            GROUP BY menedzher
        )
        SELECT manager_id, SUM(order_count) AS order_count, SUM(total_amount) AS total_amount
        FROM order_metrics
        GROUP BY manager_id;
    """
    results = _execute_kpi_query(query, (start_date_str, end_date_str, PLANFIX_USER_IDS, start_date_str, end_date_str, PLANFIX_USER_IDS), "orders and revenue")
    logger.info(f"Order results: {results}")
    return results

def count_client_statuses(start_date_str: str, end_date_str: str) -> list:
    if not PLANFIX_USER_NAMES: return []
    query = f"""
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
        SELECT manager, status, count FROM client_statuses ORDER BY manager, status;
    """
    return _execute_kpi_query(query, (
        start_date_str.split(' ')[0], end_date_str.split(' ')[0], PLANFIX_USER_NAMES,
        start_date_str.split(' ')[0], end_date_str.split(' ')[0], PLANFIX_USER_NAMES,
        start_date_str.split(' ')[0], end_date_str.split(' ')[0], PLANFIX_USER_NAMES
    ), "client statuses")


def send_to_telegram(task_results, offer_results, order_results, client_results, report_type):
    logger.info(f"Preparing {report_type} KPI report for Telegram.")
    logger.info(f"Task results received: {task_results}")
    
    data = {
        mgr_info['planfix_user_id']: {
            'WDM': 0, 'ZKL': 0, 'PRZ': 0, 'SPT': 0, 'MAT': 0, 'NOW': 0, 'MSP': 0, 
            'TPY': 0, 'WRK': 0, 'OPI': 0, 'OFW': 0, 'TTL': 0, 'ZAM': 0, 
            'PRC': 0.0, 'NWI': 0, 'WTR': 0, 'PSK': 0,
            'name': mgr_info['planfix_user_name'], 'alias': mgr_info['telegram_alias']
        } for mgr_info in MANAGERS_KPI
    }
    name_to_id_map = {m['planfix_user_name']: m['planfix_user_id'] for m in MANAGERS_KPI}
    logger.info(f"Manager name to ID mapping: {name_to_id_map}")

    for manager_name, task_type, wynik, count in task_results:
        logger.info(f"Processing task result - Manager: {manager_name}, Type: {task_type}, Wynik: {wynik}, Count: {count}")
        manager_id = name_to_id_map.get(manager_name)
        logger.info(f"Found manager ID: {manager_id}")
        if manager_id and task_type in data[manager_id]:
            data[manager_id][task_type] = count
            data[manager_id]['TTL'] += count
            logger.info(f"Updated data for manager {manager_id}: {task_type}={count}")
        else:
            logger.warning(f"Could not process task result - Manager ID not found or invalid task type: {manager_name} -> {manager_id}, {task_type}")
    
    for manager_id, count in offer_results:
        if manager_id in data: 
            data[manager_id]['OFW'] = count
            logger.info(f"Updated offers for manager {manager_id}: {count}")
    
    for manager_id, count, amount in order_results:
        if manager_id in data:
            data[manager_id]['ZAM'] = count
            data[manager_id]['PRC'] = float(amount) if amount is not None else 0.0
            logger.info(f"Updated orders for manager {manager_id}: count={count}, amount={amount}")
    
    for manager_name, status, count in client_results:
        manager_id = name_to_id_map.get(manager_name)
        if manager_id and status in data[manager_id]: 
            data[manager_id][status] = count
            logger.info(f"Updated client status for manager {manager_id}: {status}={count}")
    
    current_dt = datetime.now()
    report_title_date = current_dt.strftime('%d.%m.%Y') if report_type == 'daily' else current_dt.strftime('%m.%Y')
    report_title = f"RAPORT {report_title_date}"
    
    text = "```\n" + f"{report_title}\n"
    aliases = [mgr_data['alias'].ljust(7) for mgr_data in data.values()] # ljust for alignment
    header_line = "KPI | " + " | ".join(aliases) + "\n"
    separator_line = "═" * (len(header_line) -1) + "\n" # -1 for newline char
    light_separator_line = "─" * (len(header_line) -1) + "\n"

    text += separator_line + header_line + light_separator_line

    text += "zadania\n"
    task_order = ['WDM', 'PRZ', 'SPT', 'MAT', 'ZKL', 'TPY', 'MSP', 'NOW', 'WRK', 'OPI']
    has_any_tasks_overall = False
    for task_type in task_order:
        values = [data[mgr_id][task_type] for mgr_id in data]
        if any(v != 0 for v in values):
            has_any_tasks_overall = True
            line_values = " | ".join([f"{int(data[mgr_id][task_type]):7d}" for mgr_id in data])
            text += f"{task_type.ljust(3)} | {line_values}\n"
    if has_any_tasks_overall:
        text += light_separator_line
        ttl_values = " | ".join([f"{int(data[mgr_id]['TTL']):7d}" for mgr_id in data])
        text += f"TTL | {ttl_values}\n"
    
    text += light_separator_line + "klienci\n"
    status_order = ['NWI', 'WTR', 'PSK']
    for status in status_order:
        values = [data[mgr_id][status] for mgr_id in data]
        if any(v != 0 for v in values):
            line_values = " | ".join([f"{int(data[mgr_id][status]):7d}" for mgr_id in data])
            text += f"{status.ljust(3)} | {line_values}\n"
            
    text += light_separator_line + "zamówienia\n"
    order_kpis = ['OFW', 'ZAM', 'PRC']
    for kpi in order_kpis:
        values = [data[mgr_id][kpi] for mgr_id in data]
        if any(v != 0 for v in values):
            if kpi == 'PRC':
                line_values = " | ".join([f"{data[mgr_id][kpi]:7.0f}" for mgr_id in data])
            else:
                line_values = " | ".join([f"{int(data[mgr_id][kpi]):7d}" for mgr_id in data])
            text += f"{kpi.ljust(3)} | {line_values}\n"
            
    text += separator_line + "```"
    
    logger.info(f"Prepared report text:\n{text}")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        logger.info(f"Successfully sent {report_type} KPI report to Telegram chat ID {CHAT_ID}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send KPI report to Telegram: {e}")
        if e.response is not None:
            logger.error(f"Telegram API response: {e.response.text}")


def get_date_range(report_type: str) -> tuple[str, str]:
    today = date.today()
    if report_type == 'daily':
        start_date_obj = datetime(today.year, today.month, today.day)
        end_date_obj = start_date_obj + timedelta(days=1)
    else:  # monthly
        # Report for the current month
        start_date_obj = today.replace(day=1)
        if today.month == 12:
            end_date_obj = datetime(today.year + 1, 1, 1)
        else:
            end_date_obj = datetime(today.year, today.month + 1, 1)
        
    start_date_str = start_date_obj.strftime('%Y-%m-%d %H:%M:%S')
    end_date_str = end_date_obj.strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Generated date range for {report_type} report: {start_date_str} to {end_date_str}")
    return start_date_str, end_date_str


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting KPI Telegram report script.")
    
    try:
        _check_env_vars() # Check environment variables and manager config

        # Send daily report
        logger.info("Generating daily KPI report.")
        start_daily, end_daily = get_date_range('daily')
        tasks_daily = count_tasks_by_type(start_daily, end_daily)
        offers_daily = count_offers(start_daily, end_daily)
        orders_daily = count_orders(start_daily, end_daily)
        clients_daily = count_client_statuses(start_daily, end_daily)
        send_to_telegram(tasks_daily, offers_daily, orders_daily, clients_daily, 'daily')
        
        # Send monthly report always
        logger.info("Generating monthly KPI report.")
        start_monthly, end_monthly = get_date_range('monthly')
        tasks_monthly = count_tasks_by_type(start_monthly, end_monthly)
        offers_monthly = count_offers(start_monthly, end_monthly)
        orders_monthly = count_orders(start_monthly, end_monthly)
        clients_monthly = count_client_statuses(start_monthly, end_monthly)
        send_to_telegram(tasks_monthly, offers_monthly, orders_monthly, clients_monthly, 'monthly')
            
        logger.info("KPI Telegram report script finished successfully.")

    except ValueError as e: # Catch config errors from _check_env_vars
        logger.critical(f"Configuration error: {e}. KPI script cannot proceed.")
    except Exception as e: # Catch any other unexpected errors
        logger.critical(f"An unexpected error occurred in the KPI script: {e}")
        # logger.exception("Details of unexpected error in KPI script:") # For more detailed debugging
