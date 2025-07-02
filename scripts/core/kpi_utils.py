"""
Вспомогательные функции для KPI-отчетов (парсинг, обработка ошибок и др.)
"""

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