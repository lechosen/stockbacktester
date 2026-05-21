from flask import Flask, render_template, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime

from strategies import STRATEGIES
from strategies.ma_crossover import MACrossoverStrategy

app = Flask(__name__)

# Palette for per-stock chart traces
STOCK_COLORS = [
    "#3b82f6", "#10b981", "#f59e0b", "#ef4444",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316",
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/strategies")
def api_strategies():
    result = []
    for sid, strategy in STRATEGIES.items():
        result.append({
            "id": sid,
            "name": strategy.name,
            "description": strategy.description,
            "parameters": strategy.parameters,
        })
    return jsonify({"strategies": result})


@app.route("/api/tickers/validate")
def api_validate_ticker():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"valid": False, "error": "No symbol provided."})
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        if hist.empty:
            return jsonify({"valid": False, "error": f"Ticker '{symbol}' not found on Yahoo Finance."})

        name = symbol
        try:
            fast = ticker.fast_info
            name = getattr(fast, "display_name", None) or symbol
        except Exception:
            pass
        if name == symbol:
            try:
                info = ticker.info or {}
                name = info.get("longName") or info.get("shortName") or symbol
            except Exception:
                pass

        return jsonify({"valid": True, "symbol": symbol, "name": name})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    body = request.get_json(force=True)

    # --- Input validation ---
    symbols = [s.strip().upper() for s in body.get("symbols", []) if s.strip()]
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")
    strategy_id = body.get("strategy_id", "")
    parameters = body.get("parameters", {})
    initial_capital = float(body.get("initial_capital", 10000))

    if not symbols:
        return jsonify({"status": "error", "error": "At least one symbol is required."}), 400
    if strategy_id not in STRATEGIES:
        return jsonify({"status": "error", "error": f"Unknown strategy '{strategy_id}'."}), 400

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"status": "error", "error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if end_dt <= start_dt:
        return jsonify({"status": "error", "error": "End date must be after start date."}), 400
    if initial_capital <= 0:
        return jsonify({"status": "error", "error": "Initial capital must be positive."}), 400

    strategy = STRATEGIES[strategy_id]

    # Validate parameters early
    try:
        cleaned_params = strategy.validate_parameters(parameters)
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)}), 422

    # --- Download all stocks ---
    price_data = {}
    stock_names = {}
    for symbol in symbols:
        try:
            df = yf.download(symbol, start=start_date, end=end_date,
                             auto_adjust=True, progress=False)
        except Exception as e:
            return jsonify({"status": "error", "error": f"Failed to fetch data for {symbol}: {e}"}), 500

        if df.empty:
            return jsonify({"status": "error",
                            "error": f"No data found for '{symbol}' in the given date range."}), 422

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        price_data[symbol] = df["Close"]

        name = symbol
        try:
            info = yf.Ticker(symbol).info or {}
            name = info.get("longName") or info.get("shortName") or symbol
        except Exception:
            pass
        stock_names[symbol] = name

    # Build aligned price DataFrame (only dates where ALL stocks have data)
    prices_df = pd.DataFrame(price_data).dropna()
    if len(prices_df) < 2:
        return jsonify({"status": "error",
                        "error": "Not enough overlapping trading days across selected stocks."}), 422

    # --- Run portfolio simulation ---
    try:
        sim_result = simulate_portfolio(
            prices_df, symbols, strategy, cleaned_params,
            initial_capital, strategy_id,
        )
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)}), 422
    except Exception as e:
        return jsonify({"status": "error", "error": f"Simulation error: {e}"}), 500

    equity_curve = sim_result["equity_curve"]
    trades = sim_result["trades"]

    if not equity_curve:
        return jsonify({"status": "error",
                        "error": "No data produced by simulation."}), 422

    # --- Buy & Hold benchmark (equal weight, integer shares) ---
    bh_curve = compute_buy_hold_benchmark(prices_df, symbols, initial_capital)

    # Merge benchmark into equity curve
    bh_lookup = {p["date"]: p["portfolio_value"] for p in bh_curve}
    for point in equity_curve:
        point["benchmark_value"] = bh_lookup.get(point["date"], 0)

    # Downsample to max 1000 points
    if len(equity_curve) > 1000:
        step = len(equity_curve) // 1000
        equity_curve = equity_curve[::step]

    # --- Compute metrics ---
    bh_first = bh_curve[0]["portfolio_value"] if bh_curve else initial_capital
    bh_last = bh_curve[-1]["portfolio_value"] if bh_curve else initial_capital
    bh_return_pct = ((bh_last - bh_first) / bh_first) * 100 if bh_first > 0 else 0
    metrics = compute_metrics(equity_curve, trades, initial_capital, bh_return_pct)

    # --- Per-stock equity curves ---
    per_stock_chart = []
    per_stock_curves = sim_result.get("per_stock_curves", {})
    for i, symbol in enumerate(symbols):
        curve = per_stock_curves.get(symbol, [])
        if len(curve) > 1000:
            step = len(curve) // 1000
            curve = curve[::step]
        per_stock_chart.append({
            "symbol": symbol,
            "name": stock_names.get(symbol, symbol),
            "equity_curve": curve,
            "color": STOCK_COLORS[i % len(STOCK_COLORS)],
        })

    return jsonify({
        "status": "success",
        "metadata": {
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "strategy_name": strategy.name,
            "initial_capital": initial_capital,
            "per_stock_capital": round(initial_capital / len(symbols), 2),
            "n_stocks": len(symbols),
        },
        "metrics": metrics,
        "equity_curve": equity_curve,
        "per_stock": per_stock_chart,
        "trades": trades,
    })


