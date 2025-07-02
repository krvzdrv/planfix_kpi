"""
Модуль для формирования текстовых отчетов по KPI (Telegram/Markdown)
"""
from typing import Dict

def format_premia_report(coefficients: Dict, current_month: int, current_year: int, additional_premia: Dict) -> str:
    kpi_order = [
        'NWI', 'WTR', 'PSK', 'WDM', 'PRZ', 'KZI', 'ZKL', 'SPT', 'MAT',
        'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'TTL', 'OFW', 'ZAM', 'PRC'
    ]
    managers = ['Kozik Andrzej', 'Stukalo Nazarii']
    top_line = '══════════════════════'
    mid_line = '──────────────────────'
    message = '```'
    message += f'PREMIA_{current_month:02d}.{current_year}\n'
    message += f'{top_line}\n'
    message += 'KPI | Kozik  | Stukalo\n'
    message += f'{mid_line}\n'
    for kpi in kpi_order:
        v1 = coefficients[managers[0]].get(kpi, 0)
        v2 = coefficients[managers[1]].get(kpi, 0)
        if v1 == 0 and v2 == 0:
            continue
        message += f'{kpi:<3} |{v1:7.2f} |{v2:7.2f}\n'
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