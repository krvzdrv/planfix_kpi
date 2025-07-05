#!/usr/bin/env python3
"""
Скрипт для анализа структуры таблицы kpi_metrics и сравнения с нужными показателями
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.planfix_utils as planfix_utils

# Все нужные KPI показатели
REQUIRED_KPI_INDICATORS = [
    'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 
    'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC'
]

def get_table_structure():
    """Получает структуру таблицы kpi_metrics"""
    conn = None
    try:
        conn = planfix_utils.get_supabase_connection()
        
        with conn.cursor() as cur:
            # Получаем структуру таблицы
            cur.execute("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns 
                WHERE table_name = 'kpi_metrics' 
                ORDER BY ordinal_position
            """)
            
            columns = cur.fetchall()
            
            # Получаем пример данных
            cur.execute("SELECT * FROM kpi_metrics LIMIT 1")
            sample_data = cur.fetchone()
            
            return columns, sample_data
            
    except Exception as e:
        print(f"Ошибка при подключении к базе данных: {e}")
        return None, None
    finally:
        if conn:
            conn.close()

def analyze_kpi_metrics():
    """Анализирует структуру таблицы kpi_metrics"""
    print("=== АНАЛИЗ СТРУКТУРЫ ТАБЛИЦЫ KPI_METRICS ===\n")
    
    columns, sample_data = get_table_structure()
    
    if not columns:
        print("Не удалось получить структуру таблицы")
        return
    
    print("Структура таблицы kpi_metrics:")
    print("-" * 80)
    print(f"{'Колонка':<20} {'Тип данных':<15} {'NULL':<8}")
    print("-" * 80)
    
    existing_columns = []
    for col_name, data_type, is_nullable, default in columns:
        print(f"{col_name:<20} {data_type:<15} {is_nullable:<8}")
        existing_columns.append(col_name.lower())
    
    print("\n" + "=" * 80)
    print("СРАВНЕНИЕ С НУЖНЫМИ ПОКАЗАТЕЛЯМИ")
    print("=" * 80)
    
    # Анализируем какие показатели есть в таблице
    missing_indicators = []
    existing_indicators = []
    
    for indicator in REQUIRED_KPI_INDICATORS:
        if indicator.lower() in existing_columns:
            existing_indicators.append(indicator)
            print(f"✅ {indicator} - ЕСТЬ в таблице")
        else:
            missing_indicators.append(indicator)
            print(f"❌ {indicator} - ОТСУТСТВУЕТ в таблице")
    
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТ АНАЛИЗА")
    print("=" * 80)
    
    print(f"Всего нужных показателей: {len(REQUIRED_KPI_INDICATORS)}")
    print(f"Есть в таблице: {len(existing_indicators)}")
    print(f"Отсутствует: {len(missing_indicators)}")
    
    if missing_indicators:
        print(f"\nОтсутствующие показатели: {', '.join(missing_indicators)}")
        
        print("\nSQL для добавления отсутствующих колонок:")
        print("-" * 50)
        for indicator in missing_indicators:
            print(f"ALTER TABLE kpi_metrics ADD COLUMN {indicator.lower()} INTEGER;")
    else:
        print("\n🎉 Все нужные показатели присутствуют в таблице!")
    
    # Показываем пример данных если есть
    if sample_data:
        print(f"\nПример данных из таблицы:")
        print("-" * 50)
        for i, (col_name, _, _, _) in enumerate(columns):
            if i < len(sample_data):
                print(f"{col_name}: {sample_data[i]}")

if __name__ == "__main__":
    analyze_kpi_metrics() 