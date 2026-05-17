"""
Backfill English titles.

`title_en` フィールドが空または存在しない既存記事に対して、Claude で
タイトルを英訳して frontmatter に書き戻す。

--force 付きで実行すると既存の title_en も上書きする（モデル変更時の再翻訳用）。
"""

import argparse
import logging
import re
from pathlib import Path

from config import ARTICLES_DIR
from translator import translate_title

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FIELD_RE = re.compile(r'^(\w+):\s*"?(.*?)"?\s*$', re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    return {k: v for k, v in _FIELD_RE.findall(m.group(1))}


def _set_title_en(text: str, title_en: str) -> str:
    """frontmatter内のtitle_enフィールドを上書き、無ければtitleの直後に挿入する。"""
    safe = title_en.replace('"', "'")
    if 'title_en:' in text.split("---", 2)[1]:
        return re.sub(
            r'^title_en:\s*"?.*?"?\s*$',
            f'title_en: "{safe}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
    return re.sub(
        r'^(title:\s*"[^"]*"\s*)$',
        f'\\1\ntitle_en: "{safe}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )


def backfill(force: bool = False) -> int:
    updated = 0
    for md in sorted(ARTICLES_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if not fm:
            continue
        if fm.get("title_en") and not force:
            logger.info("Skip (has title_en): %s", md.name)
            continue

        title_ja = fm.get("title", "")
        if not title_ja:
            continue

        title_en = translate_title(title_ja)
        if not title_en:
            logger.warning("Translation failed: %s", md.name)
            continue

        new_text = _set_title_en(text, title_en)
        md.write_text(new_text, encoding="utf-8")
        updated += 1
        logger.info("[%s] %s\n    -> %s", md.name, title_ja[:50], title_en[:60])

    logger.info("Backfill complete: %d articles updated.", updated)
    return updated


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="既存の title_en も上書きする（モデル変更時の再翻訳用）")
    args = parser.parse_args()
    backfill(force=args.force)
