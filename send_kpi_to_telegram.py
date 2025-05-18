import psycopg2
import requests
from datetime import datetime, date

# --- Настройки базы данных ---
PG_HOST = "aws-0-eu-central-1.pooler.supabase.com"
PG_DB = "postgres"
PG_USER = "postgres.torlfffeghukusovmxsv"
PG_PASSWORD = "qogheb-jynsi4-mispiH"
PG_PORT = 6543

# --- Настройки Telegram ---
TELEGRAM_TOKEN = "8056760905:AAHtjq1DbUkoNGz1Xx3jEkUI8vLwWxvfbzE"
CHAT_ID = "-1001866680518"

def count_tasks_by_type(start_date, end_date):
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    
    print(f"\nDebug - Task query parameters:")
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    
    # Debug query to check task data format and PRZ tasks specifically
    cur.execute("""
        SELECT 
            owner_name,
            title,
            result,
            closed_at,
            TO_CHAR(closed_at, 'YYYY-MM-DD HH24:MI:SS') as formatted_date
        FROM planfix_tasks
        WHERE owner_name IN ('Kozik Andrzej', 'Stukalo Nazarii')
        AND closed_at IS NOT NULL
        AND TRIM(SPLIT_PART(title, '/', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną'
        LIMIT 10;
    """)
    print("\nDebug - Sample PRZ task data:")
    for row in cur.fetchall():
        print(f"Manager: {row[0]}, Title: {row[1]}, Result: {row[2]}, Date: {row[3]}, Formatted: {row[4]}")
    
    # Main query for tasks
    cur.execute("""
        WITH task_counts AS (
        SELECT
            owner_name AS manager,
                CASE 
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Nawiązać pierwszy kontakt' THEN 'WDM'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Zadzwonić do klienta' THEN 'ZKL'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Przeprowadzić pierwszą rozmowę telefoniczną' 
                         AND result = 'Klient jest zainteresowany' THEN 'PRZ'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Przeprowadzić spotkanie' THEN 'SPT'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Wysłać materiały' THEN 'MAT'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Opowiedzieć o nowościach' THEN 'NOW'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Zapisać na media społecznościowe' THEN 'MSP'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Odpowiedzieć na pytanie techniczne' THEN 'TPY'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Przywrócić klienta' THEN 'WRK'
                    WHEN TRIM(SPLIT_PART(title, '/', 1)) = 'Zebrać opinie' THEN 'OPI'
                END AS task_type,
            COUNT(*) AS task_count
        FROM
            planfix_tasks
        WHERE
            closed_at IS NOT NULL
                AND closed_at >= %s::timestamp
                AND closed_at < %s::timestamp
                AND owner_name IN ('Kozik Andrzej', 'Stukalo Nazarii')
            AND title IS NOT NULL
            AND POSITION('/' IN title) > 0
        GROUP BY
            owner_name, task_type
        )
        SELECT 
            manager,
            task_type,
            task_count
        FROM task_counts
        WHERE task_type IS NOT NULL
        ORDER BY manager, 
            CASE task_type
                WHEN 'WDM' THEN 1
                WHEN 'PRZ' THEN 2
                WHEN 'ZKL' THEN 3
                WHEN 'SPT' THEN 4
                WHEN 'MAT' THEN 5
                WHEN 'NOW' THEN 6
                WHEN 'MSP' THEN 7
                WHEN 'TPY' THEN 8
                WHEN 'WRK' THEN 9
                WHEN 'OPI' THEN 10
            END;
    """, (start_date, end_date))
    rows = cur.fetchall()
    print("\nDebug - Task results:")
    for row in rows:
        print(f"Manager: {row[0]}, Type: {row[1]}, Count: {row[2]}")
    cur.close()
    conn.close()
    return rows

