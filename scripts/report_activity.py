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
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

logger = logging.getLogger(__name__)


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

def get_daily_activity(start_date: datetime, end_date: datetime, user_names: tuple) -> dict:
    query = """
    WITH task_counts AS (
        SELECT 
            EXTRACT(HOUR FROM t.data_zakonczenia_zadania) as hour,
            t.owner_name AS manager_name,
            CASE 
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Nawiązać pierwszy kontakt' THEN 'WDM'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną' THEN 'PRZ'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Zadzwonić do klienta' THEN 'ZKL'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Przeprowadzić spotkanie' THEN 'SPT'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Wysłać materiały' THEN 'MAT'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Odpowiedzieć na pytanie techniczne' THEN 'TPY'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Zapisać na media społecznościowe' THEN 'MSP'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Opowiedzieć o nowościach' THEN 'NOW'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Zebrać opinie' THEN 'OPI'
                WHEN TRIM(SPLIT_PART(t.title, ' /', 1)) = 'Przywrócić klienta' THEN 'WRK'
                ELSE NULL
            END AS metric,
            COUNT(*) as count
        FROM planfix_tasks t
        WHERE t.data_zakonczenia_zadania >= %s AND t.data_zakonczenia_zadania < %s
        AND t.owner_name = ANY(%s)
        AND t.is_deleted = false
        AND TRIM(SPLIT_PART(t.title, ' /', 1)) IN (
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
        GROUP BY hour, t.owner_name, metric
    ),
    client_statuses AS (
        SELECT 
            EXTRACT(HOUR FROM TO_TIMESTAMP(c.data_dodania_do_nowi, 'DD-MM-YYYY HH24:MI')) as hour,
            c.menedzer AS manager_name,
            'NWI' as metric,
            COUNT(*) as count
        FROM planfix_clients c
        WHERE c.data_dodania_do_nowi IS NOT NULL AND c.data_dodania_do_nowi != ''
        AND TO_DATE(c.data_dodania_do_nowi, 'DD-MM-YYYY') >= %s AND TO_DATE(c.data_dodania_do_nowi, 'DD-MM-YYYY') < %s
        AND c.menedzer = ANY(%s)
        AND c.is_deleted = false
        GROUP BY hour, c.menedzer
        
        UNION ALL
        
        SELECT 
            EXTRACT(HOUR FROM TO_TIMESTAMP(c.data_dodania_do_w_trakcie, 'DD-MM-YYYY HH24:MI')) as hour,
            c.menedzer AS manager_name,
            'WTR' as metric,
            COUNT(*) as count
        FROM planfix_clients c
        WHERE c.data_dodania_do_w_trakcie IS NOT NULL AND c.data_dodania_do_w_trakcie != ''
        AND TO_DATE(c.data_dodania_do_w_trakcie, 'DD-MM-YYYY') >= %s AND TO_DATE(c.data_dodania_do_w_trakcie, 'DD-MM-YYYY') < %s
        AND c.menedzer = ANY(%s)
        AND c.is_deleted = false
        GROUP BY hour, c.menedzer
        
        UNION ALL
        
        SELECT 
            EXTRACT(HOUR FROM TO_TIMESTAMP(c.data_dodania_do_perspektywiczni, 'DD-MM-YYYY HH24:MI')) as hour,
            c.menedzer AS manager_name,
            'PSK' as metric,
            COUNT(*) as count
        FROM planfix_clients c
        WHERE c.data_dodania_do_perspektywiczni IS NOT NULL AND c.data_dodania_do_perspektywiczni != ''
        AND TO_DATE(c.data_dodania_do_perspektywiczni, 'DD-MM-YYYY') >= %s AND TO_DATE(c.data_dodania_do_perspektywiczni, 'DD-MM-YYYY') < %s
        AND c.menedzer = ANY(%s)
        AND c.is_deleted = false
        GROUP BY hour, c.menedzer
    ),
    order_metrics AS (
        SELECT 
            EXTRACT(HOUR FROM TO_TIMESTAMP(o.data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI')) as hour,
            o.menedzher as manager_name,
            'OFW' as metric,
            COUNT(*) as count
        FROM planfix_orders o
        WHERE o.data_potwierdzenia_zamowienia IS NOT NULL AND o.data_potwierdzenia_zamowienia != ''
        AND TO_TIMESTAMP(o.data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') >= %s 
        AND TO_TIMESTAMP(o.data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') < %s
        AND o.menedzher = ANY(%s)
        AND o.wartosc_netto_pln IS NOT NULL
        AND o.wartosc_netto_pln != ''
        AND CAST(REPLACE(REPLACE(o.wartosc_netto_pln, ' ', ''), ',', '.') AS DECIMAL) != 0
        GROUP BY hour, o.menedzher

        UNION ALL

        SELECT 
            EXTRACT(HOUR FROM TO_TIMESTAMP(o.data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI')) as hour,
            o.menedzher as manager_name,
            'ZAM' as metric,
            COUNT(*) as count
        FROM planfix_orders o
        WHERE o.data_potwierdzenia_zamowienia IS NOT NULL AND o.data_potwierdzenia_zamowienia != ''
        AND TO_TIMESTAMP(o.data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') >= %s 
        AND TO_TIMESTAMP(o.data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') < %s
        AND o.menedzher = ANY(%s)
        AND o.wartosc_netto_pln IS NOT NULL
        AND o.wartosc_netto_pln != ''
        AND CAST(REPLACE(REPLACE(o.wartosc_netto_pln, ' ', ''), ',', '.') AS DECIMAL) != 0
        GROUP BY hour, o.menedzher
    )
    SELECT 
        hour,
        manager_name,
        metric,
        count
    FROM (
        SELECT * FROM task_counts
        UNION ALL
        SELECT * FROM client_statuses
        UNION ALL
        SELECT * FROM order_metrics
    ) combined
    WHERE metric IN ('NWI', 'WDM', 'PRZ', 'ZKL', 'SPT', 'MAT', 'TPY', 'MSP', 'NOW', 'OPI', 'WRK', 'OFW', 'ZAM')
    ORDER BY hour, manager_name, metric
    """
    
    params = (
        start_date, end_date, list(user_names),  # task_counts
        start_date, end_date, list(user_names),  # NWI
        start_date, end_date, list(user_names),  # WTR
        start_date, end_date, list(user_names),  # PSK
        start_date, end_date, list(user_names),  # OFW
        start_date, end_date, list(user_names),  # ZAM
    )
    
    results = _execute_query(query, params, description="daily activity")
    
    # Инициализируем структуру данных для активности
    activity = {}
    for h in range(24):
        activity[h] = {
            'NWI': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'WDM': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'PRZ': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'ZKL': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'SPT': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'MAT': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'TPY': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'MSP': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'NOW': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'OPI': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'WRK': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'OFW': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0},
            'ZAM': {'Kozik Andrzej': 0, 'Stukalo Nazarii': 0}
        }
    
    # Заполняем данные
    for row in results:
        hour = int(row[0])
        manager = row[1]
        metric = row[2]
        count = row[3]
        activity[hour][metric][manager] = count
    
    return activity

