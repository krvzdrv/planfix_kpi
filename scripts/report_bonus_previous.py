import logging
from datetime import date
from dotenv import load_dotenv
from core.kpi_data import get_kpi_metrics, get_actual_kpi_values, calculate_kpi_coefficients, get_additional_premia
from core.kpi_report import format_premia_report
import os
import requests
from config import MANAGERS_KPI

# Load environment variables from .env file
load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

logger = logging.getLogger(__name__)


def send_to_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        logger.info("Message sent successfully to Telegram")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message to Telegram: {e}")
        raise

def main():
    try:
        # Get previous month and year
        current_date = date.today()
        
        # Calculate previous month
        if current_date.month == 1:
            previous_month = 12
            previous_year = current_date.year - 1
        else:
            previous_month = current_date.month - 1
            previous_year = current_date.year
        
        logger.info(f"Generating premia report for {previous_month:02d}.{previous_year}")
        
        # Get start and end dates for the previous month
        start_date = f"{previous_year}-{previous_month:02d}-01"
        if previous_month == 12:
            end_date = f"{previous_year + 1}-01-01"
        else:
            end_date = f"{previous_year}-{previous_month + 1:02d}-01"
        
        # Get KPI metrics
        metrics = get_kpi_metrics(previous_month, previous_year)
        if not metrics:
            logger.error(f"No KPI metrics found for {previous_month:02d}.{previous_year}")
            send_to_telegram(f"❌ Нет данных KPI для {previous_month:02d}.{previous_year}")
            return
        
        # Get actual KPI values
        actual_values = get_actual_kpi_values(start_date, end_date)
        
        # Calculate coefficients
        coefficients = calculate_kpi_coefficients(metrics, actual_values)
        
        # Get additional premia
        additional_premia = get_additional_premia(start_date, end_date)
        
        # Format and send report
        report = format_premia_report(coefficients, previous_month, previous_year, additional_premia)
        send_to_telegram(report)
        
        logger.info(f"Successfully generated and sent premia report for {previous_month:02d}.{previous_year}")
        
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        send_to_telegram(f"❌ Ошибка при генерации отчета за {previous_month:02d}.{previous_year}: {str(e)}")
        raise

if __name__ == "__main__":
    main() 