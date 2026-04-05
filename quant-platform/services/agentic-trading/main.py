"""
Agentic Trading System - v2
============================
통합 멀티에이전트 AI 트레이딩 시스템

영감:
- TradingAgents (Tauric Research): Bull/Bear Debate + Risk Panel
- ai-hedge-fund (virattt): 투자 거장 페르소나 에이전트
- 자체 설계: 거시/미시/뉴스/기술/감성 분석

아키텍처:
┌─────────────────────────────────────────────────────────────────────┐
│                      ANALYST LAYER                                   │
│  [거시] [미시] [뉴스] [기술] [감성]  +  [버핏] [린치] [소로스] [버리] │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ reports
┌───────────────────────────▼─────────────────────────────────────────┐
│                    DEBATE LAYER (TradingAgents 방식)                  │
│              Bull Researcher  ←→  Bear Researcher                    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ debate transcript
┌───────────────────────────▼─────────────────────────────────────────┐
│                 RISK PANEL (3인 토론)                                  │
│          Conservative ←→ Neutral ←→ Aggressive                      │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│              PORTFOLIO MANAGER (최종 판결)                             │
│        BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL                  │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

import httpx
import feedparser
from sqlalchemy import create_engine, text
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [agentic-v2] %(levelname)s %(message)s"
)
logger = logging.getLogger("agentic-trading")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quantpass@postgres:5432/quantdb")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

engine = create_engine(DATABASE_URL)


# ─────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────

@dataclass
class AnalystReport:
    analyst_name: str
    signal: str          # BULLISH / BEARISH / NEUTRAL
    confidence: float    # 0-1
    report: str          # Full analysis text
    data_points: dict = field(default_factory=dict)


@dataclass
class FinalDecision:
    market: str
    symbols: list
    signal: str           # BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL
    confidence: float
    position_size: float  # 0-1
    stop_loss_pct: float
    take_profit_pct: float
    bull_case: str
    bear_case: str
    risk_panel_verdict: str
    portfolio_manager_reasoning: str
    all_reports: list
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ─────────────────────────────────────────────────────────────
# Analyst Layer
# ─────────────────────────────────────────────────────────────

class MacroAnalyst:
    """거시경제: 금리, VIX, 환율, 경기사이클"""
    name = "Macro Analyst"

    def analyze(self, market: str, claude_client=None) -> AnalystReport:
        data = {}
        try:
            import yfinance as yf
            vix = yf.Ticker("^VIX").history(period="5d")
            tnx = yf.Ticker("^TNX").history(period="5d")
            usdkrw = yf.Ticker("KRW=X").history(period="5d")

            if not vix.empty:
                data["vix"] = round(float(vix["Close"].iloc[-1]), 2)
                data["vix_5d_change"] = round(float(vix["Close"].iloc[-1] / vix["Close"].iloc[0] - 1), 4)
            if not tnx.empty:
                data["us_10y_yield"] = round(float(tnx["Close"].iloc[-1]), 2)
            if not usdkrw.empty:
                data["usdkrw"] = round(float(usdkrw["Close"].iloc[-1]), 0)
        except Exception as e:
            logger.debug(f"Macro data fetch: {e}")

        vix = data.get("vix", 20)
        yield_10y = data.get("us_10y_yield", 4.5)
        usdkrw = data.get("usdkrw", 1300)

        score = 0
        if vix < 15: score += 2
        elif vix < 20: score += 1
        elif vix > 30: score -= 2
        elif vix > 25: score -= 1
        if data.get("vix_5d_change", 0) > 0.1: score -= 1
        if yield_10y > 5.0: score -= 1
        elif yield_10y < 3.5: score += 1
        if market in ("KOSPI", "KOSDAQ") and usdkrw > 1380: score -= 1

        report = (
            f"VIX={vix} (5d change={data.get('vix_5d_change',0)*100:.1f}%), "
            f"US 10Y={yield_10y}%, USD/KRW={usdkrw:.0f}\n"
            f"거시 환경: {'위험회피(Risk-Off)' if score <= -1 else '위험선호(Risk-On)' if score >= 1 else '중립'}"
        )

        signal = "BULLISH" if score >= 1 else "BEARISH" if score <= -1 else "NEUTRAL"
        confidence = min(0.85, 0.5 + abs(score) * 0.1)
        return AnalystReport(self.name, signal, confidence, report, data)


class MicroAnalyst:
    """미시경제: 시장 모멘텀, 섹터 순환, 밸류에이션"""
    name = "Micro Analyst"

    def analyze(self, market: str, symbols: list, claude_client=None) -> AnalystReport:
        try:
            import FinanceDataReader as fdr
            idx_map = {"KOSPI": "KS11", "KOSDAQ": "KQ11", "US": "^GSPC"}
            symbol = idx_map.get(market, "^GSPC")
            df = fdr.DataReader(symbol, datetime.now() - timedelta(days=120))
            if len(df) < 20:
                return AnalystReport(self.name, "NEUTRAL", 0.4, "데이터 부족")

            close = df["Close"]
            ret_20d = float(close.iloc[-1] / close.iloc[-20] - 1)
            ret_60d = float(close.iloc[-1] / close.iloc[-60] - 1) if len(df) >= 60 else 0
            vol_20d = float(close.pct_change().tail(20).std() * (252**0.5))

            score = 0
            if ret_20d > 0.02: score += 1
            if ret_20d > 0.05: score += 1
            if ret_60d > 0.05: score += 1
            if ret_20d < -0.02: score -= 1
            if ret_20d < -0.05: score -= 1
            if vol_20d > 0.25: score -= 1

            report = (
                f"{market} 지수 20일 수익률: {ret_20d*100:.1f}%, "
                f"60일 수익률: {ret_60d*100:.1f}%, "
                f"20일 변동성(연환산): {vol_20d*100:.1f}%"
            )
            signal = "BULLISH" if score >= 2 else "BEARISH" if score <= -1 else "NEUTRAL"
            confidence = min(0.80, 0.5 + abs(score) * 0.1)
            return AnalystReport(self.name, signal, confidence, report,
                                 {"ret_20d": ret_20d, "ret_60d": ret_60d, "vol": vol_20d})
        except Exception as e:
            return AnalystReport(self.name, "NEUTRAL", 0.3, f"분석 오류: {e}")


class NewsAnalyst:
    """언론/뉴스 감성 분석"""
    name = "News Analyst"

    NEWS_FEEDS = [
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
        "https://www.hankyung.com/feed/economy",
    ]

    def analyze(self, market: str, claude_client=None) -> AnalystReport:
        headlines = []
        for url in self.NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                for e in feed.entries[:5]:
                    t = e.get("title", "")
                    if t: headlines.append(t)
            except Exception:
                pass

        if not headlines:
            return AnalystReport(self.name, "NEUTRAL", 0.3, "뉴스 없음")

        # Claude 감성 분석
        if claude_client and headlines:
            try:
                prompt = f"""다음 금융 뉴스 헤드라인의 {market} 시장 감성을 분석하세요.

