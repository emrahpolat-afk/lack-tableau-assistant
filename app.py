import os
import requests
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI()

TABLEAU_BASE_URL = os.getenv(“TABLEAU_BASE_URL”)
TABLEAU_SITE_ID = os.getenv(“TABLEAU_SITE_ID”)
TABLEAU_PAT_NAME = os.getenv(“TABLEAU_PAT_NAME”)
TABLEAU_PAT_SECRET = os.getenv(“TABLEAU_PAT_SECRET”)

SLACK_BOT_TOKEN = os.getenv(“SLACK_BOT_TOKEN”)
SLACK_SIGNING_SECRET = os.getenv(“SLACK_SIGNING_SECRET”)

TABLEAU_VIEWS = {
“hemen analiz raporu”: {
“path”: “HemenLFL/HemenAnaliz”,
“link”: “https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz”,
},
“sanal market analiz raporu”: {
“path”: “LFL/SanalMarketLFL_1”,
“link”: “https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1”,
},
“kapasite raporu”: {
“path”: “KAPASTEKONTROL_17566530192920/KAPASTERAPORU”,
“link”: “https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU”,
},
}

def get_tableau_token():
try:
url = f”{TABLEAU_BASE_URL}/api/3.21/auth/signin”
xml_payload = f”””




”””
headers = {“Content-Type”: “application/xml”, “Accept”: “application/json”}
response = requests.post(url, data=xml_payload.encode(“utf-8”), headers=headers, timeout=15)
response.raise_for_status()
if “application/json” in response.headers.get(“Content-Type”, “”):
data = response.json()
token = data[“credentials”][“token”]
site_id = data[“credentials”][“site”][“id”]
else:
xml = response.text
token = xml.split(‘token=”’)[1].split(’”’)[0]
site_id = xml.split(‘site id=”’)[1].split(’”’)[0]
print(”[INFO] ✅ Tableau token fetched successfully”)
return token, site_id
except Exception as e:
print(f”[ERROR] ❌ Tableau auth failed: {e}”)
return None, None

def get_tableau_fields(view_path):
try:
token, site_id = get_tableau_token()
if not token:
return []
url_lookup = f”{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views”
headers = {“X-Tableau-Auth”: token, “Accept”: “application/json”}
response = requests.get(url_lookup, headers=headers, timeout=15)
response.raise_for_status()
data = response.json()
views = data.get(“views”, {}).get(“view”, [])
view_id = None
for view in views:
if view_path.lower() in view.get(“contentUrl”, “”).lower():
view_id = view.get(“id”)
print(f”[INFO] View ID bulundu: {view_id}”)
break
if not view_id:
print(f”[WARN] View ID bulunamadı: {view_path}”)
return []
url_data = f”{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views/{view_id}/data”
response_data = requests.get(url_data, headers=headers, timeout=15)
if response_data.status_code == 404:
print(f”[WARN] 404 - View data bulunamadı: {view_path}”)
return []
response_data.raise_for_status()
data_json = response_data.json()
fields = []
if isinstance(data_json, dict):
if “columns” in data_json:
fields = [col[“name”] for col in data_json[“columns”]]
elif “data” in data_json:
fields = list(data_json[“data”][0].keys()) if data_json[“data”] else []
print(f”[INFO] Fields fetched for {view_path}: {fields}”)
return fields
except Exception as e:
print(f”[WARN] ⚠️ Tableau field fetch error for {view_path}: {e}”)
return []

def find_tableau_report(user_message: str):
try:
reports_info = {}
for name, info in TABLEAU_VIEWS.items():
fields = get_tableau_fields(info[“path”])
reports_info[name] = {“fields”: fields, “link”: info[“link”]}
prompt = f”””
Kullanıcının mesajı: “{user_message}”
Elinde aşağıdaki raporlar ve içerdiği sütun alanları var:
{reports_info}
Hangi rapor bu soruya en uygun?
Sadece rapor adını döndür.
“””
response = client.chat.completions.create(
model=“gpt-4o-mini”,
messages=[{“role”: “user”, “content”: prompt}],
)
rapor_adi = response.choices[0].message.content.strip().lower()
print(f”[INFO] 🤖 OpenAI matched report: {rapor_adi}”)
return reports_info.get(rapor_adi)
except Exception as e:
print(f”[ERROR] 🤖 OpenAI report match failed: {e}”)
return None

bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)

@bolt_app.event(“message”)
def handle_message_events(body, say, logger):
try:
event = body.get(“event”, {})
user = event.get(“user”)
text = event.get(“text”)
if user and not event.get(“bot_id”):
rapor = find_tableau_report(text)
if rapor:
say(f”<@{user}> Sorunu analiz ettim ve uygun raporu buldum: {rapor[‘link’]}”)
else:
say(f”<@{user}> Maalesef bu konuda veri içeren bir rapor bulamadım 🤔”)
except Exception as e:
print(f”[Slack Error] {e}”)
try:
say(“Bir hata oluştu, birazdan tekrar dener misin?”)
except Exception:
pass

@api.post(”/slack/events”)
async def endpoint(req: Request):
return await handler.handle(req)

@api.get(”/”)
def root():
return {“status”: “OpenAI + Tableau bot aktif 🚀”}

@api.get(”/healthz”)
def health():
return {“ok”: True}
