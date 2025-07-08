# Planfix KPI Reports

Система автоматической генерации и отправки KPI отчетов в Telegram на основе данных из Planfix.

## Структура проекта

```
.
├── .github/
│   └── workflows/
│       ├── send_all_reports.yml    # Полный автоматический запуск всех скриптов по расписанию и вручную
│       ├── report-manual-send.yml  # Ручной запуск отчётов
│       ├── planfix-manual-sync.yml # Ручная синхронизация с Planfix
│       └── telegram-dispatch.yml   # Обработка Telegram команд через webhook
├── api/
│   └── telegram_webhook.py         # Webhook для обработки Telegram команд через Render
├── scripts/
│   ├── core/                       # Основная бизнес-логика KPI
│   │   ├── kpi_engine.py           # Централизованный движок KPI расчетов
│   │   ├── kpi_data.py             # Получение и обработка KPI данных (legacy)
│   │   ├── kpi_report.py           # Форматирование KPI отчетов (legacy)
│   │   ├── kpi_utils.py            # Утилиты (математическое округление)
│   │   └── report_formatter.py     # Универсальный форматтер отчетов
│   ├── config.py                   # Конфигурация менеджеров
│   ├── planfix_export_clients.py   # Синхронизация клиентов
│   ├── planfix_export_orders.py    # Синхронизация заказов
│   ├── planfix_export_tasks.py     # Синхронизация задач
│   ├── planfix_utils.py            # Утилиты для работы с Planfix API
│   ├── report_kpi.py               # Генерация и отправка KPI отчетов
│   ├── report_activity.py          # Генерация и отправка ежедневного отчёта
│   ├── report_bonus.py             # Генерация и отправка отчёта по премиям
│   ├── report_bonus_new.py         # Новый отчет по премиям (централизованная архитектура)
│   ├── report_bonus_previous.py    # Генерация и отправка отчёта по премиям за предыдущий месяц
│   ├── report_income.py            # Генерация и отправка отчёта по доходу
│   ├── report_status.py            # Генерация и отправка отчёта по статусам
│   └── telegram_bot.py             # Содержит логику KPI расчетов (устаревший standalone бот)
├── requirements.txt                # Зависимости Python
├── render.yaml                     # Конфигурация для Render
└── README.md                       # Документация
```

## Последние обновления

### ✅ Новая централизованная архитектура KPI
- **KPIEngine** (`scripts/core/kpi_engine.py`) - централизованный движок для всех KPI расчетов
- **ReportFormatter** (`scripts/core/report_formatter.py`) - универсальный форматтер отчетов
- Поддержка разных периодов: день, неделя, месяц, квартал, год
- Устранение дублирования логики между отчетами
- Единая точка для изменения KPI расчетов

### ✅ Исправления ZKL показателя
- Исправлена опечатка в названии задачи: `'Зadzwonić do klienta'` → `'Zadzwonić do klienta'`
- Теперь показатель ZKL корректно рассчитывается на основе завершенных задач "Позвонить клиенту"

### ✅ Математическое округление
- Заменено банковское округление на математическое во всех отчетах
- Функция `math_round()` в `scripts/core/kpi_utils.py` обеспечивает корректное округление
- Пример: 0.169333 → 0.17 (вместо 0.16 при банковском округлении)

### ✅ Оптимизация архитектуры
- Вынесена основная KPI логика в модуль `scripts/core/`
- Удалены тестовые и диагностические скрипты
- Улучшена модульность и переиспользование кода

### ✅ TTL показатель
- TTL теперь включает 10 типов задач вместо 4
- Добавлены новые типы: Wysłać materiały, Odpowiedzieć na pytanie techniczne, Zapisać na media społecznościowe, Opowiedzieć o nowościach, Przywrócić klienta, Zebrać opinie

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

## Настройка Render Webhook

Система работает через Render webhook, который обрабатывает команды Telegram и запускает GitHub Actions.

