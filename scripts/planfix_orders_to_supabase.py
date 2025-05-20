import os
import xml.etree.ElementTree as ET
from datetime import datetime
import time # For potential rate limiting
import requests # Explicitly import requests for exception handling
import logging # Added logging
import psycopg2 # Added for exception handling

# Assuming planfix_utils is in the same directory or PYTHONPATH is set up
import scripts.planfix_utils as planfix_utils

# Script-specific constants
ORDER_TEMPLATE_ID = 2420917  # Planfix ID for "Orders" general project template
ORDERS_TABLE_NAME = "planfix_orders"
ORDERS_PK_COLUMN = "planfix_id" # Primary key in Supabase table

# Custom field mapping: Planfix Custom Field ID -> Supabase Column Name
ORDER_CUSTOM_MAP = {
    38165: "order_type",          # Example: Тип заказа
    38171: "delivery_address",    # Example: Адрес доставки
    38173: "delivery_date",       # Example: Дата доставки (needs date parsing)
    41675: "contact_person_id",   # Example: ID контактного лица (клиента) в Planfix
    # Add other custom field IDs and their corresponding Supabase column names here
}

# Get a logger instance for this module
logger = logging.getLogger(__name__)


def get_planfix_orders_xml_page(page: int) -> str:
    """
    Retrieves a page of order (project) data from Planfix as XML.
    Uses ORDER_TEMPLATE_ID.
    """
    request_body_xml = f"""
    <project.getList>
        <template>{ORDER_TEMPLATE_ID}</template>
        <pageCurrent>{page}</pageCurrent>
        <pageSize>50</pageSize> 
    </project.getList>
    """
    return planfix_utils.make_planfix_request(request_body_xml)

def parse_order_data_from_xml(xml_text: str) -> list[dict]:
    """
    Parses XML text and returns a list of order dictionaries.
    Each dictionary includes 'updated_at' and 'is_deleted'.
    Uses ORDER_CUSTOM_MAP, planfix_utils.parse_planfix_date_string, 
    and planfix_utils.get_planfix_status_name.
    """
    orders_data_list = []
    try:
        root = ET.fromstring(xml_text)
        project_elements = root.findall(".//project") 

        for project_element in project_elements:
            order_data = {}
            order_data['planfix_id'] = project_element.findtext("id")
            order_data['title'] = project_element.findtext("title")
            order_data['description'] = project_element.findtext("description")
            
            status_id = project_element.findtext("status/id")
            if status_id:
                # Fetch status name using utility function (already logs internally)
                order_data['status_name'] = planfix_utils.get_planfix_status_name(status_id)
            else:
                order_data['status_name'] = None
            
            order_data['assigner_id'] = project_element.findtext("assigner/id")
            order_data['parent_id'] = project_element.findtext("parent/id") 
            order_data['client_id'] = project_element.findtext("client/id") 
            
            order_data['date_created'] = planfix_utils.parse_planfix_date_string(project_element.findtext("dateCreated"))
            order_data['date_started'] = planfix_utils.parse_planfix_date_string(project_element.findtext("dateStarted"))
            order_data['date_finished'] = planfix_utils.parse_planfix_date_string(project_element.findtext("dateFinished"))
            order_data['date_updated'] = planfix_utils.parse_planfix_date_string(project_element.findtext("dateUpdated"))

            custom_fields_element = project_element.find("customFieldData")
            if custom_fields_element is not None:
                for field_id, column_name in ORDER_CUSTOM_MAP.items():
                    custom_field_node = custom_fields_element.find(f".//custom[id='{field_id}']")
                    value = None
                    if custom_field_node is not None:
                        value_node = custom_field_node.find("value") 
                        if value_node is None: value_node = custom_field_node.find("textValue")
                        if value_node is None: value_node = custom_field_node.find("numberValue")
                        if value_node is None: value_node = custom_field_node.find("dateValue")
                        
                        if value_node is not None and value_node.text:
                            raw_value = value_node.text.strip()
                            if column_name == "delivery_date": 
                                value = planfix_utils.parse_planfix_date_string(raw_value)
                            else:
                                value = raw_value
                        elif column_name == "delivery_date":
                             value = None
                    order_data[column_name] = value
            
            order_data['updated_at'] = datetime.now()
            order_data['is_deleted'] = False
            
            if order_data.get(ORDERS_PK_COLUMN): 
                orders_data_list.append(order_data)
            else:
                logger.warning(f"Order element skipped due to missing primary key '{ORDERS_PK_COLUMN}'. Element: {ET.tostring(project_element, encoding='unicode')[:200]}...")
        return orders_data_list

    except ET.ParseError as e:
        logger.error(f"Error parsing XML for orders: {e}. XML snippet: {xml_text[:200]}...")
        return []
    except Exception as e: 
        logger.error(f"An unexpected error occurred during order parsing: {e}")
        # logger.exception("Details of unexpected error during order parsing:")
        return orders_data_list 

