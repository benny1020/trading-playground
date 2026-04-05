import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Trade:
    symbol: str
    entry_date: str
    exit_date: Optional[str]
    entry_price: float
    exit_price: Optional[float]
    quantity: int
    side: str  # 'long' or 'short'
    pnl: float = 0.0
    return_pct: float = 0.0


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: List[Trade]
    metrics: Dict


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100_000_000,
        commission_rate: float = 0.0015,
        slippage: float = 0.001,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage

    def run(
        self,
        prices: pd.DataFrame,
        signals: pd.DataFrame,
        end_date: Optional[str] = None,
    ) -> BacktestResult:
        """
        prices: DataFrame with columns = symbols, index = dates, values = adjusted close
        signals: DataFrame with same shape, values = position sizes (-1, 0, 1 or fractions)
        end_date: Point-in-time cutoff — NO data beyond this date is used.
                  Enforces no look-ahead bias in backtesting.

        Returns BacktestResult with equity_curve, trades, and metrics.
        """
        # ── Point-in-time enforcement ──────────────────────────────────────
        # Critical policy: a strategy may NEVER use data it wouldn't have
        # had access to at trade time. Strip any rows beyond end_date.
        if end_date is not None:
            cutoff = pd.Timestamp(end_date)
            prices = prices[prices.index <= cutoff]
            signals = signals[signals.index <= cutoff]

        # Align index
        prices = prices.ffill().dropna(how="all")
        signals = signals.reindex(prices.index).ffill().fillna(0)

        symbols = prices.columns.tolist()
        dates = prices.index
        n_dates = len(dates)

        # Track portfolio
        cash = self.initial_capital
        holdings: Dict[str, int] = {sym: 0 for sym in symbols}
        portfolio_values = pd.Series(index=dates, dtype=float)

        # For trade tracking
        open_positions: Dict[str, Dict] = {}
        completed_trades: List[Trade] = []

        # Previous signal to detect changes
        prev_signals = pd.Series(0.0, index=symbols)

        for i, date in enumerate(dates):
            current_prices = prices.loc[date]
            current_signals = signals.loc[date]

            # Detect signal changes
            for sym in symbols:
                prev_sig = prev_signals.get(sym, 0)
                curr_sig = current_signals.get(sym, 0)

                if pd.isna(current_prices.get(sym)) or current_prices.get(sym) is None:
                    continue

                price = float(current_prices[sym])

                # Close position if signal flipped or went to 0
                if prev_sig != 0 and curr_sig == 0:
                    qty = holdings[sym]
                    if qty != 0:
                        # Apply slippage: price moves against us on exit
                        side = "long" if qty > 0 else "short"
                        exit_price = price * (1 - self.slippage) if side == "long" else price * (1 + self.slippage)
                        commission = abs(qty) * exit_price * self.commission_rate
                        proceeds = qty * exit_price - commission
                        cash += proceeds

                        # Complete the trade record
                        if sym in open_positions:
                            op = open_positions.pop(sym)
                            pnl = proceeds - op["cost"]
                            ret_pct = pnl / (abs(op["cost"]) + 1e-10)
                            trade = Trade(
                                symbol=sym,
                                entry_date=str(op["entry_date"]),
                                exit_date=str(date),
                                entry_price=op["entry_price"],
                                exit_price=exit_price,
                                quantity=abs(qty),
                                side=side,
                                pnl=pnl,
                                return_pct=ret_pct,
                            )
                            completed_trades.append(trade)

                        holdings[sym] = 0

                elif prev_sig == 0 and curr_sig != 0:
                    # Open new position
                    # Target allocation = signal fraction of portfolio
                    portfolio_value = cash + sum(
                        holdings[s] * float(prices.loc[date, s])
                        for s in symbols
                        if not pd.isna(prices.loc[date, s])
                    )
                    target_value = portfolio_value * abs(curr_sig)

                    # Apply slippage: entry price moves against us
                    side = "long" if curr_sig > 0 else "short"
                    entry_price = price * (1 + self.slippage) if side == "long" else price * (1 - self.slippage)

                    qty = int(target_value / (entry_price + 1e-10))
                    if qty == 0:
                        continue

                    if side == "short":
                        qty = -qty

                    cost = qty * entry_price
                    commission = abs(qty) * entry_price * self.commission_rate
                    total_cost = cost + commission if side == "long" else cost - commission

                    if side == "long" and cash < total_cost:
                        # Reduce qty to fit available cash
                        qty = int(cash / (entry_price * (1 + self.commission_rate) + 1e-10))
                        if qty == 0:
                            continue
                        total_cost = qty * entry_price * (1 + self.commission_rate)

                    cash -= total_cost
                    holdings[sym] = qty

                    open_positions[sym] = {
                        "entry_date": date,
                        "entry_price": entry_price,
                        "cost": total_cost,
                        "side": side,
                    }

                elif prev_sig != 0 and curr_sig != 0 and prev_sig != curr_sig:
                    # Signal magnitude changed; rebalance
                    qty = holdings[sym]
                    if qty != 0:
                        side = "long" if qty > 0 else "short"
                        exit_price = price * (1 - self.slippage) if side == "long" else price * (1 + self.slippage)
                        commission_exit = abs(qty) * exit_price * self.commission_rate
                        proceeds = qty * exit_price - commission_exit
                        cash += proceeds

                        if sym in open_positions:
                            op = open_positions.pop(sym)
                            pnl = proceeds - op["cost"]
                            ret_pct = pnl / (abs(op["cost"]) + 1e-10)
                            trade = Trade(
                                symbol=sym,
                                entry_date=str(op["entry_date"]),
                                exit_date=str(date),
                                entry_price=op["entry_price"],
                                exit_price=exit_price,
                                quantity=abs(qty),
                                side=side,
                                pnl=pnl,
                                return_pct=ret_pct,
                            )
                            completed_trades.append(trade)
                        holdings[sym] = 0

                    # Re-enter with new signal
                    portfolio_value = cash + sum(
                        holdings[s] * float(prices.loc[date, s])
                        for s in symbols
                        if not pd.isna(prices.loc[date, s])
                    )
                    target_value = portfolio_value * abs(curr_sig)
                    side = "long" if curr_sig > 0 else "short"
                    entry_price = price * (1 + self.slippage) if side == "long" else price * (1 - self.slippage)
                    new_qty = int(target_value / (entry_price + 1e-10))
                    if new_qty == 0:
                        continue
                    if side == "short":
                        new_qty = -new_qty

                    total_cost = new_qty * entry_price
                    commission_entry = abs(new_qty) * entry_price * self.commission_rate
                    total_cost_with_commission = total_cost + commission_entry if side == "long" else total_cost - commission_entry

                    if side == "long" and cash < total_cost_with_commission:
                        new_qty = int(cash / (entry_price * (1 + self.commission_rate) + 1e-10))
                        if new_qty == 0:
                            continue
                        total_cost_with_commission = new_qty * entry_price * (1 + self.commission_rate)

                    cash -= total_cost_with_commission
                    holdings[sym] = new_qty
                    open_positions[sym] = {
                        "entry_date": date,
                        "entry_price": entry_price,
                        "cost": total_cost_with_commission,
                        "side": side,
                    }

            # Calculate portfolio value at end of day
            holdings_value = sum(
                holdings[sym] * float(prices.loc[date, sym])
                for sym in symbols
                if not pd.isna(prices.loc[date, sym]) and sym in holdings
            )
            portfolio_values[date] = cash + holdings_value
            prev_signals = current_signals.copy()

        # Close any remaining open positions at end
        last_date = dates[-1]
        for sym, op in open_positions.items():
            qty = holdings[sym]
            if qty != 0:
                price = float(prices.loc[last_date, sym]) if not pd.isna(prices.loc[last_date, sym]) else op["entry_price"]
                side = "long" if qty > 0 else "short"
                exit_price = price * (1 - self.slippage) if side == "long" else price * (1 + self.slippage)
                commission = abs(qty) * exit_price * self.commission_rate
                proceeds = qty * exit_price - commission
                pnl = proceeds - op["cost"]
                ret_pct = pnl / (abs(op["cost"]) + 1e-10)
                trade = Trade(
                    symbol=sym,
                    entry_date=str(op["entry_date"]),
                    exit_date=str(last_date),
                    entry_price=op["entry_price"],
                    exit_price=exit_price,
                    quantity=abs(qty),
                    side=side,
                    pnl=pnl,
                    return_pct=ret_pct,
                )
                completed_trades.append(trade)

        # Fill any NaN in equity curve
        portfolio_values = portfolio_values.fillna(method="ffill").fillna(self.initial_capital)

        metrics = self.calculate_metrics(portfolio_values, completed_trades)

        return BacktestResult(
            equity_curve=portfolio_values,
            trades=completed_trades,
            metrics=metrics,
        )

    def calculate_metrics(
        self,
        equity_curve: pd.Series,
        trades: List[Trade],
        benchmark: Optional[pd.Series] = None,
    ) -> Dict:
        """Calculate comprehensive performance metrics."""
        if equity_curve.empty or len(equity_curve) < 2:
            return {}

        equity_curve = equity_curve.dropna()
        returns = equity_curve.pct_change().dropna()

        # Basic stats
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1

        # CAGR
        n_years = len(equity_curve) / 252
        cagr = (equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1 / max(n_years, 1e-10)) - 1

        # Annualized volatility
        ann_vol = returns.std() * np.sqrt(252)

        # Sharpe ratio (rf = 3%)
        rf_daily = 0.03 / 252
        sharpe = (returns.mean() - rf_daily) / (returns.std() + 1e-10) * np.sqrt(252)

        # Sortino ratio
        downside_returns = returns[returns < rf_daily]
        downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 1 else 1e-10
        sortino = (cagr - 0.03) / (downside_std + 1e-10)

        # Max drawdown
        rolling_max = equity_curve.cummax()
        drawdowns = (equity_curve - rolling_max) / rolling_max
        max_drawdown = drawdowns.min()

        # Calmar ratio
        calmar = cagr / (abs(max_drawdown) + 1e-10)

        # Trade metrics
        n_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]

        win_rate = len(winning_trades) / n_trades if n_trades > 0 else 0.0
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0.0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0.0

        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / (gross_loss + 1e-10)

        # VaR and CVaR (95%)
        var_95 = float(np.percentile(returns, 5)) if len(returns) > 0 else 0.0
        cvar_95 = float(returns[returns <= var_95].mean()) if len(returns[returns <= var_95]) > 0 else var_95

        metrics = {
            "total_return": float(total_return),
            "total_return_pct": float(total_return * 100),
            "cagr": float(cagr),
            "cagr_pct": float(cagr * 100),
            "annualized_volatility": float(ann_vol),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "max_drawdown": float(max_drawdown),
            "max_drawdown_pct": float(max_drawdown * 100),
            "calmar_ratio": float(calmar),
            "win_rate": float(win_rate),
            "win_rate_pct": float(win_rate * 100),
            "profit_factor": float(profit_factor),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "n_trades": n_trades,
            "n_winning_trades": len(winning_trades),
            "n_losing_trades": len(losing_trades),
            "var_95": float(var_95),
            "cvar_95": float(cvar_95),
            "start_value": float(equity_curve.iloc[0]),
            "end_value": float(equity_curve.iloc[-1]),
            "n_trading_days": len(equity_curve),
        }

        # Beta and Alpha vs benchmark
        if benchmark is not None and len(benchmark) > 1:
            bench_returns = benchmark.pct_change().dropna()
            aligned = returns.align(bench_returns, join="inner")
            port_ret_aligned, bench_ret_aligned = aligned

            if len(port_ret_aligned) > 1:
                covariance = np.cov(port_ret_aligned, bench_ret_aligned)
                beta = covariance[0, 1] / (covariance[1, 1] + 1e-10)
                bench_cagr = (benchmark.iloc[-1] / benchmark.iloc[0]) ** (1 / max(n_years, 1e-10)) - 1
                alpha = cagr - (0.03 + beta * (bench_cagr - 0.03))
                metrics["beta"] = float(beta)
                metrics["alpha"] = float(alpha)
                metrics["alpha_pct"] = float(alpha * 100)

        return metrics
