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

# === Raporlar ===
TABLEAU_REPORTS = {
    "hemen analiz raporu": {
        "keywords": [
            "hemen", "analiz", "performans", "operasyon", "teslimat", "lead time",
            "toplama", "kuryeye atama", "bekleme", "müşteriye gösterilen teslimat süresi",
            "iptal", "yok satmalı", "alternatif ürün", "kayıp tl", "%kayıp",
            "ort sepet", "ortalama sepet", "tso", "cnf", "meta", "nac", "nsf", "pnf", "snf",
            "ortalama sipariş puanı", "ortalama teslimat puanı", "müşteri puanı"
        ],
        "desc": "Hemen Company operasyonunun teslimat, toplama, iptal ve müşteri memnuniyeti performansını analiz eden detaylı operasyon raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenLFL/HemenAnaliz"
    },
    "kapasite raporu": {
        "keywords": [
            "kapasite", "kko", "doluluk", "boşluk", "verimlilik", "kota", "planlama",
            "araç", "araç sayısı", "motorbike", "panelvan", "araç tipi", "personel kapasitesi",
            "45 dk sipariş", "hemen sipariş", "ad sayısı", "doluluk oranı"
        ],
        "desc": "Mağaza, araç ve personel bazında kapasite kullanım oranlarını, kota planlamalarını ve operasyonel doluluk durumlarını gösteren rapor.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KAPASTEKONTROL_17566530192920/KAPASTERAPORU"
    },
    "sanal market analizi lfl": {
        "keywords": [
            "sanal", "online", "market", "lfl", "analiz", "ciro", "gelir", "satış", "kayıp", 
            "iptal", "%iptal", "yok satma", "toplama uyumu", "teslimata uyum", "tso",
            "sipariş puanı", "teslimat puanı", "kanal performansı", "hızlı sipariş",
            "araç", "personel", "verimlilik", "servis seviyesi"
        ],
        "desc": "Sanal marketlerin LFL (Like-for-Like) bazında ciro, sipariş, kapasite, iptal, teslimat ve müşteri memnuniyeti metriklerini gösteren detaylı performans raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/SanalMarketLFL_1"
    },
    "macrocenter lfl raporu": {
        "keywords": [
            "macro", "macrocenter", "lfl", "ciro", "gelir", "satış", "kayıp", 
            "sipariş", "iptal", "şikayet", "kapasite", "verimlilik", "toplama uyumu",
            "teslimata uyum", "mükemmel sipariş", "araç başı", "ad başı",
            "teslimat puanı", "sipariş puanı", "operasyonel performans",
            "servis kalitesi", "kanal karşılaştırma", "macro lfl", "macro raporu"
        ],
        "desc": "Macrocenter mağazalarının LFL bazında ciro, kapasite, sipariş kalitesi ve operasyonel performans metriklerini gösteren detaylı rapor.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/LFL/MacrocenterLFL"
    },
        "operasyonel kpi raporu": {
        "keywords": [
            "operasyon", "operasyonel", "kpi", "kpi analizi", "performans",
            "süreç", "süreç analizi", "teslimat performansı", "operasyon kalitesi",
            "mağaza performansı", "efficiency", "productivity", "cycle time",
            "lead time", "kalite", "memnuniyet", "hız", "değerlendirme",
            "kontrol", "monitoring", "operasyon raporu", "operasyonel performans",
            "kpi dashboard", "operasyon kpi", "kpi raporu"
        ],
        "desc": "Operasyonun tüm kritik KPI’larını; performans, hız, kalite, verimlilik ve süreç uyumunu tek ekranda analiz eden gelişmiş operasyonel rapor.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/OperasyonKPIDashboard/OPERASYONELKPIRAPORU"
    },
    "kargo performansı sipariş detay raporu": {
        "keywords": [
            "kargo", "kargo performans", "kargo detay", "sipariş detay",
            "kargo süresi", "teslim süresi", "kuryeye atama süresi",
            "yola çıkma süresi", "teslimat süresi", "kargo gecikme",
            "geciken sipariş", "kurye problemi", "dağıtım süresi", "kargo analizi",
            "paketleme", "dağıtım", "kargo operasyon", "logistics", "lojistik",
            "kurye performansı", "sipariş akışı", "teslimat akışı"
        ],
        "desc": "Sipariş seviyesinde kargo operasyonunun performansını, teslimat aşamalarını, gecikme nedenlerini ve kurye süreçlerini analiz eden detaylı operasyon raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KargoPerformans/SipariDetayBilgileri"
    },
        "kargo operasyonu raporu": {
        "keywords": [
            "kargo operasyon", "kargo operasyonu", "kargo yönetimi",
            "dağıtım operasyonu", "dağıtım", "paketleme operasyonu",
            "teslim operasyonu", "kargo hacmi", "kargo volum",
            "kategori bazında kargo", "kategori performans", "kategori kargo",
            "lojistik operasyon", "logistics operation",
            "kargo sipariş adedi", "kargo yükü", "kargo kapasitesi",
            "kargo dağılımı", "geciken kargolar", "kargo sla",
            "kargo kalite", "operasyonel kargo analizi",
            "operasyonel dağıtım", "operasyon kırılımı",
            "operasyon bazlı metrikler"
        ],
        "desc": "Kargo operasyonunun kategori bazlı performansını, kargo hacimlerini, gecikmeleri, dağıtım ve paketleme operasyonlarını analiz eden kapsamlı bir kargo operasyon raporu.",
        "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/KargoOperasyonu/KargoOperasyonu"
    },
    "45dk analiz raporu": {
    "keywords": [
        # Kimlik
        "45dk", "45 dk", "45 dakika", "45dakika", "45 dk analiz",
        "45dk performans", "45 dk performans",

        # Teslimat süreleri
        "teslimat süresi", "teslim süresi", "hızlı teslimat", 
        "hemen teslim", "çabuk teslim", "süre analizi",

        # Sipariş metrikleri
        "sipariş sayısı", "sipariş adedi", "sipariş performansı",
        "kanal dağılımı", "kanal sipariş", "bölge sipariş",

        # Operasyonel KPI
        " teslimat kpi", "operasyonel hız", "performans hızı",
        "45dk kpi", "45dk metrik", "hızlı sipariş oranı",

        # Bölge & mağaza
        "bölge bazlı", "bölge müdürü", "mağaza bazlı",
        "bölgesel performans", "ilçe bazlı", "mahalle bazlı",

        # Doğrudan rapor yakalama
        "genel özet", "45dk genel özet", "45dk raporu"
    ],
    "desc": "45 Dakika teslimat operasyonunun hız, sipariş performansı, kanal dağılımı ve bölge bazlı KPI’larını analiz eden hızlı teslimat performans raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/45DkAnalizLive/45DkGenelzetLive"
},
    "bölge havuz takip kpi analizi": {
    "keywords": [
        # Genel isim varyasyonları
        "bölge havuz", "bölge kpi", "kpi analizi", "bölge bazlı", "bölge performans",
        "dashboard", "bölgesel rapor", "bölge özeti",

        # Operasyon türleri
        "hemen", "yemek", "45dk", "45 dk", "45 dakika", 
        "hemen lead time", "yemek lead time", "45dk lead time",
        "hemen sipariş sayısı", "yemek sipariş sayısı", "45dk sipariş sayısı",
        "stack oranı", "stack", "lead time",

        # KPI metrikleri
        "toplama süresi", "teslim süresi", "atama süresi", 
        "yolda geçen süre", "adreste geçen süre",
        "gphz", "toplam süre", "hemen top süresi", "yemek top süresi",

        # Bölge yöneticileri
        "bölge müdürü", "zone manager", "yönetici bazlı",

        # Detay tablosu
        "bölge özeti", "bölge bazında özet", "bölge tablo", 
        "sipariş dağılımı", "operasyon yükü", "stack oranları",

        # Yardımcı varyasyonlar
        "havuz analizi", "kpi", "performans analizi", "hemen kpi", "yemek kpi", "45dk kpi",
        "zon bazlı", "mahalle bazlı", "bölge detay"
    ],
    "desc": "Bölge bazlı Hemen – Yemek – 45DK operasyonlarının sipariş hacmi, lead time, toplama & teslim süreleri ve yöneticilere göre KPI performansını inceleyen detaylı analiz raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/BlgeHavuzTakipKpAnalizi/BlgeHavuzTakipKpAnalizi"
},
    "operasyonel metrikler analizi": {
    "keywords": [
        # Genel isimler ve varyasyonlar
        "operasyonel metrik", "metrik analizi", "operasyon metrikleri", 
        "hemen metrik", "sanalmarket metrik", "sanal market metrik",
        "hemen ve sanal", "hemen sanal karşılaştırma", "metrik inceleme",
        "operasyon analizi", "operasyon izleme", "hemen sanal analiz",

        # Lead time & süre metrikleri
        "lead time", "toplama süresi", "bekleme süresi", "havuz süresi",
        "onay süresi", "hazırlık süresi", "günlük ortalama sipariş", 
        "ortalama sipariş sayısı", "fiili toplama süresi",
        "yolda geçen süre", "operasyon süresi", "süre izleme",

        # Şikayet / Rate metrikleri
        "şikayet oranı", "rate", "hemen rate", "sanalmarket rate", 
        "şikayet", "müşteri rate", "hemen şikayet", "sanal şikayet",

        # Sipariş hacmi & operasyon yükü
        "sipariş sayısı", "ortalama sipariş", "günlük sipariş",
        "hemen sipariş sayısı", "sanal sipariş sayısı",

        # Kapasite analizleri
        "kko", "kapasite oranı", "kapasite analizi", "aylık kapasite", 
        "haftalık kapasite", "kapasite dağılımı", "günlük kapasite",

        # Aylık trendler
        "aylık metrik", "aylık karşılaştırma", "trend analizi",
        "ocak", "şubat", "mart", "nisan", "mayıs", "haziran", 
        "temmuz", "ağustos", "eylül",

        # Operasyon karşılaştırması
        "hemen vs sanal", "hemen sanal karşılaştırma", 
        "hız testi", "metrik karşılaştırma", "performans oranları",

        # Detay tablosu kelimeleri
        "aylık ortalama", "ortalama süreler", "tablo detay", 
        "süre karşılaştırma", "trend tablosu",

        # Soft search varyasyonlar
        "ops metrik", "ops analiz", "operasyon kpi", "operasyon izleme",
        "hemen analiz", "sanal market analiz", "hemen operasyon", 
        "sanalmarket operasyon",
    ],
    "desc": "Hemen ve Sanalmarket operasyonlarının lead time, toplama-bekleme-havuz süreleri, şikayet ve rate oranları, kapasite seviyeleri ve aylık trendlerini karşılaştırmalı olarak gösteren kapsamlı metrik analiz raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/OperasyonMetriklerizet/OperasyonelMetrikler"
},
    "tıkla gel al analizi": {
    "keywords": [
        # Genel isimler ve varyasyonlar
        "tıkla", "tikla", "tıkla gel al", "tiklagelal", 
        "click collect", "click&collect", "c&c", "tga",

        # Sipariş & satış metrikleri
        "sipariş", "sipariş sayısı", "sipariş adedi", "şipariş", "sipaşiriş",
        "ciro", "gelir", "satış", "sepet ortalaması", "sepet tutarı",
        "ortalama sepet", "basket size", "basket", "gmv",

        # İptal & uyum metrikleri
        "iptal", "iptal oranı", "%iptal", "tam sipariş", 
        "toplama uyumu", "geç toplama", "uyum oranı",
        "tam sipariş oranı", "success rate", "tamamlama oranı",

        # Şikayet & SMS & müşteri iletişimi
        "şikayet", "şikayet oranı", "şikayet sayısı", 
        "sms", "sms tablosu", "şikayet detayı", "şikayet nedenleri",
        "feedback", "müşteri sorun", "customer complaint",

        # Bölge müdürü / mağaza bazlı analizler
        "bölge müdürü", "müdür bazlı", "mağaza bazlı", 
        "mağaza özeti", "mağaza detay", "en yüksek mağaza",
        "ilk 10 mağaza", "top mağaza", "store bazlı",

        # Performans karşılaştırma
        "kıyas", "karşılaştırma", "performans karşılaştırma",
        "bölge karşılaştırma", "mağaza karşılaştırma", "ranking", "sıralama",

        # Diğer varyasyonlar
        "pickup", "aynı gün alma", "yerinden teslim", 
        "gel al sipariş", "magaza pickup", "yerinden alım",

        # Soft search – yanlış yazımlar
        "tıkla gel", "tıkla al", "tikla al", "tıkla getir", 
        "tga raporu", "tga analiz", "tg analiz",

        # Yönetici seviyesinde kullanılan kelimeler
        "bölge özeti", "müdür özeti", "operasyon özeti", 
        "şikayet inceleme", "müdür performansı"
    ],
    "desc": "Tıkla-Gel-Al operasyonunun bölge müdürü, mağaza ve müşteri metrikleri bazında sipariş, ciro, sepet ortalaması, iptal oranı, toplama uyumu, şikayet dağılımı ve SMS loglarını gösteren detaylı performans raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/TklaGelAl/TklaGelAl"
},
    "qr vardiya uyumu analizi": {
    "keywords": [
        # Ana rapor isimleri ve varyasyonlar
        "qr", "vardiya", "qr vardiya", "vardiya uyumu", 
        "qr oranı", "qr okuma", "qr okutma", "qr performans",
        "qr dashboard", "qr raporu", "vardiya raporu",
        "okutma uyumu", "okutma oranı",

        # Bölge & mağaza seviyesinde aramalar
        "bölge müdürü", "bölge bazlı", "mağaza bazlı", 
        "mağaza uyumu", "bölge uyumu", "personel uyumu",
        "zone manager", "mağaza yöneticisi", "mağaza performansı",

        # Personel & vardiya detayları
        "personel", "personel listesi", "personel qr", 
        "personel uyumsuz", "vardiya geç kalma", "vardiya başlangıç",
        "vardiya saatleri", "vardiya uyum oranı", "vardiya analizi",

        # QR okutmadan toplama yapanlar
        "okutmadan", "qr okutmadan", "qr okutmadı", 
        "okutmadan toplama", "uyumsuz personel",

        # KPI & metrikler
        "uyum oranı", "%uyum", "genel uyum", "müdür uyumu",
        "performans ölçümü", "görev uyumu", "iş gücü kalitesi",

        # Yanlış yazımlar & esnek aramalar
        "varıya", "vardya", "vardia", "qr okuma", "qrr", 
        "karekod", "kare kod", "qr kod", "qr code", "qr kpi",
        "okutma kpi", "vardiya kpi",

        # Diğer bağlamlar
        "sezonluk uyum", "mağaza seçimi", "toplam qr", 
        "okutulan qr", "qr okutulan sayı", "uyum skoru",
        "çalışan uyumu", "emekçi uyumu"
    ],
    "desc": "QR okutma oranları, vardiya uyumu, mağaza ve bölge müdürü bazlı performans ile QR okutmadan toplama yapan personel analizini içeren operasyonel kalite raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/QRADPerformans_17561276165730/QRDashboard"
},
    "hemen son sipariş analizi": {
    "keywords": [
        # Rapor adı & varyasyonlar
        "hemen son sipariş", "son sipariş", "hemen sipariş analizi",
        "latest order", "son order", "last order", "sipariş son",

        # Sipariş zinciri – operasyon adımları
        "havuz süresi", "toplama süresi", "kuryeye atama süresi",
        "kuryenin mağazaya varış süresi", "kuryenin yola çıkış süresi",
        "teslim süresi", "total lead time", "lead time",
        "faturalandırma süresi", "onay süresi",

        # Detay kolonlar
        "havuzda bekleme", "fili toplama", "kuryenin teslim aldığı saat",
        "kuryenin teslim saati", "sipariş oluşturma zamanı",
        "teslim saati", "gecikme", "geciken sipariş",

        # Mağaza bazlı
        "mağaza bazlı son sipariş", "mağaza son sipariş", "mağaza analizi",
        "mağaza lead time", "mağaza performansı", "mağaza kpi",

        # Bölge bazlı
        "bölge müdürü", "bölge bazlı sipariş", "bölge lead time",
        "bölge analizi", "bölge performansı",

        # Operasyonel kalite
        "geciken adım", "nerede gecikiyor", "süre analizi",
        "hemen leadtime", "hemen operasyon zinciri",

        # Esnek/yazım yanlış toleranslı ifadeler
        "leadtime", "leadtıme", "leadtim", "leed time",
        "havuz", "havuza düştü", "kurye atama", "kuryeye atama",
        "toplama", "toplama kpi", "toplama gecikme",

        # Sorulara yönelik
        "son sipariş kaçta", "son sipariş ne zaman", 
        "son siparişte gecikme", "hemen son rapor"
    ],
    "desc": "Hemen operasyonunda en son oluşturulan siparişin havuz, toplama, kuryeye atama, varış, çıkış ve teslim süreç sürelerini analiz eden detaylı performans raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HemenSonSipariAnalizi/HemenSonSip_"
},
    "ad – gramaj takibi": {
    "keywords": [
        # Rapor adı ve varyasyonlar
        "ad gramaj", "gramaj takibi", "ad analizi", "ad raporu",
        "gramaj raporu", "gramaj takip", "ad takip", "ad-gramaj",

        # AD – Ürün bazlı sinyaller
        "gramaj", "ürün gramaj", "ürün ağırlığı", "sku gramaj",
        "kategori sıralaması", "kategori bazlı", "kategori analizi",
        "ürün sıralaması", "sku sıralaması",

        # AD – Sipariş bazlı sinyaller
        "ad sipariş", "ad sipariş sayısı", "ad listesi",
        "tam gramaj", "gramajlı sipariş", "tam gramajlı sipariş",

        # Mağaza sinyalleri
        "mağaza sipariş sıralaması", "mağaza bazlı ad", "mağaza gramaj analizi",
        "mağaza bazlı gramaj", "mağaza ad performansı",

        # Ödeme türleri
        "ödeme türü", "ödeme yöntemi", "kredi kartı", "garantipay",
        "masterpass", "moneypay", "valörlü", "hazır limit",

        # Ürün-sipariş bilgileri
        "ürün bilgileri", "ürün sipariş bilgileri", "ürün sipariş sayısı",
        "ürün sipariş", "sku sipariş", "sku bazlı",

        # Esnek yanlış yazımlar
        "grama", "gramj", "ad gramj", "agrmaj", "ad grmaj",
        "tam gramj", "sku grmaj", "gramajı",
    ],
    "desc": "AD (Alışveriş Danışmanı) siparişlerinin gramaj, ürün, kategori, mağaza ve ödeme türü bazında detaylı analizini gösteren rapor.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/AD-GRAMAJTAKB/AD-GRAMAJTAKP"
},
    "iptal siparişler raporu": {
    "keywords": [
        # Rapor adı ve varyasyonlar
        "iptal", "iptaller", "iptal raporu", "iptal sipariş", "iptal siparişler",
        "iptal analizi", "iptal oranı", "%iptal",

        # Hemen / Sanal / Macro / 45DK özel kelimeler
        "hemen iptal", "sanal iptal", "market iptal", "macro iptal",
        "45 dk iptal", "45dk iptal", "express iptal",

        # Karışık yazımlar / varyasyonlar
        "iptal sayısı", "iptal sipariş sayısı", "iptal trend", 
        "iptal sebepleri", "iptal nedenleri", "neden iptal", "neden iptal edildi",
        "iptal dağılımı", "iptal oranları", "iptal sebebi", 
        "iptal nedeni", "iptal gerekçesi",

        # Bölge & mağaza kırılımı
        "bölge iptal", "mağaza iptal", "bölge müdürü iptal", 
        "mağaza bazlı iptal", "bölge bazlı iptal", "hiyerarşi iptal",
        "bölge müdürleri iptal", "mağaza iptal analiz",

        # Trend & zaman analizleri
        "iptal trendi", "iptal zaman analizi", "iptal aylık", 
        "günlük iptal", "haftalık iptal", "zaman serisi iptal",

        # Sipariş bazlı
        "iptal statüsü", "iptal edilen sipariş", "iptal edilmiş sipariş",
        "cancel order", "cancelled", "order canceled",

        # Esnek yanlış yazımlar
        "ıptal", "iptl", "iptl sipariş", "nasil iptal", "ipsal",
        "iptl oran", "iptall", "iptale", "iptali"
    ],
    "desc": "Mağaza, bölge, kanal ve ürün bazında tüm iptal sipariş trendlerini, iptal nedenlerini ve operasyonel kırılımları gösteren detaylı iptal analizi raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/ptalSipariler/ptalSipariler"
},
    "tekrarlı yok satmalar raporu": {
    "keywords": [
        # Temel kavramlar
        "yok satma", "yoksatma", "yok satmalar", "stok yok", "stokta yok",
        "raf yok", "yok", "ürün yok", "stok problemi", "out of stock",

        # Tekrarlı yok satma varyasyonları
        "tekrarlı yok satma", "tekrar yok satma", "tekrarlı yoksatma",
        "tekrar eden yok satma", "sürekli yok satma", 
        "çoklu yok satma", "ürün tekrar tekrar yok",
        "yok satma indeksi", "%yok satma",

        # Mağaza bazlı
        "mağaza yok satma", "mağaza bazlı yok satma",
        "mağaza stok yok", "mağaza tekrarlı yok satma",
        "mağaza ürün yok satma",

        # Bölge kırılımı
        "bölge yok satma", "bölge müdürü yok satma",
        "bölge bazlı yok satma", "offline bölge müdürü",
        "bölge stok problemi",

        # Ürün bazlı
        "sku yok satma", "ürün yok satma", "ürün bazlı yok satma",
        "sku bazlı yok satma", "ürün bulunamıyor",

        # Trend ve zaman
        "son 7 gün yok satma", "haftalık yok satma",
        "trend yok satma", "yok satma geçmişi",
        "günlük yok satma", "yok satma takibi",

        # Karışık yazım & varyasyonlar
        "yok sat", "yok satıyor", "yok sattı",
        "yok satma analizi", "tekrarlı yok", "tekrar stok yok",
        "stok yok raporu", "stok sorunu", "ürün bulunamadı",

        # Yanlış yazımlar
        "yok satmlr", "yok satmlar", "yok satmaö", "yk satma",
        "yoksat", "tekrarlıyoksatma", "tekrarlıyok", "tekarli yok"
    ],
    "desc": "Bölge, mağaza ve ürün bazında tekrarlı yok satma vakalarını, geçmiş 7 günlük trendleri, SKU bazlı yok satma sayılarını ve yok satma indeksini gösteren detaylı analiz raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/TekrarlYokSatmalarMaaza-rn/TekrarlYokSatmalar"
},
    "manuel atamalar raporu": {
    "keywords": [
        # Temel kavramlar
        "manuel atama", "manuel", "atama", "manual atama", "manual assignment",
        "manuel işlem", "manuel yönlendirme", "manuel dağıtım",
        "atama sayısı", "atama trendi",

        # Dağıtım türü ve dikey
        "instant", "time slot", "hemen", "sanalmarket", "macro", "yemek", 
        "dikey atama", "dağıtım türü", "delivery type", "dikey",

        # Randevulu sipariş-kurye ataması
        "moto kurye atama", "kurye atama", "kurye atanması",
        "randevulu sipariş", "randevulu kurye", "siparişin kuryeye atanması",
        "sürücü ataması", "kurye yönlendirme",

        # Bölge kırılımı
        "bölge", "bölge müdürü", "bölge atama", "bölge manuel atama",
        "bölge bazlı atama", "bölge müdürü atama",

        # Mağaza kırılımı
        "mağaza bazlı atama", "mağaza atama sayısı",
        "mağaza manuel atama", "mağaza atanma", "mağaza randevulu atama",

        # Zaman & trend
        "günlük atama", "saatlik atama", "atama grafiği",
        "saat bazlı atama", "atama trendi", "time series atama",

        # Süre KPI’ları
        "lead time", "atama süresi", "kurye atama süresi",
        "toplama süresi", "işlem süresi", "lt", "ttl", "kuryeye atama süresi",

        # Veri içi başlıklar
        "randevulu", "moto", "kurye", "sipariş no", "sipariş oluşturma zamanı",
        "ad soyad", "atayan kişi", "atanan sipariş",

        # Yanlış yazımlar ve varyasyonlar
        "manüel atama", "mannuel atama", "mannuel", "manuelatm", 
        "manulatama", "manuel atam", "manualatama", "manual atmalar",
        "atamlar", "atamala", "atam trendi", "atm", "kuryeatama", "kuryeye atama"
    ],
    "desc": "Manuel yapılan sipariş atamalarını bölge, mağaza, dikey, dağıtım türü ve kurye atama bazında gösteren; günlük ve saatlik trendlerle desteklenen detaylı analiz raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/ManuelAtamalar/ManuelAtamaDashboard"
},
    "havuz verimlilik analizi": {
    "keywords": [
        # Anahtar konseptler
        "havuz", "verimlilik", "havuz verimliliği", "havuz analizi", 
        "havuz performansı", "pool", "pool efficiency", "pool analysis",

        # Süreç & Zaman KPI’ları
        "havuz süresi", "havuz bekleme süresi", "havuz lead time", "havuz lt",
        "kuryeye atama süresi", "kuryeye yönlendirme", "atama süresi",
        "toplama süresi", "onay süresi", "faturalandırma süresi",
        "mağazaya varış süresi", "yola çıkma süresi", "teslim süresi",
        "kurye yolda geçen süre", "kurye mağaza çıkış süresi",

        # Sipariş metrikleri
        "havuz sipariş", "havuz sipariş sayısı", "sipariş akışı",
        "45 dk havuz", "hemen havuz", "yemek havuz",
        "kanal bazlı havuz", "kanal performansı",

        # Performans & kalite
        "verimlilik oranı", "verimlilik skoru", "performans kıyası",
        "servis seviyesi", "hizmet seviyesi", "sl", "sla", "uyum oranı",

        # Bölge/mağaza kırılımı
        "bölge havuz", "mağaza havuz", "bölge bazlı havuz", 
        "mağaza havuz verimliliği", "bölge performansı", "mağaza performansı",

        # Trend ve dönem analizi
        "havuz trend", "verimlilik trend", "zaman serisi havuz",
        "günlük havuz", "aylık havuz performansı",

        # Yanlış yazımlar & varyasyonlar
        "havüz", "havvuz", "havus", "verimilik", "verimlilk", 
        "havuzverimlilik", "havuzanalizi", "poolverimlilik", 
        "havuz verim", "hlv", "hvz", "hvz verim", "hvs", "havuz raporu"
    ],
    "desc": "Havuz bazlı sipariş yükü, süreç verimliliği, bekleme süreleri, kurye-atama-toplama metrikleri ve kanal karşılaştırmalarını detaylı analiz eden performans raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/HavuzVerimlilikAnalizi/HavuzVerimlilikAnalizi"
},
    "yok satma bazlı kapanan ürün raporu": {
    "keywords": [
        # Temel kavramlar
        "yok satma", "yok satmalar", "yok satma raporu", "kapanan ürün", 
        "kapalı ürün", "ürün kapanma", "kapanan sku", "ürün kapanış",
        "ürün kapalı", "kapanma", "ürün açılma", "açılan ürün",

        # Detay fonksiyonlar
        "ürün bazlı kapalı", "mağaza bazlı kapalı", "kapanan ürün sayısı",
        "ürün kapanma süresi", "kapanma süresi", "kapalı kalma süresi",
        "kapalı ürün sayısı", "ürün stok yok", "stok yok", "stok bulunamıyor",

        # Bölgesel detaylar
        "bölge kapalı ürün", "bölge müdürü kapanan ürün", 
        "bölge yok satma", "bölge bazlı yok satma",

        # Mağaza detayları
        "mağaza kapalı ürün", "mağazada kapalı ürün", 
        "mağaza kapanan ürün", "mağaza yok satma",

        # Ürün bazlı istatistikler
        "ürün yok satma", "ürüne özel yok satma", "sku kapanma",
        "sku bazlı yok satma",

        # Trend & analiz
        "yok satma trendi", "ürün kapanma trendi", 
        "kapanma oranı", "kapalı ürün oranı",

        # Yanlış yazımlar & varyasyonlar
        "yoksatma", "yok satmma", "yok satma kapalı", 
        "kapanan urun", "kapanan ürünler", "yok satma kapanan",
        "yok satma kapalı ürünler", "ks ürün", "ys ürün", "urun kapali", 
        "urun yok", "urun yoksatma", "yok urun", "yoksatma raporu",
        "kapali urun raporu"
    ],
    "desc": "Yok satma kaynaklı kapanan ürünlerin bölge, mağaza ve SKU bazında analizini; kapanma sürelerini ve son 2 aylık açılan-kapanan ürün detaylarını gösteren performans raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/YokSatmaBazlKapananrnRaporu/Dashboard1"
},
    "yok satma bazlı kapanan ürün raporu": {
    "keywords": [
        # Temel kavramlar
        "yok satma", "yok satmalar", "yok satma raporu", "kapanan ürün", 
        "kapalı ürün", "ürün kapanma", "kapanan sku", "ürün kapanış",
        "ürün kapalı", "kapanma", "ürün açılma", "açılan ürün",

        # Detay fonksiyonlar
        "ürün bazlı kapalı", "mağaza bazlı kapalı", "kapanan ürün sayısı",
        "ürün kapanma süresi", "kapanma süresi", "kapalı kalma süresi",
        "kapalı ürün sayısı", "ürün stok yok", "stok yok", "stok bulunamıyor",

        # Bölgesel detaylar
        "bölge kapalı ürün", "bölge müdürü kapanan ürün", 
        "bölge yok satma", "bölge bazlı yok satma",

        # Mağaza detayları
        "mağaza kapalı ürün", "mağazada kapalı ürün", 
        "mağaza kapanan ürün", "mağaza yok satma",

        # Ürün bazlı istatistikler
        "ürün yok satma", "ürüne özel yok satma", "sku kapanma",
        "sku bazlı yok satma",

        # Trend & analiz
        "yok satma trendi", "ürün kapanma trendi", 
        "kapanma oranı", "kapalı ürün oranı",

        # Yanlış yazımlar & varyasyonlar
        "yoksatma", "yok satmma", "yok satma kapalı", 
        "kapanan urun", "kapanan ürünler", "yok satma kapanan",
        "yok satma kapalı ürünler", "ks ürün", "ys ürün", "urun kapali", 
        "urun yok", "urun yoksatma", "yok urun", "yoksatma raporu",
        "kapali urun raporu"
    ],
    "desc": "Yok satma kaynaklı kapanan ürünlerin bölge, mağaza ve SKU bazında analizini; kapanma sürelerini ve son 2 aylık açılan-kapanan ürün detaylarını gösteren performans raporu.",
    "link": "https://prod-useast-b.online.tableau.com/#/site/emigros/views/YokSatmaBazlKapananrnRaporu/Dashboard1"
}
}

