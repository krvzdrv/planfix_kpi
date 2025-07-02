#!/usr/bin/env python3
"""
Точка входа для автоматического запуска премиального отчёта (GitHub Actions)
"""
from core.kpi_data import get_kpi_metrics, get_actual_kpi_values, calculate_kpi_coefficients
from core.kpi_report import format_premia_report
from datetime import datetime

# TODO: добавить отправку отчёта через Telegram API или email

def main():
    now = datetime.now()
    current_month = now.month
    current_year = now.year
    metrics = get_kpi_metrics(current_month, current_year)
    # Здесь должны быть start_date, end_date для периода отчёта
    # Например, за месяц:
    start_date = f"{current_year}-{current_month:02d}-01 00:00:00"
    # end_date = ...
    actual = get_actual_kpi_values(start_date, None)  # TODO: корректный end_date
    coeffs = calculate_kpi_coefficients(metrics, actual)
    report = format_premia_report(coeffs, current_month, current_year, additional_premia={})
    print(report)

if __name__ == "__main__":
    main() 