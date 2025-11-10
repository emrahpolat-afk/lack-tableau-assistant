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

# === Kullanıcı geçmişi ===
conversation_history = defaultdict(list)
MAX_HISTORY = 3

# === Rapor skoru ===
def keyword_score(message: str, keywords: list[str]) -> int:
    msg = message.lower()
    return sum(1 for kw in keywords if kw in msg)

# === En uygun raporu bul ===
def find_best_report(user_message: str):
    text = user_message.lower()
    scores = {name: keyword_score(text, info["keywords"]) for name, info in TABLEAU_REPORTS.items()}
    best = max(scores, key=scores.get)
    return TABLEAU_REPORTS[best] if scores[best] > 0 else None

# === OpenAI doğal konuşma ===
def openai_chat_response(user_message: str, history: list[str]):
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Sen akıllı, analitik ve sakin bir iş asistanısın. "
                    "Kullanıcıyla profesyonel ama doğal biçimde konuş. "
                    "Veri ve performans odaklı düşünürsün, ancak insani bir sıcaklık da taşırsın. "
                    "Cevapların kısa, net, mantıklı ve dostane olmalı."
                )
            }
        ]

        # kısa geçmişi dahil et
        for h in history[-3:]:
            messages.append({"role": "user", "content": h})
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] OpenAI chat hatası: {e}")
        return "Şu anda biraz meşgulüm ama birkaç saniye içinde analizlere dönerim."

# === Slack + FastAPI ===
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)

@bolt_app.event("message")
def handle_message_events(body, say, logger):
    try:
        event = body.get("event", {})
        user = event.get("user")
        text = event.get("text", "").strip()

        if not user or event.get("bot_id"):
            return

        # konuşma geçmişini kaydet
        conversation_history[user].append(text)
        if len(conversation_history[user]) > MAX_HISTORY:
            conversation_history[user] = conversation_history[user][-MAX_HISTORY:]

        # 1️⃣ Rapor araması
        rapor = find_best_report(text)
        if rapor:
            say(f"<@{user}> 📊 Analiz ettim:\n**{rapor['desc']}**\n🔗 {rapor['link']}")
            return

        # 2️⃣ Aksi halde OpenAI’den doğal yanıt
        reply = openai_chat_response(text, conversation_history[user])
        say(f"<@{user}> {reply}")

    except Exception as e:
        print(f"[Slack Error] {e}")
        say("Bir hata oluştu, ama panik yok — birkaç saniye içinde toparlarım.")

# === FastAPI endpointleri ===
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

@api.get("/")
def root():
    return {"status": "Analitik Tableau Slack Asistanı aktif 🚀"}
