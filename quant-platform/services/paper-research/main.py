"""
Paper Research Service for Quantitative Trading Platform
Fetches papers from arXiv, scores relevance, generates AI summaries
via Claude API, runs trend analysis, and stores results in PostgreSQL.
"""

import os
import re
import uuid
import logging
import time
from datetime import datetime, date, timedelta
from typing import Optional
from collections import Counter

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, text, Column, String, Float, Text, Date,
    DateTime, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import insert as pg_insert
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("paper-research")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quant123@localhost:5432/quantdb")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

ARXIV_CATEGORIES = [
    "q-fin.PM",   # Portfolio Management
    "q-fin.TR",   # Trading and Market Microstructure
    "q-fin.ST",   # Statistical Finance
    "q-fin.CP",   # Computational Finance
    "cs.LG",      # Machine Learning (filtered by quant keywords)
    "cs.AI",      # AI - Agentic / LLM trading (filtered by quant keywords)
]

RELEVANCE_KEYWORDS = [
    # Classic quant
    "momentum", "mean reversion", "factor", "alpha", "backtesting",
    "portfolio optimization", "risk", "trading strategy",
    "high frequency", "market microstructure", "arbitrage",
    "volatility", "return prediction", "asset pricing",
    "quantitative", "systematic trading", "signal",
    # ML / DL
    "machine learning", "deep learning", "stock prediction",
    "reinforcement learning", "neural network", "transformer",
    "lstm", "attention mechanism", "gradient boosting",
    # Agentic / LLM trading (hot research area)
    "agentic trading", "llm trading", "large language model",
    "gpt trading", "agent", "autonomous trading",
    "multi-agent", "chain of thought", "reasoning",
    "language model", "foundation model", "generative ai",
    # Korean market specific
    "kospi", "kosdaq", "korean stock", "emerging market",
]

# Keywords that boost relevance for cs.LG / cs.AI papers (must be finance-related)
QUANT_FINANCE_KEYWORDS = [
    "stock", "equity", "portfolio", "trading", "financial", "market",
    "return", "asset", "price prediction", "hedge fund", "alpha",
    "agentic", "autonomous", "agent-based", "llm", "gpt",
]

# High-priority papers (score x1.5 boost): explicitly agentic trading research
AGENTIC_TRADING_KEYWORDS = [
    "agentic trading", "trading agent", "llm for trading",
    "large language model trading", "autonomous trading system",
    "ai agent trading", "multi-agent trading", "gpt trading",
    "foundation model finance", "reasoning trading",
]

PAPERS_PER_CATEGORY = 50

# ---------------------------------------------------------------------------
# SQLAlchemy Models
# ---------------------------------------------------------------------------
Base = declarative_base()


class Paper(Base):
    __tablename__ = "papers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    authors = Column(Text)
    abstract = Column(Text)
    url = Column(Text, unique=True)
    source = Column(String(50))
    published_date = Column(Date)
    tags = Column(ARRAY(Text))
    summary = Column(Text)
    relevance_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class TrendReport(Base):
    __tablename__ = "trend_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_date = Column(Date, nullable=False)
    trending_topics = Column(JSONB)
    top_papers = Column(JSONB)
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)


def init_db(engine):
    """Create tables if they don't already exist."""
    Base.metadata.create_all(engine)
    ddl = """
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE INDEX IF NOT EXISTS idx_papers_relevance ON papers(relevance_score DESC);
    CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published_date DESC);
    """
    with engine.connect() as conn:
        for stmt in ddl.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    conn.execute(text(stmt))
                except Exception as exc:
                    logger.debug("DDL skip: %s", exc)
        conn.commit()
    logger.info("Database initialised")


def upsert_paper(engine, paper_dict: dict):
    """Insert or update a paper record."""
    with engine.connect() as conn:
        stmt = pg_insert(Paper).values(**paper_dict)
        stmt = stmt.on_conflict_do_update(
            index_elements=["url"],
            set_={
                "title": stmt.excluded.title,
                "abstract": stmt.excluded.abstract,
                "authors": stmt.excluded.authors,
                "relevance_score": stmt.excluded.relevance_score,
                "tags": stmt.excluded.tags,
                "summary": stmt.excluded.summary,
                "published_date": stmt.excluded.published_date,
            },
        )
        conn.execute(stmt)
        conn.commit()


def insert_trend_report(engine, report_dict: dict):
    """Insert a new trend report."""
    with engine.connect() as conn:
        stmt = pg_insert(TrendReport).values(**report_dict)
        stmt = stmt.on_conflict_do_nothing()
        conn.execute(stmt)
        conn.commit()


# ---------------------------------------------------------------------------
# arXiv fetching
# ---------------------------------------------------------------------------

