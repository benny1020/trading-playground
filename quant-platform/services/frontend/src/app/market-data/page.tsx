"use client";

import { useState } from "react";
import { api, PriceData } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Table } from "@/components/ui/Table";
import { EquityCurve } from "@/components/charts/EquityCurve";
import { formatDate, formatCurrency } from "@/lib/utils";
import { Search, TrendingUp } from "lucide-react";

const MARKETS = [
  { value: "KOSPI", label: "KOSPI" },
  { value: "KOSDAQ", label: "KOSDAQ" },
  { value: "US", label: "US (NYSE/NASDAQ)" },
];

export default function MarketDataPage() {
  const [market, setMarket] = useState("KOSPI");
  const [symbol, setSymbol] = useState("");
  const [startDate, setStartDate] = useState("2023-01-01");
  const [endDate, setEndDate] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [prices, setPrices] = useState<PriceData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);

  async function handleSearch() {
    if (!symbol.trim()) {
      setError("Enter a symbol");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await api.marketData.getPrices(
        symbol.trim().toUpperCase(),
        startDate,
        endDate
      );
      setPrices(res.data);
      setSearched(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to fetch price data");
      setPrices([]);
    } finally {
      setLoading(false);
    }
  }

  // Convert OHLCV to equity-curve-like format for chart
  const closePrices = prices.map((p) => ({
    date: p.date,
    value: p.close,
  }));

  const priceColumns = [
    {
      key: "date",
      header: "Date",
      render: (row: PriceData) => (
        <span className="text-muted">{formatDate(row.date)}</span>
      ),
    },
    {
      key: "open",
      header: "Open",
      align: "right" as const,
      render: (row: PriceData) => formatCurrency(row.open, market),
    },
    {
      key: "high",
      header: "High",
      align: "right" as const,
      render: (row: PriceData) => (
        <span className="text-success">{formatCurrency(row.high, market)}</span>
      ),
    },
    {
      key: "low",
      header: "Low",
      align: "right" as const,
      render: (row: PriceData) => (
        <span className="text-danger">{formatCurrency(row.low, market)}</span>
      ),
    },
    {
      key: "close",
      header: "Close",
      align: "right" as const,
      render: (row: PriceData) => (
        <span className="font-medium">{formatCurrency(row.close, market)}</span>
      ),
    },
    {
      key: "volume",
      header: "Volume",
      align: "right" as const,
      render: (row: PriceData) => (
        <span className="text-muted">{row.volume.toLocaleString()}</span>
      ),
    },
  ];

  const displayedPrices = [...prices].reverse().slice(0, 100);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-white">Market Data</h1>
        <p className="text-sm text-muted mt-0.5">
          View historical price data for stocks
        </p>
      </div>

      {/* Search Controls */}
      <Card>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <Select
            label="Market"
            options={MARKETS}
            value={market}
            onChange={(e) => setMarket(e.target.value)}
          />
          <Input
            label="Symbol"
            placeholder="e.g. 005930"
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              setError("");
            }}
            onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
          />
          <Input
            label="Start Date"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <Input
            label="End Date"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
          <Button onClick={handleSearch} loading={loading}>
            <Search size={14} />
            Fetch Data
          </Button>
        </div>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
      </Card>

      {/* Price Chart */}
      {closePrices.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              {symbol.toUpperCase()} — Price History
            </CardTitle>
            <span className="text-xs text-muted">
              {prices.length} trading days
            </span>
          </CardHeader>
          <EquityCurve
            data={closePrices}
            market={market}
            height={300}
          />
        </Card>
      )}

      {/* Price Table */}
      {searched && (
        <Card className="p-0">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">
              OHLCV Data
            </h2>
            {prices.length > 100 && (
              <span className="text-xs text-muted">
                Showing last 100 of {prices.length} records
              </span>
            )}
          </div>
          {prices.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm">
              No data found for {symbol} in the selected date range
            </div>
          ) : (
            <Table columns={priceColumns} data={displayedPrices} />
          )}
        </Card>
      )}

      {/* Empty state */}
      {!searched && (
        <Card className="py-16 text-center">
          <TrendingUp size={32} className="mx-auto mb-3 text-muted" />
          <p className="text-gray-400 font-medium mb-1">
            Search for stock price data
          </p>
          <p className="text-sm text-muted">
            Enter a symbol and date range above to view historical prices
          </p>
        </Card>
      )}
    </div>
  );
}
