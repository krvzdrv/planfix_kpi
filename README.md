# Planfix KPI Reports

Система автоматической генерации и отправки KPI отчетов в Telegram на основе данных из Planfix.

## Структура проекта

```
.
├── .github/
│   └── workflows/
│       └── send_kpi_to_telegram.yml   # GitHub Actions workflow
├── scripts/
│   ├── config.py                      # Конфигурация менеджеров
│   ├── planfix_export_clients.py # Синхронизация клиентов
│   ├── planfix_export_orders.py  # Синхронизация заказов
│   ├── planfix_export_tasks.py   # Синхронизация задач
│   ├── planfix_utils.py               # Утилиты для работы с Planfix API
│   └── report_kpi.py        # Генерация и отправка KPI отчетов
├── requirements.txt                   # Зависимости Python
└── README.md                          # Документация
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

## Автоматизация

Скрипты настроены на автоматический запуск через GitHub Actions каждый будний день в 16:00 по варшавскому времени (CET/CEST в зависимости от сезона):

- Летнее время (март-октябрь): 14:00 UTC = 16:00 CEST
- Зимнее время (октябрь-март): 15:00 UTC = 16:00 CET

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
