"""
エアドロップ記事用のキュレート済みトピックリスト。

各トピックは「プロジェクト解説」または「汎用ガイド」のいずれか。
プロジェクト単位の重複防止のため slug を frontmatter に保存する。
"""

from dataclasses import dataclass


@dataclass
class AirdropTopic:
    slug: str               # 記事ファイル名・dedupキー（一意）
    kind: str               # "project" | "guide"
    title_hint: str         # 記事タイトルのヒント（Claudeが最終化）
    summary: str            # 記事の主眼（プロンプトへ渡すコンテキスト）
    audience: str           # "beginner" | "intermediate"
    project_name: str = ""  # kind="project" のとき
    project_url: str = ""   # 公式URL
    # ニュース検索用のキーワード群（プロジェクト名以外の表記揺れ・関連トークン名）
    # 例: Linea → ["linea", "lxp", "consensys"]
    search_keywords: list[str] = None  # type: ignore


# ----------------------------------------------------------------------
# プロジェクト解説（チェーン・DeFi・インフラ別）
# ----------------------------------------------------------------------
PROJECT_TOPICS: list[AirdropTopic] = [
    # --- L2 / Rollup ---
    AirdropTopic(
        slug="linea", kind="project", project_name="Linea",
        project_url="https://linea.build",
        title_hint="Lineaエアドロップ完全ガイド",
        summary="ConsenSysが開発するEthereum zkEVM L2。MetaMask統合・LXP（Linea Voyageポイント）獲得が期待値の高い活動。ブリッジ・スワップ・DeFi利用が定番タスク。LXPはオンチェーンスコアの可能性あり。",
        audience="intermediate",
        search_keywords=["linea", "lxp", "consensys", "ライニア"],
    ),
    AirdropTopic(
        slug="scroll", kind="project", project_name="Scroll",
        project_url="https://scroll.io",
        title_hint="Scrollエアドロップ参加方法とポイント獲得戦略",
        summary="Ethereum zkRollup L2。Scroll Marksというポイント制度を採用。ブリッジ→DEX・レンディング利用でMarks獲得。エコシステム参加者向けの広範な配布が期待されている。",
        audience="intermediate",
        search_keywords=["scroll", "scroll marks", "スクロール"],
    ),
    AirdropTopic(
        slug="zksync", kind="project", project_name="zkSync Era",
        project_url="https://zksync.io",
        title_hint="zkSync Era エアドロップの現状と次の動向",
        summary="Matter Labs開発のzk L2。2024年6月にZKトークンを配布済みだが、エコシステムプロジェクト（個別dApp）のエアドロップは継続中。zkSync上のdAppタスクが新たな狩場。",
        audience="intermediate",
        search_keywords=["zksync", "zk era", "matter labs"],
    ),
    AirdropTopic(
        slug="base", kind="project", project_name="Base",
        project_url="https://base.org",
        title_hint="Base（Coinbase L2）の関連エアドロップ戦略",
        summary="Coinbase運営のOP Stack L2。Base自体のトークンは未発表だが、エコシステムプロジェクト（Aerodrome、Friend.tech等）のエアドロップが活発。",
        audience="intermediate",
        search_keywords=["base chain", "coinbase l2", "aerodrome"],
    ),
    AirdropTopic(
        slug="taiko", kind="project", project_name="Taiko",
        project_url="https://taiko.xyz",
        title_hint="Taikoエアドロップ：ZKロールアップ参加のチャンス",
        summary="完全互換性を持つType-1 zkEVM。トークンTAIKOは2024年配布済みだが、Loyalty Program継続。テストネット参加者向けの追加配布も観測されている。",
        audience="intermediate",
        search_keywords=["taiko", "タイコ"],
    ),
    AirdropTopic(
        slug="megaeth", kind="project", project_name="MegaETH",
        project_url="https://www.megaeth.com",
        title_hint="MegaETHエアドロップ期待値と早期参加方法",
        summary="リアルタイム処理を狙う新興L2。テストネット参加・コミュニティ貢献が主要タスク。Polymarketでもメインネット launch オッズが取引されるほど注目度高い。",
        audience="intermediate",
        search_keywords=["megaeth", "mega eth"],
    ),
    AirdropTopic(
        slug="monad", kind="project", project_name="Monad",
        project_url="https://www.monad.xyz",
        title_hint="Monadエアドロップ完全攻略：testnet参加から本番まで",
        summary="EVM互換高速L1。Paradigm主導の資金調達で注目集める。テストネット参加者・ディスコード活動が主な期待値タスク。",
        audience="intermediate",
        search_keywords=["monad", "モナド"],
    ),
    AirdropTopic(
        slug="berachain", kind="project", project_name="Berachain",
        project_url="https://berachain.com",
        title_hint="Berachainエアドロップ：Proof-of-LiquidityチェーンのBGT戦略",
        summary="Proof-of-Liquidity採用の新興L1。BGTトークン仕組みが特徴的。テストネット参加・The Honey Jar NFT保有が代表的な期待値タスク。",
        audience="intermediate",
        search_keywords=["berachain", "bera", "honey jar"],
    ),

    # --- リキッドステーキング / Restaking ---
    AirdropTopic(
        slug="eigenlayer", kind="project", project_name="EigenLayer",
        project_url="https://www.eigenlayer.xyz",
        title_hint="EigenLayerのRestaking活用とAVSエアドロップ攻略",
        summary="Ethereumのリステーキング基盤。EIGENトークンを既に配布したが、EigenLayer上のAVS（AltLayer、Renzo等）から続々とエアドロップが出ている状況。",
        audience="intermediate",
        search_keywords=["eigenlayer", "eigen", "restaking", "リステーキング"],
    ),
    AirdropTopic(
        slug="ether-fi", kind="project", project_name="ether.fi",
        project_url="https://www.ether.fi",
        title_hint="ether.fiの ETHFI ポイント仕組みとエアドロップハント",
        summary="リキッドリステーキングプロトコル。Loyalty Points・eETH保有でポイント獲得。Season 2 / 3 と継続的にエアドロップ実施。",
        audience="intermediate",
        search_keywords=["ether.fi", "etherfi", "ethfi", "eeth"],
    ),
    AirdropTopic(
        slug="renzo", kind="project", project_name="Renzo",
        project_url="https://www.renzoprotocol.com",
        title_hint="RenzoのezETHステーキングとREZエアドロップ参加",
        summary="EigenLayer上のリキッドリステーキング。ezETH預入でRenzo PointsとEigenLayer Pointsの両方を獲得できる「二重取り」が魅力。",
        audience="intermediate",
        search_keywords=["renzo", "ezeth", "rez"],
    ),
    AirdropTopic(
        slug="symbiotic", kind="project", project_name="Symbiotic",
        project_url="https://symbiotic.fi",
        title_hint="Symbioticエアドロップ：EigenLayer対抗の新Restaking基盤",
        summary="Lido・Cyber・Paradigm支援のリステーキング新プロトコル。Cap upgrade時の早期参加が期待値高。",
        audience="intermediate",
        search_keywords=["symbiotic", "シンビオティック"],
    ),

    # --- DeFi / Trading ---
    AirdropTopic(
        slug="hyperliquid", kind="project", project_name="Hyperliquid",
        project_url="https://hyperliquid.xyz",
        title_hint="Hyperliquid HYPE 配布後の状況とSpot取引でのポイント獲得",
        summary="独自L1 + perp DEX。HYPEトークン配布は2024年だが、現在もユーザーポイントで継続配布。スポット取引・perp取引がポイントタスク。",
        audience="intermediate",
        search_keywords=["hyperliquid", "hype", "ハイパーリキッド"],
    ),
    AirdropTopic(
        slug="pendle", kind="project", project_name="Pendle",
        project_url="https://www.pendle.finance",
        title_hint="Pendleの利回りトークン化を活用したエアドロップ最大化",
        summary="利回りをPT（元本）とYT（利回り）に分離するプロトコル。LRT・LSTのPT/YT取引で他プロジェクトのポイントを効率的に獲得できる。",
        audience="intermediate",
        search_keywords=["pendle", "ペンドル"],
    ),
    AirdropTopic(
        slug="jupiter", kind="project", project_name="Jupiter",
        project_url="https://jup.ag",
        title_hint="Jupiter（Solana DEXアグリゲータ）の継続エアドロップ戦略",
        summary="Solana最大手DEXアグリゲータ。JUPトークンの追加配布シーズンが継続。スワップ・LFG launchpad参加がタスク。",
        audience="intermediate",
        search_keywords=["jupiter", "jup", "ジュピター"],
    ),

    # --- インフラ ---
    AirdropTopic(
        slug="layerzero", kind="project", project_name="LayerZero",
        project_url="https://layerzero.network",
        title_hint="LayerZero ZRO 配布後のクロスチェーンエアドロップ動向",
        summary="主要なオムニチェーンメッセージングプロトコル。ZROトークン2024年配布。今後はLayerZeroを使う各dAppのエアドロップ参加が現実的。",
        audience="beginner",
        search_keywords=["layerzero", "zro", "オムニチェーン"],
    ),
    AirdropTopic(
        slug="wormhole", kind="project", project_name="Wormhole",
        project_url="https://wormhole.com",
        title_hint="Wormholeブリッジ利用と W トークン関連プロジェクト攻略",
        summary="マルチチェーンメッセージング。Wトークン配布済みだが、Wormhole経由のプロジェクト関連エアドロップが継続。",
        audience="beginner",
        search_keywords=["wormhole", "ワームホール"],
    ),

    # --- Social / Wallet ---
    AirdropTopic(
        slug="farcaster", kind="project", project_name="Farcaster",
        project_url="https://www.farcaster.xyz",
        title_hint="Farcaster登録方法とdApp連携でのエアドロップ機会",
        summary="分散型ソーシャルプロトコル。FIDアカウント所有者向けのdApp配布（Degen、Moxie等）が活発。",
        audience="beginner",
        search_keywords=["farcaster", "degen", "moxie", "ファーキャスター"],
    ),
    AirdropTopic(
        slug="hyperliquid-ecosystem", kind="project", project_name="Hyperliquid Ecosystem",
        project_url="https://hyperliquid.xyz",
        title_hint="Hyperliquid上のmemeコイン・新プロジェクトエアドロップ早分かり",
        summary="HyperliquidのHIP-1上場プロジェクト群。早期取引・流動性提供がチャンス。",
        audience="intermediate",
        search_keywords=["hyperliquid", "hip-1", "hype spot"],
    ),

    # --- Solana系 ---
    AirdropTopic(
        slug="sonic-svm", kind="project", project_name="Sonic SVM",
        project_url="https://sonic.game",
        title_hint="Sonic SVM（Solana L2）のエアドロップ攻略法",
        summary="Solana初のSVM L2。ゲームdApp向けに特化。テストネット参加・取引がタスク。",
        audience="intermediate",
        search_keywords=["sonic svm", "sonic chain"],
    ),
]


