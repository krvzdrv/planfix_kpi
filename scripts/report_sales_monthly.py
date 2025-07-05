import os
import sys
import logging
from datetime import datetime, timedelta
import psycopg2
from decimal import Decimal
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

# --- Database Settings ---
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# --- Telegram Settings ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SALES_CHAT_ID = "-1001866680518"  # ID группы для отчетов о продажах

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def format_currency(amount):
    """Format amount as currency."""
    return f"{amount:,.2f} PLN"

def format_int_currency(value):
    """Format integer currency value."""
    return f'{int(value):,}'.replace(',', ' ')

def _parse_netto_pln(value):
    """Преобразует текстовое значение wartosc_netto_pln в float. Возвращает 0.0 при ошибке."""
    if value is None:
        return 0.0
    try:
        import re
        cleaned = re.sub(r'[^0-9,.-]', '', str(value)).replace(',', '.').replace(' ', '')
        return float(cleaned)
    except Exception:
        return 0.0

def get_monthly_revenue_data(conn, start_month, start_year, end_month, end_year):
    """Получает данные о выручке по месяцам с даты подтверждения заказа."""
    try:
        monthly_data = {}
        
        # Генерируем список всех месяцев от start до end
        current_date = datetime(start_year, start_month, 1)
        end_date = datetime(end_year, end_month, 1)
        
        while current_date <= end_date:
            month = current_date.month
            year = current_date.year
            
            # Получаем первый и последний день месяца
            first_day = datetime(year, month, 1)
            if month == 12:
                last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(year, month + 1, 1) - timedelta(days=1)

            first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
            last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')

            with conn.cursor() as cur:
                # Получаем выручку по дате подтверждения заказа
                cur.execute("""
                    SELECT 
                        COUNT(*) as order_count,
                        SUM(CAST(REPLACE(wartosc_netto_pln, ',', '.') AS DECIMAL)) as total_revenue
                    FROM planfix_orders
                    WHERE 
                        data_potwierdzenia_zamowienia IS NOT NULL 
                        AND data_potwierdzenia_zamowienia != ''
                        AND TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') >= %s::timestamp 
                        AND TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') <= %s::timestamp
                        AND is_deleted = false
                        AND wartosc_netto_pln IS NOT NULL
                        AND TRIM(wartosc_netto_pln) != ''
                        AND wartosc_netto_pln != '0,00'
                """, (first_day_str, last_day_str))
                
                result = cur.fetchone()
                order_count = result[0] if result[0] else 0
                total_revenue = result[1] if result[1] else 0
                
                monthly_data[f"{year}-{month:02d}"] = {
                    'month': month,
                    'year': year,
                    'order_count': order_count,
                    'total_revenue': total_revenue
                }
            
            # Переходим к следующему месяцу
            if month == 12:
                current_date = datetime(year + 1, 1, 1)
            else:
                current_date = datetime(year, month + 1, 1)

        return monthly_data
    except Exception as e:
        logger.error(f"Error getting monthly revenue data: {e}")
        return {}

def get_monthly_clients_data(conn, start_month, start_year, end_month, end_year):
    """Получает данные о новых клиентах по месяцам."""
    try:
        monthly_data = {}
        
        # Генерируем список всех месяцев от start до end
        current_date = datetime(start_year, start_month, 1)
        end_date = datetime(end_year, end_month, 1)
        
        while current_date <= end_date:
            month = current_date.month
            year = current_date.year
            
            # Получаем первый и последний день месяца
            first_day = datetime(year, month, 1)
            if month == 12:
                last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(year, month + 1, 1) - timedelta(days=1)

            first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
            last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')

            with conn.cursor() as cur:
                # Получаем количество новых клиентов
                cur.execute("""
                    SELECT 
                        COUNT(*) as new_clients_count
                    FROM planfix_clients
                    WHERE 
                        created_date >= %s::timestamp 
                        AND created_date <= %s::timestamp
                        AND is_deleted = false
                """, (first_day_str, last_day_str))
                
                result = cur.fetchone()
                new_clients_count = result[0] if result[0] else 0
                
                month_key = f"{year}-{month:02d}"
                if month_key not in monthly_data:
                    monthly_data[month_key] = {}
                
                monthly_data[month_key]['new_clients_count'] = new_clients_count
            
            # Переходим к следующему месяцу
            if month == 12:
                current_date = datetime(year + 1, 1, 1)
            else:
                current_date = datetime(year, month + 1, 1)

        return monthly_data
    except Exception as e:
        logger.error(f"Error getting monthly clients data: {e}")
        return {}

