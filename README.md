# LINE 価格監視ボット

LINEで商品URLを送ると価格を監視し、値下がり時に通知するボットです。

---

## 機能

| コマンド | 説明 |
|---|---|
| 商品URLを送信 | 価格監視を登録 |
| `一覧` | 登録中の商品と現在価格を表示 |
| `削除 1` | 番号を指定して削除 |

対応サイト例：Amazon、楽天市場、UNIQLO、その他JSONLDや価格メタタグを持つECサイト

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
6. **Webhook URL** は後でRenderのURLを設定する（後述）
7. **Webhookの利用** を **オン** にする

---

### 2. Render.com へのデプロイ

#### 2-1. GitHubにプッシュ

```bash
git init
git add .
git commit -m "initial commit"
# GitHubで新規リポジトリを作成してプッシュ
git remote add origin https://github.com/<あなたのユーザー名>/<リポジトリ名>.git
git push -u origin main
```

#### 2-2. Renderでサービスを作成

1. [Render.com](https://render.com) にログイン・アカウント作成
2. **New** → **Web Service** をクリック
3. GitHubと連携してリポジトリを選択
4. 設定は `render.yaml` が自動で読み込まれるが、以下を確認
   - **Build Command**: `pip install -r requirements.txt && playwright install chromium --with-deps`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Environment Variables** に以下を追加
   - `LINE_CHANNEL_SECRET` → 手順1で控えた値
   - `LINE_CHANNEL_ACCESS_TOKEN` → 手順1で控えた値
6. **Disk** を追加（無料プランでは利用不可のため、SQLiteファイルの永続化にはDiskが必要）
   - Mount Path: `/data`
   - ※無料プランの場合はPlanetScaleやSupabase等の外部DBへの移行を検討してください
7. **Create Web Service** でデプロイ開始（数分かかります）

#### 2-3. Webhook URLを設定

1. Renderのデプロイ完了後、サービスのURLを確認（例：`https://price-bot-xxxx.onrender.com`）
2. LINE Developers の **Webhook URL** に以下を設定
   ```
   https://price-bot-xxxx.onrender.com/webhook
   ```
3. **検証** ボタンを押して成功することを確認

---

### 3. ローカルでの動作確認

```bash
# 依存パッケージのインストール
pip install -r requirements.txt
playwright install chromium

# 環境変数を設定
export LINE_CHANNEL_SECRET=your_secret
export LINE_CHANNEL_ACCESS_TOKEN=your_token
export DB_PATH=./price_bot.db  # ローカルではカレントディレクトリに保存

# サーバー起動
uvicorn main:app --reload --port 8000
```

ローカルでLINE Webhookを受信するには [ngrok](https://ngrok.com/) などを使用してください。

```bash
ngrok http 8000
# 表示されたhttps URLをLINE DevelopersのWebhook URLに設定
```

---

## Renderの無料プランについて

- 無料プランではインスタンスが **15分間アクセスがないとスリープ** します
- スリープ中はスケジューラーも停止します（価格チェックが行われません）
- 対策として以下のいずれかを検討してください
  - [UptimeRobot](https://uptimerobot.com/) などで `/` エンドポイントに定期アクセス（5〜10分おき）
  - Renderの有料プランにアップグレード

---

## ファイル構成

```
.
├── main.py          # FastAPI + LINEWebhookエンドポイント
├── scraper.py       # 汎用スクレイパー（requests + Playwright）
├── database.py      # SQLite操作
├── scheduler.py     # APSchedulerによる定期価格チェック
├── line_client.py   # LINE Messaging API送信
├── requirements.txt
├── render.yaml      # Renderデプロイ設定
└── README.md
```

---

## 環境変数一覧

| 変数名 | 必須 | 説明 |
|---|---|---|
| `LINE_CHANNEL_SECRET` | ✅ | LINEチャンネルシークレット |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINEチャンネルアクセストークン |
| `CHECK_INTERVAL_HOURS` | - | 価格チェック間隔（時間、デフォルト: 3） |
| `DB_PATH` | - | SQLiteファイルパス（デフォルト: /data/price_bot.db） |
