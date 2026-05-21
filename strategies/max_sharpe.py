import numpy as np
from scipy.optimize import minimize
from .base import PortfolioStrategy


class MaxSharpeStrategy(PortfolioStrategy):

    @property
    def name(self) -> str:
        return "Maximum Sharpe Ratio"

    @property
    def description(self) -> str:
        return (
            "Maximizes the Sharpe ratio (excess return / volatility) "
            "using the Markowitz tangency portfolio approach."
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
        rf_daily = params["risk_free_rate"] / 100.0 / 252.0
        excess = mu - rf_daily

        # If all excess returns are negative, fall back to minimum variance
        if np.all(excess <= 0):
            from .min_variance import MinVarianceStrategy
            return MinVarianceStrategy().compute_weights(mu, Q, cur_prices, {})

        # Tangency portfolio via variable substitution: y = w / (mu-rf)'w
        # min y'Qy  s.t.  (mu-rf)'y = 1, y >= 0
        # Then w = y / sum(y)
        result = minimize(
            fun=lambda y: y @ Q @ y,
            x0=np.ones(n) / n,
            method="SLSQP",
            jac=lambda y: 2 * Q @ y,
            bounds=[(0.0, None)] * n,
            constraints={"type": "eq", "fun": lambda y: excess @ y - 1.0},
            options={"ftol": 1e-12, "maxiter": 1000},
        )

        y = np.maximum(result.x, 0.0)
        y_sum = y.sum()
        if y_sum < 1e-10:
            return np.ones(n) / n
        return y / y_sum
