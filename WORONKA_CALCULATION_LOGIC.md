# Логика расчета значений в отчете WORONKA

## Разбор примера: `WTR ██     40  +2 ▲   [+2/-0] 10%`

### 📊 **Структура строки:**
```
WTR ██     40  +2 ▲   [+2/-0] 10%
│   │      │   │  │   │      │
│   │      │   │  │   │      └─ Процент от общей суммы
│   │      │   │  │   └─ Дневной приток/отток [IN/OUT]
│   │      │   │  └─ Индикатор направления изменения
│   │      │   └─ Чистое изменение (net)
│   │      └─ Текущее количество клиентов
│   └─ Пропорциональный бар
└─ Статус клиента
```

---

## 🔢 **Расчет каждого значения:**

### 1. **CURRENT (40)** - Текущее количество
**Источник:** `planfix_clients.status_wspolpracy`

**Логика:**
```sql
SELECT status_wspolpracy, data_ostatniego_zamowienia 
FROM planfix_clients 
WHERE menedzer = 'Stukalo Nazarii' 
  AND is_deleted = false 
  AND status_wspolpracy IS NOT NULL
```

**Обработка:**
- `status_wspolpracy = 'W trakcie'` → `WTR`
- Подсчет всех клиентов с этим статусом на сегодня
- **Результат:** 40 клиентов в статусе "W trakcie"

### 2. **NET (+2)** - Чистое изменение
**Логика для WTR:**
```python
# Для статусов кроме STL/NAK - используется дневной приток
diff = inflow  # +2
```

**Объяснение:**
- WTR не входит в STL/NAK, поэтому используется **дневной приток**
- `+2` означает, что сегодня 2 клиента перешли в статус "W trakcie"

### 3. **DIRECTION (▲)** - Индикатор направления
**Логика:**
```python
direction = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
```

**Результат:**
- `diff = +2` (положительное) → `▲` (рост)
- `diff = -5` (отрицательное) → `▼` (снижение)  
- `diff = 0` (ноль) → `-` (без изменений)

### 4. **INFLOW/OUTFLOW ([+2/-0])** - Дневной приток/отток
**Источник:** `planfix_clients.data_dodania_do_w_trakcie`

#### **INFLOW (+2)** - Дневной приток
**Логика:**
```sql
SELECT COUNT(*) 
FROM planfix_clients 
WHERE menedzer = 'Stukalo Nazarii'
  AND data_dodania_do_w_trakcie IS NOT NULL 
  AND data_dodania_do_w_trakcie != ''
  AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') = '2024-10-19'
  AND is_deleted = false
```

**Объяснение:**
- Считаем клиентов, которые **сегодня** перешли в статус "W trakcie"
- **Результат:** 2 клиента добавились сегодня

#### **OUTFLOW (-0)** - Дневной отток
**Логика:**
```sql
SELECT COUNT(*) 
FROM planfix_clients 
WHERE menedzer = 'Stukalo Nazarii'
  AND data_dodania_do_w_trakcie IS NOT NULL 
  AND data_dodania_do_w_trakcie != ''
  AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') < '2024-10-19'
  AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') >= '2024-10-18'
  AND is_deleted = false
```

**Объяснение:**
- Считаем клиентов, которые **вчера** были в статусе "W trakcie", но **сегодня** уже не в нем
- **Результат:** 0 клиентов ушло из статуса

### 5. **PERCENT (10%)** - Процент от общей суммы
**Логика:**
```python
total_sum = 40 + 9 + 4 + 8 + 18 + 17 + 9 + 7 + 0 = 112
percentage = (40 / 112) * 100 = 35.7% → 36%
```

**Объяснение:**
- WTR составляет 40 из 112 общих клиентов
- **Результат:** 36% от общего количества

---

## 🔄 **Особенности для разных статусов:**

### **STL/NAK (Stali klienci/Nieaktywni)**
**Особая логика:**
```python
if status in ['STL', 'NAK']:
    # Динамика для STL/NAK - чистая разница со вчера
    prev_count = previous_stl_nak.get(status, 0)
    diff = curr_count - prev_count
else:
    # Динамика для остальных - дневной приток
    diff = inflow
```

**Объяснение:**
- **STL/NAK** рассчитываются на основе **истории** (сравнение со вчера)
- **Остальные статусы** рассчитываются на основе **дневного притока**

### **STL vs NAK**
**Логика разделения:**
```python
if status_clean == 'Stali klienci':
    days_diff = (today - last_order_date).days
    short_status = 'STL' if days_diff <= 30 else 'NAK'
```

**Объяснение:**
- **STL** - клиенты с заказом ≤ 30 дней назад
- **NAK** - клиенты с заказом > 30 дней назад

---

## 📋 **Сопоставление полей базы данных:**

| Статус | Поле даты входа | Поле даты выхода |
|--------|-----------------|------------------|
| NWI | `data_dodania_do_nowi` | - |
| WTR | `data_dodania_do_w_trakcie` | - |
| PSK | `data_dodania_do_perspektywiczni` | - |
| PIZ | `data_pierwszego_zamowienia` | - |
| REZ | `data_dodania_do_rezygnacja` | - |
| BRK | `data_dodania_do_brak_kontaktu` | - |
| ARC | `data_dodania_do_archiwum` | - |
| STL/NAK | - | `data_ostatniego_zamowienia` |

---

## 🎯 **Итоговая логика:**

### **Для WTR в примере:**
1. **CURRENT (40)** - всего клиентов в статусе "W trakcie"
2. **NET (+2)** - дневной приток (2 клиента добавились сегодня)
3. **DIRECTION (▲)** - рост (положительное изменение)
4. **INFLOW (+2)** - 2 клиента перешли в статус сегодня
5. **OUTFLOW (-0)** - 0 клиентов ушло из статуса сегодня
6. **PERCENT (10%)** - доля от общего количества клиентов

### **Формула NET для WTR:**
```
NET = INFLOW - OUTFLOW = 2 - 0 = +2
```

### **Формула NET для STL/NAK:**
```
NET = CURRENT_TODAY - CURRENT_YESTERDAY
```

Эта логика обеспечивает точное отслеживание динамики клиентской базы по каждому статусу! 📈
