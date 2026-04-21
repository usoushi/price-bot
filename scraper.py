import os
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

SCRAPERAPI_KEY = os.getenv("SCRAPER_API_KEY", "")
SCRAPERAPI_ENDPOINT = "https://api.scraperapi.com"


def _fetch_via_scraperapi(url: str, render: bool = False, retries: int = 2) -> BeautifulSoup | None:
    if not SCRAPERAPI_KEY:
        logger.warning("SCRAPER_API_KEY not set, skipping %s", url)
        return None
    params = {"api_key": SCRAPERAPI_KEY, "url": url, "render": str(render).lower()}
    for attempt in range(1, retries + 1):
        try:
            r = httpx.get(SCRAPERAPI_ENDPOINT, params=params, timeout=60, follow_redirects=True)
            logger.info("ScraperAPI status: %d (render=%s, attempt=%d) %s", r.status_code, render, attempt, url)
            if r.status_code == 500 and attempt < retries:
                logger.warning("ScraperAPI 500, retrying... (%d/%d)", attempt, retries)
                continue
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            logger.warning("ScraperAPI error (attempt=%d) for %s: %s", attempt, url, e)
            if attempt == retries:
                return None
    return None


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


def _scrape_gu(url: str) -> tuple[str | None, int | None]:
    """GUの価格APIとHTMLから商品名・価格を取得。UNIQLOと同じAPI構造。"""
    match = re.search(r"/products/(E\d+-\d+)", url)
    if not match:
        logger.warning("GU: product ID not found in URL: %s", url)
        return None, None

    product_id = match.group(1)
    logger.info("GU: product_id=%s", product_id)

    price = None
    price_url = (
        f"https://www.gu-global.com/jp/api/commerce/v5/ja/products"
        f"/{product_id}/price-groups/00/prices?httpFailure=true"
    )
    try:
        r = httpx.get(price_url, headers=HEADERS, timeout=15, follow_redirects=True)
        logger.info("GU price API status: %d", r.status_code)
        if r.status_code == 200:
            result = r.json().get("result", {})
            if result:
                first_sku = next(iter(result.values()))
                price = first_sku.get("base", {}).get("value")
                if price is not None:
                    price = int(price)
    except Exception as e:
        logger.warning("GU price API error: %s", e)

    name = None
    try:
        r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        logger.info("GU HTML status: %d", r.status_code)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            og = soup.find("meta", property="og:title")
            if og and og.get("content"):
                name = og["content"]
            else:
                title = soup.find("title")
                name = title.get_text(strip=True) if title else None
    except Exception as e:
        logger.warning("GU HTML error: %s", e)

    logger.info("GU result: name=%s price=%s", name, price)
    return name or None, price or None


def _scrape_hm(url: str) -> tuple[str | None, int | None]:
    """H&M: ScraperAPI(render=False) + JSON-LD name + ¥正規表現で価格取得。"""
    soup = _fetch_via_scraperapi(url, render=False)
    if soup is None:
        return None, None

    # 商品名: JSON-LD(ProductGroup) > og:title
    name = None
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(tag.string or "")
            if isinstance(d, list):
                d = d[0]
            if "Product" in str(d.get("@type", "")):
                name = d.get("name")
                if name:
                    break
        except Exception:
            pass
    if not name:
        og = soup.find("meta", property="og:title")
        name = og.get("content") if og else None

    # 価格: ¥ に続く最初の数字
    price = None
    m = re.search(r"[¥￥]\s*([\d,]+)", soup.get_text())
    if m:
        price = _to_int(m.group(1))

    logger.info("H&M result: name=%s price=%s", name, price)
    return name or None, price or None


def _scrape_zara(url: str) -> tuple[str | None, int | None]:
    """ZARA: ScraperAPI(render=True) + og:title + .price セレクターで取得。"""
    soup = _fetch_via_scraperapi(url, render=True)
    if soup is None:
        return None, None

    og = soup.find("meta", property="og:title")
    name = og.get("content") if og else None

    price = None
    tag = soup.select_one(".price")
    if tag:
        price = _to_int(tag.get_text())

    logger.info("ZARA result: name=%s price=%s", name, price)
    return name or None, price or None


def _scrape_cos(url: str) -> tuple[str | None, int | None]:
    """COS: ScraperAPI(render=True) + og:title + [class*='price']で¥価格を取得。"""
    soup = _fetch_via_scraperapi(url, render=True)
    if soup is None:
        return None, None

    og = soup.find("meta", property="og:title")
    name = og.get("content") if og else None

    price = None
    price_tags = soup.select("[class*='price']")

    # 1. 「税込」を含むタグを優先（商品価格に付くことが多い）
    for tag in price_tags:
        text = tag.get_text()
        if ("¥" in text or "￥" in text) and "税込" in text:
            price = _to_int(text)
            if price:
                break

    # 2. 「税込」がなければ ¥ を含む最初のタグ
    if not price:
        for tag in price_tags:
            text = tag.get_text()
            if "¥" in text or "￥" in text:
                price = _to_int(text)
                if price:
                    break

    # 3. セレクターで取れなければページ全体の ¥ 正規表現
    if not price:
        m = re.search(r"[¥￥]\s*([\d,]+)", soup.get_text())
        if m:
            price = _to_int(m.group(1))

    logger.info("COS result: name=%s price=%s", name, price)
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

    if "gu-global.com" in hostname:
        name, price = _scrape_gu(url)
        if name and price:
            return name, price

    if "hm.com" in hostname:
        return _scrape_hm(url)

    if "zara.com" in hostname:
        return _scrape_zara(url)

    if "cos.com" in hostname:
        return _scrape_cos(url)

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
