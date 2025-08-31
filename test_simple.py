#!/usr/bin/env python3
"""
Простой тест структуры
"""
import os
import sys

print("🔍 Проверка структуры проекта")
print("=" * 40)

print(f"Текущая директория: {os.getcwd()}")
print(f"Файлы в текущей директории: {os.listdir('.')}")

if os.path.exists('bot'):
    print(f"\n📁 Директория bot существует")
    print(f"Файлы в bot: {os.listdir('bot')}")
    
    if os.path.exists('bot/api'):
        print(f"\n📁 Директория bot/api существует")
        print(f"Файлы в bot/api: {os.listdir('bot/api')}")
        
        if os.path.exists('bot/api/telegram_webhook.py'):
            print(f"\n✅ telegram_webhook.py найден")
        else:
            print(f"\n❌ telegram_webhook.py НЕ найден")
    else:
        print(f"\n❌ Директория bot/api НЕ существует")
else:
    print(f"\n❌ Директория bot НЕ существует")

print(f"\nPython path:")
for i, path in enumerate(sys.path):
    print(f"  {i}: {path}")
