import json
import os
from dotenv import load_dotenv
from groq import Groq
from product_parser import parse_product
import requests
import streamlit as st

load_dotenv()

# Настройка страницы в стиле Apple
st.set_page_config(
    page_title="PriceWatch",
    page_icon="💥",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Внедрение Apple-дизайна и скрытие лишних элементов интерфейса
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Карточки в стиле Apple (soft card) */
    .apple-card {
        background-color: #f5f5f7;
        padding: 24px;
        border-radius: 18px;
        border: 1px solid rgba(0, 0, 0, 0.04);
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
    }
    
    /* Поддержка темной темы */
    @media (prefers-color-scheme: dark) {
        .apple-card {
            background-color: #1c1c1e;
            border: 1px solid rgba(255, 255, 255, 0.06);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }
    }
    
    /* Скругленные кнопки */
    .stButton>button {
        border-radius: 980px;
        background-color: #0071e3;
        color: white;
        font-weight: 500;
        border: none;
        padding: 0.5rem 1.4rem;
        box-shadow: 0 2px 6px rgba(0, 113, 227, 0.3);
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        background-color: #0077ed;
        box-shadow: 0 4px 12px rgba(0, 113, 227, 0.4);
    }
    </style>
""",
    unsafe_allow_html=True,
)

# Подключение постоянного Production Webhook n8n
WEBHOOK_URL = "http://localhost:5678/webhook/PriceBot"

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
                        current = p["current_price"]
                        prev = p.get("previous_price", current)
                        delta_val = round(current - prev, 2)

                        st.metric(
                            label="Cari qiymət",
                            value=f"{current} {product_currency(p)}",
                            delta=f"{delta_val} {product_currency(p)}",
                            delta_color="inverse",
                        )

                        st.text(f"Hədəf: {p['target_price']} {product_currency(p)}")

                        if current <= p["target_price"]:
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
  
  url_input = st.text_input("Birmarket, Temu və ya Trendyol məhsulunun linkini daxil edin:")
  target_input = st.number_input("Hədəf qiymət (məhsulun valyutası):", min_value=0.0, step=1.0)
  
  if st.button("Məhsulu əlavə et / yenilə"):
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
          
          if existing_product:
            # Если товар уже есть — обновляем его параметры
            existing_product["target_price"] = target_input
            existing_product["currency"] = currency
            
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
              "market": parsed.get("market", "")
            }
            
            st.session_state.products.insert(0,new_product)
            save_products(st.session_state.products)
            st.success(f"Uğurla əlavə olundu: **{name}** | Qiymət: **{current_price} {currency}**")
        else:
          st.error(f"Xəta: {parsed.get('error', 'Məlumatı oxumaq mümkün olmadı')}")
    else:
      st.warning("Zəhmət olmasa linki daxil edin!")

# 3. ПРОВЕРИТЬ ЦЕНЫ & WEBHOOK & AI
elif choice == "Qiymətləri yoxla & AI Analiz":
    st.subheader("🔄 Bütün qiymətləri yenilə və AI analizi al")

    # Отображаем сохраненное уведомление, если оно есть в памяти сессии
    if "n8n_msg" in st.session_state:
        msg = st.session_state.n8n_msg
        if msg["type"] == "success":
            st.success(msg["text"])
        else:
            st.error(msg["text"])

    if not st.session_state.products:
        st.info("Siyahıda hələ məhsul yoxdur.")
    else:
        # Кнопка проверки всех товаров разом
        if st.button("⚡ Hamısının qiymətini indi yoxla", use_container_width=True):
            updated_count = 0
            progress_bar = st.progress(0)
            total_items = len(st.session_state.products)

            for idx, p in enumerate(st.session_state.products):
                with st.spinner(f"Yoxlanılır ({idx+1}/{total_items}): {p['name']}..."):
                    try:
                        parsed = parse_product(p["url"])
                    except Exception:
                        parsed = {"success": False}

                    if parsed.get("success"):
                        new_price = parsed["price"]
                        p["currency"] = parsed.get("currency", product_currency(p))
                        p["name"] = parsed.get("title", p["name"])
                        if parsed.get("image_url"):
                            p["image_url"] = parsed["image_url"]
                        prev = p.get("previous_price", p["current_price"])
                        if new_price != p["current_price"]:
                            p["previous_price"] = p["current_price"]
                            p["current_price"] = new_price
                            updated_count += 1
                
                progress_bar.progress((idx + 1) / total_items)

            save_products(st.session_state.products)

            # Отправка данных в n8n с сохранением статуса в session_state
            webhook_address = "http://localhost:5678/webhook-test/PriceBot"
            try:
                payload = st.session_state.products
                response = requests.post(webhook_address, json=payload, timeout=5)
                
                if response.status_code == 200:
                    st.session_state.n8n_msg = {
                        "type": "success", 
                        "text": f"✅ Bütün məhsullar yeniləndi ({updated_count} dəyişiklik) və n8n-ə göndərildi!"
                    }
                else:
                    st.session_state.n8n_msg = {
                        "type": "error", 
                        "text": f"⚠️ n8n cavab kodu: {response.status_code}"
                    }
            except Exception as e:
                st.session_state.n8n_msg = {
                    "type": "error", 
                    "text": f"❌ n8n-ə qoşulmaq mümkün olmadı: {e}"
                }
            
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
                    st.text(f"Cari: {p['current_price']} {product_currency(p)} | Hədəf: {p['target_price']} {product_currency(p)}")
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
                    st.text(f"Cari qiymət: {p['current_price']} {product_currency(p)}")
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
                    st.text(f"Cari qiymət: {p['current_price']} {product_currency(p)}")
                    st.markdown(f"🔗 [Link]({p['url']})")
                with col3:
                    # Уникальный ключ del_cart_... и удаление именно из cart
                    if st.button("🗑️ Sil", key=f"del_cart_{idx}"):
                        st.session_state.cart.pop(idx)
                        st.success("Məhsul səbətdən silindi!")
                        st.rerun()
                st.divider()
