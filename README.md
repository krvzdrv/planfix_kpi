# Planfix KPI Repository

Репозиторий для автоматизации KPI отчетов и Telegram бота.

## 🏗️ Структура

```
planfix_kpi/
├── bot/                              # Telegram Bot функционал
│   └── api/
│       └── telegram_webhook.py       # Webhook API для команд /premia_current, /premia_previous
├── .github/workflows/                # GitHub Actions
│   ├── manual-bot-commands.yml       # Workflow для команд бота
│   ├── send_all_reports.yml          # Автоматическая отправка всех отчетов
│   ├── report-manual-send.yml        # Ручная отправка отчетов
│   └── planfix-manual-sync.yml       # Ручная синхронизация данных
├── scripts/                          # Основные скрипты
│   ├── core/                         # KPI логика (КРИТИЧЕСКИ НУЖНА)
│   │   ├── config.py                 # MANAGERS_KPI
│   │   ├── kpi_engine.py             # KPI движок
│   │   ├── kpi_data.py               # KPI данные
│   │   ├── kpi_report.py             # KPI отчеты
│   │   ├── kpi_utils.py              # KPI утилиты
│   │   └── report_formatter.py       # Форматирование отчетов
│   ├── exporters/                    # Экспорт данных из Planfix
│   │   ├── planfix_export_clients.py
│   │   ├── planfix_export_orders.py
│   │   └── planfix_export_tasks.py
│   ├── reports/                      # Генерация отчетов
│   │   ├── report_activity.py
│   │   ├── report_bonus.py
│   │   ├── report_income.py
│   │   ├── report_kpi.py
│   │   └── report_status.py
│   └── utils/                        # Утилиты для работы с Planfix
│       └── planfix_utils.py
├── requirements.txt                  # Python зависимости
├── env.example                       # Пример переменных окружения
└── .gitignore                        # Git ignore файлы
```

## 🚀 Основные функции

### 1. Telegram Bot
- **Команды:** `/premia_current`, `/premia_previous`
- **Файл:** `bot/api/telegram_webhook.py`
- **Workflow:** `.github/workflows/manual-bot-commands.yml`

### 2. Автоматические отчеты
- **Расписание:** Ежедневно в 19:00 по варшавскому времени
- **Workflow:** `.github/workflows/reports/send_all_reports.yml`
- **Отчеты:** Activity, KPI, Bonus, Income, Status

### 3. Ручные операции
- **Отправка отчетов:** `.github/workflows/report-manual-send.yml`
- **Синхронизация данных:** `.github/workflows/planfix-manual-sync.yml`

## 🔧 Настройка

1. Скопируйте `env.example` в `.env`
2. Заполните переменные окружения
3. Настройте GitHub Secrets для workflows
4. Разверните webhook на Render (для бота)

## 📋 Критически важные файлы

**НЕ УДАЛЯТЬ:**
- `scripts/core/` - вся папка с KPI логикой (КРИТИЧЕСКИ!)
- `scripts/core/config.py` - содержит MANAGERS_KPI
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
- **manual-bot-commands** - обработка команд бота
- **report-manual-send** - ручная отправка отчетов
- **planfix-manual-sync** - ручная синхронизация данных

## 📈 Описание отчетов

### 1. Activity Report (report_activity.py)
**Формат:** `AKTYWNOŚĆ_DD.MM.YYYY`

**Периодичность:** Ежедневно в 19:00

**KPI (13 показателей):**
- **Задачи (11 KPI):**
  - WDM - Nawiązać pierwszy kontakt
  - PRZ - Przeprowadzić pierwszą rozmowę telefoniczną
  - ZKL - Zadzwonić do klienta
  - SPT - Przeprowadzić spotkanie
  - MAT - Wysłać materiały
  - TPY - Odpowiedzieć na pytanie techniczne
  - MSP - Zapisać na media społecznościowe
  - NOW - Opowiedzieć o nowościach
  - OPI - Zebrać opinie
  - WRK - Przywrócić klienta
  - KNT - Tworzyć kontent

- **Заказы (2 KPI):**
  - OFW - Отправленные предложения
  - ZAM - Подтвержденные заказы

**Особенности:**
- Группировка по часам (0-23)
- Всегда показывает рабочие часы 9:00-16:59
- Показывает часы с активностью
- ⚠️ **Клиенты (NWI, WTR, PSK) НЕ включены в отчет активности**

---

### 2. KPI Report (report_kpi.py)
**Формат:** `KPI_DD.MM.YYYY` (дневной), `KPI_MM.YYYY` (месячный)

**Периодичность:** Ежедневно в 19:00 (оба отчета)

**Разделы:**
1. **Клиенты:** NWI, WTR, PSK
2. **Задачи:** WDM, PRZ, KZI, ZKL, SPT, MAT, TPY, MSP, NOW, OPI, WRK, KNT, TTL
3. **Заказы:** OFW, ZAM, PRC (выручка)

---

### 3. Bonus Report (report_bonus.py)
**Формат:** `PREMIA_MM.YYYY`

**Периодичность:** Ежедневно в 19:00 + по команде бота

**Команды бота:**
- `/premia_current` - текущий месяц
- `/premia_previous` - предыдущий месяц

**Расчет:**
- SUM - сумма коэффициентов всех KPI
- FND - базовый фонд премии
- PRK - премия по KPI (FND × SUM)
- PRW - дополнительная премия (провизия)
- TOT - общая премия (PRK + PRW)

---

### 4. Income Report (report_income.py)
**Формат:** `PRZYCHODY_MM.YYYY`

**Периодичность:** Ежедневно в 19:00

**Показатели:**
- **Fakt (█)** - реализованные заказы
- **Dług (▒)** - заказы в долг (статус 140)
- **Brak (░)** - недостающая до плана сумма
- **Plan** - плановая выручка

---

### 5. Status Report (report_status.py)
**Формат:** `WORONKA_DD.MM.YYYY`

**Периодичность:** Ежедневно в 19:00

**Статусы клиентов (9):**
- NWI - Nowi
- WTR - W trakcie
- PSK - Perspektywiczni
- PIZ - Pierwsze zamówienie
- STL - Stali klienci (≤30 дней с последнего заказа)
- NAK - Nieaktywni klienci (>30 дней)
- REZ - Rezygnacja
- BRK - Brak kontaktu
- ARC - Archiwum

**Особенности:**
- Динамика ▲▼ показывает изменения за день
- STL/NAK рассчитываются на основе истории
- Остальные - на основе дневного притока
