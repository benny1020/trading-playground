"""
Company Dashboard API
=====================
CEO 평가, 팀 경쟁, 매매 일지, 에이전트 기억 조회 엔드포인트.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db

router = APIRouter(prefix="/api/company", tags=["company"])


@router.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    """전략팀 순위표."""
    rows = db.execute(text("""
        SELECT team_id, team_name, description, team_type,
               wins, total_competitions,
               ROUND(best_sharpe::numeric, 3) AS best_sharpe,
               ROUND(best_cagr::numeric, 3)   AS best_cagr,
               created_at
        FROM strategy_teams
        WHERE is_active = TRUE
        ORDER BY wins DESC, best_sharpe DESC NULLS LAST
    """)).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/competition/latest")
def get_latest_competition(db: Session = Depends(get_db)):
    """최근 CEO 경쟁 평가 결과."""
    row = db.execute(text("""
        SELECT round_number, test_start_date, test_end_date,
               results, winner_team_id, winner_strategy,
               ceo_praise, ceo_notes, created_at
        FROM competition_rounds
        ORDER BY created_at DESC
        LIMIT 1
    """)).fetchone()
    if not row:
        return None
    return dict(row._mapping)


@router.get("/competition/history")
def get_competition_history(
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
):
    """경쟁 라운드 히스토리."""
    rows = db.execute(text("""
        SELECT round_number, test_start_date, test_end_date,
               winner_team_id, winner_strategy,
               ceo_praise, ceo_notes, created_at,
               jsonb_array_length(results) AS team_count
        FROM competition_rounds
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/trade-journal")
def get_trade_journal(
    market: str = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """전체 매매 일지 조회."""
    q = """
        SELECT id, agent_id, market, signal_date, signal_type,
               confidence, entry_price, exit_price, exit_date,
               return_pct, was_correct, agent_breakdown, outcome_note, created_at
        FROM trade_journal
        {where}
        ORDER BY signal_date DESC, created_at DESC
        LIMIT :limit
    """
    if market:
        q = q.format(where="WHERE market = :market")
        rows = db.execute(text(q), {"market": market, "limit": limit}).fetchall()
    else:
        q = q.format(where="")
        rows = db.execute(text(q), {"limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/trade-journal/stats")
def get_trade_stats(db: Session = Depends(get_db)):
    """시장별 매매 정확도 통계."""
    rows = db.execute(text("""
        SELECT
            market,
            signal_type,
            COUNT(*) AS total,
            SUM(CASE WHEN was_correct THEN 1 ELSE 0 END) AS correct,
            ROUND(AVG(return_pct)::numeric, 2) AS avg_return_pct,
            ROUND(MIN(return_pct)::numeric, 2) AS worst_pct,
            ROUND(MAX(return_pct)::numeric, 2) AS best_pct
        FROM trade_journal
        WHERE was_correct IS NOT NULL
        GROUP BY market, signal_type
        ORDER BY market, signal_type
    """)).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/agent-memory")
def get_agent_memory(
    agent_id: str = Query(default=None),
    memory_type: str = Query(default=None),
    limit: int = Query(default=30, le=100),
    db: Session = Depends(get_db),
):
    """에이전트 기억 조회."""
    conditions = []
    params = {"limit": limit}

    if agent_id:
        conditions.append("agent_id = :agent_id")
        params["agent_id"] = agent_id
    if memory_type:
        conditions.append("memory_type = :memory_type")
        params["memory_type"] = memory_type

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = db.execute(text(f"""
        SELECT id, agent_id, memory_type, content, context,
               importance, times_used, created_at, updated_at
        FROM agent_memory
        {where}
        ORDER BY importance DESC, updated_at DESC
        LIMIT :limit
    """), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/agentic-signals")
def get_agentic_signals(
    market: str = Query(default=None),
    limit: int = Query(default=30, le=100),
    db: Session = Depends(get_db),
):
    """Agentic Trading 신호 히스토리."""
    if market:
        rows = db.execute(text("""
            SELECT id, market, final_signal, confidence, position_size,
                   stop_loss_pct, take_profit_pct, agent_signals, synthesis, created_at
            FROM agentic_signals
            WHERE market = :market
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"market": market, "limit": limit}).fetchall()
    else:
        rows = db.execute(text("""
            SELECT id, market, final_signal, confidence, position_size,
                   stop_loss_pct, take_profit_pct, agent_signals, synthesis, created_at
            FROM agentic_signals
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]
