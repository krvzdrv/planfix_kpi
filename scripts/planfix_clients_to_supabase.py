import requests
import xml.etree.ElementTree as ET
import psycopg2
import json
from datetime import datetime

# --- Настройки Planfix ---
API_URL = "https://api.planfix.com/xml/"
API_KEY = "393bbe17b391c335356c67ebf586c020"
TOKEN = "964fdc4d11e21792288d39dfab239c1b"
ACCOUNT = "alumineu"
TEMPLATE_ID = 20  # id нужного шаблона компании

# --- Настройки базы данных ---
PG_HOST = "aws-0-eu-central-1.pooler.supabase.com"
PG_DB = "postgres"
PG_USER = "postgres.torlfffeghukusovmxsv"
PG_PASSWORD = "qogheb-jynsi4-mispiH"
PG_PORT = 6543

# Сопоставление custom field name -> column name
custom_map = {
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
    "Обновить KPI": "obnowit_kpi"
}

def get_planfix_companies(page):
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<request method="contact.getList">'
        f'<account>{ACCOUNT}</account>'
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
        API_URL,
        data=body.encode('utf-8'),
        headers=headers,
        auth=(API_KEY, TOKEN)
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
        if is_company and template is not None and template.text == str(TEMPLATE_ID):
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
    custom_fields = {v: None for v in custom_map.values()}
    custom_data_root = contact.find('customData')
    if custom_data_root is not None:
        for cv in custom_data_root.findall('customValue'):
            field = cv.find('field/name')
            value = cv.find('value')
            text = cv.find('text')
            if field is not None and field.text in custom_map:
                # Для поля "Menedżer" сохраняем text (имя), а не value (ID)
                if field.text == "Menedżer":
                    custom_fields[custom_map[field.text]] = text.text if text is not None else None
                else:
                    custom_fields[custom_map[field.text]] = value.text if value is not None else None

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

