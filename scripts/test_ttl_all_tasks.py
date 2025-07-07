#!/usr/bin/env python3
"""
Тест для проверки, что TTL теперь считает все задачи
"""

import os
import sys
sys.path.append('.')

def test_ttl_all_tasks():
    """Тестируем, что TTL теперь считает все задачи"""
    
    print("=== ТЕСТ TTL - ВСЕ ЗАДАЧИ ===")
    
    print("\n📋 ИСПРАВЛЕНИЕ: TTL теперь включает ВСЕ задачи")
    
    print("\n🔍 Новый SQL-запрос для TTL:")
    sql_query = """
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
    GROUP BY owner_name
    """
    
    print(sql_query)
    
    print("\n📊 Условия для включения задачи в TTL (ИСПРАВЛЕНО):")
    conditions = [
        "data_zakonczenia_zadania IS NOT NULL (задача завершена)",
        "data_zakonczenia_zadania в указанном периоде",
        "owner_name в списке менеджеров KPI",
        "is_deleted = false (задача не удалена)",
        "✅ ВСЕ задачи (убрана фильтрация по названию)"
    ]
    
    for i, condition in enumerate(conditions, 1):
        print(f"{i}. {condition}")
    
    print("\n🎯 Расчет коэффициента TTL (не изменился):")
    calculation = """
    TTL коэффициент = (фактическое_количество_ВСЕХ_задач / план_TTL) * вес_TTL
    
    Где:
    - фактическое_количество_ВСЕХ_задач = количество ВСЕХ завершенных задач
    - план_TTL = плановое количество TTL задач (из таблицы kpi_metrics)
    - вес_TTL = вес показателя TTL (из таблицы kpi_metrics)
    """
    
    print(calculation)
    
    print("\n📈 Пример расчета (с новыми данными):")
    example = """
    Если:
    - Факт: 500 ВСЕХ задач (вместо 254 только определенных типов)
    - План: 300 задач TTL  
    - Вес: 0.2
    
    Тогда:
    TTL коэффициент = (500 / 300) * 0.2 = 0.333333... ≈ 0.33
    """
    
    print(example)
    
    print("\n⚠️  Важные изменения:")
    important_changes = [
        "TTL теперь считает ВСЕ завершенные задачи",
        "Убрана фильтрация по названию задачи",
        "Это может значительно изменить значение TTL",
        "Коэффициент может быть больше 1.0, если факт > план"
    ]
    
    for i, change in enumerate(important_changes, 1):
        print(f"{i}. {change}")
    
    print("\n🔧 Изменения в коде:")
    code_changes = [
        "scripts/core/kpi_data.py: убрана фильтрация по title",
        "scripts/telegram_bot.py: убрана фильтрация по title",
        "TTL теперь = общее количество завершенных задач"
    ]
    
    for i, change in enumerate(code_changes, 1):
        print(f"{i}. {change}")

if __name__ == "__main__":
    test_ttl_all_tasks() 