# LINE 価格監視ボット

LINEで商品URLを送ると価格を監視し、値下がり時に通知するボットです。

---

## 機能

| コマンド | 説明 |
|---|---|
| 商品URLを送信 | 価格監視を登録（上限10商品） |
| `一覧` | 登録中の商品と現在価格・最安値を表示 |
| `削除 1` | 番号を指定して削除 |
| `使い方` | 使い方と対応サイトを表示 |

### 対応サイト

| サイト | 取得方法 | 価格チェック頻度 |
|---|---|---|
| UNIQLO | 公式API | 3時間おき |
| GU | 公式API | 3時間おき |
| Amazon | HTMLスクレイピング | 3時間おき |
| 楽天市場 | HTMLスクレイピング | 3時間おき |
| H&M | ScraperAPI | 毎朝7時（JST） |
| ZARA | ScraperAPI | 毎朝7時（JST） |
| COS | ScraperAPI | 毎朝7時（JST） |

> H&M・ZARA・COSはBot対策のためScraperAPIを使用（月1,000クレジット上限）

---

## セットアップ手順

### 1. LINE Developers の設定

1. [LINE Developers](https://developers.line.biz/) にログイン
2. **プロバイダー**を作成（初回のみ）
3. **新規チャンネル** → **Messaging API** を選択して作成
4. チャンネル基本設定から以下を控える
   - **Channel secret** → `LINE_CHANNEL_SECRET`
   - Messaging API設定 → **チャンネルアクセストークン（長期）** を発行 → `LINE_CHANNEL_ACCESS_TOKEN`
5. Messaging API設定で **応答メッセージ** を **オフ** にする
6. **Webhookの利用** を **オン** にする（URLは後で設定）

---

### 2. Supabase（データベース）の設定

1. [Supabase](https://supabase.com) で無料アカウントを作成してプロジェクトを作る
2. **Settings** → **Database** → **Connection pooling** セクションを開く
3. **Mode: Transaction**（ポート6543）の接続文字列をコピーする
4. コピーしたURLを `DATABASE_URL` として後述のRender環境変数に設定する

> ※ポート5432の直接接続はRenderの無料プランでIPv6非対応のため使用不可

---

### 3. ScraperAPI の設定（H&M・ZARA・COS を使う場合）

1. [ScraperAPI](https://www.scraperapi.com/) で無料アカウントを作成（月1,000クレジット）
2. APIキーを控えて `SCRAPER_API_KEY` として後述のRender環境変数に設定する

---

### 4. Render.com へのデプロイ

#### 4-1. GitHubにプッシュ

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
git push -u origin main
```

#### 4-2. Renderでサービスを作成

1. [Render.com](https://render.com) にログイン
2. **New** → **Web Service** → GitHubリポジトリを選択
3. `render.yaml` が自動で読み込まれる（Build/Start Commandは自動設定）
4. **Environment Variables** に以下を追加

| 変数名 | 値 |
|---|---|
| `LINE_CHANNEL_SECRET` | LINEチャンネルシークレット |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINEチャンネルアクセストークン |
| `DATABASE_URL` | SupabaseのConnection Pooler URI |
| `SCRAPER_API_KEY` | ScraperAPIのAPIキー |

5. **Create Web Service** でデプロイ開始

#### 4-3. Webhook URLを設定

1. デプロイ完了後、RenderのサービスURL（例：`https://price-bot-xxxx.onrender.com`）を確認
2. LINE Developers の **Webhook URL** に以下を設定
   ```
   https://price-bot-xxxx.onrender.com/webhook
   ```
3. **検証** ボタンを押して成功することを確認

---

### 5. リッチメニューの設定（任意）

チャット画面下部に「一覧」「使い方」ボタンを表示できます。

```bash
pip install Pillow
$env:LINE_CHANNEL_ACCESS_TOKEN="あなたのトークン"  # PowerShell
python setup_richmenu.py
```

---

## Renderの無料プランについて

- 無料プランではインスタンスが **15分間アクセスがないとスリープ** します
- スリープ中はスケジューラーも停止します（価格チェックが行われません）
- 対策：[UptimeRobot](https://uptimerobot.com/) などで `/health` エンドポイントに5〜10分おきにアクセスする設定を追加してください

---

## ファイル構成

```
.
├── main.py            # FastAPI + LINE Webhookエンドポイント
├── scraper.py         # サイト別スクレイパー（httpx + BeautifulSoup）
├── database.py        # PostgreSQL操作（psycopg2）
├── scheduler.py       # APSchedulerによる定期価格チェック
├── line_client.py     # LINE Messaging API送信
├── setup_richmenu.py  # リッチメニュー設定スクリプト（初回のみ実行）
├── requirements.txt
├── render.yaml        # Renderデプロイ設定
└── README.md
```

---

## 環境変数一覧

| 変数名 | 必須 | 説明 |
|---|---|---|
| `LINE_CHANNEL_SECRET` | ✅ | LINEチャンネルシークレット |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINEチャンネルアクセストークン |
| `DATABASE_URL` | ✅ | Supabase PostgreSQL接続文字列（Pooler URI） |
| `SCRAPER_API_KEY` | - | ScraperAPI キー（H&M・ZARA・COS対応に必要） |
