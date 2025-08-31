# Planfix KPI Telegram Bot

Telegram бот для генерации отчетов по премиям через команды.

## Команды

- `/premia_current@SkorifyBot` - отчет по премии за текущий месяц
- `/premia_previous@SkorifyBot` - отчет по премии за предыдущий месяц

## Настройка

### 1. Переменные окружения

Создайте файл `.env` в корневой директории проекта или настройте переменные в Render:

```bash
# GitHub Configuration
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPO=krvzdrv/planfix_kpi

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

### 2. GitHub Token

Создайте Personal Access Token в GitHub с правами:
- `repo` - для доступа к репозиторию
- `workflow` - для запуска GitHub Actions

### 3. Telegram Bot Token

Получите токен от @BotFather в Telegram.

### 4. Webhook

После развертывания на Render, настройте webhook для бота:

```bash
python3 bot/setup_webhook.py
```

## Развертывание на Render

1. Подключите репозиторий к Render
2. Настройте переменные окружения:
   - `GITHUB_TOKEN`
   - `TELEGRAM_BOT_TOKEN`
3. Render автоматически развернет webhook

## Локальная разработка

```bash
# Установка зависимостей
pip3 install -r bot/requirements.txt

# Запуск webhook
python3 -m bot.wsgi

# Webhook будет доступен на http://127.0.0.1:5001
```

## Структура

```
bot/
├── api/
│   └── telegram_webhook.py  # Основной webhook endpoint
├── requirements.txt          # Зависимости для бота
├── wsgi.py                  # WSGI приложение для Render
├── setup_webhook.py         # Скрипт настройки webhook
└── README.md               # Этот файл
```

## Troubleshooting

### Webhook не отвечает

1. Проверьте, что Render развернул сервис
2. Проверьте переменные окружения
3. Проверьте логи в Render

### Команды не работают

1. Проверьте, что webhook настроен в Telegram
2. Проверьте, что GitHub Actions workflow работает
3. Проверьте логи в GitHub Actions
