import json
import os
import re
import urllib.parse
from urllib.parse import urlparse
from dotenv import load_dotenv
from fastapi import FastAPI
from groq import Groq

from product_parser import parse_product

load_dotenv()

app = FastAPI()

groq_api_key = (os.getenv("GROQ_API_KEY") or "").strip().strip('"').strip("'")
groq_client = Groq(api_key=groq_api_key)

# Курсы валют для приведения цен сайта к МАНАТАМ
TRY_TO_AZN = 0.05
USD_TO_AZN = 1.70
EUR_TO_AZN = 1.85
RUB_TO_AZN = 0.018


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


@app.get("/check-prices")
def check_prices():
    products = load_tracked_products()
    alerts = []

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
        target_raw = item.get("target_price") or item.get("target") or item.get("targetPrice")
        target_price_azn = extract_number(target_raw)

        site_price_raw = parsed.get("price")
        current_price = extract_number(site_price_raw)

        site_currency_str = str(parsed.get("currency") or item.get("currency") or "AZN")
        site_currency = detect_currency(site_currency_str, "AZN")
        if site_currency == "AZN" and detect_currency(str(site_price_raw), None):
            site_currency = detect_currency(str(site_price_raw))

        if current_price == 0.0 or target_price_azn == 0.0:
            print(f"DEBUG: Ошибка - нулевая цена. URL: {url}")
            continue

        current_price_azn = current_price
        if site_currency == "TRY":
            current_price_azn = current_price * TRY_TO_AZN
        elif site_currency == "USD":
            current_price_azn = current_price * USD_TO_AZN
        elif site_currency == "EUR":
            current_price_azn = current_price * EUR_TO_AZN
        elif site_currency == "RUB":
            current_price_azn = current_price * RUB_TO_AZN

        title = parsed.get("title") or item.get("name") or "Məhsul"

        # 1. ОБРЕЗАЕМ НАЗВАНИЕ: Оставляем максимум 80 символов, чтобы не спамить и не превышать лимит
        short_title = title if len(title) < 80 else title[:77] + "..."

        print(
            f"DEBUG: [{short_title}] | Текущая: {current_price} {site_currency} (={current_price_azn:.2f} AZN) | Ожидаемая цель: {target_price_azn:.2f} AZN")

        if current_price_azn <= target_price_azn:
            print(f"✅ УСПЕХ: Найдена скидка! {current_price_azn:.2f} <= {target_price_azn:.2f}")

            # Просим ИИ написать только короткую эмоцию и призыв
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
                ai_hook = escape_md(ai_hook)
            except Exception as exc:
                print(f"DEBUG GROQ ERROR: {exc}")
                ai_hook = "🔥 Не упусти шанс купить по суперцене!"

            # ЖЕСТКО СОБИРАЕМ СООБЩЕНИЕ (Цены гарантированно будут всегда!)
            ai_message = (
                f"🔥 **СКИДКА НАЙДЕНА!**\n\n"
                f"🏷 **Текущая цена:** {current_price} {site_currency} "
                f"{f'(~{current_price_azn:.2f} AZN)' if site_currency != 'AZN' else ''}\n"
                f"🎯 **Желаемая цена:** {target_price_azn:.2f} AZN\n\n"
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
                "target_price_azn": target_price_azn,
                "discount_found": True,
                "telegram_message": ai_message,
                "image_url": parsed.get("image_url", ""),
            })
        else:
            print(f"❌ ПРОПУСК: Текущая цена ({current_price_azn:.2f} AZN) выше цели ({target_price_azn:.2f} AZN)")

    return {
        "status": "success",
        "total_checked": len(products),
        "discounts_count": len(alerts),
        "alerts": alerts,
    }