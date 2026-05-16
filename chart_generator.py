"""
Chart generator.

入力:  Market オブジェクト
出力:  output/charts/{condition_id}.png  (記事に埋め込むグラフ画像)
"""

import datetime
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # ヘッドレス環境向け
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

# Windows日本語フォントを優先的に設定
_JP_FONTS = ["Yu Gothic", "Meiryo", "MS Gothic", "TakaoPGothic", "IPAexGothic"]
for _f in _JP_FONTS:
    if any(_f.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = _f
        break

from config import CHARTS_DIR
from polymarket_scraper import Market

logger = logging.getLogger(__name__)

COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed"]


def _ts_to_dt(ts: int | float) -> datetime.datetime:
    return datetime.datetime.utcfromtimestamp(ts)


def generate_chart(market: Market) -> Path:
    """
    オッズ推移折れ線グラフを生成して PNG パスを返す。
    複数トークン（Yes/No 両方）を重ねてプロット。
    """
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    plotted = 0
    for i, tok in enumerate(market.tokens):
        if not tok.history:
            continue
        xs = [_ts_to_dt(p["t"]) for p in tok.history]
        ys = [float(p["p"]) * 100 for p in tok.history]   # → 0-100%

        ax.plot(
            xs, ys,
            label=tok.outcome,
            color=COLORS[i % len(COLORS)],
            linewidth=2,
        )
        # 最新値をラベルで表示
        if ys:
            ax.annotate(
                f"{ys[-1]:.1f}%",
                xy=(xs[-1], ys[-1]),
                xytext=(6, 0),
                textcoords="offset points",
                color=COLORS[i % len(COLORS)],
                fontsize=9,
            )
        plotted += 1

    if plotted == 0:
        plt.close(fig)
        raise ValueError(f"No history data for market {market.condition_id}")

    # 軸・装飾
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    fig.autofmt_xdate()

    ax.set_ylim(0, 100)
    ax.set_ylabel("確率 (%)", color="#94a3b8")
    ax.tick_params(colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")

    ax.yaxis.grid(True, color="#334155", linestyle="--", linewidth=0.5)
    ax.set_axisbelow(True)

    title = market.question if len(market.question) <= 60 else market.question[:57] + "…"
    ax.set_title(title, color="#f1f5f9", fontsize=11, pad=10)

    legend = ax.legend(
        facecolor="#334155",
        edgecolor="none",
        labelcolor="#f1f5f9",
        fontsize=9,
    )

    plt.tight_layout()

    out_path = CHARTS_DIR / f"{market.condition_id}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    logger.info("Chart saved → %s", out_path)
    return out_path


if __name__ == "__main__":
    # 動作確認用：ダミーデータでグラフ生成
    import time
    from polymarket_scraper import TokenHistory, Market

    now = int(time.time())
    dummy_history = [
        {"t": now - (7 - i) * 86400, "p": 0.45 + i * 0.03}
        for i in range(8)
    ]
    market = Market(
        condition_id="test",
        question="Will BTC exceed $100,000 by end of 2025?",
        category="crypto",
        end_date="2025-12-31",
        volume=1_200_000,
        tokens=[TokenHistory("tok_yes", "Yes", dummy_history),
                TokenHistory("tok_no",  "No",  [{"t": h["t"], "p": 1 - h["p"]} for h in dummy_history])],
    )
    path = generate_chart(market)
    print(f"Generated: {path}")
