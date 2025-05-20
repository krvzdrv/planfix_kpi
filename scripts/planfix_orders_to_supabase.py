import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import psycopg2
import json
import os

# --- Настройки Planfix ---
API_URL = "https://api.planfix.com/xml/"
API_KEY = os.environ.get('PLANFIX_API_KEY')
TOKEN = os.environ.get('PLANFIX_TOKEN')
ACCOUNT = os.environ.get('PLANFIX_ACCOUNT')
TEMPLATE_ID = 2420917  # <-- подставьте свой номер шаблона заказа

# --- Настройки базы данных ---
PG_HOST = os.environ.get('SUPABASE_HOST')
PG_DB = os.environ.get('SUPABASE_DB')
PG_USER = os.environ.get('SUPABASE_USER')
PG_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
PG_PORT = os.environ.get('SUPABASE_PORT')

# Проверка наличия всех необходимых переменных окружения
required_env_vars = {
    'PLANFIX_API_KEY': API_KEY,
    'PLANFIX_TOKEN': TOKEN,
    'PLANFIX_ACCOUNT': ACCOUNT,
    'SUPABASE_HOST': PG_HOST,
    'SUPABASE_DB': PG_DB,
    'SUPABASE_USER': PG_USER,
    'SUPABASE_PASSWORD': PG_PASSWORD,
    'SUPABASE_PORT': PG_PORT
}

