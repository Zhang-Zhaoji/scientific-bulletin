from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt


DEFAULT_INPUT_DIR = Path("LLM_Results")
DEFAULT_OUTPUT_DIR = Path("Imgs") / "visulize_img" / "statistics"


def result_date(path: Path) -> str:
    match = re.search(r"LLM_results_(\d{4})(\d{2})(\d{2})", path.stem)
    if not match:
        raise ValueError(f"Cannot infer date from {path}")
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def score_distribution(results: list[dict]) -> list[tuple[str, int]]:
    bins = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10)]
    counts = [0] * len(bins)

    for result in results:
        if result.get("domain") == "域外局限":
            continue
        score = result.get("total_score", 0) or 0
        for idx, (low, high) in enumerate(bins):
            if low <= score < high:
                counts[idx] += 1
                break

    return [(f"{low}-{high}", count) for (low, high), count in zip(bins, counts) if count > 0]


def render_histogram(distribution: list[tuple[str, int]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    x_data = [item[0] for item in distribution]
    y_data = [item[1] for item in distribution]

    plt.figure(figsize=(10, 6))
    bars = plt.bar(x_data, y_data, color="#8ecae6")
    plt.title("Score distribution", fontsize=14)
    plt.xlabel("Score range", fontsize=12)
    plt.ylabel("Article count", fontsize=12)

    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{int(height)}",
            ha="center",
            va="bottom",
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def generate_histogram(result_path: Path, output_dir: Path, overwrite: bool = False) -> Path | None:
    date = result_date(result_path)
    output_path = output_dir / f"{date}_score_histogram.png"
    if output_path.exists() and not overwrite:
        return None

    with result_path.open("r", encoding="utf-8") as f:
        results = json.load(f)

    render_histogram(score_distribution(results), output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate score histogram PNGs from LLM result JSON files.")
    parser.add_argument("inputs", nargs="*", type=Path, help="Specific LLM_results_YYYYMMDD_*.json files.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    result_paths = args.inputs or sorted(args.input_dir.glob("LLM_results_*.json"))
    written = []
    for result_path in result_paths:
        output_path = generate_histogram(result_path, args.output_dir, overwrite=args.overwrite)
        if output_path:
            written.append(output_path)

    for output_path in written:
        print(output_path)


if __name__ == "__main__":
    main()
