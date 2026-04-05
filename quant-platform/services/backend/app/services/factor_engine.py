"""
Factor Engine
=============
월가 퀀트 표준 방식의 팩터 계산 엔진.

1. Universe Construction — 유동성/데이터 필터 후 투자 유니버스 구성
2. Factor Calculation — Momentum, Value proxy, Quality proxy, Low-Vol
3. Factor Scoring — 0-100 랭킹 → 복합 점수
4. Portfolio Construction — 상위 N종목 inverse-vol 가중치
5. Rebalancing — 목표 vs 현재 비중 비교 → 리밸런싱 거래 생성
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import FinanceDataReader as fdr
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ─── Factor Weights ──────────────────────────────────────────────────────────
FACTOR_WEIGHTS = {
    "momentum_12m1m": 0.35,   # 12개월 수익률 (최근 1개월 제외) — 모멘텀
    "momentum_3m":    0.15,   # 3개월 단기 모멘텀
    "low_vol":        0.25,   # 저변동성 — 방어적
    "value_proxy":    0.15,   # 52주 저점 대비 현재가 역수
    "quality_proxy":  0.10,   # 수익 일관성 (Sharpe proxy)
}

# ─── Universe Params ─────────────────────────────────────────────────────────
MIN_TRADING_DAYS = 60        # 최소 거래일 수
TOP_N_PORTFOLIO   = 20       # 포트폴리오 편입 종목 수
MAX_WEIGHT        = 0.15     # 종목당 최대 비중 15%
MIN_WEIGHT        = 0.01     # 종목당 최소 비중 1%


class FactorEngine:
    """
    팩터 계산 엔진.
    DB에 저장된 price 데이터를 기반으로 유니버스 팩터 점수 계산.
    """

    def run(
        self,
        db: Session,
        market: str = "ALL",
        as_of_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        팩터 스코어 계산 후 DB 저장.

        Returns:
            DataFrame: symbol, factor scores, composite_score, rank
        """
        if as_of_date is None:
            as_of_date = datetime.today().strftime("%Y-%m-%d")

        end_dt = pd.Timestamp(as_of_date)
        start_dt = end_dt - timedelta(days=400)  # 팩터 계산에 필요한 히스토리

        logger.info(f"[FactorEngine] Running for market={market}, as_of={as_of_date}")

        # 1. Load price data from DB
        prices = self._load_prices(db, market, start_dt, end_dt)
        if prices.empty:
            logger.warning("[FactorEngine] No price data found")
            return pd.DataFrame()

        # 2. Build universe (filter by minimum trading days)
        universe = self._build_universe(prices)
        if universe.empty:
            logger.warning("[FactorEngine] Universe is empty after filtering")
            return pd.DataFrame()

        logger.info(f"[FactorEngine] Universe size: {len(universe.columns)} stocks")

        # 3. Calculate factors
        factors = self._calculate_factors(universe)

        # 4. Score & rank
        scores = self._score_factors(factors)

        # 5. Save to DB
        self._save_scores(db, scores, as_of_date, market)

        return scores

    def _load_prices(
        self,
        db: Session,
        market: str,
        start_dt: pd.Timestamp,
        end_dt: pd.Timestamp,
    ) -> pd.DataFrame:
        """DB에서 종가 데이터 로드."""
        market_clause = "" if market == "ALL" else "AND market = :market"
        params = {
            "start": start_dt.date(),
            "end": end_dt.date(),
        }
        if market != "ALL":
            params["market"] = market

        rows = db.execute(text(f"""
            SELECT symbol, date, COALESCE(adj_close, close) AS price
            FROM market_data
            WHERE date BETWEEN :start AND :end
            {market_clause}
            ORDER BY symbol, date
        """), params).fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=["symbol", "date", "price"])
        df["date"] = pd.to_datetime(df["date"])
        pivot = df.pivot(index="date", columns="symbol", values="price")
        pivot = pivot.sort_index()
        return pivot

    def _build_universe(self, prices: pd.DataFrame) -> pd.DataFrame:
        """유동성/데이터 필터 적용해 투자 유니버스 구성."""
        # 최소 거래일 수 충족하는 종목만
        valid = prices.columns[prices.count() >= MIN_TRADING_DAYS]
        universe = prices[valid].copy()

        # 최근 가격 결측치 제거 (최근 5일 내 데이터 없으면 제외)
        recent = universe.iloc[-5:]
        active = recent.columns[recent.notna().any()]
        return universe[active]

    def _calculate_factors(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        각 종목별 팩터 계산.

        팩터:
        - momentum_12m1m: 252일전~21일전 수익률 (모멘텀 표준)
        - momentum_3m:    63일전~현재 수익률
        - low_vol:        60일 rolling std (낮을수록 좋음 → 역수)
        - value_proxy:    현재가 / 52주 최고가 역수 (싸게 살수록 좋음)
        - quality_proxy:  과거 1년 일간수익률 Sharpe (높을수록 좋음)
        """
        factors = pd.DataFrame(index=prices.columns)

        last_price = prices.iloc[-1]

        # ── Momentum 12M-1M ─────────────────────────────────────────────────
        p_252 = prices.iloc[-252] if len(prices) >= 252 else prices.iloc[0]
        p_21  = prices.iloc[-21]  if len(prices) >= 21  else prices.iloc[-1]

        mom_12m1m = (p_21 / (p_252 + 1e-10)) - 1
        mom_12m1m = mom_12m1m.replace([np.inf, -np.inf], np.nan)
        factors["momentum_12m1m"] = mom_12m1m

        # ── Momentum 3M ──────────────────────────────────────────────────────
        p_63 = prices.iloc[-63] if len(prices) >= 63 else prices.iloc[0]
        mom_3m = (last_price / (p_63 + 1e-10)) - 1
        mom_3m = mom_3m.replace([np.inf, -np.inf], np.nan)
        factors["momentum_3m"] = mom_3m

        # ── Low Volatility ───────────────────────────────────────────────────
        daily_returns = prices.pct_change().dropna()
        recent_returns = daily_returns.iloc[-60:]
        vol_60d = recent_returns.std()
        vol_60d = vol_60d.replace([np.inf, -np.inf], np.nan)
        # 낮은 변동성 = 좋음 → 역수 변환 (후에 rank로 처리하므로 부호만 반전)
        factors["low_vol"] = -vol_60d  # 낮은 vol → 높은 값

        # ── Value Proxy ──────────────────────────────────────────────────────
        high_252 = prices.iloc[-252:].max() if len(prices) >= 252 else prices.max()
        # 52주 최고가 대비 현재가 비율 — 낮을수록 저렴 → 역수
        price_to_high = last_price / (high_252 + 1e-10)
        factors["value_proxy"] = -price_to_high  # 낮은 비율 = 저렴 = 좋음

        # ── Quality Proxy (Sharpe) ───────────────────────────────────────────
        annual_returns = daily_returns.iloc[-252:] if len(daily_returns) >= 252 else daily_returns
        quality = annual_returns.mean() / (annual_returns.std() + 1e-10)
        quality = quality.replace([np.inf, -np.inf], np.nan)
        factors["quality_proxy"] = quality

        return factors

    def _score_factors(self, factors: pd.DataFrame) -> pd.DataFrame:
        """
        각 팩터를 0-100으로 랭킹 후 가중 합산.
        """
        scored = pd.DataFrame(index=factors.index)

        # 각 팩터를 percentile rank (0-100)
        for col in factors.columns:
            scored[f"{col}_rank"] = (
                factors[col]
                .rank(pct=True, na_option="bottom", ascending=True)
                .mul(100)
                .round(1)
            )

        # 복합 점수 계산
        composite = pd.Series(0.0, index=factors.index)
        for factor, weight in FACTOR_WEIGHTS.items():
            rank_col = f"{factor}_rank"
            if rank_col in scored.columns:
                composite += scored[rank_col].fillna(50) * weight

        scored["composite_score"] = composite.round(2)
        scored["rank"] = composite.rank(ascending=False, method="min").astype(int)

        # 원본 팩터값도 포함
        for col in factors.columns:
            scored[col] = factors[col].round(4)

        return scored.sort_values("rank")

    def _save_scores(
        self,
        db: Session,
        scores: pd.DataFrame,
        as_of_date: str,
        market: str,
    ):
        """팩터 점수를 DB에 저장 (upsert)."""
        try:
            for symbol, row in scores.iterrows():
                db.execute(text("""
                    INSERT INTO factor_scores
                        (symbol, score_date, market,
                         momentum_12m1m, momentum_3m, low_vol,
                         value_proxy, quality_proxy,
                         momentum_12m1m_rank, momentum_3m_rank, low_vol_rank,
                         value_proxy_rank, quality_proxy_rank,
                         composite_score, rank)
                    VALUES
                        (:symbol, :score_date, :market,
                         :momentum_12m1m, :momentum_3m, :low_vol,
                         :value_proxy, :quality_proxy,
                         :momentum_12m1m_rank, :momentum_3m_rank, :low_vol_rank,
                         :value_proxy_rank, :quality_proxy_rank,
                         :composite_score, :rank)
                    ON CONFLICT (symbol, score_date, market)
                    DO UPDATE SET
                        momentum_12m1m       = EXCLUDED.momentum_12m1m,
                        momentum_3m          = EXCLUDED.momentum_3m,
                        low_vol              = EXCLUDED.low_vol,
                        value_proxy          = EXCLUDED.value_proxy,
                        quality_proxy        = EXCLUDED.quality_proxy,
                        momentum_12m1m_rank  = EXCLUDED.momentum_12m1m_rank,
                        momentum_3m_rank     = EXCLUDED.momentum_3m_rank,
                        low_vol_rank         = EXCLUDED.low_vol_rank,
                        value_proxy_rank     = EXCLUDED.value_proxy_rank,
                        quality_proxy_rank   = EXCLUDED.quality_proxy_rank,
                        composite_score      = EXCLUDED.composite_score,
                        rank                 = EXCLUDED.rank,
                        updated_at           = NOW()
                """), {
                    "symbol":               symbol,
                    "score_date":           as_of_date,
                    "market":               market,
                    "momentum_12m1m":       _safe_float(row.get("momentum_12m1m")),
                    "momentum_3m":          _safe_float(row.get("momentum_3m")),
                    "low_vol":              _safe_float(row.get("low_vol")),
                    "value_proxy":          _safe_float(row.get("value_proxy")),
                    "quality_proxy":        _safe_float(row.get("quality_proxy")),
                    "momentum_12m1m_rank":  _safe_float(row.get("momentum_12m1m_rank")),
                    "momentum_3m_rank":     _safe_float(row.get("momentum_3m_rank")),
                    "low_vol_rank":         _safe_float(row.get("low_vol_rank")),
                    "value_proxy_rank":     _safe_float(row.get("value_proxy_rank")),
                    "quality_proxy_rank":   _safe_float(row.get("quality_proxy_rank")),
                    "composite_score":      _safe_float(row.get("composite_score")),
                    "rank":                 int(row.get("rank", 9999)),
                })
            db.commit()
            logger.info(f"[FactorEngine] Saved {len(scores)} factor scores")
        except Exception as e:
            logger.error(f"[FactorEngine] Failed to save scores: {e}")
            db.rollback()


class PortfolioOptimizer:
    """
    포트폴리오 최적화.
    팩터 상위 N종목 선택 후 inverse-vol 가중치 계산.
    최대/최소 비중 제약 적용.
    """

    def build_portfolio(
        self,
        db: Session,
        team_id: str,
        market: str = "ALL",
        as_of_date: Optional[str] = None,
        top_n: int = TOP_N_PORTFOLIO,
    ) -> Dict:
        """
        팩터 스코어 기반 포트폴리오 구성.

        Returns:
            dict: {symbol: target_weight, ...}
        """
        if as_of_date is None:
            as_of_date = datetime.today().strftime("%Y-%m-%d")

        # 1. 팩터 스코어 상위 종목 조회
        market_clause = "" if market == "ALL" else "AND market = :market"
        params = {"score_date": as_of_date, "top_n": top_n}
        if market != "ALL":
            params["market"] = market

        rows = db.execute(text(f"""
            SELECT symbol, composite_score, low_vol
            FROM factor_scores
            WHERE score_date = :score_date
            {market_clause}
            ORDER BY rank ASC
            LIMIT :top_n
        """), params).fetchall()

        if not rows:
            logger.warning(f"[PortfolioOptimizer] No factor scores for {as_of_date}")
            return {}

        symbols = [r[0] for r in rows]
        vol_values = {r[0]: abs(r[2]) if r[2] is not None else 0.02 for r in rows}

        # 2. Inverse-vol 가중치 계산
        weights = self._inverse_vol_weights(symbols, vol_values)

        # 3. 포지션 DB 저장
        self._save_positions(db, team_id, weights, as_of_date)

        logger.info(
            f"[PortfolioOptimizer] Built portfolio for {team_id}: "
            f"{len(weights)} stocks, top={list(weights.items())[:5]}"
        )

        return weights

    def _inverse_vol_weights(
        self,
        symbols: List[str],
        vol_values: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Inverse-volatility weighting.
        낮은 변동성 종목에 더 높은 비중.
        """
        # vol이 0이면 작은 값으로 대체
        vols = np.array([max(vol_values.get(s, 0.02), 0.001) for s in symbols])
        inv_vols = 1.0 / vols
        raw_weights = inv_vols / inv_vols.sum()

        # 최대/최소 비중 제약 (클리핑 후 재정규화)
        clipped = np.clip(raw_weights, MIN_WEIGHT, MAX_WEIGHT)
        normalized = clipped / clipped.sum()

        return {sym: round(float(w), 4) for sym, w in zip(symbols, normalized)}

    def _save_positions(
        self,
        db: Session,
        team_id: str,
        weights: Dict[str, float],
        as_of_date: str,
    ):
        """목표 포지션을 DB에 저장."""
        try:
            # 기존 포지션을 inactive로 표시
            db.execute(text("""
                UPDATE portfolio_positions
                SET is_active = FALSE
                WHERE team_id = :team_id
            """), {"team_id": team_id})

            # 새 포지션 삽입
            for symbol, weight in weights.items():
                db.execute(text("""
                    INSERT INTO portfolio_positions
                        (team_id, symbol, target_weight, last_rebalanced, is_active)
                    VALUES
                        (:team_id, :symbol, :weight, :date, TRUE)
                    ON CONFLICT (team_id, symbol)
                    DO UPDATE SET
                        target_weight    = EXCLUDED.target_weight,
                        last_rebalanced  = EXCLUDED.last_rebalanced,
                        is_active        = TRUE,
                        updated_at       = NOW()
                """), {
                    "team_id": team_id,
                    "symbol":  symbol,
                    "weight":  weight,
                    "date":    as_of_date,
                })

            db.commit()
        except Exception as e:
            logger.error(f"[PortfolioOptimizer] Failed to save positions: {e}")
            db.rollback()


class RebalanceEngine:
    """
    리밸런싱 엔진.
    현재 vs 목표 비중 비교 → 필요한 매수/매도 목록 생성.
    """

    def rebalance(
        self,
        db: Session,
        team_id: str,
        current_capital: float = 1_000_000_000,  # 기본 10억
        threshold_pct: float = 2.0,              # 2%이상 편차시 리밸런싱
    ) -> Dict:
        """
        리밸런싱 필요 여부 체크 + 거래 목록 생성.

        Returns:
            dict: {type, trades, summary}
        """
        # 현재 목표 포지션 로드
        rows = db.execute(text("""
            SELECT symbol, target_weight
            FROM portfolio_positions
            WHERE team_id = :team_id AND is_active = TRUE
            ORDER BY target_weight DESC
        """), {"team_id": team_id}).fetchall()

        if not rows:
            return {"type": "no_positions", "trades": [], "summary": "포지션 없음"}

        target_weights = {r[0]: float(r[1]) for r in rows}

        trades = []
        total_drift = 0.0

        for symbol, target_w in target_weights.items():
            # 현재 비중은 단순화 — 실제 운용에서는 현재 보유수량/현재가 계산
            # 여기서는 리밸런싱 필요 거래액만 계산
            target_value = current_capital * target_w
            trades.append({
                "symbol": symbol,
                "action": "REBALANCE",
                "target_weight": round(target_w * 100, 2),
                "target_value_krw": round(target_value),
            })

        # 리밸런싱 이력 저장
        summary = (
            f"총 {len(trades)}개 종목 목표 비중 설정. "
            f"자본 {current_capital/100_000_000:.0f}억원 기준."
        )
        self._save_rebalance_history(db, team_id, trades, summary)

        return {
            "type":    "rebalance",
            "trades":  trades,
            "summary": summary,
        }

    def _save_rebalance_history(
        self,
        db: Session,
        team_id: str,
        trades: List[Dict],
        summary: str,
    ):
        """리밸런싱 이력 저장."""
        try:
            import json
            db.execute(text("""
                INSERT INTO rebalance_history
                    (team_id, rebalance_date, trades, summary)
                VALUES
                    (:team_id, NOW()::date, :trades, :summary)
            """), {
                "team_id": team_id,
                "trades":  json.dumps(trades, ensure_ascii=False),
                "summary": summary,
            })
            db.commit()
        except Exception as e:
            logger.error(f"[RebalanceEngine] Failed to save history: {e}")
            db.rollback()


# ─── Singletons ───────────────────────────────────────────────────────────────
factor_engine      = FactorEngine()
portfolio_optimizer = PortfolioOptimizer()
rebalance_engine   = RebalanceEngine()


# ─── Utilities ───────────────────────────────────────────────────────────────
def _safe_float(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        return float(v)
    except Exception:
        return None
