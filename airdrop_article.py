"""
エアドロップ記事ジェネレータ。

キュレート済みトピックリスト (airdrop_topics.py) からまだ書いていないものを
1つ選び、初心者・中級者のエアドロップハンター向けの記事を生成する。

プロジェクト単位の重複防止のため、frontmatterに airdrop_slug を保存し、
過去全期間に同じslugの記事があればスキップする。
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
from airdrop_topics import ALL_TOPICS, AirdropTopic
from news_scraper import NewsScraper, NewsItem
from thumbnail_generator import generate_thumbnail
from translator import translate_title
from tweet_generator import compose_tweet

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# Web検索ツール定義（Anthropic Web Search beta）
# 1リクエストあたり最大3検索 → コストと品質のバランス
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
}

SYSTEM_PROMPT = """あなたは暗号資産業界で 5年以上のエアドロップハント経験を持つ
日本語ライターです。読者は初心者〜中級者の個人投資家・エアドロップハンター層。

## 必須：最新情報の確認（極めて重要）
- 記事を書く前に、必ず `web_search` ツールで対象トピックの **現在（直近1〜3ヶ月）の状況** を検索すること
- 「○○ airdrop 2026」「○○ testnet status」「○○ token launch」のような英語クエリも併用
- 古い知識（2024年・2025年の情報）をそのまま書かない。プログラム終了/メインネット移行/トークン配布済みなど **直近の変化を必ず反映**
- 検索結果が日付的に古ければ、複数回検索して最新ソースを確認

## トーン
- 経験者として、実際にやってみた人の視点で書く（「筆者の経験では」「実際に複数アドレスで試した結果」など）
- 断定的・短文を交ぜる。曖昧な「〜可能性があります」を多用しない
- 業界スラング・略語は初出時に簡潔に解説（例: 「LRT（リキッドリステーキングトークン）」）
- 「皆さん」「いかがでしょうか」「ぜひ参考に」など読者呼びかけ・締め定型句は禁止
- AIっぽいテンプレ「まず〜、次に〜、最後に〜」の連発を避ける

## 構造
- 冒頭に `## ポイント` セクション（3〜4個の箇条書きで結論先出し、AI検索引用用）
- 中身は記事内容に応じて柔軟に。テンプレ化しない
- 末尾に `## よくある質問` を3問（`### Q1. 質問文` 形式、JSON禁止）
- 1,800字以上の充実した本文

## 内容方針
- **断定的な期待値発言は避ける**：「○○ドル獲得できる」は禁止、代わりに「過去事例では1ウォレット数百〜数千ドル相当の配布があった」など事実ベース
- **リスク明示**：詐欺・Sybil検知・税金（日本）への言及を必ずどこかに含める
- **公式情報優先**：URLを記載する場合は公式のみ。怪しいサイトは絶対に薦めない
- **税金注意**：日本の税制では受領時に時価で雑所得課税のリスクあり、と必ず触れる
- **アクションステップ**：具体的に「どこから何をするか」が読者にわかる構成
- **時系列の明示**：「2026年5月時点で〜」のように、いつの時点の情報かを明示する

## 禁止
- 投資推奨や絶対的な利益保証
- 1,500字未満の浅い記事
- 「これは投資助言ではありません」のような言い訳テンプレ（disclaimerはサイト全体で出すので不要）
- 本文中にJSON・コードブロック内のメタデータ
- **Web検索を使わずに書く**（古い情報のまま書くのは絶対NG）"""


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
    """既に記事が存在するエアドロップトピックのslug集合を返す。"""
    slugs: set[str] = set()
    if not ARTICLES_DIR.exists():
        return slugs
    for md in ARTICLES_DIR.glob("*.md"):
        try:
            head = md.read_text(encoding="utf-8")[:1500]
        except OSError:
            continue
        m = re.search(r'^airdrop_slug:\s*"?(.+?)"?\s*$', head, re.MULTILINE)
        if m:
            slugs.add(m.group(1).strip())
    return slugs


def _pick_topic() -> Optional[AirdropTopic]:
    """まだ書いていないトピックをランダムに1つ選ぶ。"""
    covered = _existing_slugs()
    candidates = [t for t in ALL_TOPICS if t.slug not in covered]
    if not candidates:
        logger.warning("All airdrop topics covered (%d). Nothing to write.", len(ALL_TOPICS))
        return None
    return random.choice(candidates)


def _fetch_recent_news_for_topic(topic: AirdropTopic, news_items: list[NewsItem],
                                  max_results: int = 5) -> list[NewsItem]:
    """既取得のニュース一覧から、トピックに関連する直近記事を返す。

    プロジェクト名 + search_keywords で大文字小文字を無視してマッチング。
    新しい順に最大 max_results 件返す。
    """
    if topic.kind != "project":
        return []
    needles = [topic.project_name.lower()]
    if topic.search_keywords:
        needles.extend(k.lower() for k in topic.search_keywords)
    needles = [n for n in needles if n and len(n) >= 3]
    if not needles:
        return []

    matched: list[NewsItem] = []
    for item in news_items:
        haystack = (item.title + " " + item.summary).lower()
        if any(n in haystack for n in needles):
            matched.append(item)

    # 公開日新しい順
    matched.sort(
        key=lambda n: n.published.timestamp() if n.published else 0,
        reverse=True,
    )
    return matched[:max_results]


def _format_news_for_prompt(news: list[NewsItem]) -> str:
    if not news:
        return ""
    lines = ["", "## 直近のニュース動向（過去 1〜2 週間程度）",
             "下記の報道を参考に、プロジェクトの「現在の状況」を記事に反映してください。",
             "ただし長文の転載は避け、要点だけ自分の言葉で再構成すること。", ""]
    for n in news:
        date = n.published.strftime("%Y-%m-%d") if n.published else "n/a"
        lines.append(f"### [{date}] {n.source}")
        lines.append(f"タイトル: {n.title}")
        if n.summary:
            lines.append(f"要旨: {n.summary[:400]}")
        lines.append(f"URL: {n.link}")
        lines.append("")
    return "\n".join(lines)


def _build_user_prompt(topic: AirdropTopic, recent_news: list[NewsItem]) -> str:
    kind_jp = "プロジェクト解説" if topic.kind == "project" else "汎用ガイド"
    project_block = ""
    if topic.kind == "project":
        project_block = f"""