def upsert_companies(companies):
    if not companies:
        return
    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, port=PG_PORT
    )
    cur = conn.cursor()
    for c in companies:
        cur.execute("""
            INSERT INTO planfix_clients (
                id, userid, general, template_id, name, last_name, is_company, post, email, site, phones, address, description, sex, skype, facebook, vk, telegram_id, telegram_name, group_id, group_name, icq, can_be_worker, can_be_client, user_pic, birthdate, created_date, have_planfix_access, responsible_user_id, responsible_user_name,
                jezyk_komunikacji, subskrypcje_naszych_mediow, data_ostatniego_kontaktu, preferowana_forma_kontaktu, menedzer, ostatni_komentarz, id_custom, miasto, nazwa_pelna, nip, regon, krs, data_rejestracji_w_krs, adres_rejestrowy, ulica_i_numer_domu, kod_pocztowy, forma_prawna, krotka_nazwa, obszar_dzialalnosci, kategoria, zrodlo_leada, aleo, wszystkie_platnosci, olx, youtube, tiktok, data_rozpoczecia_dzialalnosci_w_ceidg, laczna_liczba_ofert, laczna_liczba_zamowien, suma_zamowien_pln_netto, data_ostatniego_zamowienia, wszystkie_zadania, zmien_nazwe_zadania, data_dodania_do_nowi, data_dodania_do_w_trakcie, data_dodania_do_perspektywiczni, data_dodania_do_rezygnacja, data_pierwszego_zamowienia, obnowit_kpi,
                updated_at, is_deleted
            ) VALUES (
                %(id)s, %(userid)s, %(general)s, %(template_id)s, %(name)s, %(last_name)s, %(is_company)s, %(post)s, %(email)s, %(site)s, %(phones)s, %(address)s, %(description)s, %(sex)s, %(skype)s, %(facebook)s, %(vk)s, %(telegram_id)s, %(telegram_name)s, %(group_id)s, %(group_name)s, %(icq)s, %(can_be_worker)s, %(can_be_client)s, %(user_pic)s, %(birthdate)s, %(created_date)s, %(have_planfix_access)s, %(responsible_user_id)s, %(responsible_user_name)s,
                %(jezyk_komunikacji)s, %(subskrypcje_naszych_mediow)s, %(data_ostatniego_kontaktu)s, %(preferowana_forma_kontaktu)s, %(menedzer)s, %(ostatni_komentarz)s, %(id_custom)s, %(miasto)s, %(nazwa_pelna)s, %(nip)s, %(regon)s, %(krs)s, %(data_rejestracji_w_krs)s, %(adres_rejestrowy)s, %(ulica_i_numer_domu)s, %(kod_pocztowy)s, %(forma_prawna)s, %(krotka_nazwa)s, %(obszar_dzialalnosci)s, %(kategoria)s, %(zrodlo_leada)s, %(aleo)s, %(wszystkie_platnosci)s, %(olx)s, %(youtube)s, %(tiktok)s, %(data_rozpoczecia_dzialalnosci_w_ceidg)s, %(laczna_liczba_ofert)s, %(laczna_liczba_zamowien)s, %(suma_zamowien_pln_netto)s, %(data_ostatniego_zamowienia)s, %(wszystkie_zadania)s, %(zmien_nazwe_zadania)s, %(data_dodania_do_nowi)s, %(data_dodania_do_w_trakcie)s, %(data_dodania_do_perspektywiczni)s, %(data_dodania_do_rezygnacja)s, %(data_pierwszego_zamowienia)s, %(obnowit_kpi)s,
                %(updated_at)s, %(is_deleted)s
            )
            ON CONFLICT (id) DO UPDATE SET
                userid=EXCLUDED.userid,
                general=EXCLUDED.general,
                template_id=EXCLUDED.template_id,
                name=EXCLUDED.name,
                last_name=EXCLUDED.last_name,
                is_company=EXCLUDED.is_company,
                post=EXCLUDED.post,
                email=EXCLUDED.email,
                site=EXCLUDED.site,
                phones=EXCLUDED.phones,
                address=EXCLUDED.address,
                description=EXCLUDED.description,
                sex=EXCLUDED.sex,
                skype=EXCLUDED.skype,
                facebook=EXCLUDED.facebook,
                vk=EXCLUDED.vk,
                telegram_id=EXCLUDED.telegram_id,
                telegram_name=EXCLUDED.telegram_name,
                group_id=EXCLUDED.group_id,
                group_name=EXCLUDED.group_name,
                icq=EXCLUDED.icq,
                can_be_worker=EXCLUDED.can_be_worker,
                can_be_client=EXCLUDED.can_be_client,
                user_pic=EXCLUDED.user_pic,
                birthdate=EXCLUDED.birthdate,
                created_date=EXCLUDED.created_date,
                have_planfix_access=EXCLUDED.have_planfix_access,
                responsible_user_id=EXCLUDED.responsible_user_id,
                responsible_user_name=EXCLUDED.responsible_user_name,
                jezyk_komunikacji=EXCLUDED.jezyk_komunikacji,
                subskrypcje_naszych_mediow=EXCLUDED.subskrypcje_naszych_mediow,
                data_ostatniego_kontaktu=EXCLUDED.data_ostatniego_kontaktu,
                preferowana_forma_kontaktu=EXCLUDED.preferowana_forma_kontaktu,
                menedzer=EXCLUDED.menedzer,
                ostatni_komentarz=EXCLUDED.ostatni_komentarz,
                id_custom=EXCLUDED.id_custom,
                miasto=EXCLUDED.miasto,
                nazwa_pelna=EXCLUDED.nazwa_pelna,
                nip=EXCLUDED.nip,
                regon=EXCLUDED.regon,
                krs=EXCLUDED.krs,
                data_rejestracji_w_krs=EXCLUDED.data_rejestracji_w_krs,
                adres_rejestrowy=EXCLUDED.adres_rejestrowy,
                ulica_i_numer_domu=EXCLUDED.ulica_i_numer_domu,
                kod_pocztowy=EXCLUDED.kod_pocztowy,
                forma_prawna=EXCLUDED.forma_prawna,
                krotka_nazwa=EXCLUDED.krotka_nazwa,
                obszar_dzialalnosci=EXCLUDED.obszar_dzialalnosci,
                kategoria=EXCLUDED.kategoria,
                zrodlo_leada=EXCLUDED.zrodlo_leada,
                aleo=EXCLUDED.aleo,
                wszystkie_platnosci=EXCLUDED.wszystkie_platnosci,
                olx=EXCLUDED.olx,
                youtube=EXCLUDED.youtube,
                tiktok=EXCLUDED.tiktok,
                data_rozpoczecia_dzialalnosci_w_ceidg=EXCLUDED.data_rozpoczecia_dzialalnosci_w_ceidg,
                laczna_liczba_ofert=EXCLUDED.laczna_liczba_ofert,
                laczna_liczba_zamowien=EXCLUDED.laczna_liczba_zamowien,
                suma_zamowien_pln_netto=EXCLUDED.suma_zamowien_pln_netto,
                data_ostatniego_zamowienia=EXCLUDED.data_ostatniego_zamowienia,
                wszystkie_zadania=EXCLUDED.wszystkie_zadania,
                zmien_nazwe_zadania=EXCLUDED.zmien_nazwe_zadania,
                data_dodania_do_nowi=EXCLUDED.data_dodania_do_nowi,
                data_dodania_do_w_trakcie=EXCLUDED.data_dodania_do_w_trakcie,
                data_dodania_do_perspektywiczni=EXCLUDED.data_dodania_do_perspektywiczni,
                data_dodania_do_rezygnacja=EXCLUDED.data_dodania_do_rezygnacja,
                data_pierwszego_zamowienia=EXCLUDED.data_pierwszego_zamowienia,
                obnowit_kpi=EXCLUDED.obnowit_kpi,
                updated_at=EXCLUDED.updated_at,
                is_deleted=FALSE
        """, c)
    conn.commit()
    cur.close()
    conn.close()

def main():
    all_companies = []
    page = 1
    while True:
        xml = get_planfix_companies(page)
        companies_xml = parse_companies(xml)
        companies = [company_to_dict(c) for c in companies_xml]
        all_companies.extend(companies)
        print(f"На странице {page}: {len(companies)} компаний с шаблоном {TEMPLATE_ID}")
        root = ET.fromstring(xml)
        contacts_root = root.find('.//contacts')
        if contacts_root is not None and int(contacts_root.attrib.get('count', 0)) < 100:
            break
        page += 1
    print(f"Всего найдено компаний с шаблоном {TEMPLATE_ID}: {len(all_companies)}")
    upsert_companies(all_companies)
    print("Компании успешно выгружены в Supabase.")

if __name__ == "__main__":
    main()