def main():
    """
    Main function to fetch orders from Planfix and upsert to Supabase.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Planfix orders to Supabase synchronization...")

    required_env_vars = {
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_USER_TOKEN': planfix_utils.PLANFIX_USER_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
        'SUPABASE_CONNECTION_STRING': planfix_utils.SUPABASE_CONNECTION_STRING
    }
    try:
        planfix_utils.check_required_env_vars(required_env_vars)
    except ValueError as e:
        logger.critical(f"Stopping script due to missing environment variables: {e}")
        return 

    supabase_conn = None
    try:
        supabase_conn = planfix_utils.get_supabase_connection()
        
        current_page = 0
        all_processed_order_ids = [] 

        while True:
            logger.info(f"Fetching page {current_page} of orders...")
            try:
                xml_data = get_planfix_orders_xml_page(current_page)
                page_orders_data = parse_order_data_from_xml(xml_data)

                if not page_orders_data:
                    if "<project>" not in xml_data and current_page > 0 : 
                         logger.info("No more orders found. Exiting loop.")
                         break
                    elif "<project>" not in xml_data and current_page == 0:
                         logger.info("No orders found on the first page.")
                         break
                    elif not page_orders_data and "<error>" in xml_data : 
                        logger.error("Planfix API returned an error while fetching orders. Stopping.")
                        # Further error details might be logged by make_planfix_request or parse_order_data_from_xml
                        break
                    logger.info("No order data found on this page, assuming end of data or parse error logged previously.")
                    break


                if page_orders_data:
                    for order_dict in page_orders_data:
                        pk_value = order_dict.get(ORDERS_PK_COLUMN)
                        if pk_value is not None:
                            try:
                                all_processed_order_ids.append(int(pk_value)) 
                            except ValueError:
                                logger.warning(f"Could not convert primary key '{pk_value}' to int for order ID. Skipping for deletion marking list.")
                    
                    first_item_keys = page_orders_data[0].keys()
                    all_column_names = list(first_item_keys)

                    if ORDERS_PK_COLUMN not in all_column_names:
                        logger.critical(f"Primary key '{ORDERS_PK_COLUMN}' not in data keys. Skipping upsert for this page.")
                    else:
                        planfix_utils.upsert_data_to_supabase(
                            supabase_conn,
                            ORDERS_TABLE_NAME,
                            ORDERS_PK_COLUMN,
                            all_column_names,
                            page_orders_data
                        )
                        logger.info(f"Upserted {len(page_orders_data)} orders from page {current_page}.")
                else:
                    logger.info(f"No data to upsert for page {current_page}. This might be due to parsing errors for all items on the page or end of data.")

                current_page += 1
                # time.sleep(0.5) 

            except requests.exceptions.RequestException as e: 
                logger.error(f"API request failed when fetching orders on page {current_page}: {e}")
                break 
            except Exception as e: 
                logger.error(f"An unexpected error occurred processing page {current_page} of orders: {e}")
                # logger.exception("Details of unexpected error:")
                break 


        if supabase_conn: 
            if not all_processed_order_ids and current_page == 0:
                logger.info("No orders were found in Planfix. Marking all existing orders in Supabase as deleted.")
                planfix_utils.mark_items_as_deleted_in_supabase(
                    supabase_conn, ORDERS_TABLE_NAME, ORDERS_PK_COLUMN, [] 
                )
            elif all_processed_order_ids:
                logger.info(f"Total processed order IDs for deletion check: {len(all_processed_order_ids)}")
                planfix_utils.mark_items_as_deleted_in_supabase(
                    supabase_conn, ORDERS_TABLE_NAME, ORDERS_PK_COLUMN, all_processed_order_ids 
                )
                logger.info(f"Marked orders not in the current batch as deleted.")
            else:
                logger.warning("No new order IDs were processed successfully. Skipping deletion marking to avoid data loss due to potential errors (e.g. API or parsing issues partway through).")


    except psycopg2.Error as e:
        logger.critical(f"Supabase connection error: {e}")
    except ValueError as e: # From check_required_env_vars
        logger.critical(f"Configuration error (likely missing env vars, logged earlier): {e}")
    except Exception as e: 
        logger.critical(f"An unexpected critical error occurred in main orders sync: {e}")
        # logger.exception("Details of critical unexpected error:")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Orders synchronization finished.")

if __name__ == "__main__":
    main()
