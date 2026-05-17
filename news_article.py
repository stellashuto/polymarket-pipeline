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

from config import ANTHROPIC_API_KEY, ARTICLES_DIR, ENGLISH_SOURCES
from news_scraper import NewsItem
from thumbnail_generator import generate_thumbnail
from dedupe import find_similar_article
from translator import translate_title

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """あなたは仮想通貨・金融分野で 5年以上の現場経験を持つ日本語ニュースライターです。
読者は投資家・トレーダー・Web3関係者で、テンプレ的な「AIライターが書いた感」のある
文章を即見抜きます。**人間のライターとして書いてください**。

## トーンと語り口
- **断定的に書く**。「〜と考えられます」「〜可能性があります」など曖昧表現を多用しない
- **短文と長文を混ぜる**。「BTCは下げ止まらない。市場は怯えている。」のような短文を時々挟む
- **書き手の視点を出す**。「個人的には〜」「筆者は〜とみている」を時に入れる
- **業界スラングを自然に**。「板」「玉」「踏み」「ロング」「ショート」「半減期」など
- **冗長な接続詞を削る**。「したがって」「このように」「すなわち」の連発を避ける
- 同じフレーズを1記事内で繰り返さない

## 構造
- 必ず冒頭に `## ポイント` を3〜4個の箇条書きで（固有名詞・数値必須、結論先出し）
- それ以外のセクション見出しは記事内容に合わせて自由に。テンプレ化しない
- 末尾FAQは `### Q1. 質問文` → 直後の段落で回答（JSON禁止）

## 原典の扱い
- 原文を**逐語引用しない**（30字以上連続して転載しない）
- 数値・固有名詞は原典の表記を維持
- 引用元は記事末尾の「出典」セクションでサイト側が自動表示するので、本文中で「○○によると」を多用しない

## 禁止
- 「皆さんは〜思いませんか？」「いかがでしょうか？」など読者への呼びかけ濫用
- 「ぜひ参考にしてください」「投資は自己責任で」など定型句
- 1,000字未満の短すぎる記事
- 価格予想・投資推奨（市場の解釈に留める）"""

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
    """ニュースのタイトル・タグから日本語サイト用カテゴリを推定する。
    優先順位: politics > economics > crypto
    (規制・政策ニュースは crypto より politics として分類した方が読者の関心軸に合う)
    """
    text = (item.title + " " + " ".join(item.tags)).lower()

    # 政治・規制・地政学（最優先）
    politics_kw = [
        "election", "tariff", "sanction", "war", "military", "treaty",
        "trump", "biden", "congress", "senate", "regulator", "regulation",
        "sec ", " sec,", "cftc", "lawmaker", "bill ", "vote ", "policy",
        "white house", "executive order", "supreme court",
        "選挙", "政府", "規制", "法案", "条約", "首脳",
    ]
    if any(k in text for k in politics_kw):
        return "politics"

    # 経済・マクロ（次点）
    economics_kw = [
        "fed ", "federal reserve", "frb", "fomc", "gdp", "inflation",
        "interest rate", "rate cut", "rate hike", "recession", "unemployment",
        "stock", "s&p", "nasdaq", "fx", "yen", "dollar", "treasury",
        "金利", "インフレ", "株価", "為替", "景気",
    ]
    if any(k in text for k in economics_kw):
        return "economics"

    # 仮想通貨
    crypto_kw = [
        "bitcoin", "btc", "eth", "ethereum", "altcoin", "solana", "sol ",
        "defi", "nft", "stablecoin", "blockchain", "ripple", "xrp",
        "web3", "dao", "token", "mining", "etf",
        "ビットコイン", "イーサリアム", "暗号資産", "仮想通貨", "ステーブルコイン",
    ]
    if any(k in text for k in crypto_kw):
        return "crypto"

    return item.category_hint or "crypto"


def _build_user_prompt(item: NewsItem) -> str:
    from config import ENGLISH_SOURCES
    published = item.published.strftime("%Y-%m-%d %H:%M UTC") if item.published else "不明"
    is_english = item.source in ENGLISH_SOURCES
    translation_note = ""
    if is_english:
        translation_note = (
            "\n## 重要: 翻訳に関する指示\n"
            "- 元記事は英語です。**完全に日本語にローカライズ**してください\n"
            "- 専門用語は日本の読者向けに分かりやすく言い換える（例: `bill` → 法案、`Senator` → 上院議員）\n"
            "- 数値・固有名詞は維持しつつ、文章構造は日本語として自然に再構成する\n"
            "- 英単語を残す場合は初出時に括弧で日本語訳を添える（例: `CFTC（米商品先物取引委員会）`）\n"
        )
    return f"""下記の海外/国内ニュース（一次情報のサマリー）を元に、日本の投資家向けに日本語の解説記事を書いてください。
{translation_note}
## 元ニュース情報
- タイトル: {item.title}
- ソース: {item.source}
- 公開日時: {published}
- URL: {item.link}
- 本文サマリー:
{item.summary}

## 要件
1. **新しいタイトル**を1行目に `# 〜` 形式で書く（元タイトルをそのまま使わず、日本語読者向けにリライト）
2. ## ポイント
   - 箇条書き3〜4点で結論を先出し（AI検索エンジンが引用しやすい形）。固有名詞・数値を必ず含めること
3. リード文（120字程度）：何が起きたかを端的に
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
                       thumbnail: str = "", title_en: str = "") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    published_iso = item.published.strftime("%Y-%m-%dT%H:%M:%SZ") if item.published else now
    return f"""---
title: "{_yaml_safe(title)}"
title_en: "{_yaml_safe(title_en)}"
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

    # 過去72時間以内に類似タイトルの記事があれば、別ソースからの同一事件報道と判断してスキップ
    similar = find_similar_article(item.title, hours=72, threshold=0.45)
    if similar:
        logger.info("Skipping duplicate news (similar to %s): %s",
                    similar.name, item.title[:60])
        return None

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

    # 英語タイトル: 英語ソースは元タイトルをそのまま使う、それ以外は翻訳
    if item.source in ENGLISH_SOURCES:
        title_en = item.title
    else:
        title_en = translate_title(title)
    if title_en:
        logger.info("EN title: %s", title_en[:80])

    # 引用元はfrontmatter (source / source_url) と記事ページのヘッダで明示される
    content = _build_frontmatter(item, title, category, thumbnail_name, title_en) + body

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
