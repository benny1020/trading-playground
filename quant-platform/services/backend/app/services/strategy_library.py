import pandas as pd
import numpy as np
from typing import Optional


class SmaCrossover:
    """
    SMA Crossover Strategy.
    Buy signal when short SMA crosses above long SMA.
    Sell signal when short SMA crosses below long SMA.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        short_window: int = 20,
        long_window: int = 60,
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for sym in prices.columns:
            price_series = prices[sym].dropna()
            if len(price_series) < long_window:
                continue

            short_sma = price_series.rolling(short_window).mean()
            long_sma = price_series.rolling(long_window).mean()

            # Signal: 1 when short > long, -1 when short < long, 0 otherwise
            position = pd.Series(0.0, index=price_series.index)
            position[short_sma > long_sma] = 1.0
            position[short_sma < long_sma] = -1.0

            # Only take position after both SMAs are available
            position[:long_window] = 0.0

            signals[sym] = position.reindex(prices.index).fillna(0.0)

        return signals


class RsiMeanReversion:
    """
    RSI Mean Reversion Strategy.
    Buy when RSI < oversold threshold, sell when RSI > overbought threshold.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for sym in prices.columns:
            price_series = prices[sym].dropna()
            if len(price_series) < period + 1:
                continue

            delta = price_series.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = -delta.where(delta < 0, 0.0)

            avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
            avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

            rs = avg_gain / (avg_loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))

            position = pd.Series(0.0, index=price_series.index)
            position[rsi < oversold] = 1.0
            position[rsi > overbought] = -1.0

            signals[sym] = position.reindex(prices.index).fillna(0.0)

        return signals


class BollingerBand:
    """
    Bollinger Band Strategy.
    Buy when price touches lower band, sell when price touches upper band.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0,
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for sym in prices.columns:
            price_series = prices[sym].dropna()
            if len(price_series) < period:
                continue

            rolling_mean = price_series.rolling(period).mean()
            rolling_std = price_series.rolling(period).std()

            upper_band = rolling_mean + std_dev * rolling_std
            lower_band = rolling_mean - std_dev * rolling_std

            position = pd.Series(0.0, index=price_series.index)
            position[price_series <= lower_band] = 1.0
            position[price_series >= upper_band] = -1.0

            signals[sym] = position.reindex(prices.index).fillna(0.0)

        return signals


class Momentum:
    """
    Cross-sectional Momentum Strategy.
    Buy top N performers over lookback period, rebalance monthly.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        lookback: int = 252,
        top_n: int = 10,
        rebalance_freq: str = "M",
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        # Get rebalance dates
        if rebalance_freq == "M":
            rebalance_dates = prices.resample("ME").last().index
        elif rebalance_freq == "W":
            rebalance_dates = prices.resample("W").last().index
        else:
            rebalance_dates = prices.resample(rebalance_freq).last().index

        current_signal = pd.Series(0.0, index=prices.columns)

        for date in prices.index:
            if date in rebalance_dates or (
                date == prices.index[0] and len(prices.loc[:date]) > lookback
            ):
                # Calculate lookback period returns
                past_prices = prices.loc[:date].iloc[-lookback:]
                if len(past_prices) < lookback:
                    signals.loc[date] = current_signal
                    continue

                momentum_returns = (
                    past_prices.iloc[-1] / (past_prices.iloc[0] + 1e-10) - 1
                )
                valid_returns = momentum_returns.dropna()

                if len(valid_returns) < top_n:
                    signals.loc[date] = current_signal
                    continue

                top_symbols = valid_returns.nlargest(top_n).index.tolist()

                current_signal = pd.Series(0.0, index=prices.columns)
                weight = 1.0 / top_n
                for sym in top_symbols:
                    current_signal[sym] = weight

            signals.loc[date] = current_signal

        return signals


