# Planfix KPI Repository

Репозиторий для автоматизации KPI отчетов и Telegram бота.

## 🏗️ Структура

```
planfix_kpi/
├── bot/                          # Telegram Bot функционал
│   └── api/
│       └── telegram_webhook.py   # Webhook API для команд /premia_current, /premia_previous
├── .github/workflows/            # GitHub Actions
│   ├── bot/
│   │   └── telegram-bot.yml      # Workflow для команд бота
│   └── reports/                  # Workflows для отчетов
│       ├── send_all_reports.yml  # Автоматическая отправка всех отчетов
│       ├── report-manual-send.yml # Ручная отправка отчетов
│       └── planfix-manual-sync.yml # Ручная синхронизация данных
├── scripts/                      # Основные скрипты
│   ├── core/                     # KPI логика (КРИТИЧЕСКИ НУЖНА)
│   ├── exporters/                # Экспорт данных из Planfix
│   │   ├── planfix_export_clients.py
│   │   ├── planfix_export_orders.py
│   │   └── planfix_export_tasks.py
│   ├── reports/                  # Генерация отчетов
│   │   ├── report_activity.py
│   │   ├── report_bonus.py
│   │   ├── report_income.py
│   │   ├── report_kpi.py
│   │   └── report_status.py
│   ├── utils/                    # Утилиты для работы с Planfix
│   │   └── planfix_utils.py
│   └── config/                   # Конфигурация
│       └── config.py             # MANAGERS_KPI
├── requirements.txt               # Python зависимости
├── env.example                   # Пример переменных окружения
└── .gitignore                    # Git ignore файлы
```

## 🚀 Основные функции

### 1. Telegram Bot
- **Команды:** `/premia_current`, `/premia_previous`
- **Файл:** `bot/api/telegram_webhook.py`
- **Workflow:** `.github/workflows/bot/telegram-bot.yml`

### 2. Автоматические отчеты
- **Расписание:** Ежедневно в 19:00 по варшавскому времени
- **Workflow:** `.github/workflows/reports/send_all_reports.yml`
- **Отчеты:** Activity, KPI, Bonus, Income, Status

### 3. Ручные операции
- **Отправка отчетов:** `.github/workflows/reports/report-manual-send.yml`
- **Синхронизация данных:** `.github/workflows/reports/planfix-manual-sync.yml`

## 🔧 Настройка

1. Скопируйте `env.example` в `.env`
2. Заполните переменные окружения
3. Настройте GitHub Secrets для workflows
4. Разверните webhook на Render (для бота)

## 📋 Критически важные файлы

**НЕ УДАЛЯТЬ:**
- `scripts/core/` - вся папка с KPI логикой
- `scripts/config.py` - содержит MANAGERS_KPI
- `scripts/report_*.py` - генерация отчетов
- `scripts/planfix_export_*.py` - экспорт данных
- `scripts/planfix_utils.py` - утилиты
- `requirements.txt` - зависимости
- Все workflow файлы в `.github/workflows/`

## 🎯 Команды бота

- `/premia_current` - отчет по премии за текущий месяц
- `/premia_previous` - отчет по премии за предыдущий месяц

## 📊 Workflows

- **send_all_reports** - автоматическая отправка всех отчетов
- **telegram-bot** - обработка команд бота
- **report-manual-send** - ручная отправка отчетов
- **planfix-manual-sync** - ручная синхронизация данных