def count_offers(start_date, end_date):
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    
    print(f"\nDebug - Offer query parameters:")
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    
    # Debug query to check offer data format
    cur.execute("""
        SELECT 
            menedzher,
            data_wyslania_oferty,
            TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') as parsed_date
        FROM planfix_orders
        WHERE menedzher IN ('945243', '945245')
        AND data_wyslania_oferty IS NOT NULL
        AND data_wyslania_oferty != ''
        LIMIT 5;
    """)
    print("\nDebug - Sample offer data:")
    for row in cur.fetchall():
        print(f"Manager: {row[0]}, Date: {row[1]}, Parsed: {row[2]}")
    
    # Main query for offers
    cur.execute("""
        SELECT
            menedzher AS manager,
            COUNT(*) AS offer_count
        FROM
            planfix_orders
        WHERE
            data_wyslania_oferty IS NOT NULL
            AND data_wyslania_oferty != ''
            AND TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
            AND TO_TIMESTAMP(data_wyslania_oferty, 'DD-MM-YYYY HH24:MI') < %s::timestamp
            AND menedzher IN ('945243', '945245')
        GROUP BY
            menedzher;
    """, (start_date, end_date))
    rows = cur.fetchall()
    print("\nDebug - Offer results:")
    for row in rows:
        print(f"Manager: {row[0]}, Count: {row[1]}")
    cur.close()
    conn.close()
    return rows

def count_orders(start_date, end_date):
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    
    print(f"\nDebug - Order query parameters:")
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    
    # Debug query to check order data format
    cur.execute("""
        SELECT 
            menedzher,
            data_potwierdzenia_zamowienia,
            TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') as parsed_date
        FROM planfix_orders
        WHERE menedzher IN ('945243', '945245')
        AND data_potwierdzenia_zamowienia IS NOT NULL
        AND data_potwierdzenia_zamowienia != ''
        LIMIT 5;
    """)
    print("\nDebug - Sample order data:")
    for row in cur.fetchall():
        print(f"Manager: {row[0]}, Date: {row[1]}, Parsed: {row[2]}")
    
    cur.execute("""
        WITH order_metrics AS (
            -- Count confirmed orders (ZAM)
            SELECT
                menedzher AS manager,
                COUNT(*) AS order_count,
                0 AS total_amount
            FROM
                planfix_orders
            WHERE
                data_potwierdzenia_zamowienia IS NOT NULL
                AND data_potwierdzenia_zamowienia != ''
                AND TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
                AND TO_TIMESTAMP(data_potwierdzenia_zamowienia, 'DD-MM-YYYY HH24:MI') < %s::timestamp
                AND menedzher IN ('945243', '945245')
            GROUP BY
                menedzher
            UNION ALL
            -- Calculate revenue (PRC) for realized orders
            SELECT
                menedzher AS manager,
                0 AS order_count,
                COALESCE(SUM(NULLIF(REPLACE(REPLACE(wartosc_netto_pln, ' ', ''), ',', '.'), '')::DECIMAL(10,2)), 0) AS total_amount
            FROM
                planfix_orders
            WHERE
                data_realizacji IS NOT NULL
                AND data_realizacji != ''
                AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') >= %s::timestamp
                AND TO_TIMESTAMP(data_realizacji, 'DD-MM-YYYY HH24:MI') < %s::timestamp
                AND menedzher IN ('945243', '945245')
            GROUP BY
                menedzher
        )
        SELECT 
            manager,
            SUM(order_count) AS order_count,
            SUM(total_amount) AS total_amount
        FROM order_metrics
        GROUP BY manager;
    """, (start_date, end_date, start_date, end_date))
    rows = cur.fetchall()
    print("\nDebug - Order results:")
    for row in rows:
        print(f"Manager: {row[0]}, Count: {row[1]}, Amount: {row[2]}")
    cur.close()
    conn.close()
    return rows

