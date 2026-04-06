# QuantLab Capital — AI 퀀트 자산운용사

> **Mission: 여러 전략팀이 경쟁하며 수익을 낸다. 우리는 AI를 곁들인 퀀트 자산운용사다.**

```
docker compose up -d   # 전체 시스템 가동
```

---

## 개요

QuantLab Capital은 여러 AI 전략팀이 동시에 운용되며 서로 경쟁하는 자율적 퀀트 자산운용 플랫폼입니다. Two Sigma, Citadel, WorldQuant의 리서치 파이프라인을 참고해 설계되었습니다.

### 핵심 원칙

| 원칙 | 내용 |
|------|------|
| **경쟁** | 모든 전략팀은 매주 백테스트 결과로 순위를 겨룬다 |
| **Point-in-time** | 백테스팅 시 미래 데이터 절대 사용 금지. 당시 시점 데이터만 사용 |
| **자율화** | Strategy Lab이 논문/GitHub에서 새 전략팀을 자동으로 발굴·등록 |
| **투명성** | CEO Agent가 매주 결과를 평가하고 승자를 공개적으로 칭찬 |
| **수익 우선** | 모든 팀의 목표는 하나 — 실제 수익 창출 |

---

## 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────────────┐
│                         QuantLab Capital                             │
│                      AI 퀀트 자산운용사 (18명, 5개 전략팀)             │
└──────────────────────────────────────────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
  ┌──────▼──────┐     ┌────────▼────────┐     ┌───────▼──────────┐
  │  COMMON     │     │ STRATEGY TEAMS  │     │  GOVERNANCE      │
  │  INFRA      │     │ (5팀 경쟁)      │     │                  │
  │             │     │                 │     │  CEO Agent       │
  │ Data        │◄────│ Quant Strats    │     │  (매주 평가)     │
  │ Pipeline    │     │                 │     │                  │
  │             │◄────│ Agentic Trading │     │  Strategy Lab    │
  │ Factor      │     │                 │     │  (팀 신설)       │
  │ Engine      │◄────│ TradingAgents   │     │                  │
  │             │     │  Debate Team    │     │  Risk Engine     │
  │ Backtest    │◄────│                 │     │  (포트폴리오     │
  │ Engine      │     │ AI Hedge Fund   │     │   리스크 관리)   │
  │             │◄────│                 │     │                  │
  │ Portfolio   │     │ Strategy Lab    │     │                  │
  │ Optimizer   │     │                 │     │                  │
  │             │     │ [New Teams...]  │     │                  │
  └─────────────┘     └─────────────────┘     └──────────────────┘
```

---

## 전략팀 상세 (5개 팀, 18명)

### 1. Quant Strategies Team (`quant_strategies`)
| 역할 | 이름 | 전문분야 |
|------|------|----------|
| CIO (팀장) | 김민준 | Factor Models, Statistical Arbitrage |
| Quant Researcher | 이지원 | Alpha Research, Signal Processing |
| Portfolio Manager | 박서준 | Portfolio Construction, Execution |
| Risk Manager | 최아린 | Risk Modeling, VaR/CVaR |

- **접근법**: 전통 수리 알고리즘 — SMA, RSI, Momentum, Bollinger, 이중모멘텀, MACD, Factor Model
- **Factor Engine**: Momentum12M-1M(35%) + Momentum3M(15%) + LowVol(25%) + Value(15%) + Quality(10%)
- **포트폴리오**: Inverse-volatility 가중, MAX 15% / MIN 1% 제약

### 2. Agentic Trading Team (`agentic_trading`)
| 역할 | 이름 | 전문분야 |
|------|------|----------|
| Head (팀장) | 정하은 | Multi-Agent Orchestration |
| Macro Analyst | 강지훈 | 금리, VIX, 환율 |
| Technical Analyst | 윤채원 | 5-Strategy Ensemble |
| News/Sentiment | 임도현 | NLP, 감성분석 |
| Risk Panel Lead | 손유나 | 리스크 토론 |

- **접근법**: 5개 AI 에이전트(Macro, Micro, News, Technical, Sentiment) + 투자자 페르소나(Buffett/Soros/Lynch/Druckenmiller)
- **Technical Analyst 5-전략 앙상블**: Trend(25%) + MeanReversion(20%) + Momentum(25%) + Volatility(15%) + StatArb(15%)
- **프로세스**: 분석 → Bull/Bear 토론 → Risk Panel → 최종 BUY/SELL/HOLD

### 3. TradingAgents Debate Team (`trading_agents`) — NEW
| 역할 | 이름 | 전문분야 |
|------|------|----------|
| Head (팀장) | 김태양 | Multi-Agent, Debate Systems |
| Bull Researcher | 이하람 | Growth Analysis, Upside Catalysts |
| Bear Researcher | 박솔아 | Risk Analysis, Downside Scenarios |
| Judge & Risk Lead | 최민서 | Arbitration, Capital Preservation |
| Trader Agent | 정지안 | Execution, Final Decision |

- **접근법**: TradingAgents 레포 패턴 — 멀티라운드 Bull/Bear 토론
- **아키텍처**:
```
Analyst Layer (4인) → Bull/Bear Debate (2 rounds) → Judge Synthesis
    → Risk Panel (Conservative/Neutral/Aggressive 3-way) → Trader (최종 결정)
