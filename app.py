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
client = OpenAI()  # api_key environment’tan otomatik alınır

# --- Tableau bilgileri ---
TABLEAU_BASE_URL = os.getenv("TABLEAU_BASE_URL")
TABLEAU_SITE_ID = os.getenv("TABLEAU_SITE_ID")
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

# --- Slack bilgileri ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# --- Tableau rapor listesi ---
TABLEAU_VIEWS = {
    "hemen analiz raporu": {
        "id": "HemenLFL/HemenAnaliz",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz",
    },
    "sanal market analiz raporu": {
        "id": "LFL/SanalMarketLFL_1",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1",
    },
    "kapasite raporu": {
        "id": "KAPASTEKONTROL_17566530192920/KAPASTERAPORU",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU",
    },
}


# --- Tableau Authentication ---
def get_tableau_token():
    try:
        if not all([TABLEAU_BASE_URL, TABLEAU_SITE_ID, TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET]):
            raise ValueError("Missing Tableau environment variables")

        url = f"{TABLEAU_BASE_URL}/api/3.21/auth/signin"

        xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <tsRequest>
            <credentials personalAccessTokenName="{TABLEAU_PAT_NAME}" personalAccessTokenSecret="{TABLEAU_PAT_SECRET}">
                <site contentUrl="{TABLEAU_SITE_ID}" />
            </credentials>
        </tsRequest>
        """

        headers = {
            "Content-Type": "application/xml",
            "Accept": "application/json"
        }

        response = requests.post(url, data=xml_payload.encode("utf-8"), headers=headers, timeout=15)
        response.raise_for_status()

        # JSON veya XML response kontrolü
        if response.headers.get("Content-Type", "").startswith("application/json"):
            data = response.json()
            token = data["credentials"]["token"]
            site_id = data["credentials"]["site"]["id"]
        else:
            xml = response.text
            token = xml.split('token="')[1].split('"')[0]
            site_id = xml.split('site id="')[1].split('"')[0]

        print("[INFO] ✅ Tableau token fetched successfully")
        return token, site_id

    except Exception as e:
        print(f"[ERROR] ❌ Tableau auth failed: {e}")
        return None, None


# --- Tableau metadata (field list) çek ---
def get_tableau_fields(view_id):
    try:
        token, site_id = get_tableau_token()
        if not token:
            return []

        url = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views/{view_id}/data"
        headers = {"X-Tableau-Auth": token, "Accept": "application/json"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        if "columns" in data:
            fields = [c["name"] for c in data["columns"]]
        else:
            fields = list(data.keys())

        print(f"[INFO] Fields fetched for {view_id}: {fields}")
        return fields
    except Exception as e:
        print(f"[WARN] ⚠️ Tableau field fetch error for {view_id}: {e}")
        return []


# --- OpenAI ile analiz et ---
def find_tableau_report(user_message: str):
    """Kullanıcının mesajını analiz edip uygun Tableau raporunu belirler."""
    try:
        reports_info = {}
        for name, info in TABLEAU_VIEWS.items():
            fields = get_tableau_fields(info["id"])
            reports_info[name] = {"fields": fields, "link": info["link"]}

        prompt = f"""
        Kullanıcının mesajı: "{user_message}"

        Elinde aşağıdaki raporlar ve içerdiği sütun alanları var:

        {reports_info}

        Bu soruya en uygun raporu belirle.
        Sadece rapor adını döndür (örnek: "sanal market analiz raporu").
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        rapor_adi = response.choices[0].message.content.strip().lower()
        print(f"[INFO] OpenAI matched report: {rapor_adi}")
        return reports_info.get(rapor_adi)
    except Exception as e:
        print(f"[ERROR] 🤖 OpenAI report match failed: {e}")
        return None


# --- Slack ve FastAPI uygulamaları ---
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)


# --- Slack event listener ---
@bolt_app.event("message")
def handle_message_events(body, say, logger):
    try:
        event = body.get("event", {})
        user = event.get("user")
        text = event.get("text")

        if user and not event.get("bot_id"):
            rapor = find_tableau_report(text)
            if rapor:
                say(f"<@{user}> Sorunu analiz ettim ve uygun raporu buldum: {rapor['link']}")
            else:
                say(f"<@{user}> Maalesef bu konuda veri içeren bir rapor bulamadım 🤔")
    except Exception as e:
        print(f"[Slack Error] {e}")
        try:
            say("İçeride bir hata oluştu, birazdan tekrar dener misin?")
        except Exception:
            pass


# --- Slack endpoint ---
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)


# --- Test endpoint ---
@api.get("/")
def root():
    return {"status": "OpenAI + Tableau bot aktif 🚀"}


@api.get("/healthz")
def health():
    return {"ok": True}
