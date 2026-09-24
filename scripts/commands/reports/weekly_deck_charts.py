#!/usr/bin/env python3
"""Matplotlib visual renderers for the weekly dev deck.

Pure "data in -> PNG path out" helpers. matplotlib is imported at module load,
so callers must ensure it is installed (see weekly_deck._require_deps).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

# Palette tuned to the machine-local lab template (navy + orange) with status accents.
INK = "#1E293B"
MUTE = "#64748B"
GRID = "#E2E8F0"
BASE = "#94A3B8"
ACCENT = "#4F46E5"   # indigo (ours)
ACCENT2 = "#E8772E"  # orange (template accent)
GOOD = "#10B981"     # positive delta
BAD = "#EF4444"      # negative delta

_COLORS = {"accent": ACCENT, "accent2": ACCENT2, "good": GOOD, "bad": BAD, "ink": INK}

_KFONT_CANDIDATES = (
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)


def color_for(name: str) -> str:
    return _COLORS.get(name, ACCENT)


def configure_korean_font() -> str:
    """Register a CJK font for Korean glyphs; return the resolved family name."""
    for path in _KFONT_CANDIDATES:
        if Path(path).is_file():
            try:
                fm.fontManager.addfont(path)
                family = fm.FontProperties(fname=path).get_name()
                plt.rcParams["font.family"] = family
                plt.rcParams["axes.unicode_minus"] = False
                return family
            except Exception:
                break
    warnings.warn("Korean-capable font not found; Korean text may render as boxes.", stacklevel=2)
    plt.rcParams["axes.unicode_minus"] = False
    return plt.rcParams.get("font.family", ["sans-serif"])[0]


def render_kpi_strip(kpis: list[dict], out_path: Path, width_in: float = 10.0,
                     height_in: float = 1.7) -> Path:
    """Render KPI tiles: label, big colored number+unit, optional delta arrow."""
    configure_korean_font()
    n = max(1, len(kpis))
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=200)
    fig.patch.set_alpha(0)
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")
    value_texts = []
    for i, k in enumerate(kpis):
        col = color_for(k.get("color", "accent"))
        x = i + 0.06
        if i > 0:
            ax.plot([i, i], [0.12, 0.88], color=GRID, lw=1.2)
        ax.text(x, 0.82, str(k.get("label", "")), fontsize=11, color=MUTE, va="center", ha="left")
        vt = ax.text(x, 0.46, str(k.get("value", "")), fontsize=30, color=col, fontweight="bold",
                     va="center", ha="left")
        value_texts.append((vt, k))
        delta = k.get("delta")
        if delta:
            ax.text(x, 0.16, str(delta), fontsize=12, color=k.get("delta_color", MUTE),
                    va="center", ha="left", fontweight="bold")
    # Place unit just past each number using the actually-rendered text width.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    for vt, k in value_texts:
        unit = str(k.get("unit", ""))
        if not unit:
            continue
        bb = vt.get_window_extent(renderer=renderer)
        x_end = inv.transform((bb.x1, bb.y0))[0]
        ax.text(x_end + 0.02, 0.40, unit, fontsize=13, color=MUTE, va="center", ha="left")
    fig.savefig(out_path, transparent=True, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_trend_chart(trend: dict, out_path: Path, ylabel: str = "metric") -> Path:
    """Line chart: baseline vs ours over ordered experiments/time."""
    configure_korean_font()
    labels = trend.get("labels", [])
    ours = trend.get("ours", [])
    base = trend.get("baseline", [])
    fig, ax = plt.subplots(figsize=(8.0, 3.9), dpi=200)
    fig.patch.set_facecolor("white")
    xs = range(len(labels))
    if base:
        ax.plot(xs, base, "-o", color=BASE, lw=2.2, ms=5, label="baseline")
    ax.plot(xs, ours, "-o", color=ACCENT, lw=2.8, ms=6, label="ours")
    if base and ours:
        ax.fill_between(xs, base, ours, color=ACCENT, alpha=0.07)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=11, color="#475569")
    ax.legend(frameon=False, fontsize=10, loc="best")
    ax.grid(axis="y", color=GRID, lw=1)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#CBD5E1")
    ax.tick_params(colors=MUTE, labelsize=9)
    fig.tight_layout()
    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_delta_bars(deltas: list[dict], out_path: Path) -> Path:
    """Horizontal bars of per-experiment delta, green/red by sign."""
    configure_korean_font()
    deltas = list(deltas)[:12]
    names = [d.get("name", f"exp{i}") for i, d in enumerate(deltas)]
    vals = [float(d.get("delta", 0.0)) for d in deltas]
    colors = [GOOD if v >= 0 else BAD for v in vals]
    height = max(2.4, 0.45 * len(deltas) + 0.8)
    fig, ax = plt.subplots(figsize=(8.0, height), dpi=200)
    fig.patch.set_facecolor("white")
    ys = range(len(deltas))
    ax.barh(list(ys), vals, color=colors, height=0.6)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color="#CBD5E1", lw=1)
    for y, v in zip(ys, vals, strict=False):
        ax.text(v + (0.01 if v >= 0 else -0.01), y, f"{v:+.2f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=9, color=INK)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.tick_params(colors=MUTE, labelsize=9, length=0)
    fig.tight_layout()
    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out_path
