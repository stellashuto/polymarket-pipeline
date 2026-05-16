"""
Article draft generator.

入力:  Market オブジェクト + チャート画像パス
出力:  output/articles/{condition_id}.md  (フロントマター付きMarkdown)

プロンプトキャッシングを有効化しているため、同一システムプロンプトの
繰り返し呼び出しは約90%コスト削減になります。
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY, ARTICLES_DIR
from polymarket_scraper import Market
from thumbnail_generator import generate_thumbnail

logger = logging.getLogger(__name__)

# 記事生成に使用するモデル（コスト・品質バランスでSonnet推奨）
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """あなたはPolymarket（予測市場）専門の日本語金融ライターです。
エンジニア兼データアナリストとしての実取引経験（6,000 USD規模）をもとに、
読者が実際に活用できる市場分析記事を書きます。

## 執筆スタイル
- 見出しはH2（##）/ H3（###）を使用
- 数値やオッズは具体的に記載（例：「YESオッズが62% → 71%に上昇」）
- 一次情報を強調：「Polymarketの出来高データによると」などの表現を使う
- SEO対策として「Polymarket 使い方」「予測市場 オッズ」などのキーワードを自然に含める
- 末尾の「よくある質問」は読者向けに人間が読めるQ&A形式で書く（JSON や code block で囲まない）

## 禁止事項
- 「〜かもしれません」など断定を避ける曖昧表現の多用
- 情報源のない断言
- 1,500字未満の短すぎる記事
- 本文中に JSON や `<script>` タグ、コードブロック内のメタデータを書くこと（構造化データはサイト側で別途生成する）"""

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        import httpx
        _client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            http_client=httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0)),
        )
    return _client


def _build_market_context(market: Market) -> str:
    """マーケットデータをプロンプト用テキストに変換する。"""
    lines = [
        f"## マーケット情報",
        f"- 質問: {market.question}",
        f"- カテゴリ: {market.category}",
        f"- 終了日: {market.end_date}",
        f"- 総出来高: ${market.volume:,.0f} USD",
        "",
        "## 各結果のオッズ（過去7日間）",
    ]

    for tok in market.tokens:
        if not tok.history:
            continue
        prices = [p["p"] for p in tok.history]
        latest = prices[-1] * 100
        low    = min(prices) * 100
        high   = max(prices) * 100
        # 単純移動平均（3点）
        trend_pts = prices[-3:] if len(prices) >= 3 else prices
        trend = (trend_pts[-1] - trend_pts[0]) * 100

        lines += [
            f"### {tok.outcome}",
            f"  - 現在: {latest:.1f}%",
            f"  - 7日間レンジ: {low:.1f}% ～ {high:.1f}%",
            f"  - 直近トレンド: {'↑' if trend > 0 else '↓'} {abs(trend):.1f}pt",
        ]

    return "\n".join(lines)


def _build_frontmatter(market: Market, thumbnail: str = "") -> str:
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""---
title: "{market.question}"
date: "{now}"
category: "{market.category}"
volume_usd: {market.volume:.0f}
condition_id: "{market.condition_id}"
thumbnail: "{thumbnail}"
type: "market"
---

"""


def _build_news_context(related_news: list) -> str:
    """関連ニュースをプロンプト用テキストに変換する。"""
    if not related_news:
        return ""
    lines = ["", "## 関連ニュース（直近の報道。引用時は必ずソース名を明記すること）"]
    for n in related_news[:5]:
        published = n.published.strftime("%Y-%m-%d") if n.published else "n/a"
        lines.append(f"- [{n.source} / {published}] {n.title}")
        if n.summary:
            lines.append(f"  - 要旨: {n.summary[:200]}")
        lines.append(f"  - URL: {n.link}")
    return "\n".join(lines)


def generate_article(market: Market, related_news: list | None = None) -> Path:
    """
    Claudeを使ってPolymarket市況解説記事を生成し、Markdownファイルとして保存する。

    related_news が与えられた場合は記事中で関連報道として引用する。
    """
    client = _get_client()
    market_context = _build_market_context(market)
    news_context = _build_news_context(related_news or [])

    news_instruction = ""
    if related_news:
        news_instruction = (
            "\n本文中で **関連ニュース** のうち少なくとも1〜2件を引用し、"
            "「(出典: ソース名)」の形でソース名を明記してください。"
            "Polymarketのオッズ変動と報道内容を結びつけて論じてください。"
        )

    user_prompt = f"""{market_context}
{news_context}

上記のPolymarketデータ{('と関連ニュース' if related_news else '')}をもとに、
以下の構成で日本語の市況解説記事を執筆してください。

1. **リード文**（150字程度）：イベントの概要とオッズの現状を要約
2. **背景・ファンダメンタルズ**：このイベントが注目される理由
3. **オッズ推移の分析**：7日間の変動を具体的な数値で解説
4. **関連ニュースが示す市場文脈**：直近の報道からの示唆（関連ニュースがある場合のみ）
5. **流動性・出来高の所感**：市場の信頼性について（実取引者の視点を交えて）
6. **今後の注目ポイント**：価格変動のトリガーになりうる材料
7. **まとめ**
8. **よくある質問**（3問。各質問は `### Q1. 質問文` の形式、答えは直後の段落で簡潔に。AI検索エンジン向けに「Polymarketとは」「予測市場の使い方」など検索意図の強い質問を含める）
{news_instruction}"""

    logger.info("Generating article for: %s (news: %d)",
                market.question[:60], len(related_news or []))

    full_text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            full_text += text

        final = stream.get_final_message()
        cache_read   = final.usage.cache_read_input_tokens or 0
        cache_create = final.usage.cache_creation_input_tokens or 0
        logger.info(
            "Usage — input: %d, output: %d, cache_read: %d, cache_write: %d",
            final.usage.input_tokens,
            final.usage.output_tokens,
            cache_read,
            cache_create,
        )

    # サムネ生成（質問文 + カテゴリから）
    thumb_path = generate_thumbnail(
        slug=market.condition_id,
        title=market.question,
        summary=f"Polymarketの予測市場。出来高 ${market.volume:,.0f} USD。{market.category}カテゴリ。",
        category=market.category,
    )
    thumbnail_name = thumb_path.name if thumb_path else ""

    # フロントマター + 本文
    content = _build_frontmatter(market, thumbnail_name) + full_text

    # 関連ニュースを参考文献として末尾に列挙
    if related_news:
        refs = ["\n\n---\n\n## 参考: 関連ニュース\n"]
        for n in related_news[:5]:
            refs.append(f"- [{n.title}]({n.link}) — {n.source}")
        content += "\n".join(refs) + "\n"

    out_path = ARTICLES_DIR / f"{market.condition_id}.md"
    out_path.write_text(content, encoding="utf-8")
    logger.info("Article saved → %s", out_path)
    return out_path


if __name__ == "__main__":
    import time
    import logging
    from polymarket_scraper import TokenHistory, Market

    logging.basicConfig(level=logging.INFO)

    # ダミーデータで動作確認
    now = int(time.time())
    dummy_history = [
        {"t": now - (7 - i) * 86400, "p": 0.45 + i * 0.03}
        for i in range(8)
    ]
    market = Market(
        condition_id="testdummy",
        question="Will BTC exceed $100,000 by end of 2025?",
        category="crypto",
        end_date="2025-12-31",
        volume=1_500_000,
        tokens=[
            TokenHistory("tok_yes", "Yes", dummy_history),
            TokenHistory("tok_no",  "No",  [{"t": h["t"], "p": 1 - h["p"]} for h in dummy_history]),
        ],
    )

    path = generate_article(market)
    print(f"Generated: {path}")
