import os
import re
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
from openai import OpenAI
from collections import defaultdict

# === Ortam değişkenlerini yükle ===
load_dotenv()

# === OpenAI istemcisi ===
client = OpenAI()

# === Slack bilgileri ===
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# === Raporlar ve anahtar kelimeler ===
TABLEAU_REPORTS = {
    "hemen analiz raporu": {
        "keywords": ["hemen", "analiz", "performans", "operasyon", "teslimat"],
        "desc": "Hemen Company operasyon performans analiz raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
    },
    "kapasite raporu": {
        "keywords": ["kapasite", "kko", "doluluk", "kota", "planlama"],
        "desc": "Mağaza / araç / personel kapasite ve verimlilik raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
    },
    "sanal market analizi lfl": {
        "keywords": ["sanal", "market", "lfl", "ciro", "gelir", "sipariş"],
        "desc": "Sanal Market LFL bazlı ciro, sipariş ve operasyonel performans raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1"
    },
    "macrocenter lfl raporu": {
        "keywords": ["macro", "macrocenter", "ciro", "sipariş", "verimlilik"],
        "desc": "Macrocenter LFL bazlı operasyon ve ciro performans raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/MacrocenterLFL"
    }
}

# === Kullanıcı geçmişi ===
conversation_state = defaultdict(dict)

# === Rapor skorlama ===
def keyword_score(message, keywords):
    msg = message.lower()
    return sum(1 for kw in keywords if kw in msg)

# === Eşleşen raporları bul ===
def find_matching_reports(user_message):
    scored = []
    text = user_message.lower()
    for name, info in TABLEAU_REPORTS.items():
        score = keyword_score(text, info["keywords"])
        if score > 0:
            scored.append((score, name, info))
    scored.sort(reverse=True, key=lambda x: x[0])
    return scored  # [(score, name, info), ...]

# === OpenAI doğal konuşma ===
def openai_chat_response(user_message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Kısa ve net konuş. Profesyonel ama samimi ol."},
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return "Şu anda biraz meşgulüm ama 1 dk sonra tekrar deneyebilirsin 🙂"

# === Slack + FastAPI ===
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)

@bolt_app.event("message")
def handle_message_events(body, say, logger):
    try:
        event = body.get("event", {})
        user = event.get("user")
        text = event.get("text", "").strip().lower()

        if not user or event.get("bot_id"):
            return

        # Eğer kullanıcıdan rapor seçimi bekleniyorsa:
        if conversation_state[user].get("awaiting_selection"):
            options = conversation_state[user]["awaiting_selection"]
            if text.isdigit() and 1 <= int(text) <= len(options):
                _, name, rapor = options[int(text)-1]
                say(f"<@{user}> 🔗 **{name.title()}** raporu açıyorum:\n{rapor['link']}")
                conversation_state[user].pop("awaiting_selection")
                return
            else:
                say(f"<@{user}> Geçerli bir numara seçmelisin 🙂")
                return

        # Eşleşen raporları bul
        matches = find_matching_reports(text)

        if matches:
            # Eğer tek rapor eşleşiyorsa -> direkt göster
            if len(matches) == 1:
                _, name, rapor = matches[0]
                say(f"<@{user}> 📊 **{rapor['desc']}**\n🔗 {rapor['link']}")
                return

            # Birden fazla eşleşiyorsa -> seçim iste
            conversation_state[user]["awaiting_selection"] = matches
            say(f"<@{user}> Ciro / performans bilgisi birden fazla raporda mevcut. Hangisini görmek istersin?")
            for i, (_, name, rapor) in enumerate(matches, start=1):
                say(f"{i}) **{name.title()}** – {rapor['desc']}")
            say("Lütfen sadece numara ile cevap ver. 🙂")
            return

        # OpenAI yanıtı
        reply = openai_chat_response(text)
        say(f"<@{user}> {reply}")

    except Exception as e:
        logger.error(e)
        say("Ufak bir hata oldu ama sorun değil, toparlıyorum 🚀")

@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

@api.get("/")
def root():
    return {"status": "Analitik Tableau Slack Asistanı aktif 🚀"}
