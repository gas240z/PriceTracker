# PriceWatch 💥

Qiymət monitorinqi üçün intellektual sistem — Birmarket, Temu və Trendyol-dan məhsul linki əlavə edirsən, sistem qiymətləri arxa fonda izləyir, hədəf qiymətə çatdıqda (və ya ucuzlaşdıqda) avtomatik Telegram-a xəbər göndərir, üstəlik Groq AI ilə qısa "alışa çağırış" mətni yazır.

## 🧩 Arxitektura

```
┌─────────────────┐        ┌──────────────────┐        ┌─────────────────┐
│   Streamlit UI    │──────▶│   n8n (Webhook /    │──────▶│  FastAPI backend  │
│    (app.py)        │  GET  │  Schedule Trigger)  │  GET  │    (main.py)       │
└─────────────────┘        └──────────────────┘        └─────────────────┘
        ▲                          │                             │
        │                          ▼                             ▼
        │                  ┌──────────────┐            ┌──────────────────┐
        │                  │ Split Out/If1 │            │  product_parser.py │
        │                  │ (yalnız       │            │ (Birmarket/Temu/   │
        │                  │  endirimlər)  │            │  Trendyol scraper)  │
        │                  └──────────────┘            └──────────────────┘
        │                          │                             │
        │                          ▼                             ▼
        │                  ┌──────────────┐            ┌──────────────────┐
        └──────────────────│ Telegram bot  │            │   products.json    │
         (products.json-u  └──────────────┘            │  (paylaşılan DB)    │
          yenidən oxuyur)                                └──────────────────┘
```

**Qısaca:**
- **`app.py` (Streamlit)** — istifadəçi interfeysi: məhsul əlavə et/sil/göstər, səbət, "indi yoxla" düyməsi.
- **`product_parser.py`** — Birmarket, Temu, Trendyol məhsul səhifələrini oxuyub ad/qiymət/valyuta/şəkil çıxarır. Trendyol üçün qiymət həmişə **TRY**-dır, AZN ekvivalenti ayrıca hesablanır (`price_azn`).
- **`main.py` (FastAPI)** — `/check-prices` endpoint-i: bütün məhsulları real-time yenidən yoxlayır, qiymətləri düzgün valyutada müqayisə edir, `products.json`-u yeniləyir, endirim tapılanlar üçün Groq AI ilə mətn yazır və Telegram-a hazır mesaj formalaşdırır.
- **n8n** — orkestrasiya qatı: ya `Schedule Trigger1` ilə hər 8 saatda, ya da Streamlit-dəki düymədən gələn `Webhook` ilə dərhal `/check-prices`-i çağırır, nəticəni (`alerts`) filtrləyib (`Split Out` → `If1`) Telegram-a göndərir.
- **`products.json`** — Streamlit və FastAPI backend-in birgə istifadə etdiyi sadə fayl-based "verilənlər bazası".

## 🚀 Xüsusiyyətlər

- 3 marketplace dəstəyi: **Birmarket**, **Temu**, **Trendyol** (AZN, TRY avtomatik tanınır və çevrilir)
- Trendyol üçün qiymət TRY-də saxlanılır, manat (₼) ekvivalenti mötərizədə göstərilir
- Hədəf qiymətə çatanda / qiymət düşəndə avtomatik **Telegram** bildirişi (foto + mətn)
- **Groq AI** ilə hər endirim üçün fərdi, əyləncəli "alışa çağırış" mətni (retry məntiqi ilə, rate-limit-ə davamlı)
- **n8n** ilə həm planlı (hər 8 saatda), həm də əl ilə ("indi yoxla" düyməsi) yoxlama
- Səbət, məhsul silmə, fərdi/toplu qiymət yoxlama
- Apple-stilli, açıq bənövşəyi dizayn (tünd tema uyğunluğu ilə)

## 📁 Layihə strukturu

```
.
├── app.py                 # Streamlit UI
├── main.py                # FastAPI backend (/check-prices)
├── product_parser.py      # Marketplace parser-ləri (Birmarket/Temu/Trendyol)
├── products.json          # İzlənilən məhsulların siyahısı (avtomatik yaranır/yenilənir)
├── requirements.txt       # Python asılılıqları
├── .env                   # Sirr açarları (GİT-ə DAXİL ETMƏYİN)
├── .streamlit/
│   └── config.toml        # Streamlit tema tənzimləməsi
├── docker-compose.yml     # 3 servisi (streamlit/backend/n8n) birgə işə salır
├── Dockerfile.streamlit   # Streamlit üçün image
├── Dockerfile.backend     # FastAPI backend üçün image
└── README.md
```

## ⚙️ Quraşdırma (lokal, Docker olmadan)

**Tələblər:** Python 3.11+, işləyən n8n instansiyası (lokal və ya Docker).

