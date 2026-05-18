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

# Polymarket履歴データの集計粒度（分）。interval=max と併用してマーケット作成時からの
# 全期間データを取得する。fidelity=60 (1時間足) でデータ量と精度のバランスを取る
HISTORY_FIDELITY = 60
# 旧設定（startTs/endTs指定時の日数。現在はinterval=maxを使うため未使用だが互換のため保持）
HISTORY_DAYS = 90

# 取得マーケット上限（1バッチ）。多様性確保のため広めに取る
MARKET_LIMIT = 80

# 出来高フィルター：これ未満のマーケットはスキップ（USD）
MIN_VOLUME = 50_000

# 同じ親イベント（例: "What will happen before GTA VI?"）から1バッチで採用する
# 最大マーケット数。サブマーケットが上位を独占して画一的にならないよう制限する
MAX_PER_EVENT = 1

# ニュースRSSフィード
# 著作権リスクを下げるため:
#  - 日本語ソース: 仮想通貨専門メディア（業界標準のリライト慣行に沿う）
#  - 英語ソース: 海外メディアを日本語へ翻案 → 著作権法上「翻訳」として独立著作物
#                政治・経済（FRB / SEC / 規制 / トランプ政策）も濃くカバーされる
NEWS_FEEDS: list[dict] = [
    # --- 日本語 仮想通貨専門 ---
    {"name": "CoinPost",          "url": "https://coinpost.jp/?feed=rss2",                                "category_hint": "crypto"},
    {"name": "CoinDesk JAPAN",    "url": "https://www.coindeskjapan.com/feed/",                           "category_hint": "crypto"},
    {"name": "あたらしい経済",       "url": "https://www.neweconomy.jp/feed",                                 "category_hint": "crypto"},
    {"name": "Crypto Times",      "url": "https://crypto-times.jp/feed/",                                 "category_hint": "crypto"},
    # --- 英語 海外メディア（日本語化）---
    {"name": "CoinDesk",          "url": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml","category_hint": "crypto"},
    {"name": "Cointelegraph",     "url": "https://cointelegraph.com/rss",                                 "category_hint": "crypto"},
    {"name": "The Block",         "url": "https://www.theblock.co/rss.xml",                               "category_hint": "crypto"},
    {"name": "Decrypt",           "url": "https://decrypt.co/feed",                                       "category_hint": "crypto"},
]

# 英語ソース名のセット（カテゴリ推定で英単語キーワードを重み付けするため）
ENGLISH_SOURCES = {"CoinDesk", "Cointelegraph", "The Block", "Decrypt"}

# 1フィードあたり取得件数の上限
NEWS_PER_FEED = 10

# 何時間以内に公開されたニュースを「新着」とみなすか
NEWS_FRESH_HOURS = 48
