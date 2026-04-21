"""
リッチメニュー設定スクリプト（一回だけ実行する）
実行前に: pip install Pillow httpx
実行方法: LINE_CHANNEL_ACCESS_TOKEN=xxx python setup_richmenu.py
"""
import os
import json
import httpx
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

W, H = 2500, 843

BUTTONS = [
    {"label": "一覧", "action": "一覧", "bg": (66, 133, 244)},
    {"label": "使い方", "action": "使い方", "bg": (52, 168, 83)},
]


def get_font(size: int):
    for path in [
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def create_image(path: str = "richmenu.png"):
    img = Image.new("RGB", (W, H), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    font = get_font(140)
    n = len(BUTTONS)
    bw = W // n

    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = i * bw, 0, i * bw + bw, H
        draw.rectangle([x0 + 16, y0 + 16, x1 - 16, y1 - 16], fill=btn["bg"])
        bbox = draw.textbbox((0, 0), btn["label"], font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (x0 + (bw - tw) // 2, y0 + (H - th) // 2),
            btn["label"],
            fill=(255, 255, 255),
            font=font,
        )

    img.save(path)
    print(f"Image saved: {path}")


def create_richmenu() -> str:
    bw = W // len(BUTTONS)
    menu = {
        "size": {"width": W, "height": H},
        "selected": True,
        "name": "price-bot-menu",
        "chatBarText": "メニュー",
        "areas": [
            {
                "bounds": {"x": i * bw, "y": 0, "width": bw, "height": H},
                "action": {"type": "message", "text": btn["action"]},
            }
            for i, btn in enumerate(BUTTONS)
        ],
    }
    r = httpx.post(
        "https://api.line.me/v2/bot/richmenu",
        headers={**HEADERS, "Content-Type": "application/json"},
        content=json.dumps(menu),
        timeout=30,
    )
    r.raise_for_status()
    menu_id = r.json()["richMenuId"]
    print(f"Rich menu created: {menu_id}")
    return menu_id


def upload_image(menu_id: str, path: str = "richmenu.png"):
    with open(path, "rb") as f:
        r = httpx.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers={**HEADERS, "Content-Type": "image/png"},
            content=f.read(),
            timeout=30,
        )
    r.raise_for_status()
    print("Image uploaded")


def set_default(menu_id: str):
    r = httpx.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{menu_id}",
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    print("Set as default rich menu")


if __name__ == "__main__":
    create_image()
    menu_id = create_richmenu()
    upload_image(menu_id)
    set_default(menu_id)
    print("Done! LINEアプリを再起動するとメニューが表示されます。")
