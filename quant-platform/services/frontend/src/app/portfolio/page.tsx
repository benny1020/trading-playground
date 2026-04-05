"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, FactorScore } from "@/lib/api";

// ─── Factor Bar ───────────────────────────────────────────────────────────────
const FactorBar = ({ value, label }: { value: number; label: string }) => {
  const pct = Math.min(100, Math.max(0, value));
  const color =
    pct >= 70 ? "bg-emerald-500" : pct >= 50 ? "bg-yellow-500" : pct >= 30 ? "bg-orange-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-zinc-500 w-20 text-right shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-zinc-400 w-8 text-right font-mono">{pct.toFixed(0)}</span>
    </div>
  );
};

// ─── Score Badge ──────────────────────────────────────────────────────────────
const ScoreBadge = ({ score }: { score: number }) => {
  const tier =
    score >= 80 ? { label: "S", color: "text-yellow-400 bg-yellow-400/10 border-yellow-400/30" } :
    score >= 65 ? { label: "A", color: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30" } :
    score >= 50 ? { label: "B", color: "text-blue-400 bg-blue-400/10 border-blue-400/30" } :
    score >= 35 ? { label: "C", color: "text-orange-400 bg-orange-400/10 border-orange-400/30" } :
                  { label: "D", color: "text-red-400 bg-red-400/10 border-red-400/30" };
  return (
    <span className={`text-xs font-bold px-1.5 py-0.5 rounded border ${tier.color}`}>
      {tier.label}
    </span>
  );
};

interface PortfolioSummary {
  team_id: string;
  team_name: string;
  holding_count: number;
  total_weight: number;
  last_rebalanced: string | null;
}

export default function PortfolioPage() {
  const [factorData, setFactorData] = useState<{ score_date: string | null; total: number; scores: FactorScore[] }>({
    score_date: null,
    total: 0,
    scores: [],
  });
  const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary[]>([]);
  const [selectedMarket, setSelectedMarket] = useState("ALL");
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [topN, setTopN] = useState(30);

  useEffect(() => {
    loadData();
  }, [selectedMarket, topN]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [factorRes, summaryRes] = await Promise.allSettled([
        api.portfolio.factorScores(selectedMarket === "ALL" ? undefined : selectedMarket, topN),
        api.portfolio.allPositions(),
      ]);

      if (factorRes.status === "fulfilled") setFactorData(factorRes.value.data);
      if (summaryRes.status === "fulfilled") setPortfolioSummary(summaryRes.value.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleRunEngine = async () => {
    setRunning(true);
    try {
      await api.portfolio.runFactorEngine(selectedMarket === "ALL" ? undefined : selectedMarket);
      setTimeout(() => {
        loadData();
        setRunning(false);
      }, 3000);
    } catch (e) {
      setRunning(false);
    }
  };

  const scores = factorData.scores ?? [];

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      {/* Nav */}
      <nav className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-zinc-400 hover:text-white text-sm transition-colors">
              ← QuantLab Capital
            </Link>
            <span className="text-zinc-700">/</span>
            <span className="text-white text-sm font-medium">📊 포트폴리오 &amp; 팩터 스코어</span>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedMarket}
              onChange={(e) => setSelectedMarket(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 text-white text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
            >
              {["ALL", "KOSPI", "KOSDAQ", "US"].map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <select
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              className="bg-zinc-800 border border-zinc-700 text-white text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
            >
              {[20, 30, 50, 100].map((n) => (
                <option key={n} value={n}>Top {n}</option>
              ))}
            </select>
            <button
              onClick={handleRunEngine}
              disabled={running}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:cursor-not-allowed text-white text-xs font-medium px-4 py-1.5 rounded-lg transition-colors"
            >
              {running ? (
                <>
                  <span className="animate-spin">⚙️</span> 실행 중...
                </>
              ) : (
                <>⚡ 팩터 엔진 실행</>
              )}
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white mb-1">팩터 모델 &amp; 포트폴리오</h1>
          <p className="text-zinc-500 text-sm">
            전체 유니버스 팩터 스코어링 → 상위 종목 포트폴리오 구성 → 자동 리밸런싱
          </p>
          {factorData.score_date && (
            <div className="mt-2 text-xs text-zinc-600">
              기준일: {factorData.score_date} · 총 {factorData.total}개 종목
            </div>
          )}
        </div>

        {/* Factor Explanation */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
          {[
            { name: "Momentum 12M-1M", weight: "35%", desc: "12개월 수익률 (최근 1M 제외)", icon: "🚀", color: "border-blue-500/30 bg-blue-500/5" },
            { name: "Momentum 3M", weight: "15%", desc: "3개월 단기 모멘텀", icon: "⚡", color: "border-cyan-500/30 bg-cyan-500/5" },
            { name: "Low Volatility", weight: "25%", desc: "60일 저변동성 (방어적)", icon: "🛡️", color: "border-emerald-500/30 bg-emerald-500/5" },
            { name: "Value Proxy", weight: "15%", desc: "52주 최고가 대비 저렴도", icon: "💰", color: "border-yellow-500/30 bg-yellow-500/5" },
            { name: "Quality", weight: "10%", desc: "1년 Sharpe 비율", icon: "⭐", color: "border-purple-500/30 bg-purple-500/5" },
          ].map((f) => (
            <div key={f.name} className={`border rounded-xl p-3 ${f.color}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-base">{f.icon}</span>
                <span className="text-xs font-bold text-white/70">{f.weight}</span>
              </div>
              <div className="text-xs font-medium text-white/80 mb-0.5">{f.name}</div>
              <div className="text-xs text-zinc-500">{f.desc}</div>
            </div>
          ))}
        </div>

        {/* Portfolio Summary */}
        {portfolioSummary.length > 0 && (
          <div className="mb-8">
            <h2 className="text-sm font-semibold text-zinc-400 mb-3">팀별 포트폴리오 현황</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {portfolioSummary.map((p) => (
                <Link
                  key={p.team_id}
                  href={`/teams/${p.team_id}`}
                  className="flex items-center justify-between bg-zinc-800/40 border border-zinc-700/50 rounded-xl p-4 hover:border-zinc-600 transition-all"
                >
                  <div>
                    <div className="font-medium text-white text-sm">{p.team_name}</div>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      마지막 리밸런싱: {p.last_rebalanced ?? "없음"}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold text-white">{p.holding_count}종목</div>
                    <div className="text-xs text-zinc-500">
                      비중 합계 {(Number(p.total_weight) * 100).toFixed(0)}%
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Factor Scores Table */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-zinc-400">
              팩터 스코어 랭킹
              {scores.length > 0 && (
                <span className="text-zinc-600 ml-2 font-normal">Top {scores.length}</span>
              )}
            </h2>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20 text-zinc-600 animate-pulse">
              계산 중...
            </div>
          ) : scores.length === 0 ? (
            <div className="text-center py-20">
              <div className="text-5xl mb-4">🔍</div>
              <div className="text-zinc-500 text-sm">팩터 스코어 데이터 없음</div>
              <p className="text-zinc-600 text-xs mt-2 max-w-xs mx-auto">
                상단 "팩터 엔진 실행" 버튼을 눌러 전체 유니버스 팩터 계산을 시작하세요.
                <br />
                DB에 시장 데이터가 있어야 합니다.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-700/50">
                    {[
                      "순위", "종목코드", "종목명", "시장", "섹터",
                      "복합점수", "Momentum12M", "Momentum3M",
                      "LowVol", "Value", "Quality",
                    ].map((h) => (
                      <th
                        key={h}
                        className="text-left py-2 px-3 text-xs text-zinc-500 font-medium whitespace-nowrap"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {scores.map((s) => (
                    <>
                      <tr
                        key={s.symbol}
                        onClick={() =>
                          setExpanded(expanded === s.symbol ? null : s.symbol)
                        }
                        className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors cursor-pointer"
                      >
                        <td className="py-2.5 px-3">
                          <span
                            className={`text-xs font-bold font-mono ${
                              s.rank <= 5
                                ? "text-yellow-400"
                                : s.rank <= 10
                                ? "text-emerald-400"
                                : s.rank <= 20
                                ? "text-blue-400"
                                : "text-zinc-500"
                            }`}
                          >
                            #{s.rank}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-xs text-zinc-300">{s.symbol}</td>
                        <td className="py-2.5 px-3 text-white text-xs">{s.name ?? "—"}</td>
                        <td className="py-2.5 px-3">
                          <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-700/60 text-zinc-400 border border-zinc-600/50">
                            {s.market}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-xs text-zinc-500 truncate max-w-[100px]">
                          {s.sector ?? "—"}
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="flex items-center gap-2">
                            <ScoreBadge score={s.composite_score} />
                            <span className="font-bold text-white font-mono text-xs">
                              {s.composite_score.toFixed(1)}
                            </span>
                          </div>
                        </td>
                        {[
                          { v: s.momentum_12m1m_rank },
                          { v: s.momentum_3m_rank },
                          { v: s.low_vol_rank },
                          { v: s.value_proxy_rank },
                          { v: s.quality_proxy_rank },
                        ].map((f, i) => (
                          <td key={i} className="py-2.5 px-3">
                            <div
                              className={`text-xs font-mono ${
                                f.v >= 70 ? "text-emerald-400" : f.v >= 50 ? "text-yellow-400" : "text-zinc-500"
                              }`}
                            >
                              {f.v?.toFixed(0) ?? "—"}
                            </div>
                          </td>
                        ))}
                      </tr>

                      {/* Expanded row */}
                      {expanded === s.symbol && (
                        <tr className="bg-zinc-800/20">
                          <td colSpan={11} className="px-4 py-4">
                            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                              <div>
                                <div className="text-xs text-zinc-500 mb-2">팩터 랭킹 분포</div>
                                <div className="space-y-1.5">
                                  <FactorBar value={s.momentum_12m1m_rank} label="Mom12M" />
                                  <FactorBar value={s.momentum_3m_rank} label="Mom3M" />
                                  <FactorBar value={s.low_vol_rank} label="LowVol" />
                                  <FactorBar value={s.value_proxy_rank} label="Value" />
                                  <FactorBar value={s.quality_proxy_rank} label="Quality" />
                                </div>
                              </div>
                              <div className="col-span-2">
                                <div className="text-xs text-zinc-500 mb-2">원본 팩터값</div>
                                <div className="grid grid-cols-2 gap-1.5 text-xs">
                                  {[
                                    { k: "Momentum 12M-1M", v: s.momentum_12m1m, pct: true },
                                    { k: "Momentum 3M", v: s.momentum_3m, pct: true },
                                    { k: "Vol 60d", v: s.low_vol, pct: true, abs: true },
                                    { k: "Value", v: s.value_proxy },
                                    { k: "Quality (Sharpe)", v: s.quality_proxy },
                                  ].map((item) => (
                                    <div key={item.k} className="flex justify-between gap-2 bg-zinc-700/30 rounded px-2 py-1">
                                      <span className="text-zinc-500">{item.k}</span>
                                      <span
                                        className={`font-mono font-medium ${
                                          item.v == null
                                            ? "text-zinc-600"
                                            : item.v > 0
                                            ? "text-emerald-400"
                                            : "text-red-400"
                                        }`}
                                      >
                                        {item.v == null
                                          ? "—"
                                          : item.pct
                                          ? `${item.v >= 0 ? "+" : ""}${(
                                              (item.abs ? Math.abs(item.v) : item.v) * 100
                                            ).toFixed(1)}%`
                                          : item.v.toFixed(3)}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
