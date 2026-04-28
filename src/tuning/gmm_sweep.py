"""
GMM hyperparameter sweep: raw 896-dim vs PCA-reduced 50-dim embeddings.

Fits GMM at each K in K_VALUES under both conditions and records:
  BIC, AIC, log-likelihood, convergence, wall-clock time.

Outputs (written to --output-dir):
  gmm_sweep_results.csv  — full results table
  gmm_sweep_plot.png     — BIC and AIC curves side-by-side

Run from project root:
    python -m src.tuning.gmm_sweep

Flags:
    --k-values 8 16 32 64 128   override sweep values
    --pca-dims 50               PCA dimensionality for the reduced condition
    --n-init 3                  EM random restarts per fit (higher = more reliable)
    --quick                     n-init=1 for a fast sanity-check run
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

EMBEDDINGS_DIR = Path("embeddings/metart")
DEFAULT_K_VALUES = [8, 16, 32, 48, 64, 80, 96, 128, 160, 192, 256, 320, 384, 512]
DEFAULT_PCA_DIMS = 50
DEFAULT_OUTPUT_DIR = Path("src/tuning/results")


def fit_and_score(
    X: np.ndarray,
    k: int,
    n_init: int,
    random_state: int,
    reg_covar: float,
) -> dict:
    gmm = GaussianMixture(
        n_components=k,
        covariance_type="diag",
        max_iter=300,
        n_init=n_init,
        random_state=random_state,
        reg_covar=reg_covar,
        verbose=0,
    )
    t0 = time.perf_counter()
    gmm.fit(X)
    elapsed = time.perf_counter() - t0
    return {
        "bic": gmm.bic(X),
        "aic": gmm.aic(X),
        "log_likelihood": gmm.score(X) * len(X),   # total, not per-sample
        "log_likelihood_per_sample": gmm.score(X),
        "converged": gmm.converged_,
        "n_iter": gmm.n_iter_,
        "time_s": round(elapsed, 2),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GMM K-sweep: raw vs PCA-reduced")
    p.add_argument("--embedding-dir", type=Path, default=EMBEDDINGS_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument(
        "--k-values", nargs="+", type=int, default=DEFAULT_K_VALUES,
        metavar="K", help="K values to sweep",
    )
    p.add_argument("--pca-dims", type=int, default=DEFAULT_PCA_DIMS)
    p.add_argument("--n-init", type=int, default=3)
    p.add_argument("--reg-covar", type=float, default=1e-3)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument(
        "--quick", action="store_true",
        help="Use n-init=1 for a fast sanity-check run",
    )
    p.add_argument(
        "--conditions", nargs="+", default=["raw", "pca"],
        choices=["raw", "pca"],
        help="Which conditions to run (default: both)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    n_init = 1 if args.quick else args.n_init
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading joint embeddings...")
    emb = np.load(args.embedding_dir / "joint_embeddings.npy").astype(np.float64)
    n, d = emb.shape
    print(f"  {n:,} embeddings × {d} dims")

    print("Standardizing...")
    scaler = StandardScaler()
    X_raw = scaler.fit_transform(emb)

    X_pca = None
    if "pca" in args.conditions:
        print(f"Fitting PCA {d}d → {args.pca_dims}d...")
        pca = PCA(n_components=args.pca_dims, random_state=args.random_state)
        X_pca = pca.fit_transform(X_raw)
        var = pca.explained_variance_ratio_.sum()
        print(f"  Variance retained: {var:.1%}")

    rows: list[dict] = []
    k_values = sorted(args.k_values)

    for k in k_values:
        if "raw" in args.conditions:
            print(f"\nK={k:3d}  [raw {d}d]  n_init={n_init} ...", flush=True)
            result = fit_and_score(
                X_raw, k, n_init, args.random_state, args.reg_covar
            )
            rows.append({"k": k, "condition": "raw", **result})
            print(
                f"  BIC={result['bic']:,.0f}  AIC={result['aic']:,.0f}"
                f"  ll/sample={result['log_likelihood_per_sample']:.2f}"
                f"  converged={result['converged']}  {result['time_s']}s"
            )

        if "pca" in args.conditions and X_pca is not None:
            print(f"K={k:3d}  [pca {args.pca_dims}d]  n_init={n_init} ...", flush=True)
            result = fit_and_score(
                X_pca, k, n_init, args.random_state, args.reg_covar
            )
            rows.append({"k": k, "condition": f"pca{args.pca_dims}", **result})
            print(
                f"  BIC={result['bic']:,.0f}  AIC={result['aic']:,.0f}"
                f"  ll/sample={result['log_likelihood_per_sample']:.2f}"
                f"  converged={result['converged']}  {result['time_s']}s"
            )

    df = pd.DataFrame(rows)
    csv_path = args.output_dir / "gmm_sweep_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved results → {csv_path}")

    # ── Plot ──────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(
        f"GMM sweep — joint embeddings ({n:,} points)\n"
        f"covariance=diag, n_init={n_init}, reg_covar={args.reg_covar}",
        fontsize=12,
    )

    conditions = df["condition"].unique()
    colors = {"raw": "#c41e3a", f"pca{args.pca_dims}": "#1e6fc4"}
    labels = {"raw": f"Raw {d}d", f"pca{args.pca_dims}": f"PCA {args.pca_dims}d"}

    for metric, ax, title in [
        ("bic", axes[0], "BIC (lower = better)"),
        ("aic", axes[1], "AIC (lower = better)"),
        ("log_likelihood_per_sample", axes[2], "Log-likelihood per sample (higher = better)"),
    ]:
        for cond in conditions:
            sub = df[df["condition"] == cond].sort_values("k")
            ax.plot(
                sub["k"], sub[metric],
                marker="o", label=labels.get(cond, cond),
                color=colors.get(cond, "gray"),
            )
        ax.set_xlabel("K (n_components)")
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
        # Mark the best K for each condition
        for cond in conditions:
            sub = df[df["condition"] == cond].sort_values("k")
            if metric == "log_likelihood_per_sample":
                best_idx = sub[metric].idxmax()
            else:
                best_idx = sub[metric].idxmin()
            best_row = sub.loc[best_idx]
            ax.axvline(
                best_row["k"], color=colors.get(cond, "gray"),
                linestyle="--", alpha=0.4, linewidth=1,
            )

    plt.tight_layout()
    plot_path = args.output_dir / "gmm_sweep_plot.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    print(f"Saved plot     → {plot_path}")

    # ── Summary table ─────────────────────────────────────────────────────
    print("\n── Best K by BIC ──")
    for cond in conditions:
        sub = df[df["condition"] == cond]
        best = sub.loc[sub["bic"].idxmin()]
        print(f"  {labels.get(cond, cond):15s}  K={int(best['k'])}  BIC={best['bic']:,.0f}")

    print("\n── Best K by AIC ──")
    for cond in conditions:
        sub = df[df["condition"] == cond]
        best = sub.loc[sub["aic"].idxmin()]
        print(f"  {labels.get(cond, cond):15s}  K={int(best['k'])}  AIC={best['aic']:,.0f}")


if __name__ == "__main__":
    main()
