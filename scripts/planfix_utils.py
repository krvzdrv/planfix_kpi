import os
import psycopg2
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
from dotenv import load_dotenv

# Get a logger instance for this module
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Environment Variable Loading
PLANFIX_API_KEY = os.environ.get('PLANFIX_API_KEY')
PLANFIX_TOKEN = os.environ.get('PLANFIX_TOKEN')
PLANFIX_ACCOUNT = os.environ.get('PLANFIX_ACCOUNT')
SUPABASE_CONNECTION_STRING = os.environ.get('SUPABASE_CONNECTION_STRING')
SUPABASE_HOST = os.environ.get('SUPABASE_HOST')
SUPABASE_DB = os.environ.get('SUPABASE_DB')
SUPABASE_USER = os.environ.get('SUPABASE_USER')
SUPABASE_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
SUPABASE_PORT = os.environ.get('SUPABASE_PORT')

PLANFIX_API_URL = "https://api.planfix.com/xml/"

def check_required_env_vars(env_vars_dict: dict) -> None:
    """
    Checks if all required environment variables are set.
    Raises ValueError if any variable is missing.
    Logs an error before raising.
    """
    missing_vars = [name for name, value in env_vars_dict.items() if value is None]
    if missing_vars:
        error_message = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_message)
        raise ValueError(error_message)

    # Если SUPABASE_CONNECTION_STRING не указан, проверяем наличие всех параметров подключения
    if not env_vars_dict.get('SUPABASE_CONNECTION_STRING'):
        supabase_params = {
            'SUPABASE_HOST': SUPABASE_HOST,
            'SUPABASE_DB': SUPABASE_DB,
            'SUPABASE_USER': SUPABASE_USER,
            'SUPABASE_PASSWORD': SUPABASE_PASSWORD,
            'SUPABASE_PORT': SUPABASE_PORT
        }
        missing_params = [name for name, value in supabase_params.items() if not value]
        if missing_params:
            error_message = f"Missing required Supabase connection parameters: {', '.join(missing_params)}"
            logger.error(error_message)
            raise ValueError(error_message)

def dict_to_xml(data, root_tag=None):
    """
    Рекурсивно преобразует dict/list/str в XML-строку.
    Если root_tag задан — оборачивает результат в этот тег.
    """
    xml = ''
    if isinstance(data, dict):
        for key, value in data.items():
            xml += dict_to_xml(value, key)
    elif isinstance(data, list):
        for item in data:
            xml += dict_to_xml(item, root_tag)
    else:
        # data — строка или число
        xml += f'<{root_tag}>{data}</{root_tag}>' if root_tag else str(data)
    if root_tag and not isinstance(data, (str, int, float)):
        return xml
    return xml

