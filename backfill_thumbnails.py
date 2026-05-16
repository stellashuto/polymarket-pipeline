"""
Backfill thumbnails.

既存の記事Markdown内のfrontmatterを読み、thumbnailフィールドが空の
ものに対してサムネを生成し、frontmatterを更新する。
"""

import logging
import re
from pathlib import Path

from config import ARTICLES_DIR
from thumbnail_generator import generate_thumbnail

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FIELD_RE = re.compile(r'^(\w+):\s*"?(.*?)"?\s*$', re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    return {k: v for k, v in _FIELD_RE.findall(m.group(1))}


def _update_thumbnail_field(text: str, thumb_name: str) -> str:
    """frontmatter内のthumbnailフィールドを上書き、無ければtypeの前に追加する。"""
    if 'thumbnail:' in text.split("---", 2)[1]:
        return re.sub(
            r'^thumbnail:\s*"?.*?"?\s*$',
            f'thumbnail: "{thumb_name}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
    # type行の前に挿入
    return re.sub(
        r'^(type:)',
        f'thumbnail: "{thumb_name}"\n\\1',
        text,
        count=1,
        flags=re.MULTILINE,
    )


def backfill() -> int:
    updated = 0
    for md in ARTICLES_DIR.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if not fm:
            continue
        if fm.get("thumbnail"):
            logger.info("Skip (has thumbnail): %s", md.name)
            continue

        slug = md.stem
        title = fm.get("title", "")
        category = fm.get("category", "other")
        # 本文の冒頭500文字をsummaryとして渡す
        body = text[len(_FRONTMATTER_RE.match(text).group(0)):]
        summary = re.sub(r"[#*`>\-\[\]()]", " ", body)[:500]

        logger.info("Backfilling: %s", md.name)
        thumb = generate_thumbnail(slug, title, summary, category)
        if not thumb:
            logger.warning("Failed to generate thumbnail for %s", md.name)
            continue

        new_text = _update_thumbnail_field(text, thumb.name)
        md.write_text(new_text, encoding="utf-8")
        updated += 1
        logger.info("Updated frontmatter: %s", md.name)

    logger.info("Backfill complete: %d articles updated.", updated)
    return updated


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    backfill()
