from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


DEFAULT_INPUT = Path("results/results.csv")
DEFAULT_OUTPUT = Path("results")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate benchmark plots from results.csv")
	parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="CSV file produced by runner.py")
	parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directory for generated PNG files")
	return parser.parse_args()


def read_results(path: Path) -> pd.DataFrame:
	dataframe = pd.read_csv(path)
	if dataframe.empty:
		raise ValueError(f"No rows found in {path}.")
	return dataframe


def pareto_frontier(dataframe: pd.DataFrame) -> pd.DataFrame:
	frontier_rows = []
	for _, candidate in dataframe.sort_values(["latency_p50_ms", "recall_at_10"], ascending=[True, False]).iterrows():
		dominated = False
		for _, other in dataframe.iterrows():
			if other.name == candidate.name:
				continue
			better_or_equal_recall = other["recall_at_10"] >= candidate["recall_at_10"]
			better_or_equal_latency = other["latency_p50_ms"] <= candidate["latency_p50_ms"]
			strictly_better = (
				other["recall_at_10"] > candidate["recall_at_10"]
				or other["latency_p50_ms"] < candidate["latency_p50_ms"]
			)
			if better_or_equal_recall and better_or_equal_latency and strictly_better:
				dominated = True
				break
		if not dominated:
			frontier_rows.append(candidate)
	return pd.DataFrame(frontier_rows).sort_values("latency_p50_ms")


def save_pareto_plot(dataframe: pd.DataFrame, output_path: Path) -> None:
	fig, ax = plt.subplots(figsize=(10, 6))
	for _, row in dataframe.iterrows():
		label = f"{row['db']}"
		ax.scatter(row["latency_p50_ms"], row["recall_at_10"], s=90)
		ax.annotate(label, (row["latency_p50_ms"], row["recall_at_10"]), xytext=(5, 5), textcoords="offset points")

	frontier = pareto_frontier(dataframe)
	if not frontier.empty:
		ax.plot(frontier["latency_p50_ms"], frontier["recall_at_10"], linestyle="--", linewidth=1.5, color="black")

	ax.set_title("Pareto Frontier: Recall@10 vs Latency P50")
	ax.set_xlabel("Latency P50 (ms)")
	ax.set_ylabel("Recall@10")
	ax.grid(alpha=0.3)
	fig.tight_layout()
	fig.savefig(output_path, dpi=200)
	plt.close(fig)


def save_latency_plot(dataframe: pd.DataFrame, output_path: Path) -> None:
	plot_df = dataframe[["db", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"]].set_index("db")
	fig, ax = plt.subplots(figsize=(11, 6))
	plot_df.plot(kind="bar", ax=ax)
	ax.set_title("Latency Comparison")
	ax.set_xlabel("Backend")
	ax.set_ylabel("Latency (ms)")
	ax.legend(["p50", "p95", "p99"])
	ax.grid(axis="y", alpha=0.3)
	fig.tight_layout()
	fig.savefig(output_path, dpi=200)
	plt.close(fig)


def save_disk_plot(dataframe: pd.DataFrame, output_path: Path) -> None:
	fig, ax = plt.subplots(figsize=(10, 6))
	ax.bar(dataframe["db"], dataframe["disk_mb"], color="#4C78A8")
	ax.set_title("Index Disk Size")
	ax.set_xlabel("Backend")
	ax.set_ylabel("Disk Size (MB)")
	ax.grid(axis="y", alpha=0.3)
	fig.tight_layout()
	fig.savefig(output_path, dpi=200)
	plt.close(fig)


def save_table_plot(dataframe: pd.DataFrame, output_path: Path) -> None:
	columns = [
		"db",
		"model",
		"index_time_sec",
		"disk_mb",
		"latency_p50_ms",
		"latency_p95_ms",
		"latency_p99_ms",
		"recall_at_10",
		"mrr_at_10",
	]
	display_df = dataframe[columns].copy()
	fig_height = max(3, 0.45 * (len(display_df) + 1))
	fig, ax = plt.subplots(figsize=(14, fig_height))
	ax.axis("off")
	table = ax.table(
		cellText=display_df.values,
		colLabels=display_df.columns,
		loc="center",
		cellLoc="center",
	)
	table.auto_set_font_size(False)
	table.set_fontsize(9)
	table.scale(1, 1.4)
	ax.set_title("Benchmark Results Table", pad=16)
	fig.tight_layout()
	fig.savefig(output_path, dpi=200, bbox_inches="tight")
	plt.close(fig)


def main() -> None:
	args = parse_args()
	args.output.mkdir(parents=True, exist_ok=True)
	results = read_results(args.input)

	save_pareto_plot(results, args.output / "pareto_frontier.png")
	save_latency_plot(results, args.output / "latency_distribution.png")
	save_disk_plot(results, args.output / "disk_size_chart.png")
	save_table_plot(results, args.output / "results_table.png")

	print(f"Generated pareto plot -> {args.output / 'pareto_frontier.png'}")
	print(f"Generated latency plot -> {args.output / 'latency_distribution.png'}")
	print(f"Generated disk size plot -> {args.output / 'disk_size_chart.png'}")
	print(f"Generated results table -> {args.output / 'results_table.png'}")


if __name__ == "__main__":
	main()
