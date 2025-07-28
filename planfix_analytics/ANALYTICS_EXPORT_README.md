# Экспорт аналитических данных из ПланФикса

Этот документ описывает процесс экспорта аналитических данных по продуктам из ПланФикса в Supabase.

## Обзор

Созданы два новых скрипта:

1. `scripts/planfix_get_analytics_list.py` - для получения списка доступных аналитик
2. `scripts/planfix_export_analytics.py` - для экспорта данных аналитик в Supabase

## Структура таблицы

В Supabase создается таблица `planfix_analytics` со следующей структурой:

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | TEXT | Первичный ключ (формат: `{analitic_key}_{item_id}`) |
| analitic_key | INTEGER | ID аналитики из ПланФикса |
| item_id | INTEGER | ID записи в аналитике |
| name | TEXT | Название поля |
| value | TEXT | Значение (строковое представление) |
| value_id | TEXT | Значение (идентификатор для полей с объектами) |
| updated_at | TIMESTAMP | Время последнего обновления |
| is_deleted | BOOLEAN | Флаг удаления |

## Использование

### Шаг 1: Получение списка аналитик

Запустите скрипт для получения списка доступных аналитик:

```bash
python scripts/planfix_get_analytics_list.py
```

Этот скрипт:
- Получит список всех действий из ПланФикса
- Для каждого действия получит детали и найдет прикрепленные аналитики
- Выведет список в консоль и сохранит в файл `analytics_list.txt`

### Шаг 2: Настройка ключей аналитик

После получения списка аналитик:

1. Откройте файл `analytics_list.txt`
2. Найдите аналитики, связанные с продуктами
3. Скопируйте ID нужных аналитик

### Шаг 3: Настройка скрипта экспорта

Откройте файл `scripts/planfix_export_analytics.py` и обновите список `ANALYTIC_KEYS`:

```python
ANALYTIC_KEYS = [
    12345,  # ID аналитики по продуктам
    67890,  # ID другой аналитики
    # Добавьте нужные ключи
]
```

### Шаг 4: Запуск экспорта

Запустите скрипт экспорта:

```bash
python scripts/planfix_export_analytics.py
```

Этот скрипт:
- Получит данные аналитик из ПланФикса через API `analitic.getData`
- Создаст таблицу `planfix_analytics` в Supabase (если не существует)
- Загрузит данные в таблицу
- Помечает записи как удаленные для тех, которые больше не существуют

## API ПланФикса

### Получение списка действий
```
POST https://api.planfix.com/xml/
Method: action.getList
```

### Получение деталей действия
```
POST https://api.planfix.com/xml/
Method: action.get
```

### Получение данных аналитики
```
POST https://api.planfix.com/xml/
Method: analitic.getData
```

## Структура ответа analitic.getData

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response status="ok">
  <analiticDatas>
    <analiticData>
      <key>12345</key>
      <itemData>
        <id>1</id>
        <name>Название продукта</name>
        <value>Продукт А</value>
        <valueId>prod_a</valueId>
      </itemData>
      <itemData>
        <id>2</id>
        <name>Количество</name>
        <value>100</value>
        <valueId>100</valueId>
      </itemData>
    </analiticData>
  </analiticDatas>
</response>
```

## Автоматизация

Для автоматического запуска экспорта можно добавить скрипт в cron или использовать GitHub Actions:

```yaml
# .github/workflows/analytics-export.yml
name: Analytics Export

on:
  schedule:
    - cron: '0 2 * * *'  # Ежедневно в 2:00
  workflow_dispatch:

jobs:
  export-analytics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Export analytics
        env:
          SUPABASE_CONNECTION_STRING: ${{ secrets.SUPABASE_CONNECTION_STRING }}
          PLANFIX_API_KEY: ${{ secrets.PLANFIX_API_KEY }}
          PLANFIX_TOKEN: ${{ secrets.PLANFIX_TOKEN }}
          PLANFIX_ACCOUNT: ${{ secrets.PLANFIX_ACCOUNT }}
        run: python scripts/planfix_export_analytics.py
```

## Устранение неполадок

### Ошибка аутентификации
- Проверьте правильность `PLANFIX_API_KEY`, `PLANFIX_TOKEN` и `PLANFIX_ACCOUNT`
- Убедитесь, что токен не истек

### Пустой список аналитик
- Проверьте, что в ПланФиксе есть действия с прикрепленными аналитиками
- Убедитесь, что у пользователя есть права на просмотр аналитик

### Ошибки базы данных
- Проверьте подключение к Supabase
- Убедитесь, что у пользователя есть права на создание таблиц

## Логирование

Все скрипты используют стандартное логирование Python. Логи выводятся в консоль и содержат:
- Информацию о процессе выполнения
- Количество обработанных записей
- Ошибки и предупреждения

## Примеры использования

### Получение данных по конкретным продуктам

```python
# В scripts/planfix_export_analytics.py
ANALYTIC_KEYS = [
    12345,  # Аналитика "Продажи по продуктам"
    67890,  # Аналитика "Остатки на складе"
]
```

### Фильтрация данных в Supabase

```sql
-- Получить все данные по продуктам
SELECT * FROM planfix_analytics 
WHERE analitic_key = 12345 
AND is_deleted = false;

-- Получить статистику по продуктам
SELECT 
    value as product_name,
    COUNT(*) as count
FROM planfix_analytics 
WHERE analitic_key = 12345 
AND name = 'Название продукта'
AND is_deleted = false
GROUP BY value;
``` 