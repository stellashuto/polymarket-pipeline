"""
News matcher.

Polymarketのマーケット質問と関連性の高いニュースを抽出する。
"""

import re
from typing import Iterable

from news_scraper import NewsItem
from polymarket_scraper import Market

# トークン化用のストップワード（マッチに使わない語）
_STOPWORDS = {
    "the", "a", "an", "will", "is", "are", "was", "were", "be", "been",
    "by", "in", "on", "at", "to", "of", "for", "with", "and", "or",
    "before", "after", "during", "more", "than", "less", "as",
    "this", "that", "these", "those", "do", "does", "did",
    "win", "wins", "winning", "won", "team", "teams", "game", "games",
    "year", "years", "season", "next", "first", "second", "third",
    "vi", "iv", "ii", "iii",  # GTAなどローマ数字ノイズ
    # 4桁年は単独ではマッチ不可（同じ年を扱う関係ないニュースを誤ヒットしやすいため）
    "2024", "2025", "2026", "2027",
}

_TOKEN_RE = re.compile(r"[A-Za-z]{3,}|\d{4}")  # 3文字以上の英単語 or 4桁の年


def _tokenize(text: str) -> set[str]:
    return {
        w.lower() for w in _TOKEN_RE.findall(text)
        if w.lower() not in _STOPWORDS
    }


# 重要キーワードに同義語を加える簡易シソーラス
_SYNONYMS: dict[str, list[str]] = {
    "btc":      ["bitcoin", "ビットコイン"],
    "bitcoin":  ["btc", "ビットコイン"],
    "eth":      ["ethereum", "イーサリアム"],
    "ethereum": ["eth", "イーサリアム"],
    "fed":      ["frb", "federal reserve", "fomc"],
    "trump":    ["トランプ"],
    "election": ["大統領選", "選挙"],
    "tariff":   ["関税"],
    "etf":      ["上場投資信託"],
}


def _expand(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for tok in list(tokens):
        for syn in _SYNONYMS.get(tok, []):
            expanded.add(syn.lower())
    return expanded


def find_related_news(
    market: Market,
    news: Iterable[NewsItem],
    max_results: int = 3,
    min_score: int = 3,
) -> list[NewsItem]:
    """マーケット質問に関連性のあるニュースをスコア順に返す。"""
    market_tokens = _expand(_tokenize(market.question))
    if not market_tokens:
        return []

    scored: list[tuple[int, NewsItem]] = []
    for item in news:
        haystack = item.title + " " + item.summary
        # 日本語の同義語マッチも含めるため、lower化＋部分一致で計算
        hay_lower = haystack.lower()
        score = 0
        for tok in market_tokens:
            if tok in hay_lower:
                score += 2 if tok in (item.title.lower()) else 1

        if score >= min_score:
            scored.append((score, item))

    scored.sort(key=lambda t: (t[0], t[1].published or 0), reverse=True)
    return [it for _, it in scored[:max_results]]


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    from news_scraper import NewsScraper
    from polymarket_scraper import PolymarketScraper

    news = NewsScraper().fetch(fresh_only=False)
    markets = PolymarketScraper().scrape()

    for m in markets[:5]:
        related = find_related_news(m, news)
        print(f"\n=== {m.question[:60]} ===")
        for r in related:
            print(f"  - [{r.source}] {r.title[:60]}")
