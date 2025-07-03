from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

@app.route('/api/telegram_webhook', methods=['POST', 'GET'])
def telegram_webhook():
    if request.method == 'GET':
        return 'ok', 200

    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    GITHUB_REPO = os.environ.get('GITHUB_REPO')  # например, "krvzdrv/planfix_kpi"
    GITHUB_EVENT_TYPE = "telegram_command"

    data = request.get_json(force=True, silent=True) or {}
    message = data.get('message', {})
    text = message.get('text', '')

    if text.startswith('/premia_current'):
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "event_type": GITHUB_EVENT_TYPE,
            "client_payload": {
                "chat_id": message.get('chat', {}).get('id'),
                "command": "premia_current"
            }
        }
        r = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/dispatches",
            json=payload,
            headers=headers
        )
        return jsonify({"status": "OK"}), 200
    else:
        return jsonify({"status": "Ignored"}), 200 