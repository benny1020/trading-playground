"""
CEO Agent — QuantLab Capital
============================
CEO는 모든 전략팀의 성과를 주기적으로 평가하고, 승자를 칭찬하며,
팀 간 경쟁을 통해 최고의 전략을 선별한다.

역할:
- 매주 금요일 장 마감 후 Competition Round 실행
- 모든 활성 전략팀의 백테스트 결과를 수집
- 복합 점수 (Sharpe×0.4 + CAGR×0.3 - |MDD|×0.3) 로 랭킹
- 승자 팀에게 Claude API로 CEO 칭찬 메시지 생성
- 저성과 팀에게 개선 권고
- competition_rounds DB에 결과 저장
"""

import os
import json
import logging
import uuid
from datetime import datetime, date, timedelta
from typing import Optional

import anthropic
import psycopg2
import psycopg2.extras
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

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

def generate_ceo_message(
    winner: dict,
    all_results: list,
    round_num: int,
) -> tuple[str, str]:
    """
    Claude API를 사용해 CEO 칭찬 메시지와 전체 평가 노트 생성.
    Returns (praise_for_winner, overall_notes)
    """
    if not ANTHROPIC_API_KEY:
        praise = (
            f"🏆 축하합니다! {winner['team_id']} 팀이 Round {round_num} 우승! "
            f"Sharpe {winner['sharpe']:.2f}, CAGR {winner['cagr']:.1f}%의 뛰어난 성과입니다."
        )
        notes = "CEO 평가: ANTHROPIC_API_KEY 미설정으로 자동 평가 불가"
        return praise, notes

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    rankings_text = "\n".join([
        f"  {i+1}위. {r['team_id']} - {r['strategy_name']} "
        f"(Sharpe: {r['sharpe']:.2f}, CAGR: {r['cagr']:.1f}%, MDD: {r['mdd']:.1f}%, 점수: {r['composite_score']:.3f})"
        for i, r in enumerate(all_results)
    ])

    prompt = f"""당신은 AI 퀀트 자산운용사 "QuantLab Capital"의 CEO입니다.
방금 전략팀 간 백테스팅 Competition Round {round_num}이 완료되었습니다.

=== 경쟁 결과 ===
{rankings_text}

=== 우승팀 ===
팀: {winner['team_id']}
전략: {winner['strategy_name']}
Sharpe: {winner['sharpe']:.2f}
CAGR: {winner['cagr']:.1f}%
MDD: {winner['mdd']:.1f}%
테스트 기간: {winner['test_period']}

다음 두 가지를 작성하세요:

[CEO 칭찬] (2-3문장, 한국어, 열정적이고 구체적으로. 우승팀의 수치를 언급하며 칭찬)

[전체 평가] (3-4문장, 한국어. 전체 경쟁 총평, 하위 팀에 대한 개선 방향, 다음 라운드 기대사항)

각각 "[CEO 칭찬]", "[전체 평가]" 헤더로 구분해 작성하세요."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else ""

        praise = ""
        notes = ""
        if "[CEO 칭찬]" in text:
            parts = text.split("[전체 평가]")
            praise = parts[0].replace("[CEO 칭찬]", "").strip()
            notes = parts[1].strip() if len(parts) > 1 else ""
        else:
            praise = text[:300]
            notes = text[300:]

        return praise, notes

    except Exception as e:
        logger.error(f"Claude API error in CEO message: {e}")
        return (
            f"🏆 Round {round_num} 우승: {winner['team_id']} 팀! "
            f"Sharpe {winner['sharpe']:.2f}, CAGR {winner['cagr']:.1f}%!",
            f"CEO 평가 생성 실패: {e}",
        )


# ─── Competition Runner ───────────────────────────────────────────────────────

def run_competition():
    """
    전략팀 간 경쟁 평가 실행.
    - 최근 90일 백테스트 결과 수집
    - 복합 점수로 랭킹
    - CEO 메시지 생성
    - DB 저장
    """
    logger.info("=" * 60)
    logger.info("CEO COMPETITION ROUND STARTING")
    logger.info("=" * 60)

    db = get_db()
    try:
        teams = get_all_teams(db)
        since_date = date.today() - timedelta(days=90)
        round_num = get_next_round_number(db)

        logger.info(f"Round {round_num}: Evaluating {len(teams)} teams (since {since_date})")

        results = []
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
                logger.warning(f"  {team_id}: no completed backtests found in window")

        if not results:
            logger.warning("No team results available — competition skipped")
            return

        # Sort by composite score
        results.sort(key=lambda x: x["composite_score"], reverse=True)

        winner = results[0]
        logger.info(f"\n🏆 WINNER: {winner['team_id']} — {winner['strategy_name']}")

        praise, notes = generate_ceo_message(winner, results, round_num)
        logger.info(f"\nCEO 칭찬:\n{praise}")
        logger.info(f"\nCEO 총평:\n{notes}")

        # Save to DB
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
            notes,
        ))

        # Update team win/competition counts
        for r in results:
            is_winner = r["team_id"] == winner["team_id"]
            cur.execute("""
                UPDATE strategy_teams
                SET total_competitions = total_competitions + 1,
                    wins = wins + %s,
                    best_sharpe = GREATEST(COALESCE(best_sharpe, -999), %s),
                    best_cagr   = GREATEST(COALESCE(best_cagr, -999), %s)
                WHERE team_id = %s
            """, (
                1 if is_winner else 0,
                r["sharpe"],
                r["cagr"],
                r["team_id"],
            ))

        db.commit()
        logger.info(f"\n✅ Round {round_num} saved to DB")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Competition failed: {e}", exc_info=True)
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
