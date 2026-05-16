"""
Site sync.

pipelineが生成した記事を Next.js サイトの content ディレクトリへコピーする。
"""

import logging
import shutil
from pathlib import Path

from config import ARTICLES_DIR, SITE_CONTENT_DIR

logger = logging.getLogger(__name__)


def sync_articles(prune: bool = False) -> int:
    """
    output/articles → polymarket-site/content/articles を同期する。

    Args:
        prune: True にするとサイト側に存在するがpipeline側にない記事を削除する。

    Returns:
        コピーした（=更新含む）ファイル数。
    """
    if SITE_CONTENT_DIR is None:
        logger.info("SITE_CONTENT_DIR is None — sync skipped.")
        return 0

    target: Path = SITE_CONTENT_DIR
    target.mkdir(parents=True, exist_ok=True)

    src_files = {p.name: p for p in ARTICLES_DIR.glob("*.md")}
    dst_files = {p.name: p for p in target.glob("*.md")}

    copied = 0
    for name, src in src_files.items():
        dst = target / name
        # 内容に変化があるときだけコピー（タイムスタンプの揺れを避ける）
        if (
            not dst.exists()
            or dst.read_bytes() != src.read_bytes()
        ):
            shutil.copy2(src, dst)
            copied += 1

    deleted = 0
    if prune:
        for name, dst in dst_files.items():
            if name not in src_files:
                dst.unlink()
                deleted += 1

    logger.info(
        "Site sync: %d copied, %d deleted, %d total in site.",
        copied, deleted, len(list(target.glob("*.md"))),
    )
    return copied


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="記事をサイトへ同期")
    parser.add_argument("--prune", action="store_true",
                        help="サイト側にしか存在しない記事を削除する")
    args = parser.parse_args()
    sync_articles(prune=args.prune)
