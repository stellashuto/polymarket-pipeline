"""
Polymarket data scraper.

Flow:
  1. Gamma API  → active markets list (condition_id, question, volume, category)
  2. CLOB API   → token_ids per market
  3. CLOB API   → prices-history per token (7-day, 1-hour fidelity)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import (
    GAMMA_BASE, CLOB_BASE,
    HISTORY_DAYS, HISTORY_FIDELITY, MARKET_LIMIT, MAX_PER_EVENT, MIN_VOLUME,
)

logger = logging.getLogger(__name__)

_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("crypto",       ["bitcoin", "btc", "eth", "ethereum", "crypto", "blockchain",
                      "defi", "nft", "token", "airdrop", "web3", "solana", "doge",
                      "altcoin", "stablecoin", "megaeth", "base chain"]),
    ("politics",     ["president", "election", "congress", "senate", "war", "military",
                      "government", "trump", "biden", "harris", "vote", "tariff",
                      "nato", "sanction", "ceasefire", "nuclear", "invasion", "invade"]),
    ("sports",       ["nba", "nfl", "nhl", "mlb", "fifa", "world cup", "super bowl",
                      "championship", "finals", "stanley cup", "olympics", "f1",
                      "soccer", "football", "basketball", "baseball", "tennis",
                      "win the", "tournament"]),
    ("economics",    ["gdp", "inflation", "interest rate", "federal reserve", "fed ",
                      "recession", "unemployment", "stock market", "s&p", "nasdaq",
                      "oil price", "trade deal", "ipo"]),
    ("entertainment",["album", "movie", "film", "award", "oscar", "grammy", "emmy",
                      "series", "season", "release", "rihanna", "carti", "gta"]),
]


def _infer_categories(question: str) -> list[str]:
    """質問文に該当する全カテゴリを優先順で返す。複数該当あり。"""
    q = question.lower()
    matched: list[str] = []
    for category, keywords in _CATEGORY_RULES:
        if any(kw in q for kw in keywords):
            matched.append(category)
    return matched or ["other"]


def _infer_category(question: str) -> str:
    """互換性のためのプライマリカテゴリ。"""
    return _infer_categories(question)[0]


@dataclass
class TokenHistory:
    token_id: str
    outcome: str
    history: list[dict]   # [{"t": unix_ts, "p": float}, ...]

    @property
    def latest_price(self) -> Optional[float]:
        return self.history[-1]["p"] if self.history else None


@dataclass
class Market:
    condition_id: str
    question: str
    category: str
    end_date: str
    volume: float
    slug: str = ""
    event_slug: str = ""   # 親イベントのslug。URL構築に必須
    categories: list[str] = field(default_factory=list)  # プライマリを含む全カテゴリ
    tokens: list[TokenHistory] = field(default_factory=list)

    @property
    def polymarket_url(self) -> str:
        """Polymarket公式マーケットページのURL。

        正しい形式: /event/{event_slug}/{market_slug}
        event_slug がない場合は /market/{slug} (リダイレクト経由) にフォールバック。
        """
        if self.event_slug and self.slug:
            return f"https://polymarket.com/event/{self.event_slug}/{self.slug}"
        if self.slug:
            return f"https://polymarket.com/market/{self.slug}"
        return ""

    def yes_token(self) -> Optional[TokenHistory]:
        for t in self.tokens:
            if t.outcome.lower() in ("yes", "true"):
                return t
        return self.tokens[0] if self.tokens else None


class PolymarketScraper:
    def __init__(self):
        self._client = httpx.Client(
            timeout=30,
            headers={"User-Agent": "polymarket-pipeline/1.0"},
        )

    # ------------------------------------------------------------------
    # Gamma API
    # ------------------------------------------------------------------

    def _fetch_gamma_markets(self, limit: int, offset: int = 0) -> list[dict]:
        resp = self._client.get(
            f"{GAMMA_BASE}/markets",
            params={
                "active":  "true",
                "closed":  "false",
                "limit":   limit,
                "offset":  offset,
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # CLOB API
    # ------------------------------------------------------------------

    def _fetch_clob_market(self, condition_id: str) -> Optional[dict]:
        try:
            resp = self._client.get(f"{CLOB_BASE}/markets/{condition_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("CLOB market fetch failed %s: %s", condition_id, e)
            return None

    def _fetch_prices_history(self, token_id: str) -> list[dict]:
        # Polymarket API は startTs/endTs の指定だと最大60日程度に制限される。
        # interval=max を使うとマーケット作成時からの全期間データを取得できる。
        try:
            resp = self._client.get(
                f"{CLOB_BASE}/prices-history",
                params={
                    "market":   token_id,
                    "interval": "max",
                    "fidelity": HISTORY_FIDELITY,
                },
            )
            resp.raise_for_status()
            return resp.json().get("history", [])
        except httpx.HTTPStatusError as e:
            logger.warning("Prices history failed token %s: %s", token_id, e)
            return []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def scrape(self) -> list[Market]:
        logger.info("Fetching market list from Gamma API …")
        raw_markets = self._fetch_gamma_markets(limit=MARKET_LIMIT)
        logger.info("Got %d markets, filtering by volume >= %s", len(raw_markets), MIN_VOLUME)

        # 親イベントごとに最大 MAX_PER_EVENT 件まで（同じイベントの兄弟マーケット独占を防ぐ）
        # 出来高の高いものから採用するため事前に降順ソート
        raw_markets = sorted(
            raw_markets, key=lambda r: float(r.get("volume", 0) or 0), reverse=True,
        )
        event_count: dict[str, int] = {}

        results: list[Market] = []

        for raw in raw_markets:
            condition_id = raw.get("conditionId") or raw.get("condition_id", "")
            volume       = float(raw.get("volume", 0) or 0)

            if not condition_id or volume < MIN_VOLUME:
                continue

            # 期限切れ・クローズ済みマーケットをスキップ
            if raw.get("closed") or not raw.get("active", True):
                continue

            # 同一親イベントの上限チェック
            events = raw.get("events") or []
            event_slug = events[0].get("slug", "") if events else ""
            if event_slug and event_count.get(event_slug, 0) >= MAX_PER_EVENT:
                logger.info("  Skip same-event: %s (event=%s)",
                            raw.get("question", "")[:50], event_slug)
                continue

            clob = self._fetch_clob_market(condition_id)
            if not clob:
                continue

            tokens: list[TokenHistory] = []
            for tok in clob.get("tokens", []):
                tid = tok.get("token_id", "")
                history = self._fetch_prices_history(tid)
                tokens.append(TokenHistory(
                    token_id=tid,
                    outcome=tok.get("outcome", ""),
                    history=history,
                ))
                time.sleep(0.15)   # CLOB rate-limit courtesy

            question = raw.get("question", "")
            inferred_cats = _infer_categories(question)
            raw_cat = raw.get("category", "")
            # APIに明示カテゴリがあれば最優先、その後推論結果を続ける（重複排除）
            categories: list[str] = []
            if raw_cat:
                categories.append(raw_cat)
            for c in inferred_cats:
                if c not in categories:
                    categories.append(c)
            primary = categories[0]
            # event_slug は上で取得済み
            event_count[event_slug] = event_count.get(event_slug, 0) + 1 if event_slug else 0
            market = Market(
                condition_id=condition_id,
                question=question,
                category=primary,
                categories=categories,
                end_date=raw.get("endDate") or raw.get("end_date_iso", ""),
                volume=volume,
                slug=raw.get("slug", ""),
                event_slug=event_slug,
                tokens=tokens,
            )
            results.append(market)
            logger.info("  ✓ %s  (vol $%.0f)", market.question[:60], volume)
            time.sleep(0.2)

        logger.info("Scraped %d markets total.", len(results))
        return results


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    scraper = PolymarketScraper()
    markets = scraper.scrape()
    print(json.dumps(
        [{"q": m.question, "vol": m.volume, "tokens": len(m.tokens)} for m in markets],
        indent=2, ensure_ascii=False,
    ))
