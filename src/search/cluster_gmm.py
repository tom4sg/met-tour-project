"""
GMM clustering over pre-built embedding spaces using a handwritten EM implementation.

For each space (clip, text, joint) this script:
  1. Loads the corresponding .npy file from --embedding-dir
  2. Fits the handwritten GaussianMixture model (diagonal covariance, k-means++ init)
  3. Assigns every point to its MAP cluster (argmax posterior)
  4. Saves the artifacts needed for cluster-filtered search:
       gmm_<space>.npz  — means (K×D), covariances (K×D), weights (K,),
                          assignments (N,), scaler_mean (D,), scaler_scale (D,)
       gmm_<space>_indices.json — {cluster_id: [row_indices]} for fast lookup

Example:
    python -m src.search.cluster_gmm --embedding-dir embeddings/metart --n-components 320
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from torch.distributions import Normal, Independent
from sklearn.preprocessing import StandardScaler
from tqdm.auto import tqdm


SPACES = {
    "clip": "clip_embeddings.npy",
    "text": "text_embeddings.npy",
    "joint": "joint_embeddings.npy",
}


# ── Handwritten GMM ────────────────────────────────────────────────────────────

class GMM:
    def __init__(self, K, max_iter=100, tol=1e-4, min_var=1e-6, device='cpu', seed=67):
        """
        K        : number of clusters
        max_iter : max EM iterations
        tol      : convergence threshold on log-likelihood change
        min_var  : variance floor to prevent cluster collapse
        device   : 'cuda' or 'cpu'
        """
        self.K = K
        self.max_iter = max_iter
        self.tol = tol
        self.min_var = min_var
        self.device = device
        self.seed = seed

        # set during fit()
        self.means = None        # (K, D)
        self.variances = None    # (K, D) — diagonal only, not full matrix
        self.weights = None      # (K,)


    # ------------------------------------------------------------------ #
    #  internal helpers (not called from outside)                        #
    # ------------------------------------------------------------------ #

    def _initialize_params(self, X_t):
        """
        Set initial values for means, variances, and weights
        before the EM loop begins.

        Initialize variances to the global variance of X_t along each dim.
        Initialize weights to uniform 1/K.

        Self note: This is like selecting the starter-build for the Gaussian clusters we want to fit onto the data

        Parameters
        ----------
        X_t : torch.Tensor, shape (N, D)
        """
        N, D = X_t.shape

        # ---- apply seed for reproducibility ----
        if self.seed is not None:
            torch.manual_seed(self.seed)
            np.random.seed(self.seed)

        # ---- initialize variances ----
        # use torch to get global variance across all N points, per dim
        self.variances = torch.clamp(torch.var(X_t, dim=0), min=self.min_var).repeat(self.K, 1)  # CHANGED/ADDED FOR SAVE FUNCTION

        # ---- initialize means with K-Means++ ----
        # 1) pick first mean randomly from data points
        first_idx = torch.randint(N, (1,)).item()
        chosen_indices = [first_idx]

        # 2) pick each remaining mean
        for _ in range(self.K - 1):
            # stack the already-chosen means -> (num_chosen, D)
            chosen_means = X_t[torch.tensor(chosen_indices, device=self.device)]

            # pairwise distances from every point to every chosen mean -> (N, num_chosen)
            dists = torch.cdist(X_t, chosen_means)

            # for each point, keep only the distance to its nearest chosen mean -> (N,)
            min_dists = dists.min(dim=1).values

            # sampling probability proportional to squared distance
            # far points are more likely to become the next mean
            probs = min_dists ** 2
            probs = probs / probs.sum()   # normalize to valid probability distribution

            # sample one index according to those probabilities
            next_idx = torch.multinomial(probs, num_samples=1).item()
            chosen_indices.append(next_idx)

        # --- means ---
        self.means = X_t[torch.tensor(chosen_indices, device=self.device)]  # (K, D)

        # ---- initialize weights ----
        # literally just makes a torch tensor of ones (like np.ones)
        self.weights = torch.ones(self.K, device=self.device) / self.K  # (K,) ; we do device=self.device because we want to make sure that the code operates on the correct hardware

        # ---- validate ----
        self._validate_params()

    # helper function for debugging ; can be called in m-step if we run into issues
    def _validate_params(self):
        if self.means is None:
            return
        D = self.means.shape[1]  # infer D from means directly

        # sanity checks
        if not torch.allclose(self.weights.sum(), torch.tensor(1.0, device=self.weights.device), atol=1e-4):
            raise ValueError(f"Weights do not sum to 1: {self.weights.sum().item()}")
        if self.means.shape != (self.K, D):
            raise ValueError(f"Means shape incorrect: {self.means.shape}")
        if self.variances.shape != (self.K, D):
            raise ValueError(f"Variances shape incorrect: {self.variances.shape}")

    def _compute_log_probs(self, X_t, chunk_size=512):
        """
        Essentially: For each data point, how likely is it under each Gaussian component?
                     If I assume component k generated this point, how plausible is it?

        Evaluate the diagonal Gaussian log-PDF for every point
        under every cluster. Does NOT include mixing weights.

        Uses Independent(Normal(mean_k, std_k), 1) for each cluster.
        Processes N in chunks to avoid materializing an (N, K, D) tensor
        that would exhaust RAM for large datasets.

        Parameters
        ----------
        X_t        : torch.Tensor, shape (N, D)
        chunk_size : int — rows of X_t to process at once

        Returns
        -------
        log_probs : torch.Tensor, shape (N, K)
        """
        # clamp variances to prevent scale=0 in Normal
        var = torch.clamp(self.variances, min=self.min_var)  # (K, D)
        std = torch.sqrt(var)                                 # (K, D)

        mu_exp  = self.means.unsqueeze(0)  # (1, K, D)
        std_exp = std.unsqueeze(0)         # (1, K, D)
        dist    = Independent(Normal(loc=mu_exp, scale=std_exp), 1)

        chunks = []
        for start in range(0, X_t.shape[0], chunk_size):
            x_chunk = X_t[start : start + chunk_size].unsqueeze(1)  # (chunk, 1, D)
            chunks.append(dist.log_prob(x_chunk))                    # (chunk, K)
        return torch.cat(chunks, dim=0)                              # (N, K)

    def _e_step(self, X_t):
        """
        Compute log-responsibilities for every point and cluster.

        Calls _compute_log_probs(), adds log mixing weights,
        then normalizes each row using logsumexp.

        Parameters
        ----------
        X_t : torch.Tensor, shape (N, D)

        Returns
        -------
        log_r : torch.Tensor, shape (N, K)
            Log-responsibility matrix. Rows sum to 1 in probability space.
        """
        # 1) Compute joint log-probability ( log π_k + log p(x|k) )
        # get log probs from helper — same as log_likelihood
        log_probs = self._compute_log_probs(X_t)

        # add log mixing weights — same as log_likelihood
        log_weighted = log_probs + torch.log(self.weights.to(X_t.device) + 1e-10)

        # 2) log-softmax across clusters
        # self-note: we normalize each row by subtracting its logsumexp (torch.logsumexp(..., dim=1, keepdim=True)
        # this gives us the log_r responsibility matrix
        log_r = log_weighted - torch.logsumexp(log_weighted, dim=1, keepdim=True)

        # return log_r tensor
        return log_r

    def _m_step(self, X_t, r):
        """
        Essentially: Given the input responsibility matrix, we update 3 parameters to match that

        Update means, variances, and weights from responsibilities.

        Mirrors the reference's M-step structure but:
        - updates self.variances (shape K, D) instead of full cov matrices
        - clamps variances to self.min_var after update

        Parameters
        ----------
        X_t : torch.Tensor, shape (N, D)
        r   : torch.Tensor, shape (N, K)
            Responsibilities in probability space (not log).
        """
        # r is shape (N, K) in probability space (not log)
        # X_t is shape (N, D)

        # 0) compute Nk — effective number of points per cluster
        # sum r (responsibility matrix) over dim=0 -> shape (K,)
        # we do a min clamp with 1e-10 to protect against empty clusters
        Nk = r.sum(dim=0)  # the responsibility matrix
        Nk = torch.clamp(Nk, min=1e-10)

        # --- weights ---
        # 1)
        weights = Nk / X_t.shape[0]   #   Nk / N -> shape (K,)
        self.weights = weights

        # --- means ---
        # 2)
        #    for each k: weighted sum of X_t rows, divided by Nk
        #    explanation: we matrix multiply r.T @ X_t which gives (K, N) @ (N, D) = (K, D),
        #    then divide each row k by Nk[k] ; we add .unsqueeze to add extra dim to data without changing its underlying contents
        means = r.T @ X_t / Nk.unsqueeze(1)

        dead = Nk < 1e-8
        if dead.any():
            means[dead] = X_t[torch.randint(0, X_t.shape[0], (dead.sum(),))]

        self.means = means

        # --- variances ---
        # 3) update diagonal variances, by looping over the clusters
        new_variances = torch.zeros(self.K, X_t.shape[1], device=X_t.device)

        for k in range(self.K):
            # diff between every point and cluster k's mean (x_i - mu_k) -> (N, D)
            diff_k = X_t - means[k]           # broadcasts (N,D) - (D,) = (N,D)

            # weight each point's squared diff by its responsibility for cluster k
            # r[:, k] is (N,) — unsqueeze to (N, 1) so it broadcasts across D dims
            weighted_sq = r[:, k].unsqueeze(1) * diff_k ** 2   # (N, D)

            # sum over N points, divide by Nk → (D,)
            new_variances[k] = weighted_sq.sum(dim=0) / Nk[k]

            # clamping for each individual new variance
            new_variances[k] = torch.clamp(new_variances[k], min=self.min_var)

        # UPDATE: variances
        self.variances = new_variances

        # Debugging function can be called here
        self._validate_params()

    def _compute_log_likelihood(self, X_t):
        """
        Essentially: Overall, how likely is this data point under the entire mixture model?

        Total log-likelihood of the data under the current model.

        Calls _compute_log_probs(), adds log weights, applies
        logsumexp over clusters, sums over all N points.

        Used inside fit() to check convergence.
        Used by bic() to compute the score.

        Parameters
        ----------
        X_t : torch.Tensor, shape (N, D)

        Returns
        -------
        log_likelihood : float (scalar)
        """
        # call _compute_log_probs(), get shape (N, K)
        log_probs = self._compute_log_probs(X_t)

        # add log mixing weights + epsilon (to make sure that our log_weighted doesn't reach 0)
        log_weighted = log_probs + torch.log(self.weights.to(X_t.device) + 1e-10)  # (N, K)

        # for each point, compute log(sum over K number of clusters), i.e. logsumexp over dim=1 to collapse the K dimension
        per_point = torch.logsumexp(log_weighted, dim=1)  # (N, K) -> (N,)

        # sum over all N points to get a log_likelihood scalar
        return per_point.sum()


    # ------------------------------------------------------------------ #
    #  public API (called from outside)                                  #
    # ------------------------------------------------------------------ #

    def fit(self, X):
        """
        Train the GMM using the EM algorithm.

        Converts X to a torch tensor, initializes params,
        then loops: _e_step → _m_step → _compute_log_likelihood
        until convergence or max_iter.

        Parameters
        ----------
        X : np.ndarray, shape (N, D)

        Returns
        -------
        self
        """
        # convert X to torch tensor, init params
        X_t = torch.tensor(X, dtype=torch.float32, device=self.device)

        N, D = X_t.shape
        self.D = D  # initialized only in .fit()

        # initialize params
        self._initialize_params(X_t)

        # set optional attributes
        ll_history = []  # to plot log-likelihood on a graph
        prev_ll = None
        self.converged_ = False
        self.n_iter_ = 0  # tracks current iteration

        # loop until convergence or max_iter; estep, convert log_r to responsibility matrix, m_step, compute log likelihood
        for i in range(self.max_iter):
            # e step
            log_r = self._e_step(X_t)

            # convert log_r to responsibility matrix
            r = torch.exp(log_r)

            # m step
            self._m_step(X_t, r)

            # compute ll
            ll = self._compute_log_likelihood(X_t)
            ll_value = ll.item()  # .item() converts tensor to np float, as is needed for abs() to work in convergence loop

            # DEBUGGING STEP after e-m loop; note: we changed the '-1e-6' to '1e-3' to not have issues with floating point rounding
            if prev_ll is not None and ll_value < prev_ll - 1e-3:
                print("Warning: log-likelihood decreased")

            # append to keep track of ll changes (as a numpy float)
            ll_history.append(ll_value)

            print(f"Iter {i} | log-likelihood: {ll_value:.4f}")

            # update model's metadata
            self.n_iter_ = i + 1

            # check if converged
            if prev_ll is not None:
                if abs(ll_value - prev_ll) < self.tol:
                    self.converged_ = True
                    self.lls_ = ll_history
                    return self

            # set new ll at the end
            prev_ll = ll_value

        # after loop, set model's metadata
        self.lls_ = ll_history

        # if didn't converge
        if not self.converged_:
            print(f"Warning: did not converge after {self.max_iter} iterations")

        return self

    def predict(self, X):
        """
        Assign each point to its most likely cluster.

        Runs _e_step, returns argmax over K dimension.

        Parameters
        ----------
        X : np.ndarray, shape (N, D)

        Returns
        -------
        assignments : np.ndarray, shape (N,)
        """
        # 1) e step
        X_t = torch.tensor(X, dtype=torch.float32, device=self.device)  # convert X to torch tensor like .fit() does
        log_r = self._e_step(X_t)

        # 2) return argmax over K dim
        return torch.argmax(log_r, dim=1).cpu().numpy()

    def bic(self, X):
        """
        Essentially: computes the Bayesian Information Criterion, which is used to select the optimal number of clusters.

        Computation: -2*ln(L) + k * ln(n), where L is the likelihood, k is the number of parameters, and n is the number of data points.

        n_params for diagonal GMM = K*D + K*D + (K-1)
        BIC = n_params * log(N) - 2 * log_likelihood

        Parameters
        ----------
        X : np.ndarray, shape (N, D)

        Returns
        -------
        bic_score : float — lower is better
        """
        # convert X to X_t (tensor)
        X_t = torch.tensor(X, dtype=torch.float32, device=self.device)

        N, D = X_t.shape
        K = self.K

        # free params: means + variances + weights
        n_params = K * D + K * D + (K - 1)

        # compute ll
        ll = self._compute_log_likelihood(X_t).item()

        # calculate
        return n_params * math.log(N) - 2 * ll


# ── Artifact saving ────────────────────────────────────────────────────────────

def save_space_artifacts(
    gmm: GMM,
    scaler: StandardScaler,
    assignments: np.ndarray,
    *,
    output_dir: Path,
    space: str,
    n_components: int,
    max_iter: int,
) -> None:
    stem = f"gmm_{space}_{n_components}_{max_iter}"
    npz_path = output_dir / f"{stem}.npz"
    np.savez(
        npz_path,
        means=gmm.means.cpu().numpy().astype(np.float32),
        covariances=gmm.variances.cpu().numpy().astype(np.float32),
        weights=gmm.weights.cpu().numpy().astype(np.float32),
        assignments=assignments.astype(np.int32),
        scaler_mean=scaler.mean_.astype(np.float32),
        scaler_scale=scaler.scale_.astype(np.float32),
    )

    cluster_indices: dict[str, list[int]] = {}
    for k in range(n_components):
        cluster_indices[str(k)] = np.where(assignments == k)[0].tolist()

    indices_path = output_dir / f"{stem}_indices.json"
    indices_path.write_text(json.dumps(cluster_indices), encoding="utf-8")

    manifest_path = output_dir / "gmm_manifest.json"
    try:
        manifests = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        manifests = []
    entry = {
        "space": space,
        "n_components": n_components,
        "max_iter": max_iter,
        "converged": gmm.converged_,
        "n_iter": gmm.n_iter_,
        "artifacts": {"npz": npz_path.name, "indices_json": indices_path.name},
    }
    manifests.append(entry)
    manifest_path.write_text(json.dumps(manifests, indent=2), encoding="utf-8")

    sizes = [len(v) for v in cluster_indices.values()]
    print(
        f"  [{space}] saved {npz_path.name} + {indices_path.name}  "
        f"| clusters: min={min(sizes)} max={max(sizes)} mean={np.mean(sizes):.0f}"
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit GMM clusters on embedding spaces (handwritten EM)")
    parser.add_argument("--embedding-dir", type=Path, default=Path("embeddings/metart"))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--spaces", nargs="+", default=list(SPACES.keys()),
        choices=list(SPACES.keys()),
    )
    parser.add_argument("--n-components", type=int, default=320)
    parser.add_argument("--max-iter", type=int, default=100)
    parser.add_argument("--tol", type=float, default=1e-4)
    parser.add_argument("--min-var", type=float, default=1e-6)
    parser.add_argument("--seed", type=int, default=67)
    parser.add_argument(
        "--device", default="cuda" if torch.cuda.is_available() else "cpu",
        help="PyTorch device (cuda or cpu)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.embedding_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    for space in args.spaces:
        npy_path = args.embedding_dir / SPACES[space]
        if not npy_path.exists():
            print(f"[{space}] {npy_path} not found — skipping")
            continue

        print(f"\n[{space}] Loading {npy_path} ...", flush=True)
        vectors = np.load(npy_path).astype(np.float32)
        print(f"  shape: {vectors.shape}")

        print("  Scaling with StandardScaler ...", flush=True)
        scaler = StandardScaler()
        scaled = scaler.fit_transform(vectors)

        print(f"  Fitting GMM (K={args.n_components}, device={args.device}) ...", flush=True)
        t0 = time.perf_counter()
        gmm = GMM(
            K=args.n_components,
            max_iter=args.max_iter,
            tol=args.tol,
            min_var=args.min_var,
            device=args.device,
            seed=args.seed,
        )
        gmm.fit(scaled)
        elapsed = time.perf_counter() - t0
        print(f"  converged={gmm.converged_}  iterations={gmm.n_iter_}  ({elapsed:.1f}s)")

        assignments = gmm.predict(scaled)

        save_space_artifacts(
            gmm, scaler, assignments,
            output_dir=output_dir,
            space=space,
            n_components=args.n_components,
            max_iter=args.max_iter,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
