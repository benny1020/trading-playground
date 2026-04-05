"""
CEO Agent — QuantLab Capital
============================
돈에 미친 CEO. 수익만이 목표다.

매주 전략팀들의 성과를 냉정하게 평가한다.
잘한 팀은 극찬하고, 못한 팀은 강하게 압박한다.
과거 라운드 패턴을 기억해 평가 기준을 계속 높인다.

"수익 못 내는 팀은 필요 없다. 우리는 퀀트 자산운용사다."
"""

import os
import json
import logging
import uuid
from datetime import datetime, date, timedelta
from typing import Optional

import sys
import anthropic
import psycopg2
import psycopg2.extras
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

sys.path.insert(0, "/app/shared")
try:
    from memory_manager import MemoryManager
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CEO] %(levelname)s %(message)s",
)
logger = logging.getLogger("ceo_agent")

# ─── Config ──────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://quant:quant1234@postgres:5432/quantdb")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")


# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


# ─── Scoring ─────────────────────────────────────────────────────────────────

def composite_score(sharpe: float, cagr: float, mdd: float) -> float:
    """
    복합 점수 계산.
    Sharpe (0.4) + CAGR % (0.3) - |MDD| % (0.3)
    """
    s = (sharpe or 0) * 0.4
    c = (cagr or 0) * 0.3
    d = abs(mdd or 0) * 0.3
    return s + c - d


# ─── Data Collection ─────────────────────────────────────────────────────────

def get_team_best_backtest(db, team_id: str, since_date: date) -> Optional[dict]:
    """
    해당 팀의 최근 N일 내 완료된 백테스트 중 복합 점수 최고 결과 반환.
    Point-in-time: end_date <= today (미래 데이터 사용 불가).
    """
    cur = db.cursor()

    # Map team_id to strategy market/type filters
    team_filters = {
        "quant_strategies": "TRUE",
        "agentic_trading": "s.name ILIKE '%agentic%' OR s.name ILIKE '%agent%'",
        "ai_hedge_fund": "s.name ILIKE '%hedge%' OR s.name ILIKE '%buffett%' OR s.name ILIKE '%soros%'",
        "strategy_lab": "s.name ILIKE '%lab%' OR s.name ILIKE '%paper%' OR s.name ILIKE '%arxiv%'",
    }
    extra_filter = team_filters.get(team_id, "TRUE")

    cur.execute(f"""
        SELECT
            br.id,
            s.name AS strategy_name,
            s.market,
            br.results,
            br.end_date,
            br.start_date,
            br.created_at
        FROM backtest_runs br
        JOIN strategies s ON s.id = br.strategy_id
        WHERE br.status = 'completed'
          AND br.end_date <= %s
          AND br.created_at >= %s
          AND ({extra_filter})
          AND br.results IS NOT NULL
        ORDER BY br.created_at DESC
        LIMIT 50
    """, (date.today(), since_date))

    rows = cur.fetchall()
    if not rows:
        return None

    best = None
    best_score = float("-inf")
    for row in rows:
        results = row["results"] or {}
        sharpe = results.get("sharpe_ratio", 0) or 0
        cagr = results.get("cagr", 0) or 0
        mdd = results.get("max_drawdown", 0) or 0
        score = composite_score(sharpe, cagr, mdd)
        if score > best_score:
            best_score = score
            best = {
                "team_id": team_id,
                "strategy_name": row["strategy_name"],
                "market": row["market"],
                "sharpe": sharpe,
                "cagr": cagr,
                "mdd": mdd,
                "composite_score": score,
                "test_period": f"{row['start_date']} ~ {row['end_date']}",
                "backtest_id": str(row["id"]),
            }

    return best


def get_all_teams(db) -> list:
    cur = db.cursor()
    cur.execute("SELECT * FROM strategy_teams WHERE is_active = TRUE ORDER BY team_id")
    return list(cur.fetchall())


def get_next_round_number(db) -> int:
    cur = db.cursor()
    cur.execute("SELECT COALESCE(MAX(round_number), 0) + 1 AS next FROM competition_rounds")
    return cur.fetchone()["next"]


# ─── CEO Praise Generator ─────────────────────────────────────────────────────

