import uuid
import logging
from typing import List, Optional
from datetime import datetime, date

import feedparser
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.market_data import Paper
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

ARXIV_QUANT_FIN_URL = (
    "http://export.arxiv.org/rss/q-fin"
)
ARXIV_API_URL = "https://export.arxiv.org/search/"


# ---- Pydantic Schemas ----

class PaperResponse(BaseModel):
    id: uuid.UUID
    title: str
    authors: Optional[List[str]]
    abstract: Optional[str]
    url: Optional[str]
    source: str
    published_date: Optional[date]
    tags: Optional[List[str]]
    summary: Optional[str]
    relevance_score: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class FetchPapersRequest(BaseModel):
    query: str = Field(
        default="quantitative finance trading strategy",
        description="Search query for arxiv papers",
    )
    max_results: int = Field(default=20, ge=1, le=100)
    analyze_with_ai: bool = Field(
        default=True,
        description="Whether to analyze papers with Claude AI",
    )


# ---- Helper Functions ----

def _parse_arxiv_papers(feed_entries: list) -> List[dict]:
    """Parse arxiv RSS/API feed entries into paper dicts."""
    papers = []
    for entry in feed_entries:
        title = getattr(entry, "title", "").strip()
        if not title:
            continue

        abstract = getattr(entry, "summary", "") or ""
        # Clean up abstract
        abstract = abstract.replace("\n", " ").strip()

        link = getattr(entry, "link", "") or ""
        if hasattr(entry, "id"):
            link = entry.id if "arxiv.org" in entry.id else link

        # Authors
        authors = []
        if hasattr(entry, "authors"):
            authors = [a.get("name", "") for a in entry.authors if isinstance(a, dict)]
        elif hasattr(entry, "author"):
            authors = [entry.author]

        # Published date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import time
            t = entry.published_parsed
            published = date(t.tm_year, t.tm_mon, t.tm_mday)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            t = entry.updated_parsed
            published = date(t.tm_year, t.tm_mon, t.tm_mday)

        # Tags from arxiv categories
        tags = []
        if hasattr(entry, "tags"):
            tags = [t.get("term", "") for t in entry.tags if isinstance(t, dict)]

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


