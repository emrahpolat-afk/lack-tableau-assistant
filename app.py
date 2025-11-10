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

# === Kullanıcı bazlı kısa hafıza ===
conversation_history = defaultdict(list)
MAX_HISTORY = 3

# === Basit kelime skoru ===
def keyword_score(message: str, keywords: list[str]) -> int:
    msg = message.lower()
    score = 0
    for kw in keywords:
        if kw in msg:
            score += 1
    return score

# === En iyi raporu bul ===
def find_best_report(user_message: str, user_id: str):
    text = user_message.lower()
    
    # 1️⃣ Macro özel durumu
    if "macro" in text or "macrocenter" in text:
        print("[INFO] 🎯 Macro kelimesi tespit edildi — Macrocenter LFL raporu seçildi.")
        return TABLEAU_REPORTS["macrocenter lfl raporu"]

    # 2️⃣ Diğer raporlar için skor hesapla
    scores = {name: keyword_score(text, info["keywords"]) for name, info in TABLEAU_REPORTS.items()}
    best_match = max(scores, key=scores.get)
    if scores[best_match] > 0:
        print(f"[INFO] 🔍 En yüksek skor: {best_match} ({scores[best_match]})")
        return TABLEAU_REPORTS[best_match]
    return None

# === Slack + FastAPI entegrasyonu ===
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)

# === Slack event listener ===
@bolt_app.event("message")
def handle_message_events(body, say, logger):
    try:
        event = body.get("event", {})
        user = event.get("user")
        text = event.get("text", "").strip().lower()

        if not user or event.get("bot_id"):
            return

        # 💬 Küçük sohbetleri algıla
        greetings = ["merhaba", "selam", "günaydın", "iyi akşamlar", "hey"]
        inquiries = ["nasılsın", "nasıl gidiyor", "ne haber"]
        thanks = ["teşekkür", "sağ ol", "eyvallah"]

        if any(word in text for word in greetings):
            say(f"Merhaba <@{user}> 👋 Nasılsın? Bugün hangi rapora bakalım?")
            return
        if any(word in text for word in inquiries):
            say(f"Gayet iyiyim <@{user}> 😊 Verilerle aramız gayet iyi! Sen nasılsın?")
            return
        if any(word in text for word in thanks):
            say(f"Rica ederim <@{user}> 🙌 Yardımcı olabildiysem ne mutlu!")
            return

        # 🔎 Rapor bulma
        rapor = find_best_report(text, user)
        if rapor:
            say(f"<@{user}> 🧭 Mesajını analiz ettim:\n**{rapor['desc']}**\n🔗 {rapor['link']}")
        else:
            say(f"<@{user}> Bu konuda uygun bir rapor bulamadım 🤔")

    except Exception as e:
        print(f"[Slack Error] {e}")
        say("Bir hata oluştu, tekrar dener misin?")

# === FastAPI endpointleri ===
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

@api.get("/")
def root():
    return {"status": "Smart Tableau Assistant aktif 🚀"}
