import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from fastapi import FastAPI
from groq import Groq

from product_parser import parse_product

# .env faylını main.py-nin özü ilə eyni qovluqdan oxuyur — uvicorn hansı
# qovluqdan işə salınırsa işə salınsın (working directory fərq etmir).
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

app = FastAPI()

groq_api_key = (os.getenv("GROQ_API_KEY") or "").strip().strip('"').strip("'")
groq_client = Groq(api_key=groq_api_key)

# Курсы валют для приведения цен сайта к МАНАТАМ
TRY_TO_AZN = 0.05
USD_TO_AZN = 1.70
EUR_TO_AZN = 1.85
RUB_TO_AZN = 0.018

# Единая таблица курсов — используется И для текущей цены, И для целевой,
# чтобы они всегда сравнивались в одних и тех же единицах (AZN).
CURRENCY_TO_AZN_RATE = {
    "AZN": 1.0,
    "TRY": TRY_TO_AZN,
    "USD": USD_TO_AZN,
    "EUR": EUR_TO_AZN,
    "RUB": RUB_TO_AZN,
}


def to_azn(amount: float, currency: str) -> float:
    """Verilmiş məbləği (hər hansı dəstəklənən valyutada) AZN-ə çevirir."""
    rate = CURRENCY_TO_AZN_RATE.get(currency, 1.0)
    return amount * rate


def clean_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    return raw_url.split("?")[0]


def extract_number(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).replace(',', '.')
    match = re.search(r"(\d+(?:\.\d+)?)", val_str)
    if match:
        return float(match.group(1))
    return 0.0


def detect_currency(val, default="AZN") -> str:
    if not val:
        return default
    val_str = str(val).upper()
    if "TRY" in val_str or "TL" in val_str or "₺" in val_str:
        return "TRY"
    if "USD" in val_str or "$" in val_str:
        return "USD"
    if "EUR" in val_str or "€" in val_str:
        return "EUR"
    if "RUB" in val_str or "₽" in val_str:
        return "RUB"
    if "AZN" in val_str or "₼" in val_str:
        return "AZN"
    return default


def escape_md(text: str) -> str:
    """Экранирует спецсимволы Telegram Markdown (Legacy), чтобы сообщение не сломалось."""
    if not text:
        return text
    for ch in ['_', '*', '`', '[']:
        text = text.replace(ch, f'\\{ch}')
    return text


