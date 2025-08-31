#!/usr/bin/env python3
"""
Простой тест для проверки импортов
"""
import os
import sys

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from bot.api.telegram_webhook import app
    print("✅ Импорт успешен!")
    print(f"App type: {type(app)}")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print(f"Python path: {sys.path}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Files in current directory: {os.listdir('.')}")
    if os.path.exists('bot'):
        print(f"Files in bot directory: {os.listdir('bot')}")
        if os.path.exists('bot/api'):
            print(f"Files in bot/api directory: {os.listdir('bot/api')}")

