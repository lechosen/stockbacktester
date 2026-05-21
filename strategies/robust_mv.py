import numpy as np
from scipy.optimize import minimize
from .base import PortfolioStrategy
from .min_variance import MinVarianceStrategy


class RobustMVStrategy(PortfolioStrategy):
    """
    Robust Mean-Variance Optimization.

    Minimizes portfolio variance subject to:
    - Weights sum to 1, no short selling
    - Portfolio return >= target (minimum variance portfolio return)
    - Return estimation error (robustness) <= threshold
      (w' * diag(Q) * w <= rob_bnd, where rob_bnd is the estimation
       error of the 1/n portfolio)
    """

    @property
    def name(self) -> str:
        return "Robust Mean-Variance"

    @property
    def description(self) -> str:
        return (
            "Robust mean-variance optimization that constrains return "
            "estimation error, targeting the minimum-variance portfolio return."
        )

    @property
    def parameters(self) -> list:
        return [
            {
                "id": "risk_free_rate",
                "label": "Annual Risk-Free Rate (%)",
                "type": "float",
                "default": 2.5,
                "min": 0.0,
                "max": 20.0,
            },
        ]

    def compute_weights(self, mu, Q, cur_prices, params):
        n = len(cur_prices)
        w0 = np.ones(n) / n

        # Estimation error matrix: diagonal of covariance
        var_diag = np.diag(np.diag(Q))

        # Robustness bound: estimation error of 1/n portfolio
        rob_bnd = w0 @ var_diag @ w0

        # Target return: return of minimum variance portfolio
        mv = MinVarianceStrategy()
        w_mv = mv.compute_weights(mu, Q, cur_prices, {})
        target_return = mu @ w_mv

        result = minimize(
            fun=lambda w: w @ Q @ w,
            x0=w0,
            method="SLSQP",
            jac=lambda w: 2 * Q @ w,
            bounds=[(0.0, 1.0)] * n,
            constraints=[
                {"type": "eq", "fun": lambda w: w.sum() - 1.0},
                {"type": "ineq", "fun": lambda w: mu @ w - target_return},
                {"type": "ineq", "fun": lambda w: rob_bnd - w @ var_diag @ w},
            ],
            options={"ftol": 1e-12, "maxiter": 1000},
        )

        if not result.success:
            # Fall back to minimum variance if robust optimization fails
            return w_mv
        return result.x