def get_ai_hook(short_title: str, current_price, site_currency: str, max_retries: int = 3) -> str:
    """Groq-dan alışa çağıran qısa mətn alır. Rate-limit (429) və ya müvəqqəti
    şəbəkə xətaları üçün bir neçə cəhd edir (artan gecikmə ilə), hamısı
    uğursuz olarsa hazır fallback mətni qaytarır."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": "Ты веселый ассистент по шопингу."},
                    {"role": "user",
                     "content": f"Товар: {short_title}. Цена упала до {current_price} {site_currency}! Напиши короткий, зажигательный призыв к покупке с эмодзи (1-2 предложения), без упоминания цен."
                                f"Не используй Markdown-разметку (категорически запрещены звездочки ** вокруг текста)!!"}
                ],
                temperature=0.7,
                max_tokens=150,
            )
            ai_hook = response.choices[0].message.content.strip().replace("**", "").replace("*", "")
            return escape_md(ai_hook)
        except Exception as exc:
            last_exc = exc
            print(f"DEBUG GROQ ERROR (cəhd {attempt}/{max_retries}): {exc}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # 2s, 4s, ...

    print(f"DEBUG: Groq {max_retries} cəhddən sonra da cavab vermədi, fallback mətn istifadə olunur: {last_exc}")
    return "🔥 Не упусти шанс купить по суперцене!"


def safe_markdown_url(url: str) -> str:
    """
    Заменяет круглые скобки в ссылке на их URL-кодированный вид (%28 / %29),
    чтобы они не ломали синтаксис Markdown-ссылки [текст](url).
    Ссылка при клике всё равно откроется корректно.
    """
    if not url:
        return url
    return url.replace("(", "%28").replace(")", "%29")


def load_tracked_products():
    if os.path.exists("products.json"):
        try:
            with open("products.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"DEBUG: Ошибка чтения products.json: {e}")
            return []
    return []


def save_tracked_products(products):
    try:
        with open("products.json", "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"DEBUG: Ошибка записи products.json: {e}")


@app.get("/check-prices")
def check_prices():
    products = load_tracked_products()
    alerts = []
    updated_count = 0

    if not products:
        return {"status": "error", "message": "Siyahıda məhsul yoxdur", "alerts": []}

    for item in products:
        raw_url = item.get("url", "")
        url = clean_url(raw_url)

        if not raw_url:
            continue

        parsed = parse_product(url)

        # 1. Если чистая ссылка не прошла, пробуем оригинальную
        if not parsed.get("success"):
            print(f"DEBUG: Чистая ссылка не прошла, пробуем оригинальную: {raw_url}")
            parsed = parse_product(raw_url)
            if parsed.get("success"):
                url = raw_url

        # 2. Если оригинальная не прошла, пробуем раскодировать URL (помогает для Temu)
        if not parsed.get("success"):
            decoded_url = urllib.parse.unquote(raw_url)
            if decoded_url != raw_url:
                print(f"DEBUG: Пробуем декодированную ссылку: {decoded_url}")
                parsed = parse_product(decoded_url)
                if parsed.get("success"):
                    url = decoded_url

        # 3. ФОЛЛБЕК (Резерв) - Если парсер окончательно упал
        # Берем цену из базы данных, чтобы товар не потерялся
        if not parsed.get("success"):
            print(f"DEBUG: ❌ ОШИБКА ПАРСЕРА. Пытаемся взять цену из базы данных для: {raw_url}")
            db_price_raw = item.get("current_price") or item.get("price")
            if db_price_raw:
                parsed = {
                    "success": True,
                    "price": db_price_raw,
                    "currency": item.get("currency", "AZN"),
                    "title": item.get("name") or "Məhsul",
                    "image_url": item.get("image_url", "")
                }
                print(f"DEBUG: ✔️ Использована цена из базы: {db_price_raw}")
            else:
                print(f"DEBUG: В базе тоже нет цены, пропускаем товар.")
                continue

        # --- Сравнение цен ---
        # Целевая цена ("Hədəf") хранится в РОДНОЙ валюте товара (для Trendyol —
        # это TRY, см. app.py), а не в манатах. Поэтому её нельзя использовать
        # напрямую как "target_price_azn" — сначала нужно узнать валюту товара
        # и только потом конвертировать (ниже, вместе с текущей ценой).
        target_raw = item.get("target_price") or item.get("target") or item.get("targetPrice")
        target_price_native = extract_number(target_raw)

        site_price_raw = parsed.get("price")
        current_price = extract_number(site_price_raw)

        site_currency_str = str(parsed.get("currency") or item.get("currency") or "AZN")
        site_currency = detect_currency(site_currency_str, "AZN")
        if site_currency == "AZN" and detect_currency(str(site_price_raw), None):
            site_currency = detect_currency(str(site_price_raw))

        if current_price == 0.0 or target_price_native == 0.0:
            print(f"DEBUG: Ошибка - нулевая цена. URL: {url}")
            continue

        # Həm cari, həm də hədəf qiyməti EYNİ valyuta ilə (məhsulun öz valyutası)
        # AZN-ə çeviririk ki, müqayisə həmişə düzgün olsun.
        current_price_azn = to_azn(current_price, site_currency)
        target_price_azn = to_azn(target_price_native, site_currency)

        title = parsed.get("title") or item.get("name") or "Məhsul"

        # --- Real-time yeniləmə: node-a (n8n) göndərməzdən ƏVVƏL products.json-u
        # da təzə qiymətlə yeniləyirik ki, Streamlit tərəfi ilə sinxron qalsın və
        # qiymət tarixçəsi (previous_price) düzgün toplansın. ---
        old_price = extract_number(item.get("current_price"))
        if parsed.get("success") and current_price != old_price:
            item["previous_price"] = item.get("current_price")
            updated_count += 1
        item["current_price"] = current_price
        item["currency"] = site_currency
        item["name"] = title
        if parsed.get("image_url"):
            item["image_url"] = parsed["image_url"]
        item["price_azn"] = round(current_price_azn, 2) if site_currency != "AZN" else None
        item["target_price_azn"] = round(target_price_azn, 2) if site_currency != "AZN" else None

        # 1. ОБРЕЗАЕМ НАЗВАНИЕ: Оставляем максимум 80 символов, чтобы не спамить и не превышать лимит
        short_title = title if len(title) < 80 else title[:77] + "..."

        print(
            f"DEBUG: [{short_title}] | Текущая: {current_price} {site_currency} (={current_price_azn:.2f} AZN) "
            f"| Цель: {target_price_native} {site_currency} (={target_price_azn:.2f} AZN)"
        )

        if current_price_azn <= target_price_azn:
            print(f"✅ УСПЕХ: Найдена скидка! {current_price_azn:.2f} <= {target_price_azn:.2f}")

            # Groq-a sorğu — daxildə öz retry məntiqi var (rate-limit üçün)
            ai_hook = get_ai_hook(short_title, current_price, site_currency)

            # Целевую цену тоже показываем в родной валюте (+ манаты в скобках,
            # если валюта не AZN) — так же, как и текущую цену.
            target_price_line = f"{target_price_native} {site_currency}"
            if site_currency != "AZN":
                target_price_line += f" (~{target_price_azn:.2f} AZN)"

            # ЖЕСТКО СОБИРАЕМ СООБЩЕНИЕ (Цены гарантированно будут всегда!)
            ai_message = (
                f"🔥 **СКИДКА НАЙДЕНА!**\n\n"
                f"🏷 **Текущая цена:** {current_price} {site_currency} "
                f"{f'(~{current_price_azn:.2f} AZN)' if site_currency != 'AZN' else ''}\n"
                f"🎯 **Желаемая цена:** {target_price_line}\n\n"
                f"{ai_hook}\n\n"
                f"🔗 [Перейти к товару]({safe_markdown_url(url)})"
            )

            # Защита от лимита Telegram (максимум 1024 символа для фото с подписью)
            if len(ai_message) > 1000:
                ai_message = ai_message[:997] + "..."

            alerts.append({
                "name": title,
                "url": url,
                "current_price": current_price,
                "currency": site_currency,
                "converted_price_azn": round(current_price_azn, 2),
                "target_price": target_price_native,
                "target_price_azn": round(target_price_azn, 2),
                "discount_found": True,
                "telegram_message": ai_message,
                "image_url": parsed.get("image_url", ""),
            })

            # Növbəti Groq sorğusundan əvvəl kiçik fasilə — bir neçə endirim
            # tapılanda sorğuları arka-arkaya atmamaq üçün (rate-limit qorunması).
            time.sleep(1)
        else:
            print(f"❌ ПРОПУСК: Текущая цена ({current_price_azn:.2f} AZN) выше цели ({target_price_azn:.2f} AZN)")

    # Bütün məhsullar üçün qiymətlər real vaxtda yoxlanılıb yeniləndi —
    # indi bunu products.json-a yazırıq ki, node-a göndərilməzdən əvvəl
    # məlumat bazası da təzələnmiş olsun (Streamlit tərəfi ilə sinxron).
    save_tracked_products(products)

    return {
        "status": "success",
        "total_checked": len(products),
        "updated_count": updated_count,
        "discounts_count": len(alerts),
        "alerts": alerts,
    }