import numpy as np
from scipy.optimize import minimize
from .base import PortfolioStrategy


class MinVarianceStrategy(PortfolioStrategy):

    @property
    def name(self) -> str:
        return "Minimum Variance"

    @property
    def description(self) -> str:
        return "Minimizes portfolio variance (w'Qw) subject to weights summing to 1 and no short selling."

    @property
    def parameters(self) -> list:
        return []

    def compute_weights(self, mu, Q, cur_prices, params):
        n = len(cur_prices)
        w0 = np.ones(n) / n

        result = minimize(
            fun=lambda w: w @ Q @ w,
            x0=w0,
            method="SLSQP",
            jac=lambda w: 2 * Q @ w,
            bounds=[(0.0, 1.0)] * n,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"ftol": 1e-12, "maxiter": 1000},
        )
        return result.x
