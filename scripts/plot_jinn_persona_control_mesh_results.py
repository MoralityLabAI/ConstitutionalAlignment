#!/usr/bin/env python3
"""Render the confirmatory and exploratory control-mesh result figure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirmatory", type=Path, required=True)
    parser.add_argument("--exploratory", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()

    import matplotlib.pyplot as plt
    import numpy as np

    confirmatory = load_json(args.confirmatory)
    exploratory = load_json(args.exploratory)
    surfaces = confirmatory["surfaces"]
    interface = exploratory["surfaces"]
    cell_order = (
        ("base_jinn", "base_beast"),
        ("checkpoint_100_jinn", "checkpoint_100_beast"),
    )
    protocol = [
        [float(surfaces[cell]["protocol_complete_rate"]) for cell in group]
        for group in cell_order
    ]
    executable = [
        [
            float(interface[cell]["first_turn_executable_after_shim_rate"])
            for cell in group
        ]
        for group in cell_order
    ]

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
        }
    )
    figure, axes = plt.subplots(1, 2, figsize=(7.2, 3.15), sharey=True)
    colors = ("#496A9A", "#C17C3A")
    labels = ("Jinn membrane", "Beast membrane")
    x = np.arange(2)
    width = 0.34

    for axis, values, title, panel in (
        (
            axes[0],
            protocol,
            "Protocol completion",
            "A  Confirmatory strict interface",
        ),
        (
            axes[1],
            executable,
            "Executable first call",
            "B  Exploratory typed shim",
        ),
    ):
        for index, (label, color) in enumerate(zip(labels, colors, strict=True)):
            heights = [group[index] for group in values]
            positions = x + (index - 0.5) * width
            bars = axis.bar(
                positions,
                heights,
                width,
                label=label,
                color=color,
                edgecolor="#222222",
                linewidth=0.6,
            )
            for bar, height in zip(bars, heights, strict=True):
                axis.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + 0.025,
                    f"{height * 100:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
        axis.set_xticks(x, ("Base", "Checkpoint-100"))
        axis.set_ylim(0, 0.82)
        axis.set_title(f"{panel}\n{title}", loc="left")
        axis.grid(axis="y", color="#D8D8D8", linewidth=0.6)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Rate")
    axes[0].set_yticks(
        np.linspace(0, 0.8, 5),
        tuple(f"{value:.0%}" for value in np.linspace(0, 0.8, 5)),
    )
    axes[1].legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.17),
        ncol=2,
    )
    axes[0].text(
        0.02,
        0.97,
        "Primary interaction:\n-15.3 pp [-32.6, 2.1]",
        transform=axes[0].transAxes,
        fontsize=7.5,
        va="top",
    )
    axes[1].text(
        0.02,
        0.97,
        "Adapter Jinn-Beast:\n+40.3 pp [31.3, 48.6]",
        transform=axes[1].transAxes,
        fontsize=7.5,
        va="top",
    )
    figure.tight_layout()
    figure.subplots_adjust(bottom=0.24, wspace=0.2)
    for output in (args.png.resolve(), args.svg.resolve()):
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
