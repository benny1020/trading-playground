import logging
import traceback
import asyncio
from datetime import datetime, date
from typing import Optional

from app.workers.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_backtest",
    max_retries=2,
    default_retry_delay=30,
)
def run_backtest(self, backtest_id: str):
    """
    Execute a backtest run.
    Loads the BacktestRun from DB, fetches price data, generates signals,
    runs the engine, and persists results.
    """
    import uuid
    import math
    from app.models.backtest import BacktestRun
    from app.models.strategy import Strategy
    from app.services.backtest_engine import BacktestEngine
    from app.services.strategy_library import get_strategy
    from app.services.data_service import data_service

    db = SessionLocal()
    try:
        backtest = db.query(BacktestRun).filter(
            BacktestRun.id == uuid.UUID(backtest_id)
        ).first()

        if not backtest:
            logger.error(f"Backtest {backtest_id} not found in database")
            return {"error": "Backtest not found"}

        # Update status to running
        backtest.status = "running"
        backtest.updated_at = datetime.utcnow()
        db.commit()

        strategy = db.query(Strategy).filter(
            Strategy.id == backtest.strategy_id
        ).first()

        if not strategy:
            raise ValueError(f"Strategy {backtest.strategy_id} not found")

        start_str = backtest.start_date.strftime("%Y-%m-%d")
        end_str = backtest.end_date.strftime("%Y-%m-%d")
        symbols = backtest.symbols or []

        logger.info(
            f"Running backtest {backtest_id}: strategy={strategy.name}, "
            f"market={backtest.market}, symbols={symbols}, "
            f"period={start_str} to {end_str}"
        )

        # Fetch price data
        prices = data_service.get_price_data(
            symbols=symbols,
            start=start_str,
            end=end_str,
            market=backtest.market,
        )

        if prices.empty:
            raise ValueError(
                f"No price data available for symbols {symbols} in market {backtest.market} "
                f"from {start_str} to {end_str}"
            )

        logger.info(
            f"Fetched price data: {prices.shape[0]} days, {prices.shape[1]} symbols"
        )

        # Generate signals
        strategy_instance = get_strategy(strategy.strategy_type)
        params = strategy.parameters or {}
        signals = strategy_instance.generate_signals(prices, **params)

        # Run backtest engine — enforce point-in-time (no future data)
        engine = BacktestEngine(
            initial_capital=backtest.initial_capital,
            commission_rate=backtest.commission_rate,
        )
        result = engine.run(prices, signals, end_date=end_str)

        # Serialize equity curve
        equity_curve_data = [
            {"date": str(d), "value": float(v)}
            for d, v in result.equity_curve.items()
            if not math.isnan(v)
        ]

        # Serialize trades
        trades_data = [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "side": t.side,
                "pnl": t.pnl,
                "return_pct": t.return_pct,
            }
            for t in result.trades
        ]

        # Persist results
        backtest.status = "completed"
        backtest.results = result.metrics
        backtest.equity_curve = equity_curve_data
        backtest.trades = trades_data
        backtest.error_message = None
        backtest.updated_at = datetime.utcnow()
        db.commit()

        logger.info(
            f"Backtest {backtest_id} completed. "
            f"Total return: {result.metrics.get('total_return_pct', 0):.2f}%, "
            f"Sharpe: {result.metrics.get('sharpe_ratio', 0):.2f}, "
            f"Trades: {result.metrics.get('n_trades', 0)}"
        )

        return {
            "status": "completed",
            "backtest_id": backtest_id,
            "metrics": result.metrics,
        }

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc()}"
        logger.error(f"Backtest {backtest_id} failed: {error_msg}")

        try:
            backtest = db.query(BacktestRun).filter(
                BacktestRun.id == uuid.UUID(backtest_id)
            ).first()
            if backtest:
                backtest.status = "failed"
                backtest.error_message = error_msg[:2000]
                backtest.updated_at = datetime.utcnow()
                db.commit()
        except Exception as db_exc:
            logger.error(f"Failed to update backtest status: {db_exc}")

        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc

    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.fetch_market_data",
    max_retries=3,
    default_retry_delay=60,
)
def fetch_market_data(self, market: str = "ALL", start: str = "2020-01-01"):
    """
    Scheduled task: Fetch latest market data for all tracked symbols.
    Runs daily at 6pm weekdays (after Korean market close).
    """
    from app.services.data_service import data_service

    db = SessionLocal()
    try:
        today = date.today().strftime("%Y-%m-%d")
        logger.info(f"Starting market data fetch for {market} up to {today}")

        if market in ("KOSPI", "ALL"):
            logger.info("Fetching KOSPI data...")
            data_service.fetch_kospi_stocks(db, start=start)
            logger.info("KOSPI data fetch complete")

        if market in ("KOSDAQ", "ALL"):
            logger.info("Fetching KOSDAQ data...")
            data_service.fetch_kosdaq_stocks(db, start=start)
            logger.info("KOSDAQ data fetch complete")

        logger.info(f"Market data fetch completed for {market}")
        return {"status": "completed", "market": market, "date": today}

    except Exception as exc:
        logger.error(f"Market data fetch failed: {exc}\n{traceback.format_exc()}")
        raise self.retry(exc=exc)

    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_factor_engine",
    max_retries=2,
    default_retry_delay=60,
)
def run_factor_engine(self, market: str = "ALL"):
    """
    Scheduled task: Run factor engine for universe scoring.
    Runs every Monday at 7am KST.
    """
    from app.services.factor_engine import factor_engine

    db = SessionLocal()
    try:
        today = date.today().strftime("%Y-%m-%d")
        logger.info(f"[FactorEngine] Starting factor calculation for {market}, date={today}")
        scores = factor_engine.run(db, market=market, as_of_date=today)
        n = len(scores) if scores is not None and not scores.empty else 0
        logger.info(f"[FactorEngine] Completed: {n} stocks scored")
        return {"status": "completed", "scored": n, "date": today}
    except Exception as exc:
        logger.error(f"[FactorEngine] Failed: {exc}\n{traceback.format_exc()}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_portfolio_rebalance",
    max_retries=2,
    default_retry_delay=60,
)
def run_portfolio_rebalance(self):
    """
    Scheduled task: Build portfolio and rebalance for all strategy teams.
    Runs every Monday at 7:30am KST (after factor engine completes).
    """
    from app.services.factor_engine import portfolio_optimizer, rebalance_engine

    TEAMS = ["quant_strategies", "ai_hedge_fund"]
    db = SessionLocal()
    try:
        today = date.today().strftime("%Y-%m-%d")
        results = {}
        for team_id in TEAMS:
            try:
                weights = portfolio_optimizer.build_portfolio(db, team_id=team_id, as_of_date=today)
                rebalance = rebalance_engine.rebalance(db, team_id=team_id)
                results[team_id] = {
                    "positions": len(weights),
                    "summary": rebalance.get("summary", ""),
                }
                logger.info(f"[Rebalance] {team_id}: {len(weights)} positions")
            except Exception as e:
                logger.error(f"[Rebalance] Failed for {team_id}: {e}")
                results[team_id] = {"error": str(e)}

        return {"status": "completed", "results": results, "date": today}
    except Exception as exc:
        logger.error(f"[Rebalance] Task failed: {exc}\n{traceback.format_exc()}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.fetch_papers",
    max_retries=2,
    default_retry_delay=120,
)
def fetch_papers(
    self,
    query: str = "quantitative finance trading strategy",
    max_results: int = 30,
    analyze_with_ai: bool = True,
):
    """
    Scheduled task: Crawl arxiv for quantitative finance papers.
    Runs every Monday morning.
    Optionally analyzes each paper with Claude API.
    """
    import feedparser
    import httpx
    from app.models.market_data import Paper
    from app.config import settings

    db = SessionLocal()
    try:
        logger.info(f"Fetching papers: query='{query}', max_results={max_results}")

        feed_url = (
            f"https://export.arxiv.org/search/?search_query=all:{query.replace(' ', '+')}"
            f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        )

        response = httpx.get(feed_url, timeout=30.0)
        response.raise_for_status()
        feed = feedparser.parse(response.text)

        papers_data = _parse_arxiv_entries(feed.entries)
        stored_count = 0
        skipped_count = 0

        for paper_data in papers_data:
            # Skip if already in DB
            existing = db.query(Paper).filter(Paper.url == paper_data["url"]).first()
            if existing:
                skipped_count += 1
                continue

            relevance = _score_relevance(paper_data["title"], paper_data.get("abstract", ""))

            if relevance < 0.05:
                continue

            ai_summary = ""
            if analyze_with_ai and paper_data.get("abstract") and settings.ANTHROPIC_API_KEY:
                ai_summary = _sync_analyze_with_claude(
                    paper_data["title"],
                    paper_data.get("abstract", ""),
                    settings.ANTHROPIC_API_KEY,
                )

            paper = Paper(
                title=paper_data["title"][:500],
                authors=paper_data["authors"],
                abstract=paper_data.get("abstract", ""),
                url=paper_data["url"][:1000] if paper_data.get("url") else None,
                source="arxiv",
                published_date=paper_data.get("published_date"),
                tags=paper_data.get("tags", []),
                summary=ai_summary,
                relevance_score=relevance,
            )
            db.add(paper)
            stored_count += 1

        db.commit()
        logger.info(
            f"Paper fetch complete: {stored_count} stored, {skipped_count} already existed"
        )
        return {
            "status": "completed",
            "stored": stored_count,
            "skipped": skipped_count,
            "query": query,
        }

    except Exception as exc:
        logger.error(f"Paper fetch failed: {exc}\n{traceback.format_exc()}")
        db.rollback()
        raise self.retry(exc=exc)

    finally:
        db.close()


