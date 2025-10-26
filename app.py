import os
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv

# Ortam değişkenlerini yükle
load_dotenv()

# Slack anahtarlarını al
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# Slack ve FastAPI uygulamalarını başlat
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)

# --- Mesaj olaylarını dinle ---
@bolt_app.event("message")
def handle_message_events(body, say, logger):
    event = body.get("event", {})
    user = event.get("user")
    text = event.get("text")

    logger.info(f"Slack'ten mesaj alındı: {text} (gönderen: {user})")

    # Botun kendi mesajına yanıt vermesin
    if user and not event.get("bot_id"):
        say(f"Selam <@{user}>! Mesajını aldım: '{text}'")

# --- Slack event endpoint'i ---
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

# --- Basit test endpoint'i ---
@api.get("/")
def root():
    return {"status": "Bot çalışıyor!"}
