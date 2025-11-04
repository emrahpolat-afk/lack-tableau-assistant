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
client = OpenAI()

# --- Tableau bilgileri ---
TABLEAU_BASE_URL = os.getenv("TABLEAU_BASE_URL")  # örn: https://prod-useast-b.online.tableau.com
TABLEAU_SITE_ID = os.getenv("TABLEAU_SITE_ID")    # örn: emigros
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

# --- Slack bilgileri ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# --- Tableau rapor listesi ---
TABLEAU_VIEWS = {
    "hemen analiz raporu": {
        "path": "HemenLFL/HemenAnaliz",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz",
    },
    "sanal market analiz raporu": {
        "path": "LFL/SanalMarketLFL_1",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1",
    },
    "kapasite raporu": {
        "path": "KAPASTEKONTROL_17566530192920/KAPASTERAPORU",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU",
    },
}

# --- Tableau Authentication ---
def get_tableau_token():
    """Tableau PAT ile token alır"""
    try:
        url = f"{TABLEAU_BASE_URL}/api/3.21/auth/signin"
        xml_payload = f"""
        <tsRequest>
            <credentials personalAccessTokenName="{TABLEAU_PAT_NAME}" personalAccessTokenSecret="{TABLEAU_PAT_SECRET}">
                <site contentUrl="{TABLEAU_SITE_ID}" />
            </credentials>
        </tsRequest>
        """
        headers = {"Content-Type": "application/xml"}
        response = requests.post(url, data=xml_payload, headers=headers, timeout=15)
        response.raise_for_status()
        xml = response.text
        token = xml.split('token="')[1].split('"')[0]
        site_id = xml.split('site id="')[1].split('"')[0]
        print("[INFO] ✅ Tableau token fetched successfully")
        return token, site_id
    except Exception as e:
        print(f"[ERROR] ❌ Tableau auth failed: {e}")
        return None, None

# --- Tableau GraphQL Metadata ile kolonları çek ---

import csv
import io

def get_tableau_fields(view_path):
    """REST API ile view datasından ilk satırı çekip kolon isimlerini döner."""
    try:
        token, site_id = get_tableau_token()
        if not token:
            print("[WARN] Tableau token alınamadı.")
            return []

        # 1️⃣ View ID bul
        url_lookup = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views"
        headers = {"X-Tableau-Auth": token, "Accept": "application/json"}
        response = requests.get(url_lookup, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        view_id = None
        for view in data.get("views", {}).get("view", []):
            content_url = view.get("contentUrl", "").lower()
            if view_path.lower() in content_url:
                view_id = view.get("id")
                break

        if not view_id:
            print(f"[WARN] View ID bulunamadı: {view_path}")
            return []

        # 2️⃣ CSV formatında veri al
        url_data = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views/{view_id}/data"
        headers["Accept"] = "text/csv"
        response = requests.get(url_data, headers=headers, timeout=20)
        response.raise_for_status()

        # 3️⃣ CSV’den kolon başlıklarını al
        csv_text = response.text
        reader = csv.reader(io.StringIO(csv_text))
        headers_row = next(reader, None)
        if not headers_row:
            print(f"[WARN] Veri boş geldi: {view_path}")
            return []

        print(f"[INFO] Fields fetched for {view_path}: {headers_row}")
        return headers_row

    except Exception as e:
        print(f"[WARN] ⚠️ Tableau REST fetch error for {view_path}: {e}")
        return []

# --- OpenAI ile rapor eşleştirme ---
def find_tableau_report(user_message: str):
    """Kullanıcı mesajına göre en uygun raporu seçer"""
    try:
        reports_info = {}
        for name, info in TABLEAU_VIEWS.items():
            fields = get_tableau_fields(info["path"])
            reports_info[name] = {"fields": fields, "link": info["link"]}

        prompt = f"""
        Kullanıcının mesajı: "{user_message}"

        Elinde aşağıdaki Tableau raporları var (alan isimleriyle birlikte):

        {reports_info}

        Bu mesaja en uygun raporu seç.
        Sadece rapor adını döndür (örnek: "sanal market analiz raporu").
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        rapor_adi = response.choices[0].message.content.strip().lower()
        print(f"[INFO] 🤖 OpenAI matched report: {rapor_adi}")
        return reports_info.get(rapor_adi)
    except Exception as e:
        print(f"[ERROR] 🤖 OpenAI report match failed: {e}")
        return None

# --- Slack + FastAPI entegrasyonu ---
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
            say("Bir hata oluştu, lütfen tekrar dener misin?")
        except Exception:
            pass

# --- Slack endpoint ---
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

# --- Test endpoint ---
@api.get("/")
def root():
    return {"status": "OpenAI + Tableau GraphQL bot aktif 🚀"}

@api.get("/healthz")
def health():
    return {"ok": True}
