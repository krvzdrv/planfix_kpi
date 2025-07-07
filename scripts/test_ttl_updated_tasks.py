#!/usr/bin/env python3
"""
Тест для проверки обновленного списка задач TTL
"""

import os
import sys
sys.path.append('.')

def test_ttl_updated_tasks():
    """Тестируем обновленный список задач TTL"""
    
    print("=== ТЕСТ TTL - ОБНОВЛЕННЫЙ СПИСОК ЗАДАЧ ===")
    
    print("\n📋 TTL теперь включает 10 типов задач:")
    ttl_task_types = [
        'Nawiązać pierwszy kontakt',
        'Przeprowadzić pierwszą rozmowę telefoniczną',
        'Przeprowadzić spotkanie',
        'Wysłać materiały',
        'Zadzwonić do klienta',
        'Odpowiedzieć na pytanie techniczne',
        'Zapisać na media społecznościowe',
        'Opowiedzieć o nowościach',
        'Przywrócić klienta',
        'Zebrać opinie'
    ]
    
    for i, task_type in enumerate(ttl_task_types, 1):
        print(f"{i:2d}. {task_type}")
    
    print("\n🔍 Обновленный SQL-запрос для TTL:")
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
            'Zebrać opinie'
        )
    GROUP BY owner_name
    """
    
    print(sql_query)
    
    print("\n📊 Условия для включения задачи в TTL:")
    conditions = [
        "data_zakonczenia_zadania IS NOT NULL (задача завершена)",
        "data_zakonczenia_zadania в указанном периоде",
        "owner_name в списке менеджеров KPI",
        "is_deleted = false (задача не удалена)",
        "title начинается с одного из 10 типов задач"
    ]
    
    for i, condition in enumerate(conditions, 1):
        print(f"{i}. {condition}")
    
    print("\n🎯 Расчет коэффициента TTL:")
    calculation = """
    TTL коэффициент = (фактическое_количество_TTL_задач / план_TTL) * вес_TTL
    
    Где:
    - фактическое_количество_TTL_задач = количество завершенных задач из 10 типов
    - план_TTL = плановое количество TTL задач (из таблицы kpi_metrics)
    - вес_TTL = вес показателя TTL (из таблицы kpi_metrics)
    """
    
    print(calculation)
    
    print("\n📈 Пример расчета:")
    example = """
    Если:
    - Факт: 350 задач TTL (из 10 типов)
    - План: 300 задач TTL  
    - Вес: 0.2
    
    Тогда:
    TTL коэффициент = (350 / 300) * 0.2 = 0.233333... ≈ 0.23
    """
    
    print(example)
    
    print("\n⚠️  Важные моменты:")
    important_notes = [
        "TTL - это отдельный показатель, НЕ сумма других показателей",
        "TTL рассчитывается только по завершенным задачам",
        "Учитываются только задачи с определенными названиями (10 типов)",
        "Коэффициент округляется математически до 2 знаков после запятой",
        "Добавлено 6 новых типов задач к предыдущим 4"
    ]
    
    for i, note in enumerate(important_notes, 1):
        print(f"{i}. {note}")
    
    print("\n🔄 Изменения по сравнению с предыдущей версией:")
    changes = [
        "Добавлено: Wysłać materiały",
        "Добавлено: Odpowiedzieć на pytanie techniczne", 
        "Добавлено: Zapisać na media społecznościowe",
        "Добавлено: Opowiedzieć o nowościach",
        "Добавлено: Przywrócić klienta",
        "Добавлено: Zebrać opinie"
    ]
    
    for i, change in enumerate(changes, 1):
        print(f"{i}. {change}")

if __name__ == "__main__":
    test_ttl_updated_tasks() 