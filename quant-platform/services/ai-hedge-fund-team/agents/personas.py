"""
AI Hedge Fund Team — Investor Persona Agents
=============================================
전설적 투자자의 투자 철학을 구현한 에이전트들.
각 에이전트는 결정론적(deterministic) 스코어링 → LLM 최종 판단 패턴.

패턴 출처: ai-hedge-fund 레포 (Ben Graham, Buffett, Munger 등)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("ai-hedge-fund-team")


@dataclass
class PersonaSignal:
    persona_name: str
    signal: str           # BULLISH / BEARISH / NEUTRAL
    confidence: float     # 0.0 ~ 1.0
    score: float          # 원시 점수
    max_score: float      # 최대 가능 점수
    reasoning: str
    data_points: dict = field(default_factory=dict)


class BenGrahamAgent:
    """
    벤저민 그레이엄 — 안전마진 + 재무 건전성 + 밸류에이션.
    순자산가치(NCAV) 분석, 수익 안정성, 부채비율 평가.
    Score range: 0-16 (11.2+ bullish, ≤4.8 bearish)
    """
    name = "Ben Graham"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 60:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 16, "데이터 부족", {})

        price = float(close.iloc[-1])

        # --- 1. Earnings Stability (0-4) ---
        daily_ret = close.pct_change().dropna()
        positive_days_pct = float((daily_ret > 0).sum() / len(daily_ret))
        earnings_score = 0
        if positive_days_pct > 0.53:
            earnings_score = 3
        elif positive_days_pct > 0.50:
            earnings_score = 2
        # EPS growth proxy (price trend)
        ret_1y = float(close.iloc[-1] / close.iloc[0] - 1) if len(close) > 200 else 0
        if ret_1y > 0.05:
            earnings_score += 1
        score += earnings_score
        details["earnings_stability"] = earnings_score

        # --- 2. Financial Strength (0-5) ---
        strength_score = 0
        vol_annual = float(daily_ret.std() * (252 ** 0.5))
        # Low volatility = financial stability proxy
        if vol_annual < 0.15:
            strength_score += 2
        elif vol_annual < 0.25:
            strength_score += 1
        # Consistent positive returns = dividend proxy
        monthly_ret = close.resample("ME").last().pct_change().dropna() if hasattr(close.index, 'freq') or True else daily_ret
        try:
            monthly = close.resample("ME").last().pct_change().dropna()
            positive_months = float((monthly > 0).sum() / max(len(monthly), 1))
            if positive_months > 0.6:
                strength_score += 2
            elif positive_months > 0.5:
                strength_score += 1
        except Exception:
            strength_score += 1
        # Low drawdown = strength
        rolling_max = close.cummax()
        drawdown = float(((close - rolling_max) / rolling_max).min())
        if drawdown > -0.15:
            strength_score += 1
        score += strength_score
        details["financial_strength"] = strength_score

        # --- 3. Valuation (0-7) ---
        val_score = 0
        high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
        low_52w = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())
        price_to_high = price / high_52w

        # Graham number proxy: 20% below 52w high = margin of safety
        if price_to_high < 0.50:
            val_score += 4  # Deep value (NCAV proxy)
        elif price_to_high < 0.67:
            val_score += 3
        elif price_to_high < 0.80:
            val_score += 2
        elif price_to_high < 0.90:
            val_score += 1
        # Near all-time high = overvalued
        if price_to_high > 0.98:
            val_score -= 1

        score += val_score
        details["valuation"] = val_score

        # --- Signal Determination ---
        max_score = 16
        if score >= 11:
            signal = "BULLISH"
        elif score <= 5:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = min(0.90, 0.4 + (score / max_score) * 0.5)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"안전마진: Earnings={earnings_score}/4, Strength={strength_score}/5, "
            f"Val={val_score}/7, Total={score}/{max_score}",
            details,
        )


class WarrenBuffettAgent:
    """
    워런 버핏 — Owner Earnings + 경쟁 우위 + 장기 성장.
    내재가치 대비 할인율, 안정적 수익 성장, 자본 효율성 평가.
    """
    name = "Warren Buffett"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 120:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 12, "데이터 부족", {})

        price = float(close.iloc[-1])

        # --- 1. Owner Earnings Proxy: Consistent price appreciation (0-4) ---
        oe_score = 0
        ret_6m = float(close.iloc[-1] / close.iloc[-126] - 1) if len(close) >= 126 else 0
        ret_1y = float(close.iloc[-1] / close.iloc[0] - 1) if len(close) >= 252 else ret_6m

        if ret_1y > 0.20:
            oe_score += 3
        elif ret_1y > 0.10:
            oe_score += 2
        elif ret_1y > 0:
            oe_score += 1
        if ret_6m > 0.10:
            oe_score += 1
        score += oe_score
        details["owner_earnings"] = oe_score

        # --- 2. Competitive Moat: Price stability + trend (0-4) ---
        moat_score = 0
        daily_ret = close.pct_change().dropna()
        vol = float(daily_ret.std() * (252 ** 0.5))

        # Low vol = strong moat
        if vol < 0.12:
            moat_score += 2
        elif vol < 0.20:
            moat_score += 1

        # Consistent uptrend = durable advantage
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(min(200, len(close))).mean().iloc[-1])
        if price > sma50 > sma200:
            moat_score += 2
        elif price > sma200:
            moat_score += 1
        score += moat_score
        details["competitive_moat"] = moat_score

        # --- 3. Capital Efficiency: Return consistency (0-4) ---
        cap_score = 0
        try:
            quarterly_ret = close.resample("QE").last().pct_change().dropna()
            pos_quarters = float((quarterly_ret > 0).sum() / max(len(quarterly_ret), 1))
            if pos_quarters > 0.75:
                cap_score += 3
            elif pos_quarters > 0.60:
                cap_score += 2
            elif pos_quarters > 0.50:
                cap_score += 1
        except Exception:
            cap_score += 1
        # Sharpe proxy
        sharpe = float(daily_ret.mean() / (daily_ret.std() + 1e-10) * (252 ** 0.5))
        if sharpe > 1.5:
            cap_score += 1
        score += cap_score
        details["capital_efficiency"] = cap_score

        max_score = 12
        if score >= 9:
            signal = "BULLISH"
        elif score <= 4:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = min(0.90, 0.4 + (score / max_score) * 0.5)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"Owner Earnings={oe_score}/4, Moat={moat_score}/4, "
            f"Capital Eff={cap_score}/4, Total={score}/{max_score}",
            details,
        )


class CharlieMungerAgent:
    """
    찰리 멍거 — 품질 + 합리성 + 장기 복리 성장.
    고품질 비즈니스(낮은 변동성, 꾸준한 성장)에 집중.
    """
    name = "Charlie Munger"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 120:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 10, "데이터 부족", {})

        daily_ret = close.pct_change().dropna()

        # --- 1. Quality: Low volatility + positive skew (0-4) ---
        quality_score = 0
        vol = float(daily_ret.std() * (252 ** 0.5))
        skew = float(daily_ret.skew())

        if vol < 0.15:
            quality_score += 2
        elif vol < 0.25:
            quality_score += 1
        if skew > 0:
            quality_score += 1
        # Low kurtosis = fewer tail risks
        kurt = float(daily_ret.kurtosis())
        if kurt < 5:
            quality_score += 1
        score += quality_score
        details["quality"] = quality_score

        # --- 2. Long-term Growth: Compounding (0-3) ---
        growth_score = 0
        ret_total = float(close.iloc[-1] / close.iloc[0] - 1)
        n_days = len(close)
        cagr = (1 + ret_total) ** (252 / max(n_days, 1)) - 1

        if cagr > 0.15:
            growth_score += 3
        elif cagr > 0.08:
            growth_score += 2
        elif cagr > 0:
            growth_score += 1
        score += growth_score
        details["growth"] = growth_score

        # --- 3. Rationality: Drawdown recovery + consistency (0-3) ---
        rational_score = 0
        rolling_max = close.cummax()
        max_dd = float(((close - rolling_max) / rolling_max).min())

        if max_dd > -0.10:
            rational_score += 2
        elif max_dd > -0.20:
            rational_score += 1
        # Currently recovering or at highs
        current_dd = float((close.iloc[-1] - rolling_max.iloc[-1]) / rolling_max.iloc[-1])
        if current_dd > -0.05:
            rational_score += 1
        score += rational_score
        details["rationality"] = rational_score

        max_score = 10
        if score >= 8:
            signal = "BULLISH"
        elif score <= 3:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = min(0.85, 0.4 + (score / max_score) * 0.45)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"Quality={quality_score}/4, Growth={growth_score}/3, "
            f"Rationality={rational_score}/3, Total={score}/{max_score}",
            details,
        )


class GeorgeSorosAgent:
    """
    조지 소로스 — 매크로 트렌드 + 반사성(Reflexivity).
    시장 전체 추세, 모멘텀 가속, 변동성 체제 전환 감지.
    """
    name = "George Soros"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        import numpy as np
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 60:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 10, "데이터 부족", {})

        price = float(close.iloc[-1])

        # --- 1. Macro Trend (0-4) ---
        trend_score = 0
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(min(200, len(close))).mean().iloc[-1])
        ema20 = float(close.ewm(span=20).mean().iloc[-1])

        if price > ema20 > sma50:
            trend_score += 2
        elif price > sma50:
            trend_score += 1
        if sma50 > sma200:
            trend_score += 1  # Golden cross
        # Trend acceleration
        ret_1m = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0
        ret_3m = float(close.iloc[-1] / close.iloc[-63] - 1) if len(close) >= 63 else 0
        if ret_1m > ret_3m / 3:  # Accelerating
            trend_score += 1
        score += trend_score
        details["macro_trend"] = trend_score

        # --- 2. Reflexivity: Momentum feedback loop (0-3) ---
        reflex_score = 0
        daily_ret = close.pct_change().dropna()
        # Autocorrelation of returns (positive = reflexivity in play)
        if len(daily_ret) > 20:
            autocorr = float(daily_ret.autocorr(lag=1))
            if autocorr > 0.05:
                reflex_score += 2
            elif autocorr > 0:
                reflex_score += 1
        # Volume proxy: increasing volatility with trend = conviction
        vol_recent = float(daily_ret.iloc[-20:].std()) if len(daily_ret) >= 20 else 0
        vol_prior = float(daily_ret.iloc[-60:-20].std()) if len(daily_ret) >= 60 else vol_recent
        if vol_recent < vol_prior and ret_1m > 0:
            reflex_score += 1  # Trending with decreasing vol = strong trend
        score += reflex_score
        details["reflexivity"] = reflex_score

        # --- 3. Regime Detection (0-3) ---
        regime_score = 0
        vol_20 = float(daily_ret.iloc[-20:].std() * (252 ** 0.5)) if len(daily_ret) >= 20 else 0
        vol_60 = float(daily_ret.iloc[-60:].std() * (252 ** 0.5)) if len(daily_ret) >= 60 else vol_20

        if vol_20 < vol_60 * 0.8:
            regime_score += 2  # Volatility compression = breakout coming
        elif vol_20 < vol_60:
            regime_score += 1
        # Positive skew in recent returns = bullish regime
        recent_skew = float(daily_ret.iloc[-20:].skew()) if len(daily_ret) >= 20 else 0
        if recent_skew > 0.3:
            regime_score += 1
        score += regime_score
        details["regime"] = regime_score

        max_score = 10
        if score >= 7:
            signal = "BULLISH"
        elif score <= 3:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = min(0.85, 0.4 + (score / max_score) * 0.45)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"Macro={trend_score}/4, Reflexivity={reflex_score}/3, "
            f"Regime={regime_score}/3, Total={score}/{max_score}",
            details,
        )


class PeterLynchAgent:
    """
    피터 린치 — PEG Ratio + 이해 가능한 성장주.
    성장 속도 대비 밸류에이션, 주가 모멘텀, 변동성 조절.
    """
    name = "Peter Lynch"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 120:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 10, "데이터 부족", {})

        price = float(close.iloc[-1])

        # --- 1. Growth Rate (PEG proxy) (0-4) ---
        growth_score = 0
        ret_6m = float(close.iloc[-1] / close.iloc[-126] - 1) if len(close) >= 126 else 0
        ret_1y = float(close.iloc[-1] / close.iloc[0] - 1) if len(close) >= 252 else ret_6m * 2

        annualized_growth = ret_1y
        if annualized_growth > 0.25:
            growth_score += 3
        elif annualized_growth > 0.15:
            growth_score += 2
        elif annualized_growth > 0.05:
            growth_score += 1
        # Accelerating growth
        if ret_6m > ret_1y / 2:
            growth_score += 1
        score += growth_score
        details["growth_rate"] = growth_score

        # --- 2. Understandability: Stability proxy (0-3) ---
        understand_score = 0
        daily_ret = close.pct_change().dropna()
        vol = float(daily_ret.std() * (252 ** 0.5))

        if vol < 0.20:
            understand_score += 2
        elif vol < 0.30:
            understand_score += 1
        # Predictable trend
        if len(close) >= 60:
            r2 = _trend_r_squared(close.iloc[-60:])
            if r2 > 0.7:
                understand_score += 1
        score += understand_score
        details["understandability"] = understand_score

        # --- 3. Fair Price (0-3) ---
        fair_score = 0
        high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
        ratio = price / high_52w

        # Not at peak (room to grow)
        if 0.70 < ratio < 0.90:
            fair_score += 2  # Sweet spot
        elif ratio < 0.70:
            fair_score += 1  # Might be value trap
        elif ratio < 0.95:
            fair_score += 1

        # Growth vs price: strong growth with moderate price = good PEG
        if annualized_growth > 0.15 and ratio < 0.90:
            fair_score += 1
        score += fair_score
        details["fair_price"] = fair_score

        max_score = 10
        if score >= 7:
            signal = "BULLISH"
        elif score <= 3:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = min(0.85, 0.4 + (score / max_score) * 0.45)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"Growth={growth_score}/4, Understand={understand_score}/3, "
            f"FairPrice={fair_score}/3, Total={score}/{max_score}",
            details,
        )


class MichaelBurryAgent:
    """
    마이클 버리 — 역발상(Contrarian) + 딥 밸류.
    과매도 상태, 극단적 공포, 평균회귀 기회 탐색.
    """
    name = "Michael Burry"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        import numpy as np
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 60:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 10, "데이터 부족", {})

        price = float(close.iloc[-1])
        daily_ret = close.pct_change().dropna()

        # --- 1. Deep Value: Distance from highs (0-4) ---
        deep_score = 0
        high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
        drawdown_pct = (price / high_52w) - 1

        if drawdown_pct < -0.40:
            deep_score += 4  # Extreme discount
        elif drawdown_pct < -0.25:
            deep_score += 3
        elif drawdown_pct < -0.15:
            deep_score += 2
        elif drawdown_pct < -0.05:
            deep_score += 1
        score += deep_score
        details["deep_value"] = deep_score

        # --- 2. Contrarian Signal: Extreme fear (0-3) ---
        contra_score = 0
        # RSI oversold
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss_v = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = float((100 - 100 / (1 + gain / (loss_v + 1e-10))).iloc[-1])

        if rsi < 25:
            contra_score += 2
        elif rsi < 35:
            contra_score += 1
        # Negative skew = fear environment (contrarian opportunity)
        skew = float(daily_ret.iloc[-30:].skew()) if len(daily_ret) >= 30 else 0
        if skew < -0.5:
            contra_score += 1
        score += contra_score
        details["contrarian"] = contra_score

        # --- 3. Mean Reversion Setup (0-3) ---
        mr_score = 0
        if len(close) >= 50:
            sma50 = float(close.rolling(50).mean().iloc[-1])
            z_score = (price - sma50) / (float(close.rolling(50).std().iloc[-1]) + 1e-10)
            if z_score < -2.0:
                mr_score += 2
            elif z_score < -1.0:
                mr_score += 1
        # Starting to recover (positive momentum from bottom)
        ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0
        if drawdown_pct < -0.15 and ret_5d > 0:
            mr_score += 1  # Bounce from bottom
        score += mr_score
        details["mean_reversion"] = mr_score

        max_score = 10
        # Burry is contrarian: high score = buy when others sell
        if score >= 7:
            signal = "BULLISH"
        elif score <= 2:
            signal = "BEARISH"  # Market is too euphoric
        else:
            signal = "NEUTRAL"

        confidence = min(0.85, 0.4 + (score / max_score) * 0.45)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"DeepValue={deep_score}/4, Contrarian={contra_score}/3, "
            f"MeanRev={mr_score}/3, Total={score}/{max_score}",
            details,
        )


class CathieWoodAgent:
    """
    캐시 우드 — 파괴적 혁신 + 고성장.
    급격한 모멘텀 가속, 높은 변동성 수용, 폭발적 성장 추구.
    """
    name = "Cathie Wood"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 60:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 10, "데이터 부족", {})

        price = float(close.iloc[-1])
        daily_ret = close.pct_change().dropna()

        # --- 1. Explosive Growth (0-4) ---
        growth_score = 0
        ret_3m = float(close.iloc[-1] / close.iloc[-63] - 1) if len(close) >= 63 else 0
        ret_1m = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0

        if ret_3m > 0.30:
            growth_score += 3
        elif ret_3m > 0.15:
            growth_score += 2
        elif ret_3m > 0.05:
            growth_score += 1
        # Accelerating
        if ret_1m > ret_3m / 3 * 1.2:
            growth_score += 1
        score += growth_score
        details["explosive_growth"] = growth_score

        # --- 2. Disruption Proxy: Outperformance vs market (0-3) ---
        disrupt_score = 0
        # High beta = innovation exposure
        vol = float(daily_ret.std() * (252 ** 0.5))
        if vol > 0.30:
            disrupt_score += 1  # High vol = high beta = innovation
        # Strong trend despite volatility
        if ret_3m > 0.10 and vol > 0.20:
            disrupt_score += 2
        elif ret_3m > 0.05:
            disrupt_score += 1
        score += disrupt_score
        details["disruption"] = disrupt_score

        # --- 3. Momentum Strength (0-3) ---
        mom_score = 0
        if len(close) >= 50:
            ema10 = float(close.ewm(span=10).mean().iloc[-1])
            ema30 = float(close.ewm(span=30).mean().iloc[-1])
            if price > ema10 > ema30:
                mom_score += 2
            elif price > ema30:
                mom_score += 1
        if ret_1m > 0.05:
            mom_score += 1
        score += mom_score
        details["momentum"] = mom_score

        max_score = 10
        if score >= 7:
            signal = "BULLISH"
        elif score <= 3:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = min(0.85, 0.4 + (score / max_score) * 0.45)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"Growth={growth_score}/4, Disruption={disrupt_score}/3, "
            f"Momentum={mom_score}/3, Total={score}/{max_score}",
            details,
        )


class NassimTalebAgent:
    """
    나심 탈레브 — 꼬리 리스크(Tail Risk) + 안티프래질리티(Antifragility).
    블랙스완 보호, 바벨 전략, 극단 이벤트 대비.
    """
    name = "Nassim Taleb"

    def analyze(self, market: str, price_data: dict) -> PersonaSignal:
        import numpy as np
        score = 0
        details = {}

        close = price_data.get("close_series")
        if close is None or len(close) < 60:
            return PersonaSignal(self.name, "NEUTRAL", 0.3, 0, 10, "데이터 부족", {})

        daily_ret = close.pct_change().dropna()

        # --- 1. Tail Risk Assessment (0-4) ---
        tail_score = 0
        kurt = float(daily_ret.kurtosis())
        skew = float(daily_ret.skew())

        # Low kurtosis = safer (less black swan risk)
        if kurt < 3:
            tail_score += 2
        elif kurt < 5:
            tail_score += 1
        elif kurt > 10:
            tail_score -= 1  # Dangerous tail risk

        # Positive skew = antifragile (more upside surprises)
        if skew > 0.3:
            tail_score += 2
        elif skew > 0:
            tail_score += 1
        elif skew < -0.5:
            tail_score -= 1
        score += max(0, tail_score)
        details["tail_risk"] = max(0, tail_score)

        # --- 2. Antifragility: Benefits from volatility (0-3) ---
        anti_score = 0
        vol_20 = float(daily_ret.iloc[-20:].std()) if len(daily_ret) >= 20 else 0
        vol_60 = float(daily_ret.iloc[-60:].std()) if len(daily_ret) >= 60 else vol_20
        ret_20 = float(close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0

        # Positive returns during high vol = antifragile
        if vol_20 > vol_60 and ret_20 > 0:
            anti_score += 2
        elif ret_20 > 0:
            anti_score += 1
        # Decreasing vol with gains = barbell working
        if vol_20 < vol_60 * 0.8 and ret_20 > 0:
            anti_score += 1
        score += anti_score
        details["antifragility"] = anti_score

        # --- 3. Barbell Position (0-3) ---
        barbell_score = 0
        # VaR check: limited downside
        var_5 = float(np.percentile(daily_ret, 5))
        if var_5 > -0.02:
            barbell_score += 2  # Limited daily downside
        elif var_5 > -0.03:
            barbell_score += 1
        # Max drawdown manageable
        rolling_max = close.cummax()
        max_dd = float(((close - rolling_max) / rolling_max).min())
        if max_dd > -0.15:
            barbell_score += 1
        score += barbell_score
        details["barbell"] = barbell_score

        max_score = 10
        if score >= 7:
            signal = "BULLISH"
        elif score <= 3:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = min(0.80, 0.4 + (score / max_score) * 0.4)

        return PersonaSignal(
            self.name, signal, confidence, score, max_score,
            f"TailRisk={details['tail_risk']}/4, Antifragile={anti_score}/3, "
            f"Barbell={barbell_score}/3, Total={score}/{max_score}",
            details,
        )


# ---- Utility ----

def _trend_r_squared(series) -> float:
    """선형 추세의 R-squared 계산."""
    import numpy as np
    y = series.values
    x = np.arange(len(y))
    if len(y) < 3:
        return 0.0
    corr = np.corrcoef(x, y)[0, 1]
    return corr ** 2


# ---- Registry ----

PERSONA_AGENTS = {
    "ben_graham": BenGrahamAgent(),
    "warren_buffett": WarrenBuffettAgent(),
    "charlie_munger": CharlieMungerAgent(),
    "george_soros": GeorgeSorosAgent(),
    "peter_lynch": PeterLynchAgent(),
    "michael_burry": MichaelBurryAgent(),
    "cathie_wood": CathieWoodAgent(),
    "nassim_taleb": NassimTalebAgent(),
}

PERSONA_WEIGHTS = {
    "Ben Graham": 0.15,
    "Warren Buffett": 0.15,
    "Charlie Munger": 0.10,
    "George Soros": 0.15,
    "Peter Lynch": 0.10,
    "Michael Burry": 0.15,
    "Cathie Wood": 0.10,
    "Nassim Taleb": 0.10,
}
