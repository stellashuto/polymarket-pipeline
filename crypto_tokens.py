"""
仮想通貨銘柄解説用のキュレート済みトークンリスト。

日本人読者の検索ボリュームが高い銘柄を中心に、L1/L2/DeFi/ステーブルコイン/
ミームなど多様性を確保。SEOで「○○ とは」「○○ 仕組み」を狙う長尾コンテンツ。
"""

from dataclasses import dataclass, field


@dataclass
class CryptoToken:
    slug: str               # ファイル名・dedupキー（小文字シンボル）
    symbol: str             # 表記用シンボル (BTC, ETH, ...)
    name: str               # 英語名
    name_jp: str            # 日本語表記（カタカナ）
    category: str           # "L1" | "L2" | "DeFi" | "Stablecoin" | "Meme" | "Other"
    summary: str            # プロンプト用コンテキスト
    search_keywords: list[str] = field(default_factory=list)


TOKENS: list[CryptoToken] = [
    # --- Tier 1: 主要L1 ---
    CryptoToken(
        slug="btc", symbol="BTC", name="Bitcoin", name_jp="ビットコイン",
        category="L1",
        summary="世界初の暗号資産。2009年にサトシ・ナカモト名義で誕生。PoW（Proof of Work）採用、約4年ごとに半減期で発行量が半減。デジタルゴールドとして機関投資家・国家による保有も進む。",
        search_keywords=["bitcoin", "btc", "ビットコイン"],
    ),
    CryptoToken(
        slug="eth", symbol="ETH", name="Ethereum", name_jp="イーサリアム",
        category="L1",
        summary="スマートコントラクトを実装した汎用ブロックチェーン。2015年launch、2022年The MergeでPoS移行。DeFi・NFT・L2の基盤として最大のエコシステム。",
        search_keywords=["ethereum", "eth", "イーサリアム"],
    ),
    CryptoToken(
        slug="sol", symbol="SOL", name="Solana", name_jp="ソラナ",
        category="L1",
        summary="高速・低手数料を目指すL1。Proof of HistoryとPoSの組合せで毎秒数千〜数万TPSを実現。ミームコインブームの中心舞台。",
        search_keywords=["solana", "sol", "ソラナ"],
    ),
    CryptoToken(
        slug="xrp", symbol="XRP", name="XRP", name_jp="リップル / エックスアールピー",
        category="L1",
        summary="Ripple社が主導する国際送金特化のブロックチェーン。SECとの長期訴訟が2023〜2024年に決着。日本国内取引所での取引高が世界トップクラス。",
        search_keywords=["xrp", "ripple", "リップル"],
    ),
    CryptoToken(
        slug="bnb", symbol="BNB", name="BNB", name_jp="ビーエヌビー",
        category="L1",
        summary="Binance取引所が発行・運営するBNB Chainのネイティブトークン。取引手数料割引・ローンチパッド参加権など実用性が高い。",
        search_keywords=["bnb", "binance coin", "binance chain"],
    ),
    CryptoToken(
        slug="ada", symbol="ADA", name="Cardano", name_jp="カルダノ / エイダ",
        category="L1",
        summary="査読論文ベースで設計されたPoS L1。Ouroborosコンセンサス、3層アーキテクチャ。日本のコミュニティが伝統的に強い。",
        search_keywords=["cardano", "ada", "カルダノ"],
    ),
    CryptoToken(
        slug="doge", symbol="DOGE", name="Dogecoin", name_jp="ドージコイン",
        category="Meme",
        summary="元祖ミームコイン。柴犬モチーフ。イーロン・マスク氏の影響で価格が乱高下。X（旧Twitter）統合の議論も継続。",
        search_keywords=["dogecoin", "doge", "ドージコイン"],
    ),
    CryptoToken(
        slug="trx", symbol="TRX", name="Tron", name_jp="トロン",
        category="L1",
        summary="ジャスティン・サン氏が創設したL1。USDT（テザー）流通量の大部分を支える「ステーブルコイン高速道路」。",
        search_keywords=["tron", "trx", "トロン"],
    ),
    CryptoToken(
        slug="hype", symbol="HYPE", name="Hyperliquid", name_jp="ハイパーリキッド",
        category="L1",
        summary="独自L1上に構築されたPerp DEX「Hyperliquid」のネイティブトークン。2024年大規模エアドロップで業界に衝撃。ETF申請も提出された注目銘柄。",
        search_keywords=["hyperliquid", "hype"],
    ),
    CryptoToken(
        slug="avax", symbol="AVAX", name="Avalanche", name_jp="アバランチ",
        category="L1",
        summary="サブネット構造によるスケーラブルなL1。エンタープライズ用途のカスタムチェーン構築が特徴。",
        search_keywords=["avalanche", "avax", "アバランチ"],
    ),
    CryptoToken(
        slug="sui", symbol="SUI", name="Sui", name_jp="スイ",
        category="L1",
        summary="Move言語ベースの並列処理L1。元Diem（旧Facebook）エンジニア発。ゲーム・SBT用途で注目。",
        search_keywords=["sui", "スイ", "mysten"],
    ),
    CryptoToken(
        slug="apt", symbol="APT", name="Aptos", name_jp="アプトス",
        category="L1",
        summary="Sui同様、元Diemチームが開発したMoveベースL1。BlockchainAptosの並列実行エンジン。",
        search_keywords=["aptos", "apt", "アプトス"],
    ),
    CryptoToken(
        slug="near", symbol="NEAR", name="NEAR Protocol", name_jp="ニア",
        category="L1",
        summary="シャーディング採用のスケーラブルL1。Chain Signaturesによるマルチチェーン署名やAI連携が話題。",
        search_keywords=["near protocol", "near", "ニア"],
    ),
    CryptoToken(
        slug="ton", symbol="TON", name="Toncoin", name_jp="トン / トンコイン",
        category="L1",
        summary="Telegramが開発支援するL1。Telegramミニアプリ経由のオンボーディングで2024年急成長。",
        search_keywords=["toncoin", "ton ", "テレグラム"],
    ),

    # --- L2 ---
    CryptoToken(
        slug="matic", symbol="POL", name="Polygon", name_jp="ポリゴン",
        category="L2",
        summary="EthereumのL2/サイドチェーン。2024年にMATICからPOLへトークン移行。zkEVM・AggLayer等エコシステム拡張中。",
        search_keywords=["polygon", "matic", "pol", "ポリゴン"],
    ),
    CryptoToken(
        slug="arb", symbol="ARB", name="Arbitrum", name_jp="アービトラム",
        category="L2",
        summary="Optimistic Rollup方式のEthereum L2。最大級のTVLを持つL2の1つ。2023年のARBトークンエアドロップで業界話題に。",
        search_keywords=["arbitrum", "arb", "アービトラム"],
    ),
    CryptoToken(
        slug="op", symbol="OP", name="Optimism", name_jp="オプティミズム",
        category="L2",
        summary="Optimistic RollupのEthereum L2。OP Stackを通じてBaseやWorld Chainなどスーパーチェーン構築。Retroactive Public Goods Fundingで知られる。",
        search_keywords=["optimism", "op ", "オプティミズム"],
    ),

    # --- DeFi ---
    CryptoToken(
        slug="uni", symbol="UNI", name="Uniswap", name_jp="ユニスワップ",
        category="DeFi",
        summary="最大手の分散型取引所（DEX）。AMMモデルを業界に広めた立役者。2020年のレトロアクティブUNI配布はエアドロップ史上最大級。",
        search_keywords=["uniswap", "uni ", "ユニスワップ"],
    ),
    CryptoToken(
        slug="aave", symbol="AAVE", name="Aave", name_jp="アーベ",
        category="DeFi",
        summary="最大手の分散型レンディングプロトコル。Flash Loanの概念を業界に広めた。GHOステーブルコインも提供。",
        search_keywords=["aave", "アーベ", "gho"],
    ),
    CryptoToken(
        slug="link", symbol="LINK", name="Chainlink", name_jp="チェーンリンク",
        category="DeFi",
        summary="ブロックチェーンと外部データを繋ぐオラクル基盤。CCIPでクロスチェーン通信、SWIFT連携も実証。",
        search_keywords=["chainlink", "link ", "チェーンリンク", "ccip"],
    ),
    CryptoToken(
        slug="ldo", symbol="LDO", name="Lido", name_jp="リド",
        category="DeFi",
        summary="最大級のリキッドステーキング・プロトコル。stETHを発行、ETH PoSバリデーター市場で約30%のシェア。",
        search_keywords=["lido", "ldo", "リド", "steth"],
    ),
    CryptoToken(
        slug="mkr", symbol="MKR", name="Maker / Sky", name_jp="メイカー / スカイ",
        category="DeFi",
        summary="DAIステーブルコインの発行主体。2024年にSky Protocolへリブランドし、USDS/SKYへの移行を進めている老舗DeFi。",
        search_keywords=["maker", "makerdao", "sky protocol", "dai"],
    ),
    CryptoToken(
        slug="pendle", symbol="PENDLE", name="Pendle", name_jp="ペンドル",
        category="DeFi",
        summary="利回りをPT（元本）とYT（利回り）に分離して取引できるプロトコル。LRT・LST時代の代表的なエアドロップポイント獲得手段。",
        search_keywords=["pendle", "ペンドル"],
    ),
    CryptoToken(
        slug="jup", symbol="JUP", name="Jupiter", name_jp="ジュピター",
        category="DeFi",
        summary="Solana最大のDEXアグリゲータ。JUPトークン保有でガバナンス参加、複数シーズンのエアドロップ実施。",
        search_keywords=["jupiter", "jup ", "ジュピター"],
    ),

    # --- ステーブルコイン ---
    CryptoToken(
        slug="usdt", symbol="USDT", name="Tether", name_jp="テザー",
        category="Stablecoin",
        summary="時価総額最大のステーブルコイン。1USDT≒1USDをペッグ。Tether社が発行、準備資産の構成や透明性が継続的に議論される。",
        search_keywords=["tether", "usdt", "テザー"],
    ),
    CryptoToken(
        slug="usdc", symbol="USDC", name="USD Coin", name_jp="ユーエスディーシー / USDコイン",
        category="Stablecoin",
        summary="Circle社が発行する米ドル建てステーブルコイン。準備資産の開示が厚く、米国規制下で運営される最大級のステーブル。",
        search_keywords=["usd coin", "usdc", "circle"],
    ),
    CryptoToken(
        slug="jpyc", symbol="JPYC", name="JPYC", name_jp="ジェイピーワイシー",
        category="Stablecoin",
        summary="日本円建てステーブルコイン。前払式支払手段としてスタートし、2025年改正資金決済法での仕組み変更を控える。Kaiaチェーンなど対応拡大。",
        search_keywords=["jpyc", "日本円ステーブル"],
    ),

    # --- Meme ---
    CryptoToken(
        slug="shib", symbol="SHIB", name="Shiba Inu", name_jp="シバイヌ",
        category="Meme",
        summary="DOGEに続くミームコイン2号。ShibariumというL2を独自展開。日本のSNS層からの人気が根強い。",
        search_keywords=["shiba inu", "shib", "シバイヌ"],
    ),
    CryptoToken(
        slug="pepe", symbol="PEPE", name="Pepe", name_jp="ペペ",
        category="Meme",
        summary="カエルキャラクターをモチーフにしたミームコイン。2023年launchで時価総額数十億ドル規模まで成長。",
        search_keywords=["pepe", "ペペ"],
    ),
    CryptoToken(
        slug="wif", symbol="WIF", name="Dogwifhat", name_jp="ドッグウィズハット",
        category="Meme",
        summary="Solana発のミームコイン。ピンクの帽子を被った犬の画像。2024年に大きく上昇しSolanaミームブームを象徴。",
        search_keywords=["dogwifhat", "wif", "ウィズハット"],
    ),
    CryptoToken(
        slug="bonk", symbol="BONK", name="Bonk", name_jp="ボンク",
        category="Meme",
        summary="Solana初の本格ミームコイン。2022年末リリース、SolanaコミュニティへのエアドロップでDEX出来高を一時急増させた。",
        search_keywords=["bonk", "ボンク"],
    ),
]
