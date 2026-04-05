# QuantLab Capital — 사용법 가이드

## 목차
1. [빠른 시작](#빠른-시작)
2. [전체 시스템 흐름](#전체-시스템-흐름)
3. [팀별 역할 및 동작 방식](#팀별-역할-및-동작-방식)
4. [대시보드 사용법](#대시보드-사용법)
5. [에이전트 기억 시스템](#에이전트-기억-시스템)
6. [CEO 경쟁 시스템](#ceo-경쟁-시스템)
7. [백테스팅 정책 (Point-in-Time)](#백테스팅-정책)
8. [API 레퍼런스](#api-레퍼런스)

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

[월 09:00] Strategy Lab — GitHub Trending 스캔
    └→ 퀀트/AI 관련 레포 발견 → Claude 분석 → 새 팀 strategy_teams에 등록

[화,목 10:00] Strategy Lab — arXiv 논문 수집
    └→ q-fin / cs.LG 논문 → 전략 아이디어 추출 → 백테스트 자동 제출
    └→ 과거 실패 전략 타입은 반복하지 않음 (기억 활용)

[평일 08:30] Agentic Trading — KOSPI/KOSDAQ 분석
[평일 22:00] Agentic Trading — US 시장 분석
    └→ 5개 에이전트 분석 + 전설적 투자자 페르소나
    └→ Bull/Bear 토론 → Risk Panel → 최종 BUY/SELL/HOLD 결정
    └→ 과거 신호 정확도를 컨텍스트로 활용 (기억 활용)
    └→ 매매일지에 신호 기록

[평일 18:00] Data Pipeline — 시장 데이터 업데이트
    └→ KOSPI/KOSDAQ 종가 수집 → TimescaleDB 저장

[금 16:00] Strategy Lab — 트렌드 분석 보고서
    └→ 최근 30일 논문 트렌드 → 다음 연구 방향 제안

[금 17:00] CEO Agent — Competition Round
    └→ 모든 팀 최근 90일 백테스트 수집
    └→ 복합 점수 랭킹 (Sharpe×0.4 + CAGR×0.3 - MDD×0.3)
    └→ Claude로 승자 칭찬 + 하위팀 압박 메시지
    └→ 과거 라운드 패턴 기억 → 진화하는 평가 기준
```

---

## 팀별 역할 및 동작 방식

### Common Teams (공통 인프라)

#### Data Pipeline
- **역할**: 시장 데이터 수집 및 저장
- **데이터 소스**: pykrx (KOSPI/KOSDAQ), yfinance (US)
- **스케줄**: 평일 18:00 KST 자동 실행
- **저장**: TimescaleDB `market_data` 테이블

#### Backtest Engine
- **역할**: 전략 백테스팅 (point-in-time 강제)
- **실행**: Celery 워커를 통한 비동기 처리
- **핵심 정책**: `end_date` 이후 데이터 절대 차단
- **메트릭**: Sharpe, Sortino, CAGR, MDD, VaR/CVaR, Win Rate

#### Risk Engine
- **역할**: 포트폴리오 리스크 모니터링
- **지표**: VaR 95%/99%, CVaR, Rolling Sharpe, Beta
- **알림**: MDD > 15% = WARNING, > 25% = CRITICAL

---

### Strategy Teams (전략팀 — 경쟁)

#### Quant Strategies Team
- **접근법**: 전통 수리 알고리즘
- **전략**: SMA 골든크로스, RSI 평균회귀, 모멘텀, 볼린저밴드, 이중모멘텀
- **경쟁**: 백테스팅 결과로 CEO Competition 참가

#### Agentic Trading Team
- **접근법**: 5개 전문 에이전트 + 전설적 투자자 페르소나
- **에이전트**:
  - **Macro**: 금리, VIX, 환율 분석
  - **Micro**: 시장 지수 모멘텀
  - **News**: RSS 뉴스 감성 분석 (Claude)
  - **Technical**: MA, RSI, MACD, 볼린저밴드
  - **Persona**: Buffett, Soros, Lynch, Druckenmiller 관점
- **프로세스**: 분석 → Bull/Bear 토론 → Risk Panel → 최종 결정
- **기억**: 시장별 독립 메모리 (agentic_kospi, agentic_kosdaq, agentic_us)
- **매매일지**: 모든 신호를 기록하고 정확도 추적

#### AI Hedge Fund Team
- **접근법**: 전설적 투자자 스타일 분석
- **특징**: 각 투자자의 투자 철학을 Claude로 구현

#### Strategy Lab Team
- **역할**: 신전략팀 발굴 및 등록 (R&D)
- **소스**: arXiv 논문 + GitHub Trending
- **프로세스**: 논문 읽기 → 전략 추출 → 백테스트 → 유망하면 팀 등록
- **기억**: 실패한 전략 타입 기억 → 반복 방지

---

## 대시보드 사용법

### 메인 대시보드 (http://localhost:3000)
- **전략팀 순위**: 우승 횟수, 최고 Sharpe/CAGR 한눈에 확인
- **현재 시장 신호**: Agentic Trading 최신 BUY/SELL/HOLD
- **CEO 최근 평가**: 칭찬과 압박 메시지
- **최근 백테스트**: 클릭하면 상세 결과 확인

### 회사 현황 상세 (http://localhost:3000/company)

| 탭 | 내용 |
|----|------|
| 🏢 회사 현황 | 팀 순위 + CEO 최근 메시지 |
| 🏆 CEO 경쟁 | 라운드별 전체 경쟁 결과 및 순위표 |
| 📡 매매 신호 | Agentic Trading 신호 히스토리 (에이전트별 분석 포함) |
| 📒 매매 일지 | 신호 → 실제 결과 추적 (적중률, 수익률) |
| 🧠 에이전트 기억 | 각 에이전트가 쌓은 인사이트/경고/성과 기억 |

---

## 에이전트 기억 시스템

에이전트들은 진짜 사람처럼 자기 관련 기억만 유지합니다.

### 기억 타입
| 타입 | 아이콘 | 설명 |
|------|-------|------|
| `insight` | 💡 | 학습된 시장 인사이트 |
| `performance` | 📊 | 전략/신호 성과 기록 |
| `warning` | ⚠️ | 실패 패턴, 반복 금지 사항 |
| `rule` | 📌 | 확립된 운용 규칙 |

### 에이전트별 기억 범위
| 에이전트 | 기억하는 것 |
|----------|-----------|
| `strategy_lab` | 어떤 전략 타입이 잘됐는지/실패했는지, 좋은 논문 카테고리 |
| `agentic_kospi` | KOSPI 신호 정확도, 효과적인 에이전트 조합 |
| `agentic_kosdaq` | KOSDAQ 특성에 맞는 분석 패턴 |
| `agentic_us` | US 시장 신호 성과, 뉴스 감성의 유효성 |
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

### CEO 메시지 구성
1. **칭찬**: 우승팀에게 — 구체적 수치 언급, 열정적, "이 기세로 계속!"
2. **압박**: 하위팀에게 — 냉정하고 직설적, 구체적 개선 목표 제시

### 팀 등록 방법
Strategy Lab이 자동 등록하지만, 수동으로도 가능:
```sql
INSERT INTO strategy_teams (team_id, team_name, description, team_type)
VALUES ('my_team', '내 전략팀', '설명', 'quant');
```

---

## 백테스팅 정책

### Point-in-Time 원칙 (절대 규칙)

> 백테스팅 시 `end_date` 이후의 데이터는 절대 사용하지 않는다.

```python
# BacktestEngine.run() 내부
if end_date is not None:
    cutoff = pd.Timestamp(end_date)
    prices = prices[prices.index <= cutoff]  # ← 미래 차단
    signals = signals[signals.index <= cutoff]
```

이를 통해:
- 생존자 편향 제거
- Look-ahead bias 방지
- 실제 운용 시 재현 가능한 결과 보장

### 백테스트 실행 방법

**UI**: http://localhost:3000/backtests → "새 백테스트" 버튼

**API**:
```bash
curl -X POST http://localhost:8000/api/backtests/ \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "UUID",
    "name": "내 백테스트",
    "start_date": "2020-01-01",
    "end_date": "2024-12-31",
    "initial_capital": 100000000,
    "symbols": ["005930", "000660"],
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
| GET | `/api/company/agentic-signals` | Agentic Trading 신호 |
| POST | `/api/research/trigger-strategy-discovery` | 전략 자동 발굴 트리거 |
| GET | `/api/strategies/` | 전략 목록 |
| POST | `/api/backtests/` | 백테스트 생성 |
| GET | `/api/backtests/{id}` | 백테스트 결과 |

전체 API 문서: http://localhost:8000/docs
