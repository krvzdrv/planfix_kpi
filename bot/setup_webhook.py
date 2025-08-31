#!/usr/bin/env python3
"""
Скрипт для настройки webhook'а в Telegram
"""
import os
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv('env.example')

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = "https://planfix-kpi-webhook.onrender.com/api/telegram_webhook"

def setup_webhook():
    """Настраивает webhook для Telegram бота"""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return False
    
    try:
        # Устанавливаем webhook
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
        data = {
            "url": WEBHOOK_URL,
            "allowed_updates": ["message"]
        }
        
        response = requests.post(url, json=data)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('ok'):
            print(f"✅ Webhook успешно настроен: {WEBHOOK_URL}")
            print(f"Описание: {result.get('description', 'N/A')}")
            return True
        else:
            print(f"❌ Ошибка настройки webhook: {result.get('description', 'Unknown error')}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

def get_webhook_info():
    """Получает информацию о текущем webhook'е"""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
        response = requests.get(url)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('ok'):
            webhook_info = result.get('result', {})
            print("📋 Информация о webhook:")
            print(f"URL: {webhook_info.get('url', 'Not set')}")
            print(f"Pending updates: {webhook_info.get('pending_update_count', 0)}")
            print(f"Last error: {webhook_info.get('last_error_message', 'None')}")
            return True
        else:
            print(f"❌ Ошибка получения информации: {result.get('description', 'Unknown error')}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Настройка webhook'а для Telegram бота")
    print("=" * 50)
    
    print("\n1. Текущая информация о webhook:")
    get_webhook_info()
    
    print("\n2. Настройка webhook:")
    setup_webhook()
    
    print("\n3. Обновленная информация о webhook:")
    get_webhook_info()
