"""
タイトル翻訳ヘルパー。

Claude Haiku（軽量・高速・低コスト）で日本語タイトルを英語に翻訳する。
記事本文の翻訳は将来追加予定。当面はタイトルのみで listing/SEO 用途。
"""

import logging
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"  # 品質重視（より自然な英語タイトル）

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


_SYSTEM_TITLE = """You translate news article headlines from Japanese to natural,
publication-quality English. Output ONLY the translated headline as a single line.
No quotes, no preamble, no commentary. Match the tone (matter-of-fact news headline)."""


def translate_title(ja_title: str) -> str:
    """日本語タイトルを英語に翻訳する。失敗時は空文字列を返す。"""
    if not ja_title.strip():
        return ""
    try:
        msg = _get_client().messages.create(
            model=MODEL,
            max_tokens=200,
            system=_SYSTEM_TITLE,
            messages=[{"role": "user", "content": ja_title}],
        )
        out = "".join(b.text for b in msg.content if b.type == "text").strip()
        # 余計な引用符・先頭末尾の記号を削る
        out = out.strip('"\'「」 ').strip()
        return out
    except Exception as e:
        logger.warning("Title translation failed: %s", e)
        return ""
