# QuantLab Capital — AI 퀀트 자산운용사

> **"여러 전략팀이 경쟁하며 수익을 낸다. 우리는 AI를 곁들인 퀀트 자산운용사다."**

## 구조

```
trading-playground/
└── quant-platform/          ← 메인 플랫폼 (docker compose up -d)
    ├── services/
    │   ├── backend/          ← FastAPI + Celery
    │   ├── frontend/         ← Next.js 14 대시보드
    │   ├── ceo-agent/        ← 전략팀 경쟁 평가 + 승자 칭찬
    │   ├── strategy-lab/     ← 논문/GitHub에서 신전략팀 발굴
    │   ├── agentic-trading/  ← 5개 AI 에이전트 협업
    │   ├── paper-research/   ← arXiv 크롤러
    │   ├── data-pipeline/    ← KOSPI/KOSDAQ/US 데이터
    │   └── risk-engine/      ← VaR/MDD 모니터링
    └── infrastructure/
        ├── postgres/         ← TimescaleDB 스키마
        ├── nginx/
        └── prometheus/
```

## 빠른 시작

```bash
cd quant-platform
cp .env.example .env     # ANTHROPIC_API_KEY 설정
docker compose up -d     # 전체 시스템 가동
```

대시보드: http://localhost:3000

## 자세한 내용

→ [quant-platform/README.md](quant-platform/README.md)