헤드라인:
{chr(10).join([f'- {h}' for h in headlines[:15]])}

JSON만 반환:
{{"signal": "BULLISH|BEARISH|NEUTRAL", "confidence": 0.0-1.0, "key_themes": ["테마1", "테마2"], "reasoning": "한 문장 요약"}}"""

                msg = claude_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw = msg.content[0].text
                s, e = raw.find("{"), raw.rfind("}") + 1
                if s != -1 and e > s:
                    r = json.loads(raw[s:e])
                    report = f"뉴스 감성: {r.get('reasoning', '')} | 주요 테마: {', '.join(r.get('key_themes', []))}"
                    return AnalystReport(self.name, r.get("signal", "NEUTRAL"),
                                        float(r.get("confidence", 0.5)), report)
            except Exception as e:
                logger.debug(f"News Claude: {e}")

        # Fallback: 키워드 스코어링
        pos = sum(1 for k in ["rally","gain","surge","beat","strong","상승","강세","호조"] if k in " ".join(headlines).lower())
        neg = sum(1 for k in ["crash","fall","recession","crisis","하락","약세","우려"] if k in " ".join(headlines).lower())
        score = pos - neg
        signal = "BULLISH" if score > 1 else "BEARISH" if score < -1 else "NEUTRAL"
        report = f"긍정 키워드: {pos}개, 부정 키워드: {neg}개 (총 {len(headlines)}개 헤드라인 분석)"
        return AnalystReport(self.name, signal, min(0.7, 0.5 + abs(score)*0.05), report)


class TechnicalAnalyst:
    """기술적 분석: RSI, MACD, 이동평균, 볼린저밴드"""
    name = "Technical Analyst"

    def analyze(self, market: str, symbols: list, claude_client=None) -> AnalystReport:
        try:
            import FinanceDataReader as fdr
            import pandas as pd

            idx_map = {"KOSPI": "KS11", "KOSDAQ": "KQ11", "US": "^GSPC"}
            symbol = idx_map.get(market, "^GSPC")
            df = fdr.DataReader(symbol, datetime.now() - timedelta(days=300))
            if len(df) < 60:
                return AnalystReport(self.name, "NEUTRAL", 0.4, "데이터 부족")

            close = df["Close"]
            ma20 = close.rolling(20).mean().iloc[-1]
            ma60 = close.rolling(60).mean().iloc[-1]
            ma200 = close.rolling(min(200, len(close))).mean().iloc[-1]
            price = close.iloc[-1]

            delta = close.diff()
            gain = delta.where(delta>0,0).rolling(14).mean()
            loss = (-delta.where(delta<0,0)).rolling(14).mean()
            rsi = float((100 - 100/(1+gain/loss)).iloc[-1])

            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12 - ema26
            signal_line = macd.ewm(span=9).mean()
            macd_hist = float((macd - signal_line).iloc[-1])

            bb_mid = close.rolling(20).mean().iloc[-1]
            bb_std = close.rolling(20).std().iloc[-1]
            bb_upper = bb_mid + 2*bb_std
            bb_lower = bb_mid - 2*bb_std
            bb_pct = float((price - bb_lower) / (bb_upper - bb_lower))

            score = 0
            if price > ma20: score += 1
            if price > ma60: score += 1
            if price > ma200: score += 1
            if ma20 > ma60: score += 1
            if 40 < rsi < 65: score += 1
            if rsi < 30: score += 2
            if rsi > 75: score -= 2
            if macd_hist > 0: score += 1
            if bb_pct < 0.2: score += 1
            if bb_pct > 0.9: score -= 1

            report = (
                f"가격 vs MA20={((price/ma20-1)*100):.1f}%, MA60={((price/ma60-1)*100):.1f}%, MA200={((price/ma200-1)*100):.1f}%\n"
                f"RSI={rsi:.0f}, MACD히스토그램={'▲' if macd_hist>0 else '▼'}{abs(macd_hist):.2f}, "
                f"볼린저%={bb_pct*100:.0f}%, 기술점수={score}/9"
            )
            signal = "BULLISH" if score >= 5 else "BEARISH" if score <= 2 else "NEUTRAL"
            confidence = min(0.90, 0.5 + abs(score-3)*0.06)
            return AnalystReport(self.name, signal, confidence, report,
                                 {"rsi": rsi, "macd_hist": macd_hist, "bb_pct": bb_pct, "score": score})
        except Exception as e:
            return AnalystReport(self.name, "NEUTRAL", 0.3, f"기술 분석 오류: {e}")


# ─────────────────────────────────────────────────────────────
# 투자 거장 페르소나 에이전트 (ai-hedge-fund 방식)
# ─────────────────────────────────────────────────────────────

class LegendaryInvestorAgent:
    """유명 투자가 페르소나로 시장 분석"""

    PERSONAS = {
        "Warren Buffett": (
            "워런 버핏: 모트(해자)가 있는 우량주, 합리적 가격, 장기 보유. "
            "ROE > 15%, 순이익률 > 20%, 부채비율 낮음, 경쟁우위 지속성 중시."
        ),
        "George Soros": (
            "조지 소로스: 반사성 이론(Reflexivity), 거시적 불균형 포착, 레버리지 활용. "
            "시장의 자기강화 메커니즘 분석, 되먹임 루프 식별, 추세 전환점 포착."
        ),
        "Peter Lynch": (
            "피터 린치: 자신이 아는 것에 투자, PEG < 1인 성장주 선호. "
            "일상에서 아이디어 발굴, 중소형 성장주, 10배 주식(Ten-bagger) 탐색."
        ),
        "Stanley Druckenmiller": (
            "스탠리 드러켄밀러: 매크로 드리븐, 유동성 분석, 비대칭 기회 포착. "
            "Fed 정책 방향, 달러 강세/약세, 자산군 간 자금 이동 파악."
        ),
    }

    def __init__(self, persona_name: str, claude_client=None):
        self.persona_name = persona_name
        self.persona_description = self.PERSONAS.get(persona_name, "")
        self.claude = claude_client
        self.name = f"{persona_name} Agent"

    def analyze(self, market: str, context: str, claude_client=None) -> AnalystReport:
        client = claude_client or self.claude
        if not client:
            return AnalystReport(self.name, "NEUTRAL", 0.3, "Claude API 없음 - 페르소나 분석 불가")

        try:
            prompt = f"""당신은 {self.persona_name}입니다. 다음 투자 철학을 갖고 있습니다:
{self.persona_description}

