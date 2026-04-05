"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, TeamMember, PortfolioPosition, RebalanceHistory } from "@/lib/api";

// ─── Role Config ──────────────────────────────────────────────────────────────
const ROLE_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  head:       { icon: "👑", color: "text-yellow-400 bg-yellow-400/10 border-yellow-400/30", label: "팀장" },
  quant:      { icon: "📐", color: "text-blue-400 bg-blue-400/10 border-blue-400/30", label: "퀀트" },
  pm:         { icon: "📊", color: "text-purple-400 bg-purple-400/10 border-purple-400/30", label: "PM" },
  risk:       { icon: "🛡️", color: "text-red-400 bg-red-400/10 border-red-400/30", label: "리스크" },
  researcher: { icon: "🔬", color: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30", label: "리서처" },
  data:       { icon: "🗄️", color: "text-cyan-400 bg-cyan-400/10 border-cyan-400/30", label: "데이터" },
  trader:     { icon: "⚡", color: "text-orange-400 bg-orange-400/10 border-orange-400/30", label: "트레이더" },
};

const TEAM_CONFIG: Record<string, { name: string; type: string; typeColor: string; emoji: string; mission: string }> = {
  quant_strategies: {
    name: "Quant Strategies Team",
    type: "QUANT",
    typeColor: "text-blue-400 bg-blue-400/10 border-blue-400/30",
    emoji: "📐",
    mission: "팩터 모델 기반 전체 유니버스 스캔 → 복합 팩터 점수 → inverse-vol 포트폴리오 구성 → 월별 자동 리밸런싱",
  },
  agentic_trading: {
    name: "Agentic Trading Team",
    type: "AGENTIC",
    typeColor: "text-purple-400 bg-purple-400/10 border-purple-400/30",
    emoji: "🤖",
    mission: "5개 전문 AI 에이전트 협업 분석 → Bull/Bear 토론 → Risk Panel 검토 → 최종 BUY/SELL/HOLD",
  },
  ai_hedge_fund: {
    name: "AI Hedge Fund Team",
    type: "HYBRID",
    typeColor: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
    emoji: "🏦",
    mission: "전설적 투자자 페르소나 AI 앙상블 → Buffett/Soros/Lynch/Druckenmiller 관점 종합 → 최적 투자 결정",
  },
  strategy_lab: {
    name: "Strategy Lab Team",
    type: "R&D",
    typeColor: "text-orange-400 bg-orange-400/10 border-orange-400/30",
    emoji: "🔬",
    mission: "arXiv 논문 + GitHub Trending 스캔 → 최신 전략 추출 → 백테스트 검증 → 유망 전략 신팀 등록",
  },
};

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

