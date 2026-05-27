"""
コンテンツ自動生成パイプライン エントリポイント

サポートするフロー:
  - Flow A:  RSSニュースを収集して日本語リライト記事を生成
  - Flow B:  Polymarketマーケット解説記事を、関連ニュース文脈とともに生成

実行例:
  python main.py news                  # Flow A のみ（ニュースを最大5本）
  python main.py news --limit 3        # Flow A 3本
  python main.py market --limit 2      # Flow B 2本
  python main.py all --news-limit 5 --market-limit 2  # 両方
  python main.py news --dry-run        # 取得のみ
"""

import argparse
import logging
import sys

from polymarket_scraper import PolymarketScraper
from news_scraper import NewsScraper
from news_matcher import find_related_news
from article_draft import generate_article
from news_article import generate_news_article, _infer_news_category
from airdrop_article import generate_airdrop_article
from crypto_explainer import generate_crypto_article
from site_sync import sync_articles
from diverse_select import diverse_pick

_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.stream = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        _stdout_handler,
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def run_news_flow(limit: int, dry_run: bool) -> int:
    """Flow A: RSS → Claude リライト記事。
    カテゴリ多様性を考慮し、政治/経済/暗号資産が偏らないようにラウンドロビン選択する。"""
    logger.info("=== Flow A: News rewrite ===")
    news = NewsScraper().fetch(fresh_only=True)
    if not news:
        logger.warning("No news items fetched.")
        return 0

    # 候補を多めに用意（重複でスキップされる分のバッファとして3倍）し、
    # 政治→経済→暗号資産の順で巡回する
    candidates = diverse_pick(
        news,
        limit=limit * 3,
        category_of=lambda n: _infer_news_category(n),
        rank_of=lambda n: n.published.timestamp() if n.published else 0,
        preferred_order=["politics", "economics", "crypto", "entertainment", "other"],
    )
    logger.info("Trying up to %d news items (from %d category-balanced candidates).",
                limit, len(candidates))

    if dry_run:
        for n in candidates[:limit]:
            print(f"  [DRY-RUN] [{_infer_news_category(n):10s}] [{n.source}] {n.title[:60]}")
        return 0

    saved = 0
    attempted = 0
    for item in candidates:
        if saved >= limit:
            break
        attempted += 1
        try:
            result = generate_news_article(item)
            if result is not None:
                saved += 1
        except Exception as e:
            logger.error("News article failed (%s): %s", item.id, e)
    logger.info("Flow A done: %d articles generated (%d attempted).", saved, attempted)
    return saved


def run_market_flow(limit: int, dry_run: bool, use_news_context: bool = True) -> int:
    """Flow B: Polymarket → Claude 解説記事（+関連ニュース）。重複は自動スキップ。"""
    logger.info("=== Flow B: Polymarket commentary ===")
    scraper = PolymarketScraper()
    markets = scraper.scrape()
    if not markets:
        logger.warning("No markets found.")
        return 0

    # カテゴリ多様性を考慮（スポーツ独占を防ぐ）
    markets = diverse_pick(
        markets,
        limit=limit * 4,
        category_of=lambda m: m.category,
        rank_of=lambda m: m.volume,
        preferred_order=["politics", "economics", "crypto", "sports", "entertainment", "other"],
    )
    logger.info("Trying up to %d markets from %d category-balanced candidates.",
                limit, len(markets))

    if dry_run:
        for m in markets[:limit]:
            print(f"  [DRY-RUN] [{m.category:10s}] {m.question[:60]}  vol=${m.volume:,.0f}")
        return 0

    news = []
    if use_news_context:
        try:
            news = NewsScraper().fetch(fresh_only=True)
        except Exception as e:
            logger.warning("News fetch for context failed: %s", e)

    saved = 0
    for market in markets:
        if saved >= limit:
            break
        related = find_related_news(market, news) if news else []
        if related:
            logger.info("--- %s (related: %d) ---", market.question[:60], len(related))
        try:
            result = generate_article(market, related_news=related)
            if result is not None:
                saved += 1
        except Exception as e:
            logger.error("Article failed (%s): %s", market.condition_id, e)
    logger.info("Flow B done: %d articles generated.", saved)
    return saved