현재 {market} 시장 상황:
{context}

당신의 투자 철학에 기반하여 현재 {market} 시장에 대한 견해를 제시하세요.

JSON만 반환:
{{
  "signal": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0-100,
  "reasoning": "3-4문장 분석 (당신의 철학 기반)",
  "key_conviction": "핵심 확신 한 문장"
}}"""

            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text
            s, e = raw.find("{"), raw.rfind("}") + 1
            if s != -1 and e > s:
                r = json.loads(raw[s:e])
                conf = float(r.get("confidence", 50)) / 100
                report = f"[{self.persona_name}] {r.get('reasoning', '')}\n핵심: {r.get('key_conviction', '')}"
                return AnalystReport(self.name, r.get("signal", "NEUTRAL"), conf, report)
        except Exception as ex:
            logger.debug(f"Persona {self.persona_name} error: {ex}")

        return AnalystReport(self.name, "NEUTRAL", 0.3, "페르소나 분석 실패")


# ─────────────────────────────────────────────────────────────
# Debate Layer (TradingAgents 방식)
# ─────────────────────────────────────────────────────────────

class DebateModerator:
    """Bull vs Bear Researcher 토론 조정"""

    def __init__(self, claude_client=None):
        self.claude = claude_client

    def run_debate(self, analyst_reports: list, market: str, rounds: int = 2) -> tuple:
        """
        Returns (bull_case, bear_case) as text summaries.
        """
        if not self.claude:
            # Fallback: split by signal
            bull_reports = [r for r in analyst_reports if r.signal == "BULLISH"]
            bear_reports = [r for r in analyst_reports if r.signal == "BEARISH"]
            bull_case = " | ".join([f"{r.analyst_name}: {r.report[:100]}" for r in bull_reports]) or "강세 의견 없음"
            bear_case = " | ".join([f"{r.analyst_name}: {r.report[:100]}" for r in bear_reports]) or "약세 의견 없음"
            return bull_case, bear_case

        context = "\n".join([
            f"[{r.analyst_name}] {r.signal} ({r.confidence:.0%}): {r.report[:200]}"
            for r in analyst_reports
        ])

        try:
            # Bull case
            bull_prompt = f"""당신은 강세(Bull) 리서처입니다. 다음 분석 보고서를 바탕으로 {market} 시장 매수 논거를 제시하세요.

