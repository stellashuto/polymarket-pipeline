import os
from pathlib import Path

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")

OUTPUT_DIR     = Path(__file__).parent / "output"
CHARTS_DIR     = OUTPUT_DIR / "charts"
ARTICLES_DIR   = OUTPUT_DIR / "articles"
THUMBNAILS_DIR = OUTPUT_DIR / "thumbnails"

OUTPUT_DIR.mkdir(exist_ok=True)
CHARTS_DIR.mkdir(exist_ok=True)
ARTICLES_DIR.mkdir(exist_ok=True)
THUMBNAILS_DIR.mkdir(exist_ok=True)

# Next.js サイトの content / public ディレクトリ（自動同期先）
# None にすると同期をスキップ
SITE_CONTENT_DIR: Path | None = (
    Path(__file__).parent.parent / "polymarket-site" / "content" / "articles"
)
SITE_THUMBNAILS_DIR: Path | None = (
    Path(__file__).parent.parent / "polymarket-site" / "public" / "thumbnails"
)

# どのカテゴリキーワードをアクティブに取得するか
TARGET_CATEGORIES = ["politics", "crypto", "economics"]

# 1記事あたりの取得オッズ履歴（日数）
HISTORY_DAYS = 7

# 取得マーケット上限（1バッチ）
MARKET_LIMIT = 30

# 出来高フィルター：これ未満のマーケットはスキップ（USD）
MIN_VOLUME = 50_000

# ニュースRSSフィード（仮想通貨・金融）
NEWS_FEEDS: list[dict] = [
    {"name": "CoinPost",          "url": "https://coinpost.jp/?feed=rss2",        "category_hint": "crypto"},
    {"name": "CoinDesk JAPAN",    "url": "https://www.coindeskjapan.com/feed/",   "category_hint": "crypto"},
    {"name": "あたらしい経済",       "url": "https://www.neweconomy.jp/feed",         "category_hint": "crypto"},
    {"name": "Crypto Times",      "url": "https://crypto-times.jp/feed/",         "category_hint": "crypto"},
]

# 1フィードあたり取得件数の上限
NEWS_PER_FEED = 10

# 何時間以内に公開されたニュースを「新着」とみなすか
NEWS_FRESH_HOURS = 48