def get_monthly_tasks_data(conn, start_month, start_year, end_month, end_year):
    """Получает данные о задачах по месяцам."""
    try:
        monthly_data = {}
        
        # Генерируем список всех месяцев от start до end
        current_date = datetime(start_year, start_month, 1)
        end_date = datetime(end_year, end_month, 1)
        
        while current_date <= end_date:
            month = current_date.month
            year = current_date.year
            
            # Получаем первый и последний день месяца
            first_day = datetime(year, month, 1)
            if month == 12:
                last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(year, month + 1, 1) - timedelta(days=1)

            first_day_str = first_day.strftime('%Y-%m-%d %H:%M:%S')
            last_day_str = last_day.strftime('%Y-%m-%d %H:%M:%S')

            with conn.cursor() as cur:
                # Получаем количество выполненных задач
                cur.execute("""
                    SELECT 
                        COUNT(*) as completed_tasks_count
                    FROM planfix_tasks
                    WHERE 
                        data_zakonczenia_zadania >= %s::timestamp 
                        AND data_zakonczenia_zadania <= %s::timestamp
                        AND is_deleted = false
                        AND TRIM(SPLIT_PART(title, ' /', 1)) IN (
                            'Nawiązać pierwszy kontakt',
                            'Przeprowadzić pierwszą rozmowę telefoniczną',
                            'Zadzwonić do klienta',
                            'Przeprowadzić spotkanie',
                            'Wysłać materiały',
                            'Odpowiedzieć na pytanie techniczne',
                            'Zapisać na media społecznościowe',
                            'Opowiedzieć o nowościach',
                            'Zebrać opinie',
                            'Przywrócić klienta'
                        )
                """, (first_day_str, last_day_str))
                
                result = cur.fetchone()
                completed_tasks_count = result[0] if result[0] else 0
                
                month_key = f"{year}-{month:02d}"
                if month_key not in monthly_data:
                    monthly_data[month_key] = {}
                
                monthly_data[month_key]['completed_tasks_count'] = completed_tasks_count
            
            # Переходим к следующему месяцу
            if month == 12:
                current_date = datetime(year + 1, 1, 1)
            else:
                current_date = datetime(year, month + 1, 1)

        return monthly_data
    except Exception as e:
        logger.error(f"Error getting monthly tasks data: {e}")
        return {}

