"use client";

import { useEffect, useState } from "react";
import { api, Strategy } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { formatDate } from "@/lib/utils";
import { Plus, Play, Trash2, ChevronRight, BrainCircuit } from "lucide-react";
import { useRouter } from "next/navigation";

const STRATEGY_TYPES = [
  { value: "sma_crossover", label: "SMA Crossover" },
  { value: "rsi_mean_reversion", label: "RSI Mean Reversion" },
  { value: "bollinger_band", label: "Bollinger Band" },
  { value: "momentum", label: "Momentum" },
  { value: "dual_momentum", label: "Dual Momentum" },
  { value: "macd", label: "MACD" },
  { value: "breakout", label: "Breakout" },
  { value: "factor_model", label: "Factor Model" },
];

const MARKETS = [
  { value: "KOSPI", label: "KOSPI" },
  { value: "KOSDAQ", label: "KOSDAQ" },
  { value: "US", label: "US (NYSE/NASDAQ)" },
];

const DEFAULT_PARAMS: Record<string, Record<string, any>> = {
  sma_crossover: { fast_period: 10, slow_period: 30 },
  rsi_mean_reversion: { rsi_period: 14, oversold: 30, overbought: 70 },
  bollinger_band: { period: 20, std_dev: 2.0 },
  momentum: { lookback: 12, top_n: 5 },
  dual_momentum: { lookback: 12 },
  macd: { fast: 12, slow: 26, signal: 9 },
  breakout: { lookback: 20, volume_factor: 1.5 },
  factor_model: { factors: ["value", "momentum", "quality"] },
};

