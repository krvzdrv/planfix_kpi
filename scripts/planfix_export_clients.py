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

# --- Константы ---
CLIENT_TEMPLATE_ID = 20
CLIENTS_TABLE_NAME = "planfix_clients"
CLIENTS_PK_COLUMN = "id"

# Сопоставление custom field name -> column name (как в старом скрипте)
CUSTOM_MAP = {
    "Język komunikacji": "jezyk_komunikacji",
    "Subskrypcje naszych mediów": "subskrypcje_naszych_mediow",
    "Data ostatniego kontaktu": "data_ostatniego_kontaktu",
    "Preferowana forma kontaktu": "preferowana_forma_kontaktu",
    "Menedżer": "menedzer",
    "Ostatni komentarz": "ostatni_komentarz",
    "ID": "id_custom",
    "Miasto": "miasto",
    "Nazwa pełna": "nazwa_pelna",
    "NIP": "nip",
    "REGON": "regon",
    "KRS": "krs",
    "Data rejestracji w KRS": "data_rejestracji_w_krs",
    "Adres rejestrowy": "adres_rejestrowy",
    "Ulica i numer domu": "ulica_i_numer_domu",
    "Kod pocztowy": "kod_pocztowy",
    "Forma prawna": "forma_prawna",
    "Krótka nazwa": "krotka_nazwa",
    "Obszar działalności": "obszar_dzialalnosci",
    "Kategoria": "kategoria",
    "Źródło leada": "zrodlo_leada",
    "Aleo": "aleo",
    "Wszystkie płatności": "wszystkie_platnosci",
    "Olx": "olx",
    "Youtube": "youtube",
    "TikTok": "tiktok",
    "Data rozpoczęcia działalności w CEIDG": "data_rozpoczecia_dzialalnosci_w_ceidg",
    "Łączna liczba ofert": "laczna_liczba_ofert",
    "Łączna liczba zamówień": "laczna_liczba_zamowien",
    "Suma zamówień, PLN netto": "suma_zamowien_pln_netto",
    "Data ostatniego zamówienia": "data_ostatniego_zamowienia",
    "Wszystkie zadania": "wszystkie_zadania",
    "Zmień nazwę zadania": "zmien_nazwe_zadania",
    "Data dodania do \"Nowi\"": "data_dodania_do_nowi",
    "Data dodania do \"W trakcie\"": "data_dodania_do_w_trakcie",
    "Data dodania do \"Perspektywiczni\"": "data_dodania_do_perspektywiczni",
    "Data dodania do \"Rezygnacja\"": "data_dodania_do_rezygnacja",
    "Data pierwszego zamówienia": "data_pierwszego_zamowienia",
    "Обновить KPI": "obnowit_kpi",
    "Status współpracy": "status_wspolpracy"
}

# Поля-справочники, для которых нужно брать текстовое значение (text), а не ID (value)
TEXT_VALUE_FIELDS = ["Menedżer", "Status współpracy"]

BASE_COLUMNS = {
    "id": "BIGINT",
    "userid": "BIGINT",
    "general": "BIGINT",
    "template_id": "BIGINT",
    "name": "TEXT",
    "last_name": "TEXT",
    "is_company": "BOOLEAN",
    "post": "TEXT",
    "email": "TEXT",
    "site": "TEXT",
    "phones": "JSONB",
    "address": "TEXT",
    "description": "TEXT",
    "sex": "TEXT",
    "skype": "TEXT",
    "facebook": "TEXT",
    "vk": "TEXT",
    "telegram_id": "TEXT",
    "telegram_name": "TEXT",
    "group_id": "BIGINT",
    "group_name": "TEXT",
    "icq": "TEXT",
    "can_be_worker": "BOOLEAN",
    "can_be_client": "BOOLEAN",
    "user_pic": "TEXT",
    "birthdate": "TEXT",
    "created_date": "TIMESTAMP",
    "have_planfix_access": "BOOLEAN",
    "responsible_user_id": "BIGINT",
    "responsible_user_name": "TEXT",
    "updated_at": "TIMESTAMP",
    "is_deleted": "BOOLEAN"
}

