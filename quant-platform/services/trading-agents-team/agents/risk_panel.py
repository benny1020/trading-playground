"""
TradingAgents Team — Risk Panel (3인 토론)
==========================================
TradingAgents 레포 패턴: Conservative / Neutral / Aggressive 3인 리스크 토론.

각 위험 프로필이 Trader의 결정에 대해 토론 → 합의된 리스크 평가 도출.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger("trading-agents-team")


class RiskDebater:
    """개별 리스크 토론자."""

    def __init__(self, profile: str, description: str):
        self.profile = profile
        self.description = description

    def build_prompt(self, market: str, bull_case: str, bear_case: str,
                     judge_synthesis: str, other_arguments: str = "") -> str:
        return f"""당신은 {self.profile} 리스크 분석가입니다.
성격: {self.description}

{market} 시장 토론 결과:
- Bull: {bull_case[:300]}
- Bear: {bear_case[:300]}
- Judge: {judge_synthesis[:200]}

{f"다른 분석가들의 의견:{chr(10)}{other_arguments}" if other_arguments else ""}

당신의 리스크 프로필 관점에서 포지션 크기(0-100%)와 핵심 리스크를 1-2문장으로 제시하세요."""


CONSERVATIVE = RiskDebater(
    "보수적 (Conservative)",
    "자본 보존 최우선. 불확실성 높으면 포지션 축소. MDD < 10% 목표. "
    "잠재 손실이 잠재 이익보다 중요."
)
NEUTRAL = RiskDebater(
    "중립적 (Neutral)",
    "리스크/리워드 균형 추구. 과도한 낙관도 과도한 비관도 경계. "
    "분산 투자와 적절한 포지션 사이징."
)
AGGRESSIVE = RiskDebater(
    "공격적 (Aggressive)",
    "수익 극대화 추구. 기회가 보이면 과감한 포지션. "
    "변동성은 기회. 보수적 관점이 기회를 놓치는 비용을 간과한다고 봄."
)


class RiskPanel:
    """
    3인 리스크 패널.
    Conservative → Aggressive → Neutral 순으로 토론 후 합의.
    """

    def __init__(self, claude_client=None):
        self.claude = claude_client
        self.debaters = [CONSERVATIVE, AGGRESSIVE, NEUTRAL]

    def deliberate(self, market: str, bull_case: str, bear_case: str,
                   judge_synthesis: str) -> dict:
        """
        리스크 패널 토론 실행.

        Returns:
            dict: {position_size, stop_loss, take_profit, verdict, arguments}
        """
        if not self.claude:
            return self._fallback()

        arguments = {}
        try:
            for debater in self.debaters:
                other_args = "\n".join([
                    f"- {name}: {arg[:150]}" for name, arg in arguments.items()
                ])
                prompt = debater.build_prompt(market, bull_case, bear_case,
                                               judge_synthesis, other_args)
                msg = self.claude.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=200,
                    messages=[{"role": "user", "content": prompt}]
                )
                arguments[debater.profile] = msg.content[0].text

            # 합의 도출
            consensus = self._synthesize(market, arguments, judge_synthesis)
            return consensus

        except Exception as e:
            logger.warning(f"[RiskPanel] Error: {e}")
            return self._fallback()

    def _synthesize(self, market: str, arguments: dict, judge: str) -> dict:
        """3인 의견 종합."""
        prompt = f"""{market} 시장 리스크 패널 합의를 도출하세요.

{chr(10).join([f"- {name}: {arg[:200]}" for name, arg in arguments.items()])}

토론 심판: {judge[:200]}

JSON만 반환:
{{"position_size_pct": 0-100, "stop_loss_pct": -1~-15, "take_profit_pct": 3-20, "verdict": "종합 리스크 평가 한 문장"}}"""

        try:
            msg = self.claude.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text
            s, e = raw.find("{"), raw.rfind("}") + 1
            if s != -1 and e > s:
                r = json.loads(raw[s:e])
                r["arguments"] = arguments
                return r
        except Exception:
            pass

        return self._fallback()

    def _fallback(self) -> dict:
        return {
            "position_size_pct": 50,
            "stop_loss_pct": -7,
            "take_profit_pct": 9,
            "verdict": "리스크 패널 API 없음 — 기본 중립",
            "arguments": {},
        }
