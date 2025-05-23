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
    
    # Основной KPI-запрос
    query = f"""
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
            GROUP BY
                owner_name, 
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
                END
        )
        SELECT 
            manager,
            task_type,
            task_count
        FROM task_counts
        WHERE task_type IS NOT NULL
        ORDER BY manager, 
            CASE task_type
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
    """Send KPI report to Telegram."""
    try:
        # Initialize data structure for each manager
        data = {
            'Kozik Andrzej': {
                'WDM': 0, 'PRZ': 0, 'KZI': 0, 'ZKL': 0, 'SPT': 0, 
                'MAT': 0, 'TPY': 0, 'MSP': 0, 'NOW': 0, 'OPI': 0, 'WRK': 0,
                'NWI': 0, 'WTR': 0, 'PSK': 0,
                'OFW': 0, 'ZAM': 0, 'PRC': 0
            },
            'Stukalo Nazarii': {
                'WDM': 0, 'PRZ': 0, 'KZI': 0, 'ZKL': 0, 'SPT': 0, 
                'MAT': 0, 'TPY': 0, 'MSP': 0, 'NOW': 0, 'OPI': 0, 'WRK': 0,
                'NWI': 0, 'WTR': 0, 'PSK': 0,
                'OFW': 0, 'ZAM': 0, 'PRC': 0
            }
        }
        
        # Process task results
        for row in task_results:
            manager = row[0]
            task_type = row[1]
            count = int(row[2]) if row[2] is not None else 0
            
            if manager in data and task_type in data[manager]:
                data[manager][task_type] = count

        # Process client results
        for row in client_results:
            manager = row[0]
            status = row[1]
            count = int(row[2]) if row[2] is not None else 0
            
            if manager in data and status in data[manager]:
                data[manager][status] = count

        # Process order results
        for row in order_results:
            manager_id = row[0]
            count = int(row[1]) if row[1] is not None else 0
            amount = float(row[2]) if row[2] is not None else 0.0
            
            # Find manager name by ID
            manager = next((m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_id'] == manager_id), None)
            if manager in data:
                data[manager]['OFW'] = count
                data[manager]['ZAM'] = count
                data[manager]['PRC'] = amount

        # Format message
        today = date.today()
        message = "```\n"  # Start monospace block
        
        # Daily report
        message += f"RAPORT {today.strftime('%d.%m.%Y')}\n"
        message += "═══════════════════════\n"
        message += "KPI | Kozik   | Stukalo\n"
        message += "───────────────────────\n"
        
        # Add tasks section
        message += "zadania\n"
        task_order = ['WDM', 'PRZ', 'KZI', 'ZKL', 'MAT', 'NOW', 'OPI']
        for task_type in task_order:
            kozik_count = data['Kozik Andrzej'][task_type]
            stukalo_count = data['Stukalo Nazarii'][task_type]
            message += f"{task_type:3} | {kozik_count:6d} | {stukalo_count:6d}\n"
        
        # Add task totals
        kozik_total = sum(data['Kozik Andrzej'][t] for t in task_order)
        stukalo_total = sum(data['Stukalo Nazarii'][t] for t in task_order)
        message += "───────────────────────\n"
        message += f"TTL | {kozik_total:6d} | {stukalo_total:6d}\n"
        message += "───────────────────────\n"
        
        # Add clients section
        message += "klienci\n"
        client_order = ['NWI', 'WTR', 'PSK']
        for status in client_order:
            kozik_count = data['Kozik Andrzej'][status]
            stukalo_count = data['Stukalo Nazarii'][status]
            message += f"{status:3} | {kozik_count:6d} | {stukalo_count:6d}\n"
        message += "───────────────────────\n"
        
        # Add orders section
        message += "zamówienia\n"
        order_order = ['OFW', 'ZAM', 'PRC']
        for order_type in order_order:
            kozik_count = data['Kozik Andrzej'][order_type]
            stukalo_count = data['Stukalo Nazarii'][order_type]
            if order_type == 'PRC':
                message += f"{order_type:3} | {kozik_count:6.2f} | {stukalo_count:6.2f}\n"
            else:
                message += f"{order_type:3} | {kozik_count:6d} | {stukalo_count:6d}\n"
        message += "═══════════════════════\n"
        
        # Monthly report
        message += f"\nRAPORT {today.strftime('%m.%Y')}\n"
        message += "═══════════════════════\n"
        message += "KPI | Kozik   | Stukalo\n"
        message += "───────────────────────\n"
        
        # Add tasks section
        message += "zadania\n"
        for task_type in task_order:
            kozik_count = data['Kozik Andrzej'][task_type]
            stukalo_count = data['Stukalo Nazarii'][task_type]
            message += f"{task_type:3} | {kozik_count:6d} | {stukalo_count:6d}\n"
        
        # Add task totals
        message += "───────────────────────\n"
        message += f"TTL | {kozik_total:6d} | {stukalo_total:6d}\n"
        message += "───────────────────────\n"
        
        # Add clients section
        message += "klienci\n"
        for status in client_order:
            kozik_count = data['Kozik Andrzej'][status]
            stukalo_count = data['Stukalo Nazarii'][status]
            message += f"{status:3} | {kozik_count:6d} | {stukalo_count:6d}\n"
        message += "───────────────────────\n"
        
        # Add orders section
        message += "zamówienia\n"
        for order_type in order_order:
            kozik_count = data['Kozik Andrzej'][order_type]
            stukalo_count = data['Stukalo Nazarii'][order_type]
            if order_type == 'PRC':
                message += f"{order_type:3} | {kozik_count:6.2f} | {stukalo_count:6.2f}\n"
            else:
                message += f"{order_type:3} | {kozik_count:6d} | {stukalo_count:6d}\n"
        message += "═══════════════════════\n"
        message += "```"  # End monospace block
        
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
    logger.info(f"Generated date range for {report_type} report:")
    logger.info(f"Start date: {start_date_str}")
    logger.info(f"End date: {end_date_str}")
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
