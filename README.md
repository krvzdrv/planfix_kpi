# Planfix KPI Reports

Система автоматической генерации и отправки KPI отчетов в Telegram на основе данных из Planfix.

## Структура проекта

```
.
├── .github/
│   └── workflows/
│       ├── send_all_reports.yml    # Полный автоматический запуск всех скриптов по расписанию и вручную
│       ├── report_activity.yml     # Ручной запуск отчёта по активности (и/или KPI премии)
│       ├── report_bonus.yml        # Ручной запуск отчёта по премиям (report_bonus.py)
│       └── report_income.yml       # Ручной запуск отчёта по доходу (report_income.py)
├── scripts/
│   ├── config.py                   # Конфигурация менеджеров
│   ├── planfix_export_clients.py   # Синхронизация клиентов
│   ├── planfix_export_orders.py    # Синхронизация заказов
│   ├── planfix_export_tasks.py     # Синхронизация задач
│   ├── planfix_utils.py            # Утилиты для работы с Planfix API
│   ├── report_kpi.py               # Генерация и отправка KPI отчетов
│   ├── report_activity.py          # Генерация и отправка ежедневного отчёта
│   ├── report_bonus.py             # Генерация и отправка отчёта по премиям
│   └── report_income.py            # Генерация и отправка отчёта по доходу
├── requirements.txt                # Зависимости Python
├── requirements-dev.txt            # Dev-зависимости (линтеры, тесты)
└── README.md                       # Документация
```

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/krvzdrv/planfix_kpi.git
cd planfix_kpi
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Настройка

### 1. Planfix API
- `PLANFIX_API_KEY` - API ключ Planfix
- `PLANFIX_TOKEN` - токен пользователя Planfix
- `PLANFIX_ACCOUNT` - аккаунт Planfix

### 2. Supabase Database
Для скриптов синхронизации (`planfix_export_clients.py`, `planfix_export_orders.py`, `planfix_export_tasks.py`):
- `SUPABASE_CONNECTION_STRING` - полная строка подключения к Supabase (например, `postgresql://user:password@host:port/database`)

Для скрипта отправки KPI (`report_kpi.py`):
- `SUPABASE_HOST` - хост Supabase
- `SUPABASE_DB` - имя базы данных
- `SUPABASE_USER` - пользователь
- `SUPABASE_PASSWORD` - пароль
- `SUPABASE_PORT` - порт

