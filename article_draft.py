"""
Article draft generator.

入力:  Market オブジェクト + チャート画像パス
出力:  output/articles/{condition_id}.md  (フロントマター付きMarkdown)

プロンプトキャッシングを有効化しているため、同一システムプロンプトの
繰り返し呼び出しは約90%コスト削減になります。
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import anthropic

import time

from config import ANTHROPIC_API_KEY, ARTICLES_DIR
from polymarket_scraper import Market
from thumbnail_generator import generate_thumbnail
from dedupe import find_similar_article

logger = logging.getLogger(__name__)

# 記事生成に使用するモデル（コスト・品質バランスでSonnet推奨）
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """あなたは Polymarket（予測市場）に詳しい日本語の金融ライターです。
読者は仮想通貨を実際にトレードしている投資家・トレーダー層で、ありがちな
「AIが書いたっぽい」テンプレ記事はすぐ見抜きます。**人間のライターとして書く**。

## トーンと語り口
- **短文と長文を交ぜる**。「YESオッズは22.9%。市場は冷ややかだ。」のような短い断定を時々混ぜる
- **断定する**。「〜と考えられます」「〜可能性があります」を多用しない。データから言えることは言い切る
- **書き手の視点を出す**。「筆者の見立てでは」「個人的にはここを買い場と見ている」など意見を入れる
- **業界スラングを自然に使う**。「板が薄い」「玉が動いた」「ローリングする」など
- **冗長な接続詞は削る**。「したがって」「このように」「すなわち」の連発は避ける
- 同じ言い回し（例「Polymarketのデータによると」）を1記事内で2回以上使わない

## 記事構造
- 冒頭は必ず `## 要点（TL;DR）` を3〜4個の箇条書きで（AI検索エンジン引用用）
- それ以外のセクション見出しは記事内容に合わせて自由に決める（テンプレ感回避）
- 末尾FAQは `### Q1. 質問文` → 直後の段落で回答 形式（JSON・コードブロック禁止）

## データの扱い
- 数値・オッズは具体的に（「YES 62% → 71%」のように矢印で推移を示す）
- 出来高は文脈付きで（「出来高2,700万ドル＝中規模イベント級」のように相場感を出す）

## 禁止
- 1,500字未満の短すぎる記事
- 本文中に JSON や `<script>` タグ、構造化データを書く（サイト側で別途生成）
- 「皆さんは〜思いませんか？」「いかがでしょうか？」など読者への呼びかけ濫用
- 「ぜひ参考にしてみてください」「投資は自己責任で」など締めの定型句
- AIっぽい三段論法（「まず〜、次に〜、最後に〜」の連発）"""

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


def _build_frontmatter(market: Market, title: str, thumbnail: str = "") -> str:
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_title = title.replace('"', "'")
    safe_q_en  = market.question.replace('"', "'")

    # チャート描画用に各トークンの履歴をコンパクトなJSON配列で書き出す
    # [[unix_ts, price], ...] 形式（小数4桁・整数Unix秒）
    history_lines = []
    for tok in market.tokens:
        if not tok.history:
            continue
        compact = "[" + ",".join(
            f"[{int(p['t'])},{float(p['p']):.4f}]" for p in tok.history
        ) + "]"
        safe_outcome = (tok.outcome or "").replace('"', "'")
        history_lines.append(f'  - outcome: "{safe_outcome}"')
        history_lines.append(f'    history: \'{compact}\'')

    history_block = "\n".join(history_lines) if history_lines else ""
    history_yaml = f"odds_history:\n{history_block}\n" if history_block else ""

    return f"""---
title: "{safe_title}"
question_en: "{safe_q_en}"
date: "{now}"
category: "{market.category}"
volume_usd: {market.volume:.0f}
condition_id: "{market.condition_id}"
polymarket_slug: "{market.slug}"
polymarket_url: "{market.polymarket_url}"
thumbnail: "{thumbnail}"
type: "market"
{history_yaml}---

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