def build_arxiv_url(category: str, max_results: int) -> str:
    base = "http://export.arxiv.org/api/query"
    return (
        f"{base}?search_query=cat:{category}"
        f"&start=0&max_results={max_results}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )


def parse_arxiv_feed(category: str, max_results: int = 50) -> list[dict]:
    """Fetch and parse arXiv RSS/Atom feed for a category."""
    url = build_arxiv_url(category, max_results)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        papers = []
        for entry in feed.entries:
            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = date(*entry.published_parsed[:3])

            authors = ", ".join(
                a.get("name", "") for a in getattr(entry, "authors", [])
            )
            abstract = getattr(entry, "summary", "").strip()
            # Strip newlines from abstract
            abstract = re.sub(r"\s+", " ", abstract)

            link = entry.get("link", "")
            # Prefer PDF link if available
            for lnk in getattr(entry, "links", []):
                if lnk.get("type") == "application/pdf":
                    link = lnk["href"]
                    break

            papers.append({
                "title": entry.get("title", "").strip().replace("\n", " "),
                "authors": authors,
                "abstract": abstract,
                "url": link,
                "source": "arxiv",
                "published_date": pub_date,
                "category": category,
            })
        logger.info("Fetched %d papers from arXiv category %s", len(papers), category)
        return papers
    except Exception as exc:
        logger.error("arXiv fetch failed for %s: %s", category, exc)
        return []


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def score_paper(paper: dict, category: str) -> float:
    """
    Score a paper 0-10 based on keyword matches in title + abstract.
    cs.LG papers require finance-specific keywords to score above 0.
    """
    text_blob = (
        (paper.get("title") or "") + " " + (paper.get("abstract") or "")
    ).lower()

    # cs.LG / cs.AI: require at least one quant-finance keyword
    if category in ("cs.LG", "cs.AI"):
        has_finance_context = any(kw in text_blob for kw in QUANT_FINANCE_KEYWORDS)
        if not has_finance_context:
            return 0.0

    hits = sum(1 for kw in RELEVANCE_KEYWORDS if kw in text_blob)
    # Normalize: 4+ hits = score 10, scale linearly
    score = min(10.0, hits * 10.0 / 4.0)

    # Bonus for title matches (more specific signal)
    title_lower = (paper.get("title") or "").lower()
    title_hits = sum(1 for kw in RELEVANCE_KEYWORDS if kw in title_lower)
    score = min(10.0, score + title_hits * 0.5)

    # Agentic Trading boost: x1.5 multiplier — highest priority research area
    is_agentic = any(kw in text_blob for kw in AGENTIC_TRADING_KEYWORDS)
    if is_agentic:
        score = min(10.0, score * 1.5)
        logger.debug("Agentic trading boost applied: %s", paper.get("title", "")[:60])

    return round(score, 2)


def extract_tags(paper: dict) -> list[str]:
    """Extract matching keyword tags from the paper."""
    text_blob = (
        (paper.get("title") or "") + " " + (paper.get("abstract") or "")
    ).lower()
    return [kw for kw in RELEVANCE_KEYWORDS if kw in text_blob]


# ---------------------------------------------------------------------------
# Claude AI summarization
# ---------------------------------------------------------------------------

def summarize_with_claude(paper: dict) -> Optional[str]:
    """
    Generate a practitioner-focused summary using claude-haiku-4-5-20251001.
    Returns None if the API key is not set or the call fails.
    """
    if not ANTHROPIC_API_KEY:
        return None

    prompt = (
        "You are an expert quantitative finance researcher.\n\n"
        f"Title: {paper['title']}\n"
        f"Authors: {paper.get('authors', 'Unknown')}\n"
        f"Abstract: {paper.get('abstract', '')}\n\n"
        "Please provide:\n"
        "1. A 3-sentence practitioner summary (focus on actionable insights)\n"
        "2. Key strategy insights (2-3 bullet points)\n"
        "3. Applicable markets: Korean (KOSPI/KOSDAQ) or US markets? Explain briefly.\n\n"
        "Format your response as:\n"
        "SUMMARY: <3 sentences>\n"
        "INSIGHTS:\n- <insight 1>\n- <insight 2>\n"
        "MARKETS: <applicability>"
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        logger.error("Claude summarization failed for '%s': %s", paper.get("title"), exc)
        return None


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------

def fetch_recent_papers(engine, days: int = 30) -> list[dict]:
    """Fetch papers stored in the last N days."""
    cutoff = date.today() - timedelta(days=days)
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT title, abstract, tags, relevance_score, published_date "
                "FROM papers WHERE created_at >= :cutoff ORDER BY relevance_score DESC"
            ),
            {"cutoff": cutoff},
        )
        return [dict(row._mapping) for row in result]


def compute_trending_topics(papers: list[dict]) -> dict:
    """Count keyword frequencies across recent papers."""
    keyword_counter: Counter = Counter()
    for paper in papers:
        tags = paper.get("tags") or []
        if isinstance(tags, list):
            keyword_counter.update(tags)
        else:
            # Tags stored as string fallback
            pass
    return dict(keyword_counter.most_common(20))


