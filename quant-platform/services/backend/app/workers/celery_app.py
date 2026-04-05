from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "quant_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "fetch-market-data-daily": {
            "task": "app.workers.tasks.fetch_market_data",
            "schedule": crontab(hour=18, minute=0, day_of_week="1-5"),
            "options": {"queue": "data"},
        },
        "fetch-papers-weekly": {
            "task": "app.workers.tasks.fetch_papers",
            "schedule": crontab(hour=9, minute=0, day_of_week=1),
            "options": {"queue": "research"},
        },
        # 매주 월요일 오전 — 전체 팩터 스코어 재계산
        "run-factor-engine-weekly": {
            "task": "app.workers.tasks.run_factor_engine",
            "schedule": crontab(hour=7, minute=0, day_of_week=1),
            "options": {"queue": "data"},
        },
        # 매주 월요일 오전 (팩터 엔진 후) — 포트폴리오 리밸런싱
        "run-portfolio-rebalance-weekly": {
            "task": "app.workers.tasks.run_portfolio_rebalance",
            "schedule": crontab(hour=7, minute=30, day_of_week=1),
            "options": {"queue": "backtest"},
        },
    },
)
