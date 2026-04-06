"""
AI Hedge Fund Team — Main Service
====================================
8인 전설적 투자자 페르소나 + 리스크 매니저 + 포트폴리오 매니저.

아키텍처:
┌──────────────────────────────────────────────────────────────┐
│          PERSONA LAYER (8 legends)                            │
│  [Graham] [Buffett] [Munger] [Soros]                         │
│  [Lynch] [Burry] [C.Wood] [Taleb]                            │
└───────────────────────┬──────────────────────────────────────┘
                        │ deterministic scoring
┌───────────────────────▼──────────────────────────────────────┐
│         RISK MANAGER                                          │
│  Vol-adjusted position limits + correlation penalty           │
└───────────────────────┬──────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────────┐
│         PORTFOLIO MANAGER (Claude-enhanced)                   │
│  Weighted consensus → BUY / SELL / HOLD                       │
└──────────────────────────────────────────────────────────────┘
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

from agents.personas import PERSONA_AGENTS
from agents.risk_manager import RiskManager
from agents.portfolio_manager import PortfolioManager

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
    format="%(asctime)s [ai-hedge-fund] %(levelname)s %(message)s"
)
logger = logging.getLogger("ai-hedge-fund-team")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quantpass@postgres:5432/quantdb")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
engine = create_engine(DATABASE_URL)


class AIHedgeFundSystem:
    """
    AI Hedge Fund 팀 — 8인 전설 투자자 컨센서스.
    각 시장에 대해 독립적으로 분석.
    """
    MARKETS = ["KOSPI", "KOSDAQ", "US"]
    TEAM_ID = "ai_hedge_fund"

    def __init__(self):
        self.claude = None
        if ANTHROPIC_API_KEY:
            import anthropic
            self.claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            logger.info("Claude API 연결됨")

        self.risk_manager = RiskManager()
        self.portfolio_manager = PortfolioManager(self.claude)

        # Memory
        self.memory = {}
        self.journal = {}
        if MEMORY_AVAILABLE:
            try:
                conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
                for market in self.MARKETS:
                    agent_id = f"ai_hedge_fund_{market.lower()}"
                    self.memory[market] = MemoryManager(conn, agent_id)
                    self.journal[market] = TradeJournal(conn, agent_id)
                logger.info("기억 시스템 초기화 완료")
            except Exception as e:
                logger.warning(f"기억 시스템 초기화 실패: {e}")

    def run_analysis(self, markets=None):
        if not markets:
            markets = self.MARKETS

        logger.info(f"=== AI Hedge Fund Team 분석 시작 | {markets} ===")
        results = []

        for market in markets:
            try:
                result = self._analyze_market(market)
                self._save_signal(result)
                self._save_to_journal(result)
                results.append(result)
                logger.info(
                    f"[{market}] {result.signal} "
                    f"(확신={result.confidence:.0%}, 컨센서스={result.consensus_score:.3f})"
                )
            except Exception as e:
                logger.error(f"[{market}] 분석 실패: {e}", exc_info=True)

        logger.info(f"=== 분석 완료 | {len(results)}/{len(markets)} ===")
        return results

    def _analyze_market(self, market: str):
        """단일 시장 전체 분석 파이프라인."""
        price_data = self._fetch_price_data(market)

        # 1. 8인 페르소나 분석 (결정론적 스코어링)
        persona_signals = []
        for agent_key, agent in PERSONA_AGENTS.items():
            try:
                signal = agent.analyze(market, price_data)
                persona_signals.append(signal)
                logger.debug(
                    f"[{market}] {signal.persona_name}: {signal.signal} "
                    f"({signal.confidence:.0%}) score={signal.score:.0f}/{signal.max_score:.0f}"
                )
            except Exception as e:
                logger.warning(f"[{market}] {agent_key} 분석 오류: {e}")

        # 2. 리스크 평가
        risk = self.risk_manager.assess(market, price_data)

        # 3. 메모리 컨텍스트
        memory_context = ""
        mem = self.memory.get(market)
        if mem:
            try:
                memory_context = mem.build_context_prompt(limit=5)
            except Exception:
                pass

        perf_ctx = ""
        journal = self.journal.get(market)
        if journal:
            try:
                perf_ctx = journal.build_performance_summary(market)
            except Exception:
                pass

        full_memory = (memory_context + "\n" + perf_ctx).strip()

        # 4. 포트폴리오 매니저 최종 결정
        decision = self.portfolio_manager.decide(
            market, persona_signals, risk, full_memory
        )

        return decision

    def _fetch_price_data(self, market: str) -> dict:
        """DB에서 시장 인덱스 가격 데이터 조회."""
        try:
            import pandas as pd
            idx_map = {"KOSPI": "KS11", "KOSDAQ": "KQ11", "US": "^GSPC"}
            symbol = idx_map.get(market, "^GSPC")

            with engine.connect() as conn:
                df = pd.read_sql(
                    text("""
                        SELECT date, close
                        FROM market_data
                        WHERE symbol = :symbol
                        ORDER BY date DESC
                        LIMIT 300
                    """),
                    conn, params={"symbol": symbol}
                )

            if df.empty:
                return self._fetch_from_api(market)

            df = df.sort_values("date").set_index("date")
            df.index = pd.to_datetime(df.index)
            return {"close_series": df["close"]}

        except Exception as e:
            logger.warning(f"DB 데이터 조회 실패: {e}, API 사용")
            return self._fetch_from_api(market)

    def _fetch_from_api(self, market: str) -> dict:
        """FinanceDataReader/yfinance fallback."""
        try:
            import FinanceDataReader as fdr
            import pandas as pd
            idx_map = {"KOSPI": "KS11", "KOSDAQ": "KQ11", "US": "^GSPC"}
            symbol = idx_map.get(market, "^GSPC")
            df = fdr.DataReader(symbol, datetime.now() - timedelta(days=400))
            if not df.empty:
                return {"close_series": df["Close"]}
        except Exception:
            pass

        try:
            import yfinance as yf
            import pandas as pd
            yf_map = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "US": "^GSPC"}
            ticker = yf.Ticker(yf_map.get(market, "^GSPC"))
            hist = ticker.history(period="2y")
            if not hist.empty:
                return {"close_series": hist["Close"]}
        except Exception:
            pass

        return {}

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
                    "agents": json.dumps(decision.persona_breakdown),
                    "synthesis": f"[AI-HF] consensus={decision.consensus_score:.3f} {decision.reasoning[:1200]}"
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
            try:
                journal.log_signal(
                    market=decision.market,
                    signal_type=decision.signal,
                    confidence=decision.confidence,
                    entry_price=0.0,
                    agent_breakdown=decision.persona_breakdown,
                )
            except Exception:
                pass

        mem = self.memory.get(decision.market)
        if mem:
            try:
                mem.remember_insight(
                    f"[AI-HF] {decision.market} → {decision.signal} "
                    f"(확신={decision.confidence:.0%}, consensus={decision.consensus_score:.3f}): "
                    f"{decision.reasoning[:150]}",
                    importance=0.75,
                )
            except Exception:
                pass


def main():
    system = AIHedgeFundSystem()

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # KR 시장 분석 — 08:15 (TradingAgents 팀과 15분 오프셋)
    scheduler.add_job(
        lambda: system.run_analysis(["KOSPI", "KOSDAQ"]),
        "cron", day_of_week="mon-fri", hour=8, minute=15,
        id="kr_analysis", max_instances=1
    )
    # US 시장 분석 — 21:45
    scheduler.add_job(
        lambda: system.run_analysis(["US"]),
        "cron", day_of_week="mon-fri", hour=21, minute=45,
        id="us_analysis", max_instances=1
    )
    # 시작 후 60초 뒤 즉시 실행
    scheduler.add_job(
        lambda: system.run_analysis(),
        "date", run_date=datetime.now() + timedelta(seconds=60),
        id="startup"
    )

    logger.info(
        "AI Hedge Fund Team 시작\n"
        "  페르소나: Graham|Buffett|Munger|Soros|Lynch|Burry|C.Wood|Taleb\n"
        "  리스크: Vol-adjusted + Correlation penalty\n"
        "  트레이더: 가중 컨센서스 → Claude 강화\n"
        "  스케줄: 08:15(KR), 21:45(US)"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
