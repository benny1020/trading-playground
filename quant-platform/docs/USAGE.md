# QuantLab Capital — 사용법 가이드

## 목차
1. [빠른 시작](#빠른-시작)
2. [전체 시스템 흐름](#전체-시스템-흐름)
3. [팀별 역할 및 동작 방식](#팀별-역할-및-동작-방식)
4. [대시보드 사용법](#대시보드-사용법)
5. [에이전트 기억 시스템](#에이전트-기억-시스템)
6. [CEO 경쟁 시스템](#ceo-경쟁-시스템)
7. [팩터 엔진 & 포트폴리오](#팩터-엔진--포트폴리오)
8. [백테스팅 정책 (Point-in-Time)](#백테스팅-정책)
9. [API 레퍼런스](#api-레퍼런스)

---

## 빠른 시작

```bash
# 1. 저장소 클론
git clone https://github.com/benny1020/trading-playground
cd trading-playground/quant-platform

# 2. 환경 변수 설정 (필수: ANTHROPIC_API_KEY)
cp .env.example .env
nano .env   # ANTHROPIC_API_KEY=sk-ant-xxxx 입력

# 3. 전체 시스템 가동
docker compose up -d

# 4. 상태 확인
docker compose ps
```

**접속 URL**
| 서비스 | URL | 용도 |
|--------|-----|------|
| 메인 대시보드 | http://localhost:3000 | 회사 전체 현황 |
| 팀 상세 | http://localhost:3000/teams/{team_id} | 팀원, 포트폴리오, 리밸런싱 |
| 포트폴리오/팩터 | http://localhost:3000/portfolio | 팩터 스코어 랭킹, 포지션 현황 |
| 회사 현황 상세 | http://localhost:3000/company | 팀 경쟁, 매매일지, 기억 |
| API 문서 | http://localhost:8000/docs | FastAPI Swagger |
| MLflow | http://localhost:5000 | 전략 실험 추적 |
| Jupyter Lab | http://localhost:8888 | 리서치 노트북 |
| Grafana | http://localhost:3001 | 인프라 모니터링 |
| Celery Flower | http://localhost:5555 | 작업 큐 모니터링 |

---

## 전체 시스템 흐름

```
매일 자동으로 돌아가는 파이프라인:

[월 07:00] Celery Beat — 팩터 엔진 실행
    └→ 전 종목 팩터 스코어 계산 (Momentum, Value, Quality, LowVol)
    └→ factor_scores 테이블 저장

[월 07:30] Celery Beat — 포트폴리오 리밸런싱
    └→ Inverse-vol 가중 포트폴리오 구성
    └→ 목표 vs 현재 비교 → 리밸런싱 오더

[월 09:00] Strategy Lab — GitHub Trending 스캔
    └→ 퀀트/AI 관련 레포 발견 → Claude 분석 → 새 팀 등록

[화,목 10:00] Strategy Lab — arXiv 논문 수집
    └→ q-fin / cs.LG 논문 → 전략 아이디어 추출 → 백테스트 자동 제출

[평일 08:00] TradingAgents Team — KOSPI/KOSDAQ 분석
    └→ 4대 분석가 → Bull/Bear 토론 (2 rounds) → Judge
    └→ Risk Panel (보수/중립/공격 3-way) → Trader 최종 결정

[평일 08:15] AI Hedge Fund Team — KOSPI/KOSDAQ 분석
    └→ 8인 전설 투자자 결정론적 스코어링
    └→ 가중 컨센서스 → Risk Manager → PM 최종 결정

[평일 08:30] Agentic Trading — KOSPI/KOSDAQ 분석
    └→ 5개 에이전트 + 페르소나 분석
    └→ Bull/Bear 토론 → Risk Panel → 최종 결정

[평일 18:00] Data Pipeline — 시장 데이터 업데이트
    └→ KOSPI/KOSDAQ 종가 수집 → TimescaleDB 저장

[평일 21:30] TradingAgents Team — US 시장 분석
[평일 21:45] AI Hedge Fund Team — US 시장 분석
[평일 22:00] Agentic Trading — US 시장 분석

[금 16:00] Strategy Lab — 트렌드 분석 보고서
[금 17:00] CEO Agent — Competition Round
    └→ 모든 팀 최근 90일 백테스트 수집 → 복합 점수 랭킹
    └→ Claude → 승자 칭찬 + 하위팀 압박 메시지
```

---

## 팀별 역할 및 동작 방식

### Common Teams (공통 인프라)

#### Data Pipeline
- **역할**: 시장 데이터 수집 및 저장
- **데이터 소스**: pykrx (KOSPI/KOSDAQ), yfinance (US)
- **스케줄**: 평일 18:00 KST 자동 실행
- **저장**: TimescaleDB `market_data` 테이블

#### Factor Engine & Portfolio Optimizer
- **역할**: 전 종목 팩터 스코어링 + 포트폴리오 자동 구성
- **5대 팩터**: Momentum 12M-1M(35%), Momentum 3M(15%), Low Volatility(25%), Value Proxy(15%), Quality Proxy(10%)
- **포트폴리오**: Inverse-volatility 가중, 종목당 MAX 15% / MIN 1%
- **리밸런싱**: 매주 월요일 목표 vs 현재 비교 후 조정
- **스케줄**: Celery Beat 매주 월 07:00(팩터), 07:30(리밸런싱)

#### Backtest Engine
- **역할**: 전략 백테스팅 (point-in-time 강제)
- **실행**: Celery 워커를 통한 비동기 처리
- **핵심 정책**: `end_date` 이후 데이터 절대 차단
- **메트릭**: Sharpe, Sortino, CAGR, MDD, VaR/CVaR, Win Rate, Calmar, Profit Factor

#### Risk Engine
- **역할**: 포트폴리오 리스크 모니터링
- **지표**: VaR 95%/99%, CVaR, Rolling Sharpe, Beta, Alpha
- **알림**: MDD > 15% = WARNING, > 25% = CRITICAL

---

### Strategy Teams (5개 전략팀 — 경쟁)

#### 1. Quant Strategies Team
- **접근법**: 전통 수리 알고리즘
- **전략 9개**: SMA 골든크로스, RSI 평균회귀, 모멘텀, 볼린저밴드, 이중모멘텀, 페어트레이딩, MACD, 돌파, 팩터모델
- **팀장**: 김민준 (CIO)

#### 2. Agentic Trading Team
- **접근법**: 5개 전문 에이전트 + 투자자 페르소나
- **에이전트**: Macro, Micro, News(Claude), Technical(5-전략 앙상블), Sentiment
- **프로세스**: 분석 → Bull/Bear 토론 → Risk Panel → 최종 결정
- **기억**: 시장별 독립 메모리 (agentic_kospi, agentic_kosdaq, agentic_us)
- **팀장**: 정하은 (Head of Agentic Strategies)

#### 3. TradingAgents Debate Team (NEW)
- **접근법**: TradingAgents 레포 패턴 — 멀티라운드 Bull/Bear 토론
- **4대 분석가**: Fundamentals, Market/Technical, News, Sentiment
- **토론**: Bull Researcher ↔ Bear Researcher (2 rounds) → Judge 종합
- **리스크 패널**: Conservative ↔ Neutral ↔ Aggressive 3인 합의
- **기억**: BM25 메모리 기반 유사 과거 상황 참조
- **팀장**: 김태양 (Head of Debate Strategies)

#### 4. AI Hedge Fund Team (NEW)
- **접근법**: ai-hedge-fund 레포 패턴 — 8인 전설적 투자자 결정론적 스코어링
- **8인 페르소나**: Ben Graham, Warren Buffett, Charlie Munger, George Soros, Peter Lynch, Michael Burry, Cathie Wood, Nassim Taleb
- **리스크**: 변동성-상관관계 기반 포지션 한도 자동 조절
- **포트폴리오 매니저**: 가중 컨센서스 투표 + Claude 강화
- **팀장**: 오유진 (CIO — Legendary Strategies)

#### 5. Strategy Lab Team
- **역할**: 신전략팀 발굴 및 등록 (R&D)
- **소스**: arXiv 논문 + GitHub Trending
- **기억**: 실패한 전략 타입 기억 → 반복 방지
- **팀장**: 조승우 (Head of Strategy Research)

---

## 대시보드 사용법

### 메인 대시보드 (http://localhost:3000)
- **전략팀 순위**: 우승 횟수, 최고 Sharpe/CAGR 한눈에 확인
- **현재 시장 신호**: 3개 전략팀의 최신 BUY/SELL/HOLD
- **CEO 최근 평가**: 칭찬과 압박 메시지
- **팀 이름 클릭 → 팀 상세 페이지 이동**

### 팀 상세 (http://localhost:3000/teams/{team_id})
| 탭 | 내용 |
|----|------|
| 팀원 | 팀장 + 팀원 카드 (역할, 전문 태그) |
| 포트폴리오 | 종목별 목표 비중, 팩터 스코어, 모멘텀, 변동성 |
| 리밸런싱 | 리밸런싱 이력 (매수/매도/홀드 건수) |

### 포트폴리오/팩터 (http://localhost:3000/portfolio)
- **팩터 스코어 랭킹**: 시장별/TopN별 필터
- **점수 등급**: S(≥0.8) / A(≥0.6) / B(≥0.4) / C(≥0.2) / D
- **팩터 분포 바**: Momentum, Value, Quality, LowVol 비중 시각화
- **팩터 엔진 수동 실행 버튼**

### 회사 현황 상세 (http://localhost:3000/company)
| 탭 | 내용 |
|----|------|
| 회사 현황 | 팀 순위 + CEO 최근 메시지 |
| CEO 경쟁 | 라운드별 전체 경쟁 결과 및 순위표 |
| 매매 신호 | 3개 전략팀 신호 히스토리 (에이전트별 분석 포함) |
| 매매 일지 | 신호 → 실제 결과 추적 (적중률, 수익률) |
| 에이전트 기억 | 각 에이전트가 쌓은 인사이트/경고/성과 기억 |

---

## 에이전트 기억 시스템

에이전트들은 자기 관련 기억만 유지합니다.

### 기억 타입
| 타입 | 설명 |
|------|------|
| `insight` | 학습된 시장 인사이트 |
| `performance` | 전략/신호 성과 기록 |
| `warning` | 실패 패턴, 반복 금지 사항 |
| `rule` | 확립된 운용 규칙 |

### 에이전트별 기억 범위
| 에이전트 | 기억하는 것 |
|----------|-----------|
| `strategy_lab` | 어떤 전략 타입이 잘됐는지/실패했는지, 좋은 논문 카테고리 |
| `agentic_kospi` | KOSPI 신호 정확도, 효과적인 에이전트 조합 |
| `agentic_kosdaq` | KOSDAQ 특성에 맞는 분석 패턴 |
| `agentic_us` | US 시장 신호 성과, 뉴스 감성의 유효성 |
| `trading_agents_kospi` | Bull/Bear 토론 정확도, 효과적인 분석가 조합 |
| `trading_agents_us` | US 시장 토론 결과, 리스크 패널 정확성 |
| `ai_hedge_fund_kospi` | 페르소나별 적중률, 시장 레짐별 유효한 페르소나 |
| `ai_hedge_fund_us` | US 시장 페르소나 성과, 컨센서스 정확도 |
| `ceo_agent` | 누가 꾸준히 이기는지, 어떤 전략 타입이 강한지 |

---

## CEO 경쟁 시스템

### 복합 점수 공식
```
Score = Sharpe × 0.4 + CAGR(%) × 0.3 - |MDD|(%) × 0.3
```

### Competition Round 실행
- **자동**: 매주 금요일 17:00 KST
- **수동**: `docker exec quant_ceo_agent python -c "from main import run_competition; run_competition()"`

---

## 팩터 엔진 & 포트폴리오

### 5대 팩터

| 팩터 | 비중 | 설명 |
|------|------|------|
| Momentum 12M-1M | 35% | 12개월 수익률 (최근 1개월 제외) |
| Momentum 3M | 15% | 3개월 모멘텀 |
| Low Volatility | 25% | 일별 수익률 변동성 역수 |
| Value Proxy | 15% | 52주 고점 대비 할인율 |
| Quality Proxy | 10% | 수익 안정성 (일별 수익률 표준편차 역수) |

### 포트폴리오 구성 방식
- **Inverse-volatility weighting**: 변동성 낮은 종목에 높은 비중
- **제약**: 종목당 MAX 15%, MIN 1%
- **유니버스**: TOP 20 종목 (팩터 스코어 상위)
- **리밸런싱**: 매주 월요일

### 수동 실행
```bash
# 팩터 엔진 실행
curl -X POST http://localhost:8000/api/portfolio/run-factor-engine

# 결과 조회
curl http://localhost:8000/api/portfolio/factor-scores?market=KOSPI&top_n=20
```

---

## 백테스팅 정책

### Point-in-Time 원칙 (절대 규칙)
> 백테스팅 시 `end_date` 이후의 데이터는 절대 사용하지 않는다.

### 백테스트 가능 전략 (11개)

**Quant Strategies (9개)**:
`sma_crossover`, `rsi_mean_reversion`, `bollinger_band`, `momentum`, `dual_momentum`, `pairs_trading`, `macd`, `breakout`, `factor_model`

**TradingAgents Team (1개)**:
`trading_agents_debate` — 모멘텀(40%)+평균회귀(30%)+변동성체제(30%) 앙상블

**AI Hedge Fund Team (1개)**:
`ai_hedge_fund_persona` — 가치(30%)+성장(25%)+매크로(20%)+역발상(15%)+리스크(10%)

### 백테스트 실행

**API**:
```bash
curl -X POST http://localhost:8000/api/backtests/ \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "UUID",
    "name": "TradingAgents Debate Backtest",
    "start_date": "2020-01-01",
    "end_date": "2024-12-31",
    "initial_capital": 100000000,
    "symbols": ["005930", "000660", "035720"],
    "market": "KOSPI"
  }'
```

---

## API 레퍼런스

### 주요 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/api/company/leaderboard` | 팀 순위표 |
| GET | `/api/company/competition/latest` | 최근 CEO 평가 |
| GET | `/api/company/competition/history` | 경쟁 히스토리 |
| GET | `/api/company/trade-journal` | 매매 일지 |
| GET | `/api/company/trade-journal/stats` | 매매 적중률 통계 |
| GET | `/api/company/agent-memory` | 에이전트 기억 |
| GET | `/api/company/agentic-signals` | 전략팀 매매 신호 |
| GET | `/api/portfolio/factor-scores` | 팩터 스코어 랭킹 |
| GET | `/api/portfolio/positions/{team_id}` | 팀 포트폴리오 |
| GET | `/api/portfolio/team-members/{team_id}` | 팀원 목록 |
| POST | `/api/portfolio/run-factor-engine` | 팩터 엔진 수동 실행 |
| POST | `/api/research/trigger-strategy-discovery` | 전략 자동 발굴 트리거 |
| GET | `/api/strategies/` | 전략 목록 |
| POST | `/api/backtests/` | 백테스트 생성 |
| GET | `/api/backtests/{id}` | 백테스트 결과 |
| GET | `/api/backtests/{id}/equity-curve` | 자산 곡선 |
| GET | `/api/backtests/{id}/trades` | 매매 내역 |

전체 API 문서: http://localhost:8000/docs
