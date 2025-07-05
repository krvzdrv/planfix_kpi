#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы webhook через Render
Использование: python scripts/test_render_webhook.py <RENDER_URL>
"""

import sys
import requests
import json
from datetime import datetime

def test_health_check(render_url: str):
    """Тест health check endpoint"""
    try:
        response = requests.get(f"{render_url}/health", timeout=10)
        print(f"🏥 Health check: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {data.get('status')}")
            print(f"   Service: {data.get('service')}")
            print(f"   GitHub Repo: {data.get('github_repo')}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False
    except Exception as e:
        print(f"   Error: {e}")
        return False

def test_root_endpoint(render_url: str):
    """Тест root endpoint"""
    try:
        response = requests.get(render_url, timeout=10)
        print(f"🏠 Root endpoint: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Service: {data.get('service')}")
            print(f"   Version: {data.get('version')}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False
    except Exception as e:
        print(f"   Error: {e}")
        return False

def test_webhook_endpoint(render_url: str):
    """Тест webhook endpoint"""
    try:
        # Симулируем запрос от Telegram
        test_data = {
            "message": {
                "text": "/premia_current",
                "chat": {"id": "123456789"},
                "from": {"id": "987654321", "first_name": "Test User"}
            }
        }
        
        response = requests.post(
            f"{render_url}/api/telegram_webhook",
            json=test_data,
            timeout=10
        )
        
        print(f"🤖 Webhook test: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message')}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False
    except Exception as e:
        print(f"   Error: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Использование: python scripts/test_render_webhook.py <RENDER_URL>")
        print("Пример: python scripts/test_render_webhook.py https://your-app.onrender.com")
        return
    
    render_url = sys.argv[1].rstrip('/')
    
    print("🧪 Тестирование Render Webhook")
    print("=" * 40)
    print(f"URL: {render_url}")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Тестируем endpoints
    health_ok = test_health_check(render_url)
    print()
    
    root_ok = test_root_endpoint(render_url)
    print()
    
    webhook_ok = test_webhook_endpoint(render_url)
    print()
    
    # Итоговый результат
    print("📊 Результаты тестирования:")
    print("=" * 40)
    print(f"Health check: {'✅ OK' if health_ok else '❌ FAIL'}")
    print(f"Root endpoint: {'✅ OK' if root_ok else '❌ FAIL'}")
    print(f"Webhook endpoint: {'✅ OK' if webhook_ok else '❌ FAIL'}")
    
    if health_ok and root_ok and webhook_ok:
        print("\n🎉 Все тесты прошли успешно!")
        print("Render сервис готов к работе.")
    else:
        print("\n⚠️ Некоторые тесты не прошли.")
        print("Проверьте настройки Render сервиса.")

if __name__ == "__main__":
    main() 