class DualMomentum:
    """
    Gary Antonacci's Dual Momentum Strategy.
    Combines absolute momentum (trend-following) with relative momentum (cross-sectional).
    If absolute momentum is negative, move to safe asset (cash).
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        lookback: int = 252,
        safe_asset: str = "cash",
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        # Compute trailing returns for each period
        for i, date in enumerate(prices.index):
            if i < lookback:
                continue

            past_prices = prices.iloc[i - lookback : i + 1]
            returns = (past_prices.iloc[-1] / (past_prices.iloc[0] + 1e-10)) - 1

            # Relative momentum: find best performer
            valid = returns.dropna()
            if valid.empty:
                continue

            best_sym = valid.idxmax()
            best_return = valid[best_sym]

            # Absolute momentum: if best return is negative, go to cash (stay out)
            if best_return > 0:
                signals.loc[date, best_sym] = 1.0
            # else: stay in cash (all zeros)

        return signals


class MeanReversionPairs:
    """
    Statistical Arbitrage (Pairs Trading) Strategy.
    Uses z-score of the spread between two correlated assets.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        lookback: int = 60,
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.0,
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        cols = prices.columns.tolist()
        if len(cols) < 2:
            return signals

        # Work with first two columns as the pair
        sym1, sym2 = cols[0], cols[1]

        price1 = prices[sym1].dropna()
        price2 = prices[sym2].dropna()

        aligned = pd.concat([price1, price2], axis=1).dropna()
        if len(aligned) < lookback:
            return signals

        p1 = aligned[sym1]
        p2 = aligned[sym2]

        # Compute rolling hedge ratio via OLS
        spread_series = pd.Series(np.nan, index=aligned.index)

        for i in range(lookback, len(aligned)):
            window1 = p1.iloc[i - lookback : i].values
            window2 = p2.iloc[i - lookback : i].values

            # OLS: p1 = beta * p2 + alpha
            beta = np.cov(window1, window2)[0, 1] / (np.var(window2) + 1e-10)
            spread = window1[-1] - beta * window2[-1]
            spread_series.iloc[i] = spread

        # Rolling z-score of spread
        rolling_mean = spread_series.rolling(lookback).mean()
        rolling_std = spread_series.rolling(lookback).std()
        zscore = (spread_series - rolling_mean) / (rolling_std + 1e-10)

        # Generate signals based on z-score
        sig1 = pd.Series(0.0, index=aligned.index)
        sig2 = pd.Series(0.0, index=aligned.index)

        position = 0
        for date in aligned.index:
            z = zscore.get(date, np.nan)
            if pd.isna(z):
                continue

            if position == 0:
                if z > entry_zscore:
                    position = -1  # short sym1, long sym2
                    sig1[date] = -1.0
                    sig2[date] = 1.0
                elif z < -entry_zscore:
                    position = 1  # long sym1, short sym2
                    sig1[date] = 1.0
                    sig2[date] = -1.0
            elif position == 1:
                if z >= -exit_zscore:
                    position = 0
                else:
                    sig1[date] = 1.0
                    sig2[date] = -1.0
            elif position == -1:
                if z <= exit_zscore:
                    position = 0
                else:
                    sig1[date] = -1.0
                    sig2[date] = 1.0

        signals[sym1] = sig1.reindex(prices.index).fillna(0.0)
        signals[sym2] = sig2.reindex(prices.index).fillna(0.0)

        return signals


class MacdStrategy:
    """
    MACD Crossover Strategy.
    Buy when MACD line crosses above signal line.
    Sell when MACD line crosses below signal line.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for sym in prices.columns:
            price_series = prices[sym].dropna()
            if len(price_series) < slow + signal:
                continue

            ema_fast = price_series.ewm(span=fast, adjust=False).mean()
            ema_slow = price_series.ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal, adjust=False).mean()

            position = pd.Series(0.0, index=price_series.index)
            position[macd_line > signal_line] = 1.0
            position[macd_line < signal_line] = -1.0

            # Only generate signals after enough data
            position[:slow + signal] = 0.0

            signals[sym] = position.reindex(prices.index).fillna(0.0)

        return signals


class BreakoutStrategy:
    """
    Donchian Channel Breakout Strategy.
    Buy when price breaks above the highest high of lookback period.
    Sell when price breaks below the lowest low.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        lookback: int = 20,
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for sym in prices.columns:
            price_series = prices[sym].dropna()
            if len(price_series) < lookback + 1:
                continue

            # Rolling high and low (excluding current bar to avoid look-ahead)
            upper_channel = price_series.shift(1).rolling(lookback).max()
            lower_channel = price_series.shift(1).rolling(lookback).min()

            position = pd.Series(0.0, index=price_series.index)

            pos = 0
            for date in price_series.index:
                price = price_series[date]
                upper = upper_channel.get(date, np.nan)
                lower = lower_channel.get(date, np.nan)

                if pd.isna(upper) or pd.isna(lower):
                    position[date] = 0.0
                    continue

                if pos == 0 or pos == -1:
                    if price > upper:
                        pos = 1
                if pos == 0 or pos == 1:
                    if price < lower:
                        pos = -1

                position[date] = float(pos)

            signals[sym] = position.reindex(prices.index).fillna(0.0)

        return signals


