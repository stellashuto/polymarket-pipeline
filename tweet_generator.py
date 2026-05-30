"""
記事から X 投稿用ツイート文を生成する。

- Claude Sonnet 4.6 で「キャッチーで具体的・本文を要約しすぎない」短文を生成
- 1ツイートは emoji+見出し→キーインサイト→ハッシュタグ→（URLは別途追加）構成
- URL（23字短縮）込みで 280 字以内に収める
- frontmatter の x_post フィールドに保存しておけば、後から手動コピペや
  x_publisher.py から再利用できる
"""

import logging
import re
from typing import Optional

import anthropic
import httpx

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
URL_RESERVED_LEN = 24      # t.co の23字 + 改行

_SYSTEM = """あなたは仮想通貨メディアのSNS編集者です。
記事から、X（Twitter）で実際にクリックされる "短く・刺さる" 投稿文を作ります。

## 必須要件
- 出力は **そのまま X に貼り付けられる完成テキスト** のみ（解説・引用符・補足禁止）
- 1行目: 1個の絵文字 + キャッチコピー（記事の核となる「動き」「数値」「変化」を端的に）
- 2〜4行目: 記事から拾った具体的な数値・固有名詞・直近のニュースを反映
- 最後: 半角スペース区切りで3〜4個のハッシュタグ（記事固有のキーワード優先）

## 文字数制限
- 末尾に URL（23字相当）が自動付加されるため、本文+ハッシュタグの合計は **240字以内**
- 改行は読みやすさのため2〜3箇所だけ使う

## トーン
- AIっぽいテンプレ（「皆さん」「ご紹介します」「気になる方は…」など）禁止
- 業界スラング歓迎（Sybil・ロックアップ・板・玉・PoS など）
- 「！」連打や煽りは禁止。落ち着いた事実ベース
- 投資勧誘・誇大表現禁止

## 出力例
🎁 Hyperliquid HYPE が最高値62.18ドル更新

グレースケールがHYPE現物ETF修正申請を再提出。
機関資金の流入加速で、Spot取引のポイント獲得は今が分岐点。

#エアドロップ #Hyperliquid #HYPE"""


_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            http_client=httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)),
        )
    return _client


def _visible_len(text: str) -> int:
    """X短縮URL補正込みの実効文字数（URLは固定23字としてカウント）。"""
    urls = re.findall(r"https?://\S+", text)
    return len(text) - sum(len(u) for u in urls) + 23 * len(urls)


def compose_tweet(
    title: str,
    body_excerpt: str,
    category: str,
    extra_hashtags: list[str] | None = None,
) -> str:
    """記事の要約として 240字以内のツイート文を生成して返す。"""
    extra = (
        f"\n\n## 候補ハッシュタグ\n推奨タグ: {' '.join('#' + h for h in extra_hashtags)}\n"
        f"（これを必ず使う必要はない。記事内容に合うものを選択せよ）"
        if extra_hashtags else ""
    )

    user_prompt = f"""## 記事タイトル
{title}

## 記事冒頭（800字まで）
{body_excerpt[:800]}

## カテゴリ
{category}
{extra}

上記をもとに、X 投稿用の完成テキストを出力してください。URL は付けないでください（後で自動付加されます）。
"""

    try:
        msg = _get_client().messages.create(
            model=MODEL,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        text = text.strip('"\'「」 ')
        # Claudeが先頭に「以下が」のような前置きを付けたら剥がす
        text = re.sub(r"^[^📊📈📰🎁🏛️🏆🎬🔥⚡💡🪙✨🌐🎯📍🔔]*?(?=[📊📈📰🎁🏛️🏆🎬🔥⚡💡🪙✨🌐🎯📍🔔])", "", text, count=1)

        # 240字以内に収まるよう簡易リトリム（文字数オーバーは末尾削る）
        # 本文中にURLは入れないため、純粋に len で判定
        if len(text) > 240:
            # 行単位で末尾から削る
            lines = text.split("\n")
            while len("\n".join(lines)) > 240 and len(lines) > 3:
                lines.pop()
            text = "\n".join(lines).rstrip()
            if len(text) > 240:
                text = text[:237] + "..."
        return text
    except Exception as e:
        logger.warning("Tweet composition failed: %s", e)
        return ""


def append_url(tweet_text: str, url: str) -> str:
    """ツイート本文に URL を末尾に追加する。"""
    if not tweet_text:
        return url
    return f"{tweet_text}\n\n{url}"