def count_client_statuses(start_date, end_date):
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    
    print(f"\nDebug - Client status query parameters:")
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    
    # Debug query to check client data format
    cur.execute("""
        SELECT 
            menedzer,
            data_dodania_do_nowi,
            data_dodania_do_w_trakcie,
            data_dodania_do_perspektywiczni,
            TO_DATE(data_dodania_do_nowi, 'DD-MM-YYYY') as parsed_date_nowi,
            TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') as parsed_date_w_trakcie,
            TO_DATE(data_dodania_do_perspektywiczni, 'DD-MM-YYYY') as parsed_date_perspektywiczni
        FROM planfix_clients
        WHERE menedzer IN ('Kozik Andrzej', 'Stukalo Nazarii')
        AND (data_dodania_do_nowi IS NOT NULL 
             OR data_dodania_do_w_trakcie IS NOT NULL 
             OR data_dodania_do_perspektywiczni IS NOT NULL)
        LIMIT 5;
    """)
    print("\nDebug - Sample client data:")
    for row in cur.fetchall():
        print(f"Manager: {row[0]}, NWI: {row[1]}, WTR: {row[2]}, PSK: {row[3]}")
        print(f"Parsed dates - NWI: {row[4]}, WTR: {row[5]}, PSK: {row[6]}")
    
    cur.execute("""
        WITH client_statuses AS (
            SELECT
                menedzer AS manager,
                'NWI' as status,
                COUNT(*) as count
            FROM
                planfix_clients
            WHERE
                data_dodania_do_nowi IS NOT NULL
                AND TO_DATE(data_dodania_do_nowi, 'DD-MM-YYYY') >= %s::date
                AND TO_DATE(data_dodania_do_nowi, 'DD-MM-YYYY') < %s::date
                AND menedzer IN ('Kozik Andrzej', 'Stukalo Nazarii')
            GROUP BY
                menedzer
            UNION ALL
            SELECT
                menedzer AS manager,
                'WTR' as status,
                COUNT(*) as count
            FROM
                planfix_clients
            WHERE
                data_dodania_do_w_trakcie IS NOT NULL
                AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') >= %s::date
                AND TO_DATE(data_dodania_do_w_trakcie, 'DD-MM-YYYY') < %s::date
                AND menedzer IN ('Kozik Andrzej', 'Stukalo Nazarii')
            GROUP BY
                menedzer
            UNION ALL
            SELECT
                menedzer AS manager,
                'PSK' as status,
                COUNT(*) as count
            FROM
                planfix_clients
            WHERE
                data_dodania_do_perspektywiczni IS NOT NULL
                AND TO_DATE(data_dodania_do_perspektywiczni, 'DD-MM-YYYY') >= %s::date
                AND TO_DATE(data_dodania_do_perspektywiczni, 'DD-MM-YYYY') < %s::date
                AND menedzer IN ('Kozik Andrzej', 'Stukalo Nazarii')
            GROUP BY
                menedzer
        )
        SELECT 
            manager,
            status,
            count
        FROM client_statuses
        ORDER BY manager, status;
    """, (start_date, end_date, start_date, end_date, start_date, end_date))
    rows = cur.fetchall()
    print("\nDebug - Client status results:")
    for row in rows:
        print(f"Manager: {row[0]}, Status: {row[1]}, Count: {row[2]}")
    cur.close()
    conn.close()
    return rows

