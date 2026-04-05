"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Team {
  team_id: string;
  team_name: string;
  description: string;
  team_type: string;
  wins: number;
  total_competitions: number;
  best_sharpe: number | null;
  best_cagr: number | null;
}

interface Competition {
  round_number: number;
  test_start_date: string;
  test_end_date: string;
  results: Array<{
    team_id: string;
    strategy_name: string;
    sharpe: number;
    cagr: number;
    mdd: number;
    composite_score: number;
  }>;
  winner_team_id: string;
  winner_strategy: string;
  ceo_praise: string;
  ceo_notes: string;
  created_at: string;
}

interface TradeRecord {
  id: number;
  agent_id: string;
  market: string;
  signal_date: string;
  signal_type: string;
  confidence: number;
  entry_price: number;
  exit_price: number | null;
  return_pct: number | null;
  was_correct: boolean | null;
  agent_breakdown: any[];
}

interface AgenticSignal {
  id: number;
  market: string;
  final_signal: string;
  confidence: number;
  position_size: number;
  agent_signals: any[];
  synthesis: string;
  created_at: string;
}

interface Memory {
  id: number;
  agent_id: string;
  memory_type: string;
  content: string;
  importance: number;
  times_used: number;
  created_at: string;
}

// ─── Helper components ────────────────────────────────────────────────────────

