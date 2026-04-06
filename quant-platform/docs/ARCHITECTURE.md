# QuantLab Capital — 아키텍처 문서

## 시스템 전체 구성도

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                   │
│                                                                             │
│   Next.js 14 Frontend (:3000)        Nginx Reverse Proxy (:80)              │
│   ├── / (메인 대시보드)               ├── /api → Backend                     │
│   ├── /company (회사 현황)            └── / → Frontend                       │
│   ├── /teams/{id} (팀 상세)                                                 │
│   ├── /portfolio (팩터/포지션)                                               │
│   └── /backtests (백테스트)                                                  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ HTTP / WebSocket
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                              API LAYER                                      │
│                                                                             │
│   FastAPI Backend (:8000)                                                   │
│   ├── /api/strategies/        전략 CRUD                                     │
│   ├── /api/backtests/         백테스트 실행/조회                              │
│   ├── /api/company/           회사 현황 (경쟁, 매매일지, 기억)                │
│   ├── /api/portfolio/         팩터 스코어, 포트폴리오, 리밸런싱               │
│   ├── /api/research/          논문/전략 발굴                                 │
│   └── /health                 헬스체크                                       │
│                                                                             │
│   Celery Workers (3개)                  Celery Beat (스케줄러)               │
│   ├── worker-backtest (4 concurrency)   ├── 팩터 엔진 (월 07:00)             │
│   ├── worker-research (2 concurrency)   ├── 리밸런싱 (월 07:30)              │
│   └── worker-data (2 concurrency)       └── 기타 주기적 작업                 │
│                                                                             │
│   Flower (:5555) — Celery 모니터링                                           │
└────┬──────────────┬──────────────┬──────────────────────────────────────────┘
     │              │              │
     ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐
│ Postgres │  │  Redis   │  │  Kafka   │
│  :5432   │  │  :6379   │  │  :9092   │
│TimescaleDB│  │ Cache +  │  │ Event    │
│          │  │ Broker   │  │ Stream   │
└─────────┘  └──────────┘  └──────────┘
     ▲              ▲
     │              │
┌────┴──────────────┴─────────────────────────────────────────────────────────┐
│                         STRATEGY TEAM SERVICES                              │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│   │ Agentic Trading │  │ TradingAgents   │  │ AI Hedge Fund   │            │
│   │ (:quant_agentic)│  │ (:quant_trading)│  │ (:quant_ai_hf)  │            │
│   │                 │  │                 │  │                 │            │
│   │ 5 Analysts +    │  │ 4 Analysts      │  │ 8 Personas      │            │
│   │ 4 Personas +    │  │ Bull/Bear (2R)  │  │ Risk Manager    │            │
│   │ Bull/Bear Debate│  │ Risk Panel (3)  │  │ Portfolio Mgr   │            │
│   │ Risk Panel      │  │ Trader Agent    │  │ Claude Enhanced │            │
│   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘            │
│            │                    │                     │                     │
│            └────────────────────┼─────────────────────┘                     │
│                                 │ agentic_signals 테이블에 저장              │
│                                 ▼                                           │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│   │ Strategy Lab    │  │ Paper Research  │  │ CEO Agent       │            │
│   │ arXiv + GitHub  │  │ arXiv Crawler   │  │ 매주 금 17:00   │            │
│   │ 신팀 등록       │  │ 논문 분석       │  │ 팀 경쟁 평가    │            │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐                                 │
│   │ Data Pipeline   │  │ Risk Engine     │                                 │
│   │ 시장 데이터     │  │ VaR, MDD 감시   │                                 │
│   │ KOSPI/KOSDAQ/US │  │ 포트폴리오 리스크│                                 │
│   └─────────────────┘  └─────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ML / MONITORING LAYER                               │
│                                                                             │
│   MLflow (:5000)         Grafana (:3001)       Prometheus (:9090)           │
│   전략 실험 추적          인프라 대시보드         메트릭 수집                  │
│                                                                             │
│   Jupyter Lab (:8888)    MinIO (:9000)                                      │
│   리서치 노트북           아티팩트 저장소                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 서비스 간 데이터 흐름

### 1. 시장 데이터 흐름
```
외부 API (pykrx, yfinance, FinanceDataReader)
    │
    ▼
Data Pipeline → market_data (TimescaleDB)
    │
    ├──→ Factor Engine → factor_scores → Portfolio Optimizer → portfolio_positions
    ├──→ Backtest Engine (prices DataFrame)
    ├──→ Agentic Trading (분석용)
    ├──→ TradingAgents Team (분석용)
    └──→ AI Hedge Fund Team (분석용)
```

### 2. 매매 신호 흐름
```
3개 전략팀 (독립 실행)
    │
    ├── Agentic Trading → agentic_signals (agent_signals: JSONB)
    ├── TradingAgents   → agentic_signals (synthesis: "[TradingAgents] ...")
    └── AI Hedge Fund   → agentic_signals (synthesis: "[AI-HF] ...")
    │
    ▼
CEO Agent (금요일)
    → 모든 신호 수집 → 복합 점수 → competition_rounds → 대시보드
```

