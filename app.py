import os
import requests
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
from openai import OpenAI

# --- Ortam değişkenlerini yükle ---
load_dotenv()

# --- OpenAI istemcisi ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Tableau bilgileri ---
TABLEAU_BASE_URL = os.getenv("TABLEAU_BASE_URL")
TABLEAU_SITE_ID = os.getenv("TABLEAU_SITE_ID")
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

# --- Slack bilgileri ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# --- Tableau rapor listesi (örnek view id'ler) ---
TABLEAU_VIEWS = {
    "hemen analiz raporu": {
        "id": "HemenLFL/HemenAnaliz",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
    },
    "sanal market analiz raporu": {
        "id": "LFL/SanalMarketLFL_1",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1"
    },
    "kapasite raporu": {
        "id": "KAPASTEKONTROL_17566530192920/KAPASTERAPORU",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
    }
}

# --- Tableau Authentication ---
def get_tableau_token():
    url = f"{TABLEAU_BASE_URL}/api/3.20/auth/signin"
    xml_payload = f"""
    <tsRequest>
        <credentials name="{TABLEAU_PAT_NAME}" personalAccessTokenName="{TABLEAU_PAT_NAME}" personalAccessTokenSecret="{TABLEAU_PAT_SECRET}">
            <site contentUrl="{TABLEAU_SITE_ID}" />
        </credentials>
    </tsRequest>
    """
    headers = {'Content-Type': 'application/xml'}
    response = requests.post(url, data=xml_payload, headers=headers)
    response.raise_for_status()
    xml = response.text
    token = xml.split('token="')[1].split('"')[0]
    site_id = xml.split('site id="')[1].split('"')[0]
    return token, site_id


# --- Tableau metadata (field list) çek ---
def get_tableau_fields(view_id):
    try:
        token, site_id = get_tableau_token()
        url = f"{TABLEAU_BASE_URL}/api/3.20/sites/{site_id}/views/{view_id}/data"
        headers = {"X-Tableau-Auth": token}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Tabloda alan isimlerini çıkar
        fields = list(data["columns"].keys()) if "columns" in data else []
        return fields
    except Exception as e:
        print(f"Tableau field fetch error for {view_id}: {e}")
        return []


# --- OpenAI ile analiz et ---
def find_tableau_report(user_message: str):
    """Kullanıcının mesajını analiz edip gerçek tablo alanlarına göre uygun raporu bulur."""

    # Her raporun field listesini topla
    reports_info = {}
    for name, info in TABLEAU_VIEWS.items():
        fields = get_tableau_fields(info["id"])
        reports_info[name] = {
            "fields": fields,
            "link": info["link"]
        }

    # OpenAI'ye gönderilecek prompt hazırla
    prompt = f"""
    Kullanıcının mesajı: "{user_message}"

    Elinde aşağıdaki raporlar ve içerdiği sütun alanları var:

    {reports_info}

    Bu soruya en uygun raporu belirle.
    Sadece rapor adını döndür (örnek: "sanal market analiz raporu").
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    rapor_adi = response.choices[0].message.content.strip().lower()
    return reports_info.get(rapor_adi, None)


# --- Slack ve FastAPI uygulamaları ---
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)


# --- Slack event listener ---
@bolt_app.event("message")
def handle_message_events(body, say, logger):
    event = body.get("event", {})
    user = event.get("user")
    text = event.get("text")

    if user and not event.get("bot_id"):
        rapor = find_tableau_report(text)
        if rapor:
            say(f"<@{user}> Sorunuzu analiz ettim ve uygun raporu buldum: {rapor['link']}")
        else:
            say(f"<@{user}> Maalesef bu konuda veri içeren bir rapor bulamadım 🤔")


# --- Slack endpoint ---
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)


# --- Test endpoint ---
@api.get("/")
def root():
    return {"status": "OpenAI + Tableau bot aktif 🚀"}