분석 보고서:
{context}

강세 투자자 관점에서 가장 설득력 있는 매수 근거 3가지를 제시하고, 약세 리스크를 반박하세요. (200자 이내)"""

            bear_prompt = f"""당신은 약세(Bear) 리서처입니다. 다음 분석 보고서를 바탕으로 {market} 시장 매도/관망 논거를 제시하세요.

분석 보고서:
{context}

약세 투자자 관점에서 가장 설득력 있는 매도/관망 근거 3가지를 제시하고, 강세 논거를 반박하세요. (200자 이내)"""

            bull_msg = self.claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": bull_prompt}]
            )
            bear_msg = self.claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": bear_prompt}]
            )
            return bull_msg.content[0].text, bear_msg.content[0].text
        except Exception as e:
            logger.debug(f"Debate error: {e}")
            return "강세 분석 생성 실패", "약세 분석 생성 실패"


class RiskPanel:
    """3인 리스크 패널: Conservative / Neutral / Aggressive"""

    def __init__(self, claude_client=None):
        self.claude = claude_client

    def deliberate(self, bull_case: str, bear_case: str, market: str) -> str:
        if not self.claude:
            return "리스크 패널: API 없음 - 기본 중립 권고"

        try:
            prompt = f"""{market} 시장 투자 결정을 위한 3인 리스크 패널 토론:

강세 논거:
{bull_case}

약세 논거:
{bear_case}

각 패널이 한 문장씩 의견을 제시하고 합의점을 도출하세요:
- 보수적 관점 (Conservative): 리스크 최소화, 자본 보존 우선
- 중립적 관점 (Neutral): 균형잡힌 리스크/리워드 평가
- 공격적 관점 (Aggressive): 수익 극대화, 기회 포착

최종: 포지션 크기 권고 (0%=현금, 25%=소량, 50%=보통, 75%=적극, 100%=풀포지션)와 손절/목표가 제안."""

            msg = self.claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return msg.content[0].text
        except Exception as e:
            return f"리스크 패널 오류: {e}"


class PortfolioManager:
    """최종 판결: 모든 분석 종합 → 매매 결정"""

    def __init__(self, claude_client=None):
        self.claude = claude_client

    def decide(self, analyst_reports: list, bull_case: str, bear_case: str,
               risk_verdict: str, market: str) -> FinalDecision:

        # Weighted vote (fallback)
        weights = {
            "Macro Analyst": 0.20, "Micro Analyst": 0.15,
            "News Analyst": 0.10, "Technical Analyst": 0.25,
            "Warren Buffett Agent": 0.10, "George Soros Agent": 0.08,
            "Peter Lynch Agent": 0.07, "Stanley Druckenmiller Agent": 0.05,
        }
        score = 0.0
        total_w = 0.0
        for r in analyst_reports:
            w = weights.get(r.analyst_name, 0.05)
            v = {"BULLISH": 1.0, "NEUTRAL": 0.0, "BEARISH": -1.0}.get(r.signal, 0.0)
            score += v * w * r.confidence
            total_w += w
        final_score = score / total_w if total_w else 0

        # Map to decision
        if final_score >= 0.35:
            signal = "BUY"
            position_size = min(1.0, 0.5 + final_score)
            sl, tp = -0.05, 0.12
        elif final_score >= 0.15:
            signal = "OVERWEIGHT"
            position_size = 0.6
            sl, tp = -0.06, 0.10
        elif final_score <= -0.35:
            signal = "SELL"
            position_size = 0.0
            sl, tp = 0.0, 0.0
        elif final_score <= -0.15:
            signal = "UNDERWEIGHT"
            position_size = 0.2
            sl, tp = -0.08, 0.08
        else:
            signal = "HOLD"
            position_size = 0.5
            sl, tp = -0.07, 0.09

        pm_reasoning = f"가중합산점수={final_score:.3f} | 신호={signal} | 포지션={position_size:.0%}"

        if self.claude:
            try:
                summary = "\n".join([
                    f"- {r.analyst_name}: {r.signal} ({r.confidence:.0%}) — {r.report[:100]}"
                    for r in analyst_reports
                ])
                prompt = f"""당신은 퀀트 헤지펀드의 최고투자책임자(CIO)입니다.

