"""
Централизованный движок для KPI расчетов
Поддерживает разные периоды: день, неделя, месяц, квартал, год
"""
import os
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Tuple
from .config import MANAGERS_KPI
from utils import planfix_utils
import psycopg2
from .kpi_utils import math_round

logger = logging.getLogger(__name__)

# Database settings
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# KPI Configuration
KPI_INDICATORS = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 
    'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'KNT', 'TTL', 'OFW', 'ZAM', 'PRC'
]

# KPI с ограничением min(факт, план)
CAPPED_KPI = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 
    'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'KNT', 'TTL', 'OFW', 'ZAM'
]

# Периоды для расчетов
PERIOD_TYPES = {
    'daily': 'day',
    'weekly': 'week', 
    'monthly': 'month',
    'quarterly': 'quarter',
    'yearly': 'year',
    'custom': 'custom'
}

class KPIPeriod:
    """Класс для работы с периодами KPI"""
    
    def __init__(self, period_type: str, start_date: str = None, end_date: str = None):
        self.period_type = period_type
        self.start_date = start_date
        self.end_date = end_date
        
        if not start_date or not end_date:
            self._calculate_dates()
    
    def _calculate_dates(self):
        """Рассчитывает даты периода"""
        today = date.today()
        
        if self.period_type == 'daily':
            self.start_date = today.strftime('%Y-%m-%d 00:00:00')
            self.end_date = today.strftime('%Y-%m-%d 23:59:59')
            
        elif self.period_type == 'weekly':
            # Начало недели (понедельник)
            days_since_monday = today.weekday()
            monday = today - timedelta(days=days_since_monday)
            self.start_date = monday.strftime('%Y-%m-%d 00:00:00')
            self.end_date = (monday + timedelta(days=6)).strftime('%Y-%m-%d 23:59:59')
            
        elif self.period_type == 'monthly':
            # Текущий месяц
            self.start_date = today.replace(day=1).strftime('%Y-%m-%d 00:00:00')
            if today.month == 12:
                next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_month = today.replace(month=today.month + 1, day=1)
            self.end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')
            
        elif self.period_type == 'quarterly':
            # Текущий квартал
            quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (quarter - 1) * 3 + 1
            self.start_date = today.replace(month=quarter_start_month, day=1).strftime('%Y-%m-%d 00:00:00')
            
            if quarter == 4:
                next_quarter_start = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_quarter_start = today.replace(month=quarter_start_month + 3, day=1)
            self.end_date = (next_quarter_start - timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')
            
        elif self.period_type == 'yearly':
            # Текущий год
            self.start_date = today.replace(month=1, day=1).strftime('%Y-%m-%d 00:00:00')
            self.end_date = today.replace(month=12, day=31).strftime('%Y-%m-%d 23:59:59')
            
        elif self.period_type == 'previous_month':
            # Предыдущий месяц
            if today.month == 1:
                prev_month = 12
                prev_year = today.year - 1
            else:
                prev_month = today.month - 1
                prev_year = today.year
                
            self.start_date = date(prev_year, prev_month, 1).strftime('%Y-%m-%d 00:00:00')
            if prev_month == 12:
                next_month = date(prev_year + 1, 1, 1)
            else:
                next_month = date(prev_year, prev_month + 1, 1)
            self.end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')
    
    def get_month_year(self) -> Tuple[int, int]:
        """Возвращает месяц и год для получения метрик"""
        start_dt = datetime.strptime(self.start_date, '%Y-%m-%d %H:%M:%S')
        return start_dt.month, start_dt.year

class KPIEngine:
    """Централизованный движок для KPI расчетов"""
    
    def __init__(self):
        self.managers = [m['planfix_user_name'] for m in MANAGERS_KPI]
        self.manager_ids = [m['planfix_user_id'] for m in MANAGERS_KPI]
    
    def _execute_query(self, query: str, params: tuple, description: str) -> list:
        """Выполняет SQL запрос"""
        conn = None
        try:
            conn = psycopg2.connect(
                host=PG_HOST, dbname=PG_DB, user=PG_USER, 
                password=PG_PASSWORD, port=PG_PORT
            )
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
    
    def get_kpi_metrics(self, month: int, year: int) -> dict:
        """Получает метрики KPI для указанного месяца"""
        query = """
            SELECT 
                month, year, premia_kpi,
                nwi, wtr, psk, wdm, prz, zkl, spt, msp, knt, ofw, ttl
            FROM kpi_metrics
            WHERE month = %s AND year = %s
        """
        results = self._execute_query(query, (f"{month:02d}", year), "KPI metrics")
        
        if not results:
            logger.warning(f"No KPI metrics found for {month}/{year}")
            return {}
        
        row = results[0]
        metrics = {}
        column_mapping = {
            'NWI': 3, 'WTR': 4, 'PSK': 5, 'WDM': 6, 'PRZ': 7, 
            'ZKL': 8, 'SPT': 9, 'MSP': 10, 'KNT': 11, 'OFW': 12, 'TTL': 13
        }
        
        for indicator, col_index in column_mapping.items():
            metrics[indicator] = {'plan': row[col_index], 'weight': 0}
        
        # Рассчитываем вес на основе активных KPI (только с планом > 0)
        active_kpis = sum(1 for metric in metrics.values() if isinstance(metric, dict) and metric.get('plan') is not None and metric['plan'] > 0)
        if active_kpis > 0:
            weight = 1.0 / active_kpis
            for metric in metrics.values():
                if isinstance(metric, dict) and metric.get('plan') is not None and metric['plan'] > 0:
                    metric['weight'] = weight
        
        metrics['premia'] = row[2]  # premia_kpi
        return metrics
    
    def get_actual_kpi_values(self, period: KPIPeriod) -> dict:
        """Получает фактические значения KPI за период"""
        # Запрос для задач
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
        
        # Запрос для клиентов
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
        
        # Запрос для предложений
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
        
        # Выполняем запросы
        task_results = self._execute_query(task_query, (
            period.start_date, period.end_date, tuple(self.managers),
            period.start_date, period.end_date, tuple(self.managers)
        ), "Task counts")
        
        client_results = self._execute_query(client_query, (
            period.start_date, period.end_date, tuple(self.managers),
            period.start_date, period.end_date, tuple(self.managers),
            period.start_date, period.end_date, tuple(self.managers)
        ), "Client status counts")
        
        offer_results = self._execute_query(offer_query, (
            period.start_date, period.end_date, tuple(self.managers)
        ), "Offer counts")
        
        # Формируем результат
        actual_values = {}
        for manager in self.managers:
            actual_values[manager] = {
                'NWI': 0, 'WTR': 0, 'PSK': 0, 'WDM': 0, 'PRZ': 0,
                'ZKL': 0, 'SPT': 0, 'MSP': 0, 'OFW': 0, 'TTL': 0
            }
        
        # Обрабатываем результаты задач
        for row in task_results:
            manager, task_type, count = row
            if task_type in actual_values[manager]:
                actual_values[manager][task_type] = count
        
        # Обрабатываем результаты клиентов
        for row in client_results:
            manager, status, count = row
            if status in actual_values[manager]:
                actual_values[manager][status] = count
        
        # Обрабатываем результаты предложений
        for row in offer_results:
            manager_id = row[0]
            count = row[2]
            manager = next((m['planfix_user_name'] for m in MANAGERS_KPI if m['planfix_user_name'] == manager_id), None)
            if manager in actual_values:
                actual_values[manager]['OFW'] = count
        
        return actual_values
    
    def calculate_kpi_coefficients(self, metrics: dict, actual_values: dict) -> dict:
        """Рассчитывает коэффициенты KPI для каждого менеджера"""
        coefficients = {}
        
        # Отладочная информация
        logger.info(f"Available metrics: {list(metrics.keys())}")
        logger.info(f"Metrics with plans: {[k for k, v in metrics.items() if isinstance(v, dict) and v.get('plan') is not None]}")
        
        for manager, values in actual_values.items():
            logger.info(f"Processing manager: {manager}")
            logger.info(f"Actual values for {manager}: {values}")
            
            manager_coefficients = {}
            sum_coefficient = Decimal('0')
            
            # Рассчитываем коэффициенты для всех показателей
            for indicator in KPI_INDICATORS:
                if indicator in metrics and isinstance(metrics[indicator], dict) and metrics[indicator].get('plan') is not None and metrics[indicator]['plan'] > 0:
                    actual = Decimal(str(values.get(indicator, 0)))
                    plan = Decimal(str(metrics[indicator]['plan']))
                    weight = Decimal(str(metrics[indicator]['weight']))
                    
                    logger.info(f"  {indicator}: actual={actual}, plan={plan}, weight={weight}")
                    
                    if plan > 0:
                        if indicator in CAPPED_KPI:
                            used_value = min(actual, plan)
                        else:
                            used_value = actual
                        
                        coefficient_value = float((used_value / plan) * weight)
                        coefficient = math_round(coefficient_value, 2)
                        logger.info(f"    used_value={used_value}, coefficient={coefficient}")
                    else:
                        coefficient = Decimal('0')
                        logger.info(f"    plan=0, coefficient={coefficient}")
                    
                    manager_coefficients[indicator] = coefficient
                    sum_coefficient += Decimal(str(coefficient))
            
            # Добавляем SUM коэффициент
            manager_coefficients['SUM'] = Decimal(str(math_round(sum_coefficient, 2)))
            logger.info(f"  SUM coefficient: {sum_coefficient}")
            
            # Рассчитываем PRK
            if 'premia' in metrics and metrics['premia'] is not None:
                premia = Decimal(str(metrics['premia']))
                manager_coefficients['PRK'] = Decimal(str(math_round(premia * sum_coefficient, 2)))
                logger.info(f"  PRK: {premia} * {sum_coefficient} = {manager_coefficients['PRK']}")
            else:
                manager_coefficients['PRK'] = Decimal('0')
            
            coefficients[manager] = manager_coefficients
        
        return coefficients
    
    def get_additional_premia(self, period: KPIPeriod) -> dict:
        """Получает дополнительную премию (PRW) за период"""
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
        
        # Используем ID менеджеров для таблицы заказов
        manager_ids = ('945243', '945245')  # Kozik Andrzej, Stukalo Nazarii
        
        results = self._execute_query(query, (
            period.start_date, period.end_date, manager_ids
        ), "Additional premia (PRW)")
        
        additional_premia = {}
        for row in results:
            manager_id = row[0]
            prw = row[1]
            
            # Ищем менеджера по ID (хардкод для нужных менеджеров)
            manager_name = None
            if str(manager_id) == '945243':
                manager_name = 'Kozik Andrzej'
            elif str(manager_id) == '945245':
                manager_name = 'Stukalo Nazarii'
            
            if manager_name:
                additional_premia[manager_name] = {'PRW': prw}
                logger.info(f"Found PRW for {manager_name}: {prw}")
            else:
                logger.warning(f"Manager not found for ID: {manager_id}")
        
        logger.info(f"PRW calculation results: {additional_premia}")
        return additional_premia
    
    def generate_kpi_report(self, period_type: str, start_date: str = None, end_date: str = None) -> dict:
        """Генерирует полный KPI отчет для указанного периода"""
        # Создаем период
        period = KPIPeriod(period_type, start_date, end_date)
        
        # Получаем месяц и год для метрик
        month, year = period.get_month_year()
        
        # Получаем метрики
        metrics = self.get_kpi_metrics(month, year)
        if not metrics:
            raise ValueError(f"No KPI metrics found for {month:02d}.{year}")
        
        # Получаем фактические значения
        actual_values = self.get_actual_kpi_values(period)
        
        # Рассчитываем коэффициенты
        coefficients = self.calculate_kpi_coefficients(metrics, actual_values)
        
        # Получаем дополнительную премию
        additional_premia = self.get_additional_premia(period)
        
        return {
            'period': period,
            'metrics': metrics,
            'actual_values': actual_values,
            'coefficients': coefficients,
            'additional_premia': additional_premia
        } 