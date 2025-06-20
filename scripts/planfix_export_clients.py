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
                # Для поля "Menedżer" сохраняем text (имя), а не value (ID)
                if field.text == "Menedżer":
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

def get_create_table_sql(table_name, pk_column, columns):
    # Dynamically create the column definitions from the keys of the first data row
    column_definitions = [
        f"id BIGINT PRIMARY KEY",
        f"userid BIGINT",
        f"general BIGINT",
        f"template_id BIGINT",
        f"name TEXT",
        f"last_name TEXT",
        f"is_company BOOLEAN",
        f"post TEXT",
        f"email TEXT",
        f"site TEXT",
        f"phones JSONB",
        f"address TEXT",
        f"description TEXT",
        f"sex TEXT",
        f"skype TEXT",
        f"facebook TEXT",
        f"vk TEXT",
        f"telegram_id TEXT",
        f"telegram_name TEXT",
        f"group_id BIGINT",
        f"group_name TEXT",
        f"icq TEXT",
        f"can_be_worker BOOLEAN",
        f"can_be_client BOOLEAN",
        f"user_pic TEXT",
        f"birthdate TEXT",
        f"created_date TIMESTAMP",
        f"have_planfix_access BOOLEAN",
        f"responsible_user_id BIGINT",
        f"responsible_user_name TEXT",
        f"updated_at TIMESTAMP",
        f"is_deleted BOOLEAN",
        f"jezyk_komunikacji TEXT",
        f"subskrypcje_naszych_mediow TEXT",
        f"data_ostatniego_kontaktu TEXT",
        f"preferowana_forma_kontaktu TEXT",
        f"menedzer TEXT",
        f"ostatni_komentarz TEXT",
        f"id_custom TEXT",
        f"miasto TEXT",
        f"nazwa_pelna TEXT",
        f"nip TEXT",
        f"regon TEXT",
        f"krs TEXT",
        f"data_rejestracji_w_krs TEXT",
        f"adres_rejestrowy TEXT",
        f"ulica_i_numer_domu TEXT",
        f"kod_pocztowy TEXT",
        f"forma_prawna TEXT",
        f"krotka_nazwa TEXT",
        f"obszar_dzialalnosci TEXT",
        f"kategoria TEXT",
        f"zrodlo_leada TEXT",
        f"aleo TEXT",
        f"wszystkie_platnosci TEXT",
        f"olx TEXT",
        f"youtube TEXT",
        f"tiktok TEXT",
        f"data_rozpoczecia_dzialalnosci_w_ceidg TEXT",
        f"laczna_liczba_ofert TEXT",
        f"laczna_liczba_zamowien TEXT",
        f"suma_zamowien_pln_netto TEXT",
        f"data_ostatniego_zamowienia TEXT",
        f"wszystkie_zadania TEXT",
        f"zmien_nazwe_zadania TEXT",
        f"data_dodania_do_nowi TEXT",
        f"data_dodania_do_w_trakcie TEXT",
        f"data_dodania_do_perspektywiczni TEXT",
        f"data_dodania_do_rezygnacja TEXT",
        f"data_pierwszego_zamowienia TEXT",
        f"obnowit_kpi TEXT",
        f"status_wspolpracy TEXT"
    ]
    return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(column_definitions)});"

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Planfix clients to Supabase synchronization...")

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
        supabase_conn = planfix_utils.get_supabase_connection()
        current_page = 1
        all_processed_ids = []
        all_companies = []
        while True:
            logger.info(f"Fetching page {current_page} of clients...")
            try:
                xml = get_planfix_companies(current_page)
                companies_xml = parse_companies(xml)
                companies = [company_to_dict(c) for c in companies_xml]
                all_companies.extend(companies)
                logger.info(f"На странице {current_page}: {len(companies)} компаний с шаблоном {CLIENT_TEMPLATE_ID}")
                if not companies:
                    logger.info("No more companies found. Exiting loop.")
                    break
                for c in companies:
                    pk_value = c.get(CLIENTS_PK_COLUMN)
                    if pk_value:
                        try:
                            all_processed_ids.append(int(pk_value))
                        except ValueError:
                            logger.warning(f"Could not convert primary key '{pk_value}' to int for client ID. Skipping for deletion marking list.")
                root = ET.fromstring(xml)
                contacts_root = root.find('.//contacts')
                if contacts_root is not None and int(contacts_root.attrib.get('count', 0)) < 100:
                    break
                current_page += 1
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching data from Planfix API for clients: {e}")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred processing page {current_page} of clients: {e}")
                break
        if all_companies:
            logger.info("Upserting companies to Supabase...")
            # Use the new dynamic function for CREATE TABLE
            create_sql = get_create_table_sql(CLIENTS_TABLE_NAME, CLIENTS_PK_COLUMN, all_companies[0].keys())
            planfix_utils.create_table_if_not_exists(supabase_conn, create_sql)

            # Ensure all dictionaries have the same keys before upserting
            all_keys = set().union(*(d.keys() for d in all_companies))
            for company in all_companies:
                for key in all_keys:
                    company.setdefault(key, None)

            planfix_utils.upsert_data(supabase_conn, CLIENTS_TABLE_NAME, CLIENTS_PK_COLUMN, all_companies)
            logger.info(f"Upserted {len(all_companies)} companies.")
        else:
            logger.info("No companies to upsert.")
        if supabase_conn:
            if not all_processed_ids and current_page == 1:
                logger.info("No clients were found in Planfix. Marking all existing clients in Supabase as deleted.")
                planfix_utils.mark_items_as_deleted_in_supabase(
                    supabase_conn, CLIENTS_TABLE_NAME, CLIENTS_PK_COLUMN, []
                )
            elif all_processed_ids:
                logger.info(f"Total processed client IDs for deletion check: {len(all_processed_ids)}")
                planfix_utils.mark_items_as_deleted_in_supabase(
                    supabase_conn, CLIENTS_TABLE_NAME, CLIENTS_PK_COLUMN, all_processed_ids
                )
                logger.info(f"Marked clients not in the current batch as deleted.")
            else:
                logger.warning("No new client IDs were processed successfully. Skipping deletion marking to avoid data loss due to potential errors.")
    except psycopg2.Error as e:
        logger.critical(f"Supabase connection error: {e}")
    except ValueError as e:
        logger.critical(f"Configuration error (likely missing env vars, logged earlier): {e}")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred in main client sync: {e}")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Client synchronization finished.")

if __name__ == "__main__":
    main()
