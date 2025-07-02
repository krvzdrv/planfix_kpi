import os
import sys
import logging
from datetime import datetime, date, timedelta
import psycopg2
from decimal import Decimal
import requests
from dotenv import load_dotenv
from config import MANAGERS_KPI
import asyncio
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# Load environment variables from .env file
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

# --- Database Settings ---
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# --- Telegram Settings ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Get a logger instance for this module
logger = logging.getLogger(__name__)

# Список всех возможных показателей KPI
KPI_INDICATORS = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 
    'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC'
]

# Список KPI, для которых применяется ограничение min(факт, план)
CAPPED_KPI = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM'
]

# Импортируем core-модули (новая архитектура)
try:
    from core.kpi_data import get_kpi_metrics, get_actual_kpi_values, calculate_kpi_coefficients
    from core.kpi_report import format_premia_report
except ImportError:
    # Для совместимости, если core ещё не реализован полностью
    pass

def _check_env_vars():
    """Checks for required environment variables and logs errors if any are missing."""
    required_env_vars = {
        'SUPABASE_HOST': PG_HOST,
        'SUPABASE_DB': PG_DB,
        'SUPABASE_USER': PG_USER,
        'SUPABASE_PASSWORD': PG_PASSWORD,
        'SUPABASE_PORT': PG_PORT,
        'TELEGRAM_BOT_TOKEN': TELEGRAM_TOKEN
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
            nwi, wtr, psk, wdm, prz, zkl, spt, ofw, ttl
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
    metrics = {}
    # Map existing columns to KPI indicators
    column_mapping = {
        'NWI': 3,  # nwi
        'WTR': 4,  # wtr
        'PSK': 5,  # psk
        'WDM': 6,  # wdm
        'PRZ': 7,  # prz
        'ZKL': 8,  # zkl
        'SPT': 9,  # spt
        'OFW': 10, # ofw
        'TTL': 11  # ttl
    }
    
    for indicator, col_index in column_mapping.items():
        metrics[indicator] = {'plan': row[col_index], 'weight': 0}
    
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

def _parse_netto_pln(value):
    """Преобразует текстовое значение wartosc_netto_pln в float. Возвращает 0.0 при ошибке."""
    if value is None:
        return 0.0
    try:
        import re
        cleaned = re.sub(r'[^0-9,.-]', '', str(value)).replace(',', '.').replace(' ', '')
        return float(cleaned)
    except Exception:
        return 0.0

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
                    'Przeprowadzić spotkanie'
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
            SELECT * FROM ttl_counts
        ) combined_results
        WHERE task_type IS NOT NULL;
    """
    
    # Get client status counts
    client_query = """
        WITH client_counts AS (
            SELECT
                menedzer AS manager,
                'NWI' AS status,
                COUNT(*) AS client_count
            FROM planfix_clients
            WHERE data_dodania_do_nowi IS NOT NULL
                AND data_dodania_do_nowi != ''
                AND COALESCE(
                    TO_TIMESTAMP(data_dodania_do_nowi, 'DD-MM-YYYY HH24:MI'),
                    TO_TIMESTAMP(data_dodania_do_nowi, 'DD-MM-YYYY')
                ) >= %s::timestamp
                AND COALESCE(
                    TO_TIMESTAMP(data_dodania_do_nowi, 'DD-MM-YYYY HH24:MI'),
                    TO_TIMESTAMP(data_dodania_do_nowi, 'DD-MM-YYYY')
                ) < %s::timestamp
                AND menedzer IN %s
                AND is_deleted = false
            GROUP BY menedzer
            UNION ALL
            SELECT
                menedzer AS manager,
                'WTR' AS status,
                COUNT(*) AS client_count
            FROM planfix_clients
            WHERE data_dodania_do_w_trakcie IS NOT NULL
                AND data_dodania_do_w_trakcie != ''
                AND COALESCE(
                    TO_TIMESTAMP(data_dodania_do_w_trakcie, 'DD-MM-YYYY HH24:MI'),
                    TO_TIMESTAMP(data_dodania_do_w_trakcie, 'DD-MM-YYYY')
                ) >= %s::timestamp
                AND COALESCE(
                    TO_TIMESTAMP(data_dodania_do_w_trakcie, 'DD-MM-YYYY HH24:MI'),
                    TO_TIMESTAMP(data_dodania_do_w_trakcie, 'DD-MM-YYYY')
                ) < %s::timestamp
                AND menedzer IN %s
                AND is_deleted = false
            GROUP BY menedzer
            UNION ALL
            SELECT
                menedzer AS manager,
                'PSK' AS status,
                COUNT(*) AS client_count
            FROM planfix_clients
            WHERE data_dodania_do_perspektywiczni IS NOT NULL
                AND data_dodania_do_perspektywiczni != ''
                AND COALESCE(
                    TO_TIMESTAMP(data_dodania_do_perspektywiczni, 'DD-MM-YYYY HH24:MI'),
                    TO_TIMESTAMP(data_dodania_do_perspektywiczni, 'DD-MM-YYYY')
                ) >= %s::timestamp
                AND COALESCE(
                    TO_TIMESTAMP(data_dodania_do_perspektywiczni, 'DD-MM-YYYY HH24:MI'),
                    TO_TIMESTAMP(data_dodania_do_perspektywiczni, 'DD-MM-YYYY')
                ) < %s::timestamp
                AND menedzer IN %s
                AND is_deleted = false
            GROUP BY menedzer
        )
        SELECT 
            manager,
            status,
            client_count
        FROM client_counts
        WHERE status IS NOT NULL;
    """
    
    # Get offer counts (OFW)
    offer_query = """
        SELECT
            menedzher AS manager,
            'OFW' as metric,
            COUNT(*) as count
        FROM planfix_orders
        WHERE
            data_wyslania_oferty IS NOT NULL
            AND data_wyslania_oferty != ''
            AND TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
            AND TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') < %s::timestamp
            AND menedzher IN %s
            AND is_deleted = false
            AND wartosc_netto_pln IS NOT NULL
            AND TRIM(wartosc_netto_pln) != ''
            AND wartosc_netto_pln != '0,00'
            AND COALESCE(NULLIF(CAST(REPLACE(REPLACE(REGEXP_REPLACE(wartosc_netto_pln, '[^0-9,.-]', '', 'g'), ',', '.'), ' ', '') AS DECIMAL), 0), 0) != 0
        GROUP BY menedzher;
    """
    
    PLANFIX_USER_NAMES = tuple(m['planfix_user_name'] for m in MANAGERS_KPI)
    PLANFIX_USER_IDS = tuple(m['planfix_user_id'] for m in MANAGERS_KPI)
    
    task_results = _execute_query(task_query, (
        start_date, end_date, PLANFIX_USER_NAMES,
        start_date, end_date, PLANFIX_USER_NAMES
    ), "Task counts")
    
    client_results = _execute_query(client_query, (
        start_date, end_date, PLANFIX_USER_NAMES,
        start_date, end_date, PLANFIX_USER_NAMES,
        start_date, end_date, PLANFIX_USER_NAMES
    ), "Client status counts")

    offer_results = _execute_query(offer_query, (
        start_date, end_date, PLANFIX_USER_IDS
    ), "Offer counts")
    
    # Фильтрация на Python-уровне: исключаем заказы с нулевой суммой
    filtered_offer_results = []
    for row in offer_results:
        if len(row) >= 3:
            filtered_offer_results.append(row)
        else:
            filtered_offer_results.append(row)  # если суммы нет, оставляем как есть
    offer_results = filtered_offer_results
    
    # Combine results into a dictionary
    actual_values = {}
    for manager in PLANFIX_USER_NAMES:
        actual_values[manager] = {
            'NWI': 0, 'WTR': 0, 'PSK': 0, 'WDM': 0, 'PRZ': 0,
            'ZKL': 0, 'SPT': 0, 'OFW': 0, 'TTL': 0
        }
    
    # Process task results
    for row in task_results:
        manager, task_type, count = row
        if task_type in actual_values[manager]:
            actual_values[manager][task_type] = count
    
    # Process client results
    for row in client_results:
        manager, status, count = row
        if status in actual_values[manager]:
            actual_values[manager][status] = count

    # Process offer results
    for row in offer_results:
        manager_id = row[0]
        count = row[2]
        # Find manager name by ID
        manager = next((m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_id'] == manager_id), None)
        if manager in actual_values:
            actual_values[manager]['OFW'] = count
    
    return actual_values

def calculate_kpi_coefficients(metrics: dict, actual_values: dict) -> dict:
    """Calculate KPI coefficients for each manager."""
    coefficients = {}
    for manager, values in actual_values.items():
        manager_coefficients = {}
        sum_coefficient = Decimal('0')
        # Calculate coefficient for each KPI indicator
        for indicator in KPI_INDICATORS:
            if indicator in metrics and metrics[indicator]['plan'] is not None:
                actual = Decimal(str(values.get(indicator, 0)))
                plan = Decimal(str(metrics[indicator]['plan']))
                weight = Decimal(str(metrics[indicator]['weight']))
                if plan > 0:
                    if indicator in CAPPED_KPI:
                        used_value = min(actual, plan)
                    else:
                        used_value = actual
                    coefficient = round((used_value / plan) * weight, 2)
                else:
                    coefficient = Decimal('0')
                manager_coefficients[indicator] = coefficient
                sum_coefficient += coefficient
        # Add SUM coefficient
        manager_coefficients['SUM'] = round(sum_coefficient, 2)
        # Calculate PRK (FND * SUM)
        if 'premia' in metrics and metrics['premia'] is not None:
            premia = Decimal(str(metrics['premia']))
            manager_coefficients['PRK'] = round(premia * sum_coefficient, 2)
        else:
            manager_coefficients['PRK'] = Decimal('0')
        coefficients[manager] = manager_coefficients
    return coefficients

def get_additional_premia(start_date: str, end_date: str) -> dict:
    """Get additional premia values for the period (PRW: сумма laczna_prowizja_pln по менеджерам)."""
    query = """
        SELECT 
            menedzher,
            COALESCE(SUM(CAST(REPLACE(REPLACE(laczna_prowizja_pln, ' ', ''), ',', '.') AS DECIMAL)), 0) as prw
        FROM planfix_orders
        WHERE data_realizacji IS NOT NULL AND data_realizacji != ''
            AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
            AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') < %s::timestamp
            AND menedzher IN %s
            AND is_deleted = false
        GROUP BY menedzher;
    """
    PLANFIX_USER_IDS = tuple(m['planfix_user_id'] for m in MANAGERS_KPI)
    results = _execute_query(query, (start_date, end_date, PLANFIX_USER_IDS), "Additional premia (PRW)")
    additional_premia = {}
    for row in results:
        manager_id = row[0]
        prw = row[1]
        # Find manager name by ID
        manager = next((m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_id'] == manager_id), None)
        if manager:
            additional_premia[manager] = {'PRW': prw}
    logger.info(f"PRW calculation results: {additional_premia}")
    return additional_premia

def format_premia_report(coefficients: dict, current_month: int, current_year: int, additional_premia: dict) -> str:
    """Format the premia report for Telegram (строгое оформление по ТЗ)."""
    kpi_order = [
        'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT',
        'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC'
    ]
    managers = ['Kozik Andrzej', 'Stukalo Nazarii']
    top_line = '══════════════════════'
    mid_line = '──────────────────────'
    message = ''
    message += f'PREMIA_{current_month:02d}.{current_year}\n'
    message += f'{top_line}\n'
    message += 'KPI | Kozik  | Stukalo\n'
    message += f'{mid_line}\n'
    for kpi in kpi_order:
        v1 = coefficients[managers[0]].get(kpi, 0)
        v2 = coefficients[managers[1]].get(kpi, 0)
        if v1 == 0 and v2 == 0:
            continue
        message += f'{kpi:<3} |{v1:7.2f} |{v2:7.2f}\n'
    message += f'{mid_line}\n'
    sum1 = coefficients[managers[0]].get('SUM', 0)
    sum2 = coefficients[managers[1]].get('SUM', 0)
    message += f'SUM |{sum1:7.2f} |{sum2:7.2f}\n'
    fnd1 = int(coefficients[managers[0]].get('PRK', 0) / sum1) if sum1 else 0
    fnd2 = int(coefficients[managers[1]].get('PRK', 0) / sum2) if sum2 else 0
    message += f'FND |{fnd1:7d} |{fnd2:7d}\n'
    message += f'{mid_line}\n'
    prk1 = int(coefficients[managers[0]].get('PRK', 0))
    prk2 = int(coefficients[managers[1]].get('PRK', 0))
    message += f'PRK |{prk1:7d} |{prk2:7d}\n'
    prw1 = int(additional_premia.get(managers[0], {}).get('PRW', 0))
    prw2 = int(additional_premia.get(managers[1], {}).get('PRW', 0))
    message += f'PRW |{prw1:7d} |{prw2:7d}\n'
    tot1 = prk1 + prw1
    tot2 = prk2 + prw2
    message += f'TOT |{tot1:7d} |{tot2:7d}\n'
    message += f'{top_line}\n'
    return message

def generate_premia_report_for_month(target_month: int, target_year: int) -> str:
    """Generate premia report for a specific month."""
    try:
        # Get start and end dates for the target month
        start_date = f"{target_year}-{target_month:02d}-01"
        if target_month == 12:
            end_date = f"{target_year + 1}-01-01"
        else:
            end_date = f"{target_year}-{target_month + 1:02d}-01"
        
        # Get KPI metrics
        metrics = get_kpi_metrics(target_month, target_year)
        if not metrics:
            return f"❌ Нет данных KPI для {target_month:02d}.{target_year}"
        
        # Get actual KPI values
        actual_values = get_actual_kpi_values(start_date, end_date)
        
        # Calculate coefficients
        coefficients = calculate_kpi_coefficients(metrics, actual_values)
        
        # Get additional premia
        additional_premia = get_additional_premia(start_date, end_date)
        
        # Format report
        report = format_premia_report(coefficients, target_month, target_year, additional_premia)
        return report
        
    except Exception as e:
        logger.error(f"Error generating premia report for {target_month:02d}.{target_year}: {e}")
        return f"❌ Ошибка при генерации отчета за {target_month:02d}.{target_year}: {str(e)}"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_message = """