@app.route("/api/backtest/compare", methods=["POST"])
def api_backtest_compare():
    """Run ALL strategies on the same data and return equity curves for comparison."""
    body = request.get_json(force=True)

    symbols = [s.strip().upper() for s in body.get("symbols", []) if s.strip()]
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")
    initial_capital = float(body.get("initial_capital", 10000))

    if not symbols:
        return jsonify({"status": "error", "error": "At least one symbol is required."}), 400

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"status": "error", "error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if end_dt <= start_dt:
        return jsonify({"status": "error", "error": "End date must be after start date."}), 400

    # Download all stocks once
    price_data = {}
    for symbol in symbols:
        try:
            df = yf.download(symbol, start=start_date, end=end_date,
                             auto_adjust=True, progress=False)
        except Exception as e:
            return jsonify({"status": "error", "error": f"Failed to fetch data for {symbol}: {e}"}), 500
        if df.empty:
            return jsonify({"status": "error",
                            "error": f"No data found for '{symbol}' in the given date range."}), 422
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        price_data[symbol] = df["Close"]

    prices_df = pd.DataFrame(price_data).dropna()
    if len(prices_df) < 2:
        return jsonify({"status": "error",
                        "error": "Not enough overlapping trading days across selected stocks."}), 422

    # Buy & Hold benchmark
    bh_curve = compute_buy_hold_benchmark(prices_df, symbols, initial_capital)
    bh_first = bh_curve[0]["portfolio_value"]
    bh_last = bh_curve[-1]["portfolio_value"]
    bh_return_pct = ((bh_last - bh_first) / bh_first) * 100 if bh_first > 0 else 0

    # Run every strategy
    strategy_results = []
    colors = [
        "#3b82f6", "#10b981", "#f59e0b", "#ef4444",
        "#8b5cf6", "#ec4899", "#14b8a6", "#f97316",
    ]

    for i, (sid, strategy) in enumerate(STRATEGIES.items()):
        default_params = {p["id"]: p["default"] for p in strategy.parameters}
        try:
            sim = simulate_portfolio(
                prices_df, symbols, strategy, default_params,
                initial_capital, sid,
            )
        except Exception:
            continue

        curve = sim["equity_curve"]
        if not curve:
            continue

        metrics = compute_metrics(curve, sim["trades"], initial_capital, bh_return_pct)

        # Downsample
        if len(curve) > 1000:
            step = len(curve) // 1000
            curve = curve[::step]

        strategy_results.append({
            "id": sid,
            "name": strategy.name,
            "equity_curve": curve,
            "metrics": metrics,
            "color": colors[i % len(colors)],
        })

    # Downsample benchmark
    if len(bh_curve) > 1000:
        step = len(bh_curve) // 1000
        bh_curve = bh_curve[::step]

    return jsonify({
        "status": "success",
        "metadata": {
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "n_stocks": len(symbols),
        },
        "strategies": strategy_results,
        "benchmark": bh_curve,
    })