class FactorModel:
    """
    Multi-factor Model Strategy.
    Ranks stocks by momentum + approximated value factor.
    Takes long positions in top percentile of combined factor score.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        momentum_period: int = 252,
        rebalance_freq: str = "M",
        top_pct: float = 0.2,
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        if rebalance_freq == "M":
            rebalance_dates = prices.resample("ME").last().index
        elif rebalance_freq == "W":
            rebalance_dates = prices.resample("W").last().index
        else:
            rebalance_dates = prices.resample(rebalance_freq).last().index

        current_signal = pd.Series(0.0, index=prices.columns)

        for date in prices.index:
            if date in rebalance_dates:
                past_prices = prices.loc[:date]
                if len(past_prices) < momentum_period:
                    signals.loc[date] = current_signal
                    continue

                # Momentum factor: 12-month return (skip last month to avoid reversal)
                skip = 21  # ~1 month
                lookback_prices = past_prices.iloc[-momentum_period:]
                if len(lookback_prices) < momentum_period:
                    signals.loc[date] = current_signal
                    continue

                momentum_scores = (
                    lookback_prices.iloc[-(skip + 1)]
                    / (lookback_prices.iloc[0] + 1e-10)
                    - 1
                )

                # Value factor approximation: inverse of 52-week price ratio (mean reversion component)
                recent_high = past_prices.iloc[-momentum_period:].max()
                current_price = past_prices.iloc[-1]
                value_scores = (current_price / (recent_high + 1e-10)) * -1  # lower price vs high = better value

                # Combine factors (equal weight)
                momentum_rank = momentum_scores.rank(pct=True, na_option="bottom")
                value_rank = value_scores.rank(pct=True, na_option="bottom")
                combined_rank = (momentum_rank + value_rank) / 2

                valid_combined = combined_rank.dropna()
                n_select = max(1, int(len(valid_combined) * top_pct))

                top_symbols = valid_combined.nlargest(n_select).index.tolist()

                current_signal = pd.Series(0.0, index=prices.columns)
                weight = 1.0 / max(n_select, 1)
                for sym in top_symbols:
                    current_signal[sym] = weight

            signals.loc[date] = current_signal

        return signals


class TradingAgentsDebate:
    """
    TradingAgents 팀 전략 백테스트.
    Bull/Bear 토론 기반 앙상블: 모멘텀 + 평균회귀 + 변동성 체제 감지.
    실제 TradingAgents 에이전트의 의사결정 로직을 시계열로 재현.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        momentum_weight: float = 0.40,
        mean_rev_weight: float = 0.30,
        vol_regime_weight: float = 0.30,
        rebalance_freq: str = "W",
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        if rebalance_freq == "W":
            rebalance_dates = set(prices.resample("W").last().index)
        else:
            rebalance_dates = set(prices.resample("ME").last().index)

        current_signal = pd.Series(0.0, index=prices.columns)

        for i, date in enumerate(prices.index):
            if i < 60:
                signals.loc[date] = current_signal
                continue

            if date not in rebalance_dates:
                signals.loc[date] = current_signal
                continue

            new_signal = pd.Series(0.0, index=prices.columns)

            for sym in prices.columns:
                price_series = prices[sym].dropna()
                if len(price_series) < 60:
                    continue

                price_at_date = price_series[:date]
                if len(price_at_date) < 60:
                    continue

                # --- Bull signals (momentum) ---
                ret_1m = float(price_at_date.iloc[-1] / price_at_date.iloc[-21] - 1) if len(price_at_date) >= 21 else 0
                ret_3m = float(price_at_date.iloc[-1] / price_at_date.iloc[-63] - 1) if len(price_at_date) >= 63 else 0
                mom_score = (ret_1m * 0.4 + ret_3m * 0.6)

                # --- Bear signals (mean reversion z-score) ---
                sma50 = float(price_at_date.rolling(50).mean().iloc[-1])
                std50 = float(price_at_date.rolling(50).std().iloc[-1])
                z_score = (float(price_at_date.iloc[-1]) - sma50) / (std50 + 1e-10)
                # Negative z => oversold => buy signal
                mr_signal = np.clip(-z_score / 3.0, -1.0, 1.0)

                # --- Volatility regime ---
                ret_series = price_at_date.pct_change().dropna()
                vol_20 = float(ret_series.iloc[-20:].std()) if len(ret_series) >= 20 else 0
                vol_60 = float(ret_series.iloc[-60:].std()) if len(ret_series) >= 60 else vol_20
                # Low vol regime = trend-following; high vol = caution
                vol_ratio = vol_20 / (vol_60 + 1e-10)
                vol_signal = np.clip(1.0 - vol_ratio, -1.0, 1.0)

                # --- Ensemble ---
                ensemble = (
                    momentum_weight * np.clip(mom_score * 10, -1, 1) +
                    mean_rev_weight * mr_signal +
                    vol_regime_weight * vol_signal
                )

                if ensemble >= 0.20:
                    new_signal[sym] = min(ensemble, 1.0)
                elif ensemble <= -0.20:
                    new_signal[sym] = max(ensemble, -1.0)

            # Normalize to equal weight within longs/shorts
            long_syms = new_signal[new_signal > 0]
            short_syms = new_signal[new_signal < 0]
            if len(long_syms) > 0:
                new_signal[long_syms.index] = 1.0 / len(long_syms)
            if len(short_syms) > 0:
                new_signal[short_syms.index] = -1.0 / len(short_syms)

            current_signal = new_signal
            signals.loc[date] = current_signal

        return signals


