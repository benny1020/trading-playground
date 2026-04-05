"""
Strategy Lab — QuantLab Capital R&D Team
=========================================
논문, GitHub 최신 트렌드 탐색 → 전략 아이디어 추출 → 백테스트 → 유망 전략 신설팀 등록.

Loop:
  1. arXiv 논문 수집 (paper-research service)
  2. GitHub Trending 퀀트/AI 레포 스캔
  3. Claude AI로 전략 아이디어 추출
  4. 백테스트 엔진에 제출 (point-in-time 준수)
  5. 유망 전략 → strategy_teams 테이블에 신팀 등록 → CEO에게 통보
  6. MLflow에 실험 결과 로깅

이 서비스는 팀을 신설하는 R&D 역할이다.
팀을 만들면 해당 팀의 전략들이 매주 CEO Competition에 참가한다.
"""

import os
import json
import time
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

import sys
import httpx
import mlflow
import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 공유 메모리 모듈 (volume-mounted)
sys.path.insert(0, "/app/shared")
try:
    from memory_manager import MemoryManager
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    logger_tmp = logging.getLogger("strategy-lab")
    logger_tmp.warning("memory_manager not available")

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
logger = logging.getLogger("strategy-lab")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quantpass@postgres:5432/quantdb")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")

engine = create_engine(DATABASE_URL)

import psycopg2
import psycopg2.extras

def get_raw_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

# ============================================================
# Strategy Idea Extraction
# ============================================================

STRATEGY_EXTRACTION_PROMPT = """
You are a quantitative finance researcher at a top quant hedge fund.
Analyze the following academic paper abstract and extract actionable trading strategy ideas.

Paper: {title}
Authors: {authors}
Abstract: {abstract}

Extract 1-3 concrete trading strategies that can be backtested. For each strategy provide:
1. strategy_name: Short descriptive name
2. strategy_type: One of [momentum, mean_reversion, factor, breakout, pairs, ml_based, other]
3. description: Clear description of the strategy logic
4. applicable_markets: List of ["KOSPI", "KOSDAQ", "US"] this strategy works for
5. parameters: JSON object with strategy parameters and their default values
6. symbols: List of 3-5 example ticker symbols to test with (use Korean codes like "005930" for KOSPI, or US tickers)
7. lookback_years: Recommended backtesting period in years
8. expected_edge: Why this strategy might work (market inefficiency it exploits)
9. risk_factors: Main risks to watch out for

Return a JSON array of strategy objects. Only return valid JSON, no other text.

Example for a Korean stock:
{
  "strategy_name": "Korean Earnings Momentum",
  "strategy_type": "momentum",
  "description": "Buy stocks with recent earnings upgrades, sell those with downgrades",
  "applicable_markets": ["KOSPI", "KOSDAQ"],
  "parameters": {"lookback": 63, "top_pct": 0.2, "rebalance_freq": "M"},
  "symbols": ["005930", "000660", "035420", "051910", "006400"],
  "lookback_years": 5,
  "expected_edge": "Earnings momentum persists 1-3 months post-announcement",
  "risk_factors": ["Earnings season clustering", "Market regime changes"]
}
"""

TREND_ANALYSIS_PROMPT = """
You are a head of research at a top quantitative hedge fund.
Analyze these recent academic papers in quantitative finance and identify:

1. What are the 3-5 biggest trending research themes in quant finance right now?
2. Which market inefficiencies are currently most studied?
3. What machine learning techniques are being applied to trading?
4. Are there any emerging strategies for Korean markets (KOSPI/KOSDAQ)?
5. What does the current research say about market regimes and when strategies tend to work?

Papers:
{papers_summary}

Provide a structured analysis in JSON format with keys:
- trending_themes: list of {theme, description, paper_count, relevance}
- market_opportunities: list of {market, inefficiency, suggested_approach}
- ml_techniques: list of {technique, use_case, papers_count}
- korean_market_insights: string
- regime_insights: string
- recommended_strategies: list of top 3 strategies to test next

Return only valid JSON.
"""


