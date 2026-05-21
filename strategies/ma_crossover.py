import numpy as np
import pandas as pd
from .base import PortfolioStrategy


class MACrossoverStrategy(PortfolioStrategy):
    """
    Moving Average Crossover adapted for monthly portfolio rebalancing.

    At each month-end rebalance, for each stock: if the short MA is above
    the long MA, the stock is marked as "bullish". Capital is distributed
    equally among bullish stocks. If no stocks are bullish, the portfolio
    stays in cash.
    """

    @property
    def name(self) -> str:
        return "Moving Average Crossover"

    @property
    def description(self) -> str:
        return (
            "At each monthly rebalance, invests equally in stocks whose "
            "short-term MA is above their long-term MA. Stays in cash "
            "if no stocks have a bullish signal."
        )

    @property
    def parameters(self) -> list:
        return [
            {
                "id": "short_window",
                "label": "Short MA Window (days)",
                "type": "integer",
                "default": 20,
                "min": 2,
                "max": 200,
            },
            {
                "id": "long_window",
                "label": "Long MA Window (days)",
                "type": "integer",
                "default": 50,
                "min": 5,
                "max": 500,
            },
        ]

    def compute_weights(self, mu, Q, cur_prices, params):
        # This strategy doesn't use mu/Q; it uses price_history instead.
        # Weights are computed in compute_weights_from_prices().
        n = len(cur_prices)
        return np.ones(n) / n

    def compute_weights_from_prices(self, price_history: pd.DataFrame,
                                    params: dict) -> np.ndarray:
        """
        Compute weights based on MA signals from price history.

        Args:
            price_history: DataFrame with columns = stock symbols, daily prices
            params: must contain short_window and long_window

        Returns:
            weights array (n,), equally distributed among bullish stocks
        """
        cleaned = self.validate_parameters(params)
        short_w = cleaned["short_window"]
        long_w = cleaned["long_window"]

        if short_w >= long_w:
            raise ValueError("Short MA window must be less than long MA window.")

        n = price_history.shape[1]
        if len(price_history) < long_w:
            return np.zeros(n)  # Not enough data — stay in cash

        bullish = np.zeros(n, dtype=bool)
        for i, col in enumerate(price_history.columns):
            short_ma = price_history[col].rolling(short_w).mean().iloc[-1]
            long_ma = price_history[col].rolling(long_w).mean().iloc[-1]
            if pd.notna(short_ma) and pd.notna(long_ma) and short_ma > long_ma:
                bullish[i] = True

        n_bullish = bullish.sum()
        if n_bullish == 0:
            return np.zeros(n)  # All cash

        weights = np.zeros(n)
        weights[bullish] = 1.0 / n_bullish
        return weights
