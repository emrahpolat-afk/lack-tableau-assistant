import os
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
from openai import OpenAI

# --- Ortam değişkenlerini yükle ---
load_dotenv()

# --- OpenAI istemcisi ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Tableau rapor bağlantıları ---
TABLEAU_LINKS = {
    "hemen analiz raporu": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz",
    "sanal market analiz raporu": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1",
    "kapasite raporu": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU",
    # Gelecekte buraya istediğin kadar rapor ekleyebilirsin
}


def find_best_reports(user_message: str):
    """Kullanıcının mesajına göre uygun Tableau rapor(lar)ını belirler."""
    rapor_listesi = "\n".join([f"- {k}" for k in TABLEAU_LINKS.keys()])

    prompt = f"""
    Kullanıcının sorusu: "{user_message}"

    Aşağıda Tableau sisteminde mevcut raporların listesi var:
    {rapor_listesi}

    Görev: Bu soruya en uygun olan rapor(lar)ı seç. 
    Eğer birden fazla uygun rapor varsa, virgülle ayırarak listele.
    Sadece rapor adlarını döndür. (örnek: Hemen Analiz Raporu, Kapasite Raporu)
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Sen bir veri analisti asistansın. Kullanıcının sorusuna göre en uygun Tableau raporlarını seç."},
            {"role": "user", "content": prompt}
        ]
    )

    secilenler = response.choices[0].message.content.lower().split(",")
    secilenler = [r.strip() for r in secilenler]
    links = [TABLEAU_LINKS[r] for r in TABLEAU_LINKS if r in secilenler]
    return links


def generate_ai_summary(user_message: str, reports: list):
    """OpenAI'den kısa bir analiz özeti üretir."""
    rapor_isimleri = ", ".join([name.title() for name in TABLEAU_LINKS.keys() if TABLEAU_LINKS[name] in reports])

    prompt = f"""
    Kullanıcı şu soruyu sordu: "{user_message}"
    Bu soruya uygun Tableau rapor(lar): {rapor_isimleri}

    Kullanıcıya kısa ve anlamlı bir açıklama yap, ardından 'Rapor bağlantıları aşağıda 👇' de.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Sen bir veri asistanısın. Kullanıcının mesajını özetle ve uygun raporları açıklayıcı şekilde tanıt."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# --- Slack ayarları ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)


# --- Slack mesaj dinleyici ---
@bolt_app.event("message")
def handle_message_events(body, say, logger):
    event = body.get("event", {})
    user = event.get("user")
    text = event.get("text")

    if user and not event.get("bot_id"):
        raporlar = find_best_reports(text)
        if raporlar:
            summary = generate_ai_summary(text, raporlar)
            link_text = "\n".join([f"🔗 {url}" for url in raporlar])
            say(f"<@{user}> {summary}\n\n{link_text}")
        else:
            say(f"<@{user}> Mesajını aldım ama uygun bir rapor bulamadım 🤔 Lütfen daha açık ifade edebilir misin?")


# --- Slack event endpoint ---
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)


# --- Basit test endpoint ---
@api.get("/")
def root():
    return {"status": "Bot çalışıyor!"}