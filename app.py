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
        # Operasyonel performans
        "hemen", "analiz", "performans", "operasyon", "teslimat", "lead time", 
        "toplama", "kuryeye atama", "kuryenin mağazaya varış", "yola çıkma", 
        "adreste süre", "fiili toplama", "bekleme süresi", "onayda bekleme",
        "müşteriye gösterilen teslimat süresi",
        
        # Sipariş istatistikleri
        "sipariş", "sipariş sayısı", "sipariş tutarı", "iptal", "iptal oranı", 
        "iptal sipariş", "yok satmalı sipariş", "alternatif ürün", "alternatif sipariş",
        "kayıp tl", "%kayıp", "ort sepet", "ortalama sepet tutarı", 
        "avg sku ort", "tso %", 
        
        # Müşteri deneyimi ve kalite
        "ortalama sipariş puanı", "ortalama teslimat puanı", "müşteri puanı",
        "cnf", "meta", "nac", "nsf", "pnf", "snf",
        
        # Operasyonel KPI’lar
        "verimlilik", "süre analizi", "performans puanı", "operasyon süresi", 
        "teslimat kalitesi", "servis seviyesi", "kuryenin yoldaki süresi", "leadtime"
    ],
    "desc": "Hemen Company operasyonunun teslimat, toplama, iptal ve müşteri memnuniyeti performansını analiz eden detaylı operasyon raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
},
    "kapasite raporu": {
    "keywords": [
        # Genel operasyon ve kapasite planlama
        "kapasite", "kko", "doluluk", "boşluk", "verimlilik", "mağaza kapasitesi", 
        "mağaza doluluk", "mağaza kota", "personel kapasitesi", "araç kapasitesi", 
        "kota", "doldurulan kota", "toplam kota", "kota değişimi", "td kota",
        
        # Araç ve dağıtım bilgileri
        "araç", "araç sayısı", "motorbike", "panelvan", "large motorbike", "araç tipi",
        
        # Sipariş yükü
        "sipariş", "45 dk sipariş", "hemen sipariş", "ad sayısı", "hemene düşen ad",
        
        # KPI ve oranlar
        "kko %", "doluluk oranı", "kapasite kullanımı", "kullanıcı sayısı", "aktif kullanıcı",
        "planlama", "kapasite takibi", "operasyonel planlama", "çalışan kapasitesi"
    ],
    "desc": "Mağaza, araç ve personel bazında kapasite kullanım oranlarını, kota planlamalarını ve operasyonel doluluk durumlarını gösteren rapor.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
},
    "sanal market analizi lfl": {
    "keywords": [
        # Finansal performans
        "sanal", "market", "lfl", "analiz", "ciro", "gelir", "satış", "kayıp", 
        "kayıp tl", "%kayıp", "finansal performans", "gelir analizi",

        # Sipariş istatistikleri
        "sipariş", "tüm sipariş", "iptal", "iptal oranı", "%iptal", 
        "iptal sipariş sayısı", "sipariş sayısı", "yok satma", 
        "toplanan sku", "sipariş performansı", "sipariş dağılımı",

        # Operasyonel performans ve kapasite
        "kapasite", "kko", "%kko", "doluluk oranı", "verimlilik", "kota", 
        "kota + channel + hızlı", "araç", "personel", 
        "ad başı sipariş", "ad başı kapasite", "araç başı sipariş", "araç başı kapasite",

        # Kanal bazlı dağılım
        "channel", "hızlı sipariş", "mağazadan teslim", 
        "internal time slot", "%hızlı", "kanal performansı",

        # Operasyon kalitesi
        "toplama uyumu", "teslimata uyum", "tso", "mükemmel sipariş",
        "toplama uyumu (hızlı hariç)", "teslimata uyum (hızlı hariç)",
        "tso (hızlı hariç)", "mükemmel sipariş (hızlı hariç)",

        # Müşteri memnuniyeti
        "sipariş puanı", "sipariş puanı (hızlı)", "sipariş puanı (hızlı hariç)",
        "teslimat puanı", "teslimat puanı (hızlı)", "teslimat puanı (hızlı hariç)",
        "müşteri puanı", "puan ortalaması", "memnuniyet",

        # Karşılaştırma ve kıyas
        "performans karşılaştırma", "kanal kıyaslama", 
        "operasyonel kalite", "servis seviyesi", "verimlilik analizi"
    ],
    "desc": "Sanal marketlerin LFL (Like-for-Like) bazında ciro, sipariş, kapasite, iptal, teslimat ve müşteri memnuniyeti metriklerini gösteren detaylı performans raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1"
},
   "macrocenter lfl raporu": {
    "keywords": [
        # Finansal performans
        "ciro", "gelir", "satış", "kayıp", "kayıp tl", "%kayıp", 
        "finansal performans", "gelir analizi",

        # Sipariş istatistikleri
        "sipariş", "tüm sipariş", "iptal", "iptal oranı", "%iptal", 
        "şikayet", "%şikayet", "sipariş sayısı", "sipariş performansı",

        # Operasyonel KPI'lar
        "kapasite", "kko", "%kko", "doluluk oranı", "verimlilik", 
        "araç başı sipariş", "araç başı kapasite", "ad başı sipariş", "ad başı kapasite",
        "toplama uyumu", "teslimata uyum", "tso", "mükemmel sipariş",
        "toplama uyumu (hızlı hariç)", "teslimata uyum (hızlı hariç)",
        "tso (hızlı hariç)", "mükemmel sipariş (hızlı hariç)",

        # Kanal bazlı
        "hızlı sipariş", "channel sipariş", "mağazadan teslim", 
        "%hızlı", "internal time slot", "kanal performansı",

        # Müşteri deneyimi
        "sipariş puanı", "teslimat puanı", "sipariş puanı (hızlı)", 
        "teslimat puanı (hızlı)", "teslimat puanı (hızlı hariç)", 
        "müşteri puanı", "puan ortalaması", "memnuniyet",

        # Operasyon ve kıyaslama
        "lfl", "macrocenter", "operasyonel performans", "kanal karşılaştırma", 
        "servis kalitesi", "performans ölçümü", "ciro gelişimi", "verimlilik analizi"
    ],
    "desc": "Macrocenter mağazalarının LFL (Like-for-Like) bazında ciro, kapasite, sipariş kalitesi ve operasyonel performans metriklerini gösteren detaylı rapor.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/MacrocenterLFL"
}
}

