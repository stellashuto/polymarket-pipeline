"""
Flow A: News → 日本語要約・リライト記事を生成する。

入力:  NewsItem
出力:  output/articles/news_{id}.md (フロントマター付きMarkdown)

著作権配慮：
  - 原文を逐語引用せず、要約・自前の解説で再構成する
  - 必ず出典URLを末尾に明記し、リライト記事である旨を示す
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
import httpx

from config import ANTHROPIC_API_KEY, ARTICLES_DIR
from news_scraper import NewsItem
from thumbnail_generator import generate_thumbnail

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """あなたは仮想通貨・金融分野の日本語ニュースライターです。
読者は投資家・トレーダー・Web3関係者で、CoinPost / CoinDesk JAPAN を日常的に読んでいる層です。

## 執筆方針
- 原文を逐語引用せず、要点を再構成して独自のリライト記事として書く
- 見出しはH2（##）/ H3（###）を使用
- 数値・固有名詞は原典の表記を維持し、推測で書き換えない
- リード文 → 要点 → 背景・市場への含意 → まとめ の構成
- 文末はです・ます調で統一

## SEO/GEO配慮
- 主要キーワード（銘柄名、企業名、トピック名）を見出しに含める
- 「とは」「意味」「影響」などの検索意図を満たす副見出しを1つ含める

## 禁止事項
- 原文の文章の長文引用（30字以上のまま転載しない）
- 情報源のない断定・憶測
- 価格予想・投資推奨（中立的に「市場は〜と受け止めている」程度に留める）
- 1,000字未満の短すぎる記事"""

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            http_client=httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0)),
        )
    return _client


_NON_ASCII_QUOTE = re.compile(r'["“”]')


def _yaml_safe(text: str) -> str:
    return _NON_ASCII_QUOTE.sub("'", text).replace("\\", "／")


def _infer_news_category(item: NewsItem) -> str:
    """ニュースのタイトル・タグから日本語サイト用カテゴリを推定する。"""
    text = (item.title + " " + " ".join(item.tags)).lower()
    if any(k in text for k in ["bitcoin", "btc", "eth", "ethereum", "altcoin",
                                "defi", "nft", "stablecoin", "blockchain",
                                "ビットコイン", "イーサリアム", "暗号資産", "仮想通貨"]):
        return "crypto"
    if any(k in text for k in ["fed", "frb", "gdp", "inflation", "rate",
                                "stock", "fx", "金利", "インフレ", "株価"]):
        return "economics"
    if any(k in text for k in ["election", "tariff", "war", "trump",
                                "選挙", "政府", "規制", "法案"]):
        return "politics"
    return item.category_hint or "crypto"


def _build_user_prompt(item: NewsItem) -> str:
    published = item.published.strftime("%Y-%m-%d %H:%M UTC") if item.published else "不明"
    return f"""下記の海外/国内ニュース（一次情報のサマリー）を元に、日本の投資家向けに日本語の解説記事を書いてください。

## 元ニュース情報
- タイトル: {item.title}
- ソース: {item.source}
- 公開日時: {published}
- URL: {item.link}
- 本文サマリー:
{item.summary}

## 要件
1. **新しいタイトル**を1行目に `# 〜` 形式で書く（元タイトルをそのまま使わず、日本語読者向けにリライト）
2. リード文（120字程度）：何が起きたかを端的に
3. ## 要点
   - 箇条書き3〜4点で要約
4. ## 背景・なぜ重要なのか
   - 業界文脈・関連する過去動向との接続
5. ## 市場への含意
   - 投資家・トレーダーが知るべきポイント（中立的に）
6. ## まとめ
7. ## よくある質問
   - 2問のFAQ。各質問は `### Q1. 質問文` の形式、回答は直後の段落で簡潔に。
   - AI検索エンジン向けに「○○とは」「△△の意味」など検索意図の強い質問を必ず1つ含める。

本文中で **元記事の文章を30字以上連続して転載しない**こと。要点は自分の言葉で再構成してください。"""


def _build_frontmatter(item: NewsItem, title: str, category: str,
                       thumbnail: str = "") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    published_iso = item.published.strftime("%Y-%m-%dT%H:%M:%SZ") if item.published else now
    return f"""---
title: "{_yaml_safe(title)}"
date: "{now}"
published_at: "{published_iso}"
category: "{category}"
source: "{_yaml_safe(item.source)}"
source_url: "{item.link}"
news_id: "{item.id}"
thumbnail: "{thumbnail}"
type: "news"
---

"""


def _extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def generate_news_article(item: NewsItem) -> Optional[Path]:
    """ニュースを日本語のリライト記事として生成し、Markdownで保存する。"""
    client = _get_client()
    category = _infer_news_category(item)

    logger.info("Rewriting news: [%s] %s", item.source, item.title[:60])

    full_text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=3000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": _build_user_prompt(item)}],
    ) as stream:
        for text in stream.text_stream:
            full_text += text
        final = stream.get_final_message()
        logger.info(
            "Usage — input: %d, output: %d, cache_read: %d, cache_write: %d",
            final.usage.input_tokens, final.usage.output_tokens,
            final.usage.cache_read_input_tokens or 0,
            final.usage.cache_creation_input_tokens or 0,
        )

    # 先頭行が `# タイトル` 形式ならフロントマターのタイトルにも反映、本文からは削除
    title = _extract_title(full_text, item.title)
    body = re.sub(r"^\s*#\s.*\n", "", full_text, count=1)

    slug = f"news_{item.id}"
    thumb_path = generate_thumbnail(slug, title, item.summary, category)
    thumbnail_name = thumb_path.name if thumb_path else ""

    # 引用元はfrontmatter (source / source_url) と記事ページのヘッダで明示される
    content = _build_frontmatter(item, title, category, thumbnail_name) + body

    out_path = ARTICLES_DIR / f"{slug}.md"
    out_path.write_text(content, encoding="utf-8")
    logger.info("News article saved → %s", out_path)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from news_scraper import NewsScraper
    items = NewsScraper().fetch(fresh_only=False)
    if items:
        generate_news_article(items[0])
