#!/usr/bin/env python3
"""
Скрипт для тестирования GitHub API и диагностики проблем
Использование: python scripts/test_github_api.py
"""

import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def test_github_token():
    """Тестирование GitHub токена"""
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("❌ GITHUB_TOKEN не найден в переменных окружения")
        return False
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Planfix-KPI-Test/1.0"
    }
    
    try:
        # Тестируем API пользователя
        response = requests.get("https://api.github.com/user", headers=headers)
        print(f"🔑 Тест GitHub токена: {response.status_code}")
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"   Пользователь: {user_data.get('login')}")
            print(f"   Имя: {user_data.get('name')}")
            return True
        elif response.status_code == 401:
            print("   ❌ Токен недействителен")
            return False
        else:
            print(f"   ❌ Ошибка: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

def test_repository_access():
    """Тестирование доступа к репозиторию"""
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPO')
    
    if not token or not repo:
        print("❌ GITHUB_TOKEN или GITHUB_REPO не найдены")
        return False
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Planfix-KPI-Test/1.0"
    }
    
    try:
        # Тестируем доступ к репозиторию
        response = requests.get(f"https://api.github.com/repos/{repo}", headers=headers)
        print(f"📦 Тест доступа к репозиторию: {response.status_code}")
        
        if response.status_code == 200:
            repo_data = response.json()
            print(f"   Репозиторий: {repo_data.get('full_name')}")
            print(f"   Видимость: {repo_data.get('visibility')}")
            print(f"   Права: {repo_data.get('permissions', {})}")
            return True
        elif response.status_code == 404:
            print(f"   ❌ Репозиторий не найден: {repo}")
            return False
        elif response.status_code == 401:
            print("   ❌ Нет доступа к репозиторию")
            return False
        else:
            print(f"   ❌ Ошибка: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

def test_repository_dispatch():
    """Тестирование repository dispatch"""
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPO')
    
    if not token or not repo:
        print("❌ GITHUB_TOKEN или GITHUB_REPO не найдены")
        return False
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Planfix-KPI-Test/1.0"
    }
    
    payload = {
        "event_type": "test_dispatch",
        "client_payload": {
            "test": True,
            "message": "Test dispatch from diagnostic script"
        }
    }
    
    try:
        # Тестируем repository dispatch
        response = requests.post(
            f"https://api.github.com/repos/{repo}/dispatches",
            json=payload,
            headers=headers
        )
        print(f"🚀 Тест repository dispatch: {response.status_code}")
        
        if response.status_code == 204:
            print("   ✅ Repository dispatch работает")
            return True
        elif response.status_code == 404:
            print(f"   ❌ Repository dispatch не найден для: {repo}")
            print("   Проверьте права токена (нужен repo scope)")
            return False
        elif response.status_code == 401:
            print("   ❌ Неавторизован для repository dispatch")
            return False
        else:
            print(f"   ❌ Ошибка: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

def check_workflow_exists():
    """Проверка существования workflow файла"""
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPO')
    
    if not token or not repo:
        print("❌ GITHUB_TOKEN или GITHUB_REPO не найдены")
        return False
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Planfix-KPI-Test/1.0"
    }
    
    try:
        # Проверяем существование workflow файла
        response = requests.get(
            f"https://api.github.com/repos/{repo}/contents/.github/workflows/telegram-dispatch.yml",
            headers=headers
        )
        print(f"📄 Проверка workflow файла: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ Workflow файл найден")
            return True
        elif response.status_code == 404:
            print("   ❌ Workflow файл не найден")
            print("   Проверьте: .github/workflows/telegram-dispatch.yml")
            return False
        else:
            print(f"   ❌ Ошибка: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

def main():
    print("🔍 Диагностика GitHub API")
    print("=" * 40)
    
    # Проверяем переменные окружения
    print("📋 Переменные окружения:")
    print(f"   GITHUB_TOKEN: {'set' if os.environ.get('GITHUB_TOKEN') else 'not set'}")
    print(f"   GITHUB_REPO: {os.environ.get('GITHUB_REPO', 'not set')}")
    print()
    
    # Запускаем тесты
    token_ok = test_github_token()
    print()
    
    repo_ok = test_repository_access()
    print()
    
    dispatch_ok = test_repository_dispatch()
    print()
    
    workflow_ok = check_workflow_exists()
    print()
    
    # Итоговый результат
    print("📊 Результаты диагностики:")
    print("=" * 40)
    print(f"GitHub Token: {'✅ OK' if token_ok else '❌ FAIL'}")
    print(f"Repository Access: {'✅ OK' if repo_ok else '❌ FAIL'}")
    print(f"Repository Dispatch: {'✅ OK' if dispatch_ok else '❌ FAIL'}")
    print(f"Workflow File: {'✅ OK' if workflow_ok else '❌ FAIL'}")
    
    if token_ok and repo_ok and dispatch_ok and workflow_ok:
        print("\n🎉 Все тесты прошли успешно!")
        print("GitHub API настроен правильно.")
    else:
        print("\n⚠️ Некоторые тесты не прошли.")
        print("\n🔧 Рекомендации:")
        if not token_ok:
            print("- Проверьте GITHUB_TOKEN")
        if not repo_ok:
            print("- Проверьте GITHUB_REPO (формат: owner/repo)")
        if not dispatch_ok:
            print("- Убедитесь, что токен имеет права 'repo'")
        if not workflow_ok:
            print("- Проверьте наличие файла .github/workflows/telegram-dispatch.yml")

if __name__ == "__main__":
    main() 