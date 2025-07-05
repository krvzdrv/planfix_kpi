import os
import sys
import logging
from datetime import datetime, date
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

# Import functions from telegram_bot.py
from telegram_bot import generate_premia_report_for_month

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

def test_current_month_report():
    """Test generating report for current month."""
    try:
        current_date = date.today()
        current_month = current_date.month
        current_year = current_date.year
        
        logger.info(f"Testing current month report for {current_month:02d}.{current_year}")
        
        report = generate_premia_report_for_month(current_month, current_year)
        
        print("\n" + "="*50)
        print("ОТЧЕТ ЗА ТЕКУЩИЙ МЕСЯЦ")
        print("="*50)
        print(report)
        print("="*50)
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing current month report: {e}")
        print(f"❌ Ошибка: {e}")
        return False

def test_previous_month_report():
    """Test generating report for previous month."""
    try:
        current_date = date.today()
        
        # Calculate previous month
        if current_date.month == 1:
            previous_month = 12
            previous_year = current_date.year - 1
        else:
            previous_month = current_date.month - 1
            previous_year = current_date.year
        
        logger.info(f"Testing previous month report for {previous_month:02d}.{previous_year}")
        
        report = generate_premia_report_for_month(previous_month, previous_year)
        
        print("\n" + "="*50)
        print("ОТЧЕТ ЗА ПРЕДЫДУЩИЙ МЕСЯЦ")
        print("="*50)
        print(report)
        print("="*50)
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing previous month report: {e}")
        print(f"❌ Ошибка: {e}")
        return False

def main():
    """Main test function."""
    print("🧪 Тестирование команд отчета по премии")
    print("="*50)
    
    # Test current month
    success1 = test_current_month_report()
    
    # Test previous month
    success2 = test_previous_month_report()
    
    # Summary
    print("\n" + "="*50)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("="*50)
    print(f"Текущий месяц: {'✅ Успешно' if success1 else '❌ Ошибка'}")
    print(f"Предыдущий месяц: {'✅ Успешно' if success2 else '❌ Ошибка'}")
    
    if success1 and success2:
        print("\n🎉 Все тесты прошли успешно!")
        print("Бот готов к использованию.")
        print("\nКоманды для использования в Telegram:")
        print("/premia_current - отчет за текущий месяц")
        print("/premia_previous - отчет за предыдущий месяц")
    else:
        print("\n⚠️ Некоторые тесты не прошли. Проверьте логи.")

if __name__ == "__main__":
    main() 