# ---------------------------------------------------------------------------
# Portfolio simulation (multi-stock, monthly rebalancing)
# ---------------------------------------------------------------------------

def get_month_end_dates(dates_index: pd.DatetimeIndex) -> list:
    """Return the last trading day of each month present in the index."""
    grouped = dates_index.to_series().groupby(
        [dates_index.year, dates_index.month]
    )
    return [group.index[-1] for _, group in grouped]


def weights_to_shares(weights: np.ndarray, prices: np.ndarray,
                      total_value: float):
    """
    Convert target weights to integer share counts.
    Returns (shares_array, leftover_cash).
    No short selling: shares are floored to 0 minimum.
    """
    target_values = weights * total_value
    raw_shares = target_values / prices
    int_shares = np.array([max(0, math.floor(s)) for s in raw_shares], dtype=float)
    cost = np.dot(int_shares, prices)
    cash = total_value - cost
    # If rounding pushed us over budget, reduce shares one at a time
    while cash < -0.01:
        idx = int_shares.argmax()
        if int_shares[idx] <= 0:
            break
        int_shares[idx] -= 1
        cost = np.dot(int_shares, prices)
        cash = total_value - cost
    return int_shares, cash


def simulate_portfolio(prices_df: pd.DataFrame, symbols: list,
                       strategy, params: dict,
                       initial_capital: float, strategy_id: str) -> dict:
    """
    Simulate a portfolio with monthly rebalancing.

    Rules:
    - First month: all cash (wait at least 1 month before first trade)
    - Rebalance on last trading day of each month
    - Integer shares only, leftover cash saved
    - No short selling
    """
    n = len(symbols)
    dates = prices_df.index
    month_ends = get_month_end_dates(dates)

    if len(month_ends) < 2:
        raise ValueError(
            "Need at least 2 months of data. The first month is a "
            "warm-up period (all cash). Try a wider date range."
        )

    # State
    shares = np.zeros(n)
    cash = initial_capital
    borrow_amount = 0.0

    equity_curve = []
    per_stock_curves = {sym: [] for sym in symbols}
    trades = []
    trade_num = 0

    rebalance_dates = set(month_ends)
    is_leveraged = strategy_id == "leveraged_erc"
    borrow_rate_annual = params.get("borrow_rate", 2.5) / 100.0 if is_leveraged else 0.0

    for date in dates:
        cur_prices = prices_df.loc[date].values.astype(float)

        # --- Rebalance on month-end dates (skip first month) ---
        if date in rebalance_dates:
            hist = prices_df.loc[:date]
            if len(hist) < 2:
                continue

            returns = hist.pct_change().dropna()
            if len(returns) < 2:
                continue

            mu = returns.mean().values
            Q = returns.cov().values

            # Handle leveraged strategy: pay back borrow interest
            if is_leveraged and borrow_amount > 0:
                monthly_rate = borrow_rate_annual / 12.0
                interest = borrow_amount * monthly_rate
                cash -= interest

            # Current portfolio value (equity)
            portfolio_value = np.dot(shares, cur_prices) + cash
            if is_leveraged:
                portfolio_value -= borrow_amount

            if portfolio_value <= 0:
                continue

            # Compute target weights
            if isinstance(strategy, MACrossoverStrategy):
                weights = strategy.compute_weights_from_prices(hist, params)
            else:
                weights = strategy.run(mu, Q, cur_prices, params)

            # For leveraged: invest leverage_ratio * equity
            if is_leveraged:
                leverage = params.get("leverage_ratio", 2.0)
                invest_value = portfolio_value * leverage
                new_borrow = invest_value - portfolio_value
                cash += borrow_amount
                borrow_amount = new_borrow
                cash -= new_borrow
                total_to_invest = invest_value
            else:
                total_to_invest = np.dot(shares, cur_prices) + cash

            old_shares = shares.copy()
            shares, cash = weights_to_shares(weights, cur_prices, total_to_invest)

            # Record trades for changed positions
            for i, sym in enumerate(symbols):
                diff = int(shares[i] - old_shares[i])
                if diff != 0:
                    trade_num += 1
                    net_val = np.dot(shares, cur_prices) + cash
                    if is_leveraged:
                        net_val -= borrow_amount
                    trades.append({
                        "trade_num": trade_num,
                        "symbol": sym,
                        "type": "BUY" if diff > 0 else "SELL",
                        "date": str(date.date()),
                        "price": round(float(cur_prices[i]), 4),
                        "shares": abs(diff),
                        "portfolio_value": round(float(net_val), 2),
                        "return_pct": None,
                        "profit_loss": None,
                    })

        # --- Daily equity tracking ---
        gross_value = np.dot(shares, cur_prices) + cash
        net_value = gross_value - (borrow_amount if is_leveraged else 0)
        equity_curve.append({
            "date": str(date.date()),
            "portfolio_value": round(float(net_value), 2),
        })

        for i, sym in enumerate(symbols):
            per_stock_curves[sym].append({
                "date": str(date.date()),
                "portfolio_value": round(float(shares[i] * cur_prices[i]), 2),
            })

    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "per_stock_curves": per_stock_curves,
    }


