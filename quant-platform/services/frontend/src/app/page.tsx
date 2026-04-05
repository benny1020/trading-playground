"use client";

import { useEffect, useState } from "react";
import { api, BacktestRun, Strategy } from "@/lib/api";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Team {
  team_id: string;
  team_name: string;
  team_type: string;
  wins: number;
  total_competitions: number;
  best_sharpe: number | null;
  best_cagr: number | null;
}

interface Competition {
  round_number: number;
  winner_team_id: string;
  winner_strategy: string;
  ceo_praise: string;
  ceo_notes: string;
  results: Array<{ team_id: string; sharpe: number; cagr: number; mdd: number; composite_score: number }>;
  created_at: string;
}

interface AgenticSignal {
  market: string;
  final_signal: string;
  confidence: number;
  position_size: number;
  synthesis: string;
  created_at: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const SignalDot = ({ signal }: { signal: string }) => {
  const colors: Record<string, string> = {
    BUY: "bg-emerald-500", OVERWEIGHT: "bg-green-400",
    HOLD: "bg-zinc-500", UNDERWEIGHT: "bg-orange-400", SELL: "bg-red-500",
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[signal] ?? "bg-zinc-500"}`} />;
};

const SignalPill = ({ signal }: { signal: string }) => {
  const styles: Record<string, string> = {
    BUY: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    OVERWEIGHT: "bg-green-500/15 text-green-400 border-green-500/30",
    HOLD: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
    UNDERWEIGHT: "bg-orange-500/15 text-orange-400 border-orange-500/30",
    SELL: "bg-red-500/15 text-red-400 border-red-500/30",
  };
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded border ${styles[signal] ?? "bg-zinc-700 text-zinc-300 border-zinc-600"}`}>
      {signal}
    </span>
  );
};