```
- **4대 분석가**: Fundamentals(가치+수익안정성), Market/Technical(SMA/RSI/MACD/BB/ATR), News(Claude+키워드), Sentiment(VIX Fear&Greed)
- **백테스트 전략**: `trading_agents_debate` — 모멘텀(40%)+평균회귀(30%)+변동성체제(30%) 앙상블
- **스케줄**: 08:00 KR, 21:30 US

### 4. AI Hedge Fund Team (`ai_hedge_fund`) — NEW
| 역할 | 이름 | 전문분야 |
|------|------|----------|
| CIO (팀장) | 오유진 | Value Investing, Multi-Persona Synthesis |
| Value Analyst | 한승민 | Graham/Buffett/Munger — Deep Value, Margin of Safety |
| Macro Strategist | 신예린 | Soros — Reflexivity, FX, Macro Trends |
| Growth Analyst | 권민호 | Lynch/C.Wood — PEG, Disruptive Innovation |
| Risk & Tail Manager | 배지수 | Taleb — Antifragility, Black Swan, Barbell |
| Contrarian Analyst | 임준혁 | Burry — Short Selling, Contrarian Thesis |

- **접근법**: ai-hedge-fund 레포 패턴 — 8인 전설적 투자자 결정론적 스코어링 + Claude 강화
- **8인 페르소나**:
  - **Ben Graham** (0-16점): 안전마진, 수익안정성, 재무건전성, 밸류에이션
  - **Warren Buffett** (0-12점): Owner Earnings, 경쟁우위(Moat), 자본효율성
  - **Charlie Munger** (0-10점): 품질, 장기복리성장, 합리성
  - **George Soros** (0-10점): 매크로 트렌드, 반사성(Reflexivity), 체제전환
  - **Peter Lynch** (0-10점): PEG Ratio, 이해가능한 성장, 적정가격
  - **Michael Burry** (0-10점): 역발상, 딥밸류, 과매도 평균회귀
  - **Cathie Wood** (0-10점): 파괴적 혁신, 폭발적 성장, 모멘텀
  - **Nassim Taleb** (0-10점): 꼬리리스크, 안티프래질, 바벨전략
- **리스크 매니저**: 변동성-상관관계 기반 포지션 한도 (Vol < 12% → 25% limit, Vol > 35% → 8% limit)
- **가중 투표**: Graham(15%) + Buffett(15%) + Soros(15%) + Burry(15%) + Munger(10%) + Lynch(10%) + C.Wood(10%) + Taleb(10%)
- **백테스트 전략**: `ai_hedge_fund_persona` — 가치(30%)+성장(25%)+매크로(20%)+역발상(15%)+리스크(10%)
- **스케줄**: 08:15 KR, 21:45 US

### 5. Strategy Lab Team (`strategy_lab`)
| 역할 | 이름 | 전문분야 |
|------|------|----------|
| Head (팀장) | 조승우 | Research Automation |
| arXiv Researcher | 문지우 | NLP, Paper Analysis |
| Backtester | 고아라 | Walk-forward Validation |
| GitHub Scout | 나현수 | Open Source Intelligence |

- **접근법**: arXiv 논문 + GitHub Trending에서 자동 전략 발굴 → 유망하면 신팀 등록
- **스캔 주기**: 월(GitHub), 화/목(arXiv), 금(트렌드보고서)

---

## 경쟁 시스템

### 복합 점수 (Composite Score)
```
Score = Sharpe × 0.4 + CAGR(%) × 0.3 - |MDD|(%) × 0.3
```

### Point-in-Time 정책 (절대 규칙)
> 백테스팅은 당시 시점에서 알 수 있었던 데이터만 사용한다.
- `end_date` 이후의 모든 데이터는 BacktestEngine에서 자동 차단
- 미래 주가, 미래 실적, 미래 뉴스 절대 사용 불가

---

## 백테스트 가능 전략 (11개)

| 전략 | 유형 | 팀 | 설명 |
|------|------|-----|------|
| `sma_crossover` | Trend | Quant | SMA 20/60 골든크로스 |
| `rsi_mean_reversion` | Mean-Rev | Quant | RSI 30↓매수, 70↑매도 |
| `bollinger_band` | Mean-Rev | Quant | BB 하단 매수, 상단 매도 |
| `momentum` | Momentum | Quant | 12개월 수익률 상위 N종목 |
| `dual_momentum` | Momentum | Quant | Antonacci 절대+상대 모멘텀 |
| `pairs_trading` | StatArb | Quant | 스프레드 Z-score 페어트레이딩 |
| `macd` | Trend | Quant | MACD 시그널 크로스 |
| `breakout` | Trend | Quant | Donchian 채널 돌파 |
| `factor_model` | Multi-Factor | Quant | 모멘텀+밸류 팩터 랭킹 |
| `trading_agents_debate` | Ensemble | TradingAgents | 모멘텀+평균회귀+변동성체제 앙상블 |
| `ai_hedge_fund_persona` | Multi-Persona | AI Hedge Fund | 8인 전설 투자자 컨센서스 |

---

## 기술 스택

```
Frontend:   Next.js 14 (TypeScript, Tailwind, Recharts)         — :3000
Backend:    FastAPI + Celery (Python 3.11)                       — :8000
Database:   PostgreSQL 16 + TimescaleDB                          — :5432
Cache:      Redis 7                                              — :6379
Streaming:  Apache Kafka                                         — :9092
Storage:    MinIO                                                — :9000
MLflow:     Experiment Tracking                                  — :5000
Jupyter:    Research Notebooks                                   — :8888
Grafana:    Monitoring Dashboard                                 — :3001
Prometheus: Metrics                                              — :9090
Flower:     Celery Task Monitor                                  — :5555
Nginx:      Reverse Proxy                                        — :80
```

### Docker Services (20개)

| 카테고리 | 서비스 | 컨테이너명 |
|----------|--------|------------|
| **인프라** | PostgreSQL, Redis, Kafka, Zookeeper, MinIO | quant_postgres, quant_redis, ... |
| **코어 API** | Backend, Worker×3, Beat, Flower | quant_backend, quant_worker_* |
| **프론트엔드** | Next.js | quant_frontend |
| **데이터** | Data Pipeline | quant_data_pipeline |
| **전략팀** | Agentic Trading | quant_agentic_trading |
| **전략팀** | TradingAgents Debate | quant_trading_agents |
| **전략팀** | AI Hedge Fund | quant_ai_hedge_fund |
| **연구** | Strategy Lab, Paper Research | quant_strategy_lab, quant_paper_research |
| **거버넌스** | CEO Agent, Risk Engine | quant_ceo_agent, quant_risk_engine |
| **ML/모니터링** | MLflow, Jupyter, Grafana, Prometheus, Nginx | quant_mlflow, ... |

---

## 빠른 시작

### 사전 요구사항
- Docker Desktop
- Anthropic API Key

### 설치 및 실행

```bash
# 1. 저장소 클론
git clone https://github.com/benny1020/trading-playground
cd trading-playground/quant-platform

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 ANTHROPIC_API_KEY 설정

