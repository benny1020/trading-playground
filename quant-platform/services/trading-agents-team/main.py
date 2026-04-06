"""
TradingAgents Team — Main Service
===================================
Multi-Agent Debate-Driven Trading (TradingAgents 레포 기반)

아키텍처:
┌──────────────────────────────────────────────────┐
│        ANALYST LAYER (4 agents)                   │
│  [Fundamentals] [Market/Tech] [News] [Sentiment] │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│        DEBATE LAYER (Multi-round)                 │
│      Bull ←→ Bear ←→ Judge (2-3 rounds)          │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│        RISK PANEL (3-way debate)                  │
│    Conservative ←→ Neutral ←→ Aggressive          │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│            TRADER (Final Decision)                │
│              BUY / SELL / HOLD                    │
└──────────────────────────────────────────────────┘
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

# Agents
from agents.analysts import (
    FundamentalsAnalyst, MarketAnalyst, NewsAnalyst, SentimentAnalyst
)
from agents.debate import DebateEngine
from agents.risk_panel import RiskPanel
from agents.trader import TraderAgent

# Shared memory
sys.path.insert(0, "/app/shared")
try:
    from memory_manager import MemoryManager, TradeJournal
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [trading-agents] %(levelname)s %(message)s"
)
logger = logging.getLogger("trading-agents-team")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quantpass@postgres:5432/quantdb")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
engine = create_engine(DATABASE_URL)


class TradingAgentsSystem:
    """
    TradingAgents 팀 — debate-driven consensus.
    각 시장(KOSPI/KOSDAQ/US)에 대해 독립 분석.
    """
    MARKETS = ["KOSPI", "KOSDAQ", "US"]
    TEAM_ID = "trading_agents"

    def __init__(self):
        self.claude = None
        if ANTHROPIC_API_KEY:
            import anthropic
            self.claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            logger.info("Claude API 연결됨")

        # Agents
        self.fundamentals = FundamentalsAnalyst()
        self.market_analyst = MarketAnalyst()
        self.news = NewsAnalyst()
        self.sentiment = SentimentAnalyst()

        self.debate = DebateEngine(self.claude, max_rounds=2)
        self.risk_panel = RiskPanel(self.claude)
        self.trader = TraderAgent(self.claude)

        # Memory
        self.memory = {}
        self.journal = {}
        if MEMORY_AVAILABLE:
            try:
                conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
                for market in self.MARKETS:
                    agent_id = f"trading_agents_{market.lower()}"
                    self.memory[market] = MemoryManager(conn, agent_id)
                    self.journal[market] = TradeJournal(conn, agent_id)
                logger.info("기억 시스템 초기화 완료")
            except Exception as e:
                logger.warning(f"기억 시스템 초기화 실패: {e}")

    def run_analysis(self, markets=None):
        if not markets:
            markets = self.MARKETS

        logger.info(f"=== TradingAgents Team 분석 시작 | {markets} ===")
        results = []

        for market in markets:
            try:
                result = self._analyze_market(market)
                self._save_signal(result)
                self._save_to_journal(result)
                results.append(result)
                logger.info(f"[{market}] {result.signal} (확신={result.confidence:.0%})")
            except Exception as e:
                logger.error(f"[{market}] 분석 실패: {e}")

        logger.info(f"=== 분석 완료 | {len(results)}/{len(markets)} ===")
        return results

    def _analyze_market(self, market: str):
        # 1. Analyst Layer
        reports = []
        for analyst in [self.fundamentals, self.market_analyst, self.news, self.sentiment]:
            try:
                if hasattr(analyst, 'analyze'):
                    import inspect
                    sig = inspect.signature(analyst.analyze)
                    params = list(sig.parameters.keys())
                    if 'symbols' in params:
                        reports.append(analyst.analyze(market, [], self.claude))
                    elif 'claude_client' in params:
                        reports.append(analyst.analyze(market, self.claude))
                    else:
                        reports.append(analyst.analyze(market))
            except Exception as e:
                logger.warning(f"Analyst error: {e}")

        if not reports:
            from agents.trader import TradeDecision
            return TradeDecision(
                market=market, signal="HOLD", confidence=0.0,
                position_size=0.5, stop_loss_pct=-0.07, take_profit_pct=0.09,
                reasoning="분석 데이터 없음", debate_summary="",
                risk_verdict="", analyst_breakdown=[]
            )

        # Build analyst context for debate
        context = "\n".join([
            f"[{r.analyst_name}] {r.signal} ({r.confidence:.0%}): {r.report[:200]}"
            for r in reports
        ])

        # Memory context
        memory_hints = ""
        mem = self.memory.get(market)
        if mem:
            memory_hints = mem.build_context_prompt(limit=5)

        # 2. Bull/Bear Debate (2 rounds)
        bull_case, bear_case, judge_synthesis = self.debate.run_debate(
            context, market, memory_hints
        )

        # 3. Risk Panel (3-way)
        risk_result = self.risk_panel.deliberate(market, bull_case, bear_case, judge_synthesis)

        # 4. Trader Decision
        perf_ctx = ""
        journal = self.journal.get(market)
        if journal:
            perf_ctx = journal.build_performance_summary(market)

        full_memory = (memory_hints + "\n" + perf_ctx).strip()

        decision = self.trader.decide(
            market, reports, bull_case, bear_case,
            judge_synthesis, risk_result, full_memory
        )

        return decision

    def _save_signal(self, decision):
        """DB에 신호 저장."""
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
                    "agents": json.dumps(decision.analyst_breakdown),
                    "synthesis": f"[TradingAgents] {decision.reasoning[:1500]}"
                })
                conn.commit()
            except Exception as e:
                logger.error(f"DB 저장 오류: {e}")

    def _save_to_journal(self, decision):
        """매매 일지 + 기억 저장."""
        if decision.signal == "HOLD":
            return

        journal = self.journal.get(decision.market)
        if journal:
            journal.log_signal(
                market=decision.market,
                signal_type=decision.signal,
                confidence=decision.confidence,
                entry_price=0.0,
                agent_breakdown=decision.analyst_breakdown,
            )

        mem = self.memory.get(decision.market)
        if mem:
            mem.remember_insight(
                f"[TradingAgents] {decision.market} → {decision.signal} "
                f"(확신={decision.confidence:.0%}): {decision.reasoning[:150]}",
                importance=0.7,
            )


def main():
    system = TradingAgentsSystem()

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # KR 시장 분석 — 08:00
    scheduler.add_job(
        lambda: system.run_analysis(["KOSPI", "KOSDAQ"]),
        "cron", day_of_week="mon-fri", hour=8, minute=0,
        id="kr_analysis", max_instances=1
    )
    # US 시장 분석 — 21:30
    scheduler.add_job(
        lambda: system.run_analysis(["US"]),
        "cron", day_of_week="mon-fri", hour=21, minute=30,
        id="us_analysis", max_instances=1
    )
    # 시작 후 30초 뒤 즉시 실행
    scheduler.add_job(
        lambda: system.run_analysis(),
        "date", run_date=datetime.now() + timedelta(seconds=30),
        id="startup"
    )

    logger.info(
        "TradingAgents Team 시작\n"
        "  분석: Fundamentals|Market|News|Sentiment\n"
        "  토론: Bull ↔ Bear (2 rounds)\n"
        "  리스크: Conservative ↔ Neutral ↔ Aggressive\n"
        "  트레이더: 최종 BUY/SELL/HOLD\n"
        "  스케줄: 08:00(KR), 21:30(US)"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
