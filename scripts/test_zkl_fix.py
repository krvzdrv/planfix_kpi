#!/usr/bin/env python3
"""
Диагностический скрипт для проверки исправления ZKL
"""
import os
import sys
import logging
from datetime import datetime, timedelta
import psycopg2

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Подключение к базе данных
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

def test_zkl_tasks():
    """Проверяем задачи ZKL в базе данных"""
    
    # Июнь 2025
    start_date = "2025-06-01 00:00:00"
    end_date = "2025-07-01 00:00:00"
    
    query = """
        SELECT 
            owner_name,
            title,
            data_zakonczenia_zadania,
            COUNT(*) as count
        FROM planfix_tasks
        WHERE 
            data_zakonczenia_zadania IS NOT NULL
            AND data_zakonczenia_zadania >= %s::timestamp
            AND data_zakonczenia_zadania < %s::timestamp
            AND is_deleted = false
            AND (
                TRIM(SPLIT_PART(title, ' /', 1)) = 'Zadzwonić do klienta'
                OR TRIM(SPLIT_PART(title, ' /', 1)) = 'Зadzwonić do klienta'
            )
        GROUP BY owner_name, title, data_zakonczenia_zadania
        ORDER BY owner_name, data_zakonczenia_zadania;
    """
    
    conn = None
    try:
        conn = psycopg2.connect(
            host=PG_HOST, 
            dbname=PG_DB, 
            user=PG_USER, 
            password=PG_PASSWORD, 
            port=PG_PORT
        )
        cur = conn.cursor()
        
        logger.info(f"Проверяем задачи ZKL с {start_date} по {end_date}")
        cur.execute(query, (start_date, end_date))
        rows = cur.fetchall()
        
        if not rows:
            logger.warning("Задачи ZKL не найдены!")
            return
        
        logger.info(f"Найдено {len(rows)} записей задач ZKL:")
        
        for row in rows:
            owner, title, completion_date, count = row
            logger.info(f"  {owner}: {title} (завершено: {completion_date}) - {count} шт.")
            
    except Exception as e:
        logger.error(f"Ошибка при проверке задач ZKL: {e}")
    finally:
        if conn:
            conn.close()

def test_zkl_calculation():
    """Тестируем расчет ZKL с исправленным кодом"""
    
    # Импортируем исправленный модуль
    sys.path.append('scripts/core')
    from kpi_data import get_actual_kpi_values
    
    # Июнь 2025
    start_date = "2025-06-01 00:00:00"
    end_date = "2025-07-01 00:00:00"
    
    try:
        logger.info("Тестируем расчет ZKL с исправленным кодом...")
        actual_values = get_actual_kpi_values(start_date, end_date)
        
        logger.info("Результаты расчета ZKL:")
        for manager, values in actual_values.items():
            zkl_value = values.get('ZKL', 0)
            logger.info(f"  {manager}: ZKL = {zkl_value}")
            
    except Exception as e:
        logger.error(f"Ошибка при тестировании расчета ZKL: {e}")

if __name__ == "__main__":
    logger.info("=== Диагностика исправления ZKL ===")
    
    print("\n1. Проверяем задачи ZKL в базе данных:")
    test_zkl_tasks()
    
    print("\n2. Тестируем расчет ZKL с исправленным кодом:")
    test_zkl_calculation()
    
    logger.info("=== Диагностика завершена ===") 