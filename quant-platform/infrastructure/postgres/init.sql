-- ============================================================
-- Quant Platform — PostgreSQL Initialization Script
-- ============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for full-text / trigram search

-- ============================================================
-- Strategies
-- ============================================================
CREATE TABLE IF NOT EXISTS strategies (
    id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(200) UNIQUE NOT NULL,
    description TEXT,
    strategy_type VARCHAR(50) NOT NULL,
    parameters  JSONB        DEFAULT '{}',
    market      VARCHAR(20)  DEFAULT 'ALL',
    is_active   BOOLEAN      DEFAULT TRUE,
    created_at  TIMESTAMP    DEFAULT NOW(),
    updated_at  TIMESTAMP    DEFAULT NOW()
);

-- ============================================================
-- Backtest runs
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_runs (
    id               UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id      UUID         REFERENCES strategies(id),
    name             VARCHAR(200) NOT NULL,
    status           VARCHAR(20)  DEFAULT 'pending',
    start_date       DATE         NOT NULL,
    end_date         DATE         NOT NULL,
    initial_capital  FLOAT        DEFAULT 100000000,
    commission_rate  FLOAT        DEFAULT 0.0015,
    symbols          JSONB        DEFAULT '[]',
    market           VARCHAR(20),
    results          JSONB,
    equity_curve     JSONB,
    trades           JSONB,
    error_message    TEXT,
    celery_task_id   VARCHAR(200),
    created_at       TIMESTAMP    DEFAULT NOW(),
    updated_at       TIMESTAMP    DEFAULT NOW()
);

-- ============================================================
-- Market data  (OHLCV)
-- ============================================================
CREATE TABLE IF NOT EXISTS market_data (
    id         SERIAL       PRIMARY KEY,
    symbol     VARCHAR(20)  NOT NULL,
    market     VARCHAR(20)  NOT NULL,  -- KOSPI | KOSDAQ | US
    date       DATE         NOT NULL,
    open       FLOAT,
    high       FLOAT,
    low        FLOAT,
    close      FLOAT        NOT NULL,
    volume     BIGINT,
    adj_close  FLOAT,
    created_at TIMESTAMP    DEFAULT NOW(),
    UNIQUE (symbol, date)
);

-- ============================================================
-- Stock info (metadata / fundamentals)
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_info (
    symbol     VARCHAR(20)  PRIMARY KEY,
    name       VARCHAR(200),
    market     VARCHAR(20),
    sector     VARCHAR(100),
    industry   VARCHAR(100),
    market_cap BIGINT,
    updated_at TIMESTAMP    DEFAULT NOW()
);

