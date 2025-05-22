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

# Prepare manager lists for SQL queries
PLANFIX_USER_NAMES = tuple(m['planfix_user_name'] for m in MANAGERS_KPI) if MANAGERS_KPI else tuple()
PLANFIX_USER_IDS = tuple(m['planfix_user_id'] for m in MANAGERS_KPI) if MANAGERS_KPI else tuple()

def _check_env_vars():
    """Checks for required environment variables and logs errors if any are missing."""
    required_env_vars = {
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_TOKEN': planfix_utils.PLANFIX_TOKEN,
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
    
    # Словарь соответствия полных названий и сокращений
    task_type_mapping = {
        'Nawiązać pierwszy kontakt': 'WDM',
        'Przeprowadzić pierwszą rozmowę telefoniczną': 'PRZ',
        'Zadzwonić do klienta': 'ZKL',
        'Przeprowadzić spotkanie': 'SPT',
        'Wysłać materiały': 'MAT',
        'Odpowiedzieć na pytanie techniczne': 'TPY',
        'Zapisać na media społecznościowe': 'MSP',
        'Opowiedzieć o nowościach': 'NOW',
        'Zebrać opinie': 'OPI',
        'Przywrócić klienta': 'WRK'
    }
    
    # Debug query to check task data format
    debug_query = """
        SELECT 
            owner_name,
            title,
            nastepne_zadanie,
            data_zakonczenia_zadania,
            TO_CHAR(data_zakonczenia_zadania, 'YYYY-MM-DD HH24:MI:SS') as formatted_date,
            is_deleted,
            template_id
        FROM planfix_tasks
        WHERE owner_name IN %s
        AND data_zakonczenia_zadania IS NOT NULL
        AND data_zakonczenia_zadania >= %s::timestamp
        AND data_zakonczenia_zadania < %s::timestamp
        AND is_deleted = false
        ORDER BY data_zakonczenia_zadania DESC
        LIMIT 20;
    """
    debug_results = _execute_kpi_query(debug_query, (PLANFIX_USER_NAMES, start_date_str, end_date_str), "debug tasks")
    logger.info("\nDebug - Sample task data:")
    for row in debug_results:
        logger.info(f"Manager: {row[0]}, Title: {row[1]}, Next Task: {row[2]}, Date: {row[3]}, Formatted: {row[4]}, Deleted: {row[5]}, Template: {row[6]}")
    
    # Debug query to check all tasks for the current month
    debug_all_tasks_query = """
        SELECT 
            owner_name,
            nastepne_zadanie,
            data_zakonczenia_zadania,
            TO_CHAR(data_zakonczenia_zadania, 'YYYY-MM-DD HH24:MI:SS') as formatted_date,
            is_deleted,
            template_id
        FROM planfix_tasks
        WHERE data_zakonczenia_zadania IS NOT NULL
        AND data_zakonczenia_zadania >= %s::timestamp
        AND data_zakonczenia_zadania < %s::timestamp
        ORDER BY data_zakonczenia_zadania DESC;
    """
    debug_all_results = _execute_kpi_query(debug_all_tasks_query, (start_date_str, end_date_str), "debug all tasks")
    logger.info("\nDebug - All tasks in date range:")
    for row in debug_all_results:
        logger.info(f"Manager: {row[0]}, Next Task: {row[1]}, Date: {row[2]}, Formatted: {row[3]}, Deleted: {row[4]}, Template: {row[5]}")
    
    # Debug query to count all tasks by type and manager (all time, including unfinished)
    debug_total_tasks_query = """
        SELECT 
            owner_name,
            nastepne_zadanie,
            COUNT(*) as task_count,
            COUNT(CASE WHEN data_zakonczenia_zadania IS NOT NULL THEN 1 END) as completed_count,
            COUNT(CASE WHEN data_zakonczenia_zadania IS NULL THEN 1 END) as unfinished_count
        FROM planfix_tasks
        WHERE is_deleted = false
        AND nastepne_zadanie IN (
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
        GROUP BY owner_name, nastepne_zadanie
        ORDER BY owner_name, nastepne_zadanie;
    """
    debug_total_results = _execute_kpi_query(debug_total_tasks_query, (), "debug total tasks")
    logger.info("\nDebug - Total tasks by type and manager (all time, including unfinished):")
    for row in debug_total_results:
        logger.info(f"Manager: {row[0]}, Task Type: {row[1]}, Total: {row[2]}, Completed: {row[3]}, Unfinished: {row[4]}")
    
    # Get tasks by type for each manager
    tasks_by_type_query = """
        WITH task_counts AS (
            SELECT 
                t.manager,
                CASE 
                    WHEN t.title LIKE '%Wysłać dokumenty%' THEN 'WDM'
                    WHEN t.title LIKE '%Przeprowadzić pierwszą rozmowę telefoniczną%' THEN 'PRZ'
                    WHEN t.title LIKE '%Zebrać kluczowe informacje%' THEN 'ZKL'
                    WHEN t.title LIKE '%Przeprowadzić spotkanie%' THEN 'SPT'
                    WHEN t.title LIKE '%Wysłać materiały%' THEN 'MAT'
                    WHEN t.title LIKE '%Przeprowadzić rozmowę telefoniczną%' THEN 'TPY'
                    WHEN t.title LIKE '%Przeprowadzić spotkanie%' THEN 'MSP'
                    WHEN t.title LIKE '%Opowiedzieć o nowościach%' THEN 'NOW'
                    WHEN t.title LIKE '%Odpowiedzieć na pytanie techniczne%' THEN 'OPI'
                    WHEN t.title LIKE '%Zebrać opinie%' THEN 'WRK'
                    ELSE 'OTHER'
                END as task_type,
                COUNT(*) as count
            FROM planfix_tasks t
            WHERE t.date BETWEEN %s AND %s
            AND t.manager = ANY(%s)
            AND t.deleted = false
            GROUP BY t.manager, task_type
        ),
        combined_counts AS (
            SELECT 
                t.manager,
                'PRZ' as task_type,
                COUNT(*) as count
            FROM planfix_tasks t
            WHERE t.date BETWEEN %s AND %s
            AND t.manager = ANY(%s)
            AND t.deleted = false
            AND t.title LIKE '%Przeprowadzić pierwszą rozmowę telefoniczną%'
            GROUP BY t.manager
        )
        SELECT 
            tc.manager,
            tc.task_type,
            tc.count,
            CASE 
                WHEN tc.task_type = 'PRZ' AND EXISTS (
                    SELECT 1 FROM planfix_tasks t 
                    WHERE t.manager = tc.manager 
                    AND t.title LIKE '%Przeprowadzić pierwszą rozmowę telefoniczną%'
                    AND t.wynik = 'Klient jest zainteresowany'
                    AND t.date BETWEEN %s AND %s
                ) THEN 1
                ELSE 0
            END as kzi_count
        FROM task_counts tc
        UNION ALL
        SELECT 
            cc.manager,
            cc.task_type,
            cc.count,
            0 as kzi_count
        FROM combined_counts cc
        ORDER BY 
            CASE tc.manager
                WHEN 'Kozik Andrzej' THEN 1
                WHEN 'Stukalo Nazarii' THEN 2
                ELSE 3
            END,
            CASE tc.task_type
                WHEN 'WDM' THEN 1
                WHEN 'PRZ' THEN 2
                WHEN 'KZI' THEN 3
                WHEN 'ZKL' THEN 4
                WHEN 'SPT' THEN 5
                WHEN 'MAT' THEN 6
                WHEN 'TPY' THEN 7
                WHEN 'MSP' THEN 8
                WHEN 'NOW' THEN 9
                WHEN 'OPI' THEN 10
                WHEN 'WRK' THEN 11
                ELSE 12
            END;
    """
    results = _execute_kpi_query(tasks_by_type_query, (start_date_str, end_date_str, PLANFIX_USER_NAMES, start_date_str, end_date_str, PLANFIX_USER_NAMES, start_date_str, end_date_str, PLANFIX_USER_NAMES), "tasks by type")
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


def send_to_telegram():
    """Send KPI report to Telegram."""
    try:
        # Initialize data structure for each manager
        data = {
            'Kozik Andrzej': {
                'WDM': 0, 'PRZ': 0, 'KZI': 0, 'ZKL': 0, 'SPT': 0, 
                'MAT': 0, 'TPY': 0, 'MSP': 0, 'NOW': 0, 'OPI': 0, 'WRK': 0
            },
            'Stukalo Nazarii': {
                'WDM': 0, 'PRZ': 0, 'KZI': 0, 'ZKL': 0, 'SPT': 0, 
                'MAT': 0, 'TPY': 0, 'MSP': 0, 'NOW': 0, 'OPI': 0, 'WRK': 0
            }
        }
        
        # Get task results
        task_results = get_kpi_data()
        if not task_results:
            logger.error("No task results received")
            return
            
        # Process task results
        for row in task_results:
            manager = row[0]
            task_type = row[1]
            count = row[2]
            kzi_count = row[3]
            
            if manager in data and task_type in data[manager]:
                data[manager][task_type] = count
                if task_type == 'PRZ' and kzi_count > 0:
                    data[manager]['KZI'] = kzi_count
        
        # Format message
        message = "📊 *KPI Report*\n\n"
        
        # Define task order
        task_order = ['WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK']
        
        # Add data for each manager
        for manager, manager_data in data.items():
            message += f"*{manager}*\n"
            for task_type in task_order:
                count = manager_data[task_type]
                message += f"{task_type}: {count}\n"
            message += "\n"
        
        # Send to Telegram
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
            logger.error("Missing Telegram configuration")
            return
            
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
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