def get_ceo_memory(db) -> tuple[MemoryManager, str]:
    """CEO의 과거 기억 로드. 누적 라운드 패턴 파악에 사용."""
    if not MEMORY_AVAILABLE:
        return None, ""
    try:
        mem = MemoryManager(db, "ceo_agent")
        ctx = mem.build_context_prompt(limit=10)
        return mem, ctx
    except Exception:
        return None, ""


def get_past_competition_context(db) -> str:
    """과거 경쟁 히스토리 요약 — CEO가 패턴을 인식하는 데 사용."""
    cur = db.cursor()
    try:
        cur.execute("""
            SELECT round_number, winner_team_id, winner_strategy,
                   results, created_at
            FROM competition_rounds
            ORDER BY created_at DESC
            LIMIT 5
        """)
        rows = cur.fetchall()
        if not rows:
            return ""

        lines = ["=== 과거 경쟁 히스토리 (최근 5라운드) ==="]
        for r in rows:
            results = r["results"] or []
            top3 = results[:3] if isinstance(results, list) else []
            lines.append(
                f"  Round {r['round_number']} ({str(r['created_at'].date())}): "
                f"우승={r['winner_team_id']} ({r['winner_strategy'][:40]})"
            )
        lines.append("=" * 40)
        return "\n".join(lines)
    except Exception:
        return ""


