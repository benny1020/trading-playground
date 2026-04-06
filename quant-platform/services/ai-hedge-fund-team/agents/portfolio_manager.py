"""
AI Hedge Fund Team — Portfolio Manager
========================================
전설적 투자자 시그널 종합 → 최종 포트폴리오 결정.
ai-hedge-fund 레포 패턴: 가중 투표 + LLM 최종 판단 + 제약 조건 적용.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .personas import PersonaSignal, PERSONA_WEIGHTS
from .risk_manager import RiskAssessment

logger = logging.getLogger("ai-hedge-fund-team")


@dataclass
class PortfolioDecision:
    market: str
    signal: str           # BUY / SELL / HOLD
    confidence: float
    position_size: float  # 0.0 ~ 1.0
    stop_loss_pct: float
    take_profit_pct: float
    reasoning: str
    persona_breakdown: list
    risk_assessment: str
    consensus_score: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class PortfolioManager:
    """
    포트폴리오 매니저 — 8인 투자자 신호 종합.
    가중 투표 → 리스크 조절 → 최종 BUY/SELL/HOLD.
    """

    def __init__(self, claude_client=None):
        self.claude = claude_client

    def decide(self, market: str, persona_signals: List[PersonaSignal],
               risk: RiskAssessment, memory_context: str = "") -> PortfolioDecision:
        """모든 투자자 페르소나 시그널을 종합하여 최종 결정."""
        # 1. Weighted consensus vote
        consensus_score, breakdown = self._weighted_consensus(persona_signals)

        # 2. Deterministic signal
        if consensus_score >= 0.25:
            det_signal = "BUY"
        elif consensus_score <= -0.25:
            det_signal = "SELL"
        else:
            det_signal = "HOLD"

        det_confidence = min(0.95, abs(consensus_score))

        # 3. Risk-adjusted position sizing
        base_position = risk.position_limit_pct
        if det_signal == "HOLD":
            position_size = base_position * 0.5
        else:
            position_size = base_position * det_confidence

        # 4. Claude enhancement (if available)
        if self.claude and det_signal != "HOLD":
            try:
                claude_decision = self._claude_enhance(
                    market, det_signal, det_confidence, consensus_score,
                    persona_signals, risk, memory_context
                )
                if claude_decision:
                    return claude_decision
            except Exception as e:
                logger.debug(f"[PM] Claude error: {e}")

        # 5. Fallback: deterministic decision
        return PortfolioDecision(
            market=market,
            signal=det_signal,
            confidence=round(det_confidence, 3),
            position_size=round(position_size, 3),
            stop_loss_pct=risk.stop_loss_pct,
            take_profit_pct=risk.take_profit_pct,
            reasoning=(
                f"8인 투자자 컨센서스={consensus_score:.3f} → {det_signal}, "
                f"리스크: {risk.vol_regime} (포지션 한도={risk.position_limit_pct*100:.0f}%)"
            ),
            persona_breakdown=breakdown,
            risk_assessment=risk.reasoning,
            consensus_score=round(consensus_score, 4),
        )

    def _weighted_consensus(self, signals: List[PersonaSignal]) -> tuple:
        """가중 투표로 컨센서스 점수 계산."""
        score = 0.0
        total_weight = 0.0
        breakdown = []

        signal_map = {"BULLISH": 1.0, "NEUTRAL": 0.0, "BEARISH": -1.0}

        for s in signals:
            w = PERSONA_WEIGHTS.get(s.persona_name, 0.10)
            v = signal_map.get(s.signal, 0.0)
            score += v * w * s.confidence
            total_weight += w
            breakdown.append({
                "persona": s.persona_name,
                "signal": s.signal,
                "confidence": round(s.confidence, 3),
                "score": round(s.score, 1),
                "max_score": round(s.max_score, 1),
                "reasoning": s.reasoning[:120],
            })

        consensus = score / total_weight if total_weight > 0 else 0
        return consensus, breakdown

    def _claude_enhance(self, market, det_signal, det_confidence, consensus,
                        signals, risk, memory_context) -> Optional[PortfolioDecision]:
        """Claude로 최종 판단 강화."""
        signal_summary = "\n".join([
            f"- {s.persona_name}: {s.signal} ({s.confidence:.0%}) — {s.reasoning[:100]}"
            for s in signals
        ])

        prompt = f"""당신은 AI Hedge Fund 포트폴리오 매니저입니다.
8명의 전설적 투자자 페르소나가 분석한 결과를 종합하여 최종 결정을 내리세요.

{market} 시장:
{signal_summary}

리스크: {risk.reasoning}
정량 컨센서스: {consensus:.3f} → 예비 결정: {det_signal} (확신={det_confidence:.0%})

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
            _, breakdown = self._weighted_consensus(signals)
            return PortfolioDecision(
                market=market,
                signal=r.get("signal", det_signal),
                confidence=float(r.get("confidence", det_confidence)),
                position_size=float(r.get("position_size", risk.position_limit_pct)),
                stop_loss_pct=risk.stop_loss_pct,
                take_profit_pct=risk.take_profit_pct,
                reasoning=r.get("reasoning", ""),
                persona_breakdown=breakdown,
                risk_assessment=risk.reasoning,
                consensus_score=round(consensus, 4),
            )
        return None
