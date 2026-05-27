"""
仮想通貨銘柄解説記事ジェネレータ。

各銘柄ごとに「○○ とは」「○○ 仕組み」「○○ 買い方」をカバーする長尾SEO記事を生成。
直近のRSSニュースを反映し、現在の市場動向も組み込む。

トークン単位の重複防止のため、frontmatterに crypto_slug を保存する。
"""

import logging
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
import httpx

from config import ANTHROPIC_API_KEY, ARTICLES_DIR
from crypto_tokens import TOKENS, CryptoToken
from news_scraper import NewsScraper, NewsItem
from thumbnail_generator import generate_thumbnail
from translator import translate_title

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """あなたは仮想通貨業界で 7年以上の実取引・分析経験を持つ日本語ライターです。
読者は仮想通貨の基本〜中級レベル。「○○ とは」「○○ 仕組み」のような検索意図を持って来訪する想定。

## トーン
- 経験者の視点。「筆者は2018年からこの銘柄を保有しているが」「実際にステーキングしてみると」のような体験的トーン
- 短文と長文を交ぜる。曖昧な「〜可能性があります」を多用しない
- 「皆さん」「いかがでしょうか」「ぜひ参考に」「投資は自己責任」など読者呼びかけ・定型句は禁止
- AIっぽいテンプレ「まず〜、次に〜、最後に〜」の連発を避ける
- 業界スラング（PoW・PoS・ガス代・TVL等）は初出時に簡潔に解説

## 構造（柔軟、内容に応じて省略・追加OK）
- 1行目に `# 日本語タイトル`
- `## ポイント` — 3〜4個の結論先出し
- リード文（150字程度）
- `## ○○とは` — 概要と特徴
- `## 仕組み・技術` — 技術的な要点（PoW/PoS、コンセンサス、独自要素）
- `## 歴史・主要マイルストーン`
- `## 現在の市場動向` — 直近ニュースを反映（あれば）
- `## 日本での購入方法` — Coincheck・bitFlyer・GMOコイン等の取扱状況
- `## 投資リスクと注意点`
- まとめ
- `## よくある質問` — 3問（`### Q1.` 形式）

## 必須要素
- **「日本での購入方法」セクション** で日本の代表的取引所（bitFlyer / Coincheck / GMOコイン / SBI VC Trade / BITPOINT 等）の取扱状況に触れる
- **税金注意** — 日本の暗号資産税制（雑所得・最大55%税率）への言及
- 2,000字以上の充実した本文

## 禁止
- 価格予想・買い煽り
- 特定取引所への露骨な誘導（事実ベースの情報提供のみ）
- 投資助言と誤解される表現
- 本文中のJSON・<script>タグ・コードブロック内メタデータ"""


_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            http_client=httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0)),
        )
    return _client


def _existing_slugs() -> set[str]:
    slugs: set[str] = set()
    if not ARTICLES_DIR.exists():
        return slugs
    for md in ARTICLES_DIR.glob("*.md"):
        try:
            head = md.read_text(encoding="utf-8")[:1500]
        except OSError:
            continue
        m = re.search(r'^crypto_slug:\s*"?(.+?)"?\s*$', head, re.MULTILINE)
        if m:
            slugs.add(m.group(1).strip())
    return slugs


def _pick_token() -> Optional[CryptoToken]:
    covered = _existing_slugs()
    candidates = [t for t in TOKENS if t.slug not in covered]
    if not candidates:
        logger.warning("All %d crypto tokens covered. Nothing to write.", len(TOKENS))
        return None
    return random.choice(candidates)


def _fetch_recent_news_for_token(token: CryptoToken, news_items: list[NewsItem],
                                   max_results: int = 5) -> list[NewsItem]:
    needles = [token.name.lower(), token.symbol.lower()]
    if token.search_keywords:
        needles.extend(k.lower() for k in token.search_keywords)
    needles = [n for n in needles if n and len(n) >= 3]
    if not needles:
        return []
    matched: list[NewsItem] = []
    for item in news_items:
        hay = (item.title + " " + item.summary).lower()
        if any(n in hay for n in needles):
            matched.append(item)
    matched.sort(
        key=lambda n: n.published.timestamp() if n.published else 0,
        reverse=True,
    )
    return matched[:max_results]


