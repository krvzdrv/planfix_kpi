# Исправление TTL - Все задачи

## Проблема
TTL считал только 4 типа задач:
- Nawiązać pierwszy kontakt
- Przeprowadzić pierwszą rozmowę telefoniczną
- Zadzwonić do klienta
- Przeprowadzić spotkanie

## Решение
TTL теперь считает **ВСЕ завершенные задачи** без фильтрации по названию.

## Изменения в коде

### 1. scripts/core/kpi_data.py
**Было:**
```sql
AND TRIM(SPLIT_PART(title, ' /', 1)) IN (
    'Nawiązać pierwszy kontakt',
    'Przeprowadzić pierwszą rozmowę telefoniczną',
    'Zadzwonić do klienta',
    'Przeprowadzić spotkanie'
)
```

**Стало:**
```sql
-- Убрана фильтрация по названию задачи
```

### 2. scripts/telegram_bot.py
**Было:**
```sql
AND TRIM(SPLIT_PART(title, ' /', 1)) IN (
    'Nawiązać pierwszy kontakt',
    'Przeprowadzić pierwszą rozmowę telefoniczną',
    'Zadzwonić do klienta',
    'Przeprowadzić spotkanie'
)
```

**Стало:**
```sql
-- Убрана фильтрация по названию задачи
```

## Новый SQL-запрос для TTL

```sql
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
```

## Условия для включения задачи в TTL

1. `data_zakonczenia_zadania IS NOT NULL` (задача завершена)
2. `data_zakonczenia_zadania` в указанном периоде
3. `owner_name` в списке менеджеров KPI
4. `is_deleted = false` (задача не удалена)
5. **✅ ВСЕ задачи** (убрана фильтрация по названию)

## Расчет коэффициента TTL

```
TTL коэффициент = (фактическое_количество_ВСЕХ_задач / план_TTL) * вес_TTL
```

**Где:**
- `фактическое_количество_ВСЕХ_задач` = количество ВСЕХ завершенных задач
- `план_TTL` = плановое количество TTL задач (из таблицы kpi_metrics)
- `вес_TTL` = вес показателя TTL (из таблицы kpi_metrics)

## Пример расчета

**Если:**
- Факт: 500 ВСЕХ задач (вместо 254 только определенных типов)
- План: 300 задач TTL  
- Вес: 0.2

**Тогда:**
```
TTL коэффициент = (500 / 300) * 0.2 = 0.333333... ≈ 0.33
```

## Важные изменения

1. **TTL теперь считает ВСЕ завершенные задачи**
2. **Убрана фильтрация по названию задачи**
3. **Это может значительно изменить значение TTL**
4. **Коэффициент может быть больше 1.0, если факт > план**

## Файлы изменены

- `scripts/core/kpi_data.py` - убрана фильтрация по title
- `scripts/telegram_bot.py` - убрана фильтрация по title

## Дата исправления
2025-07-07 