"""
Универсальный модуль для форматирования отчетов
Поддерживает разные типы отчетов и периоды
"""
from typing import Dict, Any, List
from datetime import datetime
from .kpi_utils import math_round

class ReportFormatter:
    """Универсальный форматтер для отчетов"""
    
    def __init__(self):
        self.kpi_order = [
            'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT',
            'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC'
        ]
        self.managers = ['Kozik Andrzej', 'Stukalo Nazarii']
    
    def format_premia_report(self, coefficients: Dict, period_type: str, additional_premia: Dict = None) -> str:
        """Форматирует отчет по премиям"""
        # Определяем заголовок в зависимости от периода
        period_titles = {
            'daily': 'ДЕНЬ',
            'weekly': 'НЕДЕЛЯ', 
            'monthly': 'МЕСЯЦ',
            'quarterly': 'КВАРТАЛ',
            'yearly': 'ГОД',
            'previous_month': 'ПРЕДЫДУЩИЙ МЕСЯЦ'
        }
        
        title = period_titles.get(period_type, period_type.upper())
        today = datetime.now()
        
        top_line = '══════════════════════'
        mid_line = '──────────────────────'
        
        message = '```\n'
        message += f'PREMIA_{title}_{today.strftime("%m.%Y")}\n'
        message += f'{top_line}\n'
        message += 'KPI | Kozik  | Stukalo\n'
        message += f'{mid_line}\n'
        
        # Добавляем KPI показатели
        for kpi in self.kpi_order:
            v1 = coefficients[self.managers[0]].get(kpi, 0)
            v2 = coefficients[self.managers[1]].get(kpi, 0)
            if v1 == 0 and v2 == 0:
                continue
            message += f'{kpi:<3} |{v1:7.2f} |{v2:7.2f}\n'
        
        message += f'{mid_line}\n'
        
        # Добавляем SUM
        sum1 = coefficients[self.managers[0]].get('SUM', 0)
        sum2 = coefficients[self.managers[1]].get('SUM', 0)
        message += f'SUM |{sum1:7.2f} |{sum2:7.2f}\n'
        
        # Добавляем FND (базовая премия)
        fnd1 = int(coefficients[self.managers[0]].get('PRK', 0) / sum1) if sum1 else 0
        fnd2 = int(coefficients[self.managers[1]].get('PRK', 0) / sum2) if sum2 else 0
        message += f'FND |{fnd1:7d} |{fnd2:7d}\n'
        
        message += f'{mid_line}\n'
        
        # Добавляем PRK (KPI премия)
        prk1 = int(coefficients[self.managers[0]].get('PRK', 0))
        prk2 = int(coefficients[self.managers[1]].get('PRK', 0))
        message += f'PRK |{prk1:7d} |{prk2:7d}\n'
        
        # Добавляем PRW (дополнительная премия)
        if additional_premia:
            prw1 = int(additional_premia.get(self.managers[0], {}).get('PRW', 0))
            prw2 = int(additional_premia.get(self.managers[1], {}).get('PRW', 0))
            message += f'PRW |{prw1:7d} |{prw2:7d}\n'
        
        # Добавляем TOT (общая премия)
        tot1 = prk1 + (prw1 if additional_premia else 0)
        tot2 = prk2 + (prw2 if additional_premia else 0)
        message += f'TOT |{tot1:7d} |{tot2:7d}\n'
        
        message += f'{top_line}\n```'
        return message
    
    def format_activity_report(self, data: Dict, period_type: str) -> str:
        """Форматирует отчет по активности"""
        period_titles = {
            'daily': 'ДЕНЬ',
            'weekly': 'НЕДЕЛЯ', 
            'monthly': 'МЕСЯЦ',
            'quarterly': 'КВАРТАЛ',
            'yearly': 'ГОД'
        }
        
        title = period_titles.get(period_type, period_type.upper())
        today = datetime.now()
        
        message = f'📊 *АКТИВНОСТЬ {title}* {today.strftime("%d.%m.%Y")}\n\n'
        
        for manager in self.managers:
            if manager in data:
                manager_data = data[manager]
                message += f'👤 *{manager}*\n'
                
                # Задачи
                if any(manager_data.get(kpi, 0) > 0 for kpi in ['WDM', 'PRZ', 'ZKL', 'SPT', 'TTL']):
                    message += '📋 *Задачи:*\n'
                    task_kpis = ['WDM', 'PRZ', 'ZKL', 'SPT', 'TTL']
                    for kpi in task_kpis:
                        value = manager_data.get(kpi, 0)
                        if value > 0:
                            message += f'  • {kpi}: {value}\n'
                
                # Клиенты
                if any(manager_data.get(kpi, 0) > 0 for kpi in ['NWI', 'WTR', 'PSK']):
                    message += '👥 *Клиенты:*\n'
                    client_kpis = ['NWI', 'WTR', 'PSK']
                    for kpi in client_kpis:
                        value = manager_data.get(kpi, 0)
                        if value > 0:
                            message += f'  • {kpi}: {value}\n'
                
                # Заказы
                if manager_data.get('OFW', 0) > 0:
                    message += f'📄 *Предложения:* {manager_data.get("OFW", 0)}\n'
                
                message += '\n'
        
        return message
    
    def format_income_report(self, data: Dict, period_type: str) -> str:
        """Форматирует отчет по доходу"""
        period_titles = {
            'daily': 'ДЕНЬ',
            'weekly': 'НЕДЕЛЯ', 
            'monthly': 'МЕСЯЦ',
            'quarterly': 'КВАРТАЛ',
            'yearly': 'ГОД'
        }
        
        title = period_titles.get(period_type, period_type.upper())
        today = datetime.now()
        
        message = f'💰 *ДОХОД {title}* {today.strftime("%d.%m.%Y")}\n\n'
        
        total_income = 0
        total_orders = 0
        
        for manager in self.managers:
            if manager in data:
                manager_data = data[manager]
                income = manager_data.get('PRC', 0)
                orders = manager_data.get('ZAM', 0)
                
                if income > 0 or orders > 0:
                    message += f'👤 *{manager}*\n'
                    if orders > 0:
                        message += f'  📦 Заказов: {orders}\n'
                    if income > 0:
                        message += f'  💰 Доход: {income:,.0f} PLN\n'
                    message += '\n'
                    
                    total_income += income
                    total_orders += orders
        
        if total_income > 0 or total_orders > 0:
            message += f'📊 *ИТОГО:*\n'
            message += f'  📦 Заказов: {total_orders}\n'
            message += f'  💰 Доход: {total_income:,.0f} PLN\n'
        
        return message
    
    def format_status_report(self, data: Dict, period_type: str) -> str:
        """Форматирует отчет по статусам клиентов"""
        period_titles = {
            'daily': 'ДЕНЬ',
            'weekly': 'НЕДЕЛЯ', 
            'monthly': 'МЕСЯЦ',
            'quarterly': 'КВАРТАЛ',
            'yearly': 'ГОД'
        }
        
        title = period_titles.get(period_type, period_type.upper())
        today = datetime.now()
        
        message = f'📈 *СТАТУСЫ КЛИЕНТОВ {title}* {today.strftime("%d.%m.%Y")}\n\n'
        
        status_names = {
            'NWI': 'Новые',
            'WTR': 'В работе', 
            'PSK': 'Перспективные'
        }
        
        for manager in self.managers:
            if manager in data:
                manager_data = data[manager]
                has_data = any(manager_data.get(kpi, 0) > 0 for kpi in status_names.keys())
                
                if has_data:
                    message += f'👤 *{manager}*\n'
                    for kpi, name in status_names.items():
                        value = manager_data.get(kpi, 0)
                        if value > 0:
                            message += f'  • {name}: {value}\n'
                    message += '\n'
        
        return message
    
    def format_custom_report(self, data: Dict, title: str, kpi_list: List[str] = None) -> str:
        """Форматирует кастомный отчет"""
        if kpi_list is None:
            kpi_list = self.kpi_order
        
        message = f'📊 *{title}*\n\n'
        
        for manager in self.managers:
            if manager in data:
                manager_data = data[manager]
                has_data = any(manager_data.get(kpi, 0) > 0 for kpi in kpi_list)
                
                if has_data:
                    message += f'👤 *{manager}*\n'
                    for kpi in kpi_list:
                        value = manager_data.get(kpi, 0)
                        if value > 0:
                            message += f'  • {kpi}: {value}\n'
                    message += '\n'
        
        return message 