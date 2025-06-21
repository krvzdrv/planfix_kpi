import psycopg2
import requests
from datetime import datetime, date, timedelta
import os
import logging
from dotenv import load_dotenv
import sys
sys.path.insert(0, os.path.dirname(__file__))
from config import MANAGERS_KPI

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID_CLIENTS', '-1001866680518')  # Специальный чат для отчёта по клиентам

logger = logging.getLogger(__name__)

# Статусы клиентов и их порядок в отчёте (сокращённые названия)
CLIENT_STATUSES = ['NWI', 'WTR', 'PSK', 'PIZ', 'STL', 'NAK', 'REZ']

# Сопоставление полных названий статусов с сокращёнными
STATUS_MAPPING = {
    'Nowi': 'NWI',
    'W trakcie': 'WTR', 
    'Perspektywiczni': 'PSK',
    'Pir': 'PIZ',
    'Stali': 'STL',
    'Nakladka': 'NAK',
    'Rezygnacja': 'REZ'
}

def _execute_query(query: str, params: tuple, description: str) -> list:
    conn = None
    try:
        conn = psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT)
        cur = conn.cursor()
        logger.info(f"Executing query for: {description} with params: {params}")
        cur.execute(query, params)
        rows = cur.fetchall()
        logger.info(f"Query for {description} returned {len(rows)} rows.")
        return rows
    except psycopg2.Error as e:
        logger.error(f"Database error during query for {description}: {e}")
        raise
    finally:
        if conn:
            conn.close()

def get_client_statuses(manager: str, current_date: date) -> dict:
    """Получить текущие статусы клиентов для менеджера."""
    query = """
    SELECT 
        status_wspolpracy as status,
        COUNT(*) as count
    FROM planfix_clients
    WHERE menedzer = %s
        AND status_wspolpracy IS NOT NULL
        AND status_wspolpracy != ''
        AND is_deleted = false
    GROUP BY status_wspolpracy
    ORDER BY status_wspolpracy;
    """
    
    params = (manager,)
    results = _execute_query(query, params, f"client statuses for {manager}")
    
    # Создаем словарь с нулевыми значениями для всех статусов
    status_counts = {status: 0 for status in CLIENT_STATUSES}
    
    # Заполняем реальными данными
    for row in results:
        full_status = row[0]
        count = row[1]
        short_status = STATUS_MAPPING.get(full_status, full_status)
        if short_status in status_counts:
            status_counts[short_status] = count
    
    return status_counts

def get_client_status_changes(manager: str, current_date: date) -> dict:
    """Получить изменения в статусах клиентов за последние сутки."""
    yesterday = current_date - timedelta(days=1)
    
    current = get_client_statuses(manager, current_date)
    previous = get_client_statuses(manager, yesterday)
    
    changes = {}
    for status in CLIENT_STATUSES:
        curr_count = current.get(status, 0)
        prev_count = previous.get(status, 0)
        diff = curr_count - prev_count
        
        if diff > 0:
            direction = "▲"
        elif diff < 0:
            direction = "▼"
        else:
            direction = "➖"
            
        changes[status] = {
            'current': curr_count,
            'change': diff,
            'direction': direction
        }
    
    return changes

def format_progress_bar(value: int, max_value: int, width: int = 14) -> str:
    """Форматировать прогресс-бар из символов █."""
    filled = int(round(width * value / max_value)) if max_value > 0 else 0
    return '█' * filled + ' ' * (width - filled)

def format_client_status_report(manager: str, status_changes: dict) -> str:
    """Форматировать отчёт по статусам клиентов."""
    total = sum(data['current'] for data in status_changes.values())
    
    lines = []
    lines.append(f"Woronka {date.today().strftime('%d.%m.%Y')}\n")
    
    for status in CLIENT_STATUSES:
        data = status_changes[status]
        current = data['current']
        change = data['change']
        direction = data['direction']
        percentage = (current / total * 100) if total > 0 else 0
        
        # Форматируем строку изменения
        if change > 0:
            change_str = f"{direction} +{change:2d}"
        elif change < 0:
            change_str = f"{direction} {change:3d}"
        else:
            change_str = f"{direction}     "
        
        # Форматируем строку статуса
        status_line = f"{status} {format_progress_bar(current, total)}{current:3d} {change_str} ({percentage:2.0f}%)"
        lines.append(status_line)
    
    lines.append("─" * 32)
    lines.append(f"👥 Wszyscy klienci: {total:8d}")
    
    return "\n".join(lines)

def send_to_telegram(message: str):
    """Отправить сообщение в Telegram."""
    try:
        logger.info(f"Attempting to send message to Telegram chat {CHAT_ID}")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': f"```\n{message}\n```",
            'parse_mode': 'Markdown'
        }
        logger.info(f"Sending request to Telegram API...")
        response = requests.post(url, json=payload, timeout=10)
        logger.info(f"Telegram API response status code: {response.status_code}")
        logger.info(f"Telegram API response text: {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Failed to send message to Telegram: {response.text}")
        else:
            logger.info("Message sent successfully to Telegram")
    except Exception as e:
        logger.error(f"Error sending to Telegram: {str(e)}")
        raise

def main():
    """Основная функция для генерации и отправки отчёта."""
    today = date.today()
    logger.info(f"Starting client status report generation for date: {today}")
    
    # Собираем данные для всех менеджеров
    all_reports = []
    
    for manager in (m['planfix_user_name'] for m in MANAGERS_KPI):
        try:
            logger.info(f"Processing report for manager: {manager}")
            status_changes = get_client_status_changes(manager, today)
            logger.info(f"Got status changes for {manager}: {status_changes}")
            report = format_client_status_report(manager, status_changes)
            all_reports.append(report)
            logger.info(f"Formatted report for {manager}")
        except Exception as e:
            logger.error(f"Error processing report for {manager}: {str(e)}")
            logger.exception("Full traceback:")
    
    # Отправляем один общий отчёт
    if all_reports:
        combined_report = "\n\n".join(all_reports)
        logger.info(f"Sending combined report to Telegram")
        send_to_telegram(combined_report)
        logger.info("Combined client status report sent successfully")

if __name__ == "__main__":
    logger.info("Client status report script started")
    main()
    logger.info("Client status report script finished") 