## 取り上げるプロジェクト
- 名称: {topic.project_name}
- 公式URL: {topic.project_url}
- プロジェクト概要（参考、古い情報の可能性あり）: {topic.summary}

注: 上記URL以外の外部URLは記事に含めないでください。怪しいサイトを誘導しないこと。
"""
    else:
        project_block = f"""
## ガイドのテーマ
{topic.summary}
"""

    news_block = _format_news_for_prompt(recent_news)
    news_instruction = ""
    if recent_news:
        news_instruction = (
            "\n**重要**: 上記の直近ニュースを記事に必ず反映してください。"
            "「2025年〜時点の状況」「直近の報道では〜」のような時系列言及で、"
            "古い知識ではなく最新の動向を中心に解説すること。"
            "ニュースを引用する場合は「（出典: ソース名）」を文中に明記。\n"
        )

    search_instructions = ""
    if topic.kind == "project":
        search_instructions = f"""
## ⚠️ 必須の事前リサーチ（記事を書く前に必ず実行）
`web_search` ツールを使って、以下を **必ず検索** してください（最低2回、できれば3回）：
1. 「{topic.project_name} airdrop 2026 latest」または「{topic.project_name} token launch」
2. 「{topic.project_name} mainnet status」または「{topic.project_name} points program 2026」
3. （必要に応じて）プロジェクトの現状確認のための追加検索

検索結果から **「今この瞬間の状況」** を把握し、以下を判定して反映：
- 既にトークン配布済みか、まだか
- testnetフェーズか、mainnet移行後か
- ポイントプログラム継続中か、終了済みか
- 直近の重要な発表・変更

古い知識（2024〜2025年の情報）をそのまま書くのは絶対NG。
"""
    else:
        search_instructions = f"""
## ⚠️ 必須の事前リサーチ
`web_search` ツールを使って、このガイドの内容に関連する **2026年現在の状況** を必ず確認してください。
特に以下のような検索を1〜2回実行：
- 「airdrop hunting 2026 best strategies」「current testnet airdrops 2026」
- 日本に固有のトピック（税金等）の場合は「暗号資産 税金 2026 改正」など
"""

    return f"""以下のテーマで日本語のエアドロップ解説記事を書いてください（{kind_jp}）。
{search_instructions}
タイトルのヒント: {topic.title_hint}
読者層: {"初心者" if topic.audience == "beginner" else "中級者（エアドロップハンター）"}
{project_block}{news_block}{news_instruction}
## 記事の構成
0. **1行目に `# 日本語タイトル`** （タイトルヒントを元にキャッチーな日本語タイトルに、可能なら検索で得た最新の数値や固有名詞を含める）
1. `## ポイント` — 3〜4個の結論先出し箇条書き（時系列「2026年5月時点で〜」を明示）
2. リード文（120字程度）
3. メインコンテンツ（複数のH2で構成、内容に応じて柔軟に）
{"4. **「最新動向」セクション** — Web検索とRSSニュースを基にプロジェクトの現状を3〜5段落で解説（情報源URL記載）" if topic.kind == "project" else ""}
5. リスク・注意点（詐欺・Sybil・税金など該当するもの）
6. まとめ
7. `## よくある質問` — 3問（`### Q1. 質問文` 形式）

