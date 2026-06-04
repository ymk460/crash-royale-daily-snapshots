# leaderboard-decks v1

日次ファイル `docs/YYYYMMDD.json` および `docs/latest.json`（当日と同一内容）のスキーマです。

## トップレベル

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `schemaVersion` | `1` | 破壊的変更時に increment |
| `kind` | `"leaderboard-decks"` | スナップショット種別 |
| `date` | `"YYYYMMDD"` | **JST** の収集日 |
| `generatedAt` | ISO8601 UTC | 生成時刻 |
| `leaderboard` | object | 使用したリーダーボード |
| `leaderboard.id` | number | |
| `leaderboard.name` | string | |
| `stats` | object | 集計メタ |
| `failedPlayers` | array | 取得失敗プレイヤー（任意） |
| `aggregatedDecks` | array | **アプリの主表示用** |
| `players` | array | 生データ（任意・分析用） |

## `aggregatedDecks[]`（≈ iOS `AggregatedDeck`）

| フィールド | 型 | iOS |
|-----------|-----|-----|
| `id` | string | `AggregatedDeck.id`（カード ID 昇順を `-` 連結） |
| `usageCount` | number | `usageCount` |
| `cards` | array | `cards` |
| `owners` | array | `owners` |

### `cards[]`（≈ `DeckCardDisplay`）

```json
{ "id": 26000000, "name": "Knight", "level": 14, "elixirCost": 3 }
```

### `owners[]`（≈ `DeckOwnerSummary`）

```json
{ "tag": "#RVCQ2CQGJ", "name": "Player", "rank": 1, "trophies": 9500 }
```

## `players[]`（オプション）

ランキング 1 行 + その日の `currentDeck`。アプリで「誰が何を使ったか」を追うとき用。

```json
{
  "tag": "#RVCQ2CQGJ",
  "name": "Player",
  "rank": 1,
  "trophies": 9500,
  "deckSignature": "26000000-26000001",
  "deck": [ /* cards と同形 */ ]
}
```

## `index.json`

```json
{
  "schemaVersion": 1,
  "latest": "20260604",
  "dates": ["20260604", "20260603"]
}
```

## iOS 取り込み例

```swift
struct DailyDeckSnapshot: Decodable {
    let schemaVersion: Int
    let kind: String
    let date: String
    let generatedAt: String
    let leaderboard: LeaderboardRef
    let stats: Stats
    let aggregatedDecks: [AggregatedDeckDTO]

    struct AggregatedDeckDTO: Decodable {
        let id: String
        let usageCount: Int
        let cards: [DeckCardDTO]
        let owners: [DeckOwnerDTO]
    }
    // DeckCardDTO / DeckOwnerDTO は AggregatedDeck と同フィールド名
}
```

`AggregatedDeckDTO` → 既存 `AggregatedDeck` へマッピングするだけで UI 再利用可能です。
