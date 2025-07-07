# Исправление TTL - Обновленный список задач

## Проблема
TTL считал только 4 типа задач:
- Nawiązać pierwszy kontakt
- Przeprowadzić pierwszą rozmowę telefoniczną
- Zadzwonić do klienta
- Przeprowadzić spotkanie

## Решение
TTL теперь считает **10 типов задач** из полного списка возможных задач.

## Полный список задач TTL

1. **Nawiązać pierwszy kontakt** (Начать первый контакт)
2. **Przeprowadzić pierwszą rozmowę telefoniczną** (Провести первый телефонный разговор)
3. **Przeprowadzić spotkanie** (Провести встречу)
4. **Wysłać materiały** (Отправить материалы)
5. **Zadzwonić do klienta** (Позвонить клиенту)
6. **Odpowiedzieć na pytanie techniczne** (Ответить на технический вопрос)
7. **Zapisać na media społecznościowe** (Записать в социальные сети)
8. **Opowiedzieć o nowościach** (Рассказать о новинках)
9. **Przywrócić klienta** (Восстановить клиента)
10. **Zebrać opinie** (Собрать отзывы)

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
```

## Обновленный SQL-запрос для TTL

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
```

## Условия для включения задачи в TTL

1. `data_zakonczenia_zadania IS NOT NULL` (задача завершена)
2. `data_zakonczenia_zadania` в указанном периоде
3. `owner_name` в списке менеджеров KPI
4. `is_deleted = false` (задача не удалена)
5. **title начинается с одного из 10 типов задач**

## Расчет коэффициента TTL

```
TTL коэффициент = (фактическое_количество_TTL_задач / план_TTL) * вес_TTL
```

**Где:**
- `фактическое_количество_TTL_задач` = количество завершенных задач из 10 типов
- `план_TTL` = плановое количество TTL задач (из таблицы kpi_metrics)
- `вес_TTL` = вес показателя TTL (из таблицы kpi_metrics)

## Пример расчета

**Если:**
- Факт: 350 задач TTL (из 10 типов)
- План: 300 задач TTL  
- Вес: 0.2

**Тогда:**
```
TTL коэффициент = (350 / 300) * 0.2 = 0.233333... ≈ 0.23
```

## Новые типы задач (добавлено 6)

1. **Wysłać materiały** (Отправить материалы)
2. **Odpowiedzieć na pytanie techniczne** (Ответить на технический вопрос)
3. **Zapisać na media społecznościowe** (Записать в социальные сети)
4. **Opowiedzieć o nowościach** (Рассказать о новинках)
5. **Przywrócić klienta** (Восстановить клиента)
6. **Zebrać opinie** (Собрать отзывы)

## Важные изменения

1. **TTL теперь считает 10 типов задач** (вместо 4)
2. **Добавлено 6 новых типов задач**
3. **Это может значительно изменить значение TTL**
4. **Коэффициент может быть больше 1.0, если факт > план**

## Файлы изменены

- `scripts/core/kpi_data.py` - обновлен список задач TTL
- `scripts/telegram_bot.py` - обновлен список задач TTL

## Дата исправления
2025-07-07 