{market} 시장 분석 결과:
{summary}

강세 논거: {bull_case[:300]}
약세 논거: {bear_case[:300]}
리스크 패널: {risk_verdict[:300]}
정량 점수: {final_score:.3f} → 예비 결정: {signal}

최종 투자 결정을 2-3문장으로 간결하게 설명하세요. 구체적 수치와 근거를 포함하세요."""

                msg = self.claude.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}]
                )
                pm_reasoning = msg.content[0].text
            except Exception as e:
                logger.debug(f"PM reasoning error: {e}")

        return FinalDecision(
            market=market, symbols=[],
            signal=signal, confidence=abs(final_score),
            position_size=round(position_size, 2),
            stop_loss_pct=sl, take_profit_pct=tp,
            bull_case=bull_case, bear_case=bear_case,
            risk_panel_verdict=risk_verdict,
            portfolio_manager_reasoning=pm_reasoning,
            all_reports=[{
                "analyst": r.analyst_name, "signal": r.signal,
                "confidence": r.confidence, "report": r.report[:500]
            } for r in analyst_reports]
        )


# ─────────────────────────────────────────────────────────────
# Main Agentic Trading System
# ─────────────────────────────────────────────────────────────

class AgenticTradingSystem:
    MARKETS = ["KOSPI", "KOSDAQ", "US"]

    def __init__(self):
        self.claude = None
        if ANTHROPIC_API_KEY:
            import anthropic
            self.claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            logger.info("Claude API 연결됨")

        # Analyst Layer
        self.macro = MacroAnalyst()
        self.micro = MicroAnalyst()
        self.news = NewsAnalyst()
        self.technical = TechnicalAnalyst()

        # Legendary Investor Agents
        self.personas = [
            LegendaryInvestorAgent("Warren Buffett", self.claude),
            LegendaryInvestorAgent("George Soros", self.claude),
            LegendaryInvestorAgent("Peter Lynch", self.claude),
            LegendaryInvestorAgent("Stanley Druckenmiller", self.claude),
        ]

        # Debate + Risk + PM
        self.debate = DebateModerator(self.claude)
        self.risk_panel = RiskPanel(self.claude)
        self.portfolio_manager = PortfolioManager(self.claude)

    def run_analysis(self, markets: Optional[list] = None):
        if not markets:
            markets = self.MARKETS

        logger.info(f"=== Agentic Trading v2 시작 | 시장: {markets} ===")
        results = []

        for market in markets:
            logger.info(f"[{market}] 분석 시작...")
            try:
                result = self._analyze_market(market)
                self._save(result)
                results.append(result)
                logger.info(
                    f"[{market}] 결정: {result.signal} | "
                    f"확신도={result.confidence:.0%} | "
                    f"포지션={result.position_size:.0%}"
                )
            except Exception as e:
                logger.error(f"[{market}] 분석 실패: {e}")

        logger.info(f"=== 분석 완료 | {len(results)}/{len(markets)} 시장 ===")
        return results

    def _analyze_market(self, market: str) -> FinalDecision:
        reports = []

        # 1. Analyst Layer (병렬 실행 단순화)
        for func in [
            lambda: self.macro.analyze(market, self.claude),
            lambda: self.micro.analyze(market, [], self.claude),
            lambda: self.news.analyze(market, self.claude),
            lambda: self.technical.analyze(market, [], self.claude),
        ]:
            try:
                reports.append(func())
            except Exception as e:
                logger.warning(f"Analyst 오류: {e}")

        # 2. Persona Agents (Claude 있을 때만)
        if self.claude:
            context_summary = "\n".join([
                f"{r.analyst_name}: {r.signal} — {r.report[:150]}"
                for r in reports
            ])
            for persona in self.personas:
                try:
                    reports.append(persona.analyze(market, context_summary, self.claude))
                except Exception as e:
                    logger.debug(f"Persona 오류: {e}")

        if not reports:
            logger.warning(f"[{market}] 분석 보고서 없음")
            return FinalDecision(market=market, symbols=[], signal="HOLD",
                                 confidence=0, position_size=0.5, stop_loss_pct=-0.07,
                                 take_profit_pct=0.09, bull_case="", bear_case="",
                                 risk_panel_verdict="", portfolio_manager_reasoning="데이터 없음")

        # 3. Bull/Bear Debate
        bull_case, bear_case = self.debate.run_debate(reports, market)

        # 4. Risk Panel
        risk_verdict = self.risk_panel.deliberate(bull_case, bear_case, market)

        # 5. Portfolio Manager 최종 결정
        decision = self.portfolio_manager.decide(reports, bull_case, bear_case, risk_verdict, market)
        return decision

    def _save(self, decision: FinalDecision):
        with engine.connect() as conn:
            try:
                conn.execute(text("""
                    INSERT INTO agentic_signals
                        (market, final_signal, confidence, position_size,
                         stop_loss_pct, take_profit_pct, agent_signals, synthesis, created_at)
                    VALUES
                        (:market, :signal, :confidence, :position,
                         :sl, :tp, :agents::jsonb, :synthesis, NOW())
                """), {
                    "market": decision.market,
                    "signal": decision.signal,
                    "confidence": decision.confidence,
                    "position": decision.position_size,
                    "sl": decision.stop_loss_pct,
                    "tp": decision.take_profit_pct,
                    "agents": json.dumps(decision.all_reports),
                    "synthesis": decision.portfolio_manager_reasoning[:2000]
                })
                conn.commit()
            except Exception as e:
                logger.debug(f"저장 오류: {e}")

    def _init_db(self):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agentic_signals (
                    id SERIAL PRIMARY KEY,
                    market VARCHAR(20),
                    final_signal VARCHAR(20),
                    confidence FLOAT,
                    position_size FLOAT,
                    stop_loss_pct FLOAT,
                    take_profit_pct FLOAT,
                    agent_signals JSONB,
                    synthesis TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_agentic_mkt ON agentic_signals(market, created_at DESC);
            """))
            conn.commit()


