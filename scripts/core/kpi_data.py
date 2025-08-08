"""
Модуль для получения и обработки KPI-данных (планы, факты, коэффициенты)
"""
import os
import logging
from decimal import Decimal
from typing import Dict, Any
from config import MANAGERS_KPI
import planfix_utils
import psycopg2
from .kpi_utils import math_round

logger = logging.getLogger(__name__)

PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# Список KPI, для которых применяется ограничение min(факт, план)
CAPPED_KPI = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'KNT', 'TTL', 'OFW', 'ZAM'
]

KPI_INDICATORS = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'KNT', 'TTL', 'OFW', 'ZAM', 'PRC'
]

def _execute_query(query: str, params: tuple, description: str) -> list:
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
    query = """
        SELECT 
            month,
            year,
            premia_kpi,
            nwi, wtr, psk, wdm, prz, zkl, spt, msp, knt, ofw, ttl
        FROM kpi_metrics
        WHERE month = %s AND year = %s
    """
    results = _execute_query(query, (f"{current_month:02d}", current_year), "KPI metrics")
    if not results:
        logger.warning(f"No KPI metrics found for {current_month}/{current_year}")
        return {}
    row = results[0]
    metrics = {}
    column_mapping = {
        'NWI': 3, 'WTR': 4, 'PSK': 5, 'WDM': 6, 'PRZ': 7, 'ZKL': 8, 'SPT': 9, 'MSP': 10, 'KNT': 11, 'OFW': 12, 'TTL': 13
    }
    for indicator, col_index in column_mapping.items():
        metrics[indicator] = {'plan': row[col_index], 'weight': 0}
    active_kpis = sum(1 for metric in metrics.values() if metric['plan'] is not None)
    if active_kpis > 0:
        weight = 1.0 / active_kpis
        for metric in metrics.values():
            if metric['plan'] is not None:
                metric['weight'] = weight
    metrics['premia'] = row[2]
    return metrics

def _parse_netto_pln(value):
    if value is None:
        return 0.0
    try:
        import re
        cleaned = re.sub(r'[^0-9,.-]', '', str(value)).replace(',', '.').replace(' ', '')
        return float(cleaned)
    except Exception:
        return 0.0

def get_actual_kpi_values(start_date: str, end_date: str) -> dict:
    task_query = """
        WITH task_counts AS (
            SELECT
                owner_name AS manager,
                CASE 
                    WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Nawiązać pierwszy kontakt' THEN 'WDM'
                    WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną' THEN 'PRZ'
                    WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Zadzwonić do klienta' THEN 'ZKL'
                    WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Przeprowadzić spotkanie' THEN 'SPT'
                    WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Zapisać na media społecznościowe' THEN 'MSP'
                    WHEN TRIM(SPLIT_PART(title, ' /', 1)) = 'Tworzyć kontent' THEN 'KNT'
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
                    'Przeprowadzić spotkanie',
                    'Wysłać materiały',
                    'Zadzwonić do klienta',
                    'Odpowiedzieć na pytanie techniczne',
                    'Zapisać na media społecznościowe',
                    'Opowiedzieć o nowościach',
                    'Przywrócić klienta',
                    'Zebrać opinie',
                    'Tworzyć kontent'
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
    filtered_offer_results = []
    for row in offer_results:
        if len(row) > 3:
            netto = _parse_netto_pln(row[3])
            if netto != 0:
                filtered_offer_results.append(row)
        else:
            filtered_offer_results.append(row)
    offer_results = filtered_offer_results
    actual_values = {}
    for manager in PLANFIX_USER_NAMES:
        actual_values[manager] = {
            'NWI': 0, 'WTR': 0, 'PSK': 0, 'WDM': 0, 'PRZ': 0,
            'ZKL': 0, 'SPT': 0, 'MSP': 0, 'KNT': 0, 'OFW': 0, 'TTL': 0
        }
    for row in task_results:
        manager, task_type, count = row
        if task_type in actual_values[manager]:
            actual_values[manager][task_type] = count
    for row in client_results:
        manager, status, count = row
        if status in actual_values[manager]:
            actual_values[manager][status] = count
    for row in offer_results:
        manager_id = row[0]
        count = row[2]
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
        
        # Рассчитываем коэффициенты для всех показателей, включая TTL
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
                    # Преобразуем в float для математического округления
                    coefficient_value = float((used_value / plan) * weight)
                    coefficient = math_round(coefficient_value, 2)
                else:
                    coefficient = Decimal('0')
                manager_coefficients[indicator] = coefficient
                sum_coefficient += Decimal(str(coefficient))
        
        # Добавляем SUM коэффициент
        manager_coefficients['SUM'] = Decimal(str(math_round(sum_coefficient, 2)))
        
        # Рассчитываем PRK
        if 'premia' in metrics and metrics['premia'] is not None:
            premia = Decimal(str(metrics['premia']))
            manager_coefficients['PRK'] = Decimal(str(math_round(premia * sum_coefficient, 2)))
        else:
            manager_coefficients['PRK'] = Decimal('0')
        
        coefficients[manager] = manager_coefficients
    return coefficients

def get_additional_premia(start_date: str, end_date: str) -> dict:
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
        manager = next((m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_id'] == manager_id), None)
        if manager:
            additional_premia[manager] = {'PRW': prw}
    logger.info(f"PRW calculation results: {additional_premia}")
    return additional_premia 