class AIHedgeFundPersona:
    """
    AI Hedge Fund 팀 전략 백테스트.
    8인 전설 투자자 컨센서스 기반: 가치 + 성장 + 역발상 + 리스크.
    각 페르소나의 핵심 신호를 시계열로 재현.
    """

    def generate_signals(
        self,
        prices: pd.DataFrame,
        rebalance_freq: str = "M",
        value_weight: float = 0.30,     # Graham + Buffett + Munger
        growth_weight: float = 0.25,    # Lynch + C.Wood
        macro_weight: float = 0.20,     # Soros
        contrarian_weight: float = 0.15,  # Burry
        risk_weight: float = 0.10,      # Taleb
        **kwargs,
    ) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        if rebalance_freq == "M":
            rebalance_dates = set(prices.resample("ME").last().index)
        elif rebalance_freq == "W":
            rebalance_dates = set(prices.resample("W").last().index)
        else:
            rebalance_dates = set(prices.resample("QE").last().index)

        current_signal = pd.Series(0.0, index=prices.columns)

        for i, date in enumerate(prices.index):
            if i < 120:
                signals.loc[date] = current_signal
                continue

            if date not in rebalance_dates:
                signals.loc[date] = current_signal
                continue

            scores = pd.Series(0.0, index=prices.columns)

            for sym in prices.columns:
                price_series = prices[sym].dropna()
                s = price_series[:date]
                if len(s) < 120:
                    continue

                daily_ret = s.pct_change().dropna()
                price = float(s.iloc[-1])
                high_52w = float(s.iloc[-252:].max()) if len(s) >= 252 else float(s.max())
                vol = float(daily_ret.std() * (252 ** 0.5))
                ret_1y = float(s.iloc[-1] / s.iloc[0] - 1) if len(s) >= 252 else 0
                ret_3m = float(s.iloc[-1] / s.iloc[-63] - 1) if len(s) >= 63 else 0

                # Value score (Graham/Buffett/Munger): price discount + stability
                price_to_high = price / (high_52w + 1e-10)
                value_score = (1.0 - price_to_high) * 2 - vol  # discount vs low vol

                # Growth score (Lynch/C.Wood): acceleration
                growth_score = ret_3m * 3 + (ret_1y * 0.5 if ret_1y > 0 else 0)

                # Macro score (Soros): trend following
                sma50 = float(s.rolling(50).mean().iloc[-1])
                sma200 = float(s.rolling(min(200, len(s))).mean().iloc[-1])
                macro_score = (1 if price > sma50 else -1) + (1 if sma50 > sma200 else -1)
                macro_score = macro_score / 2.0

                # Contrarian score (Burry): deep value/oversold
                delta = s.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss_v = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi = float((100 - 100 / (1 + gain / (loss_v + 1e-10))).iloc[-1])
                contrarian_score = np.clip((50 - rsi) / 50, -1, 1)

                # Risk score (Taleb): tail risk assessment
                kurt = float(daily_ret.iloc[-60:].kurtosis()) if len(daily_ret) >= 60 else 3
                skew = float(daily_ret.iloc[-60:].skew()) if len(daily_ret) >= 60 else 0
                risk_score = np.clip(skew * 0.5 - (kurt - 3) * 0.1, -1, 1)

                # Ensemble
                composite = (
                    value_weight * np.clip(value_score, -1, 1) +
                    growth_weight * np.clip(growth_score, -1, 1) +
                    macro_weight * macro_score +
                    contrarian_weight * contrarian_score +
                    risk_weight * risk_score
                )
                scores[sym] = composite

            # Rank-based signal: top 20% long, bottom 20% short
            valid = scores.dropna()
            if len(valid) < 5:
                signals.loc[date] = current_signal
                continue

            top_n = max(1, int(len(valid) * 0.20))
            top_syms = valid.nlargest(top_n).index
            bot_syms = valid.nsmallest(top_n).index

            new_signal = pd.Series(0.0, index=prices.columns)
            new_signal[top_syms] = 1.0 / top_n
            new_signal[bot_syms] = -1.0 / top_n

            current_signal = new_signal
            signals.loc[date] = current_signal

        return signals


