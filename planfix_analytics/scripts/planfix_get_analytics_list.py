import os
import sys
import logging
from datetime import datetime
import xml.etree.ElementTree as ET
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.planfix_utils as planfix_utils

logger = logging.getLogger(__name__)

def get_actions_list():
    """
    Получает список действий из ПланФикса через API action.getList
    """
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<request method="action.getList">'
        f'<account>{planfix_utils.PLANFIX_ACCOUNT}</account>'
        '<auth>'
        f'<key>{planfix_utils.PLANFIX_API_KEY}</key>'
        f'<user_token>{planfix_utils.PLANFIX_TOKEN}</user_token>'
        '</auth>'
        '<pageCurrent>1</pageCurrent>'
        '<pageSize>100</pageSize>'
        '</request>'
    )
    
    response = requests.post(
        planfix_utils.PLANFIX_API_URL,
        data=body.encode('utf-8'),
        headers=headers
    )
    response.raise_for_status()
    return response.text

def get_action_details(action_id):
    """
    Получает детали действия из ПланФикса через API action.get
    """
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<request method="action.get">'
        f'<account>{planfix_utils.PLANFIX_ACCOUNT}</account>'
        '<auth>'
        f'<key>{planfix_utils.PLANFIX_API_KEY}</key>'
        f'<user_token>{planfix_utils.PLANFIX_TOKEN}</user_token>'
        '</auth>'
        f'<action>'
        f'<id>{action_id}</id>'
        f'</action>'
        '</request>'
    )
    
    response = requests.post(
        planfix_utils.PLANFIX_API_URL,
        data=body.encode('utf-8'),
        headers=headers
    )
    response.raise_for_status()
    return response.text

def parse_actions_list(xml_text):
    """
    Парсит XML ответ от API action.getList
    """
    root = ET.fromstring(xml_text)
    if root.attrib.get("status") == "error":
        code = root.findtext("code")
        message = root.findtext("message")
        logger.error(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    
    actions = []
    for action in root.findall('.//action'):
        action_id = action.findtext('id')
        name = action.findtext('name')
        description = action.findtext('description')
        
        actions.append({
            "id": int(action_id) if action_id else None,
            "name": name,
            "description": description
        })
    
    return actions

def parse_action_details(xml_text):
    """
    Парсит XML ответ от API action.get для получения аналитик
    """
    root = ET.fromstring(xml_text)
    if root.attrib.get("status") == "error":
        code = root.findtext("code")
        message = root.findtext("message")
        logger.error(f"Ошибка Planfix API: code={code}, message={message}")
        return []
    
    analytics = []
    
    # Ищем аналитики в действии
    for analitic in root.findall('.//analitic'):
        analitic_id = analitic.findtext('id')
        name = analitic.findtext('name')
        description = analitic.findtext('description')
        
        analytics.append({
            "id": int(analitic_id) if analitic_id else None,
            "name": name,
            "description": description
        })
    
    return analytics

def main():
    """
    Главная функция для получения списка аналитик
    """
    logger.info("--- Starting Planfix analytics list retrieval ---")
    
    # Проверяем обязательные переменные окружения
    planfix_utils.check_required_env_vars({
        'PLANFIX_API_KEY': planfix_utils.PLANFIX_API_KEY,
        'PLANFIX_TOKEN': planfix_utils.PLANFIX_TOKEN,
        'PLANFIX_ACCOUNT': planfix_utils.PLANFIX_ACCOUNT,
    })

    try:
        # Получаем список действий
        logger.info("Fetching actions list...")
        actions_xml = get_actions_list()
        actions = parse_actions_list(actions_xml)
        
        logger.info(f"Found {len(actions)} actions")
        
        # Выводим список действий
        print("\n=== Список действий ===")
        for action in actions:
            print(f"ID: {action['id']}, Name: {action['name']}")
            if action['description']:
                print(f"  Description: {action['description']}")
            print()
        
        # Для каждого действия получаем детали и аналитики
        all_analytics = []
        
        for action in actions[:10]:  # Ограничиваем первыми 10 действиями для примера
            if not action['id']:
                continue
                
            logger.info(f"Fetching details for action {action['id']}: {action['name']}")
            
            try:
                action_details_xml = get_action_details(action['id'])
                analytics = parse_action_details(action_details_xml)
                
                if analytics:
                    logger.info(f"Found {len(analytics)} analytics in action {action['id']}")
                    for analytic in analytics:
                        analytic['action_id'] = action['id']
                        analytic['action_name'] = action['name']
                        all_analytics.append(analytic)
                
            except Exception as e:
                logger.error(f"Error getting details for action {action['id']}: {e}")
                continue
        
        # Выводим список аналитик
        print("\n=== Список аналитик ===")
        for analytic in all_analytics:
            print(f"Action: {analytic['action_name']} (ID: {analytic['action_id']})")
            print(f"  Analytic ID: {analytic['id']}")
            print(f"  Name: {analytic['name']}")
            if analytic['description']:
                print(f"  Description: {analytic['description']}")
            print()
        
        # Сохраняем результаты в файл
        with open('analytics_list.txt', 'w', encoding='utf-8') as f:
            f.write("=== Список аналитик ===\n")
            for analytic in all_analytics:
                f.write(f"Action: {analytic['action_name']} (ID: {analytic['action_id']})\n")
                f.write(f"  Analytic ID: {analytic['id']}\n")
                f.write(f"  Name: {analytic['name']}\n")
                if analytic['description']:
                    f.write(f"  Description: {analytic['description']}\n")
                f.write("\n")
        
        logger.info("Analytics list saved to analytics_list.txt")
        logger.info("--- Planfix analytics list retrieval finished successfully ---")

    except Exception as e:
        logger.critical(f"An error occurred in the main process: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    main() 