```bash
# 1. Asılılıqları qur
pip install -r requirements.txt

# 2. .env faylını yarat (layihənin kök qovluğunda)
GROQ_API_KEY=gsk_...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=5445770584

# 3. Backend-i işə sal
uvicorn main:app --reload --port 8000

# 4. Ayrı terminalda Streamlit-i işə sal
streamlit run app.py
```

n8n-i ayrıca işə salıb (`http://localhost:5678`) aşağıdakı node-ları qurun:

1. **Schedule Trigger1** — hər 8 saatda bir işə düşür
2. **Webhook** — GET, path: `PriceBot-manual`, Respond: `Immediately` (Streamlit-dəki "indi yoxla" düyməsi bunu çağırır)
3. **HTTP Request1** — GET `http://localhost:8000/check-prices` (backend-i lokal işlədirsinizsə) — hər iki trigger-dən buraya bağlanır
4. **Split Out** — `alerts` sahəsini ayrı-ayrı elementlərə bölür
5. **If1** — `discount_found == true` olanları filtrləyir
6. **Send a photo message (Telegram)** — `photo: {{ $json.image_url }}`, `caption: {{ $json.telegram_message }}`, Parse Mode: `Markdown (Legacy)`

Workflow-u **Active** etməyi unutmayın — əks halda production Webhook URL 404 qaytarır.

## 🐳 Quraşdırma (Docker Compose ilə, server üzərində)

```bash
# Layihəni serverə köçürün (.venv, __pycache__, .idea istisna olmaqla)
docker compose up -d --build
```

Bu, 3 konteyner qaldırır:
- `pricewatch_streamlit` → port **8501**
- `pricewatch_backend` → port **8000**
- `pricewatch_n8n` → port **5678**

Docker şəbəkəsi daxilində servislər bir-birini **konteyner adı** ilə tapır (`host.docker.internal` yox!):
- n8n-dəki `HTTP Request1`: `http://backend:8000/check-prices`
- Streamlit-in `N8N_TRIGGER_URL`: `http://n8n:5678/webhook/PriceBot-manual` (artıq `docker-compose.yml`-də `environment` altında təyin olunub)

Sonra brauzerdə:
- `http://SERVER_IP:8501` — tətbiq
- `http://SERVER_IP:5678` — n8n paneli (ilk dəfə admin hesabı yaradın, Telegram credential-ı yenidən bağlayın)

## 🔑 Lazım olan mühit dəyişənləri (`.env`)

| Dəyişən | Təyinatı |
|---|---|
| `GROQ_API_KEY` | Groq AI mətn generasiyası üçün ([console.groq.com](https://console.groq.com)) |
| `TELEGRAM_BOT_TOKEN` | Telegram botunuzun tokeni ([@BotFather](https://t.me/BotFather)) |
| `TELEGRAM_CHAT_ID` | Bildirişlərin göndəriləcəyi çat ID-si |
| `N8N_TRIGGER_URL` *(könüllü)* | n8n manual webhook URL-i (default: `http://localhost:5678/webhook/PriceBot-manual`) |
| `CHECK_PRICES_URL` *(könüllü)* | FastAPI backend ünvanı (default: `http://localhost:8000/check-prices`) |

## 🧠 Qiymət/valyuta məntiqi (vacib qeyd)

- **Birmarket, Temu** → qiymət **AZN**-dədir, birbaşa istifadə olunur.
- **Trendyol** → sayt Azərbaycan üçün qiyməti vizual olaraq ₼-ə çevirib göstərir, amma sistemdə əsl qiymət **həmişə TRY** kimi saxlanılır (`product_parser.py` bunu JSON-LD / daxili state-dən çıxarır, ₼-lə göstərilən mətnə etibar etmir).
- Hədəf qiymət (`target_price`) də məhsulun **öz valyutasında** (Trendyol üçün TRY) daxil edilir.
- Müqayisə həmişə **eyni valyutaya çevrilərək** aparılır (`main.py`-də `to_azn()`), əks halda TRY ilə AZN səhv müqayisə olunub yanlış "endirim tapıldı" siqnalı yarana bilər.

## 🛠 İstifadə olunan texnologiyalar

Streamlit · FastAPI · BeautifulSoup + requests · Groq (`openai/gpt-oss-120b`) · n8n · Telegram Bot API · Docker

## 📌 Məlum məhdudiyyətlər

- `products.json` fayl-based DB-dir — çoxlu paralel istifadəçi/yazma üçün nəzərdə tutulmayıb.
- Streamlit tətbiqi açıq linklə paylaşılırsa, parol qorumasız hər kəs məhsul əlavə/sil edə bilər.
- Marketplace parser-ləri HTML strukturuna bağlıdır — sayt dizaynı dəyişərsə, `product_parser.py`-də tənzimləmə tələb oluna bilər.
