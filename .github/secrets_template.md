# GitHub Secrets Template

Добавьте следующие секреты в настройках вашего GitHub репозитория (Settings → Secrets and variables → Actions → New repository secret):

## Planfix API
- `PLANFIX_API_KEY`: 393bbe17b391c335356c67ebf586c020
- `PLANFIX_TOKEN`: 964fdc4d11e21792288d39dfab239c1b
- `PLANFIX_ACCOUNT`: alumineu

## Supabase Database
- `SUPABASE_HOST`: aws-0-eu-central-1.pooler.supabase.com
- `SUPABASE_DB`: postgres
- `SUPABASE_USER`: postgres.torlfffeghukusovmxsv
- `SUPABASE_PASSWORD`: qogheb-jynsi4-mispiH
- `SUPABASE_PORT`: 6543

## Telegram Bot
- `TELEGRAM_BOT_TOKEN`: (ваш токен бота)
- `TELEGRAM_CHAT_ID`: -4797051683

## Как добавить секреты:
1. Перейдите в ваш репозиторий на GitHub
2. Откройте Settings → Secrets and variables → Actions
3. Нажмите "New repository secret"
4. Введите имя секрета (например, `PLANFIX_API_KEY`)
5. Введите значение секрета
6. Нажмите "Add secret"
7. Повторите для каждого секрета из списка выше

После добавления всех секретов, удалите этот файл из репозитория. 