// ─── MemberCard ───────────────────────────────────────────────────────────────
const MemberCard = ({ member }: { member: TeamMember }) => {
  const cfg = ROLE_CONFIG[member.role_type] ?? ROLE_CONFIG.researcher;
  return (
    <div
      className={`rounded-xl border p-5 transition-all hover:scale-[1.01] ${
        member.is_head
          ? "border-yellow-400/40 bg-gradient-to-br from-yellow-400/5 to-zinc-900"
          : "border-zinc-700/50 bg-zinc-800/40 hover:border-zinc-600"
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`w-11 h-11 rounded-full flex items-center justify-center text-lg border ${cfg.color} flex-shrink-0`}
        >
          {cfg.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-white text-base">{member.member_name}</span>
            {member.is_head && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-400/20 text-yellow-400 border border-yellow-400/30">
                LEAD
              </span>
            )}
            {member.is_ai_agent && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-violet-400/20 text-violet-400 border border-violet-400/30">
                AI
              </span>
            )}
          </div>
          <div className={`text-xs mt-0.5 px-1.5 py-0.5 rounded inline-block border ${cfg.color}`}>
            {member.role}
          </div>
          <p className="text-sm text-zinc-400 mt-2 leading-relaxed">{member.description}</p>
          {member.expertise_tags?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-3">
              {member.expertise_tags.map((tag) => (
                <span
                  key={tag}
                  className="text-xs px-2 py-0.5 rounded-full bg-zinc-700/60 text-zinc-300 border border-zinc-600/50"
                >
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function TeamDetailPage() {
  const params = useParams();
  const teamId = params?.id as string;

  const [team, setTeam] = useState<Team | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [rebalanceHistory, setRebalanceHistory] = useState<RebalanceHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"members" | "portfolio" | "rebalance">("members");

  useEffect(() => {
    if (!teamId) return;
    const load = async () => {
      try {
        const [leaderboard, membersRes, positionsRes, rebalanceRes] = await Promise.allSettled([
          api.company.leaderboard(),
          api.portfolio.teamMembersByTeam(teamId),
          api.portfolio.positions(teamId),
          api.portfolio.rebalanceHistory(teamId),
        ]);

        if (leaderboard.status === "fulfilled") {
          const found = leaderboard.value.data.find((t: Team) => t.team_id === teamId);
          if (found) setTeam(found);
        }
        if (membersRes.status === "fulfilled") setMembers(membersRes.value.data);
        if (positionsRes.status === "fulfilled") setPositions(positionsRes.value.data.positions ?? []);
        if (rebalanceRes.status === "fulfilled") setRebalanceHistory(rebalanceRes.value.data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [teamId]);

  const cfg = TEAM_CONFIG[teamId] ?? {
    name: team?.team_name ?? teamId,
    type: "TEAM",
    typeColor: "text-zinc-400 bg-zinc-700/30 border-zinc-600/30",
    emoji: "🏢",
    mission: team?.description ?? "",
  };

  const head = members.find((m) => m.is_head);
  const teamMembers = members.filter((m) => !m.is_head);

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 text-white flex items-center justify-center">
        <div className="text-zinc-500 animate-pulse">로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      {/* Nav */}
      <nav className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-4">
          <Link href="/" className="text-zinc-400 hover:text-white text-sm transition-colors">
            ← QuantLab Capital
          </Link>
          <span className="text-zinc-700">/</span>
          <Link href="/company" className="text-zinc-400 hover:text-white text-sm transition-colors">
            회사 현황
          </Link>
          <span className="text-zinc-700">/</span>
          <span className="text-white text-sm font-medium">{cfg.emoji} {cfg.name}</span>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-4xl">{cfg.emoji}</span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-white">{cfg.name}</h1>
                <span className={`text-xs px-2 py-0.5 rounded border font-mono font-bold ${cfg.typeColor}`}>
                  {cfg.type}
                </span>
              </div>
              {head && (
                <p className="text-sm text-zinc-400 mt-0.5">
                  팀장: <span className="text-white font-medium">{head.member_name}</span>
                  <span className="text-zinc-500"> — {head.role}</span>
                </p>
              )}
            </div>
          </div>
          <p className="text-zinc-400 text-sm max-w-3xl leading-relaxed mt-3 pl-1 border-l-2 border-zinc-700">
            {cfg.mission}
          </p>
        </div>

        {/* KPI Row */}
        {team && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
            {[
              { label: "팀원", value: members.length + "명", icon: "👥" },
              { label: "우승 횟수", value: `${team.wins} / ${team.total_competitions}`, icon: "🏆" },
              { label: "최고 Sharpe", value: team.best_sharpe != null ? team.best_sharpe.toFixed(2) : "—", icon: "📈" },
              { label: "최고 CAGR", value: team.best_cagr != null ? `${(team.best_cagr * 100).toFixed(1)}%` : "—", icon: "💹" },
            ].map((kpi) => (
              <div key={kpi.label} className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-1">
                  <span>{kpi.icon}</span>
                  <span className="text-xs text-zinc-500">{kpi.label}</span>
                </div>
                <div className="text-xl font-bold text-white">{kpi.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-zinc-800/40 p-1 rounded-xl w-fit border border-zinc-700/50">
          {[
            { id: "members", label: "👥 팀원", show: true },
            { id: "portfolio", label: "📊 포트폴리오", show: positions.length > 0 },
            { id: "rebalance", label: "🔄 리밸런싱", show: true },
          ]
            .filter((t) => t.show)
            .map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === tab.id
                    ? "bg-zinc-700 text-white shadow"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
        </div>

        {/* Tab: Members */}
        {activeTab === "members" && (
          <div>
            {head && (
              <div className="mb-6">
                <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">팀장</h3>
                <MemberCard member={head} />
              </div>
            )}
            {teamMembers.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">팀원</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {teamMembers.map((m) => (
                    <MemberCard key={m.id} member={m} />
                  ))}
                </div>
              </div>
            )}
            {members.length === 0 && (
              <div className="text-center py-16 text-zinc-600">팀원 정보 없음</div>
            )}
          </div>
        )}

        {/* Tab: Portfolio */}
        {activeTab === "portfolio" && (
          <div>
            {positions.length > 0 ? (
              <>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-zinc-400">
                    현재 포트폴리오 — {positions.length}개 종목
                  </h3>
                  <Link
                    href="/portfolio"
                    className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    전체 포트폴리오 보기 →
                  </Link>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-700/50">
                        {["순위", "종목", "섹터", "목표비중", "팩터점수", "모멘텀12M", "변동성"].map(
                          (h) => (
                            <th key={h} className="text-left py-2 px-3 text-xs text-zinc-500 font-medium">
                              {h}
                            </th>
                          )
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((pos, i) => (
                        <tr
                          key={pos.symbol}
                          className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors"
                        >
                          <td className="py-2.5 px-3 text-zinc-500 font-mono text-xs">{i + 1}</td>
                          <td className="py-2.5 px-3">
                            <div className="font-medium text-white">{pos.symbol}</div>
                            {pos.name && (
                              <div className="text-xs text-zinc-500 truncate max-w-[120px]">{pos.name}</div>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-xs text-zinc-400">{pos.sector ?? "—"}</td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <div
                                className="h-1.5 bg-blue-500 rounded-full"
                                style={{ width: `${Math.min(100, pos.target_weight * 100 * 8)}px` }}
                              />
                              <span className="text-white font-mono text-xs">
                                {(pos.target_weight * 100).toFixed(1)}%
                              </span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3">
                            {pos.composite_score != null ? (
                              <span
                                className={`text-sm font-bold ${
                                  pos.composite_score >= 70
                                    ? "text-emerald-400"
                                    : pos.composite_score >= 50
                                    ? "text-yellow-400"
                                    : "text-zinc-400"
                                }`}
                              >
                                {pos.composite_score.toFixed(1)}
                              </span>
                            ) : (
                              <span className="text-zinc-600">—</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-xs">
                            {pos.momentum_12m1m != null ? (
                              <span
                                className={
                                  pos.momentum_12m1m >= 0 ? "text-emerald-400" : "text-red-400"
                                }
                              >
                                {pos.momentum_12m1m >= 0 ? "+" : ""}
                                {(pos.momentum_12m1m * 100).toFixed(1)}%
                              </span>
                            ) : (
                              <span className="text-zinc-600">—</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-xs text-zinc-400">
                            {pos.low_vol != null
                              ? `${(Math.abs(pos.low_vol) * 100).toFixed(1)}%`
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="text-center py-16">
                <div className="text-4xl mb-3">📊</div>
                <div className="text-zinc-500 text-sm">포트폴리오 데이터 없음</div>
                <p className="text-zinc-600 text-xs mt-2">
                  팩터 엔진 실행 후 포지션이 생성됩니다.
                </p>
                <Link
                  href="/portfolio"
                  className="mt-4 inline-block text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  포트폴리오 페이지에서 실행 →
                </Link>
              </div>
            )}
          </div>
        )}

        {/* Tab: Rebalance */}
        {activeTab === "rebalance" && (
          <div>
            {rebalanceHistory.length > 0 ? (
              <div className="space-y-3">
                {rebalanceHistory.map((r) => (
                  <div
                    key={r.id}
                    className="bg-zinc-800/40 border border-zinc-700/50 rounded-xl p-4"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-white">
                        📅 {r.rebalance_date}
                      </span>
                      <span className="text-xs text-zinc-500">
                        {new Date(r.created_at).toLocaleString("ko-KR")}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-400">{r.summary}</p>
                    {Array.isArray(r.trades) && r.trades.length > 0 && (
                      <div className="mt-3 text-xs text-zinc-500">
                        {r.trades.length}개 종목 리밸런싱
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-16">
                <div className="text-4xl mb-3">🔄</div>
                <div className="text-zinc-500 text-sm">리밸런싱 이력 없음</div>
                <p className="text-zinc-600 text-xs mt-2">
                  매주 월요일 07:30 자동 리밸런싱 실행됩니다.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
