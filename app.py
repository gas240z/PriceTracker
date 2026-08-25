import json
import os
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from product_parser import parse_product, convert_try_to_azn
import requests
import streamlit as st

import re

def clean_price(price_val):
    """Безопасно извлекает число из строки вроде '199.90 TRY (7.07 AZN)'."""
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if not price_val:
        return 0.0
    # Ищем первое число в строке
    match = re.search(r'\d+[.,]?\d*', str(price_val).replace(' ', ''))
    if match:
        try:
            return float(match.group(0).replace(',', '.'))
        except ValueError:
            return 0.0
    return 0.0


def format_price_with_azn(product, price_value, azn_value):
    """Trendyol məhsulları üçün qiymətin yanında mötərizədə manat (₼) ekvivalentini
    göstərir, digər marketlər üçün olduğu kimi saxlanılır."""
    currency = product_currency(product)
    if product.get("market") == "Trendyol" and currency == "TRY" and azn_value not in (None, ""):
        try:
            azn_num = float(azn_value)
            return f"{price_value} {currency} (₼{azn_num:,.2f})"
        except (TypeError, ValueError):
            pass
    return f"{price_value} {currency}"

# .env faylını app.py-nin özü ilə eyni qovluqdan oxuyur — Streamlit hansı
# qovluqdan işə salınırsa işə salınsın (working directory fərq etmir).
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# Настройка страницы в стиле Apple
st.set_page_config(
    page_title="PriceWatch",
    page_icon="💥",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Внедрение Apple-дизайна (светло-фиолетовая тема) и скрытие лишних элементов интерфейса
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Мягкий светло-фиолетовый фон приложения (вместо резкого белого/тёмного) */
    .stApp {
        background-color: #F4F1FB !important;
    }
    [data-testid="stSidebar"] {
        background-color: #EAE2F7 !important;
    }
    [data-testid="stHeader"] {
        background-color: rgba(0, 0, 0, 0) !important;
    }

    /* Тёмная тема Streamlit красит весь текст в светлый цвет — на светлом фоне
       он становится нечитаемым. Принудительно задаём тёмный, приятный для глаз
       цвет текста везде, кроме кнопок (у них свой белый текст, см. ниже). */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp li,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"],
    [data-testid="stMarkdownContainer"], .stTextInput label, .stNumberInput label,
    .stSelectbox label {
        color: #2B2340 !important;
    }
    [data-testid="stMetricDelta"] {
        color: inherit !important;
    }

    /* Поля ввода: белый фон, тёмный читаемый текст, мягкая рамка вместо красной */
    .stTextInput input, .stNumberInput input {
        background-color: #FFFFFF !important;
        color: #2B2340 !important;
        border: 1px solid #D9CCF2 !important;
        border-radius: 12px !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #7C4DFF !important;
        box-shadow: 0 0 0 1px #7C4DFF !important;
    }
    div[data-baseweb="select"] > div,
    div[data-baseweb="select"] > div > div,
    div[data-baseweb="select"] [data-baseweb="input"] {
        background-color: #FFFFFF !important;
        border-color: #D9CCF2 !important;
        box-shadow: none !important;
        color: #2B2340 !important;
    }
    div[data-baseweb="select"]:focus-within > div {
        border-color: #7C4DFF !important;
        box-shadow: 0 0 0 1px #7C4DFF !important;
    }
    div[data-baseweb="select"] * {
        color: #2B2340 !important;
    }

    /* Форma sahələrini yığcam, ağ "kart" içində göstərmək üçün */
    div[data-testid="stForm"] {
        background-color: #FFFFFF;
        padding: 28px;
        border-radius: 18px;
        border: 1px solid rgba(120, 80, 200, 0.12);
        box-shadow: 0 4px 16px rgba(120, 80, 200, 0.10);
    }

    /* Карточки в стиле Apple (soft card) на светло-фиолетовом фоне */
    .apple-card {
        background-color: #FFFFFF;
        padding: 24px;
        border-radius: 18px;
        border: 1px solid rgba(120, 80, 200, 0.12);
        margin-bottom: 20px;
        box-shadow: 0 4px 16px rgba(120, 80, 200, 0.10);
    }

    /* Скругленные кнопки (обычные и кнопка отправки формы) — текст всегда белый */
    .stButton>button,
    div[data-testid="stFormSubmitButton"]>button {
        border-radius: 980px !important;
        background-color: #7C4DFF !important;
        color: #FFFFFF !important;
        font-weight: 500 !important;
        border: none !important;
        padding: 0.55rem 1.6rem !important;
        box-shadow: 0 2px 6px rgba(124, 77, 255, 0.25);
        transition: all 0.2s ease;
    }
    .stButton>button p, .stButton>button span,
    div[data-testid="stFormSubmitButton"]>button p,
    div[data-testid="stFormSubmitButton"]>button span {
        color: #FFFFFF !important;
    }
    .stButton>button:hover,
    div[data-testid="stFormSubmitButton"]>button:hover {
        background-color: #6A3DFF !important;
        box-shadow: 0 4px 12px rgba(124, 77, 255, 0.35);
    }

    /* Toast (st.toast) ayrıca DOM qatında render olunur — ona görə ayrıca stil lazımdır */
    [data-testid="stToast"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D9CCF2 !important;
        box-shadow: 0 4px 16px rgba(120, 80, 200, 0.15) !important;
    }
    [data-testid="stToast"] * {
        color: #2B2340 !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# n8n workflow-daki YENİ Webhook trigger — eyni flow-u (HTTP Request1 → Split Out
# → If1 → Telegram) DƏRHAL işə salır. Respond = "Immediately" olmalıdır ki,
# Streamlit uzun-uzadı gözləməsin (AI mətnləri + bir neçə foto göndərmək vaxt alır).
N8N_TRIGGER_URL = os.getenv("N8N_TRIGGER_URL", "http://localhost:5678/webhook/PriceBot-manual")

# Инициализация Groq AI
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

DATA_FILE = "products.json"


def load_products():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return []
  return []


def save_products(products):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=4)


def product_currency(product):
  """Old saved Birmarket products did not have a currency field."""
  return product.get("currency", "AZN")


# Инициализация сеанса
if "products" not in st.session_state:
  st.session_state.products = load_products()

if "cart" not in st.session_state:
  st.session_state.cart = []

# Сайдбар (Корзина)
st.sidebar.divider()
st.sidebar.subheader(f"🛒 Səbət ({len(st.session_state.cart)})")

if st.session_state.cart:
  currencies = {product_currency(item) for item in st.session_state.cart}
  if len(currencies) == 1:
    total_cost = sum(item["current_price"] for item in st.session_state.cart)
    st.sidebar.markdown(f"**Ümumi məbləğ:** {total_cost:.2f} {currencies.pop()}")
  else:
    st.sidebar.markdown("**Ümumi məbləğ:** müxtəlif valyutalar")
  if st.sidebar.button("Səbəti təmizlə"):
    st.session_state.cart.clear()
    st.rerun()
else:
  st.sidebar.info("Səbətiniz boşdur.")

# ИИ-анализатор
def get_ai_market_advice(product_name, current_price, target_price):
  if not groq_client:
    return "Groq API ключ не найден в .env файле."
  prompt = f"""
    Ты профессиональный финансовый аналитик и умный помощник по шопингу.
    Товар: '{product_name}'
    Текущая цена: {current_price}
    Целевая цена пользователя: {target_price}
    Дай короткий, точный и мотивирующий совет на русском языке (максимум 2-3 предложения): стоит ли покупать сейчас или лучше подождать дальнейшего снижения цены?
    """
  try:
    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": "You are an expert shopping and price-tracking advisor.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content
  except Exception as e:
    return f"Ошибка ИИ: {e}"


# Главный заголовок
st.markdown(
    "<h1 style='font-weight: 600; letter-spacing: -0.5px;'>PriceWatch</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color: #86868b; margin-top: -10px;'>Интеллектуальный"
    " мониторинг цен в стиле Apple</p>",
    unsafe_allow_html=True,
)
st.divider()

# Навигация
choice = st.sidebar.selectbox(
    "Menyu seçin",
    [
        "Məhsulları göstər",
        "Məhsul əlavə et",
        "Məhsul sil",
        "Səbət",
        "Qiymətləri yoxla & AI Analiz",
    ],
)

# 1. ПОКАЗАТЬ ТОВАРЫ
if choice == "Məhsulları göstər":
    st.subheader("📋 Siyahıdakı məhsullar")

    if not st.session_state.products:
        st.info("Siyahıda hələ məhsul yoxdur.")
    else:
        products_per_row = 3
        products = st.session_state.products

        for i in range(0, len(products), products_per_row):
            cols = st.columns(products_per_row, gap="large")
            chunk = products[i : i + products_per_row]

            for col_idx, p in enumerate(chunk):
                global_idx = i + col_idx

                with cols[col_idx]:
                    with st.container():
                        # Премиальная бирка статуса в стиле Apple вместо кнопки сверху
                        st.markdown(
                            """
                            <div style='font-size: 12px; font-weight: 600; color: #86868b; 
                            text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;'>
                                🟢 Aktiv İzləmədə
                            </div>
                            """, 
                            unsafe_allow_html=True,
                        )

                        if p.get("image_url"):
                            st.image(p["image_url"], use_container_width=True)
                        else:
                            st.warning("Şəkil yoxdur")

                        st.markdown(
                            f"<h4 style='margin: 10px 0 12px 0; font-size: 1.05rem;"
                            f" font-weight: 600;'>{p['name']}</h4>",
                            unsafe_allow_html=True,
                        )

                        # Расчет дельты
                        current = clean_price(p["current_price"])
                        prev = clean_price(p.get("previous_price", current))
                        delta_val = round(current - prev, 2)

                        # st.metric() uzun mətni (mötərizədəki manat qiyməti ilə birlikdə)
                        # kəsib "..." göstərirdi — ona görə eyni görünüşü özümüz,
                        # kəsilmə olmadan çəkirik.
                        price_str = format_price_with_azn(p, p["current_price"], p.get("price_azn"))
                        if delta_val > 0:
                            delta_bg, delta_fg, delta_arrow = "#FCE4E4", "#C0392B", "↑"
                        elif delta_val < 0:
                            delta_bg, delta_fg, delta_arrow = "#E3F5E8", "#1E8449", "↓"
                        else:
                            delta_bg, delta_fg, delta_arrow = "#EFEAFB", "#6B6280", "↑"
                        st.markdown(
                            f"""
                            <div style='margin-bottom: 10px;'>
                                <div style='font-size: 14px; color: #6B6280; font-weight: 500;'>Cari qiymət</div>
                                <div style='font-size: 1.55rem; font-weight: 700; color: #2B2340;
                                            line-height: 1.25; word-break: break-word; margin: 2px 0 6px 0;'>
                                    {price_str}
                                </div>
                                <span style='display: inline-block; padding: 2px 10px; border-radius: 999px;
                                             background: {delta_bg}; color: {delta_fg}; font-size: 13px; font-weight: 600;'>
                                    {delta_arrow} {abs(delta_val)} {product_currency(p)}
                                </span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        st.text(f"Hədəf: {format_price_with_azn(p, p['target_price'], p.get('target_price_azn'))}")

                        if current <= clean_price(p["target_price"]):
                            st.success("✅ Sərfəlidir!")
                        else:
                            st.warning("⏳ Gözləmək.")

                        st.markdown(f"🔗 [Link]({p['url']})")

                        # Нижняя кнопка добавления в корзину с корректной логикой
                        if st.button(f"🛒 Səbətə at", key=f"grid_cart_{global_idx}", use_container_width=True):
                            if "cart" not in st.session_state:
                                st.session_state.cart = []
                            
                            if p not in st.session_state.cart:
                                st.session_state.cart.insert(0, p)
                                st.toast(f"✅ {p['name'][:15]}... səbətə əlavə olundu!")
                                st.rerun()
                            else:
                                st.toast("⚠️ Bu məhsul artıq səbətdədir!")

                        if st.button(f"🤖 AI Məsləhət", key=f"grid_ai_{global_idx}", use_container_width=True):
                            with st.spinner("Təhlil..."):
                                advice = get_ai_market_advice(
                                    p["name"], p["current_price"], p["target_price"]
                                )
                                st.success(advice)

                        st.markdown("</div>", unsafe_allow_html=True)

            st.markdown(
                "<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True
            )

# 2. ДОБАВИТЬ ТОВАР
# 2. ДОБАВИТЬ ИЛИ ОБНОВИТЬ ТОВАР
elif choice == "Məhsul əlavə et":
  st.subheader("➕ Yeni Məhsul Əlavə Et və ya Yenilə")

  # st.form + clear_on_submit=True: düymə basılan kimi hər iki sahə avtomatik
  # təmizlənir, əl ilə silməyə ehtiyac qalmır.
  with st.form("add_product_form", clear_on_submit=True):
    url_input = st.text_input("Birmarket, Temu və ya Trendyol məhsulunun linkini daxil edin:")
    target_input = st.number_input("Hədəf qiymət (məhsulun valyutası):", min_value=0.0, step=1.0)
    submitted = st.form_submit_button("Məhsulu əlavə et / yenilə")

  if submitted:
    if url_input:
      # Проверяем, есть ли уже товар с такой ссылкой в списке
      existing_product = next((item for item in st.session_state.products if item["url"] == url_input), None)
      
      with st.spinner("Məhsul məlumatları çəkilir..."):
        parsed = parse_product(url_input)
        
        if parsed.get("success"):
          name = parsed["title"]
          current_price = parsed["price"]
          image_url = parsed.get("image_url", "")
          currency = parsed.get("currency", "AZN")
          market = parsed.get("market", "")
          price_azn = parsed.get("price_azn") if market == "Trendyol" else None
          target_azn = convert_try_to_azn(target_input) if market == "Trendyol" else None

          if existing_product:
            # Если товар уже есть — обновляем его параметры
            existing_product["target_price"] = target_input
            existing_product["currency"] = currency
            existing_product["market"] = market
            existing_product["price_azn"] = price_azn
            existing_product["target_price_azn"] = target_azn
            
            # Сохраняем историю цен, если цена изменилась
            if current_price != existing_product["current_price"]:
              existing_product["previous_price"] = existing_product["current_price"]
              existing_product["current_price"] = current_price
              
            if image_url:
              existing_product["image_url"] = image_url
              
            save_products(st.session_state.products)
            st.success(f"Məhsul yeniləndi: **{name}** | Yeni hədəf: **{target_input} {currency}** | Cari qiymət: **{current_price} {currency}**")
          else:
            # Если товара нет — создаем новый
            new_product = {
              "name": name,
              "url": url_input,
              "current_price": current_price,
              "target_price": target_input,
              "previous_price": current_price,
              "image_url": image_url,
              "currency": currency,
              "market": market,
              "price_azn": price_azn,
              "target_price_azn": target_azn,
            }
            
            st.session_state.products.insert(0,new_product)
            save_products(st.session_state.products)
            st.success(f"Uğurla əlavə olundu: **{name}** | Qiymət: **{current_price} {currency}**")
        else:
          st.error(f"Xəta: {parsed.get('error', 'Məlumatı oxumaq mümkün olmadı')}")
    else:
      st.warning("Zəhmət olmasa linki daxil edin!")

# 3. ПРОВЕРИТЬ ЦЕНЫ & TELEGRAM & AI
elif choice == "Qiymətləri yoxla & AI Analiz":
    st.subheader("🔄 Bütün qiymətləri yenilə və AI analizi al")

    # Toast bir dəfəlikdir: session_state-dən dərhal silinir, ona görə
    # menyunu dəyişəndə və ya səhifə yenidən çəkiləndə bir daha görünmür —
    # özü bir neçə saniyəyə ekrandan itir.
    if "check_toast" in st.session_state:
        toast = st.session_state.pop("check_toast")
        st.toast(toast["text"], icon="✅" if toast["type"] == "success" else "⚠️")

    if not st.session_state.products:
        st.info("Siyahıda hələ məhsul yoxdur.")
    else:
        # Bu düymə n8n-dəki YENİ Webhook trigger-i çağırır — həmin trigger eyni
        # flow-u (HTTP Request1 → Split Out → If1 → Telegram) dərhal işə salır,
        # Schedule Trigger1 (hər 8 saatda) ilə paralel, amma indi əl ilə.
        if st.button("⚡ Hamısının qiymətini indi yoxla və Telegram-a göndər", use_container_width=True):
            with st.spinner("n8n workflow işə salınır (real-time yoxlama + Telegram)..."):
                try:
                    resp = requests.get(N8N_TRIGGER_URL, timeout=30)
                    resp.raise_for_status()
                    triggered_ok = True
                except Exception as e:
                    triggered_ok = False
                    st.session_state.check_toast = {
                        "type": "error",
                        "text": f"❌ n8n workflow-a qoşulmaq mümkün olmadı: {e}",
                    }

            if triggered_ok:
                st.session_state.check_toast = {
                    "type": "success",
                    "text": (
                        "n8n workflow işə salındı! Endirim tapılan məhsullar "
                        "bir neçə saniyəyə Telegram-a gələcək."
                    ),
                }
                # products.json backend (main.py) tərəfindən bir neçə saniyəyə yenilənəcək —
                # siyahını təzələmək üçün səhifəni bir az sonra əl ilə yeniləmək kifayətdir.
                st.session_state.products = load_products()

            st.rerun()

        st.divider()
        st.markdown("### 📦 Məhsullar üzrə fərdi idarəetmə")

        for idx, p in enumerate(st.session_state.products):
            with st.container():
                cols = st.columns([1, 3, 2])

                with cols[0]:
                    if p.get("image_url"):
                        st.image(p["image_url"], width=80)
                    else:
                        st.text("Şəkil yoxdur")

                with cols[1]:
                    st.markdown(f"**{p['name']}**")
                    st.text(
                        f"Cari: {format_price_with_azn(p, p['current_price'], p.get('price_azn'))} "
                        f"| Hədəf: {format_price_with_azn(p, p['target_price'], p.get('target_price_azn'))}"
                    )
                    st.markdown(f"🔗 [Link]({p['url']})")

                with cols[2]:
                    if st.button("🔄 Qiyməti yoxla", key=f"check_single_{idx}", use_container_width=True):
                        with st.spinner("Yoxlanılır..."):
                            try:
                                parsed = parse_product(p["url"])
                            except Exception:
                                parsed = {"success": False}

                            if parsed.get("success"):
                                new_price = parsed["price"]
                                p["currency"] = parsed.get("currency", product_currency(p))
                                p["name"] = parsed.get("title", p["name"])
                                p["market"] = parsed.get("market", p.get("market", ""))
                                if p["market"] == "Trendyol":
                                    p["price_azn"] = parsed.get("price_azn")
                                    p["target_price_azn"] = convert_try_to_azn(clean_price(p["target_price"]))
                                if parsed.get("image_url"):
                                    p["image_url"] = parsed["image_url"]
                                if new_price != p["current_price"]:
                                    p["previous_price"] = p["current_price"]
                                    p["current_price"] = new_price
                                    save_products(st.session_state.products)
                                    st.success("Qiymət yeniləndi!")
                                else:
                                    st.info("Qiymət dəyişməyib.")
                                st.rerun()
                            else:
                                st.error("Məlumatı oxumaq olmadı (Sayt cavab vermir).")

                    if st.button("🤖 AI Təhlil", key=f"ai_single_{idx}", use_container_width=True):
                        with st.spinner("AI təhlil edir..."):
                            advice = get_ai_market_advice(
                                p["name"], p["current_price"], p["target_price"]
                            )
                            st.success(advice)

                st.divider()

# 4. УДАЛИТЬ ТОВАР
elif choice == "Məhsul sil":
    st.subheader("🗑️ Məhsulu siyahıdan silmək")
    
    if not st.session_state.products:
        st.info("Siyahı boşdur.")
    else:
        if st.button("🗑️ Bütün siyahını təmizlə"):
            st.session_state.products.clear()
            save_products(st.session_state.products)
            st.success("Bütün məhsul siyahısı silindi!")
            st.rerun()

        st.divider()
        
        # Цикл перебирает все товары. Обратите внимание на ровные отступы ниже!
        for idx, p in enumerate(st.session_state.products):
            with st.container():
                col1, col2, col3 = st.columns([1, 3, 1])
                
                with col1:
                    if p.get("image_url"):
                        st.image(p["image_url"], width=100)
                        
                with col2:
                    st.markdown(f"**{p['name']}**")
                    st.text(f"Cari qiymət: {format_price_with_azn(p, p['current_price'], p.get('price_azn'))}")
                    st.markdown(f"🔗 [Link]({p['url']})")
                    
                with col3:
                    if st.button("🗑️ Sil", key=f"del_main_{idx}"):
                        st.session_state.products.pop(idx)
                        save_products(st.session_state.products)
                        st.success("Məhsul silindi!")
                        st.rerun()
                        
            st.divider()

# 5. КОРЗИНА
elif choice == "Səbət":
    st.subheader("🛒 Səbətiniz")
    
    if not st.session_state.cart:
        st.info("Səbətiniz hələ ki boşdur.")
    else:
        if st.button("🗑️ Bütün səbəti təmizlə"):
            st.session_state.cart.clear()
            st.success("Səbət tamamilə təmizləndi!")
            st.rerun()

        st.divider()
        currencies = {product_currency(item) for item in st.session_state.cart}
        if len(currencies) == 1:
            total_cost = sum(item["current_price"] for item in st.session_state.cart)
            st.markdown(f"### Ümumi məbləğ: **{total_cost:.2f} {currencies.pop()}**")
        else:
            st.markdown("### Ümumi məbləğ: **müxtəlif valyutalar**")
        st.divider()

        # ВАЖНО: теперь отступы внутри else, и перебирается именно cart!
        for idx, p in enumerate(st.session_state.cart):
            with st.container():
                col1, col2, col3 = st.columns([1, 3, 1])
                with col1:
                    if p.get("image_url"):
                        st.image(p["image_url"], width=100)
                with col2:
                    st.markdown(f"**{p['name']}**")
                    st.text(f"Cari qiymət: {format_price_with_azn(p, p['current_price'], p.get('price_azn'))}")
                    st.markdown(f"🔗 [Link]({p['url']})")
                with col3:
                    # Уникальный ключ del_cart_... и удаление именно из cart
                    if st.button("🗑️ Sil", key=f"del_cart_{idx}"):
                        st.session_state.cart.pop(idx)
                        st.success("Məhsul səbətdən silindi!")
                        st.rerun()
                st.divider()