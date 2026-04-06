"""
TradingAgents Team — Bull/Bear Debate System
=============================================
TradingAgents 레포의 핵심 패턴: 멀티라운드 토론.

Bull Researcher: 성장/기회/모멘텀 관점
Bear Researcher: 리스크/위기/하락 관점
Judge: 양측 논거 종합 → 최종 판단

각 라운드에서 상대 논거를 반박하며 발전.
"""
import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger("trading-agents-team")


class BullResearcher:
    """
    강세 리서처 — TradingAgents 방식.
    성장 잠재력, 경쟁 우위, 긍정적 지표를 강조.
    Bear 논거를 구체적 데이터로 반박.
    """

    @staticmethod
    def build_prompt(market: str, context: str, bear_argument: str = "",
                     round_num: int = 1, memory_hints: str = "") -> str:
        base = f"""당신은 강세(Bull) 리서처입니다. {market} 시장 매수 논거를 구축하세요.

분석 보고서:
{context}"""

        if bear_argument:
            base += f"""

[Round {round_num}] Bear 리서처의 반론:
{bear_argument}

위 약세 논거를 구체적 데이터로 반박하고, 추가 매수 근거를 제시하세요."""

        if memory_hints:
            base += f"""

과거 유사 상황에서의 교훈:
{memory_hints}"""

        base += """

핵심 포인트 3가지를 구체적 수치와 함께 제시하세요. (200자 이내)"""
        return base


class BearResearcher:
    """
    약세 리서처 — TradingAgents 방식.
    리스크, 하락 요인, 구조적 취약점 강조.
    Bull 논거의 과도한 낙관을 지적.
    """

    @staticmethod
    def build_prompt(market: str, context: str, bull_argument: str = "",
                     round_num: int = 1, memory_hints: str = "") -> str:
        base = f"""당신은 약세(Bear) 리서처입니다. {market} 시장 매도/관망 논거를 구축하세요.

분석 보고서:
{context}"""

        if bull_argument:
            base += f"""

[Round {round_num}] Bull 리서처의 주장:
{bull_argument}

위 강세 논거의 과도한 낙관을 지적하고, 간과된 리스크를 제시하세요."""

        if memory_hints:
            base += f"""

과거 유사 상황에서의 교훈:
{memory_hints}"""

        base += """

핵심 리스크 3가지를 구체적 수치와 함께 제시하세요. (200자 이내)"""
        return base


class DebateEngine:
    """
    Bull/Bear 멀티라운드 토론 엔진.
    TradingAgents의 핵심: 반복적 논쟁으로 양질의 분석 도출.
    """

    def __init__(self, claude_client=None, max_rounds: int = 2):
        self.claude = claude_client
        self.max_rounds = max_rounds

    def run_debate(self, analyst_context: str, market: str,
                   memory_hints: str = "") -> Tuple[str, str, str]:
        """
        멀티라운드 토론 실행.

        Returns:
            (bull_final, bear_final, judge_synthesis)
        """
        if not self.claude:
            return self._fallback_debate(analyst_context)

        bull_arg = ""
        bear_arg = ""

        try:
            for round_num in range(1, self.max_rounds + 1):
                logger.info(f"[Debate] Round {round_num}/{self.max_rounds}")

                # Bull turn
                bull_prompt = BullResearcher.build_prompt(
                    market, analyst_context, bear_arg, round_num, memory_hints
                )
                bull_resp = self._call_claude(bull_prompt)
                bull_arg = bull_resp

                # Bear turn
                bear_prompt = BearResearcher.build_prompt(
                    market, analyst_context, bull_arg, round_num, memory_hints
                )
                bear_resp = self._call_claude(bear_prompt)
                bear_arg = bear_resp

            # Judge synthesis
            judge_synthesis = self._judge_debate(market, bull_arg, bear_arg, analyst_context)

            return bull_arg, bear_arg, judge_synthesis

        except Exception as e:
            logger.warning(f"[Debate] Error: {e}")
            return self._fallback_debate(analyst_context)

    def _call_claude(self, prompt: str, max_tokens: int = 400) -> str:
        msg = self.claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text

    def _judge_debate(self, market: str, bull_arg: str, bear_arg: str,
                      context: str) -> str:
        """토론 심판: 양측 논거 종합."""
        prompt = f"""{market} 시장 투자 토론 심판입니다.

강세 최종 논거:
{bull_arg[:500]}

약세 최종 논거:
{bear_arg[:500]}

양측 논거의 강점과 약점을 평가하고, 종합 판단을 내리세요.
JSON만 반환:
{{"winner": "BULL|BEAR|TIE", "conviction": 0.0-1.0, "synthesis": "2-3문장 종합"}}"""

        try:
            raw = self._call_claude(prompt, 300)
            s, e = raw.find("{"), raw.rfind("}") + 1
            if s != -1 and e > s:
                r = json.loads(raw[s:e])
                return f"[{r.get('winner','TIE')}] (확신={r.get('conviction',0.5):.0%}) {r.get('synthesis','')}"
        except Exception:
            pass

        return "토론 심판 판단 불가"

    def _fallback_debate(self, context: str) -> Tuple[str, str, str]:
        return (
            "Bull: 기술적/매크로 지표 기반 상승 기대",
            "Bear: 불확실성/변동성 기반 하락 리스크",
            "Judge: 양측 균형 → 중립 판단"
        )
