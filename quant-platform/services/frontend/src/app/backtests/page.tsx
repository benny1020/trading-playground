"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api, BacktestRun, Strategy } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Table } from "@/components/ui/Table";
import { formatDate, formatPercent } from "@/lib/utils";
import { Plus, BarChart2, X } from "lucide-react";

const MARKETS = [
  { value: "KOSPI", label: "KOSPI" },
  { value: "KOSDAQ", label: "KOSDAQ" },
  { value: "US", label: "US (NYSE/NASDAQ)" },
];

function BacktestsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const defaultStrategyId = searchParams.get("strategy") ?? "";

  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    name: "",
    strategy_id: defaultStrategyId,
    market: "KOSPI",
    start_date: "2020-01-01",
    end_date: "2024-12-31",
    initial_capital: "100000000",
    commission: "0.001",
    symbolInput: "",
    symbols: [] as string[],
  });

  async function load() {
    try {
      const [btRes, strRes] = await Promise.allSettled([
        api.backtests.list(),
        api.strategies.list(),
      ]);
      if (btRes.status === "fulfilled") setBacktests(btRes.value.data);
      if (strRes.status === "fulfilled") setStrategies(strRes.value.data);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    if (defaultStrategyId) {
      setModalOpen(true);
    }
  }, []);

  function addSymbol() {
    const sym = form.symbolInput.trim().toUpperCase();
    if (sym && !form.symbols.includes(sym)) {
      setForm((f) => ({ ...f, symbols: [...f.symbols, sym], symbolInput: "" }));
    }
  }

  function removeSymbol(sym: string) {
    setForm((f) => ({ ...f, symbols: f.symbols.filter((s) => s !== sym) }));
  }

  async function handleCreate() {
    if (!form.name.trim()) { setError("Name is required"); return; }
    if (!form.strategy_id) { setError("Select a strategy"); return; }
    if (form.symbols.length === 0) { setError("Add at least one symbol"); return; }

    setSubmitting(true);
    setError("");
    try {
      const result = await api.backtests.create({
        name: form.name,
        strategy_id: form.strategy_id,
        market: form.market,
        start_date: form.start_date,
        end_date: form.end_date,
        initial_capital: parseFloat(form.initial_capital),
        commission: parseFloat(form.commission),
        symbols: form.symbols,
      });
      setModalOpen(false);
      await load();
      // Navigate to the new backtest
      if (result.data?.id) {
        router.push(`/backtests/${result.data.id}`);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to create backtest");
    } finally {
      setSubmitting(false);
    }
  }

  const strategyOptions = strategies.map((s) => ({ value: s.id, label: s.name }));

  const columns = [
    {
      key: "name",
      header: "Name",
      render: (row: BacktestRun) => (
        <button
          onClick={() => router.push(`/backtests/${row.id}`)}
          className="text-primary hover:text-primary/80 font-medium transition-colors text-left"
        >
          {row.name}
        </button>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (row: BacktestRun) => <StatusBadge status={row.status} />,
    },
    {
      key: "symbols",
      header: "Symbols",
      render: (row: BacktestRun) => (
        <div className="flex flex-wrap gap-1">
          {(row.symbols ?? []).slice(0, 3).map((s) => (
            <Badge key={s} variant="muted">{s}</Badge>
          ))}
          {(row.symbols ?? []).length > 3 && (
            <Badge variant="muted">+{row.symbols.length - 3}</Badge>
          )}
        </div>
      ),
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
        ) : <span className="text-muted">-</span>,
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
        ) : <span className="text-muted">-</span>,
    },
    {
      key: "max_drawdown",
      header: "Max DD",
      align: "right" as const,
      render: (row: BacktestRun) =>
        row.results ? (
          <span className="text-danger">{formatPercent(row.results.max_drawdown)}</span>
        ) : <span className="text-muted">-</span>,
    },
    {
      key: "start_date",
      header: "Period",
      render: (row: BacktestRun) => (
        <span className="text-muted text-xs">
          {row.start_date?.slice(0, 10)} ~ {row.end_date?.slice(0, 10)}
        </span>
      ),
    },
    {
      key: "created_at",
      header: "Created",
      render: (row: BacktestRun) => (
        <span className="text-muted">{formatDate(row.created_at)}</span>
      ),
    },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Backtests</h1>
          <p className="text-sm text-muted mt-0.5">
            {backtests.length} backtest{backtests.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Button onClick={() => setModalOpen(true)}>
          <Plus size={14} />
          New Backtest
        </Button>
      </div>

      {/* Table */}
      <Card className="p-0">
        {loading ? (
          <div className="p-8 text-center text-muted text-sm">Loading...</div>
        ) : backtests.length === 0 ? (
          <div className="p-16 text-center">
            <BarChart2 size={32} className="mx-auto mb-3 text-muted" />
            <p className="text-gray-400 font-medium mb-1">No backtests yet</p>
            <p className="text-sm text-muted mb-4">
              Run your first backtest to evaluate a strategy
            </p>
            <Button size="sm" onClick={() => setModalOpen(true)}>
              <Plus size={13} />
              Create Backtest
            </Button>
          </div>
        ) : (
          <Table
            columns={columns}
            data={backtests.sort(
              (a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            )}
            onRowClick={(row) => router.push(`/backtests/${row.id}`)}
          />
        )}
      </Card>

      {/* Create Modal */}
      <Modal
        open={modalOpen}
        onClose={() => { setModalOpen(false); setError(""); }}
        title="Create Backtest"
        size="lg"
      >
        <div className="space-y-4">
          <Input
            label="Backtest Name"
            placeholder="e.g. SMA Crossover KOSPI 2020-2024"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <Select
            label="Strategy"
            options={strategyOptions}
            placeholder="Select a strategy..."
            value={form.strategy_id}
            onChange={(e) => setForm((f) => ({ ...f, strategy_id: e.target.value }))}
          />
          <Select
            label="Market"
            options={MARKETS}
            value={form.market}
            onChange={(e) => setForm((f) => ({ ...f, market: e.target.value }))}
          />

          {/* Symbol input */}
          <div>
            <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1">
              Symbols
            </label>
            <div className="flex gap-2 mb-2">
              <input
                className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors uppercase"
                placeholder="e.g. 005930 or AAPL"
                value={form.symbolInput}
                onChange={(e) => setForm((f) => ({ ...f, symbolInput: e.target.value }))}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSymbol(); } }}
              />
              <Button size="sm" variant="secondary" onClick={addSymbol}>
                Add
              </Button>
            </div>
            {form.symbols.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {form.symbols.map((sym) => (
                  <span
                    key={sym}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-primary/10 border border-primary/20 rounded-md text-xs text-primary"
                  >
                    {sym}
                    <button onClick={() => removeSymbol(sym)} className="hover:text-white">
                      <X size={10} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Start Date"
              type="date"
              value={form.start_date}
              onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
            />
            <Input
              label="End Date"
              type="date"
              value={form.end_date}
              onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Initial Capital"
              type="number"
              value={form.initial_capital}
              onChange={(e) => setForm((f) => ({ ...f, initial_capital: e.target.value }))}
            />
            <Input
              label="Commission Rate"
              type="number"
              step="0.0001"
              value={form.commission}
              onChange={(e) => setForm((f) => ({ ...f, commission: e.target.value }))}
              placeholder="0.001"
            />
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => { setModalOpen(false); setError(""); }}>
              Cancel
            </Button>
            <Button onClick={handleCreate} loading={submitting}>
              Run Backtest
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default function BacktestsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-muted">Loading...</div>}>
      <BacktestsContent />
    </Suspense>
  );
}
