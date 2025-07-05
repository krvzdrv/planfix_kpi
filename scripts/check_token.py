#!/usr/bin/env python3
"""
Быстрая проверка GitHub токена
Использование: python3 scripts/check_token.py <your_token>
"""

import sys
import requests

def check_token(token):
    """Проверка GitHub токена"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Planfix-KPI-Token-Check/1.0"
    }
    
    try:
        # Проверяем токен
        response = requests.get("https://api.github.com/user", headers=headers)
        
        print(f"🔑 Проверка токена: {response.status_code}")
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✅ Токен работает!")
            print(f"   Пользователь: {user_data.get('login')}")
            print(f"   Имя: {user_data.get('name')}")
            print(f"   Email: {user_data.get('email')}")
            
            # Проверяем права
            scopes = response.headers.get('X-OAuth-Scopes', '')
            print(f"   Права: {scopes}")
            
            if 'repo' in scopes:
                print("   ✅ Есть права repo")
            else:
                print("   ❌ Нет прав repo")
                
            if 'workflow' in scopes:
                print("   ✅ Есть права workflow")
            else:
                print("   ❌ Нет прав workflow")
                
            return True
        elif response.status_code == 401:
            print("❌ Токен недействителен")
            return False
        else:
            print(f"❌ Ошибка: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Использование: python3 scripts/check_token.py <your_token>")
        print("Пример: python3 scripts/check_token.py ghp_xxxxxxxxxxxxxxxx")
        return
    
    token = sys.argv[1]
    
    print("🔍 Быстрая проверка GitHub токена")
    print("=" * 40)
    
    if check_token(token):
        print("\n🎉 Токен настроен правильно!")
        print("Теперь добавьте его в переменные окружения Render.")
    else:
        print("\n⚠️ Проблема с токеном.")
        print("См. GITHUB_TOKEN_SETUP.md для инструкций.")

if __name__ == "__main__":
    main() 