-- ============================================================
-- Research papers
-- ============================================================
CREATE TABLE IF NOT EXISTS papers (
    id               UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    title            TEXT    NOT NULL,
    authors          TEXT,
    abstract         TEXT,
    url              TEXT    UNIQUE,
    source           VARCHAR(50),   -- arxiv | ssrn
    published_date   DATE,
    tags             TEXT[],
    summary          TEXT,          -- AI-generated summary
    relevance_score  FLOAT   DEFAULT 0,
    created_at       TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Trend reports (weekly)
-- ============================================================
CREATE TABLE IF NOT EXISTS trend_reports (
    id               UUID  PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_date      DATE  NOT NULL,
    trending_topics  JSONB,
    top_papers       JSONB,
    summary          TEXT,
    created_at       TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Performance indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_date  ON market_data(symbol, date);
CREATE INDEX IF NOT EXISTS idx_market_data_market       ON market_data(market);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy   ON backtest_runs(strategy_id);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_status     ON backtest_runs(status);
CREATE INDEX IF NOT EXISTS idx_papers_relevance         ON papers(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_papers_published         ON papers(published_date DESC);
CREATE INDEX IF NOT EXISTS idx_papers_tags              ON papers USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_papers_title_trgm        ON papers USING GIN(title gin_trgm_ops);

-- ============================================================
-- Seed data — sample strategies
-- ============================================================
INSERT INTO strategies (name, description, strategy_type, parameters, market) VALUES
(
    'SMA 골든크로스 (KOSPI)',
    '20일/60일 이동평균 골든크로스 전략. 단기 이동평균이 장기 이동평균을 상향 돌파할 때 매수.',
    'sma_crossover',
    '{"short_window": 20, "long_window": 60}',
    'KOSPI'
),
(
    'RSI 평균회귀 (US)',
    'RSI 과매도 구간(30 이하) 매수, 과매수 구간(70 이상) 매도. S&P500 구성 종목 대상.',
    'rsi_mean_reversion',
    '{"period": 14, "oversold": 30, "overbought": 70}',
    'US'
),
(
    '모멘텀 팩터 (전체)',
    '12개월 누적 수익률 상위 20% 종목 매수, 하위 20% 매도. 월별 리밸런싱.',
    'momentum',
    '{"lookback": 252, "top_pct": 0.2, "rebalance_freq": "M"}',
    'ALL'
),
(
    '볼린저밴드 (KOSDAQ)',
    '볼린저밴드 하단 이탈 시 매수, 상단 이탈 시 매도하는 평균회귀 전략.',
    'bollinger_band',
    '{"period": 20, "std_dev": 2.0}',
    'KOSDAQ'
),
(
    '이중 모멘텀 (Antonacci)',
    'Gary Antonacci의 Dual Momentum: 절대 모멘텀 + 상대 모멘텀 결합. 12개월 룩백.',
    'dual_momentum',
    '{"lookback": 252}',
    'US'
)
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- Strategy Lab: Promising Strategies Tracker
-- ============================================================
CREATE TABLE IF NOT EXISTS promising_strategies (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_name   VARCHAR(300) UNIQUE NOT NULL,
    sharpe_ratio    FLOAT,
    cagr            FLOAT,
    max_drawdown    FLOAT,
    source_paper    TEXT,
    promoted        BOOLEAN      DEFAULT FALSE,
    found_at        TIMESTAMP    DEFAULT NOW()
);

-- ============================================================
-- Risk Engine: Risk Reports
-- ============================================================
CREATE TABLE IF NOT EXISTS risk_reports (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_date     DATE         UNIQUE NOT NULL,
    dashboard_data  JSONB,
    alerts          JSONB,
    created_at      TIMESTAMP    DEFAULT NOW()
);

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_promising_sharpe ON promising_strategies(sharpe_ratio DESC);
CREATE INDEX IF NOT EXISTS idx_risk_reports_date ON risk_reports(report_date DESC);

-- ============================================================
-- Agentic Trading: Signal Storage
-- ============================================================
CREATE TABLE IF NOT EXISTS agentic_signals (
    id              SERIAL       PRIMARY KEY,
    market          VARCHAR(20)  NOT NULL,
    final_signal    VARCHAR(10)  NOT NULL,  -- BUY, SELL, HOLD
    confidence      FLOAT,
    position_size   FLOAT,
    stop_loss_pct   FLOAT,
    take_profit_pct FLOAT,
    agent_signals   JSONB,
    synthesis       TEXT,
    created_at      TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agentic_signals_market ON agentic_signals(market, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agentic_signals_date ON agentic_signals(created_at DESC);

-- ============================================================
-- Strategy Teams Registry
-- Each team is an autonomous unit competing to find alpha
-- ============================================================
CREATE TABLE IF NOT EXISTS strategy_teams (
    id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id             VARCHAR(50)  UNIQUE NOT NULL,
    team_name           VARCHAR(200) NOT NULL,
    description         TEXT,
    team_type           VARCHAR(50)  DEFAULT 'quant',  -- quant | agentic | hybrid
    is_active           BOOLEAN      DEFAULT TRUE,
    wins                INTEGER      DEFAULT 0,
    total_competitions  INTEGER      DEFAULT 0,
    best_sharpe         FLOAT,
    best_cagr           FLOAT,
    created_at          TIMESTAMP    DEFAULT NOW()
);

-- ============================================================
-- Competition Rounds — CEO evaluates all teams
-- ============================================================
CREATE TABLE IF NOT EXISTS competition_rounds (
    id                  UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    round_number        INTEGER      NOT NULL,
    test_start_date     DATE         NOT NULL,
    test_end_date       DATE         NOT NULL,
    results             JSONB,
    winner_team_id      VARCHAR(50),
    winner_strategy     VARCHAR(200),
    ceo_praise          TEXT,
    ceo_notes           TEXT,
    created_at          TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_competition_rounds_date ON competition_rounds(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_teams_wins ON strategy_teams(wins DESC);

-- Seed: initial strategy teams
INSERT INTO strategy_teams (team_id, team_name, description, team_type) VALUES
(
    'quant_strategies',
    'Quant Strategies Team',
    '전통 퀀트 전략팀. SMA/RSI/Momentum/Bollinger 등 수학적 알고리즘 기반 전략 운용.',
    'quant'
),
(
    'agentic_trading',
    'Agentic Trading Team',
    '거시경제/미시경제/뉴스/기술분석/감성 5개 AI 에이전트가 협업해 매매 신호 생성.',
    'agentic'
),
(
    'ai_hedge_fund',
    'AI Hedge Fund Team',
    'Warren Buffett, George Soros, Peter Lynch, Druckenmiller 전설적 투자자 페르소나 기반 판단.',
    'hybrid'
),
(
    'strategy_lab',
    'Strategy Lab Team',
    '논문/GitHub 최신 연구에서 전략 자동 발굴. 새 전략을 지속적으로 실험하는 R&D 팀.',
    'quant'
)
ON CONFLICT (team_id) DO NOTHING;