人間の経験者として書いてください。AIっぽいテンプレ感を出さないこと。"""


def _build_frontmatter(topic: AirdropTopic, title: str, title_en: str,
                       thumbnail: str, x_post: str = "") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_title = title.replace('"', "'")
    safe_title_en = (title_en or "").replace('"', "'")
    # ツイート本文はYAMLのブロックスカラー記法で保存（改行を保つ）
    x_post_yaml = ""
    if x_post:
        indented = "\n".join("  " + line for line in x_post.split("\n"))
        x_post_yaml = f"x_post: |\n{indented}\n"
    return f"""---
title: "{safe_title}"
title_en: "{safe_title_en}"
date: "{now}"
category: "airdrop"
categories:
  - airdrop
  - crypto
airdrop_slug: "{topic.slug}"
airdrop_kind: "{topic.kind}"
audience: "{topic.audience}"
thumbnail: "{thumbnail}"
type: "airdrop"
{x_post_yaml}---

"""


def generate_airdrop_article(topic: Optional[AirdropTopic] = None,
                              news_cache: Optional[list[NewsItem]] = None) -> Optional[Path]:
    """エアドロップ記事を生成して保存する。topicを指定しない場合は未掲載から自動選択。

    news_cache: 事前取得済みのニュースリストを渡すと再フェッチを避けられる
                （main.pyから複数回呼ぶ際にAPI節約用）
    """
    if topic is None:
        topic = _pick_topic()
    if topic is None:
        return None

    logger.info("Generating airdrop article: %s (%s)", topic.slug, topic.kind)

    # プロジェクト解説の場合、関連ニュースを取得
    recent_news: list[NewsItem] = []
    if topic.kind == "project":
        if news_cache is None:
            try:
                news_cache = NewsScraper().fetch(fresh_only=False)
            except Exception as e:
                logger.warning("News fetch failed for airdrop article: %s", e)
                news_cache = []
        recent_news = _fetch_recent_news_for_topic(topic, news_cache)
        if recent_news:
            logger.info("  Found %d recent news items for %s", len(recent_news), topic.project_name)
            for n in recent_news[:3]:
                logger.info("    - [%s] %s", n.source, n.title[:60])
        else:
            logger.info("  No recent news found for %s; writing evergreen content", topic.project_name)

    client = _get_client()
    full_text = ""
    with client.messages.stream(
        model=MODEL,
        # Web検索ツールの結果がoutputに含まれるため、4096では本文が切れる。
        # Sonnet 4.6の上限近くまで取って末尾切れを防ぐ。
        max_tokens=12000,
        tools=[WEB_SEARCH_TOOL],
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": _build_user_prompt(topic, recent_news)}],
    ) as stream:
        for text in stream.text_stream:
            full_text += text
        final = stream.get_final_message()
        logger.info(
            "Usage — input: %d, output: %d, stop: %s",
            final.usage.input_tokens, final.usage.output_tokens,
            final.stop_reason,
        )
        if final.stop_reason == "max_tokens":
            logger.warning("⚠ Article was truncated at max_tokens. Consider raising the limit.")

    # `# 日本語タイトル` を本文中から探す（Web検索使用時、リサーチ過程の前置きが
    # 入ることがあるため search で柔軟にマッチ。タイトル行以前は破棄。）
    m = re.search(r"(?:^|\n)#\s+(.+?)\s*\n", full_text)
    if m:
        ja_title = m.group(1).strip()
        body = full_text[m.end():]
    else:
        ja_title = topic.title_hint
        body = full_text
    # 本文先頭の連続する区切り線・空行を整理
    body = re.sub(r"^(\s*---\s*\n)+", "", body)

    # サムネ生成
    summary_for_thumb = (topic.summary[:300] +
                        f" 読者層: {topic.audience}向けのエアドロップ解説")
    slug_for_files = f"airdrop_{topic.slug}"
    thumb_path = generate_thumbnail(
        slug=slug_for_files,
        title=ja_title,
        summary=summary_for_thumb,
        category="airdrop",
    )
    thumbnail_name = thumb_path.name if thumb_path else ""

    # 英語タイトル
    title_en = translate_title(ja_title)
    if title_en:
        logger.info("EN title: %s", title_en[:80])

    # X 投稿用ツイート文を生成
    extra_tags = ["エアドロップ", "Airdrop"]
    if topic.kind == "project" and topic.project_name:
        extra_tags.append(topic.project_name.replace(" ", ""))
    x_post = compose_tweet(
        title=ja_title,
        body_excerpt=body,
        category="airdrop",
        extra_hashtags=extra_tags,
    )
    if x_post:
        logger.info("X post (%d chars):\n%s", len(x_post), x_post[:200])

    content = _build_frontmatter(topic, ja_title, title_en, thumbnail_name, x_post) + body

    out_path = ARTICLES_DIR / f"{slug_for_files}.md"
    out_path.write_text(content, encoding="utf-8")
    logger.info("Airdrop article saved → %s", out_path)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    generate_airdrop_article()
