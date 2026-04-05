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

// ── Portfolio / Factor Engine Types ──────────────────────────────────────────
export interface FactorScore {
  symbol: string;
  name?: string;
  sector?: string;
  market: string;
  composite_score: number;
  rank: number;
  momentum_12m1m: number | null;
  momentum_3m: number | null;
  low_vol: number | null;
  value_proxy: number | null;
  quality_proxy: number | null;
  momentum_12m1m_rank: number;
  momentum_3m_rank: number;
  low_vol_rank: number;
  value_proxy_rank: number;
  quality_proxy_rank: number;
  score_date: string;
}

export interface PortfolioPosition {
  symbol: string;
  name?: string;
  sector?: string;
  target_weight: number;
  last_rebalanced: string | null;
  composite_score: number | null;
  factor_rank: number | null;
  momentum_12m1m: number | null;
  low_vol: number | null;
  quality_proxy: number | null;
}

export interface RebalanceHistory {
  id: number;
  team_id: string;
  team_name?: string;
  rebalance_date: string;
  trades: any[];
  summary: string;
  created_at: string;
}

export interface TeamMember {
  id: number;
  team_id: string;
  team_name: string;
  member_name: string;
  role: string;
  role_type: string;
  description: string;
  is_head: boolean;
  is_ai_agent: boolean;
  expertise_tags: string[];
}

export interface TeamWithMembers {
  team_id: string;
  team_name: string;
  members: TeamMember[];
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
  portfolio: {
    factorScores: (market?: string, topN?: number) =>
      axios.get(`${API_BASE}/api/portfolio/factor-scores${market ? `?market=${market}` : ""}${topN ? `&top_n=${topN}` : ""}`),
    positions: (teamId: string) =>
      axios.get(`${API_BASE}/api/portfolio/positions/${teamId}`),
    allPositions: () =>
      axios.get(`${API_BASE}/api/portfolio/positions`),
    rebalanceHistory: (teamId: string) =>
      axios.get(`${API_BASE}/api/portfolio/rebalance-history/${teamId}`),
    runFactorEngine: (market?: string) =>
      axios.post(`${API_BASE}/api/portfolio/run-factor-engine${market ? `?market=${market}` : ""}`),
    teamMembers: () =>
      axios.get<TeamWithMembers[]>(`${API_BASE}/api/portfolio/team-members`),
    teamMembersByTeam: (teamId: string) =>
      axios.get<TeamMember[]>(`${API_BASE}/api/portfolio/team-members/${teamId}`),
  },
  company: {
    leaderboard: () => axios.get(`${API_BASE}/api/company/leaderboard`),
    latestCompetition: () => axios.get(`${API_BASE}/api/company/competition/latest`),
    competitionHistory: (limit = 10) =>
      axios.get(`${API_BASE}/api/company/competition/history?limit=${limit}`),
    tradeJournal: (market?: string, limit = 50) =>
      axios.get(`${API_BASE}/api/company/trade-journal?limit=${limit}${market ? `&market=${market}` : ""}`),
    tradeStats: () => axios.get(`${API_BASE}/api/company/trade-journal/stats`),
    agentMemory: (agentId?: string, memoryType?: string) =>
      axios.get(`${API_BASE}/api/company/agent-memory?limit=50${agentId ? `&agent_id=${agentId}` : ""}${memoryType ? `&memory_type=${memoryType}` : ""}`),
    agenticSignals: (market?: string, limit = 30) =>
      axios.get(`${API_BASE}/api/company/agentic-signals?limit=${limit}${market ? `&market=${market}` : ""}`),
  },
};