STRATEGY_REGISTRY = {
    "sma_crossover": SmaCrossover,
    "rsi_mean_reversion": RsiMeanReversion,
    "bollinger_band": BollingerBand,
    "momentum": Momentum,
    "dual_momentum": DualMomentum,
    "pairs_trading": MeanReversionPairs,
    "macd": MacdStrategy,
    "breakout": BreakoutStrategy,
    "factor_model": FactorModel,
    "trading_agents_debate": TradingAgentsDebate,
    "ai_hedge_fund_persona": AIHedgeFundPersona,
}

STRATEGY_PARAMETER_SCHEMAS = {
    "sma_crossover": {
        "description": "SMA Crossover: Buy when short MA crosses above long MA",
        "parameters": {
            "short_window": {"type": "int", "default": 20, "description": "Short SMA window"},
            "long_window": {"type": "int", "default": 60, "description": "Long SMA window"},
        },
    },
    "rsi_mean_reversion": {
        "description": "RSI Mean Reversion: Buy oversold, sell overbought",
        "parameters": {
            "period": {"type": "int", "default": 14, "description": "RSI period"},
            "oversold": {"type": "float", "default": 30.0, "description": "Oversold threshold"},
            "overbought": {"type": "float", "default": 70.0, "description": "Overbought threshold"},
        },
    },
    "bollinger_band": {
        "description": "Bollinger Bands: Buy lower band touch, sell upper band touch",
        "parameters": {
            "period": {"type": "int", "default": 20, "description": "Rolling window"},
            "std_dev": {"type": "float", "default": 2.0, "description": "Standard deviation multiplier"},
        },
    },
    "momentum": {
        "description": "Cross-sectional Momentum: Buy top N performers",
        "parameters": {
            "lookback": {"type": "int", "default": 252, "description": "Lookback period (days)"},
            "top_n": {"type": "int", "default": 10, "description": "Number of top stocks to hold"},
            "rebalance_freq": {"type": "str", "default": "M", "description": "Rebalance frequency (M/W/Q)"},
        },
    },
    "dual_momentum": {
        "description": "Gary Antonacci's Dual Momentum: Absolute + Relative momentum",
        "parameters": {
            "lookback": {"type": "int", "default": 252, "description": "Lookback period (days)"},
            "safe_asset": {"type": "str", "default": "cash", "description": "Safe asset when absolute momentum is negative"},
        },
    },
    "pairs_trading": {
        "description": "Statistical Arbitrage: Pairs trading on spread z-score",
        "parameters": {
            "lookback": {"type": "int", "default": 60, "description": "Rolling window for spread stats"},
            "entry_zscore": {"type": "float", "default": 2.0, "description": "Z-score to enter trade"},
            "exit_zscore": {"type": "float", "default": 0.0, "description": "Z-score to exit trade"},
        },
    },
    "macd": {
        "description": "MACD Crossover: Signal line crossover strategy",
        "parameters": {
            "fast": {"type": "int", "default": 12, "description": "Fast EMA period"},
            "slow": {"type": "int", "default": 26, "description": "Slow EMA period"},
            "signal": {"type": "int", "default": 9, "description": "Signal EMA period"},
        },
    },
    "breakout": {
        "description": "Donchian Channel Breakout: Buy/sell on channel breaks",
        "parameters": {
            "lookback": {"type": "int", "default": 20, "description": "Channel lookback period (days)"},
        },
    },
    "factor_model": {
        "description": "Multi-Factor Model: Combined momentum and value ranking",
        "parameters": {
            "momentum_period": {"type": "int", "default": 252, "description": "Momentum lookback period"},
            "rebalance_freq": {"type": "str", "default": "M", "description": "Rebalance frequency"},
            "top_pct": {"type": "float", "default": 0.2, "description": "Top percentile of stocks to hold"},
        },
    },
    "trading_agents_debate": {
        "description": "TradingAgents Debate: Bull/Bear debate ensemble (Momentum + Mean-Reversion + Vol Regime)",
        "parameters": {
            "momentum_weight": {"type": "float", "default": 0.40, "description": "Weight for momentum signal"},
            "mean_rev_weight": {"type": "float", "default": 0.30, "description": "Weight for mean-reversion signal"},
            "vol_regime_weight": {"type": "float", "default": 0.30, "description": "Weight for volatility regime signal"},
            "rebalance_freq": {"type": "str", "default": "W", "description": "Rebalance frequency (W/M)"},
        },
    },
    "ai_hedge_fund_persona": {
        "description": "AI Hedge Fund Personas: 8 legendary investor consensus (Graham/Buffett/Munger/Soros/Lynch/Burry/C.Wood/Taleb)",
        "parameters": {
            "rebalance_freq": {"type": "str", "default": "M", "description": "Rebalance frequency (M/W/Q)"},
            "value_weight": {"type": "float", "default": 0.30, "description": "Weight for value personas (Graham/Buffett/Munger)"},
            "growth_weight": {"type": "float", "default": 0.25, "description": "Weight for growth personas (Lynch/C.Wood)"},
            "macro_weight": {"type": "float", "default": 0.20, "description": "Weight for macro persona (Soros)"},
            "contrarian_weight": {"type": "float", "default": 0.15, "description": "Weight for contrarian persona (Burry)"},
            "risk_weight": {"type": "float", "default": 0.10, "description": "Weight for risk persona (Taleb)"},
        },
    },
}


def get_strategy(strategy_type: str):
    """Get strategy class by type string."""
    cls = STRATEGY_REGISTRY.get(strategy_type)
    if cls is None:
        raise ValueError(f"Unknown strategy type: {strategy_type}. Available: {list(STRATEGY_REGISTRY.keys())}")
    return cls()
