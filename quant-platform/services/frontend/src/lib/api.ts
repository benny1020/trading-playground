import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Types
export interface Strategy {
  id: string;
  name: string;
  description: string;
  strategy_type: string;
  market: string;
  parameters: Record<string, any>;
  created_at: string;
}

export interface BacktestMetrics {
  total_return: number;
  cagr: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  calmar_ratio: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  volatility: number;
}

export interface Trade {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  side: string;
  pnl: number;
  return_pct: number;
}

export interface BacktestRun {
  id: string;
  strategy_id: string;
  name: string;
  status: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  symbols: string[];
  market: string;
  results?: BacktestMetrics;
  equity_curve?: { date: string; value: number }[];
  trades?: Trade[];
  created_at: string;
}

export interface Paper {
  id: string;
  title: string;
  authors: string;
  abstract: string;
  url: string;
  source: string;
  published_date: string;
  summary: string;
  tags: string[];
}

export interface MarketStock {
  symbol: string;
  name: string;
  market: string;
  sector?: string;
}

export interface PriceData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// API client
export const api = {
  strategies: {
    list: () => axios.get<Strategy[]>(`${API_BASE}/api/strategies/`),
    create: (data: Partial<Strategy>) =>
      axios.post<Strategy>(`${API_BASE}/api/strategies/`, data),
    get: (id: string) =>
      axios.get<Strategy>(`${API_BASE}/api/strategies/${id}`),
    delete: (id: string) =>
      axios.delete(`${API_BASE}/api/strategies/${id}`),
    getTypes: () => axios.get(`${API_BASE}/api/strategies/types`),
  },
  backtests: {
    list: () => axios.get<BacktestRun[]>(`${API_BASE}/api/backtests/`),
    create: (data: any) =>
      axios.post<BacktestRun>(`${API_BASE}/api/backtests/`, data),
    get: (id: string) =>
      axios.get<BacktestRun>(`${API_BASE}/api/backtests/${id}`),
    getEquityCurve: (id: string) =>
      axios.get(`${API_BASE}/api/backtests/${id}/equity-curve`),
    getTrades: (id: string) =>
      axios.get(`${API_BASE}/api/backtests/${id}/trades`),
  },
  marketData: {
    searchStocks: (market: string, q: string) =>
      axios.get<MarketStock[]>(
        `${API_BASE}/api/market-data/stocks?market=${market}&search=${q}`
      ),
    getPrices: (symbol: string, start: string, end: string) =>
      axios.get<PriceData[]>(
        `${API_BASE}/api/market-data/${symbol}/prices?start=${start}&end=${end}`
      ),
  },
  research: {
    papers: () => axios.get<Paper[]>(`${API_BASE}/api/research/papers`),
    fetchPapers: () => axios.post(`${API_BASE}/api/research/papers/fetch`),
    triggerStrategyDiscovery: (focus?: string, maxPapers?: number, autoBacktest?: boolean) =>
      axios.post(`${API_BASE}/api/research/trigger-strategy-discovery`, {
        focus: focus ?? "agentic trading, momentum, mean reversion, factor investing, machine learning trading",
        max_papers: maxPapers ?? 30,
        auto_backtest: autoBacktest ?? true,
      }),
  },
};