logger = logging.getLogger(__name__)

def get_planfix_companies(page):
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<request method="contact.getList">'
        f'<account>{planfix_utils.PLANFIX_ACCOUNT}</account>'
        f'<pageCurrent>{page}</pageCurrent>'
        f'<pageSize>100</pageSize>'
        '<target>company</target>'
        '<fields>'
        '  <field>lastUpdateDate</field>'
        '  <field>lastCommentDate</field>'
        '  <field>template</field>'
        '  <field>createdDate</field>'
        '  <field>customData</field>'
        '  <field>phones</field>'
        '  <field>responsible</field>'
        '</fields>'
        '</request>'
    )
    response = requests.post(
        planfix_utils.PLANFIX_API_URL,
        data=body.encode('utf-8'),
        headers=headers,
        auth=(planfix_utils.PLANFIX_API_KEY, planfix_utils.PLANFIX_TOKEN)
    )
    response.raise_for_status()
    return response.text

def parse_companies(xml_text):
    root = ET.fromstring(xml_text)
    companies = []
    contacts_root = root.find('.//contacts')
    if contacts_root is None:
        return []
    for contact in contacts_root.findall('contact'):
        template = contact.find('template/id')
        is_company = contact.findtext('isCompany') == "1"
        if is_company and template is not None and template.text == str(CLIENT_TEMPLATE_ID):
            companies.append(contact)
    return companies

def company_to_dict(contact):
    def get_text(tag):
        el = contact.find(tag)
        return el.text if el is not None else None

    # phones as JSON
    phones = []
    phones_root = contact.find('phones')
    if phones_root is not None:
        for phone in phones_root.findall('phone'):
            phone_data = {
                "number": phone.findtext('number'),
                "typeId": phone.findtext('typeId'),
                "typeName": phone.findtext('typeName')
            }
            phones.append(phone_data)

    # custom fields
    custom_fields = {v: None for v in CUSTOM_MAP.values()}
    custom_data_root = contact.find('customData')

    if custom_data_root is not None:
        for cv in custom_data_root.findall('customValue'):
            field = cv.find('field/name')
            value = cv.find('value')
            text = cv.find('text')
            if field is not None and field.text in CUSTOM_MAP:
                # Для полей-справочников сохраняем text (имя), а не value (ID)
                if field.text in TEXT_VALUE_FIELDS:
                    custom_fields[CUSTOM_MAP[field.text]] = text.text if text is not None else None
                else:
                    custom_fields[CUSTOM_MAP[field.text]] = value.text if value is not None else None

    # responsible user
    responsible_user_id = None
    responsible_user_name = None
    responsible = contact.find('responsible')
    if responsible is not None:
        user = responsible.find('.//user')
        if user is not None:
            responsible_user_id = user.findtext('id')
            responsible_user_name = user.findtext('name')

    # group
    group_id = get_text('group/id')
    group_name = get_text('group/name')

    # created_date
    created_date = get_text('createdDate')
    if created_date:
        try:
            created_date = datetime.strptime(created_date, "%d-%m-%Y %H:%M")
        except Exception:
            try:
                created_date = datetime.strptime(created_date, "%d-%m-%Y")
            except Exception:
                created_date = None
    else:
        created_date = None

    base = {
        "id": int(get_text('id')) if get_text('id') else None,
        "userid": int(get_text('userid')) if get_text('userid') else None,
        "general": int(get_text('general')) if get_text('general') else None,
        "template_id": int(get_text('template/id')) if get_text('template/id') else None,
        "name": get_text('name'),
        "last_name": get_text('lastName'),
        "is_company": get_text('isCompany') == "1",
        "post": get_text('post'),
        "email": get_text('email'),
        "site": get_text('site'),
        "phones": json.dumps(phones) if phones else None,
        "address": get_text('address'),
        "description": get_text('description'),
        "sex": get_text('sex'),
        "skype": get_text('skype'),
        "facebook": get_text('facebook'),
        "vk": get_text('vk'),
        "telegram_id": get_text('telegramId'),
        "telegram_name": get_text('telegramName'),
        "group_id": int(group_id) if group_id else None,
        "group_name": group_name,
        "icq": get_text('icq'),
        "can_be_worker": get_text('canBeWorker') == "1",
        "can_be_client": get_text('canBeClient') == "1",
        "user_pic": get_text('userPic'),
        "birthdate": get_text('birthdate'),
        "created_date": created_date,
        "have_planfix_access": get_text('havePlanfixAccess') == "1",
        "responsible_user_id": int(responsible_user_id) if responsible_user_id else None,
        "responsible_user_name": responsible_user_name,
        "updated_at": datetime.now(),
        "is_deleted": False
    }
    base.update(custom_fields)
    return base

