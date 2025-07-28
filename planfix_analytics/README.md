# Planfix Analytics Export

Репозиторий для экспорта аналитических данных из ПланФикса в Supabase.

## Описание

Этот проект содержит скрипты для автоматического экспорта аналитических данных из ПланФикса в базу данных Supabase. Основной функционал включает:

- Получение списка доступных аналитик из ПланФикса
- Экспорт данных аналитик в Supabase
- Автоматическое создание и обновление таблиц
- Логирование всех операций

## Структура проекта

```
planfix_analytics/
├── README.md                 # Документация проекта
├── requirements.txt          # Зависимости Python
├── env.example              # Пример файла окружения
├── scripts/
│   ├── __init__.py
│   ├── planfix_utils.py     # Утилиты для работы с Planfix API
│   ├── planfix_get_analytics_list.py  # Получение списка аналитик
│   └── planfix_export_analytics.py    # Экспорт данных аналитик
└── .github/
    └── workflows/
        └── analytics-export.yml  # GitHub Actions для автоматизации
```

## Установка и настройка

### 1. Клонирование репозитория

```bash
git clone https://github.com/your-username/planfix_analytics.git
cd planfix_analytics
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка переменных окружения

Скопируйте файл `env.example` в `.env` и заполните необходимые переменные:

```bash
cp env.example .env
```

Отредактируйте файл `.env`:

```env
# Planfix Configuration
PLANFIX_API_KEY=your_planfix_api_key
PLANFIX_TOKEN=your_planfix_token
PLANFIX_ACCOUNT=your_planfix_account

# Supabase Configuration
SUPABASE_HOST=your_supabase_host
SUPABASE_DB=your_supabase_db
SUPABASE_USER=your_supabase_user
SUPABASE_PASSWORD=your_supabase_password
SUPABASE_PORT=5432
```

## Использование

### Получение списка аналитик

Для получения списка всех доступных аналитик в ПланФиксе:

```bash
python scripts/planfix_get_analytics_list.py
```

Этот скрипт:
- Получит список всех действий из ПланФикса
- Для каждого действия получит детали и найдет прикрепленные аналитики
- Выведет список в консоль и сохранит в файл `analytics_list.txt`

### Настройка экспорта

1. Откройте файл `scripts/planfix_export_analytics.py`
2. Найдите список `ANALYTIC_KEYS` и добавьте ID нужных аналитик:

```python
ANALYTIC_KEYS = [
    12345,  # ID аналитики по продуктам
    67890,  # ID другой аналитики
    # Добавьте нужные ключи
]
```

### Запуск экспорта

```bash
python scripts/planfix_export_analytics.py
```

## Структура данных

### Таблица planfix_analytics

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

## API ПланФикса

Проект использует следующие методы API ПланФикса:

- `action.getList` - получение списка действий
- `action.get` - получение деталей действия
- `analitic.getData` - получение данных аналитики

## Автоматизация

### GitHub Actions

Проект включает GitHub Actions для автоматического экспорта. Файл `.github/workflows/analytics-export.yml` настроен для:

- Ежедневного запуска в 2:00 UTC
- Ручного запуска через GitHub интерфейс
- Логирования результатов

### Настройка секретов

В настройках репозитория GitHub добавьте следующие секреты:

- `PLANFIX_API_KEY` - API ключ ПланФикса
- `PLANFIX_TOKEN` - токен пользователя ПланФикса
- `PLANFIX_ACCOUNT` - аккаунт ПланФикса
- `SUPABASE_HOST` - хост Supabase
- `SUPABASE_DB` - база данных Supabase
- `SUPABASE_USER` - пользователь Supabase
- `SUPABASE_PASSWORD` - пароль Supabase

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

## Лицензия

MIT License

## Поддержка

Для вопросов и предложений создавайте Issues в репозитории. 