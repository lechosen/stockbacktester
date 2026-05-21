import numpy as np
from .base import PortfolioStrategy


class EquallyWeightedStrategy(PortfolioStrategy):

    @property
    def name(self) -> str:
        return "Equally Weighted"

    @property
    def description(self) -> str:
        return "Allocates equal weight (1/n) to each stock in the portfolio."

    @property
    def parameters(self) -> list:
        return []

    def compute_weights(self, mu, Q, cur_prices, params):
        n = len(cur_prices)
        return np.ones(n) / n
