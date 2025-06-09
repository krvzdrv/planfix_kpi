import os
import sys
import logging
from datetime import datetime
import json
import xml.etree.ElementTree as ET
import psycopg2
import requests
from dotenv import load_dotenv
from typing import List, Dict

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

def get_all_status_mapping():
    """
    Получает все доступные статусы из Planfix.
    :return: Словарь {status_id: status_name}
    """
    try:
        params = {
            "account": os.environ.get("PLANFIX_ACCOUNT")
        }

        response_xml = planfix_utils.make_planfix_request("task.getPossibleStatusToChange", params)
        root = ET.fromstring(response_xml)

        status_mapping = {}
        for status_elem in root.findall(".//statusList/status"):
            value_elem = status_elem.find("value")
            title_elem = status_elem.find("title")

            if value_elem is not None and title_elem is not None:
                status_mapping[value_elem.text] = title_elem.text.strip()
                logger.info(f"Found status mapping: {value_elem.text} -> {title_elem.text.strip()}")

        return status_mapping

    except Exception as e:
        logger.error(f"Error fetching all status names: {e}")
        return {}

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
        '  <field>statusSet</field>'
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

def get_status_mapping():
    """Получает маппинг статусов из Planfix API."""
    try:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<request method="task.getStatusList">'
            f'<account>{os.environ.get("PLANFIX_ACCOUNT")}</account>'
            '</request>'
        )
        
        response = requests.post(
            os.environ.get("PLANFIX_API_URL", "https://api.planfix.com/xml/"),
            data=body.encode('utf-8'),
            headers={'Content-Type': 'application/xml'},
            auth=(os.environ.get("PLANFIX_API_KEY"), os.environ.get("PLANFIX_TOKEN"))
        )
        response.raise_for_status()
        
        root = ET.fromstring(response.text)
        if root.attrib.get("status") == "error":
            code = root.findtext("code")
            message = root.findtext("message")
            logger.error(f"Planfix API error getting status list: code={code}, message={message}")
            return {}
            
        status_mapping = {}
        for status in root.findall(".//status"):
            value = status.find("value")
            title = status.find("title")
            if value is not None and title is not None:
                status_mapping[value.text] = title.text.strip()
                logger.info(f"Found status mapping: {value.text} -> {title.text.strip()}")
        
        return status_mapping
        
    except Exception as e:
        logger.error(f"Error getting status mapping: {str(e)}")
        return {}

def get_status_name(task_id: int, status_value: int) -> str:
    """Получает название статуса из Planfix API."""
    try:
        # Формируем XML запрос для получения информации о задаче
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<request method="task.get">'
            f'<account>{os.environ.get("PLANFIX_ACCOUNT")}</account>'
            '<task>'
            f'<id>{task_id}</id>'
            '<general>1</general>'
            '</task>'
            '</request>'
        )
        
        # Отправляем запрос
        response = requests.post(
            os.environ.get("PLANFIX_API_URL", "https://api.planfix.com/xml/"),
            data=body.encode('utf-8'),
            headers={'Content-Type': 'application/xml'},
            auth=(os.environ.get("PLANFIX_API_KEY"), os.environ.get("PLANFIX_TOKEN"))
        )
        response.raise_for_status()
        
        # Парсим XML ответ
        root = ET.fromstring(response.text)
        if root.attrib.get("status") == "error":
            code = root.findtext("code")
            message = root.findtext("message")
            logger.error(f"Planfix API error for task {task_id}: code={code}, message={message}")
            return ""
            
        # Получаем название статуса из customData
        custom_data = root.find(".//task/customData")
        if custom_data is not None:
            for custom_value in custom_data.findall("customValue"):
                field = custom_value.find("field")
                if field is not None and field.find("name") is not None and field.find("name").text == "Статус":
                    value = custom_value.find("text")
                    if value is not None and value.text:
                        status_name = value.text.strip()
                        logger.info(f"Found status name for task {task_id}: {status_name}")
                        return status_name
                
        logger.warning(f"Status name not found in customData for task {task_id}")
        return ""
        
    except Exception as e:
        logger.error(f"Error getting status name for task {task_id}: {str(e)}")
        return ""

