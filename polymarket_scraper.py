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
    HISTORY_DAYS, MARKET_LIMIT, MIN_VOLUME,
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


def _infer_category(question: str) -> str:
    q = question.lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in q for kw in keywords):
            return category
    return "other"


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
    tokens: list[TokenHistory] = field(default_factory=list)

    @property
    def polymarket_url(self) -> str:
        """Polymarket公式ページのURL。"""
        return f"https://polymarket.com/event/{self.slug}" if self.slug else ""

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
        end_ts   = int(time.time())
        start_ts = end_ts - HISTORY_DAYS * 86_400
        try:
            resp = self._client.get(
                f"{CLOB_BASE}/prices-history",
                params={
                    "market":   token_id,
                    "startTs":  start_ts,
                    "endTs":    end_ts,
                    "fidelity": 60,   # 60 min bucket
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

        results: list[Market] = []

        for raw in raw_markets:
            condition_id = raw.get("conditionId") or raw.get("condition_id", "")
            volume       = float(raw.get("volume", 0) or 0)

            if not condition_id or volume < MIN_VOLUME:
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
            category = raw.get("category", "") or _infer_category(question)
            market = Market(
                condition_id=condition_id,
                question=question,
                category=category,
                end_date=raw.get("endDate") or raw.get("end_date_iso", ""),
                volume=volume,
                slug=raw.get("slug", ""),
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
