import os
import xml.etree.ElementTree as ET
from datetime import datetime
import time # For potential rate limiting
import requests # For exception handling
import logging # Added logging
import psycopg2 # Added for exception handling

# Assuming planfix_utils is in the same directory or PYTHONPATH is set up
import scripts.planfix_utils as planfix_utils

# Script-specific constants
TASK_TEMPLATE_ID = 2465239  # Planfix ID for "Tasks" general task template
TASKS_TABLE_NAME = "planfix_tasks"
TASKS_PK_COLUMN = "planfix_id" # Primary key in Supabase table
# No custom map for tasks in this example, but could be added if needed:
# TASK_CUSTOM_MAP = {} 

# Get a logger instance for this module
logger = logging.getLogger(__name__)


def get_planfix_tasks_xml_page(page: int) -> str:
    """
    Retrieves a page of task data from Planfix as XML.
    Uses TASK_TEMPLATE_ID.
    """
    request_body_xml = f"""
    <task.getList>
        <general>{TASK_TEMPLATE_ID}</general> 
        <pageCurrent>{page}</pageCurrent>
        <pageSize>50</pageSize> 
    </task.getList>
    """
    return planfix_utils.make_planfix_request(request_body_xml)

def parse_task_data_from_xml(xml_text: str) -> list[dict]:
    """
    Parses XML text and returns a list of task dictionaries.
    Each dictionary includes 'updated_at' and 'is_deleted'.
    Uses planfix_utils.parse_planfix_date_string and planfix_utils.get_planfix_status_name.
    """
    tasks_data_list = []
    try:
        root = ET.fromstring(xml_text)
        task_elements = root.findall(".//task")

        for task_element in task_elements:
            task_data = {}
            task_data['planfix_id'] = task_element.findtext("id")
            task_data['title'] = task_element.findtext("title")
            task_data['description'] = task_element.findtext("description")
            
            status_id = task_element.findtext("status/id")
            if status_id:
                task_data['status_name'] = planfix_utils.get_planfix_status_name(status_id) # Already logs
            else:
                task_data['status_name'] = None 
            
            task_data['project_id'] = task_element.findtext("project/id") 
            task_data['assigner_id'] = task_element.findtext("assigner/id")
            task_data['owner_id'] = task_element.findtext("owner/id") 
            
            task_data['date_created'] = planfix_utils.parse_planfix_date_string(task_element.findtext("dateCreate")) 
            task_data['start_date'] = planfix_utils.parse_planfix_date_string(task_element.findtext("dateStart"))
            task_data['due_date'] = planfix_utils.parse_planfix_date_string(task_element.findtext("dateEnd")) 
            task_data['date_completed'] = planfix_utils.parse_planfix_date_string(task_element.findtext("dateComplete"))
            task_data['last_update_date'] = planfix_utils.parse_planfix_date_string(task_element.findtext("lastUpdateDate"))
            
            task_data['updated_at'] = datetime.now()
            task_data['is_deleted'] = False
            
            if task_data.get(TASKS_PK_COLUMN): 
                tasks_data_list.append(task_data)
            else:
                logger.warning(f"Task element skipped due to missing primary key '{TASKS_PK_COLUMN}'. Element: {ET.tostring(task_element, encoding='unicode')[:200]}...")
        return tasks_data_list

    except ET.ParseError as e:
        logger.error(f"Error parsing XML for tasks: {e}. XML snippet: {xml_text[:200]}...")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred during task parsing: {e}")
        # logger.exception("Details of unexpected error during task parsing:")
        return tasks_data_list 

def main():
    """
    Main function to fetch tasks from Planfix and upsert to Supabase.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger.info("Starting Planfix tasks to Supabase synchronization...")

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
        all_processed_task_ids = [] 

        while True:
            logger.info(f"Fetching page {current_page} of tasks...")
            try:
                xml_data = get_planfix_tasks_xml_page(current_page)
                page_tasks_data = parse_task_data_from_xml(xml_data)

                if not page_tasks_data:
                    if "<task>" not in xml_data and current_page > 0 :
                         logger.info("No more tasks found. Exiting loop.")
                         break
                    elif "<task>" not in xml_data and current_page == 0:
                         logger.info("No tasks found on the first page.")
                         break
                    elif not page_tasks_data and "<error>" in xml_data :
                        logger.error("Planfix API returned an error while fetching tasks. Stopping.")
                        break
                    logger.info("No task data found on this page, assuming end of data or parse error logged previously.")
                    break
                
                if page_tasks_data:
                    for task_dict in page_tasks_data:
                        pk_value = task_dict.get(TASKS_PK_COLUMN)
                        if pk_value is not None:
                             try: 
                                all_processed_task_ids.append(int(pk_value))
                             except ValueError:
                                logger.warning(f"Task ID '{pk_value}' is not an integer. Skipping for deletion marking list.")
                    
                    first_item_keys = page_tasks_data[0].keys()
                    all_column_names = list(first_item_keys)

                    if TASKS_PK_COLUMN not in all_column_names:
                        logger.critical(f"Primary key '{TASKS_PK_COLUMN}' not in data keys. Skipping upsert for this page.")
                    else:
                        planfix_utils.upsert_data_to_supabase(
                            supabase_conn,
                            TASKS_TABLE_NAME,
                            TASKS_PK_COLUMN,
                            all_column_names,
                            page_tasks_data
                        )
                        logger.info(f"Upserted {len(page_tasks_data)} tasks from page {current_page}.")
                else:
                    logger.info(f"No data to upsert for page {current_page}. This might be due to parsing errors for all items on the page or end of data.")

                current_page += 1
                # time.sleep(0.5) 

            except requests.exceptions.RequestException as e: 
                logger.error(f"API request failed when fetching tasks on page {current_page}: {e}")
                break 
            except Exception as e: 
                logger.error(f"An unexpected error occurred processing page {current_page} of tasks: {e}")
                # logger.exception("Details of unexpected error:")
                break


        if supabase_conn:
            if not all_processed_task_ids and current_page == 0 :
                logger.info("No tasks were found in Planfix. Marking all existing tasks in Supabase as deleted.")
                planfix_utils.mark_items_as_deleted_in_supabase(
                    supabase_conn, TASKS_TABLE_NAME, TASKS_PK_COLUMN, [] 
                )
            elif all_processed_task_ids:
                logger.info(f"Total processed task IDs for deletion check: {len(all_processed_task_ids)}")
                planfix_utils.mark_items_as_deleted_in_supabase(
                    supabase_conn, TASKS_TABLE_NAME, TASKS_PK_COLUMN, all_processed_task_ids 
                )
                logger.info(f"Marked tasks not in the current batch as deleted.") # Already logged in util
            else:
                 logger.warning("No new task IDs were processed successfully. Skipping deletion marking to avoid data loss due to potential errors (e.g. API or parsing issues partway through).")


    except psycopg2.Error as e: 
        logger.critical(f"Supabase connection error: {e}")
    except ValueError as e: # From check_required_env_vars
        logger.critical(f"Configuration error (likely missing env vars, logged earlier): {e}")
    except Exception as e: 
        logger.critical(f"An unexpected critical error occurred in main tasks sync: {e}")
        # logger.exception("Details of critical unexpected error:")
    finally:
        if supabase_conn:
            supabase_conn.close()
            logger.info("Supabase connection closed.")
        logger.info("Tasks synchronization finished.")

if __name__ == "__main__":
    main()
