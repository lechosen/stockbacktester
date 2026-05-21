import numpy as np
from scipy.optimize import minimize
from .base import PortfolioStrategy


class EqualRiskContribStrategy(PortfolioStrategy):
    """
    Equal Risk Contribution (ERC) portfolio.

    Minimizes: sum_i sum_j (w_i*(Qw)_i - w_j*(Qw)_j)^2
    s.t.  sum(w) = 1, w >= 0

    This makes each asset's risk contribution equal.
    """

    @property
    def name(self) -> str:
        return "Equal Risk Contribution"

    @property
    def description(self) -> str:
        return (
            "Equalizes each asset's contribution to total portfolio risk "
            "by minimizing differences in marginal risk contributions."
        )

    @property
    def parameters(self) -> list:
        return []

    def compute_weights(self, mu, Q, cur_prices, params):
        n = len(cur_prices)
        w0 = np.ones(n) / n

        def erc_objective(w):
            Qw = Q @ w
            rc = w * Qw  # risk contributions
            # sum of squared pairwise differences
            total = 0.0
            for i in range(n):
                for j in range(i + 1, n):
                    total += (rc[i] - rc[j]) ** 2
            return 2.0 * total

        def erc_gradient(w):
            Qw = Q @ w
            rc = w * Qw
            grad = np.zeros(n)
            for k in range(n):
                for i in range(n):
                    for j in range(i + 1, n):
                        diff = rc[i] - rc[j]
                        # d(rc_i)/d(w_k) = delta_{ik} * (Qw)_i + w_i * Q_{ik}
                        drc_i = (1.0 if i == k else 0.0) * Qw[i] + w[i] * Q[i, k]
                        drc_j = (1.0 if j == k else 0.0) * Qw[j] + w[j] * Q[j, k]
                        grad[k] += 2.0 * diff * (drc_i - drc_j)
            return 2.0 * grad

        result = minimize(
            fun=erc_objective,
            x0=w0,
            method="SLSQP",
            jac=erc_gradient,
            bounds=[(1e-8, 1.0)] * n,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"ftol": 1e-12, "maxiter": 1000},
        )
        return result.x
