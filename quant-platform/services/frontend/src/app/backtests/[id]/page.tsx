"use client";

import { useEffect, useState, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, BacktestRun, Trade } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Table, Pagination } from "@/components/ui/Table";
import { EquityCurve } from "@/components/charts/EquityCurve";
import { DrawdownChart, computeDrawdown } from "@/components/charts/DrawdownChart";
import {
  formatDate,
  formatPercent,
  formatCurrency,
} from "@/lib/utils";
import { ArrowLeft, TrendingUp, TrendingDown } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string;
  positive?: boolean;
  negative?: boolean;
  neutral?: boolean;
}

function MetricCard({ label, value, positive, negative }: MetricCardProps) {
  return (
    <div className="bg-background border border-border rounded-lg px-4 py-3">
      <p className="text-xs text-muted uppercase tracking-wider mb-1">{label}</p>
      <p
        className={[
          "text-lg font-bold",
          positive ? "text-success" : negative ? "text-danger" : "text-white",
        ].join(" ")}
      >
        {value}
      </p>
    </div>
  );
}

const PAGE_SIZE = 20;

export default function BacktestDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [backtest, setBacktest] = useState<BacktestRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tradePage, setTradePage] = useState(1);
  const [tradeSortKey, setTradeSortKey] = useState("entry_date");
  const [tradeSortDir, setTradeSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    async function load() {
      try {
        const res = await api.backtests.get(id);
        setBacktest(res.data);
      } catch (e: any) {
        setError(e?.response?.data?.detail ?? "Failed to load backtest");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const drawdownData = useMemo(() => {
    if (!backtest?.equity_curve) return [];
    return computeDrawdown(backtest.equity_curve);
  }, [backtest?.equity_curve]);

  // Sort trades
  const sortedTrades = useMemo(() => {
    if (!backtest?.trades) return [];
    return [...backtest.trades].sort((a, b) => {
      const av = (a as any)[tradeSortKey];
      const bv = (b as any)[tradeSortKey];
      const dir = tradeSortDir === "asc" ? 1 : -1;
      if (typeof av === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [backtest?.trades, tradeSortKey, tradeSortDir]);

  const paginatedTrades = useMemo(() => {
    const start = (tradePage - 1) * PAGE_SIZE;
    return sortedTrades.slice(start, start + PAGE_SIZE);
  }, [sortedTrades, tradePage]);

  const totalTradePages = Math.ceil(sortedTrades.length / PAGE_SIZE);

  function handleTradeSort(key: string) {
    if (key === tradeSortKey) {
      setTradeSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setTradeSortKey(key);
      setTradeSortDir("desc");
    }
    setTradePage(1);
  }

  if (loading) {
    return (
      <div className="p-6 text-muted text-sm">Loading backtest...</div>
    );
  }
  if (error || !backtest) {
    return (
      <div className="p-6">
        <p className="text-danger">{error || "Backtest not found"}</p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-3"
          onClick={() => router.push("/backtests")}
        >
          <ArrowLeft size={14} />
          Back to Backtests
        </Button>
      </div>
    );
  }

  const r = backtest.results;
  const market = backtest.market;

  // Trade stats
  const trades = backtest.trades ?? [];
  const winningTrades = trades.filter((t) => t.pnl > 0);
  const losingTrades = trades.filter((t) => t.pnl <= 0);
  const avgWin =
    winningTrades.length > 0
      ? winningTrades.reduce((s, t) => s + t.return_pct, 0) / winningTrades.length
      : 0;
  const avgLoss =
    losingTrades.length > 0
      ? losingTrades.reduce((s, t) => s + t.return_pct, 0) / losingTrades.length
      : 0;

  const tradeColumns = [
    { key: "symbol", header: "Symbol", sortable: true },
    {
      key: "side",
      header: "Side",
      render: (row: Trade) => (
        <span className={row.side === "long" ? "text-success" : "text-danger"}>
          {row.side.toUpperCase()}
        </span>
      ),
    },
    {
      key: "entry_date",
      header: "Entry",
      sortable: true,
      render: (row: Trade) => (
        <span className="text-muted">{formatDate(row.entry_date)}</span>
      ),
    },
    {
      key: "exit_date",
      header: "Exit",
      sortable: true,
      render: (row: Trade) => (
        <span className="text-muted">{formatDate(row.exit_date)}</span>
      ),
    },
    {
      key: "entry_price",
      header: "Entry Price",
      align: "right" as const,
      sortable: true,
      render: (row: Trade) => (
        <span>{formatCurrency(row.entry_price, market)}</span>
      ),
    },
    {
      key: "exit_price",
      header: "Exit Price",
      align: "right" as const,
      render: (row: Trade) => (
        <span>{formatCurrency(row.exit_price, market)}</span>
      ),
    },
    {
      key: "quantity",
      header: "Qty",
      align: "right" as const,
      render: (row: Trade) => <span>{row.quantity.toLocaleString()}</span>,
    },
    {
      key: "pnl",
      header: "P&L",
      align: "right" as const,
      sortable: true,
      render: (row: Trade) => (
        <span className={row.pnl >= 0 ? "text-success" : "text-danger"}>
          {row.pnl >= 0 ? "+" : ""}
          {formatCurrency(row.pnl, market)}
        </span>
      ),
    },
    {
      key: "return_pct",
      header: "Return",
      align: "right" as const,
      sortable: true,
      render: (row: Trade) => (
        <span className={row.return_pct >= 0 ? "text-success" : "text-danger"}>
          {formatPercent(row.return_pct)}
        </span>
      ),
    },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push("/backtests")}
        className="mb-2"
      >
        <ArrowLeft size={14} />
        Backtests
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white">{backtest.name}</h1>
          <div className="flex items-center gap-3 mt-1.5">
            <StatusBadge status={backtest.status} />
            <span className="text-sm text-muted">
              {backtest.start_date?.slice(0, 10)} ~ {backtest.end_date?.slice(0, 10)}
            </span>
            <span className="text-sm text-muted">
              Capital: {formatCurrency(backtest.initial_capital, market)}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {(backtest.symbols ?? []).map((s) => (
              <span
                key={s}
                className="px-2 py-0.5 bg-primary/10 border border-primary/20 rounded text-xs text-primary"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      {r && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">
            Performance Metrics
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            <MetricCard
              label="Total Return"
              value={formatPercent(r.total_return)}
              positive={r.total_return >= 0}
              negative={r.total_return < 0}
            />
            <MetricCard
              label="CAGR"
              value={formatPercent(r.cagr)}
              positive={r.cagr >= 0}
              negative={r.cagr < 0}
            />
            <MetricCard
              label="Sharpe Ratio"
              value={r.sharpe_ratio.toFixed(2)}
              positive={r.sharpe_ratio >= 1}
              negative={r.sharpe_ratio < 0}
            />
            <MetricCard
              label="Sortino Ratio"
              value={r.sortino_ratio.toFixed(2)}
              positive={r.sortino_ratio >= 1}
              negative={r.sortino_ratio < 0}
            />
            <MetricCard
              label="Max Drawdown"
              value={formatPercent(r.max_drawdown)}
              negative={true}
            />
            <MetricCard
              label="Calmar Ratio"
              value={r.calmar_ratio.toFixed(2)}
              positive={r.calmar_ratio >= 1}
              negative={r.calmar_ratio < 0}
            />
            <MetricCard
              label="Win Rate"
              value={formatPercent(r.win_rate)}
              positive={r.win_rate >= 50}
              negative={r.win_rate < 40}
            />
            <MetricCard
              label="Profit Factor"
              value={r.profit_factor.toFixed(2)}
              positive={r.profit_factor >= 1.5}
              negative={r.profit_factor < 1}
            />
            <MetricCard label="Total Trades" value={r.total_trades.toString()} />
            <MetricCard
              label="Volatility"
              value={formatPercent(r.volatility)}
            />
          </div>
        </div>
      )}

      {/* Equity Curve */}
      {backtest.equity_curve && backtest.equity_curve.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Equity Curve</CardTitle>
          </CardHeader>
          <EquityCurve
            data={backtest.equity_curve}
            initialCapital={backtest.initial_capital}
            market={market}
            height={320}
          />
        </Card>
      )}

      {/* Drawdown Chart */}
      {drawdownData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Drawdown</CardTitle>
          </CardHeader>
          <DrawdownChart data={drawdownData} height={200} />
        </Card>
      )}

      {/* Trade Distribution */}
      {trades.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Trade Distribution</CardTitle>
          </CardHeader>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-muted mb-1">Winning Trades</p>
              <p className="text-xl font-bold text-success">{winningTrades.length}</p>
            </div>
            <div>
              <p className="text-xs text-muted mb-1">Losing Trades</p>
              <p className="text-xl font-bold text-danger">{losingTrades.length}</p>
            </div>
            <div>
              <p className="text-xs text-muted mb-1">Avg Win</p>
              <p className="text-xl font-bold text-success">{formatPercent(avgWin)}</p>
            </div>
            <div>
              <p className="text-xs text-muted mb-1">Avg Loss</p>
              <p className="text-xl font-bold text-danger">{formatPercent(avgLoss)}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Trades Table */}
      {trades.length > 0 && (
        <Card className="p-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">
              Trades ({sortedTrades.length})
            </h2>
          </div>
          <Table
            columns={tradeColumns}
            data={paginatedTrades}
            sortKey={tradeSortKey}
            sortDir={tradeSortDir}
            onSort={handleTradeSort}
            emptyMessage="No trades"
          />
          <Pagination
            page={tradePage}
            totalPages={totalTradePages}
            onPageChange={setTradePage}
          />
        </Card>
      )}
    </div>
  );
}
