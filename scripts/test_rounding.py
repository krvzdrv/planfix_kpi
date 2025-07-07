#!/usr/bin/env python3
"""
Тестовый скрипт для проверки округления
"""
import math
from decimal import Decimal, ROUND_HALF_UP
from core.kpi_utils import math_round

def test_rounding():
    """Тестируем различные случаи округления"""
    
    # Тестовые значения
    test_cases = [
        (0.169333, 2),  # Должно быть 0.17
        (0.165, 2),     # Должно быть 0.17
        (0.164, 2),     # Должно быть 0.16
        (0.5, 0),       # Должно быть 1
        (0.4, 0),       # Должно быть 0
        (1.5, 0),       # Должно быть 2
    ]
    
    print("=== Тест округления ===")
    print("Значение | Ожидаемое | math_round | round() | Разница")
    print("-" * 50)
    
    for value, decimals in test_cases:
        expected = round(value + 0.5 * (10 ** (-decimals - 1)), decimals)
        our_result = math_round(value, decimals)
        python_round = round(value, decimals)
        
        print(f"{value:8.6f} | {expected:9.6f} | {our_result:9.6f} | {python_round:7.6f} | {'✓' if abs(our_result - expected) < 0.0001 else '✗'}")
    
    # Тест с Decimal
    print("\n=== Тест с Decimal ===")
    decimal_cases = [
        (Decimal('0.169333'), 2),
        (Decimal('0.165'), 2),
        (Decimal('0.164'), 2),
    ]
    
    for value, decimals in decimal_cases:
        expected = round(float(value) + 0.5 * (10 ** (-decimals - 1)), decimals)
        our_result = math_round(value, decimals)
        python_round = round(float(value), decimals)
        
        print(f"{value:8.6f} | {expected:9.6f} | {our_result:9.6f} | {python_round:7.6f} | {'✓' if abs(float(our_result) - expected) < 0.0001 else '✗'}")

def test_kpi_calculation():
    """Тестируем расчет KPI как в реальном случае"""
    print("\n=== Тест расчета KPI ===")
    
    # Данные как в вашем примере
    actual = 254
    plan = 300
    weight = 0.2
    
    # Расчет коэффициента
    coefficient = (actual / plan) * weight
    print(f"Факт: {actual}")
    print(f"План: {plan}")
    print(f"Вес: {weight}")
    print(f"Коэффициент (без округления): {coefficient}")
    print(f"Коэффициент (math_round): {math_round(coefficient, 2)}")
    print(f"Коэффициент (round): {round(coefficient, 2)}")
    print(f"Коэффициент (банковское): {round(coefficient, 2)}")

def test_decimal_calculation():
    """Тестируем расчет с Decimal как в реальном коде"""
    print("\n=== Тест расчета с Decimal ===")
    
    # Данные как в вашем примере, но с Decimal
    actual = Decimal('254')
    plan = Decimal('300')
    weight = Decimal('0.2')
    
    # Расчет коэффициента как в реальном коде
    used_value = actual  # Предполагаем, что это не CAPPED_KPI
    coefficient_decimal = (used_value / plan) * weight
    coefficient_float = float(coefficient_decimal)
    
    print(f"Факт: {actual}")
    print(f"План: {plan}")
    print(f"Вес: {weight}")
    print(f"Коэффициент (Decimal): {coefficient_decimal}")
    print(f"Коэффициент (float): {coefficient_float}")
    print(f"Коэффициент (math_round float): {math_round(coefficient_float, 2)}")
    print(f"Коэффициент (math_round Decimal): {math_round(coefficient_decimal, 2)}")
    print(f"Коэффициент (round): {round(coefficient_float, 2)}")

if __name__ == "__main__":
    test_rounding()
    test_kpi_calculation()
    test_decimal_calculation() 