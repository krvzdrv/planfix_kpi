"""
Обновленный отчет по премиям с использованием централизованной архитектуры KPI
"""
import os
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
import sys

# Добавляем путь к скриптам
sys.path.insert(0, os.path.dirname(__file__))

from core.kpi_engine import KPIEngine
from core.report_formatter import ReportFormatter

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# Telegram настройки
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def send_to_telegram(message: str):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("Telegram token or chat ID not configured")
        return
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        logger.info("Message sent to Telegram successfully")
    except Exception as e:
        logger.error(f"Failed to send message to Telegram: {e}")

def generate_premia_report(period_type: str = 'monthly', start_date: str = None, end_date: str = None):
    """Генерирует отчет по премиям для указанного периода"""
    try:
        logger.info(f"Generating premia report for period: {period_type}")
        
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
            report_data['additional_premia']
        )
        
        logger.info(f"Premia report generated successfully for {period_type}")
        return report
        
    except Exception as e:
        error_msg = f"❌ Ошибка при генерации отчета за {period_type}: {str(e)}"
        logger.error(f"Error generating premia report: {e}")
        return error_msg

def main():
    """Основная функция"""
    try:
        logger.info("Starting premia report generation")
        
        # Генерируем отчет за текущий месяц
        report = generate_premia_report('monthly')
        
        # Отправляем в Telegram
        send_to_telegram(report)
        
        logger.info("Premia report completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        send_to_telegram(f"❌ Ошибка при генерации отчета: {str(e)}")
        raise

if __name__ == "__main__":
    main() 