# ---------------------------------------------------------------------------
# Buy & Hold benchmark (equal weight, integer shares, buy once)
# ---------------------------------------------------------------------------

def compute_buy_hold_benchmark(prices_df, symbols, initial_capital):
    """Buy equal-dollar amount of each stock at end of first month, hold throughout."""
    n = len(symbols)
    month_ends = get_month_end_dates(prices_df.index)

    bh_shares = np.zeros(n)
    bh_cash = initial_capital
    bought = False

    curve = []
    for date in prices_df.index:
        cur_prices = prices_df.loc[date].values.astype(float)

        # Buy on the first month-end (same timing as other strategies)
        if not bought and len(month_ends) >= 1 and date >= month_ends[0]:
            per_stock = initial_capital / n
            bh_shares = np.array([math.floor(per_stock / p) for p in cur_prices], dtype=float)
            bh_cash = initial_capital - np.dot(bh_shares, cur_prices)
            bought = True

        value = np.dot(bh_shares, cur_prices) + bh_cash
        curve.append({
            "date": str(date.date()),
            "portfolio_value": round(float(value), 2),
        })
    return curve


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(equity_curve, all_trades, initial_capital, bh_return_pct):
    if not equity_curve:
        return {}

    final_value = equity_curve[-1]["portfolio_value"]
    total_return_pct = ((final_value - initial_capital) / initial_capital) * 100

    n_days = len(equity_curve)
    n_years = n_days / 252
    if n_years > 0 and final_value > 0:
        ann_return_pct = ((final_value / initial_capital) ** (1 / n_years) - 1) * 100
    else:
        ann_return_pct = 0.0

    values = np.array([p["portfolio_value"] for p in equity_curve])
    daily_returns = np.diff(values) / np.where(values[:-1] != 0, values[:-1], 1)
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

    rebalance_dates = sorted(set(t["date"] for t in all_trades))
    total_rebalances = len(rebalance_dates)

    return {
        "total_return_pct": round(total_return_pct, 2),
        "annualized_return_pct": round(ann_return_pct, 2),
        "sharpe_ratio": round(float(sharpe), 3),
        "max_drawdown_pct": round(max_dd, 2),
        "total_trades": len(all_trades),
        "total_rebalances": total_rebalances,
        "final_portfolio_value": round(final_value, 2),
        "buy_and_hold_return_pct": round(bh_return_pct, 2),
    }


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
