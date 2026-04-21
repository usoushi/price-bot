import logging
from urllib.parse import urlparse

from apscheduler.schedulers.background import BackgroundScheduler

import database
import line_client
from scraper import get_product_info

logger = logging.getLogger(__name__)

SCRAPERAPI_HOSTS = {"hm.com", "zara.com", "cos.com"}


def _uses_scraperapi(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return any(h in hostname for h in SCRAPERAPI_HOSTS)


def _check_prices(scraperapi: bool):
    label = "daily(ScraperAPI)" if scraperapi else "interval(direct)"
    items = [item for item in database.get_all_items()
             if _uses_scraperapi(item["url"]) == scraperapi]
    logger.info("Price check [%s] started (%d items)", label, len(items))

    for item in items:
        item_id = item["id"]
        url = item["url"]
        old_price = item["current_price"]
        name = item["name"]
        user_id = item["user_id"]

        try:
            _, new_price = get_product_info(url)
        except Exception as e:
            logger.warning("scrape failed for item %d: %s", item_id, e)
            continue

        if new_price is None:
            logger.warning("price not found for item %d", item_id)
            continue

        database.update_price(item_id, new_price)

        if new_price < old_price:
            diff = old_price - new_price
            msg = (
                f"値下がり通知\n"
                f"商品：{name}\n"
                f"{old_price:,}円 → {new_price:,}円（{diff:,}円OFF）\n"
                f"{url}"
            )
            line_client.push(user_id, msg)
            logger.info("Notified %s: %s dropped %d -> %d", user_id, name, old_price, new_price)

    logger.info("Price check [%s] finished", label)


def start():
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    # UNIQLO・GU：3時間おき
    scheduler.add_job(lambda: _check_prices(False), "interval", hours=3, id="price_check_direct")
    # H&M・ZARA・COS（ScraperAPI）：毎朝7時
    scheduler.add_job(lambda: _check_prices(True), "cron", hour=7, minute=0, id="price_check_scraperapi")
    scheduler.start()
    logger.info("Scheduler started: direct=every 3h / scraperapi=daily 07:00 JST")
    return scheduler
