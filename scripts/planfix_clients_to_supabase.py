import os
import xml.etree.ElementTree as ET
from datetime import datetime
import time # For potential rate limiting
import logging # Added logging
import psycopg2 # Added for exception handling
import requests # Added for exception handling

# Assuming planfix_utils is in the same directory or PYTHONPATH is set up
import scripts.planfix_utils as planfix_utils

# Script-specific constants
CLIENT_TEMPLATE_ID = 20 # Planfix ID for "Contacts" template (counterparties)
CLIENTS_TABLE_NAME = "planfix_clients"
CLIENTS_PK_COLUMN = "id" # Primary key in Supabase table

# Custom field mapping: Planfix Custom Field ID -> Supabase Column Name
CLIENT_CUSTOM_MAP = {
    111: "client_segment", # Example: Сегмент клиента
    113: "product_type",   # Example: Тип продукта
    # Add other custom field IDs and their corresponding Supabase column names here
}

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def get_planfix_companies_xml_page(page: int) -> str:
    """
    Retrieves a page of company data from Planfix as XML.
    Uses CLIENT_TEMPLATE_ID.
    """
    request_body_xml = f"""
    <contact.getList>
        <template>{CLIENT_TEMPLATE_ID}</template>
        <pageCurrent>{page}</pageCurrent>
        <pageSize>100</pageSize> 
    </contact.getList>
    """
    return planfix_utils.make_planfix_request(request_body_xml)

def parse_company_elements_from_xml(xml_text: str) -> list[ET.Element]:
    """
    Parses XML text and returns a list of company (contact) XML Elements.
    """
    try:
        root = ET.fromstring(xml_text)
        return root.findall(".//contact")
    except ET.ParseError as e:
        logger.error(f"Error parsing XML for company elements: {e}. XML snippet: {xml_text[:200]}...")
        return []

def convert_company_element_to_dict(contact_element: ET.Element) -> dict:
    """
    Converts a Planfix contact XML element to a dictionary.
    Uses CLIENT_CUSTOM_MAP and planfix_utils.parse_planfix_date_string.
    """
    company_data = {}
    
    company_data['id'] = contact_element.findtext("id")
    company_data['name'] = contact_element.findtext("name")
    company_data['description'] = contact_element.findtext("description")
    company_data['email'] = contact_element.findtext("email")
    company_data['site'] = contact_element.findtext("site")
    company_data['address'] = contact_element.findtext("address")
    company_data['phones'] = contact_element.findtext("phones") 
    company_data['type'] = contact_element.findtext("type") 

    company_data['date_added'] = planfix_utils.parse_planfix_date_string(contact_element.findtext("dateAdded"))
    company_data['date_changed'] = planfix_utils.parse_planfix_date_string(contact_element.findtext("dateChanged"))

    custom_fields_element = contact_element.find("customFieldData")
    if custom_fields_element is not None:
        for field_id, column_name in CLIENT_CUSTOM_MAP.items():
            custom_field_node = custom_fields_element.find(f".//custom[id='{field_id}']")
            value = None
            if custom_field_node is not None:
                value_node = custom_field_node.find("value") 
                if value_node is None: value_node = custom_field_node.find("textValue")
                if value_node is None: value_node = custom_field_node.find("numberValue")
                
                if value_node is not None and value_node.text:
                    value = value_node.text.strip()
            company_data[column_name] = value
    return company_data

def main():
    """
    Main function to fetch clients from Planfix and upsert to Supabase.
    """
    # Basic logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Planfix clients to Supabase synchronization...")

    required_env_vars = {
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_USER_TOKEN': planfix_utils.PLANFIX_USER_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
        'SUPABASE_CONNECTION_STRING': planfix_utils.SUPABASE_CONNECTION_STRING
    }
    try:
        planfix_utils.check_required_env_vars(required_env_vars)
    except ValueError as e:
        # Error already logged by check_required_env_vars
        logger.critical(f"Stopping script due to missing environment variables: {e}")
        return

    supabase_conn = None
    try:
        supabase_conn = planfix_utils.get_supabase_connection()
        
        current_page = 0
        all_processed_ids = [] 

        while True:
            logger.info(f"Fetching page {current_page} of clients...")
            try:
                xml_data = get_planfix_companies_xml_page(current_page)
                company_elements = parse_company_elements_from_xml(xml_data)

                if not company_elements:
                    if "<contact>" not in xml_data and current_page > 0 :
                         logger.info("No more companies found. Exiting loop.")
                         break
                    elif "<contact>" not in xml_data and current_page == 0:
                         logger.info("No companies found on the first page.")
                         break
                    elif not company_elements and "<error>" in xml_data : 
                        logger.error("Planfix API returned an error while fetching companies. Stopping.")
                        break
                    # If parse_company_elements_from_xml returned empty due to parsing error, it logged it already.
                    # If genuinely no elements, it's end of data.
                    logger.info("No company elements found on this page, assuming end of data or parse error logged previously.")
                    break


                page_companies_data = []
                for element in company_elements:
                    company_dict = convert_company_element_to_dict(element)
                    pk_value = company_dict.get(CLIENTS_PK_COLUMN)
                    if pk_value: 
                        company_dict['updated_at'] = datetime.now()
                        company_dict['is_deleted'] = False
                        page_companies_data.append(company_dict)
                        try:
                            all_processed_ids.append(int(pk_value)) # Assuming PK is integer
                        except ValueError:
                            logger.warning(f"Could not convert primary key '{pk_value}' to int for client ID. Skipping for deletion marking list.")
                    else:
                        logger.warning(f"Company element skipped due to missing primary key '{CLIENTS_PK_COLUMN}'. Element: {ET.tostring(element, encoding='unicode')[:200]}...")


                if page_companies_data:
                    first_item_keys = page_companies_data[0].keys()
                    if CLIENTS_PK_COLUMN not in first_item_keys:
                        logger.critical(f"Primary key '{CLIENTS_PK_COLUMN}' not found in processed data keys. Skipping upsert for this page.")
                    else:
                        all_column_names = list(first_item_keys)
                        planfix_utils.upsert_data_to_supabase(
                            supabase_conn,
                            CLIENTS_TABLE_NAME,
                            CLIENTS_PK_COLUMN,
                            all_column_names,
                            page_companies_data
                        )
                        logger.info(f"Upserted {len(page_companies_data)} companies from page {current_page}.")
                else:
                    logger.info(f"No data to upsert for page {current_page}.")

                current_page += 1
                # time.sleep(1) # Optional: to be polite to the API

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching data from Planfix API for clients: {e}")
                break 
            except Exception as e: 
                logger.error(f"An unexpected error occurred processing page {current_page} of clients: {e}")
                # logger.exception("Details of unexpected error:") # For more detailed debugging
                break


        if supabase_conn: # Ensure connection is still valid
            if not all_processed_ids and current_page == 0:
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
        # logger.exception("Details of critical unexpected error:")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Client synchronization finished.")

if __name__ == "__main__":
    main()
