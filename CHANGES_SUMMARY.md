# Исправление обработки дат в planfix_export_clients.py

## Проблема
В скрипте `planfix_export_clients.py` поля с датами из Planfix не передавались корректно в базу данных Supabase. В частности, поля:
- `Data dodania do "Brak kontaktu"` → `data_dodania_do_brak_kontaktu`
- `Data dodania do "Archiwum"` → `data_dodania_do_archiwum`

## Причина
Даты из custom fields обрабатывались как обычный текст, без парсинга и нормализации формата. В отличие от других скриптов (например, `planfix_export_orders.py`), где есть специальная функция `parse_date` для обработки дат.

## Решение
1. **Добавлена функция `parse_date()`** - аналогично другим скриптам экспорта
2. **Добавлен список `DATE_FIELDS`** - содержит все поля с датами, которые нужно парсить
3. **Обновлена логика обработки custom fields** - теперь даты парсятся и сохраняются в формате `DD-MM-YYYY`

## Изменения в коде

### Добавленные константы:
```python
# Поля с датами, которые нужно парсить
DATE_FIELDS = [
    "Data ostatniego kontaktu",
    "Data rejestracji w KRS", 
    "Data rozpoczęcia działalności w CEIDG",
    "Data ostatniego zamówienia",
    "Data dodania do \"Nowi\"",
    "Data dodania do \"W trakcie\"",
    "Data dodania do \"Perspektywiczni\"",
    "Data dodania do \"Rezygnacja\"",
    "Data dodania do \"Brak kontaktu\"",
    "Data dodania do \"Archiwum\"",
    "Data pierwszego zamówienia"
]
```

### Добавленная функция:
```python
def parse_date(date_str):
    """Парсит дату из строки в формате DD-MM-YYYY или DD-MM-YYYY HH:MM"""
    if not date_str:
        return None
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None
```

### Обновленная логика обработки custom fields:
```python
# Для полей с датами парсим и сохраняем в правильном формате
elif field.text in DATE_FIELDS:
    date_value = value.text if value is not None else None
    if date_value:
        parsed_date = parse_date(date_value)
        if parsed_date:
            # Сохраняем в формате DD-MM-YYYY для совместимости с базой данных
            custom_fields[CUSTOM_MAP[field.text]] = parsed_date.strftime("%d-%m-%Y")
        else:
            # Если не удалось распарсить, сохраняем как есть
            custom_fields[CUSTOM_MAP[field.text]] = date_value
    else:
        custom_fields[CUSTOM_MAP[field.text]] = None
```

## Результат
Теперь все поля с датами будут корректно парситься и сохраняться в базе данных в едином формате `DD-MM-YYYY`, что обеспечивает совместимость с существующими отчетами и запросами.

## Совместимость
Изменения обратно совместимы - если дата не может быть распарсена, она сохраняется в исходном виде, что предотвращает потерю данных. 