class StrategyLab:
    """
    Strategy Lab 연구원.
    매 사이클마다 자신의 과거 연구 기록을 먼저 읽고 시작한다.
    실패한 전략은 반복하지 않는다. 성공 패턴은 강화한다.
    """

    def __init__(self):
        self.client = httpx.Client(base_url=BACKEND_URL, timeout=60.0)
        self.anthropic_available = bool(ANTHROPIC_API_KEY)
        if self.anthropic_available:
            import anthropic
            self.anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # 기억 시스템 초기화
        self._memory_db = None
        self.memory: MemoryManager = None
        if MEMORY_AVAILABLE:
            try:
                self._memory_db = get_raw_db()
                self.memory = MemoryManager(self._memory_db, "strategy_lab")
                logger.info("Memory system initialized")
            except Exception as e:
                logger.warning(f"Memory init failed: {e}")

        try:
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            mlflow.set_experiment("strategy-research")
            logger.info("MLflow connected")
        except Exception as e:
            logger.warning(f"MLflow not available: {e}")

    def get_unprocessed_papers(self, limit: int = 10):
        """Fetch papers that haven't been processed by strategy lab yet."""
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, title, authors, abstract, url, published_date, tags, relevance_score
                FROM papers
                WHERE relevance_score >= 5
                  AND id NOT IN (
                    SELECT DISTINCT (parameters->>'source_paper_id')::uuid
                    FROM strategies
                    WHERE parameters->>'source_paper_id' IS NOT NULL
                  )
                ORDER BY relevance_score DESC, published_date DESC
                LIMIT :limit
            """), {"limit": limit})
            return [dict(row._mapping) for row in result]

    def extract_strategies_from_paper(self, paper: dict) -> list:
        """
        논문에서 전략 추출.
        과거에 뭐가 됐고 뭐가 안됐는지 기억을 컨텍스트로 주입한다.
        실패한 전략 타입은 다시 제안하지 않도록 Claude에게 알려준다.
        """
        if not self.anthropic_available:
            logger.info("No Anthropic API key - using rule-based extraction")
            return self._rule_based_extraction(paper)

        # 과거 기억 로드 — 퀀트 리서처가 노트를 펼쳐보는 것처럼
        memory_context = ""
        bad_types = set()
        if self.memory:
            memory_context = self.memory.build_context_prompt(limit=10)
            bad_types = self.memory.get_bad_strategy_types()
            if bad_types:
                memory_context += f"\n\n❌ 이미 시도했고 성과 없었던 전략 타입 (제안 금지): {', '.join(bad_types)}"

        try:
            prompt = STRATEGY_EXTRACTION_PROMPT.format(
                title=paper["title"],
                authors=paper.get("authors", "Unknown"),
                abstract=paper.get("abstract", "")[:3000]
            )
            # 기억 컨텍스트를 프롬프트 앞에 주입
            if memory_context:
                prompt = memory_context + "\n\n" + prompt

            message = self.anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            # Extract JSON from response
            start = response_text.find('[')
            end = response_text.rfind(']') + 1
            if start != -1 and end > start:
                strategies = json.loads(response_text[start:end])
                logger.info(f"Extracted {len(strategies)} strategies from: {paper['title'][:60]}")
                return strategies
        except Exception as e:
            logger.error(f"Claude extraction failed: {e}")

        return self._rule_based_extraction(paper)

    def _rule_based_extraction(self, paper: dict) -> list:
        """Fallback: rule-based strategy extraction from paper keywords."""
        abstract = (paper.get("abstract") or "").lower()
        title = (paper.get("title") or "").lower()
        text_combined = abstract + " " + title

        strategies = []

        if any(w in text_combined for w in ["momentum", "trend", "continuation"]):
            strategies.append({
                "strategy_name": f"Momentum ({paper['title'][:40]})",
                "strategy_type": "momentum",
                "description": f"Momentum strategy inspired by: {paper['title']}",
                "applicable_markets": ["KOSPI", "US"],
                "parameters": {"lookback": 252, "top_pct": 0.2, "rebalance_freq": "M"},
                "symbols": ["005930", "000660", "AAPL", "MSFT", "GOOGL"],
                "lookback_years": 5,
                "expected_edge": "Price momentum persistence",
                "risk_factors": ["Momentum crashes in bear markets"]
            })

        if any(w in text_combined for w in ["mean reversion", "reversal", "contrarian"]):
            strategies.append({
                "strategy_name": f"Mean Reversion ({paper['title'][:40]})",
                "strategy_type": "mean_reversion",
                "description": f"Mean reversion strategy inspired by: {paper['title']}",
                "applicable_markets": ["KOSPI", "KOSDAQ", "US"],
                "parameters": {"period": 20, "std_dev": 2.0},
                "symbols": ["005930", "000660", "035420"],
                "lookback_years": 3,
                "expected_edge": "Price reversion after overreaction",
                "risk_factors": ["Trend continuation risk"]
            })

        return strategies

    def create_strategy_in_system(self, strategy_idea: dict, paper_id: str) -> Optional[str]:
        """Create strategy in the backend system."""
        try:
            params = strategy_idea.get("parameters", {})
            params["source_paper_id"] = str(paper_id)
            params["expected_edge"] = strategy_idea.get("expected_edge", "")
            params["risk_factors"] = strategy_idea.get("risk_factors", [])

            response = self.client.post("/api/strategies/", json={
                "name": f"[AUTO] {strategy_idea['strategy_name']}_{uuid.uuid4().hex[:6]}",
                "description": strategy_idea.get("description", ""),
                "strategy_type": strategy_idea.get("strategy_type", "momentum"),
                "parameters": params,
                "market": strategy_idea.get("applicable_markets", ["US"])[0]
            })

            if response.status_code == 200:
                return response.json()["id"]
            else:
                logger.warning(f"Strategy creation failed: {response.text}")
        except Exception as e:
            logger.error(f"Failed to create strategy: {e}")
        return None

    def run_backtest_for_strategy(self, strategy_id: str, strategy_idea: dict) -> Optional[str]:
        """Submit backtest job for a strategy."""
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=365 * strategy_idea.get("lookback_years", 5))).strftime("%Y-%m-%d")

            symbols = strategy_idea.get("symbols", ["005930", "AAPL", "MSFT"])[:5]
            market = strategy_idea.get("applicable_markets", ["US"])[0]

            response = self.client.post("/api/backtests/", json={
                "strategy_id": strategy_id,
                "name": f"Auto-{strategy_idea['strategy_name'][:30]}-{datetime.now().strftime('%Y%m%d')}",
                "start_date": start_date,
                "end_date": end_date,
                "initial_capital": 100_000_000,
                "commission_rate": 0.0015,
                "symbols": symbols,
                "market": market
            })

            if response.status_code == 200:
                backtest_id = response.json()["id"]
                logger.info(f"Backtest submitted: {backtest_id}")
                return backtest_id
        except Exception as e:
            logger.error(f"Failed to submit backtest: {e}")
        return None

    def evaluate_backtest_results(self, backtest_id: str, strategy_name: str) -> dict:
        """Wait for backtest and evaluate results."""
        max_wait = 300  # 5 minutes
        poll_interval = 10
        elapsed = 0

        while elapsed < max_wait:
            try:
                response = self.client.get(f"/api/backtests/{backtest_id}")
                if response.status_code == 200:
                    bt = response.json()
                    if bt["status"] == "completed":
                        results = bt.get("results", {})
                        logger.info(
                            f"Backtest done | {strategy_name[:40]} | "
                            f"Sharpe={results.get('sharpe_ratio', 0):.2f} | "
                            f"CAGR={results.get('cagr', 0)*100:.1f}% | "
                            f"MaxDD={results.get('max_drawdown', 0)*100:.1f}%"
                        )
                        return results
                    elif bt["status"] == "failed":
                        logger.warning(f"Backtest failed: {bt.get('error_message')}")
                        return {}
            except Exception as e:
                logger.error(f"Poll error: {e}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(f"Backtest timed out: {backtest_id}")
        return {}

    def log_to_mlflow(self, strategy_name: str, strategy_idea: dict, results: dict):
        """Log strategy research results to MLflow."""
        try:
            with mlflow.start_run(run_name=strategy_name[:50]):
                mlflow.set_tags({
                    "strategy_type": strategy_idea.get("strategy_type"),
                    "market": str(strategy_idea.get("applicable_markets")),
                    "source": "auto_research"
                })

                metrics_to_log = {
                    "sharpe_ratio": results.get("sharpe_ratio", 0),
                    "cagr": results.get("cagr", 0),
                    "max_drawdown": results.get("max_drawdown", 0),
                    "sortino_ratio": results.get("sortino_ratio", 0),
                    "calmar_ratio": results.get("calmar_ratio", 0),
                    "win_rate": results.get("win_rate", 0),
                    "total_trades": results.get("total_trades", 0),
                }
                mlflow.log_metrics(metrics_to_log)
                mlflow.log_param("parameters", json.dumps(strategy_idea.get("parameters", {})))
                mlflow.log_text(
                    strategy_idea.get("description", ""),
                    "strategy_description.txt"
                )
        except Exception as e:
            logger.debug(f"MLflow logging skipped: {e}")

    def is_good_strategy(self, results: dict) -> bool:
        """Determine if a strategy is worth promoting."""
        if not results:
            return False
        return (
            results.get("sharpe_ratio", 0) >= 0.8 and
            results.get("cagr", 0) >= 0.05 and
            abs(results.get("max_drawdown", 1)) <= 0.30
        )

    def _save_result_to_memory(self, idea: dict, results: dict, paper_title: str):
        """백테스트 결과를 기억에 저장. 다음 사이클에 활용된다."""
        if not self.memory or not results:
            return

        sharpe = results.get("sharpe_ratio", 0)
        cagr = results.get("cagr", 0)
        mdd = results.get("max_drawdown", 0)
        market = idea.get("applicable_markets", ["US"])[0]

        self.memory.remember_strategy_result(
            strategy_name=idea["strategy_name"],
            strategy_type=idea.get("strategy_type", "unknown"),
            market=market,
            sharpe=sharpe,
            cagr=cagr,
            mdd=mdd,
            source=paper_title[:80],
        )

        # 추가 인사이트: 좋은 전략이면 패턴 기록
        if self.is_good_strategy(results):
            self.memory.remember_insight(
                f"{idea.get('strategy_type')} 전략이 {market}에서 효과적: "
                f"Sharpe={sharpe:.2f}, 출처={paper_title[:60]}",
                importance=0.9,
            )
        elif sharpe < 0.3:
            self.memory.remember_warning(
                f"{market}에서 '{idea.get('strategy_type')}' 전략 Sharpe={sharpe:.2f} — "
                f"비슷한 접근은 재시도 불필요"
            )

    def run_research_cycle(self):
        """Main research loop: papers → strategies → backtests → evaluate."""
        logger.info("=== Starting Strategy Research Cycle ===")

        papers = self.get_unprocessed_papers(limit=5)
        if not papers:
            logger.info("No new papers to process")
            return

        good_strategies = []

        for paper in papers:
            logger.info(f"Processing paper: {paper['title'][:70]}")

            strategy_ideas = self.extract_strategies_from_paper(paper)

            for idea in strategy_ideas[:2]:  # Max 2 strategies per paper
                strategy_id = self.create_strategy_in_system(idea, paper["id"])
                if not strategy_id:
                    continue

                backtest_id = self.run_backtest_for_strategy(strategy_id, idea)
                if not backtest_id:
                    continue

                results = self.evaluate_backtest_results(backtest_id, idea["strategy_name"])

                if results:
                    self.log_to_mlflow(idea["strategy_name"], idea, results)
                    # 결과를 기억에 저장 (다음 사이클에 활용)
                    self._save_result_to_memory(idea, results, paper["title"])

                    if self.is_good_strategy(results):
                        good_strategies.append({
                            "name": idea["strategy_name"],
                            "results": results,
                            "paper": paper["title"]
                        })
                        logger.info(f"PROMISING STRATEGY FOUND: {idea['strategy_name']}")

                time.sleep(2)  # Rate limiting

        if good_strategies:
            self._save_promising_strategies(good_strategies)

        logger.info(f"=== Research Cycle Complete | {len(good_strategies)} promising strategies found ===")

    def run_trend_analysis(self):
        """Analyze paper trends and generate research recommendations."""
        logger.info("Running trend analysis...")

        if not self.anthropic_available:
            logger.info("Skipping trend analysis (no API key)")
            return

        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT title, abstract, tags, relevance_score, published_date
                FROM papers
                WHERE published_date >= NOW() - INTERVAL '30 days'
                ORDER BY relevance_score DESC
                LIMIT 30
            """))
            papers = [dict(row._mapping) for row in result]

        if not papers:
            logger.info("No recent papers for trend analysis")
            return

        papers_summary = "\n".join([
            f"- {p['title']} (score: {p.get('relevance_score', 0):.1f}, tags: {p.get('tags', [])})"
            for p in papers
        ])

        try:
            message = self.anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=3000,
                messages=[{
                    "role": "user",
                    "content": TREND_ANALYSIS_PROMPT.format(papers_summary=papers_summary)
                }]
            )

            response_text = message.content[0].text
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end > start:
                trend_data = json.loads(response_text[start:end])
                self._save_trend_report(trend_data)
                logger.info("Trend analysis saved")
        except Exception as e:
            logger.error(f"Trend analysis failed: {e}")

    def _save_promising_strategies(self, strategies: list):
        """Save promising strategies to a special tracking table."""
        with engine.connect() as conn:
            for s in strategies:
                try:
                    conn.execute(text("""
                        INSERT INTO promising_strategies (strategy_name, sharpe_ratio, cagr, max_drawdown, source_paper, found_at)
                        VALUES (:name, :sharpe, :cagr, :dd, :paper, NOW())
                        ON CONFLICT DO NOTHING
                    """), {
                        "name": s["name"],
                        "sharpe": s["results"].get("sharpe_ratio", 0),
                        "cagr": s["results"].get("cagr", 0),
                        "dd": s["results"].get("max_drawdown", 0),
                        "paper": s["paper"][:200]
                    })
                    conn.commit()
                except Exception:
                    pass  # Table might not exist yet

    def _save_trend_report(self, trend_data: dict):
        """Save trend analysis to DB."""
        with engine.connect() as conn:
            try:
                conn.execute(text("""
                    INSERT INTO trend_reports (report_date, trending_topics, top_papers, summary)
                    VALUES (CURRENT_DATE, :topics, :papers, :summary)
                    ON CONFLICT (report_date) DO UPDATE
                    SET trending_topics = :topics, summary = :summary
                """), {
                    "topics": json.dumps(trend_data.get("trending_themes", [])),
                    "papers": json.dumps(trend_data.get("recommended_strategies", [])),
                    "summary": json.dumps(trend_data)
                })
                conn.commit()
            except Exception as e:
                logger.debug(f"Trend report save: {e}")

    # ─── GitHub Trending Scanner ─────────────────────────────────────────────

    QUANT_GITHUB_QUERIES = [
        "algorithmic-trading",
        "quantitative-finance",
        "backtesting",
        "trading-strategy",
        "systematic-trading",
        "factor-investing",
    ]

    def scan_github_trending(self) -> list:
        """
        GitHub Trending에서 퀀트/AI 트레이딩 관련 레포 스캔.
        GitHub API (unauthenticated, 60 req/h) 사용.
        """
        found = []
        headers = {"Accept": "application/vnd.github.v3+json"}
        base = "https://api.github.com/search/repositories"

        for query in self.QUANT_GITHUB_QUERIES[:4]:
            try:
                resp = httpx.get(
                    base,
                    params={
                        "q": f"{query} stars:>100",
                        "sort": "updated",
                        "order": "desc",
                        "per_page": 5,
                    },
                    headers=headers,
                    timeout=15.0,
                )
                if resp.status_code != 200:
                    continue

                for repo in resp.json().get("items", []):
                    found.append({
                        "name": repo["full_name"],
                        "description": repo.get("description") or "",
                        "stars": repo["stargazers_count"],
                        "url": repo["html_url"],
                        "language": repo.get("language") or "",
                        "topics": repo.get("topics", []),
                        "updated_at": repo.get("updated_at", ""),
                    })

                time.sleep(1)  # respect rate limit

            except Exception as e:
                logger.warning(f"GitHub scan error for '{query}': {e}")

        logger.info(f"GitHub scan: found {len(found)} repos")
        return found

    def analyze_github_repos(self, repos: list) -> list:
        """
        Claude로 GitHub 레포 분석 → 새로운 전략팀 아이디어 추출.
        Returns list of team_idea dicts.
        """
        if not repos or not self.anthropic_available:
            return []

        repos_text = "\n".join([
            f"- {r['name']} ({r['stars']}⭐): {r['description'][:100]} [{r['language']}]"
            for r in repos[:15]
        ])

        prompt = f"""당신은 AI 퀀트 자산운용사 QuantLab Capital의 리서치 디렉터입니다.
다음 GitHub 레포들을 분석해 새로운 전략팀으로 만들 가치가 있는 아이디어를 추출하세요.

GitHub 레포 목록:
{repos_text}

다음 형식의 JSON 배열을 반환하세요 (최대 3개, 가치있는 것만):
[
  {{
    "team_id": "unique_snake_case_id",
    "team_name": "팀 이름",
    "description": "이 전략팀이 무엇을 하는지 2-3문장",
    "team_type": "quant|agentic|hybrid",
    "inspired_by_repo": "owner/repo",
    "strategy_approach": "어떤 방식으로 수익을 내는지",
    "applicable_markets": ["KOSPI", "KOSDAQ", "US"]
  }}
]

이미 있는 팀 (중복 제외): quant_strategies, agentic_trading, ai_hedge_fund, strategy_lab

JSON만 반환, 다른 텍스트 없이."""

        try:
            resp = self.anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            text_out = resp.content[0].text
            start = text_out.find("[")
            end = text_out.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(text_out[start:end])
        except Exception as e:
            logger.error(f"GitHub repo analysis failed: {e}")

        return []

    def register_new_team(self, team_idea: dict) -> bool:
        """
        새 전략팀을 strategy_teams 테이블에 등록.
        이 팀은 다음 CEO Competition에 자동으로 참가.
        """
        with engine.connect() as conn:
            try:
                conn.execute(text("""
                    INSERT INTO strategy_teams (team_id, team_name, description, team_type)
                    VALUES (:team_id, :team_name, :description, :team_type)
                    ON CONFLICT (team_id) DO NOTHING
                """), {
                    "team_id": team_idea["team_id"],
                    "team_name": team_idea["team_name"],
                    "description": team_idea.get("description", ""),
                    "team_type": team_idea.get("team_type", "quant"),
                })
                conn.commit()
                logger.info(
                    f"🆕 NEW TEAM REGISTERED: {team_idea['team_name']} "
                    f"(inspired by: {team_idea.get('inspired_by_repo', 'GitHub')})"
                )
                return True
            except Exception as e:
                logger.error(f"Failed to register team: {e}")
                return False

    def run_github_discovery(self):
        """GitHub 스캔 → 새 팀 아이디어 발굴 → 등록."""
        logger.info("=== GitHub Trending Discovery ===")
        repos = self.scan_github_trending()
        if not repos:
            logger.info("No repos found")
            return

        team_ideas = self.analyze_github_repos(repos)
        if not team_ideas:
            logger.info("No new team ideas from GitHub")
            return

        for idea in team_ideas:
            registered = self.register_new_team(idea)
            if registered:
                logger.info(
                    f"Strategy Lab → CEO: New team '{idea['team_name']}' "
                    f"will compete in next round!"
                )

        logger.info(f"=== GitHub Discovery: {len(team_ideas)} new teams registered ===")


