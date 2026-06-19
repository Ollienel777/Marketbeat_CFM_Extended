from dataclasses import dataclass


@dataclass
class RaamConfig:
    initial_budget_cad: float = 1_000_000

    # universe rules
    min_liq_avg_volume: float = 5_000
    min_stocks: int = 10
    max_stocks: int = 25
    max_sector_weight: float = 0.40
    max_stock_weight: float = 0.15

    # lookback windows
    mom_lookback: int = 84
    vol_window: int = 60
    corr_window: int = 63
    atr_window: int = 42
    trend_high_window: int = 63
    trend_low_window: int = 105

    # sharpe optimization
    sharpe_lookback: int = 126
    sharpe_trials: int = 30_000
    risk_free: float = 0.0

    # fallback fx if usd->cad download fails
    fallback_usd_to_cad: float = 1.41

    # factor weights for the final RAAM score
    weight_momentum: float = 0.40
    weight_volatility: float = 0.30
    weight_correlation: float = 0.25
    weight_trend: float = 0.05
