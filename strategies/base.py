from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class PortfolioStrategy(ABC):
    """Base class for multi-stock portfolio strategies with monthly rebalancing."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> list:
        pass

    @abstractmethod
    def compute_weights(self, mu: np.ndarray, Q: np.ndarray,
                        cur_prices: np.ndarray, params: dict) -> np.ndarray:
        """
        Compute target portfolio weights.

        Args:
            mu: expected returns vector (n,)
            Q: covariance matrix (n, n)
            cur_prices: current prices vector (n,)
            params: validated strategy parameters

        Returns:
            weights array (n,) with sum <= 1, all >= 0
        """
        pass

    def validate_parameters(self, params: dict) -> dict:
        cleaned = {}
        for schema in self.parameters:
            pid = schema["id"]
            ptype = schema["type"]
            val = params.get(pid, schema["default"])
            try:
                if ptype == "integer":
                    val = int(val)
                elif ptype == "float":
                    val = float(val)
                elif ptype == "boolean":
                    val = bool(val)
            except (ValueError, TypeError):
                raise ValueError(f"Parameter '{pid}' must be of type {ptype}.")
            if "min" in schema and val < schema["min"]:
                raise ValueError(f"Parameter '{pid}' must be >= {schema['min']}.")
            if "max" in schema and val > schema["max"]:
                raise ValueError(f"Parameter '{pid}' must be <= {schema['max']}.")
            cleaned[pid] = val
        return cleaned

    def run(self, mu: np.ndarray, Q: np.ndarray,
            cur_prices: np.ndarray, params: dict) -> np.ndarray:
        cleaned = self.validate_parameters(params)
        weights = self.compute_weights(mu, Q, cur_prices, cleaned)
        # Enforce no short selling
        weights = np.maximum(weights, 0.0)
        # Normalize if sum > 1
        w_sum = weights.sum()
        if w_sum > 1.0 + 1e-9:
            weights = weights / w_sum
        return weights