def parse_orders(xml_data: str) -> List[Dict]:
    """Парсит XML с заказами и возвращает список словарей."""
    try:
        root = ET.fromstring(xml_data)
        orders = []
        
        for task in root.findall('.//task'):
            try:
                # Получаем основные данные
                task_id = int(task.find('id').text)
                status_value = int(task.find('status').text)
                
                # Получаем название статуса
                status_name = get_status_name(task_id, status_value)
                logger.info(f"Processing order {task_id}: status={status_value}, status_name={status_name}")
                
                # Получаем customData
                custom_data = {}
                custom_data_elem = task.find('customData')
                if custom_data_elem is not None:
                    for item in custom_data_elem.findall('customValue'):
                        name = item.find('name').text
                        value = item.find('value').text
                        custom_data[name] = value
                
                # Формируем данные заказа
                order_data = {
                    'task_id': task_id,
                    'status_id': status_value,
                    'status_name': status_name,
                    'custom_data': custom_data
                }
                
                logger.info(f"Order {task_id} data prepared: {order_data}")
                orders.append(order_data)
                
            except Exception as e:
                logger.error(f"Error processing task: {str(e)}")
                continue
                
        logger.info(f"Successfully parsed {len(orders)} orders")
        return orders
        
    except Exception as e:
        logger.error(f"Error parsing XML: {str(e)}")
        return []

def upsert_orders(orders, supabase_conn):
    """Обновляет или добавляет заказы в Supabase."""
    try:
        logger.info(f"Starting upsert of {len(orders)} orders to Supabase")
        
        for order in orders:
            try:
                # Логируем данные перед отправкой
                logger.info(f"Preparing to upsert order {order.get('planfix_id')}:")
                logger.info(f"  Status ID: {order.get('status')}")
                logger.info(f"  Status Name: {order.get('status_name')}")
                logger.info(f"  Full order data: {json.dumps(order, ensure_ascii=False, indent=2)}")
                
                # Проверяем типы данных
                if order.get('status_name') is not None:
                    logger.info(f"  Status Name type: {type(order.get('status_name'))}")
                    logger.info(f"  Status Name value: '{order.get('status_name')}'")
                
                # Выполняем upsert
                result = supabase_conn.table('orders').upsert(order).execute()
                
                # Логируем результат
                if result.data:
                    logger.info(f"Successfully upserted order {order.get('planfix_id')}")
                    logger.info(f"  Response data: {json.dumps(result.data, ensure_ascii=False)}")
                else:
                    logger.warning(f"No data returned for order {order.get('planfix_id')}")
                    logger.warning(f"  Response: {result}")
                
            except Exception as e:
                logger.error(f"Error upserting order {order.get('planfix_id')}: {str(e)}")
                logger.error(f"  Order data: {json.dumps(order, ensure_ascii=False)}")
                continue
                
        logger.info("Finished upserting orders to Supabase")
        
    except Exception as e:
        logger.error(f"Error in upsert_orders: {str(e)}")
        raise

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Planfix orders to Supabase synchronization...")

    # Добавляем отладочный вывод
    logger.info("Environment variables:")
    logger.info(f"PLANFIX_API_KEY: {os.environ.get('PLANFIX_API_KEY')[:3]}..." if os.environ.get('PLANFIX_API_KEY') else "Not set")
    logger.info(f"PLANFIX_TOKEN: {os.environ.get('PLANFIX_TOKEN')[:3]}..." if os.environ.get('PLANFIX_TOKEN') else "Not set")
    logger.info(f"PLANFIX_ACCOUNT: {os.environ.get('PLANFIX_ACCOUNT')}")
    logger.info(f"PLANFIX_API_URL: {os.environ.get('PLANFIX_API_URL')}")

    required_env_vars = {
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_TOKEN': planfix_utils.PLANFIX_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
        'SUPABASE_CONNECTION_STRING': planfix_utils.SUPABASE_CONNECTION_STRING,
        'SUPABASE_HOST': planfix_utils.SUPABASE_HOST,
        'SUPABASE_DB': planfix_utils.SUPABASE_DB,
        'SUPABASE_USER': planfix_utils.SUPABASE_USER,
        'SUPABASE_PASSWORD': planfix_utils.SUPABASE_PASSWORD,
        'SUPABASE_PORT': planfix_utils.SUPABASE_PORT
    }
    try:
        planfix_utils.check_required_env_vars(required_env_vars)
    except ValueError as e:
        logger.critical(f"Stopping script due to missing environment variables: {e}")
        return

    supabase_conn = None
    try:
        # Загружаем маппинг статусов при запуске
        status_mapping = get_all_status_mapping()
        if not status_mapping:
            logger.error("Failed to load status mapping. Will continue without status names.")
        else:
            logger.info(f"Successfully loaded {len(status_mapping)} status mappings")

        # Получаем соединение с Supabase
        supabase_conn = planfix_utils.get_supabase_connection()
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
