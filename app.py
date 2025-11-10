import os
import requests
from fastapi import FastAPI, Request
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
from openai import OpenAI
from io import StringIO
import csv
import unicodedata
from urllib.parse import quote, unquote

# === Ortam değişkenlerini yükle ===
load_dotenv()

# === OpenAI istemcisi ===
client = OpenAI()

# === Tableau bilgileri ===
TABLEAU_BASE_URL = os.getenv("TABLEAU_BASE_URL")
TABLEAU_SITE_ID = os.getenv("TABLEAU_SITE_ID")
TABLEAU_PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_PAT_SECRET = os.getenv("TABLEAU_PAT_SECRET")

# === Slack bilgileri ===
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# === Tableau rapor listesi ===
TABLEAU_VIEWS = {
    "hemen analiz raporu": {
        "path": "HemenLFL/HemenAnaliz/sheets/GünBazında",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
    },
    "kapasite raporu": {
        "path": "KAPASTEKONTROL_17566530192920/sheets/KAPASTERAPORU",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
    },
    "macronline poc raporu": {
        "path": "MACRONLINEPOCRaporu/sheets/MACRONLINEPOCRAPORU",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/MACRONLINEPOCRaporu/MACRONLINEPOCRAPORU"
    },
    "macrocenter lfl raporu": {
        "path": "Macrocenter/sheets/KAPASITEKULLANIMI",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/Macrocenter/KAPASITEKULLANIMI"
    }
}

# === Yardımcı Fonksiyonlar ===

def strip_suffix(s: str) -> str:
    """_1696... veya ?param gibi ekleri temizler"""
    s = s.split("?")[0].split("#")[0]
    if "_" in s:
        head, tail = s.rsplit("_", 1)
        if tail.isdigit():
            return head
    return s

def to_ascii(s: str) -> str:
    """Türkçe karakterleri sadeleştirir (Gün → Gun)"""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def slug_candidates(piece: str):
    """URL ve Türkçe varyantları üretir"""
    raw = piece
    enc = quote(piece, safe="/")
    asc = to_ascii(piece)
    enc_asc = quote(asc, safe="/")

    variants = {raw, enc, asc, enc_asc,
                raw.replace(" ", "%20"),
                asc.replace(" ", "%20")}
    return {v.lower() for v in variants if v}

def resolve_view_id(views_json: dict, view_path: str) -> str | None:
    """Tableau'dan gelen view listesinde uygun ID'yi bulur"""
    parts = view_path.strip("/").split("/")
    if len(parts) < 2:
        return None

    head = "/".join(parts[:2]).lower()
    tail = parts[-1]
    tail_base = strip_suffix(tail)
    candidates = slug_candidates(tail_base)

    matched = []
    for v in views_json.get("views", {}).get("view", []):
        cu = v.get("contentUrl", "") or ""
        cu_l = strip_suffix(cu).lower()
        if head not in cu_l:
            continue
        if any(c in cu_l for c in candidates):
            matched.append(v)

    if matched:
        matched.sort(key=lambda x: len(x.get("contentUrl", "")), reverse=True)
        return matched[0].get("id")

    # eşleşme bulunamadıysa workbook bazlı fallback
    for v in views_json.get("views", {}).get("view", []):
        cu_l = strip_suffix(v.get("contentUrl", "")).lower()
        if head in cu_l:
            return v.get("id")

    return None

# === Tableau Authentication ===
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

# === Tableau View’den kolonları çek ===
def get_tableau_fields(view_path):
    """View ID bulur, CSV’den kolon isimlerini döner."""
    try:
        token, site_id = get_tableau_token()
        if not token:
            print("[WARN] Tableau token alınamadı.")
            return []

        url_lookup = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views"
        headers = {"X-Tableau-Auth": token, "Accept": "application/json"}
        resp = requests.get(url_lookup, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        view_id = resolve_view_id(data, view_path)
        if not view_id:
            print(f"[WARN] View ID bulunamadı (resolver): {view_path}")
            return []

        print(f"[INFO] ✅ View ID bulundu: {view_id} ({view_path})")

        # 2️⃣ CSV verisini çek
        data_url = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views/{view_id}/data"
        params = {"maxrows": 5}
        dr = requests.get(data_url, headers=headers, params=params, timeout=20)
        if dr.status_code != 200:
            print(f"[WARN] Veri alınamadı: {dr.status_code} - {dr.text[:200]}")
            return []

        reader = csv.DictReader(StringIO(dr.text))
        fields = reader.fieldnames or []
        print(f"[DEBUG] {view_path} için {len(fields)} kolon bulundu: {fields}")
        return fields

    except Exception as e:
        print(f"[ERROR] Tableau field fetch hatası: {e}")
        return []

# === OpenAI ile rapor eşleştirme ===
def find_tableau_report(user_message: str):
    """Kullanıcı mesajına göre en uygun raporu seçer."""
    try:
        reports_info = {}
        for name, info in TABLEAU_VIEWS.items():
            fields = get_tableau_fields(info["path"])
            reports_info[name] = {"fields": fields, "link": info["link"]}

        prompt = f"""
Kullanıcının mesajı: "{user_message}"

Elinde aşağıdaki Tableau raporları var, her biri kolon isimleriyle birlikte:
{reports_info}

Bu mesaj hangi raporla en çok ilişkiliyse, sadece o raporun adını döndür.
Örnek: "macrocenter lfl raporu"
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

# === Slack endpoint ===
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

# === Test endpoint ===
@api.get("/")
def root():
    return {"status": "OpenAI + Tableau Assistant aktif 🚀"}

@api.get("/healthz")
def health():
    return {"ok": True}

# === Debug endpoint (ID eşleşme testi) ===
@api.get("/debug_match")
def debug_match(path: str):
    try:
        token, site_id = get_tableau_token()
        if not token:
            return {"error": "Token alınamadı"}

        url_lookup = f"{TABLEAU_BASE_URL}/api/3.21/sites/{site_id}/views"
        headers = {"X-Tableau-Auth": token, "Accept": "application/json"}
        resp = requests.get(url_lookup, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        vid = resolve_view_id(data, unquote(path))
        return {"path": path, "resolved_view_id": vid}
    except Exception as e:
        return {"error": str(e)}
