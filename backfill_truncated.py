"""
途中で切れた記事を検出して再生成する。

判定基準:
  - 本文末尾が句点で終わっていない
  - "よくある質問" セクションがない

該当する記事の slug を取得し、対応する topic/token を呼び出して再生成。
"""

import logging
import re
from pathlib import Path

from config import ARTICLES_DIR, OUTPUT_DIR
from airdrop_topics import ALL_TOPICS
from crypto_tokens import TOKENS
from airdrop_article import generate_airdrop_article
from crypto_explainer import generate_crypto_article

logger = logging.getLogger(__name__)

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FIELD_RE = re.compile(r'^(\w+):\s*"?(.*?)"?\s*$', re.MULTILINE)

_GOOD_TAIL_CHARS = ("。", "！", "？", ")", "）", '"', "」", "]", "】", "*")


def _parse_fm(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    return dict(_FIELD_RE.findall(m.group(1))) if m else {}


def _is_truncated(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    body = parts[-1] if len(parts) >= 3 else text
    body = body.rstrip()
    tail_char = body[-1] if body else ""
    has_faq = "よくある質問" in body
    if not has_faq:
        return True
    if tail_char not in _GOOD_TAIL_CHARS:
        return True
    return False


def regenerate_truncated() -> int:
    topics_by_slug = {t.slug: t for t in ALL_TOPICS}
    tokens_by_slug = {t.slug: t for t in TOKENS}

    targets: list[tuple[Path, str, str]] = []  # (path, kind, slug)
    for path in sorted(list(ARTICLES_DIR.glob("airdrop_*.md")) +
                       list(ARTICLES_DIR.glob("crypto_*.md"))):
        if not _is_truncated(path):
            continue
        fm = _parse_fm(path.read_text(encoding="utf-8"))
        airdrop_slug = fm.get("airdrop_slug", "")
        crypto_slug = fm.get("crypto_slug", "")
        if airdrop_slug:
            targets.append((path, "airdrop", airdrop_slug))
        elif crypto_slug:
            targets.append((path, "crypto", crypto_slug))
        else:
            logger.warning("Cannot identify slug for %s", path.name)

    logger.info("Found %d truncated articles to regenerate", len(targets))

    success = 0
    for path, kind, slug in targets:
        logger.info("Regenerating [%s] %s (slug=%s)", kind, path.name, slug)
        # サムネは流用可能だが、念のため削除して再生成させる
        thumb = OUTPUT_DIR / "thumbnails" / f"{path.stem}.webp"

        try:
            path.unlink()  # 旧記事削除（重複防止ロジックが効くと再生成されないため）
            if kind == "airdrop":
                topic = topics_by_slug.get(slug)
                if topic is None:
                    logger.warning("Topic not found: %s", slug)
                    continue
                result = generate_airdrop_article(topic=topic)
            else:
                token = tokens_by_slug.get(slug)
                if token is None:
                    logger.warning("Token not found: %s", slug)
                    continue
                result = generate_crypto_article(token=token)
            if result is not None:
                success += 1
                logger.info("  ✓ regenerated")
        except Exception as e:
            logger.error("  ✗ regenerate failed: %s", e)
        # サムネは既存を使い回す（コスト節約）
        _ = thumb

    logger.info("Done: %d/%d articles regenerated.", success, len(targets))
    return success


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    regenerate_truncated()
