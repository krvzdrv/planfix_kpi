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
        return jsonify({"error": "Server configuration error"}), 500

    try:
        data = request.get_json(force=True, silent=True) or {}
        message = data.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        user_id = message.get('from', {}).get('id')
        user_name = message.get('from', {}).get('first_name', 'Unknown')

        logger.info(f"Received message from {user_name} (ID: {user_id}): {text}")

        # Обработка команд
        if text.startswith('/premia_current'):
            command = "premia_current"
            logger.info(f"Processing command: {command}")
            
        elif text.startswith('/premia_previous'):
            command = "premia_previous"
            logger.info(f"Processing command: {command}")
            
        else:
            logger.info(f"Ignoring message: {text}")
            return jsonify({"status": "Ignored", "message": "Command not recognized"}), 200

        # Отправляем команду в GitHub Actions
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
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

        logger.info(f"Sending dispatch to GitHub: {command}")
        response = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/dispatches",
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 204:
            logger.info(f"Successfully dispatched {command} to GitHub Actions")
            return jsonify({
                "status": "OK", 
                "message": f"Command {command} sent to GitHub Actions",
                "command": command
            }), 200
        else:
            logger.error(f"Failed to dispatch to GitHub: {response.status_code} - {response.text}")
            return jsonify({
                "error": "Failed to dispatch command",
                "github_response": response.text
            }), 500

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        return jsonify({"error": "Network error"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        "status": "healthy",
        "service": "planfix-kpi-webhook",
        "github_repo": os.environ.get('GITHUB_REPO', 'not_set')
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
            "/": "This info"
        }
    }), 200

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) 