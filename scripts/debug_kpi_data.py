#!/usr/bin/env python3
"""
Диагностический скрипт для проверки данных KPI
Использование: python3 scripts/debug_kpi_data.py <month> <year>
Пример: python3 scripts/debug_kpi_data.py 11 2024
"""

import sys
import os
from datetime import date
from dotenv import load_dotenv
from core.kpi_data import get_kpi_metrics, get_actual_kpi_values, calculate_kpi_coefficients
from config import MANAGERS_KPI

load_dotenv()

def debug_kpi_metrics(month: int, year: int):
    """Диагностика KPI метрик"""
    print(f"🔍 Диагностика KPI метрик для {month:02d}.{year}")
    print("=" * 50)
    
    # Получаем метрики
    metrics = get_kpi_metrics(month, year)
    
    if not metrics:
        print("❌ Нет данных KPI для указанного периода")
        return
    
    print("📊 Плановые показатели:")
    print("-" * 30)
    
    # Проверяем все показатели
    all_indicators = ['NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC']
    
    for indicator in all_indicators:
        if indicator in metrics:
            plan = metrics[indicator].get('plan')
            weight = metrics[indicator].get('weight', 0)
            status = "✅" if plan is not None else "❌"
            print(f"{status} {indicator:<3}: план={plan}, вес={weight}")
        else:
            print(f"❌ {indicator:<3}: не найден в метриках")
    
    print(f"\n💰 Базовая премия: {metrics.get('premia')}")
    return metrics

def debug_actual_values(month: int, year: int):
    """Диагностика фактических значений"""
    print(f"\n📈 Диагностика фактических значений для {month:02d}.{year}")
    print("=" * 50)
    
    # Вычисляем период
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    print(f"Период: {start_date} - {end_date}")
    
    # Получаем фактические значения
    actual_values = get_actual_kpi_values(start_date, end_date)
    
    if not actual_values:
        print("❌ Нет фактических данных")
        return
    
    print("\n📊 Фактические значения по менеджерам:")
    print("-" * 40)
    
    all_indicators = ['NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC']
    
    for manager in actual_values:
        print(f"\n👤 {manager}:")
        for indicator in all_indicators:
            value = actual_values[manager].get(indicator, 0)
            if value > 0:
                print(f"  ✅ {indicator}: {value}")
            else:
                print(f"  ❌ {indicator}: {value}")
    
    return actual_values

def debug_coefficients(metrics, actual_values):
    """Диагностика коэффициентов"""
    print(f"\n🧮 Диагностика коэффициентов")
    print("=" * 50)
    
    if not metrics or not actual_values:
        print("❌ Нет данных для расчета коэффициентов")
        return
    
    # Рассчитываем коэффициенты
    coefficients = calculate_kpi_coefficients(metrics, actual_values)
    
    if not coefficients:
        print("❌ Не удалось рассчитать коэффициенты")
        return
    
    print("📊 Коэффициенты по менеджерам:")
    print("-" * 40)
    
    all_indicators = ['NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC']
    
    for manager in coefficients:
        print(f"\n👤 {manager}:")
        manager_coeffs = coefficients[manager]
        
        for indicator in all_indicators:
            if indicator in manager_coeffs:
                coeff = manager_coeffs[indicator]
                if coeff > 0:
                    print(f"  ✅ {indicator}: {coeff:.2f}")
                else:
                    print(f"  ❌ {indicator}: {coeff:.2f}")
        
        # Показываем итоговые значения
        sum_coeff = manager_coeffs.get('SUM', 0)
        prk = manager_coeffs.get('PRK', 0)
        print(f"  📊 SUM: {sum_coeff:.2f}")
        print(f"  💰 PRK: {prk:.2f}")
    
    return coefficients

def check_database_connection():
    """Проверка подключения к базе данных"""
    print("🔌 Проверка подключения к базе данных")
    print("=" * 50)
    
    required_vars = ['SUPABASE_HOST', 'SUPABASE_DB', 'SUPABASE_USER', 'SUPABASE_PASSWORD', 'SUPABASE_PORT']
    
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: {'set' if value else 'not set'}")
        else:
            print(f"❌ {var}: not set")
    
    print()

def main():
    if len(sys.argv) != 3:
        print("Использование: python3 scripts/debug_kpi_data.py <month> <year>")
        print("Пример: python3 scripts/debug_kpi_data.py 11 2024")
        return
    
    try:
        month = int(sys.argv[1])
        year = int(sys.argv[2])
    except ValueError:
        print("❌ Ошибка: месяц и год должны быть числами")
        return
    
    if month < 1 or month > 12:
        print("❌ Ошибка: месяц должен быть от 1 до 12")
        return
    
    print("🔍 Диагностика данных KPI")
    print("=" * 50)
    
    # Проверяем подключение к БД
    check_database_connection()
    
    # Диагностируем метрики
    metrics = debug_kpi_metrics(month, year)
    
    if not metrics:
        return
    
    # Диагностируем фактические значения
    actual_values = debug_actual_values(month, year)
    
    if not actual_values:
        return
    
    # Диагностируем коэффициенты
    coefficients = debug_coefficients(metrics, actual_values)
    
    print("\n🎯 Итоговая диагностика:")
    print("=" * 50)
    
    if coefficients:
        print("✅ Все данные загружены и обработаны")
        print("📊 Коэффициенты рассчитаны")
        print("📋 Готово к формированию отчета")
    else:
        print("❌ Проблемы с данными или расчетами")

if __name__ == "__main__":
    main() 