### 3. 기억(Memory) 흐름
```
각 전략팀 에이전트
    │
    ├── MemoryManager.remember_insight() → agent_memories (PostgreSQL)
    ├── TradeJournal.log_signal() → trade_journal
    │
    ├── MemoryManager.build_context_prompt() → 분석 시 과거 교훈 반영
    └── TradeJournal.build_performance_summary() → 과거 성과 참조
```

---

## 핵심 서비스 상세

### Backend (FastAPI)

```
services/backend/
├── main.py                           # FastAPI app 진입점
├── app/
│   ├── database.py                   # SQLAlchemy 세션
│   ├── models/                       # ORM 모델
│   │   ├── strategy.py
│   │   └── backtest.py
│   ├── routers/                      # API 엔드포인트
│   │   ├── strategies.py
│   │   ├── backtests.py
│   │   ├── company.py
│   │   ├── research.py
│   │   └── portfolio.py
│   ├── services/                     # 비즈니스 로직
│   │   ├── backtest_engine.py        # 백테스트 엔진 (point-in-time)
│   │   ├── strategy_library.py       # 11개 전략 구현
│   │   ├── factor_engine.py          # 팩터 계산 + 포트폴리오 최적화
│   │   └── data_service.py           # 데이터 조회
│   └── workers/                      # Celery 비동기 작업
│       ├── celery_app.py             # Beat 스케줄 정의
│       └── tasks.py                  # 백테스트, 팩터 엔진 태스크
```

### TradingAgents Team

```
services/trading-agents-team/
├── main.py                           # TradingAgentsSystem 오케스트레이터
│   ├── run_analysis()                # 시장 분석 실행
│   ├── _analyze_market()             # Analyst → Debate → Risk → Trader
│   ├── _save_signal()                # DB 저장
│   └── _save_to_journal()            # 기억 저장
├── agents/
│   ├── analysts.py                   # 4대 분석가
│   │   ├── FundamentalsAnalyst       # ROE, 수익안정성, 밸류에이션
│   │   ├── MarketAnalyst             # SMA/EMA/RSI/MACD/BB/ATR
│   │   ├── NewsAnalyst               # Claude + 키워드 fallback
│   │   └── SentimentAnalyst          # VIX Fear & Greed
│   ├── debate.py                     # Bull/Bear 토론 엔진
│   │   ├── BullResearcher            # 성장/기회/모멘텀 관점
│   │   ├── BearResearcher            # 리스크/위기/하락 관점
│   │   └── DebateEngine              # 2라운드 토론 + Judge 종합
│   ├── risk_panel.py                 # 3인 리스크 토론
│   │   ├── CONSERVATIVE              # 자본 보존 최우선
│   │   ├── NEUTRAL                   # 리스크/리워드 균형
│   │   ├── AGGRESSIVE                # 수익 극대화
│   │   └── RiskPanel                 # 합의 도출
│   └── trader.py                     # 최종 거래 에이전트
│       ├── TradeDecision             # BUY/SELL/HOLD 데이터클래스
│       └── TraderAgent               # 가중투표 + Claude 결정
```

### AI Hedge Fund Team

```
services/ai-hedge-fund-team/
├── main.py                           # AIHedgeFundSystem 오케스트레이터
│   ├── run_analysis()                # 시장 분석 실행
│   ├── _analyze_market()             # Persona → Risk → PM
│   ├── _fetch_price_data()           # DB → API fallback
│   ├── _save_signal()                # DB 저장
│   └── _save_to_journal()            # 기억 저장
├── agents/
│   ├── personas.py                   # 8인 투자자 페르소나
│   │   ├── BenGrahamAgent            # 0-16점: 안전마진+재무건전성+밸류에이션
│   │   ├── WarrenBuffettAgent        # 0-12점: Owner Earnings+Moat+자본효율
│   │   ├── CharlieMungerAgent        # 0-10점: 품질+성장+합리성
│   │   ├── GeorgeSorosAgent          # 0-10점: 매크로+반사성+체제전환
│   │   ├── PeterLynchAgent           # 0-10점: PEG+이해도+적정가격
│   │   ├── MichaelBurryAgent         # 0-10점: 역발상+딥밸류+평균회귀
│   │   ├── CathieWoodAgent           # 0-10점: 파괴적혁신+폭발성장+모멘텀
│   │   └── NassimTalebAgent          # 0-10점: 꼬리리스크+안티프래질+바벨
│   ├── risk_manager.py               # 변동성-상관관계 리스크
│   │   └── RiskManager               # Vol-adjusted limits + correlation
│   └── portfolio_manager.py          # 최종 포트폴리오 결정
│       └── PortfolioManager          # 가중 컨센서스 + Claude 강화
```

---

## 데이터베이스 스키마 (ERD)