def generate_article(market: Market, related_news: list | None = None,
                    skip_if_recent_hours: int = 18) -> Path | None:
    """
    Claudeを使ってPolymarket市況解説記事を生成し、Markdownファイルとして保存する。

    related_news が与えられた場合は記事中で関連報道として引用する。

    skip_if_recent_hours 以内に同じマーケットを生成済みなら再生成しない
    （朝・昼・夜の3回スケジュールで同じトップマーケットが繰り返し記事化されるのを防ぐ）。
    """
    out_path = ARTICLES_DIR / f"{market.condition_id}.md"
    if out_path.exists() and skip_if_recent_hours > 0:
        age = time.time() - out_path.stat().st_mtime
        if age < skip_if_recent_hours * 3600:
            logger.info("Skipping recent market (age %.1fh): %s",
                        age / 3600, market.question[:60])
            return None

    # 同じトピックの記事（別マーケット）が直近に生成されていればスキップ
    similar = find_similar_article(market.question, hours=72, threshold=0.45,
                                   skip_path=out_path)
    if similar:
        logger.info("Skipping similar-topic market (similar to %s): %s",
                    similar.name, market.question[:60])
        return None

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

0. **# 日本語タイトル**：1行目に `# 〜` 形式で記事のタイトルを書く
   - 英語の質問文をそのまま使わず、日本語読者向けにリライト
   - 主要な数値（オッズ%）か固有名詞を含め、検索意図に合うキャッチーな見出しに
   - 例: 「フランスの2026 W杯優勝オッズはYES 17%──Polymarket最新分析」
1. **## 要点（TL;DR）**：3〜4個の箇条書きで「現在のオッズ・直近トレンド・注目すべき材料」を結論先出し（AI検索エンジンが引用しやすい形）
2. **リード文**（150字程度）：イベントの概要とオッズの現状を要約
3. **背景・ファンダメンタルズ**：このイベントが注目される理由
4. **オッズ推移の分析**：以下の専用フォーマットで書くこと
   - 冒頭に「**オッズスナップショット**」という段落を置き、以下の箇条書き形式で数値を明示：
     - 現在のオッズ: YES XX.X% / NO XX.X%
     - 7日前のオッズ: YES XX.X%（参照値）
     - 期間内ピーク → ボトム: YES XX.X% → XX.X%
     - 方向性: 7日前 XX.X% → ピーク XX.X% → 現在 XX.X%（変動 ±X.Xpt）
   - その後にプロセ解説を続ける
   - 数値表を使う場合は markdown テーブルではなく上記の箇条書きを優先（モバイルでの見やすさのため）
5. **関連ニュースが示す市場文脈**：直近の報道からの示唆（関連ニュースがある場合のみ）
6. **流動性・出来高の所感**：市場の信頼性について（実取引者の視点を交えて）
7. **今後の注目ポイント**：価格変動のトリガーになりうる材料
8. **まとめ**
9. **よくある質問**（3問。各質問は `### Q1. 質問文` の形式、答えは直後の段落で簡潔に。AI検索エンジン向けに「Polymarketとは」「予測市場の使い方」など検索意図の強い質問を含める）
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

    # 先頭行の `# 日本語タイトル` を抽出し、本文からは除去
    title_match = re.match(r"^\s*#\s+(.+?)\s*\n", full_text)
    if title_match:
        ja_title = title_match.group(1).strip()
        body = full_text[title_match.end():]
    else:
        # Claudeが見出しを書かなかった場合は英語タイトルにフォールバック
        ja_title = market.question
        body = full_text

    # サムネ生成（日本語タイトル + カテゴリから）
    thumb_path = generate_thumbnail(
        slug=market.condition_id,
        title=ja_title,
        summary=f"Polymarketの予測市場。出来高 ${market.volume:,.0f} USD。{market.category}カテゴリ。",
        category=market.category,
    )
    thumbnail_name = thumb_path.name if thumb_path else ""

    # フロントマター + 本文（タイトル行は除去済み）
    content = _build_frontmatter(market, ja_title, thumbnail_name) + body

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
