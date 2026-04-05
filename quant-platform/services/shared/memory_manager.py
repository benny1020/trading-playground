"""
MemoryManager — QuantLab Capital 에이전트 기억 시스템
======================================================
모든 에이전트가 공유하는 영구 기억 레이어.

에이전트는 매번 실행 시:
  1. 자신의 과거 기억을 DB에서 로드 (중요도순)
  2. 기억을 Claude 프롬프트에 컨텍스트로 주입
  3. 새로운 인사이트/결과를 기억으로 저장

이를 통해:
  - Strategy Lab: 이미 실패한 전략 반복 안 함
  - Agentic Trading: 과거 신호 정확도 파악해서 가중치 조정
  - CEO Agent: 누적 경쟁 패턴으로 진화하는 평가
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger("memory_manager")


class MemoryManager:
    def __init__(self, db_conn, agent_id: str):
        self.db = db_conn
        self.agent_id = agent_id

    # ─── 기억 저장 ────────────────────────────────────────────────────────────

    def remember(
        self,
        content: str,
        memory_type: str = "insight",
        context: dict = None,
        importance: float = 0.5,
    ):
        """새 기억 저장. 유사한 기억이 있으면 importance만 업데이트."""
        cur = self.db.cursor()
        try:
            # 동일 content 있으면 중복 저장 안 함 (importance 갱신)
            cur.execute("""
                SELECT id FROM agent_memory
                WHERE agent_id = %s AND content = %s
                LIMIT 1
            """, (self.agent_id, content))
            existing = cur.fetchone()

            if existing:
                cur.execute("""
                    UPDATE agent_memory
                    SET importance  = GREATEST(importance, %s),
                        times_used  = times_used + 1,
                        updated_at  = NOW()
                    WHERE id = %s
                """, (importance, existing[0]))
            else:
                cur.execute("""
                    INSERT INTO agent_memory
                        (agent_id, memory_type, content, context, importance)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    self.agent_id,
                    memory_type,
                    content,
                    json.dumps(context or {}),
                    importance,
                ))
            self.db.commit()
        except Exception as e:
            logger.error(f"[Memory] save failed: {e}")
            self.db.rollback()

    def remember_strategy_result(
        self,
        strategy_name: str,
        strategy_type: str,
        market: str,
        sharpe: float,
        cagr: float,
        mdd: float,
        source: str = "",
    ):
        """전략 백테스트 결과를 기억에 저장."""
        is_good = sharpe >= 0.8 and cagr >= 0.05 and abs(mdd) <= 0.30
        verdict = "GOOD" if is_good else ("OK" if sharpe >= 0.5 else "BAD")

        content = (
            f"[{verdict}] {strategy_type} 전략 '{strategy_name}' on {market}: "
            f"Sharpe={sharpe:.2f}, CAGR={cagr*100:.1f}%, MDD={mdd*100:.1f}%"
        )
        if source:
            content += f" (출처: {source[:80]})"

        importance = 0.9 if is_good else (0.7 if verdict == "OK" else 0.5)

        self.remember(
            content=content,
            memory_type="performance",
            context={
                "strategy_name": strategy_name,
                "strategy_type": strategy_type,
                "market": market,
                "sharpe": sharpe,
                "cagr": cagr,
                "mdd": mdd,
                "verdict": verdict,
            },
            importance=importance,
        )

    def remember_insight(self, insight: str, importance: float = 0.7):
        """자유 형식 인사이트 저장."""
        self.remember(insight, memory_type="insight", importance=importance)

    def remember_warning(self, warning: str):
        """경고/실패 패턴 저장 (높은 중요도)."""
        self.remember(warning, memory_type="warning", importance=0.8)

    # ─── 기억 조회 ────────────────────────────────────────────────────────────

    def recall(self, limit: int = 15, memory_type: str = None) -> list[dict]:
        """중요도순으로 최근 기억 조회."""
        cur = self.db.cursor()
        try:
            if memory_type:
                cur.execute("""
                    SELECT memory_type, content, context, importance, created_at
                    FROM agent_memory
                    WHERE agent_id = %s AND memory_type = %s
                    ORDER BY importance DESC, updated_at DESC
                    LIMIT %s
                """, (self.agent_id, memory_type, limit))
            else:
                cur.execute("""
                    SELECT memory_type, content, context, importance, created_at
                    FROM agent_memory
                    WHERE agent_id = %s
                    ORDER BY importance DESC, updated_at DESC
                    LIMIT %s
                """, (self.agent_id, limit))

            rows = cur.fetchall()
            return [
                {
                    "type": r[0],
                    "content": r[1],
                    "context": r[2] or {},
                    "importance": r[3],
                    "date": str(r[4].date()) if r[4] else "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"[Memory] recall failed: {e}")
            return []

    def build_context_prompt(self, limit: int = 12) -> str:
        """
        Claude 프롬프트에 주입할 기억 컨텍스트 문자열 생성.
        에이전트가 프롬프트 앞부분에 이 내용을 포함시켜 과거를 기억하게 함.
        """
        memories = self.recall(limit=limit)
        if not memories:
            return ""

        lines = ["=== 과거 경험 및 학습된 규칙 ==="]
        for m in memories:
            icon = {"insight": "💡", "rule": "📌", "warning": "⚠️", "performance": "📊"}.get(m["type"], "•")
            lines.append(f"{icon} [{m['date']}] {m['content']}")
        lines.append("=" * 40)

        return "\n".join(lines)

    def has_tried_strategy_type(self, strategy_type: str, market: str) -> Optional[dict]:
        """이 전략 타입을 해당 시장에서 이미 시도했는지 확인. 결과 반환."""
        cur = self.db.cursor()
        try:
            cur.execute("""
                SELECT context FROM agent_memory
                WHERE agent_id = %s
                  AND memory_type = 'performance'
                  AND context->>'strategy_type' = %s
                  AND context->>'market' = %s
                ORDER BY importance DESC
                LIMIT 1
            """, (self.agent_id, strategy_type, market))
            row = cur.fetchone()
            if row:
                return row[0]
        except Exception:
            pass
        return None

    def get_bad_strategy_types(self) -> set[str]:
        """실패한 전략 타입 집합 반환 (반복 방지)."""
        cur = self.db.cursor()
        try:
            cur.execute("""
                SELECT DISTINCT context->>'strategy_type'
                FROM agent_memory
                WHERE agent_id = %s
                  AND memory_type = 'performance'
                  AND context->>'verdict' = 'BAD'
            """, (self.agent_id,))
            return {r[0] for r in cur.fetchall() if r[0]}
        except Exception:
            return set()


# ─── Trade Journal (Agentic Trading 전용) ───────────────────────────────��─────

class TradeJournal:
    def __init__(self, db_conn, agent_id: str = "agentic_trading"):
        self.db = db_conn
        self.agent_id = agent_id

    def log_signal(
        self,
        market: str,
        signal_type: str,
        confidence: float,
        entry_price: float,
        agent_breakdown: list,
        signal_date: date = None,
    ) -> int:
        """새 매매 신호를 일지에 기록. trade_id 반환."""
        cur = self.db.cursor()
        try:
            cur.execute("""
                INSERT INTO trade_journal
                    (agent_id, market, signal_date, signal_type,
                     confidence, entry_price, agent_breakdown)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                self.agent_id,
                market,
                signal_date or date.today(),
                signal_type,
                confidence,
                entry_price,
                json.dumps(agent_breakdown),
            ))
            self.db.commit()
            return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"[TradeJournal] log_signal failed: {e}")
            self.db.rollback()
            return -1

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_date: date = None,
    ):
        """매매 결과 기록 (exit price → return 계산)."""
        cur = self.db.cursor()
        try:
            cur.execute(
                "SELECT signal_type, entry_price FROM trade_journal WHERE id = %s",
                (trade_id,)
            )
            row = cur.fetchone()
            if not row:
                return

            signal_type, entry_price = row
            if entry_price and entry_price > 0:
                ret = (exit_price - entry_price) / entry_price
                if signal_type == "SELL":
                    ret = -ret
                was_correct = ret > 0 if signal_type != "HOLD" else True
            else:
                ret = 0
                was_correct = None

            cur.execute("""
                UPDATE trade_journal
                SET exit_price  = %s,
                    exit_date   = %s,
                    return_pct  = %s,
                    was_correct = %s
                WHERE id = %s
            """, (exit_price, exit_date or date.today(), ret * 100, was_correct, trade_id))
            self.db.commit()
        except Exception as e:
            logger.error(f"[TradeJournal] close_trade failed: {e}")
            self.db.rollback()

    def get_accuracy_report(self, market: str, days: int = 60) -> dict:
        """
        최근 N일간 신호 정확도 분석.
        에이전트가 자신의 과거 성과를 파악하는 데 사용.
        """
        cur = self.db.cursor()
        try:
            since = date.today() - timedelta(days=days)
            cur.execute("""
                SELECT
                    signal_type,
                    COUNT(*)                                       AS total,
                    SUM(CASE WHEN was_correct THEN 1 ELSE 0 END)  AS correct,
                    AVG(return_pct)                                AS avg_return,
                    MIN(return_pct)                                AS worst,
                    MAX(return_pct)                                AS best
                FROM trade_journal
                WHERE agent_id = %s
                  AND market   = %s
                  AND signal_date >= %s
                  AND was_correct IS NOT NULL
                GROUP BY signal_type
            """, (self.agent_id, market, since))

            rows = cur.fetchall()
            report = {}
            for r in rows:
                total = r[1] or 1
                report[r[0]] = {
                    "total": total,
                    "correct": r[2] or 0,
                    "accuracy": round((r[2] or 0) / total * 100, 1),
                    "avg_return_pct": round(r[3] or 0, 2),
                    "worst_pct": round(r[4] or 0, 2),
                    "best_pct": round(r[5] or 0, 2),
                }
            return report
        except Exception as e:
            logger.error(f"[TradeJournal] accuracy_report failed: {e}")
            return {}

    def get_open_trades(self, market: str) -> list:
        """아직 결과가 기록되지 않은 오픈 포지션 조회."""
        cur = self.db.cursor()
        try:
            cur.execute("""
                SELECT id, signal_date, signal_type, entry_price, confidence
                FROM trade_journal
                WHERE agent_id = %s
                  AND market   = %s
                  AND exit_date IS NULL
                  AND signal_type != 'HOLD'
                ORDER BY signal_date DESC
                LIMIT 20
            """, (self.agent_id, market))
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "signal_date": str(r[1]),
                    "signal_type": r[2],
                    "entry_price": r[3],
                    "confidence": r[4],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"[TradeJournal] get_open_trades failed: {e}")
            return []

    def build_performance_summary(self, market: str) -> str:
        """Claude 프롬프트에 주입할 과거 성과 요약."""
        report = self.get_accuracy_report(market)
        open_trades = self.get_open_trades(market)

        lines = [f"=== {market} 매매 히스토리 (최근 60일) ==="]

        if report:
            for signal_type, stats in report.items():
                lines.append(
                    f"  {signal_type}: {stats['correct']}/{stats['total']}건 적중 "
                    f"({stats['accuracy']}%) | 평균수익: {stats['avg_return_pct']:+.2f}% "
                    f"| 범위: {stats['worst_pct']:+.1f}% ~ {stats['best_pct']:+.1f}%"
                )
        else:
            lines.append("  (매매 기록 없음)")

        if open_trades:
            lines.append(f"\n오픈 포지션 {len(open_trades)}건:")
            for t in open_trades[:5]:
                lines.append(
                    f"  {t['signal_date']} {t['signal_type']} @ {t['entry_price']}"
                )

        lines.append("=" * 40)
        return "\n".join(lines)
