import os
import sys
import logging
from datetime import datetime
import json
import xml.etree.ElementTree as ET
import psycopg2
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.planfix_utils as planfix_utils

ORDER_TEMPLATE_ID = 2420917
ORDERS_TABLE_NAME = "planfix_orders"
ORDERS_PK_COLUMN = "planfix_id"

# Сопоставление custom field name -> column name (как в старом скрипте)
CUSTOM_MAP = {
    "Zadanie powiązane": "zadanie_powiazane",
    "Kontakt": "kontakt",
    "Numer zamówienia": "numer_zamowienia",
    "Wartość netto": "wartosc_netto",
    "Доставка": "dostawa",
    "Оплата": "oplata",
    "Плательщик": "platelshchik",
    "Numer kolejny FS": "numer_kolejny_fs",
    "Numer documentu FS": "numer_documentu_fs",
    "Faktura VAT.pdf": "faktura_vat_pdf",
    "Waluta": "waluta",
    "Счет контрагента": "schet_kontragenta",
    "Data wystawienia FS": "data_wystawienia_fs",
    "Data dostawy": "data_dostawy",
    "Faktura proforma.pdf": "faktura_proforma_pdf",
    "ID moysklad": "id_moysklad",
    "Запустить сценарий \"Создать/обновить документ отгрузки\"": "zapustit_stsenariy_sozdat_obnovit_dokument_otgruzki",
    "Kwota zapłacona": "kwota_zaplacona",
    "Data wystawienia PF": "data_wystawienia_pf",
    "Numer documentu PF": "numer_documentu_pf",
    "Numer kolejny PF": "numer_kolejny_pf",
    "Запустить сценарий Data PF": "zapustit_stsenariy_data_pf",
    "Запустить сценарий Data FS": "zapustit_stsenariy_data_fs",
    "Stawka VAT": "stawka_vat",
    "PLN/EUR": "pln_eur",
    "PLN/USD": "pln_usd",
    "Typ ceny": "typ_ceny",
    "Kwota VAT": "kwota_vat",
    "Wartość brutto": "wartosc_brutto",
    "Wartość netto, PLN": "wartosc_netto_pln",
    "Menedżer": "menedzher",
    "Data wysłania oferty": "data_wyslania_oferty",
    "Data potwierdzenia zamówienia": "data_potwierdzenia_zamowienia",
    "Data rozpoczęcia kompletacji": "data_rozpoczecia_kompletacji",
    "Data gotowości do wysyłki": "data_gotowosci_do_wysylki",
    "Data wysyłki": "data_wysylki",
    "Data przekazania do weryfikacji": "data_przekazania_do_weryfikacji",
    "Data realizacji": "data_realizacji",
    "Data anulowania": "data_anulowania",
    "Obliczenie liczby ofert i zamówień": "obliczenie_liczby_ofert_i_zamowien",
    "Łączna prowizja, PLN": "laczna_prowizja_pln",
    "Kompletator": "kompletator",
    "Łączna masa, kg": "laczna_masa_kg",
    "Potwierdzenie wywozu": "potwierdzenie_wywozu",
    "Adres dostawy": "adres_dostawy",
    "Sposób dostawy": "sposob_dostawy",
    "Запустить сценарий \"Обновить данные в KPI\"": "zapustit_stsenariy_obnovit_dannye_v_kpi",
    "Język": "jezyk",
    "Pro Forma Invoice.pdf": "pro_forma_invoice_pdf",
    "VAT Invoice.pdf": "vat_invoice_pdf",
    "Numer trackingu": "numer_trackingu"
}

logger = logging.getLogger(__name__)