def make_planfix_request(method_name: str, params: dict) -> str:
    """
    Sends a POST request to Planfix API.
    method_name: имя метода API (например, 'task.getList').
    params: словарь с параметрами запроса.
    """
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    auth_xml = f"""
    <auth>
        <key>{PLANFIX_API_KEY}</key>
        <user_token>{PLANFIX_TOKEN}</user_token>
    </auth>
    """
    
    if not PLANFIX_ACCOUNT:
        logger.error("PLANFIX_ACCOUNT environment variable is not set.")
        raise ValueError("PLANFIX_ACCOUNT environment variable is not set.")

    try:
        # Формируем XML-тело запроса на основе method_name и params
        request_body_xml = f"<{method_name}>"
        request_body_xml += dict_to_xml(params)
        request_body_xml += f"</{method_name}>"
        
        final_xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <request method="{method_name}">
            <account>{PLANFIX_ACCOUNT}</account>
            {auth_xml}
            {request_body_xml}
        </request>
        """
        logger.info(f"Making Planfix API request to method: {method_name}")
        
        response = requests.post(PLANFIX_API_URL, data=final_xml_payload.encode('utf-8'), headers=headers)
        response.raise_for_status()
        
        # Check for Planfix API errors in response
        root = ET.fromstring(response.text)
        error = root.find('.//error')
        if error is not None:
            error_code = error.find('code').text if error.find('code') is not None else 'Unknown'
            error_message = error.find('message').text if error.find('message') is not None else 'Unknown error'
            logger.error(f"Planfix API error: Code {error_code}, Message: {error_message}")
            raise ValueError(f"Planfix API error: {error_message}")
            
        logger.info(f"Planfix API request to {method_name} successful.")
        return response.text
        
    except ET.ParseError as e:
        logger.error(f"XML ParseError for request_body_xml: {e}. Request body: {request_body_xml[:200]}...")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Planfix API request failed: {e}")
        raise

def get_planfix_status_name(status_id: str) -> str | None:
    """
    Gets the name of a Planfix status by its ID.
    Logs errors if fetching or parsing fails.
    """
    if not status_id:
        logger.warning("get_planfix_status_name called with empty status_id.")
        return None

    params = {
        'status': {
            'id': status_id
        }
    }
    try:
        logger.info(f"Fetching status name for ID: {status_id}")
        response_xml = make_planfix_request('status.get', params)
        root = ET.fromstring(response_xml)
        status_name_element = root.find(".//status/name")
        
        if status_name_element is not None and status_name_element.text:
            status_name = status_name_element.text.strip()
            logger.info(f"Successfully fetched status name for ID {status_id}: {status_name}")
            return status_name
        else:
            error_node = root.find(".//error")
            if error_node is not None:
                error_code = error_node.find("code").text if error_node.find("code") is not None else "UnknownCode"
                error_message = error_node.find("message").text if error_node.find("message") is not None else "Unknown error message"
                logger.error(f"Error from Planfix API fetching status ID {status_id}: Code {error_code}, Message: {error_message}")
            else:
                logger.error(f"Could not find status name for ID {status_id} in response, and no error tag found. Response: {response_xml[:200]}...")
            return None
    except requests.exceptions.RequestException as e:
        # Error already logged by make_planfix_request, but can add context
        logger.error(f"Request failed while trying to get status name for ID {status_id}: {e}")
        return None
    except ET.ParseError as e:
        logger.error(f"Failed to parse XML response for status ID {status_id}: {e}. Response: {response_xml[:200]}...")
        return None
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred in get_planfix_status_name for ID {status_id}: {e}")
        return None


def get_supabase_connection():
    """Establishes a connection to the Supabase database."""
    try:
        logger.info("Attempting to connect to Supabase...")
        if SUPABASE_CONNECTION_STRING:
            conn = psycopg2.connect(SUPABASE_CONNECTION_STRING)
        else:
            # Fallback to individual parameters if connection string is not provided
            required_params = {
                'SUPABASE_HOST': SUPABASE_HOST, 'SUPABASE_DB': SUPABASE_DB,
                'SUPABASE_USER': SUPABASE_USER, 'SUPABASE_PASSWORD': SUPABASE_PASSWORD,
                'SUPABASE_PORT': SUPABASE_PORT
            }
            if any(not v for v in required_params.values()):
                raise ValueError(f"Missing one or more Supabase connection parameters: {', '.join(k for k, v in required_params.items() if not v)}")
            conn = psycopg2.connect(
                host=SUPABASE_HOST, dbname=SUPABASE_DB,
                user=SUPABASE_USER, password=SUPABASE_PASSWORD, port=SUPABASE_PORT
            )
        logger.info("Successfully connected to Supabase.")
        return conn
    except (psycopg2.OperationalError, ValueError) as e:
        logger.critical(f"Could not connect to Supabase: {e}")
        raise

def create_table_if_not_exists(conn, create_sql):
    """Executes a CREATE TABLE IF NOT EXISTS statement."""
    try:
        with conn.cursor() as cur:
            logger.info(f"Executing CREATE TABLE statement...")
            cur.execute(create_sql)
            conn.commit()
            logger.info("Table statement executed successfully.")
    except psycopg2.Error as e:
        logger.error(f"Error executing CREATE TABLE statement: {e}")
        conn.rollback()
        raise

def upsert_data_to_supabase(conn: psycopg2.extensions.connection, table_name: str, primary_key_column: str, column_names: list[str], data_list: list[dict]) -> None:
    """
    Upserts data into a Supabase table.
    data_list items already include 'updated_at' and 'is_deleted'.
    Logs information about the upsert process and errors.
    """
    if not data_list:
        logger.info(f"No data provided for upsert to table {table_name}. Skipping.")
        return

    logger.info(f"Starting upsert process for {len(data_list)} records into table '{table_name}'.")
    
    cursor = None # Initialize cursor to None for finally block
    try:
        cursor = conn.cursor()
        
        cols_sql = ", ".join([f'"{col}"' for col in column_names])
        placeholders_sql = ", ".join(["%s"] * len(column_names))
        update_cols = [col for col in column_names if col != primary_key_column]
        update_set_sql = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in update_cols])

        upsert_query = f"""
        INSERT INTO "{table_name}" ({cols_sql})
        VALUES ({placeholders_sql})
        ON CONFLICT ("{primary_key_column}") DO UPDATE SET
        {update_set_sql};
        """
        
        records_to_insert = []
        for record_dict in data_list:
            record_values = [record_dict.get(col) for col in column_names]
            records_to_insert.append(tuple(record_values))

        if records_to_insert:
            # logger.debug(f"Upsert query: {upsert_query}")
            # logger.debug(f"First record to upsert (sample): {records_to_insert[0]}")
            cursor.executemany(upsert_query, records_to_insert)
            conn.commit()
            logger.info(f"Successfully upserted {len(records_to_insert)} records to '{table_name}'.")
        else:
            logger.info(f"No valid records to upsert to '{table_name}' after processing data_list.")

    except Exception as e:
        if conn: # only try to rollback if conn exists
            conn.rollback()
        logger.error(f"Error during Supabase upsert to table '{table_name}': {e}")
        # logger.exception("Exception details during Supabase upsert:") # If more detail is needed
        raise
    finally:
        if cursor:
            cursor.close()

def mark_items_as_deleted_in_supabase(conn: psycopg2.extensions.connection, table_name: str, id_column_name: str, actual_ids: list[int | str]) -> None:
    """
    Marks items as deleted in Supabase table if their IDs are not in actual_ids list.
    Logs the process and any errors.
    """
    logger.info(f"Starting process to mark items as deleted in table '{table_name}'.")
    logger.info(f"Number of actual (active) IDs received: {len(actual_ids)} for table '{table_name}'.")

    cursor = None
    try:
        cursor = conn.cursor()
        if not actual_ids: 
            update_query = f"""
            UPDATE "{table_name}"
            SET is_deleted = TRUE, updated_at = NOW()
            WHERE is_deleted = FALSE; 
            """
            logger.info(f"actual_ids list is empty. Marking all non-deleted items in '{table_name}' as deleted.")
            cursor.execute(update_query)
        else:
            ids_tuple = tuple(actual_ids)
            if not ids_tuple: # Should be caught by 'if not actual_ids' but as a safeguard
                logger.warning(f"actual_ids list resulted in an empty tuple for table {table_name}. No items will be marked as deleted based on 'NOT IN ()' clause, which could be problematic.")
                # This path should ideally not be hit if `actual_ids` is truly empty due to the above `if not actual_ids`.
                # If `actual_ids` contains items that result in an empty tuple (e.g. list of Nones, though type hints suggest int/str),
                # then this warning is relevant.
            
            update_query = f"""
            UPDATE "{table_name}"
            SET is_deleted = TRUE, updated_at = NOW()
            WHERE "{id_column_name}" NOT IN %s AND is_deleted = FALSE;
            """
            # logger.debug(f"Marking items as deleted query: {update_query} with {len(ids_tuple)} IDs.")
            cursor.execute(update_query, (ids_tuple,))

        deleted_count = cursor.rowcount
        conn.commit()
        logger.info(f"Successfully marked {deleted_count} items as deleted in '{table_name}'.")

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error marking items as deleted in Supabase table '{table_name}': {e}")
        raise
    finally:
        if cursor:
            cursor.close()


def parse_planfix_date_string(date_str: str | None) -> datetime | None:
    """
    Parses a Planfix date string into a datetime object.
    Handles formats "%d-%m-%Y %H:%M" and "%d-%m-%Y".
    Logs a warning if parsing fails.
    """
    if not date_str:
        return None
    formats_to_try = ["%d-%m-%Y %H:%M", "%d-%m-%Y"]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    logger.warning(f"Could not parse date string '{date_str}' with known formats.")
    return None
