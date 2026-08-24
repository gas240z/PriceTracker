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
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
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

TEMU_PRICE_KEY_CANDIDATES = [
    "priceString", "formattedPrice", "displayPrice", "priceText", "minPriceText",
    "maxPriceText", "amountStr", "minAmount", "minGroupPrice", "actualPrice",
    "salePrice", "normalPrice", "promoPrice", "activityAmount", "spikePrice",
    "price", "goodsPrice", "retailPrice", "marketPrice", "discountPrice",
    "priceVal", "amount", "finalPrice", "currentPrice", "skuPrice", "goodsAmount"
]
TEMU_TITLE_KEY_CANDIDATES = ["goodsName", "productName", "title", "itemName", "subject"]


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


def _extract_trendyol_image(clean_html: str, soup: BeautifulSoup) -> str:
    for meta_key in ("og:image", "twitter:image"):
        val = _content(soup, property=meta_key) or _content(soup, name=meta_key)
        if _is_valid_image(val) and "dsmcdn" in val:
            return val

    ty_pattern = r'https?://(?:cdn\.)?dsmcdn\.com/[^\s"\'\\]*?/ty\d+/[^\s"\'\\]*?\.(?:jpg|jpeg|webp|png)'
    matches = re.findall(ty_pattern, clean_html, re.I)
    for m in matches:
        if _is_valid_image(m):
            return m

    rel_pattern = r'/ty\d+/[^\s"\'\\]+?\.(?:jpg|jpeg|webp|png)'
    rel_matches = re.findall(rel_pattern, clean_html, re.I)
    for m in rel_matches:
        full_url = "https://cdn.dsmcdn.com" + m
        if _is_valid_image(full_url):
            return full_url

    gen_pattern = r'https?://(?:cdn\.)?dsmcdn\.com/[^\s"\'\\]+?\.(?:jpg|jpeg|webp|png)'
    for m in re.findall(gen_pattern, clean_html, re.I):
        if _is_valid_image(m):
            return m

    return ""


def _fallback_regex_image(clean_html: str, market: str) -> str:
    if market == "Temu":
        matches = re.findall(r'https://img\.kwcdn\.com/[^\s"\'\\]+\.(?:jpg|jpeg|webp|png)', clean_html, re.I)
        for m in matches:
            if _is_valid_image(m):
                return m
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
        if 1.0 <= val <= 5.0 and not any(sym in str(raw) for sym in ["₼", "₺", "$", "€", "£", "AZN", "TRY", "USD", "EUR"]):
            return None
        return val
    except ValueError:
        return None


def _currency(raw: str, fallback: str = "") -> str:
    upper = raw.upper()
    for code in ("AZN", "TRY", "TL", "USD", "EUR", "GBP"):
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
                "title": _first_value(product.get("name")),
                "price": raw_price,
                "currency": _first_value(offers.get("priceCurrency")),
                "image_url": _first_value(product.get("image")),
            }
    return {}


def _looks_like_bot_wall(html: str) -> bool:
    sample = html[:5000].lower()
    return any(marker in sample for marker in BOT_WALL_MARKERS)


def _parse_temu_data(soup: BeautifulSoup, clean_html: str, url: str) -> tuple[str, str, str]:
    goods_id_match = re.search(r'g-(\d+)\.html', url)
    target_goods_id = goods_id_match.group(1) if goods_id_match else ""

    found_title = ""
    found_price = ""
    found_image = ""

    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if not text or len(text) < 20:
            continue
        chunks = re.findall(r'(?:window\.)?[\w\d_\.$]+\s*=\s*(\{.+?\});?\s*(?:$|\n|<)', text)
        for chunk in chunks:
            try:
                data = json.loads(chunk)
                for item in _walk_json(data):
                    if isinstance(item, dict):
                        item_id = str(item.get("goodsId") or item.get("goods_id") or item.get("id") or "")
                        is_target_match = target_goods_id and item_id == target_goods_id

                        if is_target_match or ("goodsName" in item and ("minAmount" in item or "price" in item or "salePrice" in item)):
                            if not found_title:
                                for tk in TEMU_TITLE_KEY_CANDIDATES:
                                    val = item.get(tk)
                                    if isinstance(val, str) and len(val) > 4 and not any(b in val.lower() for b in ["temu", "lightning", "security", "verify", "adjust", "главная"]):
                                        found_title = val
                                        break
                            if not found_price:
                                for pk in TEMU_PRICE_KEY_CANDIDATES:
                                    val = item.get(pk)
                                    if val is not None:
                                        p_str = str(val).strip()
                                        if p_str and re.search(r'\d', p_str):
                                            found_price = p_str
                                            break
                            if not found_image:
                                for ik in ["hdThumbUrl", "imageUrl", "goodsImageUrl", "thumbUrl", "image"]:
                                    val = item.get(ik)
                                    if _is_valid_image(val):
                                        found_image = val
                                        break
                            if is_target_match and found_title and found_price:
                                return found_title, found_price, found_image
            except (json.JSONDecodeError, TypeError):
                continue

    return found_title, found_price, found_image


