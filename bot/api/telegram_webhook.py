from flask import Flask, request, jsonify
import os
import requests
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/api/telegram_webhook', methods=['POST', 'GET'])
def telegram_webhook():
    if request.method == 'GET':
        return 'ok', 200

    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    GITHUB_REPO = os.environ.get('GITHUB_REPO')  # например, "krvzdrv/planfix_kpi"
    GITHUB_EVENT_TYPE = "telegram_command"

    # Проверяем наличие необходимых переменных окружения
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.error("Missing required environment variables: GITHUB_TOKEN or GITHUB_REPO")
        logger.error(f"GITHUB_TOKEN: {'set' if GITHUB_TOKEN else 'not set'}")
        logger.error(f"GITHUB_REPO: {GITHUB_REPO}")
        return jsonify({"error": "Server configuration error"}), 500

    # Логируем конфигурацию (без токена)
    logger.info(f"GitHub Repo: {GITHUB_REPO}")
    logger.info(f"GitHub Token: {'set' if GITHUB_TOKEN else 'not set'}")

    try:
        data = request.get_json(force=True, silent=True) or {}
        message = data.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        user_id = message.get('from', {}).get('id')
        user_name = message.get('from', {}).get('first_name', 'Unknown')

        logger.info(f"Received message from {user_name} (ID: {user_id}): {text}")

        # Обработка команд
        command = None
        
        # Команды помощи
        if text.startswith('/start') or text.startswith('/help'):
            help_text = """
🤖 **Доступные команды бота:**

📊 **Отчеты:**
/report_all - Отправить все отчеты
/report_activity - Отчет об активности
/report_kpi - KPI отчет
/report_bonus - Отчет о премиях (текущий месяц)
/report_bonus_previous - Отчет о премиях (предыдущий месяц)
/report_income - Отчет о доходах
/report_status - Статус клиентов

🔄 **Синхронизация данных:**
/sync_all - Синхронизировать все данные
/sync_clients - Синхронизировать клиентов
/sync_orders - Синхронизировать заказы
/sync_tasks - Синхронизировать задачи

ℹ️ /help - Показать это сообщение
"""
            # Отправляем справку напрямую
            TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
            if TELEGRAM_BOT_TOKEN:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": help_text,
                            "parse_mode": "Markdown"
                        },
                        timeout=10
                    )
                except Exception as e:
                    logger.error(f"Failed to send help message: {e}")
            return jsonify({"status": "OK", "message": "Help sent"}), 200
        
        # Отчеты
        elif text.startswith('/report_all'):
            command = "report_all"
        elif text.startswith('/report_activity'):
            command = "report_activity"
        elif text.startswith('/report_kpi'):
            command = "report_kpi"
        elif text.startswith('/report_bonus_previous'):
            command = "report_bonus_previous"
        elif text.startswith('/report_bonus'):
            command = "report_bonus"
        elif text.startswith('/report_income'):
            command = "report_income"
        elif text.startswith('/report_status'):
            command = "report_status"
            
        # Синхронизация данных
        elif text.startswith('/sync_all'):
            command = "sync_all"
        elif text.startswith('/sync_clients'):
            command = "sync_clients"
        elif text.startswith('/sync_orders'):
            command = "sync_orders"
        elif text.startswith('/sync_tasks'):
            command = "sync_tasks"
            
        # Старые команды для обратной совместимости
        elif text.startswith('/premia_current'):
            command = "report_bonus"
        elif text.startswith('/premia_previous'):
            command = "report_bonus_previous"
            
        else:
            logger.info(f"Ignoring message: {text}")
            return jsonify({"status": "Ignored", "message": "Command not recognized. Use /help for available commands."}), 200
        
        logger.info(f"Processing command: {command}")

        # Отправляем команду в GitHub Actions
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Planfix-KPI-Webhook/1.0"
        }
        payload = {
            "event_type": GITHUB_EVENT_TYPE,
            "client_payload": {
                "chat_id": chat_id,
                "command": command,
                "user_id": user_id,
                "user_name": user_name
            }
        }

        github_url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
        logger.info(f"Sending dispatch to GitHub: {command}")
        logger.info(f"GitHub URL: {github_url}")
        logger.info(f"Payload: {payload}")

        response = requests.post(
            github_url,
            json=payload,
            headers=headers,
            timeout=10
        )

        logger.info(f"GitHub API Response Status: {response.status_code}")
        logger.info(f"GitHub API Response Headers: {dict(response.headers)}")
        logger.info(f"GitHub API Response Body: {response.text}")

        if response.status_code == 204:
            logger.info(f"Successfully dispatched {command} to GitHub Actions")
            return jsonify({
                "status": "OK", 
                "message": f"Command {command} sent to GitHub Actions",
                "command": command
            }), 200
        elif response.status_code == 404:
            logger.error(f"Repository not found: {GITHUB_REPO}")
            logger.error(f"Check if repository exists and token has access")
            return jsonify({
                "error": "Repository not found",
                "github_response": response.text,
                "repository": GITHUB_REPO
            }), 500
        elif response.status_code == 401:
            logger.error(f"Unauthorized: Check GitHub token permissions")
            return jsonify({
                "error": "Unauthorized - check GitHub token",
                "github_response": response.text
            }), 500
        else:
            logger.error(f"Failed to dispatch to GitHub: {response.status_code} - {response.text}")
            return jsonify({
                "error": "Failed to dispatch command",
                "github_response": response.text,
                "status_code": response.status_code
            }), 500

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        return jsonify({"error": "Network error", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    github_repo = os.environ.get('GITHUB_REPO', 'not_set')
    github_token = os.environ.get('GITHUB_TOKEN', 'not_set')
    
    return jsonify({
        "status": "healthy",
        "service": "planfix-kpi-webhook",
        "github_repo": github_repo,
        "github_token": "set" if github_token != "not_set" else "not_set"
    }), 200

@app.route('/debug', methods=['GET'])
def debug_info():
    """Debug endpoint to check configuration"""
    return jsonify({
        "service": "Planfix KPI Telegram Webhook",
        "version": "1.0.0",
        "environment": {
            "GITHUB_REPO": os.environ.get('GITHUB_REPO', 'not_set'),
            "GITHUB_TOKEN": "set" if os.environ.get('GITHUB_TOKEN') else "not_set",
            "PORT": os.environ.get('PORT', '8080')
        },
        "endpoints": {
            "/api/telegram_webhook": "Telegram webhook endpoint",
            "/health": "Health check",
            "/debug": "Debug information",
            "/": "This info"
        }
    }), 200

@app.route('/', methods=['GET'])
def root():
    """Root endpoint"""
    return jsonify({
        "service": "Planfix KPI Telegram Webhook",
        "version": "1.0.0",
        "endpoints": {
            "/api/telegram_webhook": "Telegram webhook endpoint",
            "/health": "Health check",
            "/debug": "Debug information",
            "/": "This info"
        }
    }), 200

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5001))) 