def format_activity_report(activity: dict, current_date: date) -> str:
    message = '```'
    message += f'AKTYWNOŚĆ_{current_date.strftime("%d.%m.%Y")}\n'
    message += '════════════════════════\n'
    message += 'GDZ   | Kozik  | Stukalo\n'
    message += '────────────────────────\n'
    total = {m['planfix_user_name']: 0 for m in MANAGERS_KPI}
    active_hours = set()
    for h in activity.keys():
        kozik = sum(activity[h][metric]['Kozik Andrzej'] for metric in activity[h] if metric != 'KZI')
        stukalo = sum(activity[h][metric]['Stukalo Nazarii'] for metric in activity[h] if metric != 'KZI')
        if kozik > 0 or stukalo > 0:
            active_hours.add(h)
    for h in range(9, 17):
        active_hours.add(h)
    for h in sorted(active_hours):
        h_next = h + 1
        godz = f"{h:02d}–{h_next:02d}"
        kozik = sum(activity[h][metric]['Kozik Andrzej'] for metric in activity[h] if metric != 'KZI')
        stukalo = sum(activity[h][metric]['Stukalo Nazarii'] for metric in activity[h] if metric != 'KZI')
        total['Kozik Andrzej'] += kozik
        total['Stukalo Nazarii'] += stukalo
        message += f"{godz} |{kozik:7d} |{stukalo:7d}\n"
    message += '────────────────────────\n'
    message += f"Suma  |{total['Kozik Andrzej']:7d} |{total['Stukalo Nazarii']:7d}\n"
    message += '════════════════════════\n'
    message += '```'
    return message

def send_to_telegram(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
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
    today = date.today()
    activity = get_daily_activity(today, today + timedelta(days=1), tuple(m['planfix_user_name'] for m in MANAGERS_KPI))
    message = format_activity_report(activity, today)
    send_to_telegram(message)
    logger.info("Daily activity report sent successfully")

if __name__ == "__main__":
    main() 