### Архитектура
```
Telegram Bot → Render Webhook → GitHub API → GitHub Actions → Отчет → Telegram
```

### 1. Создание сервиса на Render

1. Перейдите на [render.com](https://render.com)
2. Создайте новый Web Service
3. Подключите ваш GitHub репозиторий
4. Render автоматически настроит сервис используя `render.yaml`

### 2. Настройка GitHub токена

**Создание токена:**
1. Перейдите в GitHub Settings → Developer settings → Personal access tokens
2. Создайте новый token с правами:
   - `repo` (для repository_dispatch)
   - `workflow` (для запуска GitHub Actions)

**Настройка на Render:**
1. В Render Dashboard добавьте переменные окружения:
   - `GITHUB_TOKEN` - ваш GitHub токен
   - `GITHUB_REPO` - ваш репозиторий (например, `krvzdrv/planfix_kpi`)

### 3. Настройка Telegram Webhook

После деплоя на Render настройте webhook:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app-name.onrender.com/api/telegram_webhook"
  }'
```

### 4. Проверка системы

**Проверка Render сервиса:**
- Health check: `https://your-app-name.onrender.com/health`
- Debug info: `https://your-app-name.onrender.com/debug`

**Тестирование команд в Telegram:**
- `/premia_current` - отчет за текущий месяц
- `/premia_previous` - отчет за предыдущий месяц

### 5. Диагностика проблем

**GitHub API возвращает 404:**
1. Проверьте переменные окружения на Render
2. Убедитесь, что токен имеет права `repo`
3. Проверьте формат `GITHUB_REPO`: `owner/repo`

**Webhook не работает:**
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

**Отчеты не отправляются:**
1. Проверьте `TELEGRAM_BOT_TOKEN`
2. Убедитесь, что бот добавлен в чат
3. Проверьте права бота в чате

## Автоматизация и GitHub Actions

- **send_all_reports.yml** — основной workflow, который автоматически (по расписанию и вручную) запускает полный цикл:
  - Синхронизация клиентов, заказов, задач
  - Генерация и отправка ежедневного отчёта (report_activity.py)
  - Генерация и отправка KPI-отчёта (report_kpi.py)
  - Генерация и отправка отчёта по премиям (report_bonus.py)
  - Генерация и отправка отчёта по доходу (report_income.py)
- **report-manual-send.yml** — ручной запуск отчётов
- **planfix-manual-sync.yml** — ручная синхронизация с Planfix
- **telegram-dispatch.yml** — обработка Telegram команд через webhook

### Расписание автоматического запуска

Workflow `Send All Reports` настроен на автоматический запуск каждый будний день в 19:00 по варшавскому времени (CET/CEST):
- Летнее время (март-октябрь): 17:00 UTC = 19:00 CEST
- Зимнее время (октябрь-март): 18:00 UTC = 19:00 CET

### Ручной запуск отчётов через GitHub Actions

В разделе Actions на GitHub вы можете вручную запустить любой из следующих workflow:
- **Send All Reports** — полный цикл (все скрипты)
- **Report Manual Send** — ручной запуск отчётов
- **Planfix Manual Sync** — ручная синхронизация с Planfix

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
- ZKL - Позвонить клиенту ✅ (исправлено)
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

### Общие показатели
- TTL - Общее количество задач (10 типов)

### Расчет коэффициентов
- Используется математическое округление (0.5 округляется вверх)
- Коэффициент = (факт / план) × вес
- Пример: (254/300) × 0.2 = 0.169333 → 0.17

## Безопасность

- **Никогда не коммитьте токены в репозиторий**
- **Используйте переменные окружения**
- **Регулярно обновляйте токены**
- **Устанавливайте срок действия токенов**
- **Используйте минимальные необходимые права**

## Мониторинг

- Настройте уведомления в Render Dashboard
- Мониторьте GitHub Actions
- Проверяйте логи регулярно
- Настройте алерты при ошибках

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