const typeColor: Record<string, string> = {
  quant: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  agentic: "text-purple-400 bg-purple-500/10 border-purple-500/20",
  hybrid: "text-teal-400 bg-teal-500/10 border-teal-500/20",
};

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [competition, setCompetition] = useState<Competition | null>(null);
  const [signals, setSignals] = useState<AgenticSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [discoveryRunning, setDiscoveryRunning] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/company/leaderboard`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/backtests/?limit=8`).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/company/competition/latest`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/agentic-signals?limit=6`).then(r => r.json()).catch(() => []),
    ]).then(([t, bt, c, s]) => {
      setTeams(Array.isArray(t) ? t : []);
      setBacktests(Array.isArray(bt) ? bt : []);
      setCompetition(c);
      setSignals(Array.isArray(s) ? s : []);
      setLoading(false);
    });
  }, []);

  const runDiscovery = async () => {
    setDiscoveryRunning(true);
    try {
      await api.research.triggerStrategyDiscovery();
    } finally {
      setTimeout(() => setDiscoveryRunning(false), 3000);
    }
  };

  const completedBt = backtests.filter(b => b.status === "completed");
  const avgSharpe = completedBt.length
    ? (completedBt.reduce((s, b) => s + (b.results?.sharpe_ratio ?? 0), 0) / completedBt.length).toFixed(2)
    : "—";

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* ── Top Nav ──────────────────────────────────────────────────────── */}
      <header className="border-b border-zinc-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl">🏦</span>
          <span className="font-bold text-lg tracking-tight">QuantLab Capital</span>
          <span className="text-xs text-zinc-500 border border-zinc-700 rounded px-2 py-0.5">AI 퀀트 자산운용사</span>
        </div>
        <nav className="flex items-center gap-1 text-sm">
          {[
            { href: "/", label: "대시보드" },
            { href: "/company", label: "🏢 회사현황" },
            { href: "/portfolio", label: "📊 포트폴리오" },
            { href: "/strategies", label: "전략" },
            { href: "/backtests", label: "백테스트" },
            { href: "/research", label: "리서치" },
          ].map(n => (
            <Link key={n.href} href={n.href}
              className="px-3 py-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors">
              {n.label}
            </Link>
          ))}
        </nav>
        <button
          onClick={runDiscovery}
          disabled={discoveryRunning}
          className="flex items-center gap-2 px-4 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          {discoveryRunning ? "⏳ 탐색 중..." : "⚡ 전략 자동 발굴"}
        </button>
      </header>

      <main className="p-6 space-y-6 max-w-7xl mx-auto">

        {/* ── KPI Row ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "활성 전략팀", value: loading ? "—" : `${teams.length}팀`, icon: "👥", color: "text-blue-400" },
            { label: "평균 Sharpe", value: loading ? "—" : avgSharpe, icon: "📊", color: "text-emerald-400" },
            { label: "완료 백테스트", value: loading ? "—" : completedBt.length.toString(), icon: "✅", color: "text-yellow-400" },
            { label: "최근 CEO 라운드", value: loading ? "—" : competition ? `Round ${competition.round_number}` : "없음", icon: "🏆", color: "text-orange-400" },
          ].map(k => (
            <div key={k.label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
              <div className="text-2xl mb-1">{k.icon}</div>
              <div className={`text-2xl font-black ${k.color}`}>{k.value}</div>
              <div className="text-xs text-zinc-500 mt-0.5">{k.label}</div>
            </div>
          ))}
        </div>

        {/* ── Main Grid ────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Team Performance (left 2 cols) */}
          <div className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold flex items-center gap-2">🥇 전략팀 성과 순위</h2>
              <Link href="/company" className="text-xs text-zinc-500 hover:text-zinc-300">전체 보기 →</Link>
            </div>
            {loading ? (
              <div className="text-zinc-600 text-center py-8">로딩 중...</div>
            ) : teams.length === 0 ? (
              <div className="text-zinc-600 text-center py-8">팀 데이터 없음</div>
            ) : (
              <div className="space-y-2">
                {teams.map((team, i) => {
                  const winRate = team.total_competitions > 0
                    ? Math.round((team.wins / team.total_competitions) * 100)
                    : 0;
                  return (
                    <div key={team.team_id}
                      className="flex items-center gap-3 p-3 rounded-lg hover:bg-zinc-800/50 transition-colors">
                      <span className={`w-7 text-center font-black text-lg shrink-0 ${
                        i === 0 ? "text-yellow-400" : i === 1 ? "text-zinc-400" : i === 2 ? "text-orange-600" : "text-zinc-700"
                      }`}>{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Link href={`/teams/${team.team_id}`} className="font-medium text-sm truncate hover:text-blue-400 transition-colors">
                            {team.team_name}
                          </Link>
                          <span className={`text-xs px-1.5 py-0.5 rounded border ${typeColor[team.team_type] ?? "text-zinc-400 bg-zinc-800 border-zinc-700"}`}>
                            {team.team_type}
                          </span>
                        </div>
                        {/* Win rate bar */}
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex-1 bg-zinc-800 rounded-full h-1">
                            <div className="bg-yellow-500 h-1 rounded-full" style={{ width: `${winRate}%` }} />
                          </div>
                          <span className="text-xs text-zinc-500 w-10 text-right">{team.wins}승</span>
                        </div>
                      </div>
                      <div className="flex gap-4 shrink-0 text-right">
                        <div>
                          <div className="text-xs text-zinc-600">Sharpe</div>
                          <div className={`font-bold text-sm ${
                            (team.best_sharpe ?? 0) >= 1.0 ? "text-emerald-400"
                            : (team.best_sharpe ?? 0) >= 0.5 ? "text-yellow-400"
                            : "text-zinc-500"
                          }`}>
                            {team.best_sharpe?.toFixed(2) ?? "—"}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-zinc-600">CAGR</div>
                          <div className="font-bold text-sm text-blue-400">
                            {team.best_cagr != null ? `${(team.best_cagr * 100).toFixed(1)}%` : "—"}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Agentic Signals (right col) */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold flex items-center gap-2">📡 현재 시장 신호</h2>
              <Link href="/company?tab=signals" className="text-xs text-zinc-500 hover:text-zinc-300">더보기 →</Link>
            </div>
            {signals.length === 0 ? (
              <p className="text-zinc-600 text-sm text-center py-8">신호 없음</p>
            ) : (
              <div className="space-y-3">
                {signals.slice(0, 6).map((s, i) => (
                  <div key={i} className="border border-zinc-800 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-zinc-300">{s.market}</span>
                        <SignalPill signal={s.final_signal} />
                      </div>
                      <span className="text-xs text-zinc-600">
                        {new Date(s.created_at).toLocaleDateString("ko-KR")}
                      </span>
                    </div>
                    <div className="flex gap-3 text-xs text-zinc-500">
                      <span>확신도 <span className="text-zinc-300 font-medium">{(s.confidence * 100).toFixed(0)}%</span></span>
                      <span>포지션 <span className="text-zinc-300 font-medium">{(s.position_size * 100).toFixed(0)}%</span></span>
                    </div>
                    {s.synthesis && (
                      <p className="text-zinc-500 text-xs mt-1.5 leading-relaxed line-clamp-2">
                        {s.synthesis}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── CEO Message + Recent Backtests ───────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* CEO Latest */}
          {competition && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">🏆 CEO 최근 평가 — Round {competition.round_number}</h2>
                <Link href="/company" className="text-xs text-zinc-500 hover:text-zinc-300">경쟁 히스토리 →</Link>
              </div>
              {/* Top 3 results */}
              {Array.isArray(competition.results) && competition.results.length > 0 && (
                <div className="space-y-1">
                  {competition.results.slice(0, 3).map((r, i) => (
                    <div key={r.team_id} className="flex items-center gap-2 text-sm">
                      <span className={`w-5 font-black ${i === 0 ? "text-yellow-400" : "text-zinc-600"}`}>{i + 1}</span>
                      <span className="font-medium flex-1 truncate">{r.team_id}</span>
                      <span className="text-emerald-400 font-mono text-xs">S {r.sharpe?.toFixed(2)}</span>
                      <span className="text-blue-400 font-mono text-xs">{r.cagr?.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="border-t border-zinc-800 pt-3 space-y-2">
                {competition.ceo_praise && (
                  <div>
                    <div className="text-xs text-yellow-500 mb-1">💬 칭찬</div>
                    <p className="text-zinc-300 text-xs leading-relaxed">{competition.ceo_praise.slice(0, 200)}</p>
                  </div>
                )}
                {competition.ceo_notes && (
                  <div>
                    <div className="text-xs text-red-400 mb-1">🔥 압박</div>
                    <p className="text-zinc-400 text-xs leading-relaxed">{competition.ceo_notes.slice(0, 150)}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Recent Backtests */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold">⚡ 최근 백테스트</h2>
              <Link href="/backtests" className="text-xs text-zinc-500 hover:text-zinc-300">전체 보기 →</Link>
            </div>
            <div className="space-y-2">
              {backtests.slice(0, 6).map(bt => {
                const sharpe = bt.results?.sharpe_ratio ?? null;
                const cagr = bt.results?.cagr ?? null;
                return (
                  <Link key={bt.id} href={`/backtests/${bt.id}`}
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-zinc-800/50 transition-colors group">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      bt.status === "completed" ? "bg-emerald-500"
                      : bt.status === "running" ? "bg-yellow-500 animate-pulse"
                      : bt.status === "failed" ? "bg-red-500"
                      : "bg-zinc-600"
                    }`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate group-hover:text-white transition-colors">
                        {bt.name}
                      </div>
                      <div className="text-xs text-zinc-500">
                        {bt.market} · {new Date(bt.created_at).toLocaleDateString("ko-KR")}
                      </div>
                    </div>
                    {bt.status === "completed" && sharpe != null && (
                      <div className="flex gap-3 shrink-0 text-right">
                        <div>
                          <div className="text-xs text-zinc-600">Sharpe</div>
                          <div className={`text-xs font-bold ${sharpe >= 1 ? "text-emerald-400" : sharpe >= 0.5 ? "text-yellow-400" : "text-red-400"}`}>
                            {sharpe.toFixed(2)}
                          </div>
                        </div>
                        {cagr != null && (
                          <div>
                            <div className="text-xs text-zinc-600">CAGR</div>
                            <div className={`text-xs font-bold ${cagr > 0 ? "text-blue-400" : "text-red-400"}`}>
                              {(cagr * 100).toFixed(1)}%
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {bt.status !== "completed" && (
                      <span className="text-xs text-zinc-500 shrink-0 capitalize">{bt.status}</span>
                    )}
                  </Link>
                );
              })}
              {backtests.length === 0 && (
                <p className="text-zinc-600 text-sm text-center py-6">백테스트 없음</p>
              )}
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}
