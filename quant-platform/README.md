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

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        QuantLab Capital                         │
│                     AI 퀀트 자산운용사                            │
└─────────────────────────────────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
   ┌──────▼──────┐    ┌────────▼────────┐   ┌──────▼──────────┐
   │  COMMON     │    │  STRATEGY TEAMS │   │  GOVERNANCE     │
   │  TEAMS      │    │  (경쟁)         │   │                 │
   │             │    │                 │   │  CEO Agent      │
   │ Data        │◄───│ Quant Strats    │   │  (매주 평가)    │
   │ Pipeline    │    │ Agentic Trading │   │                 │
   │             │◄───│ AI Hedge Fund   │   │  Strategy Lab   │
   │ Backtest    │    │ Strategy Lab    │   │  (팀 신설)      │
   │ Engine      │◄───│ [New Teams...]  │   │                 │
   │             │    │                 │   │  Risk Engine    │
   │ Risk Engine │    └─────────────────┘   │  (포트폴리오    │
   └─────────────┘                          │   리스크 관리)  │
                                            └─────────────────┘
```

### 팀 분류

#### Common Teams (공통 인프라)

모든 전략팀이 공유하는 인프라. 데이터 공급, 검증, 리스크 관리를 담당.

| 팀 | 역할 | 기술 스택 |
|----|------|-----------|
| **Data Pipeline** | KOSPI/KOSDAQ/US 시장 데이터 수집 | pykrx, FinanceDataReader, yfinance |
| **Backtest Engine** | 전략 검증 (point-in-time 강제) | Vectorized Python, Celery |
| **Risk Engine** | VaR/CVaR/MDD 실시간 모니터링 | PostgreSQL, Redis |

#### Strategy Teams (전략팀 — 경쟁)

각 팀은 독립적으로 전략을 연구하고 백테스트 결과로 경쟁한다.

| 팀 | 접근법 | 핵심 기술 |
|----|--------|-----------|
| **Quant Strategies** | 전통 수리 알고리즘 (SMA, RSI, Momentum) | Python, NumPy |
| **Agentic Trading** | 5개 AI 에이전트 협업 신호 생성 | Claude AI, Multi-agent |
| **AI Hedge Fund** | 전설적 투자자 페르소나 (Buffett, Soros) | Claude AI, LangGraph 패턴 |
| **Strategy Lab** | 논문/GitHub 발굴 → 신팀 등록 | arXiv API, GitHub API, Claude AI |
| **[New Teams]** | Strategy Lab이 지속 발굴·등록 | 동적 생성 |

#### Governance

| 서비스 | 역할 |
|--------|------|
| **CEO Agent** | 매주 금요일 전략팀 경쟁 평가. 복합 점수로 랭킹. Claude로 승자 칭찬 생성 |
| **Strategy Lab** | 매주 월 GitHub, 화/목 arXiv 스캔. 유망 아이디어 → 신팀 등록 |

---

## 경쟁 시스템

### 복합 점수 (Composite Score)

```
Score = Sharpe × 0.4 + CAGR(%) × 0.3 - |MDD|(%) × 0.3
```

### Competition Round 흐름

```
[매주 금요일 17:00 KST]
         │
         ▼
  CEO Agent 실행
         │
         ▼
  모든 팀의 최근 90일 백테스트 결과 수집
         │
         ▼
  복합 점수 계산 → 랭킹
         │
         ▼
  Claude API → CEO 칭찬 메시지 생성
         │
         ▼
  competition_rounds DB 저장
  strategy_teams.wins 업데이트
         │
         ▼
  Dashboard에 결과 표시
```

### Point-in-Time 정책 (절대 규칙)

> 백테스팅은 당시 시점에서 알 수 있었던 데이터만 사용한다.

- `end_date` 이후의 모든 데이터는 BacktestEngine에서 자동 차단
- 미래 주가, 미래 실적, 미래 뉴스 절대 사용 불가
- Walk-forward validation 원칙 준수

---

## Strategy Lab 운영 정책

```
[매주 월요일 09:00]
  GitHub Trending 스캔
    → 퀀트/AI 관련 레포 추출
    → Claude 분석 → 신팀 아이디어
    → strategy_teams 테이블에 등록
    → 다음 CEO Competition에 자동 참가

[화, 목요일 10:00]
  arXiv 논문 수집 (q-fin.PM, q-fin.TR, q-fin.ST, cs.LG, cs.AI)
    → Claude 전략 추출
    → 백테스트 자동 제출
    → Sharpe ≥ 0.8, CAGR ≥ 5%, MDD ≤ 30% → promising_strategies

[금요일 16:00]
  트렌드 분석 보고서 생성 (CEO Competition 1시간 전)
```

---

## 전략 목록 (현재)

| 전략명 | 유형 | 시장 | 설명 |
|--------|------|------|------|
| SMA 골든크로스 | Trend | KOSPI | 20/60일 이동평균 크로스오버 |
| RSI 평균회귀 | Mean Rev | US | RSI 30↓매수, 70↑매도 |
| 모멘텀 팩터 | Momentum | ALL | 12개월 수익률 상위 20% |
| 볼린저밴드 | Mean Rev | KOSDAQ | BB 하단 매수, 상단 매도 |
| 이중 모멘텀 (Antonacci) | Momentum | US | 절대+상대 모멘텀 결합 |

---

## 기술 스택

```
Frontend:   Next.js 14 (TypeScript, Tailwind, Recharts) — :3000
Backend:    FastAPI + Celery (Python 3.11) — :8000
Database:   PostgreSQL 16 + TimescaleDB — :5432
Cache:      Redis 7 — :6379
Streaming:  Apache Kafka — :9092
Storage:    MinIO — :9000
MLflow:     Experiment Tracking — :5000
Jupyter:    Research Notebooks — :8888
Grafana:    Monitoring Dashboard — :3001
Flower:     Celery Task Monitor — :5555
Nginx:      Reverse Proxy — :80
```

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
| API 문서 | http://localhost:8000/docs |
| MLflow | http://localhost:5000 |
| Jupyter Lab | http://localhost:8888 |
| Grafana | http://localhost:3001 |
| Celery Flower | http://localhost:5555 |

---

## 데이터베이스 스키마

```
strategies          — 전략 정의
backtest_runs       — 백테스트 실행 기록
market_data         — OHLCV 시장 데이터 (TimescaleDB)
stock_info          — 종목 메타데이터
papers              — arXiv 논문
trend_reports       — 주간 트렌드 분석
promising_strategies— 유망 전략 트래커
risk_reports        — 리스크 보고서
agentic_signals     — Agentic Trading 매매 신호
strategy_teams      — 팀 레지스트리 (wins, best_sharpe)
competition_rounds  — CEO 경쟁 평가 결과
```

---

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Claude AI API 키 (필수) | — |
| `POSTGRES_USER` | DB 사용자 | `quant` |
| `POSTGRES_PASSWORD` | DB 비밀번호 | `quant1234` |
| `POSTGRES_DB` | DB 이름 | `quantdb` |
| `MINIO_ROOT_USER` | MinIO 사용자 | `quantlab` |
| `MINIO_ROOT_PASSWORD` | MinIO 비밀번호 | — |
| `GRAFANA_PASSWORD` | Grafana 비밀번호 | — |
| `JUPYTER_TOKEN` | Jupyter 토큰 | — |

---

## 참고 레포지토리

- [TradingAgents](https://github.com/TauricResearch/TradingAgents) — Bull/Bear 토론 기반 에이전트
- [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) — 전설적 투자자 페르소나

---

## License

MIT
