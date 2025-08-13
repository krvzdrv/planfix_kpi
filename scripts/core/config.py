"""
Конфигурация KPI менеджеров
Содержит информацию о менеджерах для расчета KPI показателей
"""

# Конфигурация менеджеров для KPI расчетов
# Каждый менеджер должен иметь:
# - planfix_user_name: имя пользователя в Planfix (как отображается в системе)
# - planfix_user_id: ID пользователя в Planfix (числовой идентификатор)

MANAGERS_KPI = [
    {
        'planfix_user_name': 'Kozik Andrzej',
        'planfix_user_id': 853159  # Реальный ID из Planfix
    },
    {
        'planfix_user_name': 'Stukalo Nazarii', 
        'planfix_user_id': 945243  # Реальный ID из Planfix
    }
]

# Проверка конфигурации
if not MANAGERS_KPI:
    raise ValueError("MANAGERS_KPI list cannot be empty")

# Проверяем, что у каждого менеджера есть необходимые поля
for i, manager in enumerate(MANAGERS_KPI):
    if 'planfix_user_name' not in manager:
        raise ValueError(f"Manager {i} missing 'planfix_user_name' field")
    if 'planfix_user_id' not in manager:
        raise ValueError(f"Manager {i} missing 'planfix_user_id' field")
    if not manager['planfix_user_name']:
        raise ValueError(f"Manager {i} has empty 'planfix_user_name'")
    if not manager['planfix_user_id']:
        raise ValueError(f"Manager {i} has empty 'planfix_user_id'")

print(f"✅ KPI configuration loaded: {len(MANAGERS_KPI)} managers configured")
for manager in MANAGERS_KPI:
    print(f"  - {manager['planfix_user_name']} (ID: {manager['planfix_user_id']})")