def get_create_table_sql(table_name, pk_column, columns_map):
    column_definitions = [f'"{name}" {dtype}' for name, dtype in columns_map.items()]
    # Manually set the primary key
    for i, col_def in enumerate(column_definitions):
        if col_def.startswith(f'"{pk_column}"'):
            column_definitions[i] = f'"{pk_column}" BIGINT PRIMARY KEY'
            break
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(column_definitions)});'

def main():
    """Главная функция для экспорта клиентов из Planfix в Supabase."""
    logger.info("--- Starting Planfix clients export ---")
    planfix_utils.check_required_env_vars({
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_TOKEN': planfix_utils.PLANFIX_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
    })

    conn = None
    try:
        page = 1
        all_companies_data = []
        all_company_ids = []

        while True:
            logger.info(f"Fetching page {page} of companies...")
            xml_text = get_planfix_companies(page)
            companies = parse_companies(xml_text)
            if not companies:
                logger.info("No more companies found.")
                break

            for company_xml in companies:
                company_data = company_to_dict(company_xml)
                if company_data and company_data.get("id"):
                    all_companies_data.append(company_data)
                    all_company_ids.append(company_data["id"])
            
            page += 1
            # break # для отладки

        logger.info(f"Total companies (templateId={CLIENT_TEMPLATE_ID}) processed: {len(all_companies_data)}")

        if not all_companies_data:
            logger.info("No companies to update. Exiting.")
            return

        conn = planfix_utils.get_supabase_connection()

        # --- Schema Management ---
        # 1. Define all columns and their types
        all_columns = BASE_COLUMNS.copy()
        custom_columns_map = {v: "TEXT" for v in CUSTOM_MAP.values()} # Treat all custom as TEXT for simplicity
        all_columns.update(custom_columns_map)

        # 2. Create table if it doesn't exist
        create_sql = get_create_table_sql(CLIENTS_TABLE_NAME, CLIENTS_PK_COLUMN, all_columns)
        planfix_utils.create_table_if_not_exists(conn, create_sql)

        # 3. Add any missing columns to the existing table
        planfix_utils.add_missing_columns(conn, CLIENTS_TABLE_NAME, all_columns)

        # --- Data Upsert ---
        # Get final list of columns from the DB in case some were added
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {CLIENTS_TABLE_NAME} LIMIT 0")
            db_column_names = [desc[0] for desc in cur.description]

        planfix_utils.upsert_data_to_supabase(
            conn,
            CLIENTS_TABLE_NAME,
            CLIENTS_PK_COLUMN,
            db_column_names,
            all_companies_data
        )

        # --- Mark Deleted ---
        planfix_utils.mark_items_as_deleted_in_supabase(
            conn,
            CLIENTS_TABLE_NAME,
            CLIENTS_PK_COLUMN,
            all_company_ids
        )

        logger.info("--- Planfix clients export finished successfully ---")

    except Exception as e:
        logger.critical(f"An error occurred in the main process: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            logger.info("Supabase connection closed.")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main()
