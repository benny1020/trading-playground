"""
Risk Engine - Portfolio Risk Monitoring & Management
====================================================
Runs continuously to monitor strategy risk metrics.
Triggers alerts when thresholds are breached.

Metrics tracked:
- Portfolio VaR (95%, 99%)
- Conditional VaR (CVaR / Expected Shortfall)
- Maximum Drawdown (current + historical)
- Sharpe Ratio (rolling 252-day)
- Correlation matrix between strategies
- Factor exposure (market beta)
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import create_engine, text
import redis
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [risk-engine] %(levelname)s %(message)s"
)
logger = logging.getLogger("risk-engine")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quantpass@postgres:5432/quantdb")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

engine = create_engine(DATABASE_URL)
r = redis.from_url(REDIS_URL, decode_responses=True)


class RiskEngine:

    # Risk thresholds
    MAX_DRAWDOWN_ALERT = -0.15      # Alert at 15% drawdown
    MAX_DRAWDOWN_CRITICAL = -0.25   # Critical at 25% drawdown
    MIN_SHARPE_ALERT = 0.3          # Alert if rolling Sharpe drops below 0.3
    MAX_VAR_95_PCT = 0.03           # Alert if 1-day VaR 95% exceeds 3%
    MIN_CALMAR_RATIO = 0.5

    def __init__(self):
        self.http = httpx.Client(base_url=BACKEND_URL, timeout=30.0)

    def get_completed_backtests(self) -> list:
        """Fetch all completed backtests."""
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, name, strategy_id, results, equity_curve, created_at
                FROM backtest_runs
                WHERE status = 'completed'
                  AND equity_curve IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 100
            """))
            return [dict(row._mapping) for row in result]

    def compute_var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """Historical VaR (negative number = loss)."""
        if len(returns) < 20:
            return 0.0
        return float(np.percentile(returns.dropna(), (1 - confidence) * 100))

    def compute_cvar(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """Conditional VaR (Expected Shortfall)."""
        if len(returns) < 20:
            return 0.0
        var = self.compute_var(returns, confidence)
        return float(returns[returns <= var].mean())

    def compute_max_drawdown(self, equity: pd.Series) -> dict:
        """Compute drawdown statistics."""
        if len(equity) < 2:
            return {"max_drawdown": 0, "current_drawdown": 0, "recovery_days": None}

        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max

        max_dd = float(drawdown.min())
        current_dd = float(drawdown.iloc[-1])

        # Find recovery period
        last_peak_idx = drawdown.idxmin()
        recovery_days = None
        after_trough = drawdown[last_peak_idx:]
        recovered = after_trough[after_trough >= -0.001]
        if not recovered.empty:
            recovery_days = (recovered.index[0] - last_peak_idx).days

        return {
            "max_drawdown": max_dd,
            "current_drawdown": current_dd,
            "recovery_days": recovery_days
        }

    def compute_rolling_sharpe(self, returns: pd.Series, window: int = 252, rf: float = 0.03) -> Optional[float]:
        """Rolling annualized Sharpe ratio."""
        if len(returns) < window:
            window = len(returns)
        if window < 20:
            return None
        recent = returns.tail(window).dropna()
        excess = recent - rf / 252
        if excess.std() == 0:
            return None
        return float((excess.mean() / excess.std()) * np.sqrt(252))

    def compute_beta(self, strategy_returns: pd.Series, market_returns: pd.Series) -> float:
        """Market beta."""
        aligned = pd.DataFrame({"strat": strategy_returns, "mkt": market_returns}).dropna()
        if len(aligned) < 20:
            return 1.0
        cov = aligned.cov()
        return float(cov.loc["strat", "mkt"] / cov.loc["mkt", "mkt"])

    def analyze_backtest(self, bt: dict) -> dict:
        """Full risk analysis for a backtest."""
        try:
            equity_curve = bt.get("equity_curve")
            if not equity_curve:
                return {}

            if isinstance(equity_curve, str):
                equity_data = json.loads(equity_curve)
            else:
                equity_data = equity_curve

            equity = pd.Series({d["date"]: d["value"] for d in equity_data})
            equity.index = pd.to_datetime(equity.index)
            equity = equity.sort_index()

            returns = equity.pct_change().dropna()

            dd_stats = self.compute_max_drawdown(equity)
            var_95 = self.compute_var(returns, 0.95)
            var_99 = self.compute_var(returns, 0.99)
            cvar_95 = self.compute_cvar(returns, 0.95)
            rolling_sharpe = self.compute_rolling_sharpe(returns)

            # Skewness and kurtosis
            skew = float(stats.skew(returns.dropna())) if len(returns) > 3 else 0
            kurt = float(stats.kurtosis(returns.dropna())) if len(returns) > 3 else 0

            risk_analysis = {
                "backtest_id": str(bt["id"]),
                "backtest_name": bt["name"],
                "var_95_daily": var_95,
                "var_99_daily": var_99,
                "cvar_95_daily": cvar_95,
                "max_drawdown": dd_stats["max_drawdown"],
                "current_drawdown": dd_stats["current_drawdown"],
                "recovery_days": dd_stats["recovery_days"],
                "rolling_sharpe_252": rolling_sharpe,
                "return_skewness": skew,
                "return_kurtosis": kurt,
                "alerts": [],
                "analyzed_at": datetime.now().isoformat()
            }

            # Generate alerts
            alerts = []
            if dd_stats["max_drawdown"] < self.MAX_DRAWDOWN_CRITICAL:
                alerts.append({
                    "level": "CRITICAL",
                    "metric": "max_drawdown",
                    "value": dd_stats["max_drawdown"],
                    "threshold": self.MAX_DRAWDOWN_CRITICAL,
                    "message": f"Max drawdown {dd_stats['max_drawdown']*100:.1f}% exceeds critical threshold"
                })
            elif dd_stats["max_drawdown"] < self.MAX_DRAWDOWN_ALERT:
                alerts.append({
                    "level": "WARNING",
                    "metric": "max_drawdown",
                    "value": dd_stats["max_drawdown"],
                    "threshold": self.MAX_DRAWDOWN_ALERT,
                    "message": f"Max drawdown {dd_stats['max_drawdown']*100:.1f}% exceeds alert threshold"
                })

            if var_95 < -self.MAX_VAR_95_PCT:
                alerts.append({
                    "level": "WARNING",
                    "metric": "var_95",
                    "value": var_95,
                    "threshold": -self.MAX_VAR_95_PCT,
                    "message": f"Daily VaR 95% is {abs(var_95)*100:.2f}% - high risk"
                })

            if rolling_sharpe is not None and rolling_sharpe < self.MIN_SHARPE_ALERT:
                alerts.append({
                    "level": "WARNING",
                    "metric": "rolling_sharpe",
                    "value": rolling_sharpe,
                    "threshold": self.MIN_SHARPE_ALERT,
                    "message": f"Rolling Sharpe {rolling_sharpe:.2f} below minimum"
                })

            risk_analysis["alerts"] = alerts
            return risk_analysis

        except Exception as e:
            logger.error(f"Risk analysis failed for {bt.get('name')}: {e}")
            return {}

    def run_risk_monitor(self):
        """Run risk analysis on all completed backtests."""
        logger.info("Running risk monitoring cycle...")

        backtests = self.get_completed_backtests()
        if not backtests:
            logger.info("No completed backtests to analyze")
            return

        all_alerts = []
        risk_dashboard = []

        for bt in backtests:
            analysis = self.analyze_backtest(bt)
            if not analysis:
                continue

            # Store in Redis for quick access
            cache_key = f"risk:backtest:{bt['id']}"
            r.setex(cache_key, 3600, json.dumps(analysis))

            risk_dashboard.append(analysis)

            if analysis.get("alerts"):
                all_alerts.extend(analysis["alerts"])
                for alert in analysis["alerts"]:
                    logger.warning(
                        f"[{alert['level']}] {bt['name']}: {alert['message']}"
                    )

        # Store dashboard in Redis
        r.setex("risk:dashboard", 3600, json.dumps(risk_dashboard))

        # Save risk report to DB
        self._save_risk_report(risk_dashboard, all_alerts)

        logger.info(
            f"Risk monitoring complete | {len(backtests)} backtests analyzed | "
            f"{len(all_alerts)} alerts generated"
        )

    def compute_strategy_correlations(self):
        """Compute correlation matrix between all strategies."""
        logger.info("Computing strategy correlations...")

        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, name, equity_curve
                FROM backtest_runs
                WHERE status = 'completed' AND equity_curve IS NOT NULL
                ORDER BY created_at DESC LIMIT 20
            """))
            backtests = [dict(row._mapping) for row in result]

        if len(backtests) < 2:
            return

        returns_dict = {}
        for bt in backtests:
            try:
                if isinstance(bt["equity_curve"], str):
                    ec = json.loads(bt["equity_curve"])
                else:
                    ec = bt["equity_curve"]
                equity = pd.Series({d["date"]: d["value"] for d in ec})
                returns = equity.pct_change().dropna()
                returns_dict[bt["name"][:30]] = returns
            except Exception:
                continue

        if len(returns_dict) < 2:
            return

        returns_df = pd.DataFrame(returns_dict).dropna()
        corr_matrix = returns_df.corr()

        cache_data = {
            "matrix": corr_matrix.to_dict(),
            "strategies": list(returns_dict.keys()),
            "computed_at": datetime.now().isoformat()
        }
        r.setex("risk:correlations", 86400, json.dumps(cache_data))
        logger.info(f"Correlation matrix computed for {len(returns_dict)} strategies")

    def _save_risk_report(self, dashboard: list, alerts: list):
        """Persist risk report to DB."""
        with engine.connect() as conn:
            try:
                conn.execute(text("""
                    INSERT INTO risk_reports (report_date, dashboard_data, alerts, created_at)
                    VALUES (CURRENT_DATE, :dashboard, :alerts, NOW())
                    ON CONFLICT (report_date) DO UPDATE
                    SET dashboard_data = :dashboard, alerts = :alerts
                """), {
                    "dashboard": json.dumps(dashboard),
                    "alerts": json.dumps(alerts)
                })
                conn.commit()
            except Exception as e:
                logger.debug(f"Risk report save: {e}")


def main():
    risk_engine = RiskEngine()
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # Hourly risk monitoring during trading hours
    scheduler.add_job(
        risk_engine.run_risk_monitor,
        "interval",
        hours=1,
        id="risk_monitor",
        max_instances=1
    )

    # Daily correlation analysis
    scheduler.add_job(
        risk_engine.compute_strategy_correlations,
        "cron",
        hour=19, minute=0,
        id="correlations",
        max_instances=1
    )

    # Startup run
    scheduler.add_job(
        risk_engine.run_risk_monitor,
        "date",
        run_date=datetime.now() + timedelta(seconds=90),
        id="startup"
    )

    logger.info("Risk Engine started. Monitoring every hour.")
    scheduler.start()


if __name__ == "__main__":
    main()