def run_airdrop_flow(limit: int, dry_run: bool) -> int:
    """Flow C: キュレート済みトピックリストからエアドロップ解説記事を生成。
    プロジェクト単位の重複防止は airdrop_article 側で airdrop_slug を見て自動判定する。
    プロジェクト記事には直近のニュースを自動で組み込む（最新情報反映）。"""
    logger.info("=== Flow C: Airdrop guides ===")

    if dry_run:
        from airdrop_article import _pick_topic
        for _ in range(limit):
            t = _pick_topic()
            if t is None:
                print("  [DRY-RUN] (no more topics)")
                break
            print(f"  [DRY-RUN] [{t.kind:7s}] [{t.audience:12s}] {t.slug}")
        return 0

    # ニュースを1回だけフェッチして使い回す（複数記事生成時のAPI節約）
    news_cache = None
    try:
        news_cache = NewsScraper().fetch(fresh_only=False)
        logger.info("Cached %d news items for airdrop articles", len(news_cache))
    except Exception as e:
        logger.warning("News fetch failed (airdrop flow will use evergreen content): %s", e)
        news_cache = []

    saved = 0
    for _ in range(limit):
        try:
            result = generate_airdrop_article(news_cache=news_cache)
            if result is None:
                break  # 全トピック書き尽くした or 失敗
            saved += 1
        except Exception as e:
            logger.error("Airdrop article failed: %s", e)
            break
    logger.info("Flow C done: %d articles generated.", saved)
    return saved


def run_crypto_flow(limit: int, dry_run: bool) -> int:
    """Flow D: 仮想通貨銘柄解説記事。トークン単位の重複防止＋RSSニュース反映。"""
    logger.info("=== Flow D: Crypto explainers ===")

    if dry_run:
        from crypto_explainer import _pick_token
        for _ in range(limit):
            t = _pick_token()
            if t is None:
                print("  [DRY-RUN] (no more tokens)")
                break
            print(f"  [DRY-RUN] [{t.category:10s}] {t.symbol} ({t.name})")
        return 0

    news_cache = None
    try:
        news_cache = NewsScraper().fetch(fresh_only=False)
        logger.info("Cached %d news items for crypto explainers", len(news_cache))
    except Exception as e:
        logger.warning("News fetch failed (crypto flow uses evergreen): %s", e)
        news_cache = []

    saved = 0
    for _ in range(limit):
        try:
            result = generate_crypto_article(news_cache=news_cache)
            if result is None:
                break
            saved += 1
        except Exception as e:
            logger.error("Crypto explainer failed: %s", e)
            break
    logger.info("Flow D done: %d articles generated.", saved)
    return saved


def main():
    parser = argparse.ArgumentParser(description="コンテンツ自動生成パイプライン")
    parser.add_argument("flow", choices=["news", "market", "airdrop", "crypto", "all"],
                        help="実行するフロー")
    parser.add_argument("--limit", type=int, default=5,
                        help="news/market 単独実行時の上限 (default: 5)")
    parser.add_argument("--news-limit", type=int, default=3,
                        help="all モード時の Flow A 上限")
    parser.add_argument("--market-limit", type=int, default=1,
                        help="all モード時の Flow B 上限")
    parser.add_argument("--airdrop-limit", type=int, default=2,
                        help="all モード時の Flow C 上限")
    parser.add_argument("--crypto-limit", type=int, default=2,
                        help="all モード時の Flow D 上限")
    parser.add_argument("--dry-run", action="store_true",
                        help="記事を生成せず取得対象のみ表示")
    parser.add_argument("--no-news-context", action="store_true",
                        help="Flow B で関連ニュース引用を無効化")
    parser.add_argument("--no-sync", action="store_true",
                        help="生成後にサイトへ自動同期しない")
    args = parser.parse_args()

    if args.flow == "news":
        run_news_flow(args.limit, args.dry_run)
    elif args.flow == "market":
        run_market_flow(args.limit, args.dry_run,
                        use_news_context=not args.no_news_context)
    elif args.flow == "airdrop":
        run_airdrop_flow(args.limit, args.dry_run)
    elif args.flow == "crypto":
        run_crypto_flow(args.limit, args.dry_run)
    else:  # all
        run_news_flow(args.news_limit, args.dry_run)
        run_market_flow(args.market_limit, args.dry_run,
                        use_news_context=not args.no_news_context)
        run_airdrop_flow(args.airdrop_limit, args.dry_run)
        run_crypto_flow(args.crypto_limit, args.dry_run)

    if not args.dry_run and not args.no_sync:
        sync_articles()


if __name__ == "__main__":
    main()