def _format_news_block(news: list[NewsItem]) -> str:
    if not news:
        return ""
    lines = ["", "## 直近のニュース動向（過去 1〜2 週間）",
             "下記の最新ニュースを「現在の市場動向」セクションに必ず反映してください。",
             "古い知識を漫然と書くのではなく、直近の動きを中心に解説すること。", ""]
    for n in news:
        date = n.published.strftime("%Y-%m-%d") if n.published else "n/a"
        lines.append(f"### [{date}] {n.source}")
        lines.append(f"タイトル: {n.title}")
        if n.summary:
            lines.append(f"要旨: {n.summary[:400]}")
        lines.append(f"URL: {n.link}")
        lines.append("")
    return "\n".join(lines)


def _build_user_prompt(token: CryptoToken, news: list[NewsItem]) -> str:
    cat_jp = {
        "L1": "L1ブロックチェーン",
        "L2": "L2スケーリングソリューション",
        "DeFi": "DeFiプロトコル",
        "Stablecoin": "ステーブルコイン",
        "Meme": "ミームコイン",
        "Other": "その他",
    }.get(token.category, "暗号資産")

    return f"""以下の銘柄について「○○ とは」を網羅する解説記事を日本語で書いてください。

## 銘柄情報
- シンボル: {token.symbol}
- 英語名: {token.name}
- 日本語表記: {token.name_jp}
- カテゴリ: {cat_jp}
- 概要（参考、古い可能性あり）: {token.summary}

{_format_news_block(news)}

## タイトル指示
タイトルは「{token.name}（{token.symbol}）とは？〜」または「{token.symbol}徹底解説」のような検索意図ど真ん中の形式に。
直近ニュースの要素を含められれば尚良し（例: 「ETF承認」「最高値更新」など）。

人間の経験者として書いてください。AIっぽいテンプレ感を出さないこと。"""


def _build_frontmatter(token: CryptoToken, title: str, title_en: str,
                       thumbnail: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_title = title.replace('"', "'")
    safe_title_en = (title_en or "").replace('"', "'")
    return f"""---
title: "{safe_title}"
title_en: "{safe_title_en}"
date: "{now}"
category: "crypto"
categories:
  - crypto
crypto_slug: "{token.slug}"
crypto_symbol: "{token.symbol}"
crypto_category: "{token.category}"
thumbnail: "{thumbnail}"
type: "explainer"
---

"""


def generate_crypto_article(token: Optional[CryptoToken] = None,
                              news_cache: Optional[list[NewsItem]] = None) -> Optional[Path]:
    if token is None:
        token = _pick_token()
    if token is None:
        return None

    logger.info("Generating crypto explainer: %s (%s)", token.symbol, token.name)

    # 直近ニュースを取得
    recent_news: list[NewsItem] = []
    if news_cache is None:
        try:
            news_cache = NewsScraper().fetch(fresh_only=False)
        except Exception as e:
            logger.warning("News fetch failed: %s", e)
            news_cache = []
    recent_news = _fetch_recent_news_for_token(token, news_cache)
    if recent_news:
        logger.info("  Found %d recent news items for %s", len(recent_news), token.symbol)

    client = _get_client()
    full_text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": _build_user_prompt(token, recent_news)}],
    ) as stream:
        for text in stream.text_stream:
            full_text += text
        final = stream.get_final_message()
        logger.info(
            "Usage — input: %d, output: %d, cache_read: %d",
            final.usage.input_tokens, final.usage.output_tokens,
            final.usage.cache_read_input_tokens or 0,
        )

    m = re.match(r"^\s*#\s+(.+?)\s*\n", full_text)
    if m:
        ja_title = m.group(1).strip()
        body = full_text[m.end():]
    else:
        ja_title = f"{token.name}（{token.symbol}）とは？仕組み・特徴・買い方まとめ"
        body = full_text

    slug_for_files = f"crypto_{token.slug}"
    thumb_path = generate_thumbnail(
        slug=slug_for_files,
        title=ja_title,
        summary=f"{token.name}({token.symbol})の解説。{token.summary[:200]}",
        category="crypto",
    )
    thumbnail_name = thumb_path.name if thumb_path else ""

    title_en = translate_title(ja_title)
    if title_en:
        logger.info("EN title: %s", title_en[:80])

    content = _build_frontmatter(token, ja_title, title_en, thumbnail_name) + body

    out_path = ARTICLES_DIR / f"{slug_for_files}.md"
    out_path.write_text(content, encoding="utf-8")
    logger.info("Crypto explainer saved → %s", out_path)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    generate_crypto_article()
