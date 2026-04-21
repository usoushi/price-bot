# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 開発ルール

**PoCファースト原則**（`.claude/rules/poc-first.md` およびグローバル `CLAUDE.md` に記載）
- 外部API・スクレイピングの新規実装前に必ずPoCスクリプトで動作確認する
- PoCで問題が判明した場合は代替手段を提案してから本実装に進む

## アーキテクチャ

```
LINE Webhook → main.py → scraper.py（価格取得）→ database.py（PostgreSQL保存）
                       → line_client.py（返信）

scheduler.py（APScheduler）→ scraper.py → database.py → line_client.py（値下がり通知）
```

### スクレイピング戦略（scraper.py）

サイトによって取得方法が異なる：

| サイト | 方法 |
|---|---|
| UNIQLO / GU | 公式内部APIを直接呼び出し（スクレイピング不要） |
| H&M / ZARA / COS | ScraperAPI経由（Bot対策回避）。H&MはScraperAPI render=False（1クレジット）、ZARA・COSはrender=True（5クレジット） |
| Amazon / 楽天市場 | httpxで直接取得 + BeautifulSoup |
| その他 | JSON-LD → metaタグ → CSSセレクターの順でフォールバック |

### スケジューラー（scheduler.py）

- **直接アクセスサイト**（UNIQLO・GU・Amazon・楽天）：3時間おき
- **ScraperAPIサイト**（H&M・ZARA・COS）：毎朝7時（JST）、月1,000クレジット上限を考慮

### 非同期処理（main.py）

ScraperAPIは最大60秒かかる場合があり、LINE Webhookの10秒タイムアウトを超えるため、URL登録処理は `threading.Thread(daemon=True)` でバックグラウンド実行し、結果は `line_client.push()` で通知する。

## ローカル実行

```powershell
pip install -r requirements.txt

$env:LINE_CHANNEL_SECRET="xxx"
$env:LINE_CHANNEL_ACCESS_TOKEN="xxx"
$env:DATABASE_URL="postgresql://..."
$env:SCRAPER_API_KEY="xxx"

uvicorn main:app --reload --port 8000
```

## リッチメニュー設定（初回のみ）

```powershell
pip install Pillow
$env:LINE_CHANNEL_ACCESS_TOKEN="xxx"
python setup_richmenu.py
```

## デプロイ

Render.com + Supabase PostgreSQL。`render.yaml` により自動設定される。

**重要**：SupabaseのDATABASE_URLはポート5432の直接接続ではなく、**Connection Pooler（ポート6543）のURIを使う**（RenderのFreeプランはIPv6非対応のため）。

## 環境変数

| 変数名 | 必須 | 説明 |
|---|---|---|
| `LINE_CHANNEL_SECRET` | ✅ | LINE Webhook署名検証 |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE API送信 |
| `DATABASE_URL` | ✅ | Supabase PostgreSQL（Pooler URI） |
| `SCRAPER_API_KEY` | - | H&M・ZARA・COS対応に必要 |
