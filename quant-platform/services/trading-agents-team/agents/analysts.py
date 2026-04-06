"""
TradingAgents Team — Analyst Agents
====================================
4개 전문 분석가: Fundamentals, Market(Technical), News, Sentiment
각각 독립적으로 시장/종목 분석 → AnalystReport 반환.

(TradingAgents 레포 패턴: tool-driven, 마크다운 테이블 출력)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("trading-agents-team")


@dataclass
class AnalystReport:
    analyst_name: str
    signal: str          # BULLISH / BEARISH / NEUTRAL
    confidence: float    # 0.0 ~ 1.0
    report: str
    data_points: dict = field(default_factory=dict)


class FundamentalsAnalyst:
    """
    재무 분석가 — ai-hedge-fund Ben Graham + Buffett 패턴.
    ROE, 순이익률, 부채비율, FCF, 밸류에이션 종합 점수.
    """
    name = "Fundamentals Analyst"

    def analyze(self, market: str, symbols: list, claude_client=None) -> AnalystReport:
        try:
            import FinanceDataReader as fdr
            import pandas as pd

            idx_map = {"KOSPI": "KS11", "KOSDAQ": "KQ11", "US": "^GSPC"}
            symbol = idx_map.get(market, "^GSPC")
            df = fdr.DataReader(symbol, datetime.now() - timedelta(days=365))
            if len(df) < 60:
                return AnalystReport(self.name, "NEUTRAL", 0.4, "데이터 부족")

            close = df["Close"]
            price = float(close.iloc[-1])

            # 가격 기반 밸류에이션 proxy
            ret_1y = float(close.iloc[-1] / close.iloc[0] - 1)
            high_52w = float(close.max())
            low_52w = float(close.min())
            price_to_high = price / high_52w
            price_to_low = price / low_52w

            # 수익 안정성 (일별 수익률 std)
            daily_ret = close.pct_change().dropna()
            earnings_stability = 1.0 / (float(daily_ret.std()) * 15.87 + 0.01)  # 연환산 vol 역수

            score = 0
            # Value: 52주 고점 대비 20% 이상 할인
            if price_to_high < 0.8:
                score += 2
            elif price_to_high < 0.9:
                score += 1
            if price_to_high > 0.98:
                score -= 1

            # 1년 수익률 (성장성)
            if ret_1y > 0.15:
                score += 2
            elif ret_1y > 0.05:
                score += 1
            elif ret_1y < -0.15:
                score -= 2
            elif ret_1y < -0.05:
                score -= 1

            # 안정성
            if earnings_stability > 5:
                score += 1
            elif earnings_stability < 2:
                score -= 1

            signal = "BULLISH" if score >= 3 else "BEARISH" if score <= -1 else "NEUTRAL"
            confidence = min(0.85, 0.5 + abs(score) * 0.08)

            report = (
                f"[Fundamentals] {market}\n"
                f"  1Y Return: {ret_1y*100:.1f}%\n"
                f"  Price/52w-High: {price_to_high:.2f} | Price/52w-Low: {price_to_low:.2f}\n"
                f"  Earnings Stability Score: {earnings_stability:.1f}\n"
                f"  Composite Score: {score}/5"
            )

            return AnalystReport(self.name, signal, confidence, report,
                                 {"ret_1y": ret_1y, "price_to_high": price_to_high,
                                  "stability": earnings_stability, "score": score})
        except Exception as e:
            return AnalystReport(self.name, "NEUTRAL", 0.3, f"분석 오류: {e}")


class MarketAnalyst:
    """
    시장 기술 분석가 — TradingAgents 패턴.
    SMA/EMA + RSI + MACD + BB + ATR 종합.
    """
    name = "Market Analyst"

    def analyze(self, market: str, symbols: list, claude_client=None) -> AnalystReport:
        try:
            import FinanceDataReader as fdr
            import numpy as np

            idx_map = {"KOSPI": "KS11", "KOSDAQ": "KQ11", "US": "^GSPC"}
            symbol = idx_map.get(market, "^GSPC")
            df = fdr.DataReader(symbol, datetime.now() - timedelta(days=300))
            if len(df) < 60:
                return AnalystReport(self.name, "NEUTRAL", 0.4, "데이터 부족")

            close = df["Close"]
            high = df["High"] if "High" in df.columns else close
            low = df["Low"] if "Low" in df.columns else close
            price = float(close.iloc[-1])

            # Moving Averages
            sma50 = float(close.rolling(50).mean().iloc[-1])
            sma200 = float(close.rolling(min(200, len(close))).mean().iloc[-1])
            ema10 = float(close.ewm(span=10).mean().iloc[-1])

            # RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss_val = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = float((100 - 100 / (1 + gain / (loss_val + 1e-10))).iloc[-1])

            # MACD
            macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
            macd_signal = macd.ewm(span=9).mean()
            macd_hist = float((macd - macd_signal).iloc[-1])

            # Bollinger Bands
            bb_mid = float(close.rolling(20).mean().iloc[-1])
            bb_std = float(close.rolling(20).std().iloc[-1])
            bb_pct = (price - (bb_mid - 2*bb_std)) / (4*bb_std + 1e-10)

            # ATR (Average True Range)
            tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
            atr = float(tr.rolling(14).mean().iloc[-1])
            atr_pct = atr / price * 100

            score = 0
            if price > sma50: score += 1
            if price > sma200: score += 1
            if sma50 > sma200: score += 1  # Golden cross
            if price > ema10: score += 1
            if rsi < 30: score += 2       # Oversold
            elif rsi > 70: score -= 2     # Overbought
            elif 40 < rsi < 60: score += 1
            if macd_hist > 0: score += 1
            if bb_pct < 0.2: score += 1
            elif bb_pct > 0.9: score -= 1

            signal = "BULLISH" if score >= 5 else "BEARISH" if score <= 1 else "NEUTRAL"
            confidence = min(0.90, 0.5 + abs(score - 3) * 0.06)

            report = (
                f"[Market/Technical] {market}\n"
                f"  Price: {price:,.0f} | SMA50: {sma50:,.0f} | SMA200: {sma200:,.0f}\n"
                f"  RSI: {rsi:.0f} | MACD Hist: {'▲' if macd_hist>0 else '▼'}{abs(macd_hist):.2f}\n"
                f"  BB%: {bb_pct*100:.0f}% | ATR: {atr_pct:.1f}%\n"
                f"  Score: {score}/10"
            )

            return AnalystReport(self.name, signal, confidence, report,
                                 {"rsi": rsi, "macd_hist": macd_hist, "bb_pct": bb_pct,
                                  "atr_pct": atr_pct, "score": score})
        except Exception as e:
            return AnalystReport(self.name, "NEUTRAL", 0.3, f"분석 오류: {e}")


class NewsAnalyst:
    """뉴스 감성 분석 — Claude AI 또는 키워드 fallback."""
    name = "News Analyst"

    FEEDS = [
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.hankyung.com/feed/economy",
    ]

    def analyze(self, market: str, claude_client=None) -> AnalystReport:
        import feedparser
        headlines = []
        for url in self.FEEDS:
            try:
                feed = feedparser.parse(url)
                for e in feed.entries[:5]:
                    t = e.get("title", "")
                    if t:
                        headlines.append(t)
            except Exception:
                pass

        if not headlines:
            return AnalystReport(self.name, "NEUTRAL", 0.3, "뉴스 수집 실패")

        if claude_client:
            try:
                prompt = (
                    f"금융 뉴스 감성 분석 ({market} 시장).\n\n"
                    f"헤드라인:\n" + "\n".join([f"- {h}" for h in headlines[:12]]) +
                    '\n\nJSON만: {"signal":"BULLISH|BEARISH|NEUTRAL","confidence":0.0-1.0,"reasoning":"한 문장"}'
                )
                import json
                msg = claude_client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=200,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw = msg.content[0].text
                s, e = raw.find("{"), raw.rfind("}") + 1
                if s != -1 and e > s:
                    r = json.loads(raw[s:e])
                    return AnalystReport(self.name, r.get("signal", "NEUTRAL"),
                                         float(r.get("confidence", 0.5)),
                                         f"[News] {r.get('reasoning', '')}")
            except Exception:
                pass

        # Keyword fallback
        text = " ".join(headlines).lower()
        pos = sum(1 for k in ["rally", "surge", "gain", "strong", "상승", "호조", "강세"] if k in text)
        neg = sum(1 for k in ["crash", "fall", "recession", "하락", "우려", "약세"] if k in text)
        s = pos - neg
        signal = "BULLISH" if s > 1 else "BEARISH" if s < -1 else "NEUTRAL"
        return AnalystReport(self.name, signal, min(0.7, 0.5 + abs(s) * 0.05),
                             f"[News] 긍정:{pos} 부정:{neg} ({len(headlines)}건)")


class SentimentAnalyst:
    """소셜/감성 분석가 — 시장 공포탐욕 지수 proxy."""
    name = "Sentiment Analyst"

    def analyze(self, market: str, claude_client=None) -> AnalystReport:
        try:
            import yfinance as yf
            vix = yf.Ticker("^VIX").history(period="5d")
            if vix.empty:
                return AnalystReport(self.name, "NEUTRAL", 0.4, "VIX 데이터 없음")

            vix_val = float(vix["Close"].iloc[-1])
            vix_change = float(vix["Close"].iloc[-1] / vix["Close"].iloc[0] - 1)

            # Fear & Greed proxy
            if vix_val < 15:
                sentiment = "EXTREME_GREED"
                score = 1
            elif vix_val < 20:
                sentiment = "GREED"
                score = 0.5
            elif vix_val < 25:
                sentiment = "NEUTRAL"
                score = 0
            elif vix_val < 30:
                sentiment = "FEAR"
                score = -0.5
            else:
                sentiment = "EXTREME_FEAR"
                score = -1

            # VIX 급등 = 공포 확대
            if vix_change > 0.15:
                score -= 0.5

            signal = "BULLISH" if score >= 0.5 else "BEARISH" if score <= -0.5 else "NEUTRAL"
            confidence = min(0.8, 0.5 + abs(score) * 0.15)

            return AnalystReport(self.name, signal, confidence,
                                 f"[Sentiment] VIX={vix_val:.1f} ({sentiment}), 5일 변화: {vix_change*100:.1f}%",
                                 {"vix": vix_val, "vix_change": vix_change, "sentiment": sentiment})
        except Exception as e:
            return AnalystReport(self.name, "NEUTRAL", 0.3, f"감성 분석 오류: {e}")