def send_to_telegram(task_results, offer_results, order_results, client_results, report_type):
    # Initialize data structure for each manager
    managers = {
        '945243': 'Kozik Andrzej',
        '945245': 'Stukalo Nazarii'
    }
    data = {manager_id: {
        'WDM': 0, 'ZKL': 0, 'PRZ': 0, 'SPT': 0, 'MAT': 0, 'NOW': 0,
        'MSP': 0, 'TPY': 0, 'WRK': 0, 'OPI': 0, 'OFW': 0,
        'TTL': 0, 'ZAM': 0, 'PRC': 0,
        'NWI': 0, 'WTR': 0, 'PSK': 0
    } for manager_id in managers.keys()}
    
    # Process task results
    for manager, task_type, count in task_results:
        if manager in ['Kozik Andrzej', 'Stukalo Nazarii']:
            manager_id = '945243' if manager == 'Kozik Andrzej' else '945245'
            if task_type in data[manager_id]:
                data[manager_id][task_type] = count
                data[manager_id]['TTL'] += count
    
    # Process offer results
    for manager_id, count in offer_results:
        if manager_id in data:
            data[manager_id]['OFW'] = count
    
    # Process order results
    for manager_id, count, amount in order_results:
        if manager_id in data:
            data[manager_id]['ZAM'] = count
            data[manager_id]['PRC'] = amount
    
    # Process client status results
    for manager, status, count in client_results:
        if manager in ['Kozik Andrzej', 'Stukalo Nazarii']:
            manager_id = '945243' if manager == 'Kozik Andrzej' else '945245'
            if status in data[manager_id]:
                data[manager_id][status] = count
    
    # Get current date for report title
    current_date = datetime.now()
    if report_type == 'daily':
        report_title = f"RAPORT {current_date.strftime('%d.%m.%Y')}"
    else:  # monthly
        report_title = f"RAPORT {current_date.strftime('%m.%Y')}"
    
    # Format the table
    text = "```\n"  # Start monospace formatting
    text += f"{report_title}\n"
    text += "════════════════════════\n"
    text += "KPI | Kozik   | Stukalo\n"
    text += "────────────────────────\n"
    
    # Add task metrics in specific order, skipping if both managers have 0
    text += "zadania\n"
    task_order = ['WDM', 'PRZ', 'SPT', 'MAT', 'ZKL', 'TPY', 'MSP', 'NOW', 'WRK', 'OPI']
    has_any_tasks = False
    for task_type in task_order:
        kozik_value = data['945243'][task_type]
        stukalo_value = data['945245'][task_type]
        if kozik_value != 0 or stukalo_value != 0:
            if not has_any_tasks:
                has_any_tasks = True
            text += f"{task_type} | {int(kozik_value):7d} | {int(stukalo_value):8d}\n"
    
    if has_any_tasks:
        text += "────────────────────────\n"
        text += f"TTL | {int(data['945243']['TTL']):7d} | {int(data['945245']['TTL']):8d}\n"
    
    # Add client status metrics if any are non-zero
    text += "────────────────────────\n"
    text += "klienci\n"
    status_order = ['NWI', 'WTR', 'PSK']
    has_any_statuses = False
    for status in status_order:
        kozik_value = data['945243'][status]
        stukalo_value = data['945245'][status]
        if kozik_value != 0 or stukalo_value != 0:
            if not has_any_statuses:
                has_any_statuses = True
            text += f"{status} | {int(kozik_value):7d} | {int(stukalo_value):8d}\n"
    
    # Add order metrics if any are non-zero
    text += "────────────────────────\n"
    text += "zamówienia\n"
    has_any_orders = False
    
    # Add OFW first
    if data['945243']['OFW'] != 0 or data['945245']['OFW'] != 0:
        has_any_orders = True
        text += f"OFW | {int(data['945243']['OFW']):7d} | {int(data['945245']['OFW']):8d}\n"
    
    # Then add ZAM
    if data['945243']['ZAM'] != 0 or data['945245']['ZAM'] != 0:
        if not has_any_orders:
            text += "────────────────────────\n"
        has_any_orders = True
        text += f"ZAM | {int(data['945243']['ZAM']):7d} | {int(data['945245']['ZAM']):8d}\n"
    
    # Finally add PRC
    if data['945243']['PRC'] != 0 or data['945245']['PRC'] != 0:
        if not has_any_orders:
            text += "────────────────────────\n"
        has_any_orders = True
        text += f"PRC | {float(data['945243']['PRC']):7.0f} | {float(data['945245']['PRC']):8.0f}\n"
    
    text += "════════════════════════\n"
    text += "```"  # End monospace formatting
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, data=payload)
    response.raise_for_status()

def get_date_range(report_type):
    # Use current date instead of 2025
    today = date.today()
    
    if report_type == 'daily':
        start_date = today
        end_date = today.replace(day=today.day + 1)
    else:  # monthly
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1)
    
    print(f"\nDebug - Date range for {report_type} report:")
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    
    # Convert dates to the format used in the database
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    print(f"Formatted start date: {start_date_str}")
    print(f"Formatted end date: {end_date_str}")
    
    return start_date_str, end_date_str

if __name__ == "__main__":
    # Send daily report
    start_date, end_date = get_date_range('daily')
    task_results = count_tasks_by_type(start_date, end_date)
    offer_results = count_offers(start_date, end_date)
    order_results = count_orders(start_date, end_date)
    client_results = count_client_statuses(start_date, end_date)
    send_to_telegram(task_results, offer_results, order_results, client_results, 'daily')
    
    # Send monthly report
    start_date, end_date = get_date_range('monthly')
    task_results = count_tasks_by_type(start_date, end_date)
    offer_results = count_offers(start_date, end_date)
    order_results = count_orders(start_date, end_date)
    client_results = count_client_statuses(start_date, end_date)
    send_to_telegram(task_results, offer_results, order_results, client_results, 'monthly')
    
    print("Отчеты отправлены в Telegram.")