def _parse_arxiv_entries(entries: list) -> list:
    """Parse arxiv feed entries into structured dicts."""
    papers = []
    for entry in entries:
        title = getattr(entry, "title", "").strip()
        if not title:
            continue

        abstract = getattr(entry, "summary", "") or ""
        abstract = abstract.replace("\n", " ").strip()

        link = getattr(entry, "link", "") or ""
        if hasattr(entry, "id") and "arxiv.org" in getattr(entry, "id", ""):
            link = entry.id

        authors = []
        if hasattr(entry, "authors"):
            authors = [
                a.get("name", "") for a in entry.authors if isinstance(a, dict)
            ]
        elif hasattr(entry, "author"):
            authors = [entry.author]

        published = None
        for attr in ("published_parsed", "updated_parsed"):
            t = getattr(entry, attr, None)
            if t:
                try:
                    published = date(t.tm_year, t.tm_mon, t.tm_mday)
                    break
                except Exception:
                    pass

        tags = []
        if hasattr(entry, "tags"):
            tags = [
                t.get("term", "") for t in entry.tags if isinstance(t, dict)
            ]

        papers.append(
            {
                "title": title,
                "abstract": abstract,
                "url": link,
                "authors": authors,
                "published_date": published,
                "tags": tags,
                "source": "arxiv",
            }
        )
    return papers


