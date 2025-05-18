# Planfix Sync

Скрипты для синхронизации данных между Planfix CRM и Supabase, с последующей отправкой KPI отчетов в Telegram.

## Описание

Этот проект содержит набор скриптов для автоматической синхронизации данных:
- Клиентов из Planfix в Supabase
- Заказов из Planfix в Supabase
- Задач из Planfix в Supabase
- Отправки KPI отчетов в Telegram

## Структура проекта

```
planfix_sync/
├── .github/
│   └── workflows/          # GitHub Actions конфигурации
├── scripts/               # Python скрипты
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
- `PLANFIX_TOKEN` - токен Planfix
- `PLANFIX_ACCOUNT` - аккаунт Planfix

### Supabase
- `SUPABASE_HOST` - хост Supabase
- `SUPABASE_DB` - имя базы данных
- `SUPABASE_USER` - пользователь
- `SUPABASE_PASSWORD` - пароль
- `SUPABASE_PORT` - порт

### Telegram
- `TELEGRAM_BOT_TOKEN` - токен бота
- `TELEGRAM_CHAT_ID` - ID чата для отправки отчетов

## Автоматизация

Скрипты настроены на автоматический запуск через GitHub Actions каждый будний день в 16:00 по варшавскому времени (CET).

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