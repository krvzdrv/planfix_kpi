#!/usr/bin/env python3
"""
Скрипт для настройки webhook в Telegram
Использование: python scripts/setup_telegram_webhook.py <RENDER_URL>
"""

import sys
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def setup_webhook(render_url: str):
    """Настройка webhook в Telegram"""
    
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return False
    
    webhook_url = f"{render_url}/api/telegram_webhook"
    
    print(f"🔧 Настройка webhook для бота...")
    print(f"URL: {webhook_url}")
    
    try:
        # Устанавливаем webhook
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={"url": webhook_url}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print("✅ Webhook успешно настроен!")
                print(f"Webhook URL: {result.get('result', {}).get('url')}")
                return True
            else:
                print(f"❌ Ошибка при настройке webhook: {result.get('description')}")
                return False
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")
            print(f"Ответ: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при настройке webhook: {e}")
        return False

def check_webhook():
    """Проверка текущего webhook"""
    
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return
    
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                webhook_info = result.get('result', {})
                print("📋 Информация о webhook:")
                print(f"URL: {webhook_info.get('url', 'Не настроен')}")
                print(f"Активен: {webhook_info.get('ok', False)}")
                print(f"Ошибок: {webhook_info.get('last_error_count', 0)}")
                if webhook_info.get('last_error_message'):
                    print(f"Последняя ошибка: {webhook_info.get('last_error_message')}")
            else:
                print(f"❌ Ошибка при получении информации о webhook: {result.get('description')}")
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Ошибка при проверке webhook: {e}")

def main():
    if len(sys.argv) != 2:
        print("Использование: python scripts/setup_telegram_webhook.py <RENDER_URL>")
        print("Пример: python scripts/setup_telegram_webhook.py https://your-app.onrender.com")
        return
    
    render_url = sys.argv[1].rstrip('/')
    
    print("🤖 Настройка Telegram Webhook")
    print("=" * 40)
    
    # Проверяем текущий webhook
    print("\n📋 Текущий webhook:")
    check_webhook()
    
    # Настраиваем новый webhook
    print(f"\n🔧 Настройка нового webhook...")
    if setup_webhook(render_url):
        print("\n✅ Webhook настроен успешно!")
        
        # Проверяем результат
        print("\n📋 Обновленная информация о webhook:")
        check_webhook()
    else:
        print("\n❌ Не удалось настроить webhook")

if __name__ == "__main__":
    main() 