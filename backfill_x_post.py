"""
既存の airdrop / crypto 記事に x_post（ツイート文）フィールドを追加する。

frontmatter にすでに x_post があればスキップ。なければ Claude で生成して
type 行の直後に挿入する。
"""

import argparse
import logging
import re
from pathlib import Path

from config import ARTICLES_DIR
from tweet_generator import compose_tweet

logger = logging.getLogger(__name__)

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FIELD_RE = re.compile(r'^(\w+):\s*"?(.*?)"?\s*$', re.MULTILINE)


def _has_x_post(fm_text: str) -> bool:
    return bool(re.search(r"^x_post:\s*\|", fm_text, re.MULTILINE))


def _insert_x_post(text: str, x_post: str) -> str:
    """frontmatter の `type:` 行直後に x_post: | ブロックを挿入。"""
    indented = "\n".join("  " + line for line in x_post.split("\n"))
    block = f"x_post: |\n{indented}\n"
    return re.sub(
        r'^(type:\s*"?[^"\n]*"?\s*\n)',
        f'\\1{block}',
        text,
        count=1,
        flags=re.MULTILINE,
    )


def backfill(force: bool = False) -> int:
    files = sorted(
        list(ARTICLES_DIR.glob("airdrop_*.md")) +
        list(ARTICLES_DIR.glob("crypto_*.md"))
    )
    updated = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        fm_match = _FM_RE.match(text)
        if not fm_match:
            continue
        fm_text = fm_match.group(1)
        if _has_x_post(fm_text) and not force:
            logger.info("Skip (has x_post): %s", path.name)
            continue

        fields = dict(_FIELD_RE.findall(fm_text))
        title = fields.get("title", "")
        category = fields.get("category", "other")
        # 追加ハッシュタグ候補
        extra = []
        if category == "airdrop":
            extra = ["エアドロップ", "Airdrop"]
            if fields.get("airdrop_kind") == "project":
                # slug を CamelCase 風に
                slug = fields.get("airdrop_slug", "")
                if slug and not slug.startswith("guide-"):
                    extra.append(slug.replace("-", "").title())
        elif category == "crypto":
            sym = fields.get("crypto_symbol", "")
            extra = ["仮想通貨"]
            if sym:
                extra.append(sym)

        # 本文抜粋（frontmatter以降の最初の800字）
        body = text[fm_match.end():]

        logger.info("Composing tweet: %s", path.name)
        x_post = compose_tweet(title=title, body_excerpt=body,
                               category=category, extra_hashtags=extra)
        if not x_post:
            logger.warning("  failed: %s", path.name)
            continue

        new_text = _insert_x_post(text, x_post)
        path.write_text(new_text, encoding="utf-8")
        updated += 1
        logger.info("  ✓ %d chars", len(x_post))

    logger.info("Done: %d files updated.", updated)
    return updated


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="既存の x_post も再生成する")
    args = parser.parse_args()
    backfill(force=args.force)
