"""
Вспомогательные функции для KPI-отчетов (парсинг, обработка ошибок и др.)
"""
import math

def safe_int(val, default=0):
    try:
        return int(val)
    except Exception:
        return default

def safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return default

def math_round(value, decimals=0):
    """
    Математическое округление (в отличие от банковского round()).
    Округляет 0.5 вверх, а не к четному числу.
    """
    if decimals == 0:
        return int(math.floor(value + 0.5))
    else:
        multiplier = 10 ** decimals
        return math.floor(value * multiplier + 0.5) / multiplier 