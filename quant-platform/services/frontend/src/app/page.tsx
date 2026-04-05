"use client";

import { useEffect, useState } from "react";
import { api, BacktestRun, Strategy } from "@/lib/api";
import { Card, StatCard } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { formatDate, formatPercent } from "@/lib/utils";
import {
  Activity,
  BrainCircuit,
  BarChart2,
  TrendingUp,
  TrendingDown,
  Zap,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import Link from "next/link";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface MarketIndex {
  name: string;
  value: string;
  change: string;
  changePct: string;
  positive: boolean;
}

const MARKET_DATA: MarketIndex[] = [
  { name: "KOSPI", value: "2,628.45", change: "+14.32", changePct: "+0.55%", positive: true },
  { name: "KOSDAQ", value: "751.23", change: "-3.21", changePct: "-0.43%", positive: false },
  { name: "S&P 500", value: "5,204.34", change: "+23.11", changePct: "+0.45%", positive: true },
  { name: "NASDAQ", value: "16,248.52", change: "+87.44", changePct: "+0.54%", positive: true },
];

type DiscoveryStatus = "idle" | "running" | "done" | "error";

export default function DashboardPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatus>("idle");
  const [discoveryResult, setDiscoveryResult] = useState<{ strategies_created: number; backtests_triggered: number } | null>(null);

  async function runStrategyDiscovery() {
    setDiscoveryStatus("running");
    setDiscoveryResult(null);
    try {
      const res = await axios.post(`${API_BASE}/api/research/trigger-strategy-discovery`, {
        focus: "agentic trading, momentum, mean reversion, factor investing, machine learning trading, reinforcement learning",
        max_papers: 30,
        auto_backtest: true,
      });
      setDiscoveryStatus("done");
      // Poll for results after 10s
      setTimeout(async () => {
        const [strRes, btRes] = await Promise.allSettled([api.strategies.list(), api.backtests.list()]);
        if (strRes.status === "fulfilled") setStrategies(strRes.value.data);
        if (btRes.status === "fulfilled") setBacktests(btRes.value.data);
        setDiscoveryResult({ strategies_created: 0, backtests_triggered: 0 });
      }, 10000);
    } catch {
      setDiscoveryStatus("error");
    }
  }

  useEffect(() => {
    async function load() {
      try {
        const [strRes, btRes] = await Promise.allSettled([
          api.strategies.list(),
          api.backtests.list(),
        ]);
        if (strRes.status === "fulfilled") setStrategies(strRes.value.data);
        if (btRes.status === "fulfilled") setBacktests(btRes.value.data);
      } catch (_) {
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const completedBacktests = backtests.filter((b) => b.status === "completed");
  const bestSharpe = completedBacktests.length
    ? Math.max(...completedBacktests.map((b) => b.results?.sharpe_ratio ?? 0))
    : null;
  const bestCAGR = completedBacktests.length
    ? Math.max(...completedBacktests.map((b) => b.results?.cagr ?? 0))
    : null;

  const recentBacktests = [...backtests]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 8);

  const columns = [
    {
      key: "name",
      header: "Name",
      render: (row: BacktestRun) => (
        <Link
          href={`/backtests/${row.id}`}
          className="text-primary hover:text-primary/80 font-medium transition-colors"
        >
          {row.name}
        </Link>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (row: BacktestRun) => <StatusBadge status={row.status} />,
    },
    {
      key: "sharpe",
      header: "Sharpe",
      align: "right" as const,
      render: (row: BacktestRun) =>
        row.results ? (
          <span className={row.results.sharpe_ratio >= 1 ? "text-success" : "text-gray-300"}>
            {row.results.sharpe_ratio.toFixed(2)}
          </span>
        ) : (
          <span className="text-muted">-</span>
        ),
    },
    {
      key: "cagr",
      header: "CAGR",
      align: "right" as const,
      render: (row: BacktestRun) =>
        row.results ? (
          <span className={row.results.cagr >= 0 ? "text-success" : "text-danger"}>
            {formatPercent(row.results.cagr)}
          </span>
        ) : (
          <span className="text-muted">-</span>
        ),
    },
    {
      key: "max_drawdown",
      header: "Max DD",
      align: "right" as const,
      render: (row: BacktestRun) =>
        row.results ? (
          <span className="text-danger">
            {formatPercent(row.results.max_drawdown)}
          </span>
        ) : (
          <span className="text-muted">-</span>
        ),
    },
    {
      key: "created_at",
      header: "Date",
      render: (row: BacktestRun) => (
        <span className="text-muted">{formatDate(row.created_at)}</span>
      ),
    },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-muted mt-0.5">
            전략 연구 → 백테스팅 → 수익 창출 | KOSPI · KOSDAQ · US Stocks
          </p>
        </div>

        {/* Strategy Discovery Button */}
        <div className="flex flex-col items-end gap-1">
          <button
            onClick={runStrategyDiscovery}
            disabled={discoveryStatus === "running"}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              discoveryStatus === "running"
                ? "bg-primary/30 text-primary/60 cursor-not-allowed"
                : discoveryStatus === "done"
                ? "bg-success/20 text-success border border-success/40 hover:bg-success/30"
                : discoveryStatus === "error"
                ? "bg-danger/20 text-danger border border-danger/40 hover:bg-danger/30"
                : "bg-primary text-white hover:bg-primary/80 shadow-lg shadow-primary/20"
            }`}
          >
            {discoveryStatus === "running" ? (
              <><Loader2 size={15} className="animate-spin" /> 리서치 중...</>
            ) : discoveryStatus === "done" ? (
              <><CheckCircle2 size={15} /> 완료!</>
            ) : (
              <><Zap size={15} /> 전략 자동 발굴</>
            )}
          </button>
          <p className="text-xs text-muted">
            {discoveryStatus === "running"
              ? "arXiv 논문 분석 → 전략 생성 → 백테스트 실행 중..."
              : discoveryStatus === "done"
              ? "전략이 생성되고 백테스트가 시작됐어요"
              : "최신 논문 리서치 후 전략 자동 생성"}
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Strategies"
          value={loading ? "-" : strategies.length}
          icon={<BrainCircuit size={16} />}
        />
        <StatCard
          label="Total Backtests"
          value={loading ? "-" : backtests.length}
          icon={<BarChart2 size={16} />}
        />
        <StatCard
          label="Best Sharpe Ratio"
          value={loading || bestSharpe === null ? "-" : bestSharpe.toFixed(2)}
          positive={bestSharpe !== null && bestSharpe >= 1}
          icon={<Activity size={16} />}
        />
        <StatCard
          label="Best CAGR"
          value={loading || bestCAGR === null ? "-" : formatPercent(bestCAGR)}
          positive={bestCAGR !== null && bestCAGR >= 0}
          negative={bestCAGR !== null && bestCAGR < 0}
          icon={<TrendingUp size={16} />}
        />
      </div>

      {/* Market Overview */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">
            Market Overview
          </h2>
          <span className="text-xs text-muted">Placeholder data</span>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {MARKET_DATA.map((index) => (
            <div
              key={index.name}
              className="bg-background rounded-lg px-4 py-3 border border-border"
            >
              <p className="text-xs text-muted mb-1">{index.name}</p>
              <p className="text-base font-bold text-white">{index.value}</p>
              <div className="flex items-center gap-1 mt-0.5">
                {index.positive ? (
                  <TrendingUp size={11} className="text-success" />
                ) : (
                  <TrendingDown size={11} className="text-danger" />
                )}
                <span
                  className={`text-xs font-medium ${
                    index.positive ? "text-success" : "text-danger"
                  }`}
                >
                  {index.change} ({index.changePct})
                </span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Recent Backtests */}
      <Card className="p-0">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">
            Recent Backtests
          </h2>
          <Link
            href="/backtests"
            className="text-xs text-primary hover:text-primary/80 transition-colors"
          >
            View all
          </Link>
        </div>
        <Table
          columns={columns}
          data={recentBacktests}
          emptyMessage={
            loading ? "Loading..." : "No backtests found. Create your first backtest."
          }
        />
      </Card>
    </div>
  );
}
