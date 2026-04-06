"""
AI Hedge Fund Team — Risk Manager
===================================
변동성-상관관계 기반 포지션 한도 조절.
ai-hedge-fund 레포 패턴: Vol-adjusted limits + correlation multiplier.
"""
import logging
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("ai-hedge-fund-team")


@dataclass
class RiskAssessment:
    market: str
    annualized_vol: float
    vol_regime: str              # LOW / NORMAL / HIGH / EXTREME
    position_limit_pct: float    # 0.0 ~ 1.0
    stop_loss_pct: float
    take_profit_pct: float
    max_drawdown_limit: float
    risk_score: float            # 0(safe) ~ 1(dangerous)
    reasoning: str


class RiskManager:
    """
    변동성-상관관계 리스크 매니저.
    포지션 크기를 변동성에 반비례하게 조절.
    """

    # Volatility regime thresholds (annualized)
    VOL_LOW = 0.12
    VOL_NORMAL = 0.20
    VOL_HIGH = 0.35
    # Base position limit
    BASE_LIMIT = 0.20  # 20%

    def assess(self, market: str, price_data: dict,
               active_positions: Optional[List[dict]] = None) -> RiskAssessment:
        """포지션 리스크 평가."""
        close = price_data.get("close_series")
        if close is None or len(close) < 30:
            return self._default_assessment(market)

        daily_ret = close.pct_change().dropna()
        ann_vol = float(daily_ret.std() * np.sqrt(252))

        # --- Volatility Regime ---
        if ann_vol < self.VOL_LOW:
            vol_regime = "LOW"
            vol_multiplier = 1.25
        elif ann_vol < self.VOL_NORMAL:
            vol_regime = "NORMAL"
            vol_multiplier = 1.0 - (ann_vol - self.VOL_LOW) * 0.5
        elif ann_vol < self.VOL_HIGH:
            vol_regime = "HIGH"
            vol_multiplier = 0.75 - (ann_vol - self.VOL_NORMAL) * 0.5
        else:
            vol_regime = "EXTREME"
            vol_multiplier = 0.40

        position_limit = self.BASE_LIMIT * vol_multiplier

        # --- Correlation Adjustment ---
        if active_positions:
            corr_mult = self._correlation_multiplier(close, active_positions)
            position_limit *= corr_mult

        position_limit = max(0.05, min(0.30, position_limit))

        # --- Stop Loss / Take Profit ---
        atr_pct = self._atr_percentage(close)
        stop_loss = -max(atr_pct * 2, 0.03)
        take_profit = max(atr_pct * 3, 0.05)

        # --- Risk Score ---
        risk_score = min(1.0, ann_vol / 0.50)

        # --- Max Drawdown ---
        rolling_max = close.cummax()
        current_dd = float((close.iloc[-1] - rolling_max.iloc[-1]) / rolling_max.iloc[-1])
        max_dd_limit = -0.15 if vol_regime in ("LOW", "NORMAL") else -0.10

        return RiskAssessment(
            market=market,
            annualized_vol=round(ann_vol, 4),
            vol_regime=vol_regime,
            position_limit_pct=round(position_limit, 4),
            stop_loss_pct=round(stop_loss, 4),
            take_profit_pct=round(take_profit, 4),
            max_drawdown_limit=max_dd_limit,
            risk_score=round(risk_score, 4),
            reasoning=(
                f"Vol={ann_vol*100:.1f}% ({vol_regime}), "
                f"Position Limit={position_limit*100:.1f}%, "
                f"SL={stop_loss*100:.1f}%, TP={take_profit*100:.1f}%, "
                f"Current DD={current_dd*100:.1f}%"
            ),
        )

    def _atr_percentage(self, close, period: int = 14) -> float:
        """ATR을 가격 대비 비율로 반환."""
        if len(close) < period + 1:
            return 0.02
        high = close.rolling(2).max()
        low = close.rolling(2).min()
        tr = high - low
        atr = float(tr.rolling(period).mean().iloc[-1])
        return atr / float(close.iloc[-1])

    def _correlation_multiplier(self, close, active_positions: List[dict]) -> float:
        """활성 포지션과의 상관관계에 따른 멀티플라이어."""
        # Simplified: use average correlation estimate from volatility clustering
        correlations = []
        for pos in active_positions:
            pos_close = pos.get("close_series")
            if pos_close is not None and len(pos_close) >= 30:
                aligned = close.iloc[-60:].align(pos_close.iloc[-60:], join="inner")[0]
                if len(aligned) > 20:
                    ret1 = close.iloc[-60:].pct_change().dropna()
                    ret2 = pos_close.iloc[-60:].pct_change().dropna()
                    min_len = min(len(ret1), len(ret2))
                    if min_len > 10:
                        corr = float(np.corrcoef(
                            ret1.values[-min_len:], ret2.values[-min_len:]
                        )[0, 1])
                        correlations.append(corr)

        if not correlations:
            return 1.0

        avg_corr = float(np.mean(correlations))

        if avg_corr >= 0.80:
            return 0.70
        elif avg_corr >= 0.60:
            return 0.85
        elif avg_corr >= 0.40:
            return 1.00
        elif avg_corr >= 0.20:
            return 1.05
        else:
            return 1.10

    def _default_assessment(self, market: str) -> RiskAssessment:
        return RiskAssessment(
            market=market,
            annualized_vol=0.20,
            vol_regime="NORMAL",
            position_limit_pct=0.15,
            stop_loss_pct=-0.07,
            take_profit_pct=0.10,
            max_drawdown_limit=-0.15,
            risk_score=0.40,
            reasoning="데이터 부족 — 기본 중립 리스크 설정",
        )
