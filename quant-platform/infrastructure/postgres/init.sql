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
    '전통 퀀트 전략팀. SMA/RSI/Momentum/Bollinger 등 수학적 알고리즘 기반 전략 운용. 팩터 모델 기반 유니버스 스캔 + 포트폴리오 최적화.',
    'quant'
),
(
    'agentic_trading',
    'Agentic Trading Team',
    '거시경제/미시경제/뉴스/기술분석/감성 5개 AI 에이전트가 협업해 매매 신호 생성. Bull/Bear 토론 → Risk Panel → 최종 결정.',
    'agentic'
),
(
    'ai_hedge_fund',
    'AI Hedge Fund Team',
    'Warren Buffett, George Soros, Peter Lynch, Druckenmiller 등 전설적 투자자 페르소나 AI. 가치/성장/매크로 다각도 분석.',
    'hybrid'
),
(
    'strategy_lab',
    'Strategy Lab Team',
    '논문/GitHub 최신 연구에서 전략 자동 발굴. arXiv q-fin + GitHub Trending 스캔 → 전략 추출 → 백테스트 → 유망 전략 등록.',
    'quant'
)
ON CONFLICT (team_id) DO NOTHING;

-- ============================================================
-- Factor Scores — 팩터 모델 스코어 저장
-- ============================================================
CREATE TABLE IF NOT EXISTS factor_scores (
    id                    SERIAL       PRIMARY KEY,
    symbol                VARCHAR(20)  NOT NULL,
    score_date            DATE         NOT NULL,
    market                VARCHAR(20)  DEFAULT 'ALL',
    momentum_12m1m        FLOAT,
    momentum_3m           FLOAT,
    low_vol               FLOAT,
    value_proxy           FLOAT,
    quality_proxy         FLOAT,
    momentum_12m1m_rank   FLOAT,
    momentum_3m_rank      FLOAT,
    low_vol_rank          FLOAT,
    value_proxy_rank      FLOAT,
    quality_proxy_rank    FLOAT,
    composite_score       FLOAT,
    rank                  INTEGER,
    updated_at            TIMESTAMP    DEFAULT NOW(),
    UNIQUE (symbol, score_date, market)
);

CREATE INDEX IF NOT EXISTS idx_factor_scores_date   ON factor_scores(score_date DESC);
CREATE INDEX IF NOT EXISTS idx_factor_scores_rank   ON factor_scores(score_date, rank ASC);
CREATE INDEX IF NOT EXISTS idx_factor_scores_symbol ON factor_scores(symbol);