# ----------------------------------------------------------------------
# 汎用ガイド（プロジェクト非依存のハウツー記事）
# ----------------------------------------------------------------------
GUIDE_TOPICS: list[AirdropTopic] = [
    AirdropTopic(
        slug="guide-airdrop-basics", kind="guide",
        title_hint="エアドロップとは何か：初心者が知るべき基本と仕組み",
        summary="エアドロップの定義・歴史・代表事例（Uniswap、ARB、JUP等）・なぜプロジェクトが配布するのか（マーケティング・分散化）・参加者にとっての利益と注意点。",
        audience="beginner",
    ),
    AirdropTopic(
        slug="guide-wallet-prep", kind="guide",
        title_hint="エアドロップハンター向け：ウォレット準備の完全ガイド",
        summary="MetaMask・Phantom・Rabbyの違いと使い分け・複数アドレス管理のベストプラクティス・シードフレーズ管理・ハードウェアウォレット推奨度・OPSEC基礎。",
        audience="intermediate",
    ),
    AirdropTopic(
        slug="guide-sybil-avoidance", kind="guide",
        title_hint="Sybil検知を避けるためのエアドロップハント基本作法",
        summary="Sybil farmingとは・どう検知されるか（ガス支払いウォレットの追跡、行動パターン）・除外を避ける合法的なアプローチ・実際に検知されたケーススタディ。",
        audience="intermediate",
    ),
    AirdropTopic(
        slug="guide-tax-japan", kind="guide",
        title_hint="エアドロップに関する日本の税金処理：実務的Q&A",
        summary="エアドロップ受領時の所得税課税タイミング（受領 vs 売却）・雑所得の計算方法・取得価額の決め方・税務当局見解・実務的な対応。",
        audience="beginner",
    ),
    AirdropTopic(
        slug="guide-scam-detection", kind="guide",
        title_hint="偽エアドロップ・フィッシング詐欺の見抜き方",
        summary="代表的な詐欺パターン（DM経由・偽サイト・トークン承認罠）・実例・対策（公式URL確認・承認チェック・revoke方法）・被害時の対処。",
        audience="beginner",
    ),
    AirdropTopic(
        slug="guide-points-meta", kind="guide",
        title_hint="ポイントシステム時代のエアドロップ戦略：効率的に複数プロジェクトを追う",
        summary="Loyalty Points方式が主流になった背景・代表プロジェクトの比較・ポイント獲得効率の比較・時間と資金配分の考え方。",
        audience="intermediate",
    ),
    AirdropTopic(
        slug="guide-retroactive-vs-active", kind="guide",
        title_hint="遡及型 vs 公表型エアドロップ：参加戦略の違い",
        summary="未公表・遡及型（UNI/ARB型）と公表・タスク型（Optimism/zkSync型）の違い・どちらが期待値高いか・両方を併走する具体例。",
        audience="intermediate",
    ),
    AirdropTopic(
        slug="guide-testnet-strategy", kind="guide",
        title_hint="テストネット参加から最大限のエアドロップ期待値を引き出す方法",
        summary="現在期待値の高いテストネット（Monad/MegaETH/Berachain等）・参加コスト・実際の操作手順・複数アカウントの是非。",
        audience="intermediate",
    ),
]


ALL_TOPICS: list[AirdropTopic] = PROJECT_TOPICS + GUIDE_TOPICS
