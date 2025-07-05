# Настройка системы через Render

## Обзор

Система теперь полностью работает через Render webhook, который обрабатывает команды Telegram и запускает GitHub Actions для генерации отчетов.

## Архитектура

```
Telegram Bot → Render Webhook → GitHub API → GitHub Actions → Отчет → Telegram
```

## Шаг 1: Настройка Render

### 1.1 Создание сервиса на Render

1. Перейдите на [render.com](https://render.com)
2. Создайте новый Web Service
3. Подключите ваш GitHub репозиторий
4. Настройте следующие параметры:

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
gunicorn api.telegram_webhook:app
```

### 1.2 Переменные окружения

Добавьте следующие переменные окружения в настройках Render:

- `GITHUB_TOKEN` - токен GitHub с правами на `repository_dispatch`
- `GITHUB_REPO` - ваш репозиторий (например, `krvzdrv/planfix_kpi`)

### 1.3 Получение GitHub Token

1. Перейдите в GitHub Settings → Developer settings → Personal access tokens
2. Создайте новый token с правами:
   - `repo` (для repository_dispatch)
   - `workflow` (для запуска GitHub Actions)

## Шаг 2: Настройка Telegram Webhook

### 2.1 Автоматическая настройка

После деплоя на Render используйте скрипт:

```bash
python scripts/setup_telegram_webhook.py https://your-app-name.onrender.com
```

### 2.2 Ручная настройка

Или настройте вручную через curl:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app-name.onrender.com/api/telegram_webhook"
  }'
```

### 2.3 Проверка webhook

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

## Шаг 3: Проверка системы

### 3.1 Проверка Render сервиса

- Health check: `https://your-app-name.onrender.com/health`
- Информация: `https://your-app-name.onrender.com/`

### 3.2 Тестирование команд

Отправьте в Telegram:
- `/premia_current` - отчет за текущий месяц
- `/premia_previous` - отчет за предыдущий месяц

### 3.3 Мониторинг логов

- Render Dashboard → Logs
- GitHub Actions → Actions tab

## Шаг 4: Настройка GitHub Secrets

Убедитесь, что в GitHub Secrets настроены:

- `SUPABASE_HOST`
- `SUPABASE_DB`
- `SUPABASE_USER`
- `SUPABASE_PASSWORD`
- `SUPABASE_PORT`
- `TELEGRAM_BOT_TOKEN`

## Устранение неполадок

### Проблема: Webhook не работает

1. Проверьте URL в Telegram:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

2. Проверьте логи Render в Dashboard

3. Убедитесь, что переменные окружения настроены правильно

### Проблема: GitHub Actions не запускаются

1. Проверьте GitHub Token права
2. Убедитесь, что workflow файл существует
3. Проверьте логи GitHub Actions

### Проблема: Отчеты не отправляются

1. Проверьте TELEGRAM_BOT_TOKEN
2. Убедитесь, что бот добавлен в чат
3. Проверьте права бота в чате

## Полезные команды

### Проверка статуса webhook
```bash
python scripts/setup_telegram_webhook.py --check
```

### Перезапуск webhook
```bash
python scripts/setup_telegram_webhook.py https://your-app-name.onrender.com
```

### Тестирование Render сервиса
```bash
curl https://your-app-name.onrender.com/health
```

## Структура файлов

```
├── api/
│   └── telegram_webhook.py    # Flask приложение для Render
├── scripts/
│   ├── setup_telegram_webhook.py  # Настройка webhook
│   ├── report_bonus.py            # Отчет за текущий месяц
│   └── report_bonus_previous.py   # Отчет за предыдущий месяц
├── .github/workflows/
│   └── telegram-dispatch.yml      # GitHub Actions workflow
└── render.yaml                    # Конфигурация Render
```

## Безопасность

- GitHub Token должен иметь минимальные необходимые права
- Webhook URL должен быть HTTPS
- Переменные окружения не должны быть в коде
- Регулярно обновляйте токены

## Мониторинг

- Настройте уведомления в Render Dashboard
- Мониторьте GitHub Actions
- Проверяйте логи регулярно
- Настройте алерты при ошибках 