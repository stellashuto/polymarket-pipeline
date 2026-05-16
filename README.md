# Polymarket Pipeline

Polymarket予測市場データと仮想通貨ニュースを組み合わせて日本語記事を自動生成するパイプライン。

## セットアップ

```powershell
# 仮想環境（任意）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# APIキー
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
```

## 実行

```powershell
# ニュース要約記事を5本
python main.py news --limit 5

# 予測市場記事を2本（関連ニュース引用つき）
python main.py market --limit 2

# 両方一括
python main.py all --news-limit 5 --market-limit 2

# 取得対象だけ確認
python main.py all --dry-run

# サイトへの自動同期をスキップ
python main.py news --no-sync
```

## 構成

| ファイル | 役割 |
|---|---|
| `polymarket_scraper.py` | Polymarket Gamma/CLOB API スクレイパー |
| `news_scraper.py` | 仮想通貨RSSフィード収集 |
| `news_matcher.py` | マーケット質問と関連ニュースのマッチング |
| `article_draft.py` | 予測市場解説記事ジェネレータ（Flow B） |
| `news_article.py` | ニュース要約記事ジェネレータ（Flow A） |
| `site_sync.py` | 生成記事を Next.js サイトへ同期 |
| `main.py` | エントリポイント |

## 出力

- `output/articles/` — 生成記事（Markdown + frontmatter）
- `polymarket-site/content/articles/` — サイト用に自動同期される
