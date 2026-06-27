import pandas as pd

from raam.sweep import generate_param_grid, make_label, summarize_sweep


def test_generate_param_grid_is_full_cartesian_product():
    grid = generate_param_grid({"a": [1, 2], "b": [10, 20, 30]})
    assert len(grid) == 6
    assert {"a": 1, "b": 10} in grid
    assert {"a": 2, "b": 30} in grid


def test_generate_param_grid_default_size():
    # 4 max_stocks x 3 max_sector_weight x 3 max_stock_weight
    assert len(generate_param_grid()) == 36


def test_make_label_includes_params_and_window():
    label = make_label("sweep", {"max_stocks": 15, "max_sector_weight": 0.25}, "2018-01-01", "2020-01-01")
    assert label == "sweep_max_stocks15_max_sector_weight0.25_2018-01-01_2020-01-01"


def test_summarize_sweep_averages_across_windows_and_ranks_by_sharpe():
    results = pd.DataFrame([
        {"max_stocks": 10, "max_sector_weight": 0.25, "max_stock_weight": 0.10, "strategy_sharpe": 0.5, "strategy_cagr": 0.05, "strategy_max_drawdown": -0.1},
        {"max_stocks": 10, "max_sector_weight": 0.25, "max_stock_weight": 0.10, "strategy_sharpe": 0.7, "strategy_cagr": 0.07, "strategy_max_drawdown": -0.08},
        {"max_stocks": 20, "max_sector_weight": 0.40, "max_stock_weight": 0.15, "strategy_sharpe": 0.3, "strategy_cagr": 0.03, "strategy_max_drawdown": -0.2},
        {"max_stocks": 20, "max_sector_weight": 0.40, "max_stock_weight": 0.15, "strategy_sharpe": 0.2, "strategy_cagr": 0.02, "strategy_max_drawdown": -0.25},
    ])

    summary = summarize_sweep(results)

    assert len(summary) == 2
    assert summary.iloc[0]["max_stocks"] == 10  # higher avg sharpe (0.6) ranked first
    assert summary.iloc[0]["avg_sharpe"] == 0.6
    assert summary.iloc[0]["n_windows"] == 2
    assert summary.iloc[1]["max_stocks"] == 20
    assert summary.iloc[1]["avg_sharpe"] == 0.25


def test_summarize_sweep_empty_input():
    assert summarize_sweep(pd.DataFrame()).empty
