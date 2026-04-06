"""
TradingAgents Team — Trader Agent
==================================
최종 거래 결정. 모든 분석 + 토론 + 리스크 패널 종합.
BM25 메모리에서 유사 과거 상황 참조.
"""
import json
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("trading-agents-team")


@dataclass
class TradeDecision:
    market: str
    signal: str           # BUY / SELL / HOLD
    confidence: float     # 0.0 ~ 1.0
    position_size: float  # 0.0 ~ 1.0
    stop_loss_pct: float
    take_profit_pct: float
    reasoning: str
    debate_summary: str
    risk_verdict: str
    analyst_breakdown: list
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class TraderAgent:
    """
    최종 거래 에이전트 — TradingAgents Trader 패턴.
    모든 입력을 종합하여 BUY/SELL/HOLD 결정.
    과거 의사결정 기억을 참조하여 실수를 반복하지 않음.
    """

    def __init__(self, claude_client=None):
        self.claude = claude_client

    def decide(self, market: str, analyst_reports: list,
               bull_case: str, bear_case: str, judge_synthesis: str,
               risk_result: dict, memory_context: str = "") -> TradeDecision:
        """
        최종 거래 결정.

        Args:
            analyst_reports: AnalystReport 리스트
            bull_case: Bull 최종 논거
            bear_case: Bear 최종 논거
            judge_synthesis: 토론 심판 종합
            risk_result: RiskPanel 결과 dict
            memory_context: 과거 기억/성과 컨텍스트
        """
        # 기본값 (risk panel에서)
        pos_size = risk_result.get("position_size_pct", 50) / 100
        sl = risk_result.get("stop_loss_pct", -7) / 100
        tp = risk_result.get("take_profit_pct", 9) / 100

        # Weighted analyst vote
        signal, confidence, breakdown = self._weighted_vote(analyst_reports)

        # Claude 최종 결정
        if self.claude:
            try:
                decision = self._claude_decision(
                    market, signal, confidence, pos_size,
                    analyst_reports, bull_case, bear_case,
                    judge_synthesis, risk_result, memory_context
                )
                if decision:
                    return decision
            except Exception as e:
                logger.debug(f"[Trader] Claude error: {e}")

        # Fallback: deterministic
        return TradeDecision(
            market=market, signal=signal, confidence=confidence,
            position_size=round(pos_size, 2),
            stop_loss_pct=sl, take_profit_pct=tp,
            reasoning=f"가중투표 점수={confidence:.3f}, signal={signal}",
            debate_summary=judge_synthesis[:200],
            risk_verdict=risk_result.get("verdict", ""),
            analyst_breakdown=breakdown,
        )

    def _weighted_vote(self, reports: list) -> tuple:
        """가중 투표로 신호 결정."""
        weights = {
            "Fundamentals Analyst": 0.25,
            "Market Analyst": 0.30,
            "News Analyst": 0.20,
            "Sentiment Analyst": 0.25,
        }
        score = 0.0
        total_w = 0.0
        breakdown = []

        for r in reports:
            w = weights.get(r.analyst_name, 0.15)
            v = {"BULLISH": 1.0, "NEUTRAL": 0.0, "BEARISH": -1.0}.get(r.signal, 0.0)
            score += v * w * r.confidence
            total_w += w
            breakdown.append({
                "analyst": r.analyst_name,
                "signal": r.signal,
                "confidence": round(r.confidence, 2),
            })

        final_score = score / total_w if total_w > 0 else 0

        if final_score >= 0.25:
            signal = "BUY"
        elif final_score <= -0.25:
            signal = "SELL"
        else:
            signal = "HOLD"

        return signal, abs(final_score), breakdown

    def _claude_decision(self, market, fallback_signal, fallback_conf, pos_size,
                         reports, bull_case, bear_case, judge, risk_result,
                         memory_context) -> Optional[TradeDecision]:
        """Claude로 최종 결정."""
        summary = "\n".join([
            f"- {r.analyst_name}: {r.signal} ({r.confidence:.0%}) — {r.report[:120]}"
            for r in reports
        ])

        prompt = f"""당신은 TradingAgents 퀀트 트레이더입니다. 최종 거래 결정을 내리세요.

{market} 시장 분석:
{summary}

토론 결과: {judge[:300]}
리스크 패널: {risk_result.get('verdict', '')[:200]}
정량 점수: {fallback_conf:.3f} → 예비 결정: {fallback_signal}

{f"과거 교훈:{chr(10)}{memory_context[:300]}" if memory_context else ""}

JSON만 반환:
{{"signal":"BUY|SELL|HOLD","confidence":0.0-1.0,"position_size":0.0-1.0,"reasoning":"2-3문장"}}"""

        msg = self.claude.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s != -1 and e > s:
            r = json.loads(raw[s:e])
            return TradeDecision(
                market=market,
                signal=r.get("signal", fallback_signal),
                confidence=float(r.get("confidence", fallback_conf)),
                position_size=float(r.get("position_size", pos_size)),
                stop_loss_pct=risk_result.get("stop_loss_pct", -7) / 100,
                take_profit_pct=risk_result.get("take_profit_pct", 9) / 100,
                reasoning=r.get("reasoning", ""),
                debate_summary=judge[:200],
                risk_verdict=risk_result.get("verdict", ""),
                analyst_breakdown=[{
                    "analyst": rp.analyst_name,
                    "signal": rp.signal,
                    "confidence": round(rp.confidence, 2),
                } for rp in reports],
            )
        return None
