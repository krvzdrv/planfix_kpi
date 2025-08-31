#!/usr/bin/env python3
"""
Тестовый скрипт для проверки команды premia_current
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# GitHub настройки
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'krvzdrv/planfix_kpi')

def test_github_dispatch():
    """Тестирует отправку команды в GitHub Actions"""
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN не найден в переменных окружения")
        return False
    
    try:
        # Отправляем команду в GitHub Actions
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Planfix-KPI-Test/1.0"
        }
        payload = {
            "event_type": "telegram_command",
            "client_payload": {
                "chat_id": "123456789",  # Тестовый chat_id
                "command": "premia_current",
                "user_id": "987654321",  # Тестовый user_id
                "user_name": "Test User"
            }
        }

        github_url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
        print(f"📤 Отправляем команду в GitHub: {payload['client_payload']['command']}")
        print(f"GitHub URL: {github_url}")
        print(f"Payload: {payload}")

        response = requests.post(
            github_url,
            json=payload,
            headers=headers,
            timeout=10
        )

        print(f"📊 GitHub API Response Status: {response.status_code}")
        print(f"GitHub API Response Headers: {dict(response.headers)}")
        print(f"GitHub API Response Body: {response.text}")

        if response.status_code == 204:
            print("✅ Команда успешно отправлена в GitHub Actions")
            return True
        elif response.status_code == 404:
            print(f"❌ Repository не найден: {GITHUB_REPO}")
            print("Проверьте, существует ли репозиторий и есть ли доступ у токена")
            return False
        elif response.status_code == 401:
            print("❌ Неавторизован: Проверьте права GitHub токена")
            return False
        else:
            print(f"❌ Ошибка отправки в GitHub: {response.status_code} - {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

def test_webhook_endpoint():
    """Тестирует webhook endpoint"""
    webhook_url = "https://planfix-kpi-webhook.onrender.com/api/telegram_webhook"
    
    try:
        # Тестируем GET запрос
        response = requests.get(webhook_url, timeout=10)
        print(f"📡 Webhook GET Response: {response.status_code}")
        
        # Тестируем POST запрос с тестовыми данными
        test_data = {
            "message": {
                "text": "/premia_current@SkorifyBot",
                "chat": {"id": "123456789"},
                "from": {"id": "987654321", "first_name": "Test User"}
            }
        }
        
        response = requests.post(webhook_url, json=test_data, timeout=10)
        print(f"📡 Webhook POST Response: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        return response.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка webhook: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Тестирование команды premia_current")
    print("=" * 50)
    
    print("\n1. Тестирование webhook endpoint:")
    test_webhook_endpoint()
    
    print("\n2. Тестирование GitHub dispatch:")
    test_github_dispatch()
