"""
Title-similarity based deduplication.

複数のニュースソースが同じ事件を扱った場合や、過去24時間以内に同じトピックの
記事を生成済みの場合に重複を防ぐ。
"""

import logging
import re
import time
import unicodedata
from pathlib import Path

from config import ARTICLES_DIR

logger = logging.getLogger(__name__)

_LATIN_RE = re.compile(r"[A-Za-z]{3,}|\d{2,}")
_JP_RE    = re.compile(r"[ぁ-んァ-ヶ一-龠ー]+")

# 固有名詞ぽいパターン：全大文字4文字以上（IREN, COIN, IBM）または先頭大文字＋4文字以上（Bitcoin, Coinbase）
# 「Will」「The」など短い英単語を弾くため最小長を多めに取る
_STRONG_ENTITY_RE = re.compile(r"[A-Z]{4,}[A-Z0-9]*|[A-Z][a-z]{4,}")
_NOISE_BIGRAMS = {
    "した", "して", "する", "ます", "です", "した", "した。",
    "なっ", "あっ", "いっ", "って", "から", "まで", "など",
    "もの", "こと", "それ", "これ", "そう", "よう", "ため",
    "とい", "いる", "なる", "ある", "らせ", "せず",
}


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def _tokens(text: str) -> tuple[set[str], set[str]]:
    """
    日本語バイグラム集合と Latin/数字トークン集合を別々に返す。
    Latinは「会社名・銘柄・固有数値」など強い識別力を持つので分離して比較する。
    """
    norm = _normalize_text(text)

    latin: set[str] = set(_LATIN_RE.findall(norm))

    jp: set[str] = set()
    for run in _JP_RE.findall(norm):
        if len(run) < 2:
            continue
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg in _NOISE_BIGRAMS:
                continue
            jp.add(bg)
    return jp, latin


def _entities(text: str) -> set[str]:
    """元の大文字小文字を尊重して固有名詞ぽい語を抽出 → 比較は小文字化。"""
    return {w.lower() for w in _STRONG_ENTITY_RE.findall(text)}


def _similarity(text_a: str, text_b: str) -> float:
    """
    日本語バイグラム類似度と Latin トークン類似度の最大値に、
    固有名詞共有のブースト(+0.15)を加算したスコアを返す。

    "IREN"のような強い識別語が両方に登場する場合、片方の日本語表現が
    違っても重複と判定できる。
    """
    jp_a, lat_a = _tokens(text_a)
    jp_b, lat_b = _tokens(text_b)

    score_jp = _jaccard(jp_a, jp_b)

    score_lat = 0.0
    if len(lat_a) >= 2 and len(lat_b) >= 2:
        score_lat = _jaccard(lat_a, lat_b)

    base = max(score_jp, score_lat)

    if _entities(text_a) & _entities(text_b):
        base = min(1.0, base + 0.15)
    return base


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _read_title(md_path: Path) -> str:
    """Markdown frontmatterからtitle: 行を1つだけ読む。"""
    try:
        with md_path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 20:    # frontmatterはせいぜい20行
                    break
                m = re.match(r'^title:\s*"?(.+?)"?\s*$', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


def find_similar_article(
    title: str,
    hours: int = 72,
    threshold: float = 0.45,
    skip_path: Path | None = None,
) -> Path | None:
    """
    タイトルが類似する既存記事を探す。

    Args:
        title:     チェックしたい記事タイトル
        hours:     何時間以内に作られた記事を対象にするか
        threshold: Jaccard類似度のしきい値（0〜1）。0.45は経験的に「同じ事件を別表現で書いた」程度を捕まえる
        skip_path: 自分自身のパス（同じファイルとマッチしないように除外）

    Returns:
        類似記事のパス。なければ None。
    """
    cutoff = time.time() - hours * 3600

    best: tuple[float, Path] | None = None
    for p in ARTICLES_DIR.glob("*.md"):
        if skip_path is not None and p == skip_path:
            continue
        if p.stat().st_mtime < cutoff:
            continue
        existing = _read_title(p)
        if not existing:
            continue
        score = _similarity(title, existing)
        if score >= threshold and (best is None or score > best[0]):
            best = (score, p)

    if best:
        logger.info("Similar article (score=%.2f): %s", best[0], best[1].name)
        return best[1]
    return None


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="既存記事の重複検出")
    parser.add_argument("--threshold", type=float, default=0.45)
    args = parser.parse_args()

    # 既存記事同士の重複を全件チェック
    files = sorted(ARTICLES_DIR.glob("*.md"))
    titles = [(p, _read_title(p)) for p in files]
    titles = [(p, t) for p, t in titles if t]

    pairs_seen: set[tuple[str, str]] = set()
    for i, (pa, ta) in enumerate(titles):
        for pb, tb in titles[i + 1:]:
            key = tuple(sorted([pa.name, pb.name]))
            if key in pairs_seen:
                continue
            pairs_seen.add(key)
            score = _similarity(ta, tb)
            if score >= args.threshold:
                print(f"[{score:.2f}] {pa.name}")
                print(f"         {pb.name}")
                print(f"         A: {ta}")
                print(f"         B: {tb}\n")