```
┌────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  strategies    │     │  backtest_runs   │     │   market_data      │
│────────────────│     │──────────────────│     │────────────────────│
│ id (PK)        │◄────│ strategy_id (FK) │     │ symbol + date (PK) │
│ name           │     │ status           │     │ open, high, low    │
│ strategy_type  │     │ start/end_date   │     │ close, volume      │
│ parameters     │     │ initial_capital  │     │ market             │
│ market         │     │ results (JSONB)  │     │ (TimescaleDB)      │
│ is_active      │     │ equity_curve     │     └────────────────────┘
└────────────────┘     │ trades (JSONB)   │
                       └──────────────────┘

┌────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│ strategy_teams │     │ competition_     │     │  team_members      │
│────────────────│     │    rounds        │     │────────────────────│
│ team_id (PK)   │◄────│ winner_team_id   │     │ team_id            │
│ team_name      │     │ round_number     │     │ member_name        │
│ team_type      │     │ team_scores      │     │ role               │
│ wins           │     │ ceo_praise       │     │ role_type           │
│ best_sharpe    │     │ ceo_pressure     │     │ expertise_tags[]   │
│ best_cagr      │     └──────────────────┘     └────────────────────┘
└────────────────┘

┌────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│ agentic_       │     │ factor_scores    │     │ portfolio_         │
│   signals      │     │──────────────────│     │    positions       │
│────────────────│     │ symbol           │     │────────────────────│
│ market         │     │ score_date       │     │ team_id            │
│ final_signal   │     │ momentum_12m1m   │     │ symbol             │
│ confidence     │     │ low_vol          │     │ target_weight      │
│ position_size  │     │ value_proxy      │     │ current_weight     │
│ agent_signals  │     │ quality_proxy    │     │ factor_score       │
│  (JSONB)       │     │ composite_score  │     └────────────────────┘
│ synthesis      │     │ rank             │
└────────────────┘     └──────────────────┘
```

---

## 전략 알고리즘 상세

### TradingAgents Debate 전략 (백테스트 버전)

```
For each rebalance date (weekly):
  For each symbol:
    1. Momentum Signal (40%):
       - 1M return × 0.4 + 3M return × 0.6
       - Clip to [-1, 1]

    2. Mean Reversion Signal (30%):
       - Z-score = (Price - SMA50) / STD50
       - Signal = clip(-Z/3, -1, 1)  # 과매도 = 매수

    3. Volatility Regime Signal (30%):
       - Vol ratio = Vol20d / Vol60d
       - Signal = clip(1 - ratio, -1, 1)  # 저변동성 = 추세 추종

    4. Ensemble:
       - score = 0.4 × momentum + 0.3 × mean_rev + 0.3 × vol_regime
       - BUY if score ≥ 0.20, SELL if score ≤ -0.20
       - Equal-weight within long/short baskets
```

### AI Hedge Fund Persona 전략 (백테스트 버전)

```
For each rebalance date (monthly):
  For each symbol:
    1. Value Score (30% — Graham/Buffett/Munger):
       - (1 - price/52w_high) × 2 - annualized_vol

    2. Growth Score (25% — Lynch/C.Wood):
       - 3M_return × 3 + 1Y_return × 0.5

    3. Macro Score (20% — Soros):
       - Price > SMA50? (+1/-1) + SMA50 > SMA200? (+1/-1)

    4. Contrarian Score (15% — Burry):
       - (50 - RSI14) / 50, clipped

    5. Risk Score (10% — Taleb):
       - Skew × 0.5 - (Kurtosis - 3) × 0.1

    6. Composite = weighted sum
       - Top 20% → LONG (equal weight)
       - Bottom 20% → SHORT (equal weight)
```

---

## 배포 / 운영

### 개발 환경
```bash
docker compose up -d              # 전체 기동
docker compose logs -f backend    # 로그 확인
docker compose restart backend    # 서비스 재시작
```

### 프로덕션 고려사항
- `.env`에서 모든 기본 비밀번호 변경
- `ENVIRONMENT=production` 설정
- Nginx에 SSL/TLS 추가
- PostgreSQL 백업 자동화 (`pg_dump`)
- Grafana 알림 설정 (MDD > 15% 등)

### 새 전략팀 추가 방법
1. `services/new-team/` 디렉토리 생성
2. `main.py` — 분석 로직 + APScheduler
3. `Dockerfile` + `requirements.txt`
4. `docker-compose.yml`에 서비스 추가
5. `init.sql` (또는 직접 SQL)로 팀 등록
6. `strategy_library.py`에 백테스트 전략 추가 (선택)

### 환경 이전 (맥 → 맥)
```bash
git clone https://github.com/benny1020/trading-playground
cd trading-playground/quant-platform
cp /path/to/.env .     # .env 수동 복사
docker compose up -d   # 끝
```
DB 스키마 + 시드 데이터는 `init.sql`이 첫 기동 시 자동 생성.