def _score_relevance(title: str, abstract: str) -> float:
    """Keyword-based relevance scoring for quant finance papers."""
    keywords_high = [
        "trading strategy", "backtesting", "momentum", "mean reversion",
        "factor model", "portfolio optimization", "alpha", "statistical arbitrage",
        "pairs trading", "machine learning trading", "reinforcement learning",
        "asset pricing", "systematic trading", "quantitative finance",
    ]
    keywords_medium = [
        "stock market", "equity return", "return prediction", "volatility forecasting",
        "financial time series", "deep learning", "LSTM", "transformer",
        "cross-sectional", "factor investing", "smart beta", "risk premium",
    ]

    text = (title + " " + abstract).lower()
    score = 0.0

    for kw in keywords_high:
        if kw.lower() in text:
            score += 0.1

    for kw in keywords_medium:
        if kw.lower() in text:
            score += 0.05

    return min(1.0, score)


def _sync_analyze_with_claude(title: str, abstract: str, api_key: str) -> str:
    """Synchronous Claude API call for paper analysis."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            f"You are a quantitative finance researcher. Briefly analyze this paper:\n\n"
            f"Title: {title}\n\nAbstract: {abstract[:1500]}\n\n"
            f"Provide:\n"
            f"SUMMARY: [2-3 sentence plain English summary]\n"
            f"IMPLICATIONS: [practical trading implications in 1-2 sentences]\n"
            f"LIMITATIONS: [key limitations in 1 sentence]"
        )

        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text if message.content else ""
    except Exception as e:
        logger.warning(f"Claude analysis failed for '{title[:50]}': {e}")
        return ""
