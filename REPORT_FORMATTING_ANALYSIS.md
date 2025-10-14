# Анализ формирования отчетов в Planfix KPI

## Обзор системы форматирования

В проекте используется **4 различных подхода** к формированию отчетов:

1. **Прямое форматирование в модуле** (Activity, Income, KPI)
2. **Универсальный форматтер** (Bonus - через ReportFormatter)
3. **Специализированный форматтер** (Bonus - через kpi_report.py)
4. **Сложное форматирование с историей** (Status - воронка)

---

## 1. 📊 Activity Report (report_activity.py)

### Функция форматирования: `format_activity_report()`

**Структура отчета:**
```
AKTYWNOŚĆ_DD.MM.YYYY
════════════════════════
GDZ   | Kozik  | Stukalo
────────────────────────
09–10 |      5 |      3
10–11 |      2 |      7
...
────────────────────────
Suma  |     25 |     18
════════════════════════
```

**Особенности:**
- **Группировка по часам** (9:00-16:59)
- **Показывает только активные часы** + рабочие часы
- **Суммирует все KPI** кроме KZI
- **Фиксированная структура** для двух менеджеров

**Код форматирования:**
```python
def format_activity_report(activity: dict, current_date: date) -> str:
    message = '```'
    message += f'AKTYWNOŚĆ_{current_date.strftime("%d.%m.%Y")}\n'
    message += '════════════════════════\n'
    message += 'GDZ   | Kozik  | Stukalo\n'
    message += '────────────────────────\n'
    
    # Логика показа часов
    active_hours = set()
    for h in activity.keys():
        kozik = sum(activity[h][metric]['Kozik Andrzej'] for metric in activity[h] if metric != 'KZI')
        stukalo = sum(activity[h][metric]['Stukalo Nazarii'] for metric in activity[h] if metric != 'KZI')
        if kozik > 0 or stukalo > 0:
            active_hours.add(h)
    for h in range(9, 17):  # Всегда показываем рабочие часы
        active_hours.add(h)
    
    # Формируем строки
    for h in sorted(active_hours):
        h_next = h + 1
        godz = f"{h:02d}–{h_next:02d}"
        kozik = sum(activity[h][metric]['Kozik Andrzej'] for metric in activity[h] if metric != 'KZI')
        stukalo = sum(activity[h][metric]['Stukalo Nazarii'] for metric in activity[h] if metric != 'KZI')
        message += f"{godz} |{kozik:7d} |{stukalo:7d}\n"
    
    message += '```'
    return message
```

---

## 2. 💰 Income Report (report_income.py)

### Функция форматирования: `generate_income_report()`

**Структура отчета:**
```
PRZYCHODY_MM.YYYY
👤 Kozik Andrzej:

[███████████████████████████████████]
 █  Fakt: 15 000 PLN (75%)
 ▒  Dług:  3 000 PLN (15%)
 ░  Brak:  2 000 PLN (10%)
    Plan: 20 000 PLN

👤 Stukalo Nazarii:
...
```

**Особенности:**
- **Пропорциональные прогресс-бары** (█▒░)
- **Проценты в скобках** для каждого типа
- **Выравнивание по правому краю** для сумм
- **Фиксированная длина бара** (31 символ)

**Код форматирования:**
```python
def generate_proportional_bar(fakt_percent, dlug_percent, brak_percent, total_length):
    inner_length = total_length - 2  # Убираем скобки
    fakt_blocks = int((fakt_percent / 100) * inner_length)
    dlug_blocks = int((dlug_percent / 100) * inner_length)
    brak_blocks = inner_length - fakt_blocks - dlug_blocks
    bar = '█' * fakt_blocks + '▒' * dlug_blocks + '░' * brak_blocks
    return f"[{bar}]"

def line_with_percent(label, value, percent):
    sum_str = format_int_currency(value).rjust(max_sum_len)
    percent_str = format_percent(percent)
    left_part = f" {label} {sum_str} PLN "
    padding_len = 6 - len(percent_str)
    right_part = f"{' ' * max(0, padding_len)}{percent_str}"
    return f"{left_part}{right_part}"