# === Kullanıcı bazlı kısa hafıza (bağlam) ===
conversation_history = defaultdict(list)
MAX_HISTORY = 3  # Son 3 mesajı hatırla

# === Basit kelime skoru hesaplayıcı ===
def keyword_score(message: str, report_keywords: list[str]) -> int:
    msg_words = set(re.findall(r"\w+", message.lower()))
    return len(msg_words & set(k.lower() for k in report_keywords))

# === OpenAI destekli yedek analiz ===
def openai_fallback(user_message: str, history: list[str]):
    try:
        examples = """
Örnek 1:
Kullanıcı: macro lfl
Cevap: macrocenter lfl raporu

Örnek 2:
Kullanıcı: sanal market ciro analizi
Cevap: hemen analiz raporu

Örnek 3:
Kullanıcı: kapasite doluluk oranı
Cevap: kapasite raporu

Örnek 4:
Kullanıcı: macronline test sonucu
Cevap: macronline poc raporu
"""
        prompt = f"""
Kullanıcının son konuşma geçmişi:
{history}

Şu anda söylediği mesaj: "{user_message}"

Elindeki rapor listesi:
{[r for r in TABLEAU_REPORTS.keys()]}

Yukarıdaki örnekleri dikkate alarak bu mesaj hangi raporla ilgiliyse
sadece o raporun adını döndür (örnek: "hemen analiz raporu").
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": examples + prompt}],
        )
        rapor_adi = response.choices[0].message.content.strip().lower()
        print(f"[INFO] 🧠 OpenAI fallback seçimi: {rapor_adi}")
        return TABLEAU_REPORTS.get(rapor_adi)
    except Exception as e:
        print(f"[ERROR] OpenAI fallback hatası: {e}")
        return None

# === Ana karar fonksiyonu ===
def find_best_report(user_message: str, user_id: str):
    """Bağlam ve anahtar kelimelere göre rapor seç."""
    history = conversation_history[user_id]
    full_context = " ".join(history + [user_message])

    # 1️⃣ Lokal kelime eşleştirme
    scores = {r: keyword_score(full_context, info["keywords"]) for r, info in TABLEAU_REPORTS.items()}
    best_match = max(scores, key=scores.get)
    if scores[best_match] > 1:
        print(f"[INFO] 🔍 Lokal eşleşme bulundu: {best_match} (skor {scores[best_match]})")
        return TABLEAU_REPORTS[best_match]

    # 2️⃣ Eğer emin değilse OpenAI fallback
    print("[WARN] Lokal eşleşme düşük, OpenAI fallback çağrılıyor...")
    return openai_fallback(user_message, history)

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
        text = event.get("text", "").strip()

        if not user or event.get("bot_id"):
            return

        # Mesaj geçmişine ekle
        conversation_history[user].append(text)
        if len(conversation_history[user]) > MAX_HISTORY:
            conversation_history[user] = conversation_history[user][-MAX_HISTORY:]

        rapor = find_best_report(text, user)

        if rapor:
            say(f"""
<@{user}> 🧭 Mesajını analiz ettim:
**{rapor['desc']}**
🔗 {rapor['link']}
""")
        else:
            say(f"<@{user}> Bu konuda uygun bir rapor bulamadım 🤔")

    except Exception as e:
        print(f"[Slack Error] {e}")
        say("Bir hata oluştu, tekrar dener misin?")

# === FastAPI endpointleri ===
@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

@api.get("/")
def root():
    return {"status": "Bağlam farkında OpenAI + Slack asistan aktif 🚀"}

@api.get("/context/{user_id}")
def get_context(user_id: str):
    """Belirli bir kullanıcının son mesaj geçmişini göster."""
    return {"user": user_id, "context": conversation_history[user_id]}
