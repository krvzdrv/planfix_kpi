"""
Модуль для получения и обработки KPI-данных (планы, факты, коэффициенты)
"""
from decimal import Decimal
from typing import Dict, Any

# Список KPI, для которых применяется ограничение min(факт, план)
CAPPED_KPI = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM'
]

KPI_INDICATORS = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC'
]

def get_kpi_metrics(current_month: int, current_year: int) -> Dict[str, Any]:
    """Заглушка: получить планы и веса KPI из БД."""
    # TODO: реализовать импорт из report_bonus.py/telegram_bot.py
    return {}

def get_actual_kpi_values(start_date: str, end_date: str) -> Dict[str, Any]:
    """Заглушка: получить фактические значения KPI из БД."""
    # TODO: реализовать импорт из report_bonus.py/telegram_bot.py
    return {}

def calculate_kpi_coefficients(metrics: dict, actual_values: dict) -> dict:
    """Calculate KPI coefficients for each manager."""
    coefficients = {}
    for manager, values in actual_values.items():
        manager_coefficients = {}
        sum_coefficient = Decimal('0')
        for indicator in KPI_INDICATORS:
            if indicator in metrics and metrics[indicator].get('plan') is not None:
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
        manager_coefficients['SUM'] = round(sum_coefficient, 2)
        if 'premia' in metrics and metrics['premia'] is not None:
            premia = Decimal(str(metrics['premia']))
            manager_coefficients['PRK'] = round(premia * sum_coefficient, 2)
        else:
            manager_coefficients['PRK'] = Decimal('0')
        coefficients[manager] = manager_coefficients
    return coefficients 