```

---

## 3. 📈 KPI Report (report_kpi.py)

### Функция форматирования: `send_to_telegram()` (встроенная)

**Структура отчета:**
```
KPI_DD.MM.YYYY
══════════════════════
KPI | Kozik  | Stukalo
──────────────────────
klienci
NWI |      5 |      3
WTR |      2 |      7
PSK |      1 |      4
──────────────────────
zadania
WDM |      3 |      2
PRZ |      1 |      5
...
TTL |     15 |     12
──────────────────────
zamówienia
OFW |      2 |      3
ZAM |      1 |      2
PRC |   5000 |   3000
══════════════════════
```

**Особенности:**
- **Разделы**: клиенты, задачи, заказы
- **Показывает только ненулевые значения**
- **Два формата**: дневной и месячный
- **TTL** - сумма всех задач кроме KZI

**Код форматирования:**
```python
# Дневной отчет
if report_type == 'daily':
    message = '```'
    message += f'KPI_{today.strftime("%d.%m.%Y")}\n'
    message += f'{top_line}\n'
    message += 'KPI | Kozik  | Stukalo\n'
    message += f'{mid_line}\n'
    
    # Клиенты
    message += 'klienci\n'
    client_order = ['NWI', 'WTR', 'PSK']
    for status in client_order:
        kozik_count = data['Kozik Andrzej'][status]
        stukalo_count = data['Stukalo Nazarii'][status]
        if kozik_count > 0 or stukalo_count > 0:
            message += f'{status:<3} |{kozik_count:7d} |{stukalo_count:7d}\n'
    
    # Задачи
    message += f'{mid_line}\n'
    message += 'zadania\n'
    task_order = ['WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'KNT']
    for task_type in task_order:
        kozik_count = data['Kozik Andrzej'][task_type]
        stukalo_count = data['Stukalo Nazarii'][task_type]
        if kozik_count > 0 or stukalo_count > 0:
            message += f'{task_type:<3} |{kozik_count:7d} |{stukalo_count:7d}\n'
    
    # TTL (сумма задач)
    kozik_total = sum(data['Kozik Andrzej'][t] for t in task_order if t != 'KZI')
    stukalo_total = sum(data['Stukalo Nazarii'][t] for t in task_order if t != 'KZI')
    if kozik_total > 0 or stukalo_total > 0:
        message += f'{mid_line}\n'
        message += f'TTL |{kozik_total:7d} |{stukalo_total:7d}\n'
    
    # Заказы
    message += f'{mid_line}\n'
    message += 'zamówienia\n'
    order_order = ['OFW', 'ZAM', 'PRC']
    for order_type in order_order:
        kozik_count = data['Kozik Andrzej'][order_type]
        stukalo_count = data['Stukalo Nazarii'][order_type]
        if kozik_count > 0 or stukalo_count > 0:
            message += f'{order_type:<3} |{kozik_count:7d} |{stukalo_count:7d}\n'
    
    message += f'{top_line}\n```'
```

---

## 4. 🎯 Bonus Report (report_bonus.py)

### Два подхода к форматированию:

#### A) Через ReportFormatter (новый подход)
```python
def generate_premia_report(period_type: str = 'monthly', start_date: str = None, end_date: str = None):
    # Создаем KPI движок
    kpi_engine = KPIEngine()
    
    # Генерируем KPI отчет
    report_data = kpi_engine.generate_kpi_report(period_type, start_date, end_date)
    
    # Создаем форматтер
    formatter = ReportFormatter()
    
    # Форматируем отчет
    report = formatter.format_premia_report(
        report_data['coefficients'],
        period_type,
        report_data['additional_premia'],
        report_data.get('month'),
        report_data.get('year')
    )
    return report
```

#### B) Через kpi_report.py (старый подход)
```python
def format_premia_report(coefficients: Dict, current_month: int, current_year: int, additional_premia: Dict) -> str:
    message = '```'
    message += f'PREMIA_{current_month:02d}.{current_year}\n'
    message += f'{top_line}\n'
    message += 'KPI | Kozik  | Stukalo\n'
    message += f'{mid_line}\n'
    
    # Показываем все KPI с коэффициентами
    for kpi in kpi_order:
        v1 = coefficients[managers[0]].get(kpi, 0)
        v2 = coefficients[managers[1]].get(kpi, 0)
        if v1 == 0 and v2 == 0:
            continue
        message += f'{kpi:<3} |{v1:7.2f} |{v2:7.2f}\n'
    
    # SUM, FND, PRK, PRW, TOT
    message += f'{mid_line}\n'
    sum1 = coefficients[managers[0]].get('SUM', 0)
    sum2 = coefficients[managers[1]].get('SUM', 0)
    message += f'SUM |{sum1:7.2f} |{sum2:7.2f}\n'
    
    fnd1 = int(coefficients[managers[0]].get('PRK', 0) / sum1) if sum1 else 0
    fnd2 = int(coefficients[managers[1]].get('PRK', 0) / sum2) if sum2 else 0
    message += f'FND |{fnd1:7d} |{fnd2:7d}\n'
    
    message += f'{mid_line}\n'
    prk1 = int(coefficients[managers[0]].get('PRK', 0))
    prk2 = int(coefficients[managers[1]].get('PRK', 0))
    message += f'PRK |{prk1:7d} |{prk2:7d}\n'
    
    prw1 = int(additional_premia.get(managers[0], {}).get('PRW', 0))
    prw2 = int(additional_premia.get(managers[1], {}).get('PRW', 0))
    message += f'PRW |{prw1:7d} |{prw2:7d}\n'
    
    tot1 = prk1 + prw1
    tot2 = prk2 + prw2
    message += f'TOT |{tot1:7d} |{tot2:7d}\n'
    message += f'{top_line}\n```'
    return message
```

**Структура отчета:**
```
PREMIA_MM.YYYY
══════════════════════
KPI | Kozik  | Stukalo
──────────────────────
NWI |   0.25 |   0.15
WTR |   0.30 |   0.20
...
──────────────────────
SUM |   1.25 |   0.95
FND |   8000 |   8000
──────────────────────
PRK |  10000 |   7600
PRW |   2000 |   1500
TOT |  12000 |   9100
══════════════════════
```

---

## 5. 📊 ReportFormatter (core/report_formatter.py)

### Универсальный класс для форматирования

**Методы:**
- `format_premia_report()` - отчет по премиям
- `format_activity_report()` - отчет по активности
- `format_income_report()` - отчет по доходам
- `format_status_report()` - отчет по статусам
- `format_custom_report()` - кастомный отчет

**Особенности:**
- **Поддержка разных периодов** (daily, weekly, monthly, etc.)
- **Единый стиль форматирования**
- **Гибкая настройка** через параметры
- **Использует математическое округление** [[memory:2467738]]

---

## Общие принципы форматирования

### 1. **Структура сообщений**
- Все отчеты обернуты в ``` (Markdown code blocks)
- Заголовки в формате `ТИП_ДАТА`
- Разделители: `══════════════════════` и `──────────────────────`

### 2. **Выравнивание данных**
- **Фиксированная ширина колонок** для менеджеров
- **Выравнивание по правому краю** для чисел
- **Пропорциональные элементы** (бары, проценты)

### 3. **Фильтрация данных**
- **Показ только ненулевых значений** в большинстве отчетов
- **Исключение KZI** из сумм в Activity и KPI
- **Условное отображение** разделов

### 4. **Специальные элементы**
- **Прогресс-бары** (█▒░) в Income отчете
- **Динамические индикаторы** (▲▼) в Status отчете
- **Проценты в скобках** для наглядности

### 5. **Обработка ошибок**
- **Fallback значения** при отсутствии данных
- **Логирование ошибок** форматирования
- **Graceful degradation** при проблемах с данными

---

## Сравнение подходов

| Отчет | Подход | Сложность | Гибкость | Переиспользование |
|-------|--------|-----------|----------|-------------------|
| Activity | Прямое форматирование | Низкая | Низкая | Низкое |
| Income | Прямое форматирование | Высокая | Средняя | Низкое |
| KPI | Прямое форматирование | Средняя | Низкая | Низкое |
| Bonus | Универсальный форматтер | Средняя | Высокая | Высокое |
| Status | Сложное форматирование | Очень высокая | Высокая | Низкое |

**Рекомендация:** Унифицировать все отчеты через ReportFormatter для консистентности и переиспользования кода.
