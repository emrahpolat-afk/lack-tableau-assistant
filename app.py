import os
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# --- OpenAI istemcisi ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Tableau rapor bağlantıları ---
TABLEAU_LINKS = {
    "hemen analiz raporu": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz",
    "sanal market analiz raporu": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1",
    "kapasite raporu": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
}


def find_tableau_report(user_message: str):
    """Kullanıcının mesajını analiz edip en uygun raporu bulur."""
    prompt = f"""
    Kullanıcının mesajı: "{user_message}"
    Aşağıdaki raporlardan hangisi bu soruya en uygun?
    - Hemen Analiz Raporu
    - Sanal Market Analiz Raporu
    - Kapasite Raporu

    Sadece rapor adını döndür (örnek: 'Hemen Analiz Raporu').
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    rapor_adi = response.choices[0].message.content.strip().lower()
    return TABLEAU_LINKS.get(rapor_adi, None)


# --- Ortam değişkenlerini yükle ---
load_dotenv()

# --- Slack anahtarlarını al ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# --- Slack ve FastAPI uygulamalarını başlat ---
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)


# --- Mesaj olaylarını dinle ---
@bolt_app.event("message")
def handle_message_events(body, say, logger):
    event = body.get("event", {})
    user = event.get("user")
    text = event.get("text")

    # Botun kendi mesajına yanıt vermesin
    if user and not event.get("bot_id"):
        rapor_linki = find_tableau_report(text)
        if rapor_linki:
            say(f"<@{user}> İlgili raporu buldum: {rapor_linki}")
        else:
            say(f"<@{user}> Mesajını aldım ama uygun bir rapor bulamadım 🤔 Daha net sorabilir misin?")


# --- Slack event endpoint'i ---
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)


# --- Basit test endpoint'i ---
@api.get("/")
def root():
    return {"status": "Bot çalışıyor!"}
