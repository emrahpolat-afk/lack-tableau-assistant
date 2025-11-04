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
        "path": "HemenLFL/HemenAnaliz/sheets/G%C3%BCn%20Baz%C4%B1nda",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
    },
    "kapasite raporu": {
    "path": "KAPASTEKONTROL_17566530192920/KAPASTERAPORU",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
},
    "macronline poc raporu": {
        "path": "MACRONLINEPOCRaporu/sheets/MACRONLINEPOCRAPORU",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/MACRONLINEPOCRaporu/MACRONLINEPOCRAPORU"
    },
    "macrocenter lfl raporu": {
        "path": "LFL/MacrocenterLFL/sheets/Macrocenter%20LFL%20G%C3%BCn",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/MacrocenterLFL"
    }
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
    """Önce view_id bulur, sonra ilk 5 satırı çekip kolon isimlerini döner."""
    try:
        token, site_id = get_tableau_token()
        if not token:
            print("[WARN] Tableau token alınamadı.")
            return []

        # 1️⃣ View ID’yi bul
        url_lookup = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views"
        headers = {"X-Tableau-Auth": token, "Accept": "application/json"}
        response = requests.get(url_lookup, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        print("[DEBUG] Tableau'dan dönen view listesi:")
        for v in data.get("views", {}).get("view", []):
            print(f" - {v.get('name')} | {v.get('contentUrl')}")

        view_id = None
        for view in data.get("views", {}).get("view", []):
            content_url = view.get("contentUrl", "").lower()
            if view_path.lower().split("/")[-1] in content_url.lower():
                view_id = view.get("id")
                break

        if not view_id:
            print(f"[WARN] View ID bulunamadı: {view_path}")
            return []

        print(f"[INFO] View ID bulundu: {view_id}")

        # 2️⃣ İlk 5 satırı çek
        data_url = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views/{view_id}/data"
        params = {"maxrows": 5}
        data_response = requests.get(data_url, headers=headers, params=params, timeout=15)

        if data_response.status_code != 200:
            print(f"[WARN] Veri alınamadı: {data_response.status_code} - {data_response.text}")
            return []

        csv_data = data_response.text
        print("[DEBUG] İlk 5 satırdan gelen ham CSV verisi:")
        print(csv_data.splitlines()[:6])  # ilk 5 satırı göster

        # 3️⃣ Kolon isimlerini çıkar
        import csv
        from io import StringIO
        reader = csv.DictReader(StringIO(csv_data))
        fieldnames = reader.fieldnames
        print(f"[INFO] Kolonlar bulundu: {fieldnames}")

        return fieldnames or []

    except Exception as e:
        print(f"[ERROR] Tableau field fetch hatası: {e}")
        return []

        # 2️⃣ View datasını al
        url_data = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views/{view_id}/data"
        response_data = requests.get(url_data, headers=headers, timeout=15)
        response_data.raise_for_status()
        data_json = response_data.json()

        fields = []
        if "columns" in data_json:
            fields = [col["name"] for col in data_json["columns"]]
        elif isinstance(data_json, dict):
            fields = list(data_json.keys())

        print(f"[INFO] Fields fetched for {view_path}: {fields}")
        return fields

    except Exception as e:
        print(f"[WARN] ⚠️ Tableau field fetch error for {view_path}: {e}")
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
# --- Manuel test (Render deploy sırasında çalışır) ---

if __name__ == "__main__":
    print("=== VIEW LIST TEST ===")
    fields = get_tableau_fields("LFL/MacrocenterLFL")
    print("=== TEST SONU ===", fields)

