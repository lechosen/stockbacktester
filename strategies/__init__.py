from .equally_weighted import EquallyWeightedStrategy
from .min_variance import MinVarianceStrategy
from .max_sharpe import MaxSharpeStrategy
from .equal_risk_contrib import EqualRiskContribStrategy
from .leveraged_erc import LeveragedERCStrategy
from .robust_mv import RobustMVStrategy
from .ma_crossover import MACrossoverStrategy

STRATEGIES = {
    "equally_weighted": EquallyWeightedStrategy(),
    "min_variance": MinVarianceStrategy(),
    "max_sharpe": MaxSharpeStrategy(),
    "equal_risk_contrib": EqualRiskContribStrategy(),
    "leveraged_erc": LeveragedERCStrategy(),
    "robust_mv": RobustMVStrategy(),
    "ma_crossover": MACrossoverStrategy(),
}