def parse_product(url: str) -> dict:
    market = market_from_url(url)
    if not market:
        return {
            "success": False,
            "error": "Dəstəklənməyən link. Birmarket, Temu və ya Trendyol linki daxil edin.",
            "url": url,
        }

    try:
        current_headers = REQUEST_HEADERS.copy()
        if market == "Temu":
            current_headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            })

        response = requests.get(url, headers=current_headers, timeout=15)
        response.raise_for_status()
        raw_html = response.text

        if market == "Temu" and _looks_like_bot_wall(raw_html):
            return {
                "success": False,
                "error": "Temu заблокировал запрос (антибот-защита). Попробуйте позже или другой прокси/IP.",
                "url": url,
            }

        clean_html = raw_html.replace("\\/", "/").replace("\\u002F", "/")
        soup = BeautifulSoup(raw_html, "html.parser")

        structured = _parse_structured_product(soup)

        temu_title, temu_price, temu_image = "", "", ""
        if market == "Temu":
            temu_title, temu_price, temu_image = _parse_temu_data(soup, clean_html, url)

        # === 1. TITLE ===
        title = structured.get("title") or _content(soup, property="og:title")
        bad_titles = ["молниеносные скидки", "lightning deals", "temu", "trendyol", "security measure", "just a moment", "adjust", "главная"]
        if title and any(bad in title.lower() for bad in bad_titles):
            title = ""

        if not title:
            h1 = soup.find("h1")
            if h1:
                t_text = h1.get_text(" ", strip=True)
                if t_text.lower() not in bad_titles:
                    title = t_text

        if not title and market == "Temu":
            title = temu_title
            if not title:
                for key in TEMU_TITLE_KEY_CANDIDATES:
                    alt_match = re.search(rf'"{key}"\s*:\s*"([^"\\]{{5,120}})"', clean_html)
                    if alt_match:
                        val = alt_match.group(1)
                        if val.lower() not in bad_titles:
                            title = val
                            break
            # Фоллбек из URL slug
            if not title:
                parsed_path = urlparse(url).path
                match_slug = re.search(r'/az-[a-z]{2}/([^/]+?)-g-\d+\.html', parsed_path)
                if match_slug:
                    slug = match_slug.group(1)
                    decoded_slug = unquote(slug).replace("-", " ")
                    if len(decoded_slug) > 5:
                        title = decoded_slug.capitalize()

        # === 2. PRICE ===
        price_raw = structured.get("price") or _content(soup, itemprop="price")
        currency = structured.get("currency") or _content(soup, itemprop="priceCurrency")

        if not price_raw:
            price_raw = _content(soup, property="product:price:amount") or _content(soup, property="og:price:amount")
            currency = currency or _content(soup, property="product:price:currency") or _content(soup, property="og:price:currency")

        if not price_raw and market == "Temu":
            price_raw = temu_price
            # Прямой глобальный поиск по ключам в сыром HTML
            if not price_raw:
                for key in TEMU_PRICE_KEY_CANDIDATES:
                    m = re.search(rf'"{key}"\s*:\s*(?:"([^"]+)"|([\d.]+))', clean_html)
                    if m:
                        price_raw = m.group(1) or m.group(2)
                        break

        # Универсальный поиск цены по тексту всей страницы
        if not price_raw:
            text_content = soup.get_text(" ", strip=True)
            price_matches = re.findall(r'(?:₼|\$|€|£|AZN|TRY|USD|EUR)\s*(\d+[\.,]\d{2})', text_content, re.I)
            if not price_matches:
                price_matches = re.findall(r'(\d+[\.,]\d{2})\s*(?:₼|\$|€|£|AZN|TRY|USD|EUR)', text_content, re.I)
            if price_matches:
                price_raw = price_matches[0]

        if not price_raw:
            price_node = soup.select_one('[data-testid*="price" i], [class*="price" i], [id*="price" i]')
            if price_node:
                price_raw = price_node.get_text(" ", strip=True)

        price = _extract_number(price_raw)
        if price is None:
            return {"success": False, "error": "Səhifədə məhsulun qiyməti tapılmadı.", "url": url}

        # === 3. IMAGE ===
        image_url = ""
        if market == "Trendyol":
            image_url = _extract_trendyol_image(clean_html, soup)
        else:
            image_url = structured.get("image_url", "") or temu_image
            if not _is_valid_image(image_url):
                image_url = _content(soup, property="og:image")
            if not _is_valid_image(image_url):
                image_url = _fallback_regex_image(clean_html, market)

        if not _is_valid_image(image_url):
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
                if _is_valid_image(src):
                    image_url = src
                    break

        if image_url and not image_url.startswith("http"):
            image_url = urljoin(response.url, image_url)

        currency = _currency(f"{currency} {price_raw}", "AZN" if market == "Birmarket" else ("TRY" if market == "Trendyol" else ""))

        return {
            "success": True,
            "title": title or f"{market} məhsulu",
            "price": price,
            "currency": currency or "VALYUTA",
            "image_url": image_url,
            "url": url,
            "market": market,
        }
    except requests.RequestException as exc:
        return {"success": False, "error": f"Sayt sorğusunu yerinə yetirmək olmadı: {exc}", "url": url}
    except Exception as exc:
        return {"success": False, "error": str(exc), "url": url}