def generate_monthly_sales_report(conn):
    """Генерирует отчет о динамике продаж по месяцам."""
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    # Начинаем с марта 2024 года
    start_month = 3
    start_year = 2024
    
    # Получаем все данные
    revenue_data = get_monthly_revenue_data(conn, start_month, start_year, current_month, current_year)
    clients_data = get_monthly_clients_data(conn, start_month, start_year, current_month, current_year)
    tasks_data = get_monthly_tasks_data(conn, start_month, start_year, current_month, current_year)
    
    # Объединяем данные
    all_months = set(list(revenue_data.keys()) + list(clients_data.keys()) + list(tasks_data.keys()))
    all_months = sorted(all_months)
    
    # Формируем отчет
    message = '```'
    message += f'DYNAMIKA SPRZEDAŻY (marzec 2024 - {current_month:02d}.{current_year})\n'
    message += '═══════════════════════════════════════════════════════════════\n\n'
    
    # Заголовок таблицы
    message += f"{'Miesiąc':<12} {'Zamówienia':<10} {'Przychód (PLN)':<15} {'Nowi klienci':<15} {'Zadania':<10}\n"
    message += '─' * 70 + '\n'
    
    # Данные по месяцам
    total_orders = 0
    total_revenue = 0
    total_clients = 0
    total_tasks = 0
    
    for month_key in all_months:
        year, month = month_key.split('-')
        month_name = datetime(int(year), int(month), 1).strftime('%m.%Y')
        
        revenue_info = revenue_data.get(month_key, {})
        clients_info = clients_data.get(month_key, {})
        tasks_info = tasks_data.get(month_key, {})
        
        order_count = revenue_info.get('order_count', 0)
        revenue = revenue_info.get('total_revenue', 0)
        new_clients = clients_info.get('new_clients_count', 0)
        completed_tasks = tasks_info.get('completed_tasks_count', 0)
        
        # Суммируем для итогов
        total_orders += order_count
        total_revenue += revenue
        total_clients += new_clients
        total_tasks += completed_tasks
        
        # Форматируем строку
        revenue_str = format_int_currency(revenue) if revenue > 0 else '0'
        message += f"{month_name:<12} {order_count:<10} {revenue_str:<15} {new_clients:<15} {completed_tasks:<10}\n"
    
    # Итоговая строка
    message += '─' * 70 + '\n'
    total_revenue_str = format_int_currency(total_revenue)
    message += f"{'RAZEM':<12} {total_orders:<10} {total_revenue_str:<15} {total_clients:<15} {total_tasks:<10}\n"
    
    # Дополнительная статистика
    message += '\n📊 STATYSTYKI:\n'
    message += '─────────────────────────────────────\n'
    
    if all_months:
        # Средние значения
        months_count = len(all_months)
        avg_orders = total_orders / months_count
        avg_revenue = total_revenue / months_count
        avg_clients = total_clients / months_count
        avg_tasks = total_tasks / months_count
        
        message += f'Średnio miesięcznie:\n'
        message += f'  • Zamówienia: {avg_orders:.1f}\n'
        message += f'  • Przychód: {format_int_currency(avg_revenue)} PLN\n'
        message += f'  • Nowi klienci: {avg_clients:.1f}\n'
        message += f'  • Zadania: {avg_tasks:.1f}\n\n'
        
        # Лучший месяц
        best_month = max(revenue_data.items(), key=lambda x: x[1].get('total_revenue', 0))
        best_month_key = best_month[0]
        best_month_revenue = best_month[1].get('total_revenue', 0)
        year, month = best_month_key.split('-')
        best_month_name = datetime(int(year), int(month), 1).strftime('%m.%Y')
        
        message += f'Najlepszy miesiąc: {best_month_name}\n'
        message += f'  • Przychód: {format_int_currency(best_month_revenue)} PLN\n'
        message += f'  • Zamówienia: {best_month[1].get("order_count", 0)}\n'
    
    message += '\n═══════════════════════════════════════════════════════════════\n'
    message += f'Raport wygenerowany: {current_date.strftime("%d.%m.%Y %H:%M")}\n'
    message += '```'
    
    return message

def send_to_telegram(message):
    """Отправляет сообщение в Telegram."""
    bot_token = TELEGRAM_TOKEN
    
    if not bot_token:
        logger.error("Missing Telegram configuration")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': SALES_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to send message to Telegram: {response.text}")
            return False
        else:
            logger.info("Message sent successfully to Telegram")
            return True
    except Exception as e:
        logger.error(f"Failed to send message to Telegram: {e}")
        return False

def main():
    """Основная функция для генерации и отправки отчета о динамике продаж."""
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(
            host=PG_HOST,
            dbname=PG_DB,
            user=PG_USER,
            password=PG_PASSWORD,
            port=PG_PORT
        )
        
        # Генерируем отчет
        report = generate_monthly_sales_report(conn)
        
        # Отправляем в Telegram
        success = send_to_telegram(report)
        
        if success:
            logger.info("Monthly sales report sent successfully")
        else:
            logger.error("Failed to send monthly sales report")
        
        conn.close()
        
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting monthly sales report generation...")
    main() 