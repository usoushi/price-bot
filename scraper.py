import re
import json
import logging
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PRICE_RE = re.compile(r"[\d,]+")

_client = httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True, http2=True)


def _to_int(price_str: str) -> int | None:
    cleaned = PRICE_RE.search(price_str.replace(",", "").replace("，", ""))
    if cleaned:
        try:
            return int(cleaned.group().replace(",", ""))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Generic parsers
# ---------------------------------------------------------------------------

def _parse_jsonld(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            data = data[0]
        dtype = data.get("@type", "")
        if dtype in ("Product", "ItemPage") or "Product" in str(dtype):
            name = data.get("name")
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0]
            price_raw = offers.get("price") or offers.get("lowPrice")
            price = _to_int(str(price_raw)) if price_raw is not None else None
            return name, price
    return None, None


def _parse_meta(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    name = None
    price = None

    og_title = soup.find("meta", property="og:title")
    if og_title:
        name = og_title.get("content")

    for attr, value in [
        ("property", "product:price:amount"),
        ("name", "price"),
        ("itemprop", "price"),
    ]:
        tag = soup.find("meta", {attr: value})
        if tag:
            price = _to_int(tag.get("content", ""))
            if price:
                break

    return name, price


def _parse_common_selectors(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    price = None
    for selector in [
        "[itemprop='price']",
        ".price",
        "#price",
        ".product-price",
        ".item-price",
        ".priceValue",
        ".price_value",
    ]:
        tag = soup.select_one(selector)
        if tag:
            price = _to_int(tag.get_text())
            if price:
                break

    name = None
    for selector in ["h1", "[itemprop='name']", ".product-name", ".item-name"]:
        tag = soup.select_one(selector)
        if tag:
            name = tag.get_text(strip=True)
            if name:
                break

    return name, price


# ---------------------------------------------------------------------------
# Site-specific parsers
# ---------------------------------------------------------------------------

def _scrape_uniqlo(url: str) -> tuple[str | None, int | None]:
    """UNIQLOの価格APIとHTMLから商品名・価格を取得。"""
    # 商品ID抽出: /products/E484875-000/ -> E484875-000
    match = re.search(r"/products/(E\d+-\d+)", url)
    if not match:
        logger.warning("UNIQLO: product ID not found in URL: %s", url)
        return None, None

    product_id = match.group(1)
    logger.info("UNIQLO: product_id=%s", product_id)

    # 1. 価格API: /prices エンドポイントから最初のSKUの価格を取得
    price = None
    price_url = (
        f"https://www.uniqlo.com/jp/api/commerce/v5/ja/products"
        f"/{product_id}/prices?httpFailure=true"
    )
    try:
        r = httpx.get(price_url, headers=HEADERS, timeout=15, follow_redirects=True)
        logger.info("UNIQLO price API status: %d", r.status_code)
        if r.status_code == 200:
            data = r.json()
            result = data.get("result", {})
            # resultはSKU IDをキーとした辞書 {"09100230": {"base": {"value": 3990}, ...}}
            if result:
                first_sku = next(iter(result.values()))
                price = first_sku.get("base", {}).get("value")
                if price is not None:
                    price = int(price)
    except Exception as e:
        logger.warning("UNIQLO price API error: %s", e)

    # 2. 商品名をHTMLのog:title -> titleタグから取得
    name = None
    try:
        r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        logger.info("UNIQLO HTML status: %d", r.status_code)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            og = soup.find("meta", property="og:title")
            if og and og.get("content"):
                name = og["content"]
            else:
                title = soup.find("title")
                name = title.get_text(strip=True) if title else None
    except Exception as e:
        logger.warning("UNIQLO HTML error: %s", e)

    logger.info("UNIQLO result: name=%s price=%s", name, price)
    return name or None, price or None


def _scrape_amazon(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    name_tag = soup.select_one("#productTitle")
    name = name_tag.get_text(strip=True) if name_tag else None

    price = None
    for selector in [
        ".a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".a-price-whole",
    ]:
        tag = soup.select_one(selector)
        if tag:
            price = _to_int(tag.get_text())
            if price:
                break
    return name, price


def _scrape_rakuten(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    name_tag = soup.select_one(".item_name, h1.item_name")
    name = name_tag.get_text(strip=True) if name_tag else None
    price_tag = soup.select_one(".price2, .price")
    price = _to_int(price_tag.get_text()) if price_tag else None
    return name, price


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _fetch_soup(url: str) -> BeautifulSoup | None:
    try:
        resp = _client.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("fetch error %s: %s", url, e)
        return None


def get_product_info(url: str) -> tuple[str | None, int | None]:
    """(商品名, 価格) を返す。取得できない場合は (None, None)。"""
    hostname = urlparse(url).hostname or ""

    # --- サイト専用パーサー ---
    if "uniqlo.com" in hostname:
        name, price = _scrape_uniqlo(url)
        if name and price:
            return name, price

    soup = _fetch_soup(url)
    if soup is None:
        return None, None

    if "amazon.co.jp" in hostname or "amazon.com" in hostname:
        name, price = _scrape_amazon(soup)
        if name and price:
            return name, price

    if "rakuten.co.jp" in hostname:
        name, price = _scrape_rakuten(soup)
        if name and price:
            return name, price

    # --- 汎用フォールバック ---
    name, price = _parse_jsonld(soup)
    if not (name and price):
        meta_name, meta_price = _parse_meta(soup)
        name = name or meta_name
        price = price or meta_price
    if not (name and price):
        sel_name, sel_price = _parse_common_selectors(soup)
        name = name or sel_name
        price = price or sel_price

    return name or None, price or None
