"""
Thumbnail generator.

記事の内容からビジュアル概念を抽出し、Replicate (Flux Schnell) で
サムネイル画像を生成して output/thumbnails/{slug}.jpg に保存する。

ビジュアル概念抽出は Claude Haiku（軽量モデル）で行い、画像生成APIを
無駄に叩かないようローカルキャッシュを利用する。
"""

import logging
import re
import time
from pathlib import Path
from typing import Optional

import anthropic
import httpx
import replicate

from config import (
    ANTHROPIC_API_KEY, REPLICATE_API_TOKEN, THUMBNAILS_DIR,
)

logger = logging.getLogger(__name__)

PROMPT_MODEL = "claude-sonnet-4-6"   # 品質重視（より洗練されたサムネプロンプト）
IMAGE_MODEL  = "black-forest-labs/flux-schnell"

PROMPT_SYSTEM = """You are a visual director for a Japanese cryptocurrency / finance news media site.
Your job: given a news article (title + short summary + category), produce ONE short English image-generation prompt
(under 50 words) that describes a thumbnail image suitable for the article.

Rules:
- Output ONLY the prompt itself, with no preamble, no quotes, no labels
- Avoid text/letters in the image (they render poorly)
- Avoid logos and trademarked symbols
- Use abstract/photographic concepts (financial cityscape, glowing graphs, futuristic terminal, etc.)
- Style: cinematic, modern, news-magazine aesthetic, soft lighting
- Aspect: 16:9 horizontal composition with negative space at top-left for headline overlay
- Include relevant visual metaphor (e.g. rising candles for crypto rally, scales for regulation, globe for international news)"""

_anth: Optional[anthropic.Anthropic] = None


def _anth_client() -> anthropic.Anthropic:
    global _anth
    if _anth is None:
        _anth = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anth


def _generate_visual_prompt(title: str, summary: str, category: str) -> str:
    msg = _anth_client().messages.create(
        model=PROMPT_MODEL,
        max_tokens=200,
        system=PROMPT_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Category: {category}\n"
                f"Title: {title}\n"
                f"Summary: {summary[:500]}"
            ),
        }],
    )
    text = "".join(block.text for block in msg.content if block.type == "text").strip()
    text = text.strip("`'\"")
    return text


def _save_image(url: str, dest: Path) -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


def generate_thumbnail(slug: str, title: str, summary: str, category: str,
                       force: bool = False) -> Optional[Path]:
    """
    記事用サムネイルを生成して保存する。

    Args:
        slug: 出力ファイル名のベース（例: condition_id, news_xxxx）
        title, summary, category: 視覚化のヒント
        force: True にすると既存ファイルがあっても再生成

    Returns:
        保存されたファイルパス。生成失敗時は None。
    """
    if not REPLICATE_API_TOKEN:
        logger.warning("REPLICATE_API_TOKEN not set — thumbnail skipped.")
        return None

    dest = THUMBNAILS_DIR / f"{slug}.webp"
    if dest.exists() and not force:
        logger.info("Thumbnail cached: %s", dest.name)
        return dest

    try:
        visual_prompt = _generate_visual_prompt(title, summary, category)
        logger.info("Visual prompt: %s", visual_prompt[:120])
    except Exception as e:
        logger.warning("Visual prompt generation failed: %s", e)
        return None

    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        # Replicateの無料ティアはバースト1なのでリトライ込みで安全に実行
        output = None
        for attempt in range(5):
            try:
                output = client.run(
                    IMAGE_MODEL,
                    input={
                        "prompt": visual_prompt,
                        "aspect_ratio": "16:9",
                        "num_outputs": 1,
                        "output_format": "webp",
                        "output_quality": 85,
                        "go_fast": True,
                    },
                )
                break
            except replicate.exceptions.ReplicateError as e:
                # 429: rate limit. 数秒待ってからリトライ
                msg = str(e)
                m = re.search(r"resets in ~(\d+)s", msg)
                if "429" in msg or "throttled" in msg.lower():
                    wait = int(m.group(1)) + 2 if m else 12
                    logger.warning("Rate limited; retry in %ds (attempt %d/5)", wait, attempt + 1)
                    time.sleep(wait)
                    continue
                raise

        if output is None:
            raise RuntimeError("Replicate exhausted retries")

        # Replicate v0.32+ returns a list of FileOutput objects
        if isinstance(output, list) and output:
            first = output[0]
        else:
            first = output

        # FileOutput has .url() method; fallback to str(...) for older versions
        if hasattr(first, "read"):
            dest.write_bytes(first.read())
        elif hasattr(first, "url"):
            _save_image(first.url() if callable(first.url) else first.url, dest)
        else:
            _save_image(str(first), dest)

        logger.info("Thumbnail saved → %s", dest)
        return dest
    except Exception as e:
        logger.warning("Image generation failed: %s", e)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    path = generate_thumbnail(
        slug="test_btc",
        title="ビットコインが10万ドルに迫る、機関投資家の買いが加速",
        summary="米スポットETFへの資金流入が続き、ビットコイン価格が9.8万ドルまで上昇。市場関係者は10万ドル突破を時間の問題と見ている。",
        category="crypto",
    )
    print("Result:", path)
