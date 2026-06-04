#!/usr/bin/env python3
"""
Collect top-N player currentDeck from a trophy-road leaderboard and write daily JSON.

Requires CR_TOKEN environment variable (Clash Royale API key).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

API_BASE = "https://api.clashroyale.com/v1"
SCHEMA_VERSION = 1
KIND = "leaderboard-decks"

CURRENT_TROPHY_ROAD_MIN_ID = 170_000_000

EXCLUDED_KEYWORDS = [
    "merge",
    "tactics",
    "touchdown",
    "triple draft",
    "draft",
    "sudden death",
    "heist",
    "ball",
    "ramp up",
    "mirror",
    "clone",
    "sparky",
    "goblin",
    "touch down",
    "2v2",
    "elixir",
    "tournament",
]

PREFERRED_KEYWORDS = [
    "path of legend",
    "ultimate champion",
    "royal champion",
    "grand champion",
    "champion",
    "master",
    "ladder",
    "classic",
    "1v1",
    "retro royale",
]

GENERIC_LEADERBOARD_NAME = re.compile(r"^Leaderboard #\d+$", re.IGNORECASE)


class ClashRoyaleClient:
    def __init__(self, token: str, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["Accept"] = "application/json"

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{API_BASE}{path}"
        response = self._session.get(url, params=params, timeout=60)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "5"))
            time.sleep(retry_after)
            response = self._session.get(url, params=params, timeout=60)
        response.raise_for_status()
        return response.json()


def encode_player_tag(tag: str) -> str:
    tag = tag.strip()
    if tag.startswith("%23"):
        tag = "#" + tag[3:]
    if tag and not tag.startswith("#"):
        tag = "#" + tag
    return quote(tag, safe="")


def localized_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("en") or next(iter(value.values()), None)
    return None


def select_leaderboard(boards: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        b
        for b in boards
        if b.get("id") is not None
        and not any(kw in (b.get("name") or "").lower() for kw in EXCLUDED_KEYWORDS)
    ]
    if not candidates:
        raise RuntimeError("使用可能なリーダーボードがありません")

    for keyword in PREFERRED_KEYWORDS:
        for board in candidates:
            if keyword in (board.get("name") or "").lower():
                return board

    current_roads = [
        b
        for b in candidates
        if int(b["id"]) >= CURRENT_TROPHY_ROAD_MIN_ID
        and not GENERIC_LEADERBOARD_NAME.match(b.get("name") or "")
    ]
    if current_roads:
        return max(current_roads, key=lambda b: int(b["id"]))

    named = [
        b for b in candidates if not GENERIC_LEADERBOARD_NAME.match(b.get("name") or "")
    ]
    if named:
        return max(named, key=lambda b: int(b["id"]))

    return max(candidates, key=lambda b: int(b["id"]))


def parse_leaderboard_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("items") or []
    else:
        items = []
    players: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        tag = row.get("tag") or row.get("playerTag")
        players.append(
            {
                "tag": tag,
                "name": row.get("name"),
                "rank": row.get("rank"),
                "trophies": row.get("trophies"),
            }
        )
    return players


def card_from_api(item: dict[str, Any]) -> dict[str, Any] | None:
    card_id = item.get("id")
    if card_id is None:
        return None
    return {
        "id": int(card_id),
        "name": localized_name(item.get("name")) or f"Card {card_id}",
        "level": item.get("level"),
        "elixirCost": item.get("elixirCost"),
    }


def deck_signature(cards: list[dict[str, Any]]) -> str:
    return "-".join(str(c["id"]) for c in sorted(cards, key=lambda c: c["id"]))


def fetch_player_deck(
    client: ClashRoyaleClient, player: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    tag = player.get("tag")
    if not tag:
        return player, None, "タグなし"

    try:
        payload = client.get(f"/players/{encode_player_tag(tag)}")
    except requests.HTTPError as error:
        return player, None, f"HTTP {error.response.status_code if error.response else error}"
    except requests.RequestException as error:
        return player, None, str(error)

    raw_deck = payload.get("currentDeck") or []
    cards = [c for item in raw_deck if (c := card_from_api(item)) is not None]
    if not cards:
        return player, None, "currentDeck なし"

    record = {
        "tag": payload.get("tag") or tag,
        "name": payload.get("name") or player.get("name") or "Unknown",
        "rank": player.get("rank"),
        "trophies": payload.get("trophies") or player.get("trophies"),
        "deckSignature": deck_signature(cards),
        "deck": cards,
    }
    return player, record, None


def aggregate_decks(player_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in player_records:
        signature = record["deckSignature"]
        bucket = grouped.setdefault(
            signature,
            {"id": signature, "cards": record["deck"], "usageCount": 0, "owners": []},
        )
        bucket["usageCount"] += 1
        bucket["owners"].append(
            {
                "tag": record["tag"],
                "name": record["name"],
                "rank": record.get("rank"),
                "trophies": record.get("trophies"),
            }
        )

    decks = list(grouped.values())
    for deck in decks:
        deck["owners"].sort(key=lambda o: o.get("rank") if o.get("rank") is not None else 10**9)

    decks.sort(
        key=lambda d: (
            -d["usageCount"],
            d["owners"][0].get("rank") if d["owners"] else 10**9,
        )
    )
    return decks


def update_index(output_dir: str, date_str: str) -> None:
    index_path = os.path.join(output_dir, "index.json")
    if os.path.isfile(index_path):
        with open(index_path, encoding="utf-8") as file:
            index = json.load(file)
    else:
        index = {"schemaVersion": SCHEMA_VERSION, "latest": date_str, "dates": []}

    dates: list[str] = index.get("dates") or []
    if date_str not in dates:
        dates.insert(0, date_str)
    index["schemaVersion"] = SCHEMA_VERSION
    index["latest"] = date_str
    index["dates"] = sorted(dates, reverse=True)

    with open(index_path, "w", encoding="utf-8") as file:
        json.dump(index, file, ensure_ascii=False, indent=2)
        file.write("\n")


def collect(
    *,
    limit: int,
    concurrency: int,
    output_dir: str,
    date_str: str | None,
) -> str:
    token = os.environ.get("CR_TOKEN", "").strip()
    if not token:
        raise SystemExit("CR_TOKEN が設定されていません")

    jst = ZoneInfo("Asia/Tokyo")
    if date_str is None:
        date_str = datetime.now(jst).strftime("%Y%m%d")

    client = ClashRoyaleClient(token)

    boards_payload = client.get("/leaderboards")
    if isinstance(boards_payload, dict):
        boards = boards_payload.get("items") or []
    else:
        boards = boards_payload

    board = select_leaderboard(boards)
    board_id = int(board["id"])
    board_name = localized_name(board.get("name")) or f"Leaderboard #{board_id}"

    leaderboard_payload = client.get(
        f"/leaderboard/{board_id}",
        params={"limit": limit},
    )
    rankings = parse_leaderboard_items(leaderboard_payload)[:limit]
    rankings = [p for p in rankings if p.get("tag")]

    if not rankings:
        raise RuntimeError("リーダーボードにプレイヤーがいません")

    player_records: list[dict[str, Any]] = []
    failed_players: list[dict[str, str]] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(fetch_player_deck, client, player): player
            for player in rankings
        }
        for future in as_completed(futures):
            _player, record, error = future.result()
            if record:
                player_records.append(record)
            elif error:
                tag = _player.get("tag") or "?"
                failed_players.append({"tag": tag, "reason": error})

    aggregated = aggregate_decks(player_records)
    if not aggregated:
        raise RuntimeError("集計できるデッキがありません")

    snapshot = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": KIND,
        "date": date_str,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "leaderboard": {"id": board_id, "name": board_name},
        "stats": {
            "rankingCount": len(rankings),
            "playersWithDeck": len(player_records),
            "playersFailed": len(failed_players),
            "uniqueDecks": len(aggregated),
            "requestedLimit": limit,
        },
        "failedPlayers": failed_players,
        "aggregatedDecks": aggregated,
        "players": player_records,
    }

    os.makedirs(output_dir, exist_ok=True)
    dated_path = os.path.join(output_dir, f"{date_str}.json")
    latest_path = os.path.join(output_dir, "latest.json")

    with open(dated_path, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)
        file.write("\n")

    with open(latest_path, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)
        file.write("\n")

    update_index(output_dir, date_str)
    return dated_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect daily leaderboard deck snapshot")
    parser.add_argument("--limit", type=int, default=100, help="Top N players (default: 100)")
    parser.add_argument("--concurrency", type=int, default=8, help="Parallel getPlayer calls")
    parser.add_argument(
        "--output-dir",
        default="docs",
        help="Output directory for GitHub Pages (default: docs)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="YYYYMMDD (default: today in Asia/Tokyo)",
    )
    args = parser.parse_args()

    path = collect(
        limit=args.limit,
        concurrency=args.concurrency,
        output_dir=args.output_dir,
        date_str=args.date,
    )
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