🤖 Бот отчетов по премии

Доступные команды:
/premia_current - Отчет по премии за текущий месяц
/premia_previous - Отчет по премии за предыдущий месяц
/help - Показать эту справку
    """
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_message = """
📋 Справка по командам:

/premia_current - Генерирует отчет по премии за текущий месяц на сегодняшний день

/premia_previous - Генерирует отчет по премии за предыдущий месяц

/help - Показать эту справку

Отчеты включают:
• KPI показатели (NWI, WTR, PSK, WDM, PRZ, ZKL, SPT, OFW, TTL)
• Коэффициенты выполнения
• Расчет премии (PRK, PRW, TOT)
    """
    await update.message.reply_text(help_message)

async def premia_current_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /premia_current command."""
    await update.message.reply_text("🔄 Генерирую отчет по премии за текущий месяц...")
    
    try:
        current_date = date.today()
        current_month = current_date.month
        current_year = current_date.year
        
        report = generate_premia_report_for_month(current_month, current_year)
        await update.message.reply_text(f'<pre>{report}</pre>', parse_mode='HTML')
        
    except Exception as e:
        error_message = f"❌ Ошибка при генерации отчета: {str(e)}"
        await update.message.reply_text(error_message)
        logger.error(f"Error in premia_current_command: {e}")

async def premia_previous_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /premia_previous command."""
    await update.message.reply_text("🔄 Генерирую отчет по премии за предыдущий месяц...")
    
    try:
        current_date = date.today()
        
        # Calculate previous month
        if current_date.month == 1:
            previous_month = 12
            previous_year = current_date.year - 1
        else:
            previous_month = current_date.month - 1
            previous_year = current_date.year
        
        report = generate_premia_report_for_month(previous_month, previous_year)
        await update.message.reply_text(f'<pre>{report}</pre>', parse_mode='HTML')
        
    except Exception as e:
        error_message = f"❌ Ошибка при генерации отчета: {str(e)}"
        await update.message.reply_text(error_message)
        logger.error(f"Error in premia_previous_command: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ Произошла ошибка при обработке команды. Попробуйте позже.")

def main():
    """Main function to run the Telegram bot."""
    try:
        _check_env_vars()
        
        # Create application
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("premia_current", premia_current_command))
        application.add_handler(CommandHandler("premia_previous", premia_previous_command))
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Start the bot
        logger.info("Starting Telegram bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Telegram bot for premia reports...")
    main() 