# 3. 전체 시스템 가동
docker compose up -d

# 4. 상태 확인
docker compose ps
```

### 접속 URL

| 서비스 | URL |
|--------|-----|
| 메인 대시보드 | http://localhost:3000 |
| 팀 상세 | http://localhost:3000/teams/{team_id} |
| 포트폴리오/팩터 | http://localhost:3000/portfolio |
| API 문서 | http://localhost:8000/docs |
| MLflow | http://localhost:5000 |
| Jupyter Lab | http://localhost:8888 |
| Grafana | http://localhost:3001 |
| Celery Flower | http://localhost:5555 |

---

## 데이터베이스 스키마

```
strategies           — 전략 정의 (11개 등록)
backtest_runs        — 백테스트 실행 기록
market_data          — OHLCV 시장 데이터 (TimescaleDB hypertable)
stock_info           — 종목 메타데이터
papers               — arXiv/SSRN 논문
trend_reports        — 주간 트렌드 분석
promising_strategies — 유망 전략 트래커
risk_reports         — 리스크 보고서
agentic_signals      — AI 매매 신호 (BUY/SELL/HOLD)
strategy_teams       — 팀 레지스트리 (5개 팀)
competition_rounds   — CEO 경쟁 평가 결과
factor_scores        — 멀티팩터 스코어 (Momentum, Value, Quality, LowVol)
portfolio_positions  — 팀별 포트폴리오 포지션
rebalance_history    — 리밸런싱 이력
team_members         — 팀원 레지스트리 (18명)
```

---

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Claude AI API 키 (필수) | — |
| `POSTGRES_USER` | DB 사용자 | `quant` |
| `POSTGRES_PASSWORD` | DB 비밀번호 | `quantpass` |
| `POSTGRES_DB` | DB 이름 | `quantdb` |
| `MINIO_ACCESS_KEY` | MinIO 사용자 | `minioadmin` |
| `MINIO_SECRET_KEY` | MinIO 비밀번호 | `minioadmin` |
| `GRAFANA_PASSWORD` | Grafana 비밀번호 | `admin` |
| `JUPYTER_TOKEN` | Jupyter 토큰 | `quantlab2024` |

---

## 참고 레포지토리

- [TradingAgents](https://github.com/TauricResearch/TradingAgents) — Bull/Bear 토론 기반 에이전트
- [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) — 전설적 투자자 페르소나

---

## License

MIT
