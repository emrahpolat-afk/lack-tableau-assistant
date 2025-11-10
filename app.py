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

# === Raporlar ===
TABLEAU_REPORTS = {
    "hemen analiz raporu": {
        "keywords": [
            "hemen", "analiz", "performans", "operasyon", "teslimat", "lead time",
            "toplama", "kuryeye atama", "bekleme", "müşteriye gösterilen teslimat süresi",
            "iptal", "yok satmalı", "alternatif ürün", "kayıp tl", "%kayıp",
            "ort sepet", "ortalama sepet", "tso", "cnf", "meta", "nac", "nsf", "pnf", "snf",
            "ortalama sipariş puanı", "ortalama teslimat puanı", "müşteri puanı"
        ],
        "desc": "Hemen Company operasyonunun teslimat, toplama, iptal ve müşteri memnuniyeti performansını analiz eden detaylı operasyon raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
    },
    "kapasite raporu": {
        "keywords": [
            "kapasite", "kko", "doluluk", "boşluk", "verimlilik", "kota", "planlama",
            "araç", "araç sayısı", "motorbike", "panelvan", "araç tipi", "personel kapasitesi",
            "45 dk sipariş", "hemen sipariş", "ad sayısı", "doluluk oranı"
        ],
        "desc": "Mağaza, araç ve personel bazında kapasite kullanım oranlarını, kota planlamalarını ve operasyonel doluluk durumlarını gösteren rapor.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
    },
    "sanal market analizi lfl": {
        "keywords": [
            "sanal", "online", "market", "lfl", "analiz", "ciro", "gelir", "satış", "kayıp", 
            "iptal", "%iptal", "yok satma", "toplama uyumu", "teslimata uyum", "tso",
            "sipariş puanı", "teslimat puanı", "kanal performansı", "hızlı sipariş",
            "araç", "personel", "verimlilik", "servis seviyesi"
        ],
        "desc": "Sanal marketlerin LFL (Like-for-Like) bazında ciro, sipariş, kapasite, iptal, teslimat ve müşteri memnuniyeti metriklerini gösteren detaylı performans raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1"
    },
    "macrocenter lfl raporu": {
        "keywords": [
            "macro", "macrocenter", "lfl", "ciro", "gelir", "satış", "kayıp", 
            "sipariş", "iptal", "şikayet", "kapasite", "verimlilik", "toplama uyumu",
            "teslimata uyum", "mükemmel sipariş", "araç başı", "ad başı",
            "teslimat puanı", "sipariş puanı", "operasyonel performans",
            "servis kalitesi", "kanal karşılaştırma", "macro lfl", "macro raporu"
        ],
        "desc": "Macrocenter mağazalarının LFL bazında ciro, kapasite, sipariş kalitesi ve operasyonel performans metriklerini gösteren detaylı rapor.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/MacrocenterLFL"
    }
}

# === Slack + FastAPI ===
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)

def keyword_score(message, keywords):
    msg = message.lower()
    return sum(1 for kw in keywords if kw in msg)

def find_matching_reports(user_message):
    matches = []
    for name, info in TABLEAU_REPORTS.items():
        score = keyword_score(user_message, info["keywords"])
        if score > 0:
            matches.append((name, info))
    return matches

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
        return "Bir saniye, yeniden deniyorum 🙂"

@bolt_app.event("message")
def handle_message_events(body, say, logger):
    try:
        event = body.get("event", {})
        user = event.get("user")
        text = event.get("text", "").strip()

        if not user or event.get("bot_id"):
            return

        matches = find_matching_reports(text)

        if matches:
            say(f"<@{user}> 📊 İlgili raporlar aşağıda:")
            for name, rapor in matches:
                say(f"• **{name.title()}** → {rapor['desc']}\n🔗 {rapor['link']}")
            return

        reply = openai_chat_response(text)
        say(f"<@{user}> {reply}")

    except Exception as e:
        logger.error(e)
        say("Ufak bir hata oldu ama birkaç saniye içinde toparlarım 🚀")

@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

@api.get("/")
def root():
    return {"status": "Analitik Tableau Slack Asistanı aktif 🚀"}
