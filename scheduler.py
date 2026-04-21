import logging

from apscheduler.schedulers.background import BackgroundScheduler

import database
import line_client
from scraper import get_product_info

logger = logging.getLogger(__name__)


def check_all_prices():
    logger.info("Price check started")
    items = database.get_all_items()
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

    logger.info("Price check finished (%d items)", len(items))


def start():
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(check_all_prices, "interval", hours=3, id="price_check")
    scheduler.start()
    logger.info("Scheduler started (every 3 hours)")
    return scheduler