def get_planfix_orders(page):
    """
    Получает список заказов из Planfix API
    """
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<request method="task.getList">'
        f'<account>{os.environ.get("PLANFIX_ACCOUNT")}</account>'
        f'<pageCurrent>{page}</pageCurrent>'
        f'<pageSize>100</pageSize>'
        '<filters>'
        '  <filter>'
        '    <type>51</type>'
        '    <operator>equal</operator>'
        f'    <value>{ORDER_TEMPLATE_ID}</value>'
        '  </filter>'
        '</filters>'
        '<fields>'
        '  <field>id</field>'
        '  <field>title</field>'
        '  <field>description</field>'
        '  <field>status</field>'
        '  <field>statusName</field>'
        '  <field>assigner</field>'
        '  <field>owner</field>'
        '  <field>dateCreate</field>'
        '  <field>dateStart</field>'
        '  <field>dateEnd</field>'
        '  <field>dateComplete</field>'
        '  <field>lastUpdateDate</field>'
        '  <field>type</field>'
        '  <field>template</field>'
        '  <field>customData</field>'
        '</fields>'
        '</request>'
    )
    response = requests.post(
        os.environ.get("PLANFIX_API_URL", "https://api.planfix.com/xml/"),
        data=body.encode('utf-8'),
        headers=headers,
        auth=(os.environ.get("PLANFIX_API_KEY"), os.environ.get("PLANFIX_TOKEN"))
    )
    response.raise_for_status()
    
    # Добавляем отладочный вывод XML-ответа только для заказа A-10051
    if page == 1:
        root = ET.fromstring(response.text)
        for task in root.findall('.//task'):
            title = task.findtext('title')
            if title and 'A-10051' in title:
                logger.info("XML Response for order A-10051:")
                task_xml = ET.tostring(task, encoding='unicode')
                logger.info(task_xml)
                break
    
    return response.text

