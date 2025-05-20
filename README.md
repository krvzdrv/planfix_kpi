# Planfix KPI

Скрипты для синхронизации данных между Planfix CRM и Supabase, с последующей отправкой KPI отчетов в Telegram.

## Описание

Этот проект содержит набор скриптов для автоматической синхронизации данных:
- Клиентов из Planfix в Supabase (`planfix_clients_to_supabase.py`)
- Заказов из Planfix в Supabase (`planfix_orders_to_supabase.py`)
- Задач из Planfix в Supabase (`planfix_tasks_to_supabase.py`)
- Отправки KPI отчетов в Telegram (`send_kpi_to_telegram.py`)

Общие служебные функции для взаимодействия с API Planfix и операций с базой данных Supabase централизованы в модуле `scripts/planfix_utils.py` для улучшения удобства сопровождения. Основные скрипты синхронизации были рефакторены для использования этих утилит.

Все скрипты теперь используют стандартный модуль `logging` Python для вывода информации и ошибок, что полезно для мониторинга и отладки.

## Структура проекта

```
planfix_sync/
├── .github/
│   └── workflows/          # GitHub Actions конфигурации
├── scripts/               # Python скрипты
│   ├── planfix_utils.py   # Общие утилиты
│   ├── config.py          # Конфигурация менеджеров для KPI
│   ├── planfix_clients_to_supabase.py
│   ├── planfix_orders_to_supabase.py
│   ├── planfix_tasks_to_supabase.py
│   └── send_kpi_to_telegram.py
├── requirements.txt       # Зависимости Python
└── README.md             # Документация
```

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/krvzdrv/planfix_sync.git
cd planfix_sync
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Настройка

Для работы скриптов необходимо настроить следующие переменные окружения:

### Planfix
- `PLANFIX_API_KEY` - API ключ Planfix
- `PLANFIX_USER_TOKEN` - токен пользователя Planfix (ранее PLANFIX_TOKEN)
- `PLANFIX_ACCOUNT` - аккаунт Planfix

### Supabase
Для скриптов синхронизации (`planfix_clients_to_supabase.py`, `planfix_orders_to_supabase.py`, `planfix_tasks_to_supabase.py`):
- `SUPABASE_CONNECTION_STRING` - полная строка подключения к Supabase (например, `postgresql://user:password@host:port/database`)

Для скрипта отправки KPI (`send_kpi_to_telegram.py` все еще использует индивидуальные переменные):
- `SUPABASE_HOST` - хост Supabase
- `SUPABASE_DB` - имя базы данных
- `SUPABASE_USER` - пользователь
- `SUPABASE_PASSWORD` - пароль
- `SUPABASE_PORT` - порт

### Telegram
- `TELEGRAM_BOT_TOKEN` - токен бота
- `TELEGRAM_CHAT_ID` - ID чата для отправки отчетов

### Конфигурация менеджеров для KPI

Данные менеджеров для отчетов KPI настраиваются в файле `scripts/config.py`. Измените список `MANAGERS_KPI` в этом файле, чтобы добавить, удалить или изменить менеджеров, включенных в отчеты KPI. Каждый менеджер представлен в виде словаря:

```python
# scripts/config.py
MANAGERS_KPI = [
    {"planfix_user_name": "Kozik Andrzej", "planfix_user_id": "945243", "telegram_alias": "Kozik"},
    {"planfix_user_name": "Stukalo Nazarii", "planfix_user_id": "945245", "telegram_alias": "Stukalo"},
    # Добавьте сюда других менеджеров
]
```
- `planfix_user_name`: Полное имя менеджера, как оно указано в Planfix (используется для фильтрации задач/клиентов).
- `planfix_user_id`: ID пользователя Planfix для менеджера (используется для фильтрации заказов).
- `telegram_alias`: Короткий псевдоним, используемый для отображения в заголовке отчета Telegram.

## Автоматизация

Скрипты настроены на автоматический запуск через GitHub Actions каждый будний день в 16:00 по варшавскому времени (CET/CEST в зависимости от сезона).

## Ручной запуск

Для ручного запуска используйте следующие команды:

```bash
python scripts/planfix_clients_to_supabase.py
python scripts/planfix_orders_to_supabase.py
python scripts/planfix_tasks_to_supabase.py
python scripts/send_kpi_to_telegram.py
```

## Лицензия

MIT