const SignalBadge = ({ signal }: { signal: string }) => {
  const colors: Record<string, string> = {
    BUY: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    OVERWEIGHT: "bg-green-500/20 text-green-400 border border-green-500/30",
    HOLD: "bg-zinc-500/20 text-zinc-400 border border-zinc-500/30",
    UNDERWEIGHT: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
    SELL: "bg-red-500/20 text-red-400 border border-red-500/30",
    BULLISH: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    BEARISH: "bg-red-500/20 text-red-400 border border-red-500/30",
    NEUTRAL: "bg-zinc-500/20 text-zinc-400 border border-zinc-500/30",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold ${colors[signal] ?? "bg-zinc-700 text-zinc-300"}`}>
      {signal}
    </span>
  );
};

const MemoryIcon = ({ type }: { type: string }) => {
  const icons: Record<string, string> = {
    insight: "💡",
    rule: "📌",
    warning: "⚠️",
    performance: "📊",
  };
  return <span>{icons[type] ?? "•"}</span>;
};

const pct = (v: number | null, decimals = 1) =>
  v != null ? `${(v * 100).toFixed(decimals)}%` : "—";
const num = (v: number | null, d = 2) =>
  v != null ? v.toFixed(d) : "—";

// ─── Tabs ─────────────────────────────────────────────────────────────────────

type Tab = "overview" | "competition" | "signals" | "journal" | "memory";

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: "overview", label: "회사 현황", icon: "🏢" },
  { id: "competition", label: "CEO 경쟁", icon: "🏆" },
  { id: "signals", label: "매매 신호", icon: "📡" },
  { id: "journal", label: "매매 일지", icon: "📒" },
  { id: "memory", label: "에이전트 기억", icon: "🧠" },
];

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CompanyPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [teams, setTeams] = useState<Team[]>([]);
  const [competition, setCompetition] = useState<Competition | null>(null);
  const [competitionHistory, setCompetitionHistory] = useState<Competition[]>([]);
  const [signals, setSignals] = useState<AgenticSignal[]>([]);
  const [journal, setJournal] = useState<TradeRecord[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [marketFilter, setMarketFilter] = useState<string>("");
  const [agentFilter, setAgentFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.company.leaderboard(),
      api.company.latestCompetition(),
      api.company.competitionHistory(8),
    ]).then(([lb, comp, hist]) => {
      setTeams(lb.data);
      setCompetition(comp.data);
      setCompetitionHistory(hist.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (tab === "signals") {
      api.company.agenticSignals(marketFilter || undefined, 40).then(r => setSignals(r.data));
    }
    if (tab === "journal") {
      api.company.tradeJournal(marketFilter || undefined, 60).then(r => setJournal(r.data));
    }
    if (tab === "memory") {
      api.company.agentMemory(agentFilter || undefined).then(r => setMemories(r.data));
    }
  }, [tab, marketFilter, agentFilter]);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-2xl">🏦</span>
          <h1 className="text-2xl font-bold tracking-tight">QuantLab Capital</h1>
          <span className="text-xs text-zinc-500 border border-zinc-700 rounded px-2 py-0.5">AI 퀀트 자산운용사</span>
        </div>
        <p className="text-zinc-400 text-sm ml-9">여러 전략팀이 경쟁하며 수익을 낸다.</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-zinc-800 pb-0">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              tab === t.id
                ? "bg-zinc-800 text-white border-t border-l border-r border-zinc-700"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="text-center text-zinc-500 py-20">로딩 중...</div>
      )}

      {/* ── Overview ─────────────────────────────────────────────────────── */}
      {!loading && tab === "overview" && (
        <div className="space-y-6">
          {/* Team Leaderboard */}
          <section>
            <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
              <span>🥇</span> 전략팀 순위
            </h2>
            <div className="grid gap-3">
              {teams.map((team, i) => (
                <div key={team.team_id}
                  className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center gap-4">
                  <div className={`text-2xl font-black w-8 text-center ${
                    i === 0 ? "text-yellow-400" : i === 1 ? "text-zinc-400" : i === 2 ? "text-orange-600" : "text-zinc-600"
                  }`}>
                    {i + 1}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{team.team_name}</span>
                      <span className="text-xs text-zinc-500 border border-zinc-700 rounded px-1.5 py-0.5">
                        {team.team_type}
                      </span>
                    </div>
                    <p className="text-zinc-500 text-xs mt-0.5">{team.description}</p>
                  </div>
                  <div className="flex gap-6 text-right">
                    <div>
                      <div className="text-xs text-zinc-500">우승</div>
                      <div className="font-bold text-yellow-400">
                        {team.wins}/{team.total_competitions}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-zinc-500">최고 Sharpe</div>
                      <div className="font-bold text-emerald-400">{num(team.best_sharpe)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-zinc-500">최고 CAGR</div>
                      <div className="font-bold text-blue-400">
                        {team.best_cagr != null ? `${(team.best_cagr * 100).toFixed(1)}%` : "—"}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Latest CEO Message */}
          {competition && (
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-zinc-900 border border-yellow-500/30 rounded-xl p-5">
                <div className="text-xs text-yellow-500 font-bold mb-2">🏆 CEO 칭찬 — Round {competition.round_number}</div>
                <p className="text-zinc-200 text-sm leading-relaxed">{competition.ceo_praise}</p>
                <div className="mt-3 text-xs text-zinc-500">
                  우승팀: <span className="text-yellow-400 font-semibold">{competition.winner_team_id}</span>
                  {" · "}{competition.winner_strategy}
                </div>
              </div>
              <div className="bg-zinc-900 border border-red-500/30 rounded-xl p-5">
                <div className="text-xs text-red-400 font-bold mb-2">🔥 CEO 압박</div>
                <p className="text-zinc-300 text-sm leading-relaxed">{competition.ceo_notes}</p>
              </div>
            </section>
          )}
        </div>
      )}

      {/* ── Competition History ───────────────────────────────────────────── */}
      {!loading && tab === "competition" && (
        <div className="space-y-4">
          {competitionHistory.length === 0 && (
            <p className="text-zinc-500 text-center py-16">경쟁 기록이 없습니다. CEO가 아직 평가를 실행하지 않았습니다.</p>
          )}
          {competitionHistory.map(c => (
            <div key={c.round_number} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
              <div className="px-5 py-3 bg-zinc-800/60 flex items-center justify-between">
                <span className="font-bold">Round {c.round_number}</span>
                <span className="text-xs text-zinc-400">{c.test_start_date} ~ {c.test_end_date}</span>
                <span className="text-yellow-400 text-sm font-semibold">🏆 {c.winner_team_id}</span>
              </div>
              {/* Rankings table */}
              {Array.isArray(c.results) && c.results.length > 0 && (
                <div className="px-5 py-3">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                        <th className="text-left pb-2">순위</th>
                        <th className="text-left pb-2">팀</th>
                        <th className="text-left pb-2">전략</th>
                        <th className="text-right pb-2">Sharpe</th>
                        <th className="text-right pb-2">CAGR</th>
                        <th className="text-right pb-2">MDD</th>
                        <th className="text-right pb-2">점수</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.results.map((r, i) => (
                        <tr key={r.team_id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                          <td className={`py-2 font-bold ${i === 0 ? "text-yellow-400" : "text-zinc-500"}`}>
                            {i + 1}
                          </td>
                          <td className="py-2 font-medium">{r.team_id}</td>
                          <td className="py-2 text-zinc-400 text-xs">{r.strategy_name?.slice(0, 30)}</td>
                          <td className={`py-2 text-right font-mono ${r.sharpe >= 1 ? "text-emerald-400" : r.sharpe >= 0.5 ? "text-yellow-400" : "text-red-400"}`}>
                            {r.sharpe?.toFixed(2)}
                          </td>
                          <td className="py-2 text-right font-mono text-blue-400">
                            {r.cagr?.toFixed(1)}%
                          </td>
                          <td className="py-2 text-right font-mono text-orange-400">
                            {r.mdd?.toFixed(1)}%
                          </td>
                          <td className="py-2 text-right font-mono text-zinc-300">
                            {r.composite_score?.toFixed(3)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {c.ceo_praise && (
                <div className="px-5 py-3 border-t border-zinc-800 grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-yellow-500 mb-1">💬 칭찬</div>
                    <p className="text-zinc-300 text-xs leading-relaxed">{c.ceo_praise}</p>
                  </div>
                  <div>
                    <div className="text-xs text-red-400 mb-1">🔥 압박</div>
                    <p className="text-zinc-400 text-xs leading-relaxed">{c.ceo_notes}</p>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Agentic Signals ───────────────────────────────────────────────── */}
      {!loading && tab === "signals" && (
        <div className="space-y-4">
          <div className="flex gap-2">
            {["", "KOSPI", "KOSDAQ", "US"].map(m => (
              <button key={m}
                onClick={() => setMarketFilter(m)}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  marketFilter === m
                    ? "bg-blue-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                {m || "전체"}
              </button>
            ))}
          </div>
          <div className="space-y-3">
            {signals.map(s => (
              <div key={s.id}
                className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-zinc-400 font-mono text-xs border border-zinc-700 rounded px-2 py-0.5">
                      {s.market}
                    </span>
                    <SignalBadge signal={s.final_signal} />
                    <span className="text-xs text-zinc-500">
                      확신도 {(s.confidence * 100).toFixed(0)}% · 포지션 {(s.position_size * 100).toFixed(0)}%
                    </span>
                  </div>
                  <span className="text-xs text-zinc-600">
                    {new Date(s.created_at).toLocaleString("ko-KR")}
                  </span>
                </div>
                {/* Agent breakdown */}
                {Array.isArray(s.agent_signals) && s.agent_signals.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {s.agent_signals.map((a: any, i: number) => (
                      <div key={i} className="flex items-center gap-1.5 bg-zinc-800 rounded px-2 py-1 text-xs">
                        <span className="text-zinc-400">{a.analyst}</span>
                        <SignalBadge signal={a.signal} />
                        <span className="text-zinc-500">{((a.confidence || 0) * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                )}
                {s.synthesis && (
                  <p className="text-zinc-400 text-xs leading-relaxed border-t border-zinc-800 pt-2 mt-2">
                    {s.synthesis.slice(0, 300)}{s.synthesis.length > 300 ? "…" : ""}
                  </p>
                )}
              </div>
            ))}
            {signals.length === 0 && (
              <p className="text-zinc-500 text-center py-16">신호 없음 — Agentic Trading이 아직 실행되지 않았습니다.</p>
            )}
          </div>
        </div>
      )}

      {/* ── Trade Journal ─────────────────────────────────────────────────── */}
      {!loading && tab === "journal" && (
        <div className="space-y-4">
          <div className="flex gap-2">
            {["", "KOSPI", "KOSDAQ", "US"].map(m => (
              <button key={m}
                onClick={() => setMarketFilter(m)}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  marketFilter === m
                    ? "bg-blue-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                {m || "전체"}
              </button>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border border-zinc-800 rounded-xl overflow-hidden">
              <thead className="bg-zinc-800/60">
                <tr className="text-zinc-400 text-xs">
                  <th className="text-left p-3">날짜</th>
                  <th className="text-left p-3">에이전트</th>
                  <th className="text-left p-3">시장</th>
                  <th className="text-left p-3">신호</th>
                  <th className="text-right p-3">확신도</th>
                  <th className="text-right p-3">진입가</th>
                  <th className="text-right p-3">청산가</th>
                  <th className="text-right p-3">수익률</th>
                  <th className="text-center p-3">적중</th>
                </tr>
              </thead>
              <tbody>
                {journal.map(t => (
                  <tr key={t.id} className="border-t border-zinc-800/50 hover:bg-zinc-800/20">
                    <td className="p-3 text-zinc-400 font-mono text-xs">{t.signal_date}</td>
                    <td className="p-3 text-xs text-zinc-300">{t.agent_id}</td>
                    <td className="p-3">
                      <span className="text-xs border border-zinc-700 rounded px-1.5 py-0.5">{t.market}</span>
                    </td>
                    <td className="p-3"><SignalBadge signal={t.signal_type} /></td>
                    <td className="p-3 text-right text-zinc-400 font-mono text-xs">
                      {t.confidence ? `${(t.confidence * 100).toFixed(0)}%` : "—"}
                    </td>
                    <td className="p-3 text-right font-mono text-xs text-zinc-300">
                      {t.entry_price ? t.entry_price.toLocaleString() : "—"}
                    </td>
                    <td className="p-3 text-right font-mono text-xs text-zinc-300">
                      {t.exit_price ? t.exit_price.toLocaleString() : <span className="text-zinc-600">미청산</span>}
                    </td>
                    <td className={`p-3 text-right font-mono font-bold text-xs ${
                      t.return_pct == null ? "text-zinc-600"
                        : t.return_pct > 0 ? "text-emerald-400"
                        : "text-red-400"
                    }`}>
                      {t.return_pct != null ? `${t.return_pct > 0 ? "+" : ""}${t.return_pct.toFixed(2)}%` : "—"}
                    </td>
                    <td className="p-3 text-center text-lg">
                      {t.was_correct == null ? "⏳" : t.was_correct ? "✅" : "❌"}
                    </td>
                  </tr>
                ))}
                {journal.length === 0 && (
                  <tr>
                    <td colSpan={9} className="text-center text-zinc-600 py-12">매매 기록 없음</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Agent Memory ──────────────────────────────────────────────────── */}
      {!loading && tab === "memory" && (
        <div className="space-y-4">
          <div className="flex gap-2 flex-wrap">
            {["", "strategy_lab", "agentic_kospi", "agentic_kosdaq", "agentic_us", "ceo_agent"].map(a => (
              <button key={a}
                onClick={() => setAgentFilter(a)}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  agentFilter === a
                    ? "bg-purple-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                {a || "전체"}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            {memories.map(m => (
              <div key={m.id}
                className={`bg-zinc-900 rounded-xl px-4 py-3 flex items-start gap-3 border ${
                  m.memory_type === "warning"
                    ? "border-red-500/30"
                    : m.memory_type === "performance"
                    ? "border-blue-500/30"
                    : "border-zinc-800"
                }`}>
                <MemoryIcon type={m.memory_type} />
                <div className="flex-1 min-w-0">
                  <p className="text-zinc-200 text-sm">{m.content}</p>
                  <div className="flex gap-3 mt-1 text-xs text-zinc-600">
                    <span>{m.agent_id}</span>
                    <span>중요도 {(m.importance * 100).toFixed(0)}%</span>
                    <span>참조 {m.times_used}회</span>
                    <span>{new Date(m.created_at).toLocaleDateString("ko-KR")}</span>
                  </div>
                </div>
                <div className="shrink-0">
                  <div className="w-16 bg-zinc-800 rounded-full h-1.5">
                    <div
                      className="bg-purple-500 h-1.5 rounded-full"
                      style={{ width: `${(m.importance * 100).toFixed(0)}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
            {memories.length === 0 && (
              <p className="text-zinc-500 text-center py-16">
                기억 없음 — 에이전트들이 실행되면 여기에 학습된 인사이트가 쌓입니다.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