def main():
    lab = StrategyLab()

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # Research cycle: Tuesday and Thursday at 10am
    scheduler.add_job(
        lab.run_research_cycle,
        CronTrigger(day_of_week="tue,thu", hour=10, minute=0),
        id="research_cycle",
        name="Strategy Research Cycle (arXiv → backtest)",
        max_instances=1,
    )

    # Trend analysis: Every Friday 4pm (before CEO competition at 5pm)
    scheduler.add_job(
        lab.run_trend_analysis,
        CronTrigger(day_of_week="fri", hour=16, minute=0),
        id="trend_analysis",
        name="Trend Analysis",
        max_instances=1,
    )

    # GitHub discovery: every Monday 9am — find and register new teams
    scheduler.add_job(
        lab.run_github_discovery,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="github_discovery",
        name="GitHub Trending Discovery",
        max_instances=1,
    )

    # Startup: run research cycle after 60s, GitHub discovery after 90s
    scheduler.add_job(
        lab.run_research_cycle,
        "date",
        run_date=datetime.now() + timedelta(seconds=60),
        id="startup_research",
    )
    scheduler.add_job(
        lab.run_github_discovery,
        "date",
        run_date=datetime.now() + timedelta(seconds=90),
        id="startup_github",
    )

    logger.info(
        "Strategy Lab started.\n"
        "  Research cycle: Tue/Thu 10am KST\n"
        "  Trend analysis: Fri 4pm KST\n"
        "  GitHub discovery: Mon 9am KST"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
