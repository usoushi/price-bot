import os
import logging
import re
import threading

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import database
import line_client
import scheduler
from scraper import get_product_info

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

URL_RE = re.compile(r"https?://\S+")


@app.on_event("startup")
def startup():
    database.init_db()
    scheduler.start()
    logger.info("App started")


@app.api_route("/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok"}


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    user_id: str = event.source.user_id
    text: str = event.message.text.strip()
    reply_token: str = event.reply_token

    database.upsert_user(user_id)

    # --- URL registration ---
    url_match = URL_RE.search(text)
    if url_match:
        url = url_match.group()
        line_client.reply(reply_token, "URLを確認中です。少々お待ちください...")
        # ScraperAPI使用サイトは最大60秒かかるためバックグラウンドで処理
        threading.Thread(target=_register_item, args=(user_id, url), daemon=True).start()
        return

    # --- 一覧 ---
    if text in ("一覧", "リスト", "list"):
        _show_list(user_id, reply_token)
        return

    # --- 削除 N ---
    delete_match = re.match(r"^削除\s*(\d+)$", text)
    if delete_match:
        index = int(delete_match.group(1))
        _delete_item(user_id, reply_token, index)
        return

    # --- help ---
    line_client.reply(
        reply_token,
        "使い方:\n"
        "・商品URLを送信 → 価格監視を登録\n"
        "・「一覧」→ 登録中の商品を表示\n"
        "・「削除 1」→ 番号を指定して削除",
    )


ITEM_LIMIT = 10


def _register_item(user_id: str, url: str):
    if len(database.get_items_by_user(user_id)) >= ITEM_LIMIT:
        line_client.push(
            user_id,
            f"登録上限（{ITEM_LIMIT}商品）に達しています。\n「削除 番号」で不要な商品を削除してから登録してください。",
        )
        return
    name, price = get_product_info(url)
    if not name or not price:
        line_client.push(
            user_id,
            "このURLには対応していません。\n商品名や価格を取得できませんでした。",
        )
        return
    database.add_item(user_id, url, name, price)
    line_client.push(
        user_id,
        f"登録しました！\n商品：{name}\n現在価格：{price:,}円\n値下がり時にお知らせします。",
    )


def _show_list(user_id: str, reply_token: str):
    items = database.get_items_by_user(user_id)
    if not items:
        line_client.reply(reply_token, "登録中の商品はありません。")
        return
    lines = ["登録中の商品一覧:"]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['name']}\n   現在：{item['current_price']:,}円（最安：{item['lowest_price']:,}円）")
    line_client.reply(reply_token, "\n".join(lines))


def _delete_item(user_id: str, reply_token: str, index: int):
    name = database.delete_item(user_id, index)
    if name is None:
        line_client.reply(reply_token, f"番号 {index} の商品が見つかりません。「一覧」で番号を確認してください。")
    else:
        line_client.reply(reply_token, f"「{name}」を削除しました。")