# === Slack + FastAPI ===
bolt_app = SlackApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
api = FastAPI()
handler = SlackRequestHandler(bolt_app)

def keyword_score(message, keywords):
    msg = message.lower()
    return sum(1 for kw in keywords if kw in msg)

def find_matching_reports(user_message):
    matches = []
    for name, info in TABLEAU_REPORTS.items():
        score = keyword_score(user_message, info["keywords"])
        if score > 0:
            matches.append((name, info))
    return matches

def openai_chat_response(user_message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Kısa ve net konuş. Profesyonel ama samimi ol."},
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return "Bir saniye, yeniden deniyorum 🙂"

@bolt_app.event("message")
def handle_message_events(body, say, logger):
    try:
        event = body.get("event", {})
        user = event.get("user")
        text = event.get("text", "").strip()

        if not user or event.get("bot_id"):
            return

        matches = find_matching_reports(text)

        if matches:
            say(f"<@{user}> 📊 İlgili raporlar aşağıda:")
            for name, rapor in matches:
                say(f"• **{name.title()}** → {rapor['desc']}\n🔗 {rapor['link']}")
            return

        reply = openai_chat_response(text)
        say(f"<@{user}> {reply}")

    except Exception as e:
        logger.error(e)
        say("Ufak bir hata oldu ama birkaç saniye içinde toparlarım 🚀")

@api.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)

@api.get("/")
def root():
    return {"status": "Analitik Tableau Slack Asistanı aktif 🚀"}