### 3. Telegram Bot
1. Создайте нового бота через [@BotFather](https://t.me/BotFather)
2. Получите токен бота
3. Создайте группу в Telegram
4. Добавьте бота в группу и назначьте его администратором
5. Отправьте любое сообщение в группу
6. Получите ID группы:
   - Перейдите по ссылке `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Найдите поле `chat.id` в ответе - это и будет ID вашей группы
7. Настройте переменные окружения:
   - `TELEGRAM_BOT_TOKEN` - токен вашего бота
   - `TELEGRAM_CHAT_ID` - ID группы (например, `-4797051683`)

### 4. Конфигурация менеджеров для KPI

Данные менеджеров для отчетов KPI настраиваются в файле `scripts/config.py`. Измените список `MANAGERS_KPI` в этом файле, чтобы добавить, удалить или изменить менеджеров, включенных в отчеты KPI. Каждый менеджер представлен в виде словаря:

```python
# scripts/config.py
MANAGERS_KPI = [
    {"planfix_user_name": "Kozik Andrzej", "planfix_user_id": "945243", "telegram_alias": "Kozik"},
    {"planfix_user_name": "Stukalo Nazarii", "planfix_user_id": "945245", "telegram_alias": "Stukalo"},
    # Добавьте сюда других менеджеров
]
```

Поля:
- `planfix_user_name`: Полное имя менеджера в Planfix (для фильтрации задач/клиентов)
- `planfix_user_id`: ID пользователя Planfix (для фильтрации заказов)
- `telegram_alias`: Короткий псевдоним для отображения в отчете

## Автоматизация и GitHub Actions

- **send_all_reports.yml** — основной workflow, который автоматически (по расписанию и вручную) запускает полный цикл:
  - Синхронизация клиентов, заказов, задач
  - Генерация и отправка ежедневного отчёта (report_activity.py)
  - Генерация и отправка KPI-отчёта (report_kpi.py)
  - Генерация и отправка отчёта по премиям (report_bonus.py)
  - Генерация и отправка отчёта по доходу (report_income.py)
- **report_activity.yml** — ручной запуск отчёта по активности (и/или KPI премии)
- **report_bonus.yml** — ручной запуск отчёта по премиям
- **report_income.yml** — ручной запуск отчёта по доходу

### Расписание автоматического запуска

Workflow `Send All Reports` настроен на автоматический запуск каждый будний день в 19:00 по варшавскому времени (CET/CEST):
- Летнее время (март-октябрь): 17:00 UTC = 19:00 CEST
- Зимнее время (октябрь-март): 18:00 UTC = 19:00 CET

### Ручной запуск отчётов через GitHub Actions

В разделе Actions на GitHub вы можете вручную запустить любой из следующих workflow:
- **Send All Reports** — полный цикл (все скрипты)
- **Report Activity** — только ежедневный отчёт (и/или KPI премии)
- **Report Bonus** — только отчёт по премиям
- **Report Income** — только отчёт по доходу

## Ручной запуск

Для ручного запуска используйте следующие команды:

```bash
# Синхронизация данных
python scripts/planfix_export_clients.py
python scripts/planfix_export_orders.py
python scripts/planfix_export_tasks.py

# Отправка KPI отчета
python scripts/report_kpi.py
```

## Формат KPI отчета

Отчет включает следующие метрики:

### Клиенты
- NWI - Новые клиенты
- WTR - Клиенты в работе
- PSK - Перспективные клиенты

### Задачи
- WDM - Первый контакт
- PRZ - Первый телефонный разговор
- KZI - Клиент заинтересован
- ZKL - Позвонить клиенту
- SPT - Провести встречу
- MAT - Отправить материалы
- TPY - Ответить на технический вопрос
- MSP - Записать в соцсети
- NOW - Рассказать о новостях
- OPI - Собрать отзывы
- WRK - Вернуть клиента

### Заказы
- OFW - Отправленные предложения
- ZAM - Подтвержденные заказы
- PRC - Сумма реализованных заказов

## Лицензия

MIT

## Зависимости

- Основные зависимости перечислены в файле `requirements.txt`.
- Для установки зависимостей выполните:
```bash
pip install -r requirements.txt
```

### Dev-зависимости (рекомендуется для разработки)

Создайте файл `requirements-dev.txt` и добавьте туда:
```
flake8
black
pytest
```
Установите:
```bash
pip install -r requirements-dev.txt
```

## Проверка кода и тесты

- Для проверки стиля кода:
```bash
flake8 scripts/
black --check scripts/
```
- Для автоформатирования:
```bash
black scripts/
```
- Для запуска тестов (если появятся):
```bash
pytest
```

## Интеграция Telegram и GitHub через Render

1. В корне репозитория есть папка `api/` с файлом `telegram_webhook.py` — это Flask-приложение для Render.
2. В настройках Render добавьте переменные окружения:
   - `GITHUB_TOKEN` — токен GitHub с правом на repository_dispatch
   - `GITHUB_REPO` — например, `krvzdrv/planfix_kpi`
3. После деплоя на Render настройте webhook Telegram:
   - Вызовите:
     ```
     https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://<your-render-app>.onrender.com/api/telegram_webhook
     ```
4. В репозитории есть workflow `.github/workflows/telegram-dispatch.yml` для обработки событий repository_dispatch.
5. Теперь при отправке команд `/premia_current` или `/premia_previous` в Telegram-бота будет запускаться GitHub Actions и формироваться отчёт.

### Поддерживаемые команды

- `/premia_current` — отчет по премии за текущий месяц
- `/premia_previous` — отчет по премии за предыдущий месяц

### Архитектура системы

```
Telegram Bot → Render Webhook → GitHub API → GitHub Actions → Отчет → Telegram
```

### Мониторинг

- Health check: `https://<your-render-app>.onrender.com/health`
- Информация о сервисе: `https://<your-render-app>.onrender.com/`

### Подробная инструкция

Для полной настройки системы через Render см. [RENDER_SETUP.md](RENDER_SETUP.md)

Для настройки GitHub токена см. [GITHUB_TOKEN_SETUP.md](GITHUB_TOKEN_SETUP.md)
