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
from utils.planfix_utils import (
    check_required_env_vars,
    make_planfix_request,
    get_supabase_connection,
    mark_items_as_deleted_in_supabase,
    upsert_data_to_supabase
)

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
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<request method="task.getList">'
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
        '  <field>importance</field>'
        '  <field>status</field>'
        '  <field>statusSet</field>'
        '  <field>statusName</field>'
        '  <field>checkResult</field>'
        '  <field>type</field>'
        '  <field>owner</field>'
        '  <field>parent</field>'
        '  <field>template</field>'
        '  <field>project</field>'
        '  <field>client</field>'
        '  <field>beginDateTime</field>'
        '  <field>general</field>'
        '  <field>isOverdued</field>'
        '  <field>isCloseToDeadline</field>'
        '  <field>isNotAcceptedInTime</field>'
        '  <field>isSummary</field>'
        '  <field>starred</field>'
        '  <field>customData</field>'
        '</fields>'
        '</request>'
    )
    response = requests.post(
        "https://api.planfix.com/xml/",
        data=body.encode('utf-8'),
        headers=headers,
        auth=(os.environ.get('PLANFIX_API_KEY'), os.environ.get('PLANFIX_TOKEN'))
    )
    response.raise_for_status()
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
    for task in root.findall('.//task'):
        def get_text(tag):
            el = task.find(tag)
            return el.text if el is not None else None

        # customData as dict
        custom_fields = {v: None for v in CUSTOM_MAP.values()}
        custom_data_root = task.find('customData')
        if custom_data_root is not None:
            for cv in custom_data_root.findall('customValue'):
                field = cv.find('field/name')
                value = cv.find('value')
                if field is not None and field.text in CUSTOM_MAP:
                    custom_fields[CUSTOM_MAP[field.text]] = value.text if value is not None else None

        orders.append({
            "planfix_id": int(get_text('id')) if get_text('id') else None,
            "title": get_text('title'),
            "description": get_text('description'),
            "importance": get_text('importance'),
            "status": get_text('statusName') or get_text('status'),
            "status_set": int(get_text('statusSet')) if get_text('statusSet') else None,
            "check_result": int(get_text('checkResult')) if get_text('checkResult') else None,
            "type": get_text('type'),
            "owner_id": int(get_text('owner/id')) if get_text('owner/id') else None,
            "owner_name": get_text('owner/name'),
            "parent_id": int(get_text('parent/id')) if get_text('parent/id') else None,
            "template_id": int(get_text('template/id')) if get_text('template/id') else None,
            "project_id": int(get_text('project/id')) if get_text('project/id') else None,
            "project_title": get_text('project/title'),
            "client_id": int(get_text('client/id')) if get_text('client/id') else None,
            "client_name": get_text('client/name'),
            "begin_datetime": parse_date(get_text('beginDateTime')),
            "general": int(get_text('general')) if get_text('general') else None,
            "is_overdued": get_text('isOverdued') == "1",
            "is_close_to_deadline": get_text('isCloseToDeadline') == "1",
            "is_not_accepted_in_time": get_text('isNotAcceptedInTime') == "1",
            "is_summary": get_text('isSummary') == "1",
            "starred": get_text('starred') == "1",
            **custom_fields,
            "updated_at": datetime.now(),
            "is_deleted": False
        })
    return orders

def upsert_orders(orders, supabase_conn):
    if not orders:
        return
    first_item_keys = orders[0].keys()
    all_column_names = list(first_item_keys)
    upsert_data_to_supabase(
        supabase_conn,
        ORDERS_TABLE_NAME,
        ORDERS_PK_COLUMN,
        all_column_names,
        orders
    )
    logger.info(f"Upserted {len(orders)} orders.")

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Planfix orders to Supabase synchronization...")

    required_env_vars = {
        'PLANFIX_API_KEY': os.environ.get('PLANFIX_API_KEY'),
        'PLANFIX_TOKEN': os.environ.get('PLANFIX_TOKEN'),
        'PLANFIX_ACCOUNT': os.environ.get('PLANFIX_ACCOUNT'),
        'SUPABASE_CONNECTION_STRING': os.environ.get('SUPABASE_CONNECTION_STRING'),
        'SUPABASE_HOST': os.environ.get('SUPABASE_HOST'),
        'SUPABASE_DB': os.environ.get('SUPABASE_DB'),
        'SUPABASE_USER': os.environ.get('SUPABASE_USER'),
        'SUPABASE_PASSWORD': os.environ.get('SUPABASE_PASSWORD'),
        'SUPABASE_PORT': os.environ.get('SUPABASE_PORT')
    }
    try:
        check_required_env_vars(required_env_vars)
    except ValueError as e:
        logger.critical(f"Stopping script due to missing environment variables: {e}")
        return

    supabase_conn = None
    try:
        supabase_conn = get_supabase_connection()
        all_orders = []
        all_ids = []
        page = 1
        while True:
            logger.info(f"Fetching page {page} of orders...")
            xml = get_planfix_orders(page)
            if page == 1:
                logger.debug("----- XML-ответ первой страницы -----")
                logger.debug(xml[:2000])
                logger.debug("----- Конец XML-ответа -----")
            orders = parse_orders(xml)
            if not orders:
                break
            upsert_orders(orders, supabase_conn)
            all_orders.extend(orders)
            all_ids.extend([o[ORDERS_PK_COLUMN] for o in orders if o[ORDERS_PK_COLUMN] is not None])
            logger.info(f"Загружено заказов на странице {page}: {len(orders)}")
            if len(orders) < 100:
                break
            page += 1
        logger.info(f"Всего загружено заказов: {len(all_orders)}")
        # Можно добавить пометку удалённых, если нужно
    except psycopg2.Error as e:
        logger.critical(f"Supabase connection error: {e}")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred in main order sync: {e}")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Order synchronization finished.")

if __name__ == "__main__":
    main()
