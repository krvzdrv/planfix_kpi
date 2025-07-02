import os
import requests

def handler(request, response):
    GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
    GITHUB_REPO = os.environ['GITHUB_REPO']  # например, "krvzdrv/planfix_kpi"
    GITHUB_EVENT_TYPE = "telegram_command"

    data = request.json()
    message = data.get('message', {})
    text = message.get('text', '')

    # Проверяем команду
    if text.startswith('/premia_current'):
        # Отправляем событие в GitHub Actions
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "event_type": GITHUB_EVENT_TYPE,
            "client_payload": {
                "chat_id": message['chat']['id'],
                "command": "premia_current"
            }
        }
        r = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/dispatches",
            json=payload,
            headers=headers
        )
        response.status_code = 200
        response.text = "OK"
        return response
    else:
        response.status_code = 200
        response.text = "Ignored"
        return response 