def main():
    system = AgenticTradingSystem()
    try:
        system._init_db()
    except Exception as e:
        logger.warning(f"DB 초기화: {e}")

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # KOSPI/KOSDAQ 개장 전 8:30 AM
    scheduler.add_job(
        lambda: system.run_analysis(["KOSPI", "KOSDAQ"]),
        "cron", day_of_week="mon-fri", hour=8, minute=30,
        id="kr_morning", max_instances=1
    )
    # US 개장 전 10:00 PM KST
    scheduler.add_job(
        lambda: system.run_analysis(["US"]),
        "cron", day_of_week="mon-fri", hour=22, minute=0,
        id="us_open", max_instances=1
    )
    # 전체 일일 분석 6:00 AM KST
    scheduler.add_job(
        lambda: system.run_analysis(),
        "cron", day_of_week="tue-sat", hour=6, minute=0,
        id="daily_full", max_instances=1
    )
    # 시작 시 30초 후 즉시 실행
    scheduler.add_job(
        lambda: system.run_analysis(),
        "date", run_date=datetime.now() + timedelta(seconds=30),
        id="startup"
    )

    logger.info(
        "Agentic Trading v2 시작\n"
        "  분석팀: 거시|미시|뉴스|기술 + 버핏|소로스|린치|드러켄밀러\n"
        "  토론: Bull ↔ Bear 리서처\n"
        "  리스크패널: 보수|중립|공격적\n"
        "  포트폴리오매니저: 최종 판결\n"
        "  스케줄: 8:30 AM(KR), 10:00 PM(US open), 6:00 AM(전체)"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
