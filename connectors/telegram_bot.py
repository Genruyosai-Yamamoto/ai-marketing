import os
import requests


class TelegramAPIError(RuntimeError):
    pass


def _token():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    return token


def call(method, payload=None, timeout=15):
    token = _token()
    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload or {},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise TelegramAPIError(data.get("description", "Telegram API request failed"))
    return data.get("result")


def send_message(chat_id, text):
    # Telegram text messages have a 4096-character limit.
    return call("sendMessage", {
        "chat_id": str(chat_id),
        "text": str(text)[:4000],
        "disable_web_page_preview": True,
    })


def get_me():
    return call("getMe")


def set_webhook(url, secret_token):
    return call("setWebhook", {
        "url": url,
        "secret_token": secret_token,
        "allowed_updates": ["message"],
    }).lstrip(),