def _compute_relevance_score(title: str, abstract: str) -> float:
    """
    Simple keyword-based relevance scoring for quant finance papers.
    Returns a float between 0 and 1.
    """
    keywords_high = [
        "trading strategy", "backtesting", "momentum", "mean reversion",
        "factor model", "portfolio optimization", "alpha", "hedge fund",
        "machine learning trading", "reinforcement learning trading",
        "pairs trading", "statistical arbitrage", "high frequency",
        "risk model", "asset pricing",
    ]
    keywords_medium = [
        "stock market", "equity", "return prediction", "volatility",
        "financial time series", "deep learning", "LSTM", "transformer",
        "cross-sectional", "factor investing", "smart beta",
        "quantitative", "systematic",
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


async def _analyze_paper_with_claude(title: str, abstract: str) -> str:
    """Use Claude API to generate a concise summary and analysis of a paper."""
    if not settings.ANTHROPIC_API_KEY:
        return ""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""You are a quantitative finance researcher. Analyze this academic paper and provide:
1. A 2-3 sentence plain-English summary of the key contribution
2. Practical trading implications (1-2 sentences)
3. Key limitations (1 sentence)

Paper Title: {title}

Abstract: {abstract}

Provide your analysis in this exact format:
SUMMARY: [2-3 sentence summary]
IMPLICATIONS: [trading implications]
LIMITATIONS: [key limitations]"""

        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text if message.content else ""
    except Exception as e:
        logger.error(f"Claude API error for paper analysis: {e}")
        return ""


async def _fetch_and_store_papers(
    query: str,
    max_results: int,
    analyze_with_ai: bool,
    db: Session,
):
    """Background task to crawl arxiv and store papers."""
    try:
        # Use arxiv API for structured search
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        feed_url = f"https://export.arxiv.org/search/?search_query=all:{query.replace(' ', '+')}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
            feed_content = response.text

        feed = feedparser.parse(feed_content)
        papers_data = _parse_arxiv_papers(feed.entries)

        stored_count = 0
        for paper_data in papers_data:
            # Check if paper already exists
            existing = (
                db.query(Paper).filter(Paper.url == paper_data["url"]).first()
            )
            if existing:
                continue

            relevance = _compute_relevance_score(
                paper_data["title"], paper_data.get("abstract", "")
            )

            # Only store if somewhat relevant
            if relevance < 0.05:
                continue

            ai_summary = ""
            if analyze_with_ai and paper_data.get("abstract"):
                ai_summary = await _analyze_paper_with_claude(
                    paper_data["title"], paper_data["abstract"]
                )

            paper = Paper(
                title=paper_data["title"][:500],
                authors=paper_data["authors"],
                abstract=paper_data.get("abstract", ""),
                url=paper_data["url"][:1000],
                source="arxiv",
                published_date=paper_data.get("published_date"),
                tags=paper_data.get("tags", []),
                summary=ai_summary,
                relevance_score=relevance,
            )
            db.add(paper)
            stored_count += 1

        db.commit()
        logger.info(f"Stored {stored_count} new papers from arxiv query: '{query}'")

    except Exception as e:
        logger.error(f"Paper fetch failed: {e}")
        db.rollback()


# ---- Endpoints ----

@router.get("/papers", response_model=List[PaperResponse], summary="List research papers")
def list_papers(
    source: Optional[str] = Query(None, description="Filter by source: arxiv or ssrn"),
    min_relevance: Optional[float] = Query(None, ge=0.0, le=1.0),
    search: Optional[str] = Query(None, description="Search in title or abstract"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List stored research papers with optional filtering."""
    query = db.query(Paper)

    if source:
        query = query.filter(Paper.source == source)
    if min_relevance is not None:
        query = query.filter(Paper.relevance_score >= min_relevance)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            Paper.title.ilike(search_term) | Paper.abstract.ilike(search_term)
        )

    return (
        query.order_by(Paper.relevance_score.desc(), Paper.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post(
    "/papers/fetch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger paper crawl from arxiv",
)
async def fetch_papers(
    payload: FetchPapersRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger a crawl of arxiv for quantitative finance papers.
    Papers are analyzed with Claude AI if ANTHROPIC_API_KEY is configured.
    Returns immediately; crawl runs in background.
    """
    background_tasks.add_task(
        _fetch_and_store_papers,
        payload.query,
        payload.max_results,
        payload.analyze_with_ai,
        db,
    )
    return {
        "status": "accepted",
        "message": f"Paper crawl started for query: '{payload.query}'",
        "max_results": payload.max_results,
        "analyze_with_ai": payload.analyze_with_ai,
    }


@router.get("/papers/{paper_id}", response_model=PaperResponse, summary="Get paper detail")
def get_paper(paper_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific research paper by ID."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found.")
    return paper


@router.delete("/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a paper")
def delete_paper(paper_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a research paper from the database."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found.")
    db.delete(paper)
    db.commit()
    return None


class DiscoveryRequest(BaseModel):
    focus: str = Field(
        default="agentic trading, momentum, mean reversion, factor investing, machine learning trading",
        description="Research focus keywords for trend-based strategy discovery",
    )
    max_papers: int = Field(default=30, ge=5, le=100)
    auto_backtest: bool = Field(default=True, description="Automatically backtest discovered strategies")


async def _run_strategy_discovery(focus: str, max_papers: int, auto_backtest: bool, db: Session):
    """
    Full pipeline:
    1. Fetch latest papers matching focus keywords from arXiv
    2. Score & analyze with Claude AI
    3. Extract strategy ideas from top papers
    4. Create strategies in DB
    5. Trigger backtests
    """
    logger.info("=== Strategy Discovery Started | focus: %s ===", focus[:80])

    # Step 1: Fetch papers
    queries = [q.strip() for q in focus.split(",")][:3]
    all_papers_stored = 0
    for query in queries:
        await _fetch_and_store_papers(
            query=query,
            max_results=max_papers // len(queries),
            analyze_with_ai=bool(settings.ANTHROPIC_API_KEY),
            db=db,
        )
        all_papers_stored += 1

    # Step 2: Get top newly scored papers
    from app.models.market_data import Paper as PaperModel
    top_papers = (
        db.query(PaperModel)
        .filter(PaperModel.relevance_score >= 0.3)
        .order_by(PaperModel.created_at.desc(), PaperModel.relevance_score.desc())
        .limit(10)
        .all()
    )

    if not top_papers:
        logger.info("No high-relevance papers found")
        return {"papers_fetched": all_papers_stored, "strategies_created": 0}

    # Step 3 & 4: Extract strategy ideas with Claude and create them
    strategies_created = 0
    backtests_triggered = 0

    if settings.ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        for paper in top_papers[:5]:
            try:
                prompt = f"""You are a senior quantitative researcher. Extract ONE concrete trading strategy from this paper.

Paper: {paper.title}
Abstract: {(paper.abstract or '')[:1500]}

Return ONLY valid JSON with this exact structure:
{{
  "name": "Short strategy name",
  "description": "Clear 1-2 sentence description of the logic",
  "strategy_type": "momentum|mean_reversion|factor|breakout|pairs|ml_based",
  "market": "KOSPI|KOSDAQ|US|ALL",
  "parameters": {{"key": "value"}}
}}"""

                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = msg.content[0].text
                import json
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    idea = json.loads(raw[start:end])
                    idea["name"] = f"[DISCOVERY] {idea['name'][:60]}_{uuid.uuid4().hex[:4]}"
                    idea["parameters"]["source_paper"] = str(paper.id)

                    # Create strategy via DB directly
                    from app.models.strategy import Strategy
                    strategy = Strategy(
                        name=idea["name"],
                        description=idea.get("description", ""),
                        strategy_type=idea.get("strategy_type", "momentum"),
                        parameters=idea.get("parameters", {}),
                        market=idea.get("market", "US"),
                    )
                    db.add(strategy)
                    db.flush()
                    strategies_created += 1

                    # Step 5: Trigger backtest
                    if auto_backtest:
                        from app.models.backtest import BacktestRun
                        from datetime import timedelta
                        market = idea.get("market", "US")
                        default_symbols = {
                            "KOSPI": ["005930", "000660", "035420", "051910", "006400"],
                            "KOSDAQ": ["247540", "196170", "091990", "293490", "112040"],
                            "US": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
                        }.get(market, ["AAPL", "MSFT", "GOOGL"])

                        bt = BacktestRun(
                            strategy_id=strategy.id,
                            name=f"Auto-{idea['name'][:40]}",
                            status="pending",
                            start_date=(datetime.now() - timedelta(days=365*3)).date(),
                            end_date=datetime.now().date(),
                            initial_capital=100_000_000,
                            commission_rate=0.0015,
                            symbols=default_symbols,
                            market=market,
                        )
                        db.add(bt)
                        db.flush()
                        backtests_triggered += 1

                        # Dispatch to Celery if available
                        try:
                            from app.workers.tasks import run_backtest
                            run_backtest.delay(str(bt.id))
                        except Exception:
                            pass

            except Exception as e:
                logger.warning("Strategy extraction failed for paper %s: %s", paper.id, e)

        db.commit()

    logger.info(
        "=== Discovery Complete | papers: %d | strategies: %d | backtests: %d ===",
        all_papers_stored, strategies_created, backtests_triggered,
    )
    return {
        "papers_fetched": all_papers_stored,
        "strategies_created": strategies_created,
        "backtests_triggered": backtests_triggered,
    }


@router.post(
    "/trigger-strategy-discovery",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger trend research → strategy discovery → auto backtest",
)
async def trigger_strategy_discovery(
    payload: DiscoveryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    One-click pipeline:
    1. Fetch latest arXiv papers matching the focus area
    2. Extract strategy ideas with Claude AI
    3. Create strategies in DB
    4. Automatically trigger backtests

    Runs in background, returns immediately.
    """
    background_tasks.add_task(
        _run_strategy_discovery,
        payload.focus,
        payload.max_papers,
        payload.auto_backtest,
        db,
    )
    return {
        "status": "accepted",
        "message": "Strategy discovery pipeline started. Check /api/strategies and /api/backtests for results.",
        "focus": payload.focus,
        "auto_backtest": payload.auto_backtest,
    }