def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def parse_orders(xml_text):
    root = ET.fromstring(xml_text)
    if root.attrib.get("status") == "error":
        code = root.findtext("code")
        message = root.findtext("message")
        logger.error(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    orders = []
    custom_fields = {
        "Zadanie powiązane": "zadanie_powiazane",
        "Kontakt": "kontakt",
        "Wynik": "wynik",
        "Prywatna notatka": "prywatna_notatka",
        "Zmień nazwę zadania": "zmien_nazwe_zadania",
        "Ostatni komentarz": "ostatni_komentarz",
        "Autor komentarza": "autor_komentarza",
        "Data utworzenia zadania": "data_utworzenia_zadania",
        "Data zakończenia zadania": "data_zakonczenia_zadania",
        "Запустить сценарий \"Обновить данные в KPI\"": "zapustit_scenarij_obnovit_dannye_v_kpi"
    }
    for task in root.findall('.//task'):
        template_id = task.findtext('template/id')
        if str(template_id) != str(ORDER_TEMPLATE_ID):
            continue
        def get_text(tag):
            el = task.find(tag)
            return el.text if el is not None else None
        title = get_text('title')
        task_id = get_text('id')
        
        # Получаем статус и его название напрямую из API
        status = get_text('status')
        status_name = get_text('statusName')
        
        # Логируем информацию только для заказа A-10051
        if title and 'A-10051' in title:
            task_type = None
            if title and '/' in title:
                task_type = title.split('/')[0].strip()
                
            logger.info(f"Order {title}: task_id={task_id}, status={status}, status_name={status_name}")
            
            # Логируем все customData для этого заказа
            custom_data_root = task.find('customData')
            if custom_data_root is not None:
                logger.info("Custom data for order A-10051:")
                for cv in custom_data_root.findall('customValue'):
                    field = cv.find('field/name')
                    value = cv.find('value')
                    text = cv.find('text')
                    if field is not None:
                        logger.info(f"Field: {field.text}, Value: {value.text if value is not None else None}, Text: {text.text if text is not None else None}")
        
        task_type = None
        if title and '/' in title:
            task_type = title.split('/')[0].strip()
            
        # Добавляем отладочный вывод
        logger.info(f"Order {title}: status={status}, status_name={status_name}")
        
        # Парсим customData
        custom_data = {}
        custom_result = {v: None for v in custom_fields.values()}
        custom_data_root = task.find('customData')
        if custom_data_root is not None:
            for cv in custom_data_root.findall('customValue'):
                field = cv.find('field/name')
                value = cv.find('value')
                text = cv.find('text')
                if field is not None:
                    field_name = field.text
                    if field_name in custom_fields:
                        # Для дат парсим value как дату, если это дата
                        if field_name in ["Data utworzenia zadania", "Data zakończenia zadania"]:
                            custom_result[custom_fields[field_name]] = parse_date(value.text) if value is not None else None
                        else:
                            custom_result[custom_fields[field_name]] = value.text if value is not None else text.text if text is not None else None
                    custom_data[field_name] = {
                        "value": value.text if value is not None else None,
                        "text": text.text if text is not None else None
                    }
        
        # Формируем запись для Supabase
        order_data = {
            "planfix_id": task_id,
            "title": title,
            "status": status,
            "status_name": status_name,
            "task_type": task_type,
            "description": get_text('description'),
            "assigner": get_text('assigner/name'),
            "owner": get_text('owner/name'),
            "date_create": parse_date(get_text('dateCreate')),
            "date_start": parse_date(get_text('dateStart')),
            "date_end": parse_date(get_text('dateEnd')),
            "date_complete": parse_date(get_text('dateComplete')),
            "last_update_date": parse_date(get_text('lastUpdateDate')),
            "custom_data": json.dumps(custom_data) if custom_data else None,
            "updated_at": datetime.now().isoformat(),
            "is_deleted": False
        }
        
        # Добавляем кастомные поля
        order_data.update(custom_result)
        
        orders.append(order_data)
    
    return orders

def upsert_orders(orders, supabase_conn):
    """
    Обновляет или создаёт записи в Supabase
    """
    if not orders:
        logger.info("No orders to upsert")
        return

    try:
        # Получаем список всех ID заказов
        order_ids = [order["planfix_id"] for order in orders]
        
        # Получаем существующие заказы
        cursor = supabase_conn.cursor()
        cursor.execute(
            f'SELECT {ORDERS_PK_COLUMN}, status_name FROM {ORDERS_TABLE_NAME} WHERE {ORDERS_PK_COLUMN} = ANY(%s)',
            (order_ids,)
        )
        existing_orders = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Обновляем только те заказы, где изменился статус
        for order in orders:
            order_id = order["planfix_id"]
            if order_id not in existing_orders or existing_orders[order_id] != order["status_name"]:
                logger.info(f"Updating order {order_id} with new status name: {order['status_name']}")
                planfix_utils.upsert_data_to_supabase(
                    supabase_conn,
                    ORDERS_TABLE_NAME,
                    ORDERS_PK_COLUMN,
                    list(order.keys()),
                    [order]
                )
            else:
                logger.debug(f"Order {order_id} status name unchanged: {order['status_name']}")
                
    except Exception as e:
        logger.error(f"Error upserting orders: {e}")
        raise

def main():
    supabase_conn = None
    try:
        # Получаем соединение с Supabase
        supabase_conn = planfix_utils.get_supabase_connection()
        all_orders = []
        
        # Получаем все заказы постранично
        page = 1
        while True:
            logger.info(f"Fetching orders page {page}")
            xml_response = get_planfix_orders(page)
            orders = parse_orders(xml_response)
            
            if not orders:
                logger.info("No more orders to process")
                break
                
            all_orders.extend(orders)
            page += 1
        
        # Обновляем заказы в Supabase
        if all_orders:
            logger.info(f"Upserting {len(all_orders)} orders to Supabase")
            upsert_orders(all_orders, supabase_conn)
            
            # Помечаем удаленные заказы
            actual_ids = [order["planfix_id"] for order in all_orders]
            planfix_utils.mark_items_as_deleted_in_supabase(
                supabase_conn,
                ORDERS_TABLE_NAME,
                ORDERS_PK_COLUMN,
                actual_ids
            )
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise
    finally:
        if supabase_conn:
            supabase_conn.close()

if __name__ == "__main__":
    main()
