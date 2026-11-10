"""Load public A/B datasets into DuckDB and print a readout for each (CLI output)."""

import sys
import time
from pathlib import Path

import duckdb

from splitkit.analysis import analyze_experiment, duckdb_fetcher
from splitkit.datasets.loaders import load_cookie_cats, load_criteo, load_udacity
from splitkit.db.schema import create_schema
from splitkit.metrics.spec import load_metrics

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DATASETS = [
    ("cookie_cats", load_cookie_cats, RAW / "cookie_cats/cookie_cats.csv", "gate_30", "gate_40", (0.5, 0.5)),
    ("udacity_landing", load_udacity, RAW / "udacity/ab_data.csv", "control", "treatment", (0.5, 0.5)),
    ("criteo_uplift", load_criteo, RAW / "criteo/criteo-uplift-v2.1.csv", "control", "treatment", (0.15, 0.85)),
]


def out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def main() -> int:
    db = ROOT / "data" / "splitkit.duckdb"
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    create_schema(con)
    for key, loader, path, ctrl, trt, weights in DATASETS:
        t = time.perf_counter()
        loader(con, path)
        load_s = time.perf_counter() - t
        metrics = load_metrics((ROOT / "config/metrics" / f"{key}.yaml").read_text())
        t = time.perf_counter()
        rep = analyze_experiment(duckdb_fetcher(con), key, metrics, ctrl, trt, weights=weights)
        analyze_s = time.perf_counter() - t
        out(f"\n== {key}  users={rep.counts}  load={load_s:.1f}s  analyze={analyze_s:.2f}s")
        out(f"   SRM p={rep.srm.p_value:.4g}  {'BLOCKED' if rep.blocked else 'ok'}")
        for m in rep.metrics:
            r = m.result
            out(f"   {m.metric:<12} {ctrl}={r.mean_a:.5g} {trt}={r.mean_b:.5g} "
                f"lift={r.abs_lift:+.4g} ({r.rel_lift:+.1%}) CI=[{r.ci_low:+.4g}, {r.ci_high:+.4g}] "
                f"p={r.p_value:.3g} p_bh={m.adjusted_p:.3g} {'SIGNIFICANT' if m.significant else ''}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