-- ============================================================
-- Portfolio Positions — 팀별 목표 포지션
-- ============================================================
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id               SERIAL       PRIMARY KEY,
    team_id          VARCHAR(50)  NOT NULL,
    symbol           VARCHAR(20)  NOT NULL,
    target_weight    FLOAT        NOT NULL,
    last_rebalanced  DATE,
    is_active        BOOLEAN      DEFAULT TRUE,
    updated_at       TIMESTAMP    DEFAULT NOW(),
    UNIQUE (team_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_team_active ON portfolio_positions(team_id, is_active);

-- ============================================================
-- Rebalance History — 리밸런싱 이력
-- ============================================================
CREATE TABLE IF NOT EXISTS rebalance_history (
    id               SERIAL       PRIMARY KEY,
    team_id          VARCHAR(50)  NOT NULL,
    rebalance_date   DATE         NOT NULL,
    trades           JSONB,
    summary          TEXT,
    created_at       TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rebalance_history_team ON rebalance_history(team_id, created_at DESC);

-- ============================================================
-- Team Members — 팀원 구조 (월가 퀀트 역할)
-- ============================================================
CREATE TABLE IF NOT EXISTS team_members (
    id               SERIAL       PRIMARY KEY,
    team_id          VARCHAR(50)  NOT NULL,
    member_name      VARCHAR(100) NOT NULL,
    role             VARCHAR(100) NOT NULL,
    role_type        VARCHAR(50)  NOT NULL,  -- head|quant|pm|risk|data|trader|researcher
    description      TEXT,
    is_head          BOOLEAN      DEFAULT FALSE,
    is_ai_agent      BOOLEAN      DEFAULT TRUE,
    expertise_tags   TEXT[],
    created_at       TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id);

-- ============================================================
-- Seed: Team Members (월가 퀀트 역할 구조)
-- ============================================================

-- Quant Strategies Team
INSERT INTO team_members (team_id, member_name, role, role_type, description, is_head, expertise_tags) VALUES
('quant_strategies', '김민준', 'CIO / 팀장', 'head',
 '팀 전략 총괄. 팩터 알파 선별 및 포트폴리오 방향성 결정. 전통 퀀트 전략 시그마 관리.',
 TRUE, ARRAY['factor_model','portfolio_construction','risk_management']),
('quant_strategies', '이지원', '퀀트 리서처', 'quant',
 '알파 팩터 발굴 및 검증. Momentum/Value/Quality 팩터 연구. 시계열 분석 및 백테스트 설계.',
 FALSE, ARRAY['momentum','value','factor_research','backtesting']),
('quant_strategies', '박서준', '포트폴리오 매니저', 'pm',
 '팩터 스코어 기반 포트폴리오 구성. Inverse-vol 가중치 계산. 월별 리밸런싱 실행.',
 FALSE, ARRAY['portfolio_optimization','rebalancing','position_sizing']),
('quant_strategies', '최아린', '리스크 매니저', 'risk',
 'VaR/CVaR 모니터링. 드로우다운 제한 관리. 섹터 익스포저 중립화. 리스크 리포트 작성.',
 FALSE, ARRAY['risk_management','var','drawdown','sector_neutrality'])
ON CONFLICT DO NOTHING;

-- Agentic Trading Team
INSERT INTO team_members (team_id, member_name, role, role_type, description, is_head, expertise_tags) VALUES
('agentic_trading', '정하은', 'Head of Agentic / 팀장', 'head',
 '멀티 에이전트 오케스트레이션 총괄. Bull/Bear 토론 심판. 최종 매매 신호 승인.',
 TRUE, ARRAY['multi_agent','orchestration','signal_generation']),
('agentic_trading', '강지훈', '매크로 분석가', 'researcher',
 '금리/VIX/환율/원자재 글로벌 매크로 분석. Fed 정책 영향도 모델링. 시장 위험 선행 지표.',
 FALSE, ARRAY['macro','rates','vix','fx','commodities']),
('agentic_trading', '윤채원', '기술 분석가', 'quant',
 'MA/RSI/MACD/볼린저밴드 기술적 분석. 패턴 인식 및 추세 판단. 진입/청산 타이밍.',
 FALSE, ARRAY['technical_analysis','chart_patterns','momentum_signals']),
('agentic_trading', '임도현', '뉴스/감성 분석가', 'researcher',
 'RSS/뉴스 실시간 감성 분석(Claude AI). 소셜 미디어 센티먼트. 공시/이벤트 임팩트.',
 FALSE, ARRAY['nlp','sentiment','news_analysis','event_driven']),
('agentic_trading', '손유나', '리스크 패널', 'risk',
 '포지션 사이즈 결정. 손절/익절 수준 설정. 변동성 조정 포지셔닝.',
 FALSE, ARRAY['position_sizing','stop_loss','volatility_targeting'])
ON CONFLICT DO NOTHING;

-- AI Hedge Fund Team
INSERT INTO team_members (team_id, member_name, role, role_type, description, is_head, expertise_tags) VALUES
('ai_hedge_fund', '오유진', 'CIO / 팀장', 'head',
 'AI 투자 철학 총괄. 투자자 페르소나 앙상블 관리. 포트폴리오 최종 결정.',
 TRUE, ARRAY['investment_strategy','ai_ensemble','hedge_fund']),
('ai_hedge_fund', '한승민', '가치투자 분석가', 'researcher',
 'Buffett/Graham/Munger 철학 구현. 내재가치 계산. 안전마진 분석. PBR/PER 밸류에이션.',
 FALSE, ARRAY['value_investing','intrinsic_value','buffett','graham']),
('ai_hedge_fund', '신예린', '글로벌 매크로 분석가', 'researcher',
 'Soros/Druckenmiller 철학 구현. 글로벌 자금 흐름. 환율/채권/주식 상관관계.',
 FALSE, ARRAY['macro','soros','druckenmiller','reflexivity']),
('ai_hedge_fund', '권민호', '성장주 분석가', 'researcher',
 'Lynch/Wood 철학 구현. 고성장 기업 발굴. PEG 분석. 혁신 기업 스크리닝.',
 FALSE, ARRAY['growth_investing','lynch','cathie_wood','innovation']),
('ai_hedge_fund', '배지수', '리스크 매니저', 'risk',
 '포트폴리오 상관관계 분석. 꼬리 리스크 헤지. 변동성 조정 포지션 관리.',
 FALSE, ARRAY['tail_risk','correlation','hedging','volatility'])
ON CONFLICT DO NOTHING;

-- Strategy Lab Team
INSERT INTO team_members (team_id, member_name, role, role_type, description, is_head, expertise_tags) VALUES
('strategy_lab', '조승우', 'Head of Research / 팀장', 'head',
 'R&D 방향성 결정. 논문 선별 기준 수립. 신규 전략팀 등록 승인.',
 TRUE, ARRAY['research','strategy_discovery','academic']),
('strategy_lab', '문지우', 'arXiv 리서처', 'researcher',
 'arXiv q-fin/cs.LG 논문 스캔. 전략 아이디어 추출. 구현 가능성 평가.',
 FALSE, ARRAY['arxiv','academic_research','nlp','strategy_extraction']),
('strategy_lab', '고아라', '백테스터', 'quant',
 '추출된 전략 Python 구현. Point-in-time 백테스트 실행. Sharpe/MDD 성과 분석.',
 FALSE, ARRAY['backtesting','python','quantitative_finance']),
('strategy_lab', '나현수', 'GitHub 스카우터', 'researcher',
 'GitHub Trending 퀀트 레포 스캔. 오픈소스 전략 분석. 신규 기술 트렌드 모니터링.',
 FALSE, ARRAY['github','open_source','trend_analysis'])
ON CONFLICT DO NOTHING;
