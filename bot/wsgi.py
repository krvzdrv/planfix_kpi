import os
import sys

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot.api.telegram_webhook import app

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5001)
