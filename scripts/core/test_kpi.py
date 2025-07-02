import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from core.kpi_data import calculate_kpi_coefficients
from core.kpi_report import format_premia_report

class TestKPI(unittest.TestCase):
    def test_calculate_kpi_coefficients(self):
        metrics = {
            'NWI': {'plan': 10, 'weight': 0.2},
            'WTR': {'plan': 20, 'weight': 0.2},
            'PSK': {'plan': 30, 'weight': 0.2},
            'premia': 1000
        }
        actual = {
            'Manager1': {'NWI': 10, 'WTR': 25, 'PSK': 15},
            'Manager2': {'NWI': 5, 'WTR': 20, 'PSK': 30}
        }
        coeffs = calculate_kpi_coefficients(metrics, actual)
        # NWI: факт=10, план=10, вес=0.2 => 0.2
        # WTR: факт=25, план=20, вес=0.2 => 0.2 (ограничено планом)
        # PSK: факт=15, план=30, вес=0.2 => 0.1
        self.assertAlmostEqual(float(coeffs['Manager1']['NWI']), 0.2)
        self.assertAlmostEqual(float(coeffs['Manager1']['WTR']), 0.2)
        self.assertAlmostEqual(float(coeffs['Manager1']['PSK']), 0.1)
        self.assertAlmostEqual(float(coeffs['Manager1']['SUM']), 0.5)
        self.assertAlmostEqual(float(coeffs['Manager1']['PRK']), 500)

    def test_format_premia_report(self):
        coeffs = {
            'Kozik Andrzej': {'NWI': 0.2, 'WTR': 0.2, 'PSK': 0.1, 'SUM': 0.5, 'PRK': 500},
            'Stukalo Nazarii': {'NWI': 0.1, 'WTR': 0.2, 'PSK': 0.2, 'SUM': 0.5, 'PRK': 500}
        }
        additional = {'Kozik Andrzej': {'PRW': 100}, 'Stukalo Nazarii': {'PRW': 200}}
        report = format_premia_report(coeffs, 7, 2024, additional)
        self.assertIn('PREMIA_07.2024', report)
        self.assertIn('KPI | Kozik', report)
        self.assertIn('PRW', report)
        self.assertIn('TOT', report)

if __name__ == "__main__":
    unittest.main() 