"""Phase 0: confirm the TabPFN API key works, and record which model the API serves and what a call costs.

Uses synthetic data only (no real data leaves the machine in this check).
"""
from __future__ import annotations

import time

from sklearn.datasets import make_classification
from sklearn.metrics import roc_auc_score
from tabpfn_client import TabPFNClassifier, estimate_cost, get_api_usage

from cloudsea import settings  # noqa: F401  (loads TABPFN_TOKEN from .env)


def main() -> None:
    # Roughly our shape: a few hundred rows, ~30 features, imbalanced positives.
    X, y = make_classification(n_samples=400, n_features=30, n_informative=8,
                               weights=[0.8], random_state=0)
    X_train, X_test, y_train, y_test = X[:300], X[300:], y[:300], y[300:]

    print("available models:", TabPFNClassifier.list_available_models())
    print("estimated cost:", estimate_cost(X_train, X_test))

    clf = TabPFNClassifier()
    t0 = time.perf_counter()
    clf.fit(X_train, y_train)
    t1 = time.perf_counter()
    proba = clf.predict_proba(X_test)[:, 1]
    t2 = time.perf_counter()

    print(f"model_path: {clf.model_path!r}")
    print(f"fit {t1 - t0:.1f}s, predict {t2 - t1:.1f}s for {len(X_test)} rows")
    print(f"synthetic ROC-AUC {roc_auc_score(y_test, proba):.3f} (sanity only)")
    print("usage:", get_api_usage())


if __name__ == "__main__":
    main()
