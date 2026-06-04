# crash-royale-daily-snapshots

Clash Royale API から取得した日次スナップショットを GitHub Pages で公開するリポジトリです。

## 公開 URL（Pages 有効化後）

```
https://<owner>.github.io/crash-royale-daily-snapshots/latest.json
https://<owner>.github.io/crash-royale-daily-snapshots/20260604.json
https://<owner>.github.io/crash-royale-daily-snapshots/index.json
```

## セットアップ

1. GitHub リポジトリの **Settings → Secrets** に `CR_TOKEN`（[Clash Royale API キー](https://developer.clashroyale.com/)）を登録
2. **Settings → Pages → Build from branch → `/docs` on `main`**
3. `.github/workflows/collect-leaderboard-decks.yml` が毎日 **JST 1:00** に実行される

手動実行: **Actions → Collect leaderboard decks → Run workflow**

## ローカル実行

macOS では `pip` コマンドが無いことが多いです。次のどちらかを使ってください。

```bash
cd ~/Documents/crash-royale-daily-snapshots

# 依存関係（どちらか）
python3 -m pip install -r requirements.txt
# または
pip3 install -r requirements.txt

export CR_TOKEN='your-token'
python3 scripts/collect_leaderboard_decks.py --limit 100 --output-dir docs
```

Homebrew の Python 3.12 を使う場合:

```bash
/opt/homebrew/bin/python3.12 -m pip install -r requirements.txt
/opt/homebrew/bin/python3.12 scripts/collect_leaderboard_decks.py --limit 100
```

## JSON（v1: `leaderboard-decks`）

`docs/YYYYMMDD.json` の形式は [schema/leaderboard-decks.v1.md](schema/leaderboard-decks.v1.md) を参照。

iOS アプリの `AggregatedDeck` / `DeckCardDisplay` / `DeckOwnerSummary` と同じフィールド名でデコードできます。

## ディレクトリ

```
docs/              # GitHub Pages ルート（日次 JSON）
scripts/           # 収集スクリプト
schema/            # スキーマ説明
.github/workflows/
```