def generate_ceo_message(
    winner: dict,
    all_results: list,
    losers: list,
    round_num: int,
    memory_context: str = "",
    history_context: str = "",
) -> tuple[str, str]:
    """
    돈에 미친 CEO 메시지 생성.
    - 우승팀: 극찬 + 계속 밀어붙여라
    - 하위팀: 강한 압박 + 구체적 개선 지시
    - 기억 기반: 같은 팀이 반복 우승하면 더 높은 기준 요구
    Returns (praise_for_winner, pressure_for_losers)
    """
    if not ANTHROPIC_API_KEY:
        praise = (
            f"🏆 {winner['team_id']} 팀 Round {round_num} 우승! "
            f"Sharpe {winner['sharpe']:.2f}, CAGR {winner['cagr']:.1f}%! 계속 이 기세로!"
        )
        notes = f"하위 팀들: 수익 못 내면 팀 해체 검토. 다음 라운드까지 Sharpe 1.0 이상 목표."
        return praise, notes

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    rankings_text = "\n".join([
        f"  {i+1}위. {r['team_id']} | {r['strategy_name']} "
        f"| Sharpe={r['sharpe']:.2f} CAGR={r['cagr']:.1f}% MDD={r['mdd']:.1f}% "
        f"| 점수={r['composite_score']:.3f}"
        for i, r in enumerate(all_results)
    ])

    loser_text = "\n".join([
        f"  - {r['team_id']}: Sharpe={r['sharpe']:.2f}, CAGR={r['cagr']:.1f}%"
        for r in losers
    ]) if losers else "  없음"

    prompt = f"""당신은 AI 퀀트 자산운용사 "QuantLab Capital"의 CEO입니다.
당신은 수익에 완전히 집착합니다. 돈을 못 버는 팀은 존재 이유가 없다고 생각합니다.
매우 직설적이고, 데이터에 근거해 말하며, 팀원들에게 최대 성과를 요구합니다.

{memory_context}

{history_context}

=== Round {round_num} 결과 ===
{rankings_text}

=== 우승팀 ===
{winner['team_id']} | {winner['strategy_name']} | Sharpe={winner['sharpe']:.2f} CAGR={winner['cagr']:.1f}%

=== 하위 팀 ===
{loser_text}

다음을 작성하세요:

[CEO 칭찬] (우승팀에게. 2-3문장. 구체적 수치 언급. 열정적이고 직접적. 계속 압박하는 톤도 포함)

[CEO 압박] (하위 팀들에게. 3-4문장. 냉정하고 직설적. "이 수준이면 팀 해체" 류의 강한 메시지. 구체적 개선 지시 포함. 다음 라운드 목표 수치 제시)

각각 "[CEO 칭찬]", "[CEO 압박]" 헤더로 구분. 한국어로 작성."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text_out = resp.content[0].text if resp.content else ""

        praise = ""
        pressure = ""
        if "[CEO 칭찬]" in text_out:
            parts = text_out.split("[CEO 압박]")
            praise = parts[0].replace("[CEO 칭찬]", "").strip()
            pressure = parts[1].strip() if len(parts) > 1 else ""
        else:
            praise = text_out[:350]
            pressure = text_out[350:]

        return praise, pressure

    except Exception as e:
        logger.error(f"Claude API error in CEO message: {e}")
        return (
            f"🏆 Round {round_num} 우승: {winner['team_id']}! Sharpe {winner['sharpe']:.2f}!",
            f"하위 팀들 — 다음 라운드까지 Sharpe 1.0 이상 달성 못하면 팀 재편 고려.",
        )


# ─── Competition Runner ───────────────────────────────────────────────────────

def run_competition():
    """
    전략팀 간 경쟁 평가 실행.
    CEO가 과거 기억을 바탕으로 진화하는 평가를 수행한다.
    못하는 팀은 강하게 압박한다.
    """
    logger.info("=" * 60)
    logger.info("CEO COMPETITION ROUND STARTING — 수익만이 답이다")
    logger.info("=" * 60)

    db = get_db()
    try:
        # CEO 기억 로드
        ceo_memory, memory_context = get_ceo_memory(db)
        history_context = get_past_competition_context(db)

        teams = get_all_teams(db)
        since_date = date.today() - timedelta(days=90)
        round_num = get_next_round_number(db)

        logger.info(f"Round {round_num}: {len(teams)}개 팀 평가 (기준일: {since_date})")
        if memory_context:
            logger.info(f"CEO 기억 로드:\n{memory_context[:300]}")

        results = []
        no_result_teams = []
        for team in teams:
            team_id = team["team_id"]
            best = get_team_best_backtest(db, team_id, since_date)
            if best:
                results.append(best)
                logger.info(
                    f"  {team_id}: {best['strategy_name']} | "
                    f"Sharpe={best['sharpe']:.2f} CAGR={best['cagr']:.1f}% "
                    f"MDD={best['mdd']:.1f}% → score={best['composite_score']:.3f}"
                )
            else:
                no_result_teams.append(team_id)
                logger.warning(f"  {team_id}: ❌ 결과 없음 — CEO가 알 것이다")

        if not results:
            logger.warning("결과 없음 — 라운드 스킵")
            if ceo_memory:
                ceo_memory.remember_warning(
                    f"Round {round_num}: 어떤 팀도 결과를 제출하지 않음. 시스템 점검 필요.",
                    # importance already 0.8 in remember_warning
                )
            return

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        winner = results[0]
        losers = results[1:]  # 1위 제외한 전부가 압박 대상

        logger.info(f"\n🏆 WINNER: {winner['team_id']} — {winner['strategy_name']}")

        praise, pressure = generate_ceo_message(
            winner=winner,
            all_results=results,
            losers=losers,
            round_num=round_num,
            memory_context=memory_context,
            history_context=history_context,
        )

        logger.info(f"\n💬 CEO 칭찬:\n{praise}")
        logger.info(f"\n🔥 CEO 압박:\n{pressure}")
        if no_result_teams:
            logger.info(f"\n❌ 결과 미제출 팀: {no_result_teams} — 다음 라운드 경고 처리")

        # DB 저장
        cur = db.cursor()
        cur.execute("""
            INSERT INTO competition_rounds (
                round_number, test_start_date, test_end_date,
                results, winner_team_id, winner_strategy,
                ceo_praise, ceo_notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            round_num,
            since_date,
            date.today(),
            json.dumps(results),
            winner["team_id"],
            winner["strategy_name"],
            praise,
            pressure,
        ))

        for r in results:
            is_winner = r["team_id"] == winner["team_id"]
            cur.execute("""
                UPDATE strategy_teams
                SET total_competitions = total_competitions + 1,
                    wins = wins + %s,
                    best_sharpe = GREATEST(COALESCE(best_sharpe, -999), %s),
                    best_cagr   = GREATEST(COALESCE(best_cagr, -999), %s)
                WHERE team_id = %s
            """, (1 if is_winner else 0, r["sharpe"], r["cagr"], r["team_id"]))

        db.commit()

        # CEO 기억에 이번 라운드 인사이트 저장
        if ceo_memory:
            ceo_memory.remember_insight(
                f"Round {round_num} 우승: {winner['team_id']} "
                f"(Sharpe={winner['sharpe']:.2f}, CAGR={winner['cagr']:.1f}%). "
                f"참가 {len(results)}팀 중 1위.",
                importance=0.8,
            )
            if winner["sharpe"] > 1.5:
                ceo_memory.remember_insight(
                    f"{winner['team_id']}의 {winner['strategy_name']} 전략이 "
                    f"Sharpe {winner['sharpe']:.2f} 달성 — 이게 우리가 원하는 수준",
                    importance=0.9,
                )
            for loser in losers:
                if loser["sharpe"] < 0.3:
                    ceo_memory.remember_warning(
                        f"{loser['team_id']} 팀 만성 저성과: "
                        f"Sharpe={loser['sharpe']:.2f}. Round {round_num}에도 기준 미달."
                    )

        logger.info(f"\n✅ Round {round_num} 완료 및 저장")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Competition 실패: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


