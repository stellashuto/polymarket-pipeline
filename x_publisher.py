"""
X (Twitter) 自動投稿モジュール。

⚠️ 2026-05-30 時点で X API Free tier では POST /2/tweets が 402 (credits不足)
   を返すため、現在は使用していない。手動投稿に切り替え中。
   将来 Basic ($200/月) を契約するか、Zapier等の代替に切り替えた場合に再有効化する。

- OAuth 1.0a で認証（tweet 投稿に必要）
- 記事の frontmatter + 最初のポイント箇条書きから 280 字以内のツイート生成
- ハッシュタグはカテゴリ・暗号資産シンボル・エアドロップトピックから自動生成
- 投稿済み記事の slug は output/tweeted_slugs.json で追跡（重複防止）
- X が記事URLからOGP（タイトル・サムネ）を自動取得するので画像アップロード不要
- Free tier (500投稿/月) を超えないよう月間カウンタも保持

将来の有効化時は `publish.ps1` に `python x_publisher.py --limit N` を組み込む。
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import tweepy

from config import (
    X_API_KEY, X_API_KEY_SECRET,
    X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
    ARTICLES_DIR, OUTPUT_DIR,
)

logger = logging.getLogger(__name__)

SITE_URL = "https://cryptobrief.app"
TRACK_FILE = OUTPUT_DIR / "tweeted_slugs.json"
MAX_TWEET_LEN = 280
URL_RESERVED_LEN = 24      # t.co短縮後の長さ (23) + 改行
MONTHLY_TWEET_CAP = 450    # Free tier 500/月 のうち 90% に制限（緩衝枠）

# カテゴリ別の頭絵文字とハッシュタグ
CATEGORY_META = {
    "crypto":        {"emoji": "📊", "tags": ["仮想通貨", "暗号資産"]},
    "airdrop":       {"emoji": "🎁", "tags": ["エアドロップ", "Airdrop"]},
    "politics":      {"emoji": "🏛️", "tags": ["政治", "Polymarket"]},
    "economics":     {"emoji": "📈", "tags": ["経済", "マーケット"]},
    "sports":        {"emoji": "🏆", "tags": ["スポーツ", "Polymarket"]},
    "entertainment": {"emoji": "🎬", "tags": ["エンタメ"]},
    "other":         {"emoji": "📰", "tags": ["CryptoBrief"]},
}


def is_configured() -> bool:
    return all([X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET])


_client: Optional[tweepy.Client] = None


def _get_client() -> tweepy.Client:
    global _client
    if _client is None:
        _client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_KEY_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET,
        )
    return _client


# ----------------------------------------------------------------------
# トラッキング
# ----------------------------------------------------------------------

def _load_tracking() -> dict:
    if TRACK_FILE.exists():
        try:
            return json.loads(TRACK_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"slugs": [], "monthly_count": {}}


def _save_tracking(data: dict) -> None:
    TRACK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _current_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _monthly_count(track: dict) -> int:
    return track.get("monthly_count", {}).get(_current_month_key(), 0)


# ----------------------------------------------------------------------
# 記事パース
# ----------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FIELD_RE = re.compile(r'^(\w+):\s*"?(.*?)"?\s*$', re.MULTILINE)
_BLOCK_SCALAR_RE = re.compile(r"^(\w+):\s*\|\s*\n((?:  .*\n)+)", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm_body = m.group(1)
    out = dict(_FIELD_RE.findall(fm_body))
    # YAML ブロックスカラー（複数行値）を別途取り出す
    for key, block in _BLOCK_SCALAR_RE.findall(fm_body + "\n"):
        # 各行先頭の2スペースを剥がす
        value = "\n".join(line[2:] for line in block.rstrip().split("\n"))
        out[key] = value
    return out


def _first_point(body: str, max_chars: int = 120) -> str:
    """`## ポイント` の最初の箇条書きを抜き出して短縮する。"""
    # ## ポイント ... 直後の `- 〜` を探す
    point_section = re.search(r"##\s*ポイント.*?\n((?:\s*-\s.+\n)+)", body)
    if not point_section:
        return ""
    bullets = re.findall(r"-\s+(.+)", point_section.group(1))
    if not bullets:
        return ""
    text = bullets[0].strip()
    # **強調** 記法・出典括弧を整理
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"（出典:[^）]*）", "", text)
    text = re.sub(r"\([^)]*出典[^)]*\)", "", text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


def _hashtags(fm: dict[str, str]) -> list[str]:
    tags: list[str] = []
    cat = fm.get("category", "other")
    tags.extend(CATEGORY_META.get(cat, CATEGORY_META["other"])["tags"])

    sym = fm.get("crypto_symbol", "")
    if sym:
        tags.append(sym)

    airdrop_slug = fm.get("airdrop_slug", "")
    if airdrop_slug and airdrop_slug.startswith("guide-") is False:
        # プロジェクト固有のslug → タグ化（記号除去）
        proj = re.sub(r"[^a-zA-Z0-9]", "", airdrop_slug)
        if proj:
            tags.append(proj[:20])

    # 重複削除
    seen, ordered = set(), []
    for t in tags:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(t)
    return ordered[:4]


# ----------------------------------------------------------------------
# ツイート組み立て
# ----------------------------------------------------------------------

def build_tweet(article_path: Path) -> Optional[tuple[str, str]]:
    """記事ファイルから (tweet_text, url) を生成。失敗時 None。

    frontmatter に `x_post` フィールドがあればそれをそのまま使う（記事生成時に
    Claudeが最適化したテキスト）。なければテンプレートで合成する。
    """
    try:
        raw = article_path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = _parse_frontmatter(raw)
    if not fm:
        return None

    slug = article_path.stem
    url = f"{SITE_URL}/articles/{slug}"
    title = fm.get("title", "").strip()
    if not title:
        return None

    # 生成済みツイートがあればそのまま使う（URL追加だけ）
    pre_made = fm.get("x_post", "").strip()
    if pre_made:
        return f"{pre_made}\n\n{url}", url

    category = fm.get("category", "other")
    emoji = CATEGORY_META.get(category, CATEGORY_META["other"])["emoji"]

    # 本文部分のみ
    fm_match = _FRONTMATTER_RE.match(raw)
    body = raw[fm_match.end():] if fm_match else raw
    first_point = _first_point(body, max_chars=130)

    tags_str = "  " + " ".join(f"#{t}" for t in _hashtags(fm))

    # 1: emoji + title
    # 2: blank
    # 3: 最初のポイント
    # 4: blank
    # 5: hashtags
    # 6: blank
    # 7: URL
    parts: list[str] = []
    parts.append(f"{emoji} {title}")
    if first_point:
        parts.append("")
        parts.append(first_point)
    parts.append("")
    parts.append(tags_str.strip())
    parts.append("")
    parts.append(url)

    text = "\n".join(parts)

    # X側のt.co短縮を考慮した実効長を算出
    # 日本語は1文字=1としてカウント、URLは23字に固定
    visible_chars = len(text) - len(url) + 23
    if visible_chars > MAX_TWEET_LEN:
        # title を縮めて再構築
        overflow = visible_chars - MAX_TWEET_LEN
        # 最初のポイントを優先削除
        if first_point and overflow > 0:
            first_point = first_point[: max(0, len(first_point) - overflow - 3)] + "…"
            overflow -= overflow
            parts = [
                f"{emoji} {title}",
                "",
                first_point,
                "",
                tags_str.strip(),
                "",
                url,
            ]
            text = "\n".join(parts)
            visible_chars = len(text) - len(url) + 23
        # それでも超える場合はタイトル削る
        if visible_chars > MAX_TWEET_LEN:
            title_max = len(title) - (visible_chars - MAX_TWEET_LEN) - 1
            title = title[: max(20, title_max)] + "…"
            parts[0] = f"{emoji} {title}"
            text = "\n".join(parts)

    return text, url


# ----------------------------------------------------------------------
# 投稿
# ----------------------------------------------------------------------

def post_tweet(text: str) -> Optional[str]:
    """ツイートを投稿し、ツイートID を返す。失敗時 None。"""
    if not is_configured():
        logger.warning("X API not configured. Tweet skipped.")
        return None
    try:
        resp = _get_client().create_tweet(text=text)
        tweet_id = resp.data.get("id") if resp.data else None
        logger.info("Posted tweet id=%s", tweet_id)
        return str(tweet_id) if tweet_id else None
    except tweepy.TweepyException as e:
        logger.error("Tweet failed: %s", e)
        return None


def tweet_recent(limit: int = 2, lookback: int = 12) -> int:
    """直近 lookback 件の記事から未投稿のものを最大 limit 件投稿する。"""
    if not is_configured():
        logger.info("X publisher skipped (no credentials).")
        return 0

    track = _load_tracking()
    posted_slugs: set[str] = set(track.get("slugs", []))
    current_month = _current_month_key()
    monthly = track.get("monthly_count", {}).get(current_month, 0)

    if monthly >= MONTHLY_TWEET_CAP:
        logger.warning("Monthly tweet cap (%d) reached. Skipping.", MONTHLY_TWEET_CAP)
        return 0

    # 新しい記事ほど優先（ファイルmtime順）
    candidates = sorted(
        ARTICLES_DIR.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:lookback]

    posted = 0
    for path in candidates:
        if posted >= limit:
            break
        if monthly + posted >= MONTHLY_TWEET_CAP:
            break
        slug = path.stem
        if slug in posted_slugs:
            continue

        built = build_tweet(path)
        if not built:
            continue
        text, _url = built
        tweet_id = post_tweet(text)
        if tweet_id is None:
            continue
        posted_slugs.add(slug)
        posted += 1

    track["slugs"] = sorted(posted_slugs)[-1000:]  # 直近1000件だけ覚える
    track.setdefault("monthly_count", {})
    track["monthly_count"][current_month] = monthly + posted
    _save_tracking(track)

    logger.info("X publish: %d tweets posted this run (month total: %d).",
                posted, monthly + posted)
    return posted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true",
                        help="ツイート文だけ生成・表示する")
    args = parser.parse_args()

    if args.dry_run:
        # 直近の未投稿記事のツイートをプレビュー
        track = _load_tracking()
        posted = set(track.get("slugs", []))
        candidates = sorted(ARTICLES_DIR.glob("*.md"),
                            key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        for p in candidates:
            if p.stem in posted:
                continue
            built = build_tweet(p)
            if not built:
                continue
            text, url = built
            print("=" * 60)
            print(f"[{p.name}] (visible chars: {len(text) - len(url) + 23})")
            print(text)
        print("=" * 60)
    else:
        tweet_recent(limit=args.limit)
