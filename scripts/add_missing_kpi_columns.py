#!/usr/bin/env python3
import sys
import os
from dotenv import load_dotenv
import psycopg2

# Загрузка переменных окружения
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.planfix_utils as planfix_utils

# Порядок колонок по вашему сообщению
ALL_KPI = [
    'nwi', 'wtr', 'psk',
    'wdm', 'prz', 'kzi', 'zkl', 'spt', 'mat', 'tpy', 'msp', 'now', 'opi', 'wrk',
    'ttl', 'ofw', 'zam', 'prc'
]

# Недостающие (по результату анализа)
MISSING = ['now', 'opi', 'wrk', 'zam', 'prc']  # только те, что не добавились

# Тип для всех новых колонок
COL_TYPE = 'INTEGER'

def add_missing_columns():
    conn = None
    try:
        conn = planfix_utils.get_supabase_connection()
        with conn.cursor() as cur:
            for col in MISSING:
                print(f"Добавляю колонку: {col} ...", end=' ')
                try:
                    cur.execute(f"ALTER TABLE kpi_metrics ADD COLUMN {col} {COL_TYPE};")
                    conn.commit()
                    print("OK")
                except psycopg2.errors.DuplicateColumn:
                    print("уже существует")
                    conn.rollback()
                except Exception as e:
                    print(f"ошибка: {e}")
                    conn.rollback()
        print("\nГотово!")
    except Exception as e:
        print(f"Ошибка подключения или выполнения: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_missing_columns() 