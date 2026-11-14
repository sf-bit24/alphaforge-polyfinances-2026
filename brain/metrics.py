from __future__ import annotations

import numpy as np
import pandas as pd


def portfolio_return(weights: np.ndarray, returns: np.ndarray) -> float:
    return float(np.dot(weights, returns))


def portfolio_volatility(weights: np.ndarray, covariance: np.ndarray) -> float:
    return float(np.sqrt(weights @ covariance @ weights))


def max_drawdown(returns: pd.Series) -> float:
    curve = (1 + returns.fillna(0)).cumprod()
    drawdown = curve / curve.cummax() - 1
    return float(drawdown.min())


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    return float(returns.quantile(1 - confidence))
