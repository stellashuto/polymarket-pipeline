"""
News scraper.

複数のRSSフィードから仮想通貨・金融ニュースを収集する。

出力: NewsItem のリスト（タイトル、本文サマリー、ソース、公開日時、URL）
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser
import httpx

from config import NEWS_FEEDS, NEWS_PER_FEED, NEWS_FRESH_HOURS

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE       = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    text = _HTML_TAG_RE.sub("", text or "")
    text = _WS_RE.sub(" ", text).strip()
    return text


def _parse_dt(entry) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime(*st[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


@dataclass
class NewsItem:
    id: str               # URLのハッシュ（記事の一意ID）
    title: str
    summary: str          # HTMLタグ除去済み本文サマリー
    link: str
    source: str           # フィード名
    category_hint: str    # config側で付与した推定カテゴリ
    published: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)

    @property
    def age_hours(self) -> Optional[float]:
        if not self.published:
            return None
        delta = datetime.now(timezone.utc) - self.published
        return delta.total_seconds() / 3600


class NewsScraper:
    def __init__(self, timeout: float = 15.0):
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "polymarket-pipeline/1.0 (+news)"},
            follow_redirects=True,
        )

    def _fetch_feed(self, url: str) -> Optional[bytes]:
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            return resp.content
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning("Feed fetch failed %s: %s", url, e)
            return None

    def fetch(self, fresh_only: bool = True) -> list[NewsItem]:
        """すべてのRSSフィードから記事を収集する。"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_FRESH_HOURS)
        results: list[NewsItem] = []
        seen_links: set[str] = set()

        for feed_cfg in NEWS_FEEDS:
            content = self._fetch_feed(feed_cfg["url"])
            if not content:
                continue

            parsed = feedparser.parse(content)
            if parsed.bozo and not parsed.entries:
                logger.warning("Feed parse failed %s: %s",
                               feed_cfg["url"], parsed.bozo_exception)
                continue

            count = 0
            for entry in parsed.entries[: NEWS_PER_FEED * 2]:
                link = (entry.get("link") or "").strip()
                title = _strip_html(entry.get("title", ""))
                if not link or not title or link in seen_links:
                    continue
                seen_links.add(link)

                published = _parse_dt(entry)
                if fresh_only and published and published < cutoff:
                    continue

                summary = _strip_html(
                    entry.get("summary")
                    or entry.get("description")
                    or (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
                )

                tags = []
                for t in entry.get("tags", []) or []:
                    term = (t.get("term") or "").strip()
                    if term:
                        tags.append(term)

                item = NewsItem(
                    id=hashlib.sha1(link.encode("utf-8")).hexdigest()[:16],
                    title=title,
                    summary=summary[:1500],   # 過大化防止
                    link=link,
                    source=feed_cfg["name"],
                    category_hint=feed_cfg["category_hint"],
                    published=published,
                    tags=tags,
                )
                results.append(item)
                count += 1
                if count >= NEWS_PER_FEED:
                    break

            logger.info("  %-18s  %d items", feed_cfg["name"], count)
            time.sleep(0.2)

        # 新しい順に並べる（公開日不明は最後）
        results.sort(
            key=lambda x: x.published or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        logger.info("Scraped %d news items total.", len(results))
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    scraper = NewsScraper()
    items = scraper.fetch(fresh_only=False)
    for it in items[:15]:
        age = f"{it.age_hours:.1f}h" if it.age_hours is not None else "n/a"
        print(f"[{it.source:18s}] ({age})  {it.title[:70]}")
