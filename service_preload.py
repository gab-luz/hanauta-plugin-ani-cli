#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from urllib import request

STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "service" / "plugins"
CACHE_FILE = STATE_DIR / "ani_cli_catalog.json"
POSTER_DIR = STATE_DIR / "ani_cli_posters"
TMDB_PAGE = "https://www.themoviedb.org/keyword/210024-anime/tv?page={page}"
USER_AGENT = "HanautaAniCliPreload/1.0"
MIN_REFRESH_SECONDS = 20 * 60
MAX_ITEMS = 16


def load_cache() -> dict[str, object]:
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_cache(payload: dict[str, object]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_cache_fresh(payload: dict[str, object]) -> bool:
    fetched_at = int(payload.get("fetched_at", 0) or 0)
    if fetched_at <= 0:
        return False
    return (time.time() - fetched_at) < MIN_REFRESH_SECONDS


def normalize_poster_url(raw: str) -> str:
    text = str(raw).strip()
    if not text:
        return ""
    if text.startswith("https://") or text.startswith("http://"):
        if "/t/p/" not in text:
            return ""
        filename = text.split("/")[-1]
        return f"https://image.tmdb.org/t/p/w342/{filename}" if filename else ""
    if not text.startswith("/t/p/"):
        return ""
    filename = text.split("/")[-1]
    return f"https://image.tmdb.org/t/p/w342/{filename}" if filename else ""


def fetch_html(page: int) -> str:
    req = request.Request(TMDB_PAGE.format(page=page), headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=9) as response:
        return response.read().decode("utf-8", errors="ignore")


def parse_catalog(html_text: str) -> list[dict[str, str]]:
    cards = re.findall(
        r'<a[^>]+href="(?P<href>/tv/[^\"]+)"[^>]*>\s*(?P<img><img[^>]+>)',
        html_text,
        flags=re.IGNORECASE,
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, img_tag in cards:
        title_match = re.search(r'alt="([^"]+)"', img_tag, flags=re.IGNORECASE)
        image_match = re.search(r'https?://[^"\' ]*/t/p/[^"\' ]+|/t/p/[^"\' ]+', img_tag, flags=re.IGNORECASE)
        if title_match is None or image_match is None:
            continue
        title = title_match.group(1).strip()
        if not title or title == "The Movie Database (TMDB)":
            continue
        poster_url = normalize_poster_url(image_match.group(0))
        if not poster_url:
            continue
        tmdb_match = re.search(r"/tv/(\d+)", href)
        tmdb_id = tmdb_match.group(1) if tmdb_match else ""
        detail_url = "https://www.themoviedb.org" + href
        key = f"{title.lower()}::{tmdb_id}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "title": title,
                "tmdb_id": tmdb_id,
                "detail_url": detail_url,
                "poster_url": poster_url,
            }
        )
        if len(rows) >= MAX_ITEMS:
            break
    return rows


def download_poster(row: dict[str, str]) -> str:
    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    tmdb_id = row.get("tmdb_id", "") or str(abs(hash(row.get("title", ""))))
    target = POSTER_DIR / f"{tmdb_id}.jpg"
    if target.exists() and target.stat().st_size > 64:
        return str(target)
    req = request.Request(row.get("poster_url", ""), headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=6) as response:
        data = response.read()
    if not data:
        return ""
    target.write_bytes(data)
    return str(target)


def refresh_catalog() -> None:
    old = load_cache()
    if is_cache_fresh(old):
        return

    page = random.randint(1, 8)
    html_text = fetch_html(page)
    parsed = parse_catalog(html_text)
    items: list[dict[str, str]] = []
    for row in parsed:
        try:
            poster_path = download_poster(row)
        except Exception:
            poster_path = ""
        if not poster_path:
            continue
        items.append(
            {
                "title": row.get("title", ""),
                "tmdb_id": row.get("tmdb_id", ""),
                "detail_url": row.get("detail_url", ""),
                "poster_path": poster_path,
            }
        )

    if not items and old.get("items"):
        return

    payload = {
        "source": "tmdb_keyword_anime",
        "fetched_at": int(time.time()),
        "page": page,
        "items": items,
    }
    save_cache(payload)


if __name__ == "__main__":
    refresh_catalog()
