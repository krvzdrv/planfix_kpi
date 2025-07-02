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
        # Get current month and year
        current_date = date.today()
        current_month = current_date.month
        current_year = current_date.year
        # Get start and end dates for the current month
        start_date = f"{current_year}-{current_month:02d}-01"
        if current_month == 12:
            end_date = f"{current_year + 1}-01-01"
        else:
            end_date = f"{current_year}-{current_month + 1:02d}-01"
        # Get KPI metrics
        metrics = get_kpi_metrics(current_month, current_year)
        if not metrics:
            logger.error("No KPI metrics found for the current month")
            return
        # Get actual KPI values
        actual_values = get_actual_kpi_values(start_date, end_date)
        # Calculate coefficients
        coefficients = calculate_kpi_coefficients(metrics, actual_values)
        # Get additional premia
        additional_premia = get_additional_premia(start_date, end_date)
        # Format and send report
        report = format_premia_report(coefficients, current_month, current_year, additional_premia)
        send_to_telegram(report)
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        raise

if __name__ == "__main__":
    main() 