missing_vars = [var for var, value in required_env_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Отсутствуют следующие переменные окружения: {', '.join(missing_vars)}")

# Сопоставление custom field name -> column name
custom_map = {
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

def get_planfix_orders(page):
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<request method="task.getList">'
        f'<account>{ACCOUNT}</account>'
        f'<pageCurrent>{page}</pageCurrent>'
        f'<pageSize>100</pageSize>'
        '<filters>'
        '  <filter>'
        '    <type>51</type>'
        '    <operator>equal</operator>'
        f'    <value>{TEMPLATE_ID}</value>'
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
        API_URL,
        data=body.encode('utf-8'),
        headers=headers,
        auth=(API_KEY, TOKEN)
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

def get_status_name(status_id):
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<request method="status.get">'
        f'<account>{ACCOUNT}</account>'
        f'<id>{status_id}</id>'
        '</request>'
    )
    response = requests.post(
        API_URL,
        data=body.encode('utf-8'),
        headers=headers,
        auth=(API_KEY, TOKEN)
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    if root.attrib.get("status") == "error":
        print(f"Error getting status name for ID {status_id}: {root.findtext('message')}")
        return None
    return root.findtext('.//name')

def parse_orders(xml_text):
    root = ET.fromstring(xml_text)
    if root.attrib.get("status") == "error":
        code = root.findtext("code")
        message = root.findtext("message")
        print(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    orders = []
    for task in root.findall('.//task'):
        def get_text(tag):
            el = task.find(tag)
            return el.text if el is not None else None

        # Debug: Print full task XML for status-related fields
        task_id = get_text('id')
        status_el = task.find('status')
        status_name_el = task.find('statusName')
        status_set_el = task.find('statusSet')
        
        print(f"\nDebug - Task {task_id} status details:")
        print(f"Status element: {status_el.text if status_el is not None else 'None'}")
        print(f"StatusName element: {status_name_el.text if status_name_el is not None else 'None'}")
        print(f"StatusSet element: {status_set_el.text if status_set_el is not None else 'None'}")
        
        # Get status name from API if not provided in task data
        status_id = get_text('status')
        status_name = get_text('statusName')
        if not status_name and status_id:
            status_name = get_status_name(status_id)
            print(f"Retrieved status name for ID {status_id}: {status_name}")

        # customData as dict
        custom_fields = {v: None for v in custom_map.values()}
        custom_data_root = task.find('customData')
        if custom_data_root is not None:
            for cv in custom_data_root.findall('customValue'):
                field = cv.find('field/name')
                value = cv.find('value')
                if field is not None and field.text in custom_map:
                    custom_fields[custom_map[field.text]] = value.text if value is not None else None

        orders.append({
            "planfix_id": int(get_text('id')),
            "title": get_text('title'),
            "description": get_text('description'),
            "importance": get_text('importance'),
            "status": status_name or status_id,  # Use status name if available, fallback to ID
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
            **custom_fields
        })
    return orders

def upsert_orders(orders):
    if not orders:
        return
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    for o in orders:
        o["updated_at"] = datetime.now()
        o["is_deleted"] = False
        cur.execute("""
            INSERT INTO planfix_orders (
                planfix_id, title, description, importance, status, status_set, check_result, type,
                owner_id, owner_name, parent_id, template_id, project_id, project_title, client_id, client_name,
                begin_datetime, general, is_overdued, is_close_to_deadline, is_not_accepted_in_time, is_summary, starred,
                zadanie_powiazane, kontakt, numer_zamowienia, wartosc_netto, dostawa, oplata, platelshchik, numer_kolejny_fs,
                numer_documentu_fs, faktura_vat_pdf, waluta, schet_kontragenta, data_wystawienia_fs, data_dostawy,
                faktura_proforma_pdf, id_moysklad, zapustit_stsenariy_sozdat_obnovit_dokument_otgruzki, kwota_zaplacona,
                data_wystawienia_pf, numer_documentu_pf, numer_kolejny_pf, zapustit_stsenariy_data_pf, zapustit_stsenariy_data_fs,
                stawka_vat, pln_eur, pln_usd, typ_ceny, kwota_vat, wartosc_brutto, wartosc_netto_pln, menedzher,
                data_wyslania_oferty, data_potwierdzenia_zamowienia, data_rozpoczecia_kompletacji, data_gotowosci_do_wysylki,
                data_wysylki, data_przekazania_do_weryfikacji, data_realizacji, data_anulowania, obliczenie_liczby_ofert_i_zamowien,
                laczna_prowizja_pln, kompletator, laczna_masa_kg, potwierdzenie_wywozu, adres_dostawy, sposob_dostawy,
                zapustit_stsenariy_obnovit_dannye_v_kpi, jezyk, pro_forma_invoice_pdf, vat_invoice_pdf, numer_trackingu,
                updated_at, is_deleted
            ) VALUES (
                %(planfix_id)s, %(title)s, %(description)s, %(importance)s, %(status)s, %(status_set)s, %(check_result)s, %(type)s,
                %(owner_id)s, %(owner_name)s, %(parent_id)s, %(template_id)s, %(project_id)s, %(project_title)s, %(client_id)s, %(client_name)s,
                %(begin_datetime)s, %(general)s, %(is_overdued)s, %(is_close_to_deadline)s, %(is_not_accepted_in_time)s, %(is_summary)s, %(starred)s,
                %(zadanie_powiazane)s, %(kontakt)s, %(numer_zamowienia)s, %(wartosc_netto)s, %(dostawa)s, %(oplata)s, %(platelshchik)s, %(numer_kolejny_fs)s,
                %(numer_documentu_fs)s, %(faktura_vat_pdf)s, %(waluta)s, %(schet_kontragenta)s, %(data_wystawienia_fs)s, %(data_dostawy)s,
                %(faktura_proforma_pdf)s, %(id_moysklad)s, %(zapustit_stsenariy_sozdat_obnovit_dokument_otgruzki)s, %(kwota_zaplacona)s,
                %(data_wystawienia_pf)s, %(numer_documentu_pf)s, %(numer_kolejny_pf)s, %(zapustit_stsenariy_data_pf)s, %(zapustit_stsenariy_data_fs)s,
                %(stawka_vat)s, %(pln_eur)s, %(pln_usd)s, %(typ_ceny)s, %(kwota_vat)s, %(wartosc_brutto)s, %(wartosc_netto_pln)s, %(menedzher)s,
                %(data_wyslania_oferty)s, %(data_potwierdzenia_zamowienia)s, %(data_rozpoczecia_kompletacji)s, %(data_gotowosci_do_wysylki)s,
                %(data_wysylki)s, %(data_przekazania_do_weryfikacji)s, %(data_realizacji)s, %(data_anulowania)s, %(obliczenie_liczby_ofert_i_zamowien)s,
                %(laczna_prowizja_pln)s, %(kompletator)s, %(laczna_masa_kg)s, %(potwierdzenie_wywozu)s, %(adres_dostawy)s, %(sposob_dostawy)s,
                %(zapustit_stsenariy_obnovit_dannye_v_kpi)s, %(jezyk)s, %(pro_forma_invoice_pdf)s, %(vat_invoice_pdf)s, %(numer_trackingu)s,
                %(updated_at)s, %(is_deleted)s
            )
            ON CONFLICT (planfix_id) DO UPDATE SET
                title=EXCLUDED.title,
                description=EXCLUDED.description,
                importance=EXCLUDED.importance,
                status=EXCLUDED.status,
                status_set=EXCLUDED.status_set,
                check_result=EXCLUDED.check_result,
                type=EXCLUDED.type,
                owner_id=EXCLUDED.owner_id,
                owner_name=EXCLUDED.owner_name,
                parent_id=EXCLUDED.parent_id,
                template_id=EXCLUDED.template_id,
                project_id=EXCLUDED.project_id,
                project_title=EXCLUDED.project_title,
                client_id=EXCLUDED.client_id,
                client_name=EXCLUDED.client_name,
                begin_datetime=EXCLUDED.begin_datetime,
                general=EXCLUDED.general,
                is_overdued=EXCLUDED.is_overdued,
                is_close_to_deadline=EXCLUDED.is_close_to_deadline,
                is_not_accepted_in_time=EXCLUDED.is_not_accepted_in_time,
                is_summary=EXCLUDED.is_summary,
                starred=EXCLUDED.starred,
                zadanie_powiazane=EXCLUDED.zadanie_powiazane,
                kontakt=EXCLUDED.kontakt,
                numer_zamowienia=EXCLUDED.numer_zamowienia,
                wartosc_netto=EXCLUDED.wartosc_netto,
                dostawa=EXCLUDED.dostawa,
                oplata=EXCLUDED.oplata,
                platelshchik=EXCLUDED.platelshchik,
                numer_kolejny_fs=EXCLUDED.numer_kolejny_fs,
                numer_documentu_fs=EXCLUDED.numer_documentu_fs,
                faktura_vat_pdf=EXCLUDED.faktura_vat_pdf,
                waluta=EXCLUDED.waluta,
                schet_kontragenta=EXCLUDED.schet_kontragenta,
                data_wystawienia_fs=EXCLUDED.data_wystawienia_fs,
                data_dostawy=EXCLUDED.data_dostawy,
                faktura_proforma_pdf=EXCLUDED.faktura_proforma_pdf,
                id_moysklad=EXCLUDED.id_moysklad,
                zapustit_stsenariy_sozdat_obnovit_dokument_otgruzki=EXCLUDED.zapustit_stsenariy_sozdat_obnovit_dokument_otgruzki,
                kwota_zaplacona=EXCLUDED.kwota_zaplacona,
                data_wystawienia_pf=EXCLUDED.data_wystawienia_pf,
                numer_documentu_pf=EXCLUDED.numer_documentu_pf,
                numer_kolejny_pf=EXCLUDED.numer_kolejny_pf,
                zapustit_stsenariy_data_pf=EXCLUDED.zapustit_stsenariy_data_pf,
                zapustit_stsenariy_data_fs=EXCLUDED.zapustit_stsenariy_data_fs,
                stawka_vat=EXCLUDED.stawka_vat,
                pln_eur=EXCLUDED.pln_eur,
                pln_usd=EXCLUDED.pln_usd,
                typ_ceny=EXCLUDED.typ_ceny,
                kwota_vat=EXCLUDED.kwota_vat,
                wartosc_brutto=EXCLUDED.wartosc_brutto,
                wartosc_netto_pln=EXCLUDED.wartosc_netto_pln,
                menedzher=EXCLUDED.menedzher,
                data_wyslania_oferty=EXCLUDED.data_wyslania_oferty,
                data_potwierdzenia_zamowienia=EXCLUDED.data_potwierdzenia_zamowienia,
                data_rozpoczecia_kompletacji=EXCLUDED.data_rozpoczecia_kompletacji,
                data_gotowosci_do_wysylki=EXCLUDED.data_gotowosci_do_wysylki,
                data_wysylki=EXCLUDED.data_wysylki,
                data_przekazania_do_weryfikacji=EXCLUDED.data_przekazania_do_weryfikacji,
                data_realizacji=EXCLUDED.data_realizacji,
                data_anulowania=EXCLUDED.data_anulowania,
                obliczenie_liczby_ofert_i_zamowien=EXCLUDED.obliczenie_liczby_ofert_i_zamowien,
                laczna_prowizja_pln=EXCLUDED.laczna_prowizja_pln,
                kompletator=EXCLUDED.kompletator,
                laczna_masa_kg=EXCLUDED.laczna_masa_kg,
                potwierdzenie_wywozu=EXCLUDED.potwierdzenie_wywozu,
                adres_dostawy=EXCLUDED.adres_dostawy,
                sposob_dostawy=EXCLUDED.sposob_dostawy,
                zapustit_stsenariy_obnovit_dannye_v_kpi=EXCLUDED.zapustit_stsenariy_obnovit_dannye_v_kpi,
                jezyk=EXCLUDED.jezyk,
                pro_forma_invoice_pdf=EXCLUDED.pro_forma_invoice_pdf,
                vat_invoice_pdf=EXCLUDED.vat_invoice_pdf,
                numer_trackingu=EXCLUDED.numer_trackingu,
                updated_at=EXCLUDED.updated_at,
                is_deleted=FALSE
        """, o)
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    all_orders = []
    page = 1
    while True:
        xml = get_planfix_orders(page)
        if page == 1:
            print("----- XML-ответ первой страницы -----")
            print(xml[:2000])
            print("----- Конец XML-ответа -----")
        orders = parse_orders(xml)
        if not orders:
            break
        upsert_orders(orders)
        all_orders.extend(orders)
        print(f"Загружено заказов на странице {page}: {len(orders)}")
        if len(orders) < 100:
            break
        page += 1
    print(f"Всего загружено заказов: {len(all_orders)}")