const strategyTypeLabel = (type: string) =>
  STRATEGY_TYPES.find((s) => s.value === type)?.label ?? type;

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const [form, setForm] = useState({
    name: "",
    description: "",
    strategy_type: "sma_crossover",
    market: "KOSPI",
    parametersJson: JSON.stringify(DEFAULT_PARAMS["sma_crossover"], null, 2),
  });
  const [paramError, setParamError] = useState("");

  async function loadStrategies() {
    try {
      const res = await api.strategies.list();
      setStrategies(res.data);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStrategies();
  }, []);

  function handleTypeChange(type: string) {
    setForm((f) => ({
      ...f,
      strategy_type: type,
      parametersJson: JSON.stringify(DEFAULT_PARAMS[type] ?? {}, null, 2),
    }));
    setParamError("");
  }

  async function handleCreate() {
    if (!form.name.trim()) {
      setError("Name is required");
      return;
    }
    let parameters: Record<string, any>;
    try {
      parameters = JSON.parse(form.parametersJson);
    } catch {
      setParamError("Invalid JSON");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await api.strategies.create({
        name: form.name,
        description: form.description,
        strategy_type: form.strategy_type,
        market: form.market,
        parameters,
      });
      setModalOpen(false);
      setForm({
        name: "",
        description: "",
        strategy_type: "sma_crossover",
        market: "KOSPI",
        parametersJson: JSON.stringify(DEFAULT_PARAMS["sma_crossover"], null, 2),
      });
      await loadStrategies();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to create strategy");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.strategies.delete(id);
      setStrategies((prev) => prev.filter((s) => s.id !== id));
    } catch (_) {}
    setDeleteId(null);
  }

  function handleRunBacktest(strategyId: string) {
    router.push(`/backtests?strategy=${strategyId}`);
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Strategies</h1>
          <p className="text-sm text-muted mt-0.5">
            {strategies.length} strategy{strategies.length !== 1 ? "ies" : "y"}
          </p>
        </div>
        <Button onClick={() => setModalOpen(true)}>
          <Plus size={14} />
          New Strategy
        </Button>
      </div>

      {/* Strategy Grid */}
      {loading ? (
        <div className="text-muted text-sm">Loading...</div>
      ) : strategies.length === 0 ? (
        <Card className="py-16 text-center">
          <BrainCircuit size={32} className="mx-auto mb-3 text-muted" />
          <p className="text-gray-400 font-medium mb-1">No strategies yet</p>
          <p className="text-sm text-muted mb-4">
            Create your first quantitative trading strategy
          </p>
          <Button onClick={() => setModalOpen(true)} size="sm">
            <Plus size={13} />
            Create Strategy
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {strategies.map((strategy) => (
            <StrategyCard
              key={strategy.id}
              strategy={strategy}
              onRunBacktest={() => handleRunBacktest(strategy.id)}
              onDelete={() => setDeleteId(strategy.id)}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      <Modal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setError("");
          setParamError("");
        }}
        title="Create Strategy"
        size="lg"
      >
        <div className="space-y-4">
          <Input
            label="Strategy Name"
            placeholder="e.g. My SMA Crossover"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <Textarea
            label="Description"
            placeholder="Describe what this strategy does..."
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            rows={2}
          />
          <div className="grid grid-cols-2 gap-4">
            <Select
              label="Strategy Type"
              options={STRATEGY_TYPES}
              value={form.strategy_type}
              onChange={(e) => handleTypeChange(e.target.value)}
            />
            <Select
              label="Market"
              options={MARKETS}
              value={form.market}
              onChange={(e) => setForm((f) => ({ ...f, market: e.target.value }))}
            />
          </div>
          <div>
            <Textarea
              label="Parameters (JSON)"
              value={form.parametersJson}
              onChange={(e) => {
                setForm((f) => ({ ...f, parametersJson: e.target.value }));
                setParamError("");
              }}
              rows={6}
              error={paramError}
              className="font-mono text-xs"
            />
            <p className="text-xs text-muted mt-1">
              Edit parameters as JSON key-value pairs
            </p>
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="secondary"
              onClick={() => {
                setModalOpen(false);
                setError("");
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleCreate} loading={submitting}>
              Create Strategy
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal
        open={deleteId !== null}
        onClose={() => setDeleteId(null)}
        title="Delete Strategy"
        size="sm"
      >
        <p className="text-sm text-gray-300 mb-4">
          Are you sure you want to delete this strategy? This action cannot be
          undone.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleteId(null)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={() => deleteId && handleDelete(deleteId)}
          >
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  );
}

function StrategyCard({
  strategy,
  onRunBacktest,
  onDelete,
}: {
  strategy: Strategy;
  onRunBacktest: () => void;
  onDelete: () => void;
}) {
  const paramKeys = Object.keys(strategy.parameters ?? {});

  return (
    <Card className="flex flex-col gap-3" hoverable>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-white truncate">
            {strategy.name}
          </h3>
          {strategy.description && (
            <p className="text-xs text-muted mt-0.5 line-clamp-2">
              {strategy.description}
            </p>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="p-1 rounded text-muted hover:text-danger transition-colors shrink-0"
        >
          <Trash2 size={13} />
        </button>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="primary">{strategyTypeLabel(strategy.strategy_type)}</Badge>
        <Badge variant="muted">{strategy.market}</Badge>
      </div>

      {/* Parameters preview */}
      {paramKeys.length > 0 && (
        <div className="bg-background rounded-lg px-3 py-2 border border-border">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {paramKeys.slice(0, 4).map((key) => (
              <div key={key} className="flex justify-between text-xs">
                <span className="text-muted truncate">{key}</span>
                <span className="text-gray-300 ml-2 shrink-0">
                  {String(strategy.parameters[key])}
                </span>
              </div>
            ))}
            {paramKeys.length > 4 && (
              <div className="col-span-2 text-xs text-muted">
                +{paramKeys.length - 4} more
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mt-auto pt-1">
        <span className="text-xs text-muted">
          {formatDate(strategy.created_at)}
        </span>
        <Button size="sm" variant="outline" onClick={onRunBacktest}>
          <Play size={12} />
          Run Backtest
        </Button>
      </div>
    </Card>
  );
}
