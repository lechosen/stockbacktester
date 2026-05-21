import numpy as np
from .base import PortfolioStrategy
from .equal_risk_contrib import EqualRiskContribStrategy


class LeveragedERCStrategy(PortfolioStrategy):
    """
    Leveraged Equal Risk Contribution portfolio.

    Computes ERC weights then applies leverage (e.g., 2x) by borrowing
    additional capital at the risk-free rate. The weights sum to the
    leverage ratio instead of 1.
    """

    @property
    def name(self) -> str:
        return "Leveraged Equal Risk Contribution"

    @property
    def description(self) -> str:
        return (
            "Applies leverage to the ERC portfolio by borrowing capital. "
            "Weights sum to the leverage ratio (e.g., 2.0 for 2x leverage)."
        )

    @property
    def parameters(self) -> list:
        return [
            {
                "id": "leverage_ratio",
                "label": "Leverage Ratio",
                "type": "float",
                "default": 2.0,
                "min": 1.0,
                "max": 5.0,
            },
            {
                "id": "borrow_rate",
                "label": "Annual Borrow Rate (%)",
                "type": "float",
                "default": 2.5,
                "min": 0.0,
                "max": 20.0,
            },
        ]

    def compute_weights(self, mu, Q, cur_prices, params):
        leverage = params["leverage_ratio"]
        # Get base ERC weights (sum to 1)
        erc = EqualRiskContribStrategy()
        base_weights = erc.compute_weights(mu, Q, cur_prices, {})
        # Scale by leverage ratio
        return base_weights * leverage

    def run(self, mu, Q, cur_prices, params):
        cleaned = self.validate_parameters(params)
        weights = self.compute_weights(mu, Q, cur_prices, cleaned)
        # Enforce no short selling but allow sum > 1 (leverage)
        weights = np.maximum(weights, 0.0)
        return weights
