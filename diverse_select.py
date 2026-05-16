"""
カテゴリ多様性を考慮した選択ヘルパー。

ラウンドロビン方式で、カテゴリ間のバランスをとりつつ各カテゴリ内では
出来高/新しさの順で取り出す。
"""

from typing import Iterable, TypeVar, Callable

T = TypeVar("T")


def diverse_pick(
    items: Iterable[T],
    limit: int,
    category_of: Callable[[T], str],
    rank_of: Callable[[T], float],
    preferred_order: list[str] | None = None,
) -> list[T]:
    """
    Args:
        items:            候補
        limit:            欲しい件数
        category_of:      各アイテムのカテゴリを返す関数
        rank_of:          各アイテムのスコア（大きいほど上位）を返す関数
        preferred_order:  カテゴリの優先巡回順（指定なしならアルファベット順）

    Returns:
        ラウンドロビンで最大 limit 件返す。
    """
    # カテゴリごとにスコア降順でグループ化
    buckets: dict[str, list[T]] = {}
    for it in items:
        buckets.setdefault(category_of(it), []).append(it)
    for c in buckets:
        buckets[c].sort(key=rank_of, reverse=True)

    if preferred_order is None:
        preferred_order = sorted(buckets.keys())

    # 指定順 → それ以外の順
    order = [c for c in preferred_order if c in buckets]
    order += [c for c in buckets if c not in preferred_order]

    out: list[T] = []
    while len(out) < limit:
        progressed = False
        for cat in order:
            if buckets[cat]:
                out.append(buckets[cat].pop(0))
                progressed = True
                if len(out) >= limit:
                    break
        if not progressed:
            break
    return out
