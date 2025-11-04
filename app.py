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
def get_tableau_fields(view_path):
    """View içindeki kolon isimlerini GraphQL metadata API üzerinden çeker"""
    try:
        token, site_id = get_tableau_token()
        if not token:
            return []

        graphql_url = f"{TABLEAU_BASE_URL}/api/metadata/graphql"
        headers = {
            "X-Tableau-Auth": token,
            "Content-Type": "application/json",
        }

        # qualifiedName ile sorgu (örnek: LFL/SanalMarketLFL_1)
        graphql_query = {
            "query": f"""
            {{
              view(qualifiedName: "{view_path}") {{
                name
                workbook {{
                  name
                }}
                fields {{
                  name
                  dataType
                }}
              }}
            }}
            """
        }

        response = requests.post(graphql_url, json=graphql_query, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

        fields = []
        try:
            view_info = data.get("data", {}).get("view")
            if view_info and "fields" in view_info:
                fields = [f["name"] for f in view_info["fields"]]
        except Exception:
            pass

        if not fields:
            print(f"[WARN] View bulunamadı veya alan listesi boş: {view_path}")
        else:
            print(f"[INFO] Fields fetched for {view_path}: {fields}")

        return fields

    except Exception as e:
        print(f"[WARN] ⚠️ Tableau GraphQL fetch error for {view_path}: {e}")
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
