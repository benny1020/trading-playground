"""
Portfolio API
=============
팩터 스코어, 포트폴리오 포지션, 리밸런싱 이력 API.
"""
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional

from app.database import get_db

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/factor-scores")
def get_factor_scores(
    market: Optional[str] = Query(default=None),
    score_date: Optional[str] = Query(default=None),
    top_n: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """최신 팩터 스코어 조회."""
    # score_date 없으면 최신 날짜 사용
    if not score_date:
        latest = db.execute(text("""
            SELECT MAX(score_date) FROM factor_scores
        """)).scalar()
        if not latest:
            return {"score_date": None, "scores": []}
        score_date = str(latest)

    market_clause = "" if not market or market == "ALL" else "AND market = :market"
    params = {"score_date": score_date, "top_n": top_n}
    if market and market != "ALL":
        params["market"] = market

    rows = db.execute(text(f"""
        SELECT
            fs.symbol,
            si.name,
            si.sector,
            fs.market,
            fs.composite_score,
            fs.rank,
            fs.momentum_12m1m,
            fs.momentum_3m,
            fs.low_vol,
            fs.value_proxy,
            fs.quality_proxy,
            fs.momentum_12m1m_rank,
            fs.momentum_3m_rank,
            fs.low_vol_rank,
            fs.value_proxy_rank,
            fs.quality_proxy_rank,
            fs.score_date
        FROM factor_scores fs
        LEFT JOIN stock_info si ON si.symbol = fs.symbol
        WHERE fs.score_date = :score_date
        {market_clause}
        ORDER BY fs.rank ASC
        LIMIT :top_n
    """), params).fetchall()

    return {
        "score_date": score_date,
        "total": len(rows),
        "scores": [dict(r._mapping) for r in rows],
    }


@router.get("/positions/{team_id}")
def get_team_positions(
    team_id: str,
    db: Session = Depends(get_db),
):
    """팀별 현재 포트폴리오 포지션 조회."""
    rows = db.execute(text("""
        SELECT
            pp.symbol,
            si.name,
            si.sector,
            pp.target_weight,
            pp.last_rebalanced,
            pp.updated_at,
            fs.composite_score,
            fs.rank AS factor_rank,
            fs.momentum_12m1m,
            fs.low_vol,
            fs.quality_proxy
        FROM portfolio_positions pp
        LEFT JOIN stock_info si ON si.symbol = pp.symbol
        LEFT JOIN factor_scores fs ON fs.symbol = pp.symbol
            AND fs.score_date = (SELECT MAX(score_date) FROM factor_scores)
        WHERE pp.team_id = :team_id AND pp.is_active = TRUE
        ORDER BY pp.target_weight DESC
    """), {"team_id": team_id}).fetchall()

    return {
        "team_id": team_id,
        "total": len(rows),
        "positions": [dict(r._mapping) for r in rows],
    }


@router.get("/positions")
def get_all_positions(db: Session = Depends(get_db)):
    """전체 팀 포지션 요약 조회."""
    rows = db.execute(text("""
        SELECT
            pp.team_id,
            st.team_name,
            COUNT(pp.symbol) AS holding_count,
            ROUND(SUM(pp.target_weight)::numeric, 4) AS total_weight,
            MAX(pp.last_rebalanced) AS last_rebalanced
        FROM portfolio_positions pp
        JOIN strategy_teams st ON st.team_id = pp.team_id
        WHERE pp.is_active = TRUE
        GROUP BY pp.team_id, st.team_name
        ORDER BY pp.team_id
    """)).fetchall()

    return [dict(r._mapping) for r in rows]


@router.post("/run-factor-engine")
def run_factor_engine(
    background_tasks: BackgroundTasks,
    market: str = Query(default="ALL"),
    db: Session = Depends(get_db),
):
    """팩터 엔진 수동 실행 (백그라운드)."""
    from app.services.factor_engine import factor_engine, portfolio_optimizer, rebalance_engine
    from app.database import SessionLocal

    def _run():
        _db = SessionLocal()
        try:
            scores = factor_engine.run(_db, market=market)
            if scores.empty:
                return

            # 각 팀별 포트폴리오 구성
            team_markets = {
                "quant_strategies": market,
                "ai_hedge_fund": market,
            }
            for team_id, m in team_markets.items():
                portfolio_optimizer.build_portfolio(_db, team_id=team_id, market=m)
                rebalance_engine.rebalance(_db, team_id=team_id)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"status": "started", "message": f"팩터 엔진 실행 중 (market={market})"}


@router.get("/rebalance-history/{team_id}")
def get_rebalance_history(
    team_id: str,
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
):
    """팀별 리밸런싱 이력 조회."""
    rows = db.execute(text("""
        SELECT id, team_id, rebalance_date, trades, summary, created_at
        FROM rebalance_history
        WHERE team_id = :team_id
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"team_id": team_id, "limit": limit}).fetchall()

    return [dict(r._mapping) for r in rows]


@router.get("/rebalance-history")
def get_all_rebalance_history(
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    """전체 리밸런싱 이력 조회."""
    rows = db.execute(text("""
        SELECT rh.id, rh.team_id, st.team_name, rh.rebalance_date,
               rh.summary, rh.created_at
        FROM rebalance_history rh
        JOIN strategy_teams st ON st.team_id = rh.team_id
        ORDER BY rh.created_at DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    return [dict(r._mapping) for r in rows]


@router.get("/team-members")
def get_all_team_members(db: Session = Depends(get_db)):
    """전체 팀원 목록 조회."""
    rows = db.execute(text("""
        SELECT
            tm.id, tm.team_id, st.team_name,
            tm.member_name, tm.role, tm.role_type,
            tm.description, tm.is_head, tm.is_ai_agent,
            tm.expertise_tags
        FROM team_members tm
        JOIN strategy_teams st ON st.team_id = tm.team_id
        ORDER BY tm.team_id, tm.is_head DESC, tm.id ASC
    """)).fetchall()

    # 팀별로 그룹화
    teams: dict = {}
    for r in rows:
        d = dict(r._mapping)
        tid = d["team_id"]
        if tid not in teams:
            teams[tid] = {"team_id": tid, "team_name": d["team_name"], "members": []}
        teams[tid]["members"].append(d)

    return list(teams.values())


@router.get("/team-members/{team_id}")
def get_team_members(team_id: str, db: Session = Depends(get_db)):
    """팀별 팀원 목록 조회."""
    rows = db.execute(text("""
        SELECT
            tm.id, tm.team_id, st.team_name,
            tm.member_name, tm.role, tm.role_type,
            tm.description, tm.is_head, tm.is_ai_agent,
            tm.expertise_tags
        FROM team_members tm
        JOIN strategy_teams st ON st.team_id = tm.team_id
        WHERE tm.team_id = :team_id
        ORDER BY tm.is_head DESC, tm.id ASC
    """), {"team_id": team_id}).fetchall()

    return [dict(r._mapping) for r in rows]
