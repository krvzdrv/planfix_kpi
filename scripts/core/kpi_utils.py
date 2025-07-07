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
    Поддерживает как float, так и Decimal.
    """
    from decimal import Decimal, ROUND_HALF_UP
    
    # Если value это Decimal, используем Decimal методы
    if isinstance(value, Decimal):
        if decimals == 0:
            return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        else:
            scale = Decimal('0.' + '0' * (decimals - 1) + '1')
            return value.quantize(scale, rounding=ROUND_HALF_UP)
    
    # Для float используем math методы
    if decimals == 0:
        return int(math.floor(float(value) + 0.5))
    else:
        multiplier = 10 ** decimals
        result = math.floor(float(value) * multiplier + 0.5) / multiplier
        # Если исходное значение было Decimal, возвращаем Decimal
        if hasattr(value, '_is_special'):  # Это Decimal
            return Decimal(str(result))
        return result 