# ─── Leaderboard Logger ───────────────────────────────────────────────────────

def log_leaderboard():
    """팀 순위 로그 출력 (매일 오전)."""
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("""
            SELECT team_name, wins, total_competitions,
                   ROUND(best_sharpe::numeric, 2) AS best_sharpe,
                   ROUND(best_cagr::numeric, 2) AS best_cagr
            FROM strategy_teams
            WHERE is_active = TRUE
            ORDER BY wins DESC, best_sharpe DESC
        """)
        rows = cur.fetchall()

        logger.info("\n📊 LEADERBOARD")
        logger.info("-" * 50)
        for i, r in enumerate(rows):
            wins = r["wins"] or 0
            total = r["total_competitions"] or 0
            win_rate = f"{wins}/{total}" if total > 0 else "0/0"
            logger.info(
                f"  {i+1}. {r['team_name']:<30} 승: {win_rate:<6} "
                f"최고 Sharpe: {r['best_sharpe'] or 'N/A':<8} "
                f"최고 CAGR: {r['best_cagr'] or 'N/A'}%"
            )
        logger.info("-" * 50)

        # Latest round
        cur.execute("""
            SELECT round_number, winner_team_id, winner_strategy,
                   ceo_praise, created_at
            FROM competition_rounds
            ORDER BY created_at DESC
            LIMIT 1
        """)
        latest = cur.fetchone()
        if latest:
            logger.info(f"\n🏆 최근 우승: Round {latest['round_number']} - "
                       f"{latest['winner_team_id']} ({latest['winner_strategy']})")
            logger.info(f"CEO: {latest['ceo_praise'][:200] if latest['ceo_praise'] else ''}")

    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
    finally:
        db.close()


# ─── Scheduler ───────────────────────────────────────────────────────────────

def main():
    logger.info("CEO Agent starting — QuantLab Capital")
    logger.info("Mission: 전략팀 경쟁 평가 및 승자 칭찬")

    # Startup: show current standings
    log_leaderboard()

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # Weekly competition: Friday 5pm KST (after KOSPI close + US pre-market)
    scheduler.add_job(
        run_competition,
        CronTrigger(day_of_week="fri", hour=17, minute=0, timezone="Asia/Seoul"),
        id="weekly_competition",
        name="Weekly Strategy Competition",
        misfire_grace_time=3600,
    )

    # Daily leaderboard log: 9am KST
    scheduler.add_job(
        log_leaderboard,
        CronTrigger(hour=9, minute=0, timezone="Asia/Seoul"),
        id="daily_leaderboard",
        name="Daily Leaderboard",
    )

    # Run competition on startup if last one was > 7 days ago
    scheduler.add_job(
        _maybe_run_startup_competition,
        "date",
        run_date=datetime.now().replace(second=0, microsecond=0).__class__(
            datetime.now().year,
            datetime.now().month,
            datetime.now().day,
            datetime.now().hour,
            datetime.now().minute + 1,
        ),
        id="startup_competition",
    )

    logger.info("Scheduler started. Competition: every Friday 17:00 KST")
    scheduler.start()


def _maybe_run_startup_competition():
    """시작 시 마지막 경쟁이 7일 이상 지났으면 즉시 실행."""
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("""
            SELECT created_at FROM competition_rounds
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row or (datetime.utcnow() - row["created_at"]).days >= 7:
            logger.info("Startup: triggering competition (>7 days since last round)")
            db.close()
            run_competition()
        else:
            logger.info(f"Startup: last competition was recent ({row['created_at'].date()}), skipping")
            db.close()
    except Exception as e:
        logger.error(f"Startup competition check failed: {e}")
        db.close()


if __name__ == "__main__":
    main()
