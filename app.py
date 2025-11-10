import os
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
from openai import OpenAI

# === Ortam değişkenlerini yükle ===
load_dotenv()

# === OpenAI istemcisi ===
client = OpenAI()

# === Slack bilgileri ===
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# === Rapor listesi ve anahtar kelimeler ===
TABLEAU_REPORTS = {
    "hemen analiz raporu": {
        "keywords": ["hemen", "analiz", "ciro", "iptal", "sipariş", "performans", "günlük", "trend"],
        "desc": "Günlük performans, ciro, sipariş ve iptal oranlarını gösteren genel analiz raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
    },
    "kapasite raporu": {
        "keywords": ["kapasite", "doluluk", "mağaza", "planlama", "yük", "operasyon"],
        "desc": "Mağaza bazında kapasite kullanım oranlarını ve planlanan kapasiteyi gösterir.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
    },
    "macronline poc raporu": {
        "keywords": ["macronline", "poc", "deneme", "yeni model", "proje", "test"],
        "desc": "Macronline projesi kapsamında yapılan test ve pilot sonuçlarını gösterir.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/MACRONLINEPOCRaporu/MACRONLINEPOCRAPORU"
    },
    "macrocenter lfl raporu": {
        "keywords": ["macrocenter", "lfl", "ciro", "geçen yıl", "karşılaştırma", "büyüme"],
        "desc": "Macrocenter mağazalarının geçen yıla göre LFL (Like-for-Like) performansını gösterir.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/Macrocenter/KAPASITEKULLANIMI"
    }
}

# === OpenAI destekli eşleştirme fonksiyonu ===
def find_best_report(user_message: str):
    """Kullanıcı mesajını analiz eder, en uygun raporu seçer."""
    try:
        prompt = f"""
Kullanıcının mesajı: "{user_message}"

Elinde aşağıdaki raporlar ve onların anahtar kelimeleri var:

{{
{os.linesep.join([f'- {r}: {info["keywords"]}' for r, info in TABLEAU_REPORTS.items()])}
}}

Kullanıcının mesajına göre en alakalı raporu seç.
Sadece rapor adını döndür (örnek: "hemen analiz raporu").
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        rapor_adi = response.choices[0].message.content.strip().lower()
        print(f"[INFO] 🤖 OpenAI seçimi: {rapor_adi}")

        return TABLEAU_REPORTS.get(rapor_adi)

    except Exception as e:
        print(f"[ERROR] OpenAI eşleştirme hatası: {e}")
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
        text = event.get("text")

        if user and not event.get("bot_id"):
            rapor = find_best_report(text)
            if rapor:
                say(f"""
<@{user}> 🧭 Mesajını analiz ettim!
**{rapor['desc']}**
🔗 {rapor['link']}
""")
            else:
                say(f"<@{user}> Bu konuda uygun bir rapor bulamadım 🤔 Anahtar kelimeleri biraz farklı deneyebilirsin.")
    except Exception as e:
        print(f"[Slack Error] {e}")
        try:
            say("Bir hata oluştu, tekrar dener misin?")
        except Exception:
            pass

# === FastAPI endpointleri ===
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

@api.get("/")
def root():
    return {"status": "Anahtar kelime temelli OpenAI + Slack asistan aktif 🚀"}

@api.get("/healthz")
def health():
    return {"ok": True}

@api.get("/debug_keywords")
def debug_keywords():
    """Raporların anahtar kelimelerini görüntülemek için"""
    return {r: info["keywords"] for r, info in TABLEAU_REPORTS.items()}
