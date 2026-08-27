"""Product-page parsers for the marketplaces supported by PriceWatch."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,az;q=0.8,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "max-age=0",
}

MARKETS = {
    "birmarket.az": "Birmarket",
    "temu.com": "Temu",
    "trendyol.com": "Trendyol",
}

CURRENCY_SYMBOLS = {"₼": "AZN", "₺": "TRY", "$": "USD", "€": "EUR", "£": "GBP"}

BOT_WALL_MARKERS = [
    "verify you are human", "are you a robot", "captcha", "unusual traffic",
    "access denied", "just a moment", "security measure", "checking your browser",
    "px-captcha", "perimeterx", "_px3", "temu.com/verify",
]

TEMU_ORANGE_PRICE_KEYS = [
    "activityAmount", "activity_amount",
    "activityPrice", "activity_price",
    "spikePrice", "spike_price",
    "actPrice", "act_price",
    "bottomPrice", "bottom_price",
    "directPrice", "direct_price",
    "flashSalePrice", "flash_sale_price",
    "todayPrice", "today_price",
    "eventPrice", "event_price",
    "flashPrice", "flash_price",
    "payAmount", "pay_amount",
    "promoPrice", "promo_price",
    "discountPrice", "discount_price"
]

TEMU_STANDARD_PRICE_KEYS = [
    "salePrice", "sale_price",
    "minAmount", "min_amount",
    "actualPrice", "actual_price",
    "finalPrice", "final_price",
    "currentPrice", "current_price",
    "priceString", "formattedPrice", "displayPrice", "priceText",
    "minPriceText", "goodsPrice", "goods_price", "amountStr", "amount", "price"
]

TEMU_TITLE_KEY_CANDIDATES = ["goodsName", "productName", "title", "itemName", "subject", "goods_name"]

# Ehtiyat (fallback) TRY -> AZN məzənnəsi. Yalnız canlı konvertasiya (Frankfurter API)
# əlçatan olmadıqda istifadə olunur. Vaxtaşırı yenilənməlidir.
TRY_TO_AZN_FALLBACK_RATE = 0.039


def market_from_url(url: str) -> str | None:
    url = (url or "").strip()
    if url and not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for domain, market in MARKETS.items():
        if host == domain or host.endswith("." + domain):
            return market
    return None


def _content(soup: BeautifulSoup, **attrs: str) -> str:
    tag = soup.find("meta", attrs=attrs)
    return tag.get("content", "").strip() if tag else ""


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _json_ld_products(soup: BeautifulSoup) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_json(payload):
            item_type = item.get("@type", "")
            if item_type == "Product" or (isinstance(item_type, list) and "Product" in item_type):
                products.append(item)
    return products


def _first_value(value: Any) -> str:
    if isinstance(value, list):
        return _first_value(value[0]) if value else ""
    return str(value).strip() if value is not None else ""


def _is_valid_image(url: Any) -> bool:
    if not url or not isinstance(url, str):
        return False
    if len(url) < 15 or url.startswith("data:"):
        return False
    lower = url.lower()
    if lower.endswith((".svg", ".gif")):
        return False
    bad_words = ["flag", "logo", "icon", "placeholder", "sprite", "avatar", "banner", "empty", "seller", "stamp", "badge"]
    return not any(w in lower for w in bad_words)


def _clean_title(title: str) -> str:
    """Удаляет мусорные приписки вроде ' - Temu' из заголовка."""
    if not title:
        return ""
    t = title.strip()
    t = re.sub(r'\s*[-|]?\s*Temu$', '', t, flags=re.I)
    return t.strip()


def _extract_trendyol_image(clean_html: str, soup: BeautifulSoup) -> str:
    for meta_key in ("og:image", "twitter:image"):
        val = _content(soup, property=meta_key) or _content(soup, name=meta_key)
        if _is_valid_image(val) and "dsmcdn" in val:
            return val
    ty_pattern = r'https?://(?:cdn\.)?dsmcdn\.com/[^\s"\'\\]*?/ty\d+/[^\s"\'\\]*?\.(?:jpg|jpeg|webp|png)'
    matches = re.findall(ty_pattern, clean_html, re.I)
    for m in matches:
        if _is_valid_image(m): return m
    return ""


def _extract_trendyol_try_price(decoded_html: str) -> str:
    """Trendyol.az səhifədə istifadəçiyə qiyməti ₼-ə (AZN) çevrilmiş göstərir,
    lakin səhifənin daxili JSON/JS state-ində (analitika dataLayer-i, məhsul
    state obyekti və s.) əsl TL (TRY) qiyməti də saxlanılır. Bu funksiya həmin
    əsl TRY dəyərini tapmağa çalışır ki, biz heç vaxt ₼ ilə göstərilən
    (artıq konvertasiya olunmuş) rəqəmi TRY kimi qəbul etməyək."""
    candidate_patterns = [
        # Analitika/dataLayer tipli obyektlər: "currency":"TRY", ... "value":1234.56
        r'"currency"\s*:\s*"TRY"[^{}]{0,120}?"(?:value|price)"\s*:\s*"?(\d+(?:\.\d+)?)"?',
        r'"(?:value|price)"\s*:\s*"?(\d+(?:\.\d+)?)"?[^{}]{0,120}?"currency"\s*:\s*"TRY"',
        # Formatlanmış mətn dəyərləri: "text":"1.660,00 TL" və ya "1660.00 TL"
        r'"text"\s*:\s*"([\d.,]+)\s*TL"',
        r'"(?:sellingPrice|originalPrice|discountedPrice|price)Text"\s*:\s*"([\d.,]+)\s*TL"',
        # Sərbəst mətndə "... TL" yanında olan rəqəm
        r'([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))\s*TL\b',
    ]
    for pattern in candidate_patterns:
        matches = re.findall(pattern, decoded_html, re.I)
        for raw in matches:
            val = _extract_number(raw)
            if val and 0.5 <= val < 5_000_000:
                return raw
    return ""


def _convert_try_to_azn(amount: float) -> float | None:
    """TRY -> AZN konvertasiyası. Əvvəlcə canlı məzənnə (Frankfurter API) ilə,
    o əlçatan olmadıqda təxmini sabit kursla hesablanır."""
    if amount is None or amount <= 0:
        return None
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest",
            params={"amount": amount, "from": "TRY", "to": "AZN"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        val = (data.get("rates") or {}).get("AZN")
        if val:
            return round(float(val), 2)
    except Exception:
        pass
    return round(amount * TRY_TO_AZN_FALLBACK_RATE, 2)


def _convert_azn_to_try(amount: float) -> float | None:
    """AZN -> TRY konvertasiyası (əks istiqamət). Trendyol.az səhifəsində yalnız
    manatla göstərilən qiymət tapıldıqda, ondan təxmini TL dəyəri hesablamaq üçün
    istifadə olunur (son çarə fallback)."""
    if amount is None or amount <= 0:
        return None
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest",
            params={"amount": amount, "from": "AZN", "to": "TRY"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        val = (data.get("rates") or {}).get("TRY")
        if val:
            return round(float(val), 2)
    except Exception:
        pass
    if TRY_TO_AZN_FALLBACK_RATE:
        return round(amount / TRY_TO_AZN_FALLBACK_RATE, 2)
    return None


def _fallback_regex_image(clean_html: str, market: str) -> str:
    if market == "Temu":
        matches = re.findall(r'https://img\.kwcdn\.com/[^\s"\'\\]+\.(?:jpg|jpeg|webp|png)', clean_html, re.I)
        for m in matches:
            if _is_valid_image(m): return m
    return ""


def _extract_number(raw: str) -> float | None:
    raw = str(raw).replace("\xa0", " ")
    match = re.search(r"\d[\d\s.,]*", raw)
    if not match:
        return None
    number = re.sub(r"\s+", "", match.group(0))
    if "," in number and "." in number:
        decimal = "," if number.rfind(",") > number.rfind(".") else "."
        number = number.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in number:
        number = number.replace(".", "").replace(",", ".")
    elif number.count(".") > 1:
        pieces = number.split(".")
        number = "".join(pieces[:-1]) + "." + pieces[-1]
    try:
        val = float(number)
        return val
    except ValueError:
        return None


def _currency(raw: str, fallback: str = "") -> str:
    upper = raw.upper()
    for code in ("AZN", "TRY", "TL", "USD", "EUR", "GBP", "RUB"):
        if re.search(rf"\b{code}\b", upper):
            return "TRY" if code == "TL" else code
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in raw:
            return code
    return fallback


def _parse_structured_product(soup: BeautifulSoup) -> dict[str, str]:
    for product in _json_ld_products(soup):
        offers = product.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            offers = {}
        raw_price = _first_value(offers.get("price") or offers.get("lowPrice"))
        if raw_price:
            return {
                "title": _clean_title(_first_value(product.get("name"))),
                "price": raw_price,
                "currency": _first_value(offers.get("priceCurrency")),
                "image_url": _first_value(product.get("image")),
            }
    return {}


def _looks_like_bot_wall(html: str) -> bool:
    sample = html[:5000].lower()
    return any(marker in sample for marker in BOT_WALL_MARKERS)


def _clean_and_decode_html(raw_html: str) -> str:
    cleaned = raw_html.replace("\\/", "/").replace("\\u002F", "/").replace('\\"', '"').replace("\\u0022", '"')
    try:
        cleaned = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), cleaned)
    except Exception:
        pass
    return cleaned


def _parse_temu_price_val(val: Any) -> float | None:
    if val is None:
        return None
    p_str = str(val).strip()
    if not p_str or p_str in ("0", "0.0", "0.00"):
        return None

    # В Temu любые целые числа в JSON — это копейки/центы (262 = 2.62 ₼)
    if p_str.isdigit():
        num = int(p_str)
        return (num / 100.0) if num > 0 else None

    num = _extract_number(p_str)
    if num is not None and num > 0:
        return num
    return None


def _parse_temu_data(soup: BeautifulSoup, decoded_html: str, url: str) -> tuple[str, str, str, str]:
    found_title = ""
    found_price = ""
    found_currency = "AZN"
    found_image = ""

    # === 1. TITLE ===
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if len(text) < 20: continue
        tm = re.search(r'"(?:goodsName|productName|title|itemName|subject|goods_name)"\s*:\s*"([^"\\]{5,200})"', text)
        if tm:
            val = tm.group(1).strip()
            if not any(b in val.lower() for b in ["temu", "lightning", "security", "verify", "adjust"]):
                found_title = val
                break

    if not found_title:
        og_t = _content(soup, property="og:title") or _content(soup, name="title")
        if og_t and not any(b in og_t.lower() for b in ["temu", "lightning", "security", "verify", "adjust"]):
            found_title = og_t

    if not found_title:
        parsed_path = urlparse(url).path
        match_slug = re.search(r'/(?:az-[a-z]{2}/)?([^/]+?)-g-\d+\.html', parsed_path)
        if match_slug:
            slug = match_slug.group(1)
            decoded_slug = unquote(slug).replace("-", " ")
            if len(decoded_slug) > 3:
                found_title = decoded_slug.capitalize()

    found_title = _clean_title(found_title)

    # === 2. IMAGE ===
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        im = re.search(r'"(?:hdThumbUrl|imageUrl|goodsImageUrl|thumbUrl|image|share_image_url)"\s*:\s*"(https?://[^\s"\\]+)"', text)
        if im:
            val = im.group(1).replace("\\/", "/")
            if _is_valid_image(val):
                found_image = val
                break

    if not found_image:
        matches = re.findall(r'https://img\.kwcdn\.com/[^\s"\'\\]+\.(?:jpg|jpeg|webp|png)', decoded_html, re.I)
        for m in matches:
            if _is_valid_image(m):
                found_image = m
                break

    # === 3. MULTI-LAYER PRICE SEARCH ===
    orange_prices: list[float] = []
    standard_prices: list[float] = []
    text_prices: list[float] = []

    # Уровень 1: Поиск в видимом чистом тексте (Без HTML тегов)
    clean_text = soup.get_text(" ", strip=True)
    text_orange_matches = re.findall(r'(?:Только сегодня|Lightning deal|Flash deal|около|около\s*(?:₼|\$|€|AZN|USD|TRY)?)\s*(\d+[\.,]\d{2})', clean_text, re.I)
    for tom in text_orange_matches:
        p = _extract_number(tom)
        if p and 0.1 <= p < 10000: orange_prices.append(p)

    text_orange_matches_html = re.findall(r'(?:Только сегодня|Lightning deal|Flash deal|около)\s*[^0-9]{0,20}(\d+[\.,]\d{2})', decoded_html, re.I)
    for tom in text_orange_matches_html:
        p = _extract_number(tom)
        if p and 0.1 <= p < 10000: orange_prices.append(p)

    # Уровень 2: Оранжевые ключи в JSON
    for key in TEMU_ORANGE_PRICE_KEYS:
        matches = re.findall(rf'"{key}"\s*:\s*(?:{{[^}}]*"amount"\s*:\s*)?"?(\d+(?:\.\d+)?)"?', decoded_html, re.I)
        for raw_v in matches:
            p = _parse_temu_price_val(raw_v)
            if p and 0.1 <= p < 10000: orange_prices.append(p)

    # Уровень 3: Стандартные ключи цен в JSON
    for key in TEMU_STANDARD_PRICE_KEYS:
        matches = re.findall(rf'"{key}"\s*:\s*(?:{{[^}}]*"amount"\s*:\s*)?"?(\d+(?:\.\d+)?)"?', decoded_html, re.I)
        for raw_v in matches:
            p = _parse_temu_price_val(raw_v)
            if p and 0.1 <= p < 10000: standard_prices.append(p)

    # Уровень 4: Любая сумма около символов валют
    body_matches = re.findall(r'(?:₼|AZN|\$|€|£|TRY)\s*(\d+[\.,]\d{2})|(\d+[\.,]\d{2})\s*(?:₼|AZN|\$|€|£|TRY)', clean_text, re.I)
    for m in body_matches:
        val_str = m[0] or m[1]
        p = _extract_number(val_str)
        if p and 0.1 <= p < 10000: text_prices.append(p)

    if orange_prices:
        found_price = f"{min(orange_prices):.2f}"
    elif standard_prices:
        found_price = f"{min(standard_prices):.2f}"
    elif text_prices:
        found_price = f"{min(text_prices):.2f}"

    return found_title, found_price, found_image, found_currency


def parse_product(url: str) -> dict:
    market = market_from_url(url)
    if not market:
        return {
            "success": False,
            "error": "Dəstəklənməyən link. Birmarket, Temu və ya Trendyol linki daxil edin.",
            "url": url,
        }

    try:
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)

        if market == "Temu":
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,az;q=0.8,en-US;q=0.7,en;q=0.6",
                "Referer": "https://www.temu.com/",
                "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Upgrade-Insecure-Requests": "1",
            })

        response = session.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        raw_html = response.text

        if market == "Temu" and _looks_like_bot_wall(raw_html):
            return {
                "success": False,
                "error": "Temu заблокировал запрос (антибот-защита). Попробуйте позже или другой прокси/IP.",
                "url": url,
            }

        decoded_html = _clean_and_decode_html(raw_html)
        soup = BeautifulSoup(raw_html, "html.parser")

        structured = _parse_structured_product(soup)

        temu_title, temu_price, temu_image, temu_currency = "", "", "", ""
        if market == "Temu":
            temu_title, temu_price, temu_image, temu_currency = _parse_temu_data(soup, decoded_html, response.url)

        # === 1. TITLE ===
        title = structured.get("title") or _clean_title(_content(soup, property="og:title"))
        bad_titles = ["молниеносные скидки", "lightning deals", "temu", "trendyol", "security measure", "just a moment", "adjust", "главная"]
        if title and any(bad in title.lower() for bad in bad_titles):
            title = ""

        if not title:
            h1 = soup.find("h1")
            if h1:
                t_text = _clean_title(h1.get_text(" ", strip=True))
                if t_text.lower() not in bad_titles:
                    title = t_text

        if not title and market == "Temu":
            title = temu_title

        # === 2. PRICE ===
        price_raw = temu_price if market == "Temu" else ""
        currency = structured.get("currency") or _content(soup, itemprop="priceCurrency")

        if not price_raw:
            price_raw = structured.get("price") or _content(soup, itemprop="price") or _content(soup, property="product:price:amount") or _content(soup, property="og:price:amount")

        # Trendyol.az səhifəni Azərbaycan üçün lokallaşdırıb qiyməti ₼-ə (AZN)
        # çevrilmiş göstərir. Ona görə generic "₼/AZN simvolu ilə mətn axtarışı"
        # fallback-ini Trendyol üçün İSTİFADƏ ETMİRİK — bu, TRY yerinə səhv
        # olaraq artıq konvertasiya olunmuş AZN dəyərini götürərdi.
        if not price_raw and market != "Trendyol":
            text_content = soup.get_text(" ", strip=True)
            price_matches = re.findall(r'(?:₼|\$|€|£|AZN|TRY|USD|EUR)\s*(\d+[\.,]\d{2})', text_content, re.I)
            if not price_matches:
                price_matches = re.findall(r'(\d+[\.,]\d{2})\s*(?:₼|\$|€|£|AZN|TRY|USD|EUR)', text_content, re.I)
            if price_matches:
                price_raw = price_matches[0]

        # === СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ TRENDYOL (qiymət YALNIZ TL/TRY olmalıdır) ===
        azn_visible_price: float | None = None  # sonda price_azn üçün istifadə olunacaq
        if market == "Trendyol":
            if price_raw:
                p_str = str(price_raw)
                # Пытаемся найти число перед TRY или TL
                match_try = re.search(r'([\d\s\.,]+)\s*(?:TRY|TL)', p_str, re.I)
                if match_try:
                    price_raw = match_try.group(1)
                elif re.search(r'AZN|₼', p_str, re.I):
                    # Bu mənbə əslində AZN dəyəridir, TRY kimi istifadə etmə —
                    # aşağıda əsl TL dəyərini axtaracağıq.
                    price_raw = ""
                else:
                    p_str = re.sub(r'\s*\([^)]*AZN[^)]*\)', '', p_str, flags=re.I)
                    price_raw = p_str

            if not price_raw or not _extract_number(price_raw):
                tl_price = _extract_trendyol_try_price(decoded_html)
                if tl_price:
                    price_raw = tl_price

            if not price_raw or not _extract_number(price_raw):
                # Son çarə: heç bir yerdə TL dəyəri tapılmadısa, səhifədə görünən
                # ₼ (AZN) qiymətini tapıb ondan təxmini TL hesablayırıq — bu sayədə
                # məhsul "qiymət tapılmadı" xətası ilə əlavə edilmədən qalmır.
                text_content = soup.get_text(" ", strip=True)
                azn_matches = re.findall(
                    r'(?:₼|AZN)\s*(\d+[\.,]\d{2})|(\d+[\.,]\d{2})\s*(?:₼|AZN)',
                    text_content, re.I,
                )
                for m in azn_matches:
                    val_str = m[0] or m[1]
                    candidate = _extract_number(val_str)
                    if candidate and candidate > 0:
                        azn_visible_price = candidate
                        break
                if azn_visible_price:
                    try_estimate = _convert_azn_to_try(azn_visible_price)
                    if try_estimate:
                        price_raw = f"{try_estimate:.2f}"

            currency = "TRY"

        price = _extract_number(price_raw)

        if price is None or price <= 0:
            return {"success": False, "error": "Səhifədə məhsulun qiyməti tapılmadı.", "url": url}

        price = _extract_number(price_raw)

        if price is None or price <= 0:
            return {"success": False, "error": "Səhifədə məhsulun qiyməti tapılmadı.", "url": url}

        # === 3. IMAGE ===
        image_url = ""
        if market == "Trendyol":
            image_url = _extract_trendyol_image(decoded_html, soup)
        else:
            image_url = structured.get("image_url", "") or temu_image
            if not _is_valid_image(image_url):
                image_url = _content(soup, property="og:image")
            if not _is_valid_image(image_url):
                image_url = _fallback_regex_image(decoded_html, market)

        if not _is_valid_image(image_url):
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
                if _is_valid_image(src):
                    image_url = src
                    break

        if image_url and not image_url.startswith("http"):
            image_url = urljoin(response.url, image_url)

        # === 4. CURRENCY OVERRIDE ===
        default_market_currency = "AZN" if market in ("Birmarket", "Temu") else ("TRY" if market == "Trendyol" else "")
        currency = _currency(f"{currency} {price_raw} {temu_currency}", default_market_currency)

        final_currency = currency if (currency and currency not in ("VALYUTA", "VALYUTA ")) else default_market_currency

        # Trendyol üçün mütləq TRY saxlanılır (yuxarıdakı məntiq artıq AZN-i
        # kənarlaşdırıb, amma ehtiyat üçün bir daha təsdiqləyirik).
        if market == "Trendyol":
            final_currency = "TRY"

        result = {
            "success": True,
            "title": title or f"{market} məhsulu",
            "price": price,
            "currency": final_currency,
            "image_url": image_url,
            "url": response.url,
            "market": market,
        }

        # Trendyol üçün əlavə olaraq manat (AZN) qarşılığını da hesablayıb
        # göndəririk ki, UI-də "20.76 TRY (₼0.81)" kimi mötərizədə göstərilə bilsin.
        if market == "Trendyol":
            price_azn = azn_visible_price if azn_visible_price else _convert_try_to_azn(price)
            result["price_azn"] = price_azn
            if price_azn is not None:
                result["price_display"] = f"{price:,.2f} TRY (₼{price_azn:,.2f})"
            else:
                result["price_display"] = f"{price:,.2f} TRY"

        return result
    except requests.RequestException as exc:
        # response varsa (məs. 404), status kodunu çıxarırıq ki, çağıran tərəf
        # "məhsul həqiqətən silinib" ilə "müvəqqəti şəbəkə xətası"-nı ayıra bilsin.
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        return {
            "success": False,
            "error": f"Sayt sorğusunu yerinə yetirmək olmadı: {exc}",
            "url": url,
            "status_code": status_code,
            "not_found": status_code == 404,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "url": url}


# Tətbiqin digər hissələrindən (məs. app.py-də istifadəçinin əl ilə daxil etdiyi
# "Hədəf qiymət" üçün) çağırmaq üçün ictimai (public) alias.
def convert_try_to_azn(amount: float) -> float | None:
    return _convert_try_to_azn(amount)