def generate_trend_summary_claude(trending_topics: dict, top_papers: list[dict]) -> Optional[str]:
    """Ask Claude to write a weekly trend summary."""
    if not ANTHROPIC_API_KEY:
        return None

    topics_str = ", ".join(f"{k} ({v})" for k, v in list(trending_topics.items())[:10])
    paper_titles = "\n".join(f"- {p['title']}" for p in top_papers[:5])

    prompt = (
        "You are a quantitative finance research analyst.\n\n"
        f"This week's trending topics in quant finance research (keyword counts):\n{topics_str}\n\n"
        f"Top papers this week:\n{paper_titles}\n\n"
        "Write a concise 3-paragraph weekly trend report for a systematic trading team. "
        "Include: (1) dominant research themes, (2) emerging strategies gaining attention, "
        "(3) implications for Korean and US equity markets."
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        logger.error("Claude trend summary failed: %s", exc)
        return None


def run_trend_analysis(engine):
    """Weekly trend analysis: compute topic frequencies and store a trend report."""
    logger.info("Running weekly trend analysis...")
    papers = fetch_recent_papers(engine, days=30)
    if not papers:
        logger.warning("No papers found for trend analysis")
        return

    trending_topics = compute_trending_topics(papers)
    top_papers = sorted(papers, key=lambda p: p.get("relevance_score", 0), reverse=True)[:10]
    top_papers_serializable = [
        {
            "title": p["title"],
            "relevance_score": float(p.get("relevance_score") or 0),
            "published_date": str(p.get("published_date") or ""),
        }
        for p in top_papers
    ]

    # AI summary
    summary = generate_trend_summary_claude(trending_topics, top_papers)
    if not summary:
        # Fallback plain summary
        top_kws = list(trending_topics.items())[:5]
        summary = (
            f"Weekly trend report ({date.today()}). "
            f"Top research keywords: {', '.join(f'{k} ({v})' for k, v in top_kws)}. "
            f"Analysed {len(papers)} papers from the past 30 days."
        )

    report = {
        "id": uuid.uuid4(),
        "report_date": date.today(),
        "trending_topics": trending_topics,
        "top_papers": top_papers_serializable,
        "summary": summary,
        "created_at": datetime.utcnow(),
    }

    insert_trend_report(engine, report)
    logger.info("Trend report stored for %s", date.today())


# ---------------------------------------------------------------------------
# Main paper fetch task
# ---------------------------------------------------------------------------

def run_paper_fetch(engine):
    """Fetch new papers from arXiv, score them, summarise high-relevance ones."""
    logger.info("=== Paper fetch started ===")
    total_new = 0

    for category in ARXIV_CATEGORIES:
        papers = parse_arxiv_feed(category, max_results=PAPERS_PER_CATEGORY)
        time.sleep(3)  # Be polite to arXiv

        for raw_paper in papers:
            score = score_paper(raw_paper, category)
            if score == 0.0:
                continue  # Skip irrelevant papers

            tags = extract_tags(raw_paper)

            # AI summary for high-relevance papers
            summary = None
            if score >= 6.0 and ANTHROPIC_API_KEY:
                summary = summarize_with_claude(raw_paper)
                time.sleep(1)  # Rate limiting

            paper_record = {
                "id": uuid.uuid4(),
                "title": raw_paper["title"],
                "authors": raw_paper.get("authors"),
                "abstract": raw_paper.get("abstract"),
                "url": raw_paper.get("url"),
                "source": "arxiv",
                "published_date": raw_paper.get("published_date"),
                "tags": tags,
                "summary": summary,
                "relevance_score": score,
                "created_at": datetime.utcnow(),
            }

            try:
                upsert_paper(engine, paper_record)
                total_new += 1
            except Exception as exc:
                logger.error("Failed to store paper '%s': %s", raw_paper.get("title"), exc)

    logger.info("=== Paper fetch complete: %d papers stored/updated ===", total_new)


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------

def main():
    engine = get_engine()
    init_db(engine)

    # Initial run on startup
    logger.info("Running initial paper fetch on startup...")
    try:
        run_paper_fetch(engine)
    except Exception as exc:
        logger.error("Initial paper fetch failed: %s", exc, exc_info=True)

    logger.info("Running initial trend analysis on startup...")
    try:
        run_trend_analysis(engine)
    except Exception as exc:
        logger.error("Initial trend analysis failed: %s", exc, exc_info=True)

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # Fetch new papers every Monday at 09:00 KST
    scheduler.add_job(
        func=run_paper_fetch,
        args=[engine],
        trigger=CronTrigger(
            day_of_week="mon",
            hour=9,
            minute=0,
            timezone="Asia/Seoul",
        ),
        id="weekly_paper_fetch",
        name="Weekly arXiv Paper Fetch",
        misfire_grace_time=3600,
    )

    # Trend analysis every Friday at 17:00 KST
    scheduler.add_job(
        func=run_trend_analysis,
        args=[engine],
        trigger=CronTrigger(
            day_of_week="fri",
            hour=17,
            minute=0,
            timezone="Asia/Seoul",
        ),
        id="weekly_trend_analysis",
        name="Weekly Trend Analysis",
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduler started — paper fetch: Mon 09:00 KST | trend analysis: Fri 17:00 KST"
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
