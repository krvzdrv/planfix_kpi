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

# Статусы клиентов и их порядок в отчёте
CLIENT_STATUSES = ['NWI', 'WTR', 'PSK', 'PIR', 'STL', 'NAK', 'REZ']

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
    WITH status_counts AS (
        SELECT
            'NWI' as status,
            COUNT(*) as count
        FROM planfix_clients
        WHERE menedzer = %s
            AND data_dodania_do_nowi IS NOT NULL
            AND data_dodania_do_nowi != ''
            AND TO_DATE(data_dodania_do_nowi, 'DD-MM-YYYY') <= %s
            AND is_deleted = false
        GROUP BY menedzer
        
        UNION ALL
        
        SELECT
            'WTR' as status,
            COUNT(*) as count
        FROM planfix_clients
        WHERE menedzer = %s
            AND data_dodania_do_w_trakcie IS NOT NULL
            AND data_dodania_do_w_trakcie != ''
            AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') <= %s
            AND is_deleted = false
        GROUP BY menedzer
        
        UNION ALL
        
        SELECT
            'PSK' as status,
            COUNT(*) as count
        FROM planfix_clients
        WHERE menedzer = %s
            AND data_dodania_do_perspektywiczni IS NOT NULL
            AND data_dodania_do_perspektywiczni != ''
            AND TO_DATE(data_dodania_do_perspektywiczni, 'DD-MM-YYYY') <= %s
            AND is_deleted = false
        GROUP BY menedzer
        
        UNION ALL
        
        SELECT
            'PIR' as status,
            COUNT(*) as count
        FROM planfix_clients
        WHERE menedzer = %s
            AND data_dodania_do_pir IS NOT NULL
            AND data_dodania_do_pir != ''
            AND TO_DATE(data_dodania_do_pir, 'DD-MM-YYYY') <= %s
            AND is_deleted = false
        GROUP BY menedzer
        
        UNION ALL
        
        SELECT
            'STL' as status,
            COUNT(*) as count
        FROM planfix_clients
        WHERE menedzer = %s
            AND data_dodania_do_stali IS NOT NULL
            AND data_dodania_do_stali != ''
            AND TO_DATE(data_dodania_do_stali, 'DD-MM-YYYY') <= %s
            AND is_deleted = false
        GROUP BY menedzer
        
        UNION ALL
        
        SELECT
            'NAK' as status,
            COUNT(*) as count
        FROM planfix_clients
        WHERE menedzer = %s
            AND data_dodania_do_nakladka IS NOT NULL
            AND data_dodania_do_nakladka != ''
            AND TO_DATE(data_dodania_do_nakladka, 'DD-MM-YYYY') <= %s
            AND is_deleted = false
        GROUP BY menedzer
        
        UNION ALL
        
        SELECT
            'REZ' as status,
            COUNT(*) as count
        FROM planfix_clients
        WHERE menedzer = %s
            AND data_dodania_do_rezygnacja IS NOT NULL
            AND data_dodania_do_rezygnacja != ''
            AND TO_DATE(data_dodania_do_rezygnacja, 'DD-MM-YYYY') <= %s
            AND is_deleted = false
        GROUP BY menedzer
    )
    SELECT status, COALESCE(count, 0) as count
    FROM (
        SELECT unnest(ARRAY['NWI', 'WTR', 'PSK', 'PIR', 'STL', 'NAK', 'REZ']) as status
    ) s
    LEFT JOIN status_counts sc USING (status)
    ORDER BY array_position(ARRAY['NWI', 'WTR', 'PSK', 'PIR', 'STL', 'NAK', 'REZ'], status);
    """
    
    params = tuple([manager, current_date] * 7)  # Для каждого статуса
    results = _execute_query(query, params, f"client statuses for {manager}")
    
    return {row[0]: row[1] for row in results}

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
            direction = "-"
            
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
    lines.append(f"{manager} {date.today().strftime('%d.%m.%Y')}\n")
    
    for status in CLIENT_STATUSES:
        data = status_changes[status]
        current = data['current']
        change = data['change']
        direction = data['direction']
        percentage = (current / total * 100) if total > 0 else 0
        
        # Форматируем строку изменения
        change_str = f"{direction:1s} {'+' if change > 0 else ''}{change:3d}" if change != 0 else f"{direction:1s}     "
        
        # Форматируем строку статуса
        status_line = f"{status} {format_progress_bar(current, total)}{current:3d} {change_str} {percentage:3.0f}%"
        lines.append(status_line)
    
    lines.append("─" * 35)
    lines.append(f"{'':19d} {total:3d}    {'+' if sum(d['change'] for d in status_changes.values()) > 0 else ''}{sum(d['change'] for d in status_changes.values()):3d} 100%")
    
    return "\n".join(lines)

def send_to_telegram(message: str):
    """Отправить сообщение в Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': f"```\n{message}\n```",
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, json=payload, timeout=10)
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
    
    for manager in (m['planfix_user_name'] for m in MANAGERS_KPI):
        try:
            status_changes = get_client_status_changes(manager, today)
            report = format_client_status_report(manager, status_changes)
            send_to_telegram(report)
            logger.info(f"Client status report for {manager} sent successfully")
        except Exception as e:
            logger.error(f"Error processing report for {manager}: {e}")

if __name__ == "__main__":
    main() 