"""
Site sync.

pipelineが生成した記事・サムネイルを Next.js サイトへコピーする。
"""

import logging
import shutil
from pathlib import Path

from config import (
    ARTICLES_DIR, THUMBNAILS_DIR,
    SITE_CONTENT_DIR, SITE_THUMBNAILS_DIR,
)

logger = logging.getLogger(__name__)


def _sync_dir(src: Path, dst: Path, suffixes: tuple[str, ...],
              prune: bool) -> tuple[int, int]:
    if not dst:
        return 0, 0
    dst.mkdir(parents=True, exist_ok=True)
    src_files: dict[str, Path] = {}
    for s in suffixes:
        for p in src.glob(f"*{s}"):
            src_files[p.name] = p
    dst_files: dict[str, Path] = {}
    for s in suffixes:
        for p in dst.glob(f"*{s}"):
            dst_files[p.name] = p

    copied = 0
    for name, sp in src_files.items():
        dp = dst / name
        if not dp.exists() or dp.read_bytes() != sp.read_bytes():
            shutil.copy2(sp, dp)
            copied += 1

    deleted = 0
    if prune:
        for name, dp in dst_files.items():
            if name not in src_files:
                dp.unlink()
                deleted += 1
    return copied, deleted


def sync_articles(prune: bool = False) -> int:
    """記事＋サムネイルを polymarket-site に同期する。"""
    total_copied = 0

    if SITE_CONTENT_DIR is not None:
        c, d = _sync_dir(ARTICLES_DIR, SITE_CONTENT_DIR, (".md",), prune)
        logger.info("Articles sync: %d copied, %d deleted.", c, d)
        total_copied += c

    if SITE_THUMBNAILS_DIR is not None:
        c, d = _sync_dir(
            THUMBNAILS_DIR, SITE_THUMBNAILS_DIR,
            (".webp", ".jpg", ".png"), prune,
        )
        logger.info("Thumbnails sync: %d copied, %d deleted.", c, d)
        total_copied += c

    return total_copied


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="記事・サムネをサイトへ同期")
    parser.add_argument("--prune", action="store_true",
                        help="サイト側にしか存在しないファイルを削除する")
    args = parser.parse_args()
    sync_articles(prune=args.prune)
