"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { formatDate } from "@/lib/utils";

interface EquityCurveProps {
  data: { date: string; value: number }[];
  initialCapital?: number;
  market?: string;
  height?: number;
}

function formatYAxis(value: number, market?: string): string {
  if (market === "KRX" || market === "KOSPI" || market === "KOSDAQ") {
    if (Math.abs(value) >= 1_0000_0000) {
      return `${(value / 1_0000_0000).toFixed(0)}억`;
    } else if (Math.abs(value) >= 10_000) {
      return `${(value / 10_000).toFixed(0)}만`;
    }
    return value.toLocaleString();
  }
  if (Math.abs(value) >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  } else if (Math.abs(value) >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`;
  }
  return `$${value}`;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: any[];
  label?: string;
  initialCapital?: number;
  market?: string;
}

function CustomTooltip({ active, payload, label, initialCapital, market }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const value = payload[0].value as number;
  const returnPct = initialCapital ? ((value - initialCapital) / initialCapital) * 100 : null;
  const isPositive = returnPct !== null ? returnPct >= 0 : true;

  const formattedValue =
    market === "KRX" || market === "KOSPI" || market === "KOSDAQ"
      ? `${value.toLocaleString()}원`
      : `$${value.toLocaleString()}`;

  return (
    <div className="bg-[#1a1d27] border border-[#2a2d3e] rounded-lg px-3 py-2 shadow-xl text-xs">
      <p className="text-gray-400 mb-1">{label ? formatDate(label) : ""}</p>
      <p className="text-white font-semibold">{formattedValue}</p>
      {returnPct !== null && (
        <p className={isPositive ? "text-[#22c55e]" : "text-[#ef4444]"}>
          {isPositive ? "+" : ""}
          {returnPct.toFixed(2)}%
        </p>
      )}
    </div>
  );
}

export function EquityCurve({
  data,
  initialCapital,
  market,
  height = 320,
}: EquityCurveProps) {
  if (!data || data.length === 0) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center text-muted text-sm"
      >
        No equity curve data
      </div>
    );
  }

  const minValue = Math.min(...data.map((d) => d.value));
  const maxValue = Math.max(...data.map((d) => d.value));
  const padding = (maxValue - minValue) * 0.05;

  // Thin out dates for x-axis labels
  const tickCount = Math.min(8, data.length);
  const step = Math.floor(data.length / tickCount);
  const ticks = data
    .filter((_, i) => i % step === 0 || i === data.length - 1)
    .map((d) => d.date);

  const isPositiveEnd =
    data.length > 1
      ? data[data.length - 1].value >= data[0].value
      : true;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart
        data={data}
        margin={{ top: 10, right: 10, left: 10, bottom: 0 }}
      >
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop
              offset="5%"
              stopColor={isPositiveEnd ? "#6366f1" : "#ef4444"}
              stopOpacity={0.2}
            />
            <stop
              offset="95%"
              stopColor={isPositiveEnd ? "#6366f1" : "#ef4444"}
              stopOpacity={0}
            />
          </linearGradient>
        </defs>
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="#2a2d3e"
          vertical={false}
        />
        <XAxis
          dataKey="date"
          ticks={ticks}
          tick={{ fill: "#6b7280", fontSize: 11 }}
          axisLine={{ stroke: "#2a2d3e" }}
          tickLine={false}
          tickFormatter={(val) => {
            const d = new Date(val);
            return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}`;
          }}
        />
        <YAxis
          domain={[minValue - padding, maxValue + padding]}
          tick={{ fill: "#6b7280", fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(val) => formatYAxis(val, market)}
          width={70}
        />
        <Tooltip
          content={
            <CustomTooltip initialCapital={initialCapital} market={market} />
          }
        />
        {initialCapital && (
          <ReferenceLine
            y={initialCapital}
            stroke="#6b7280"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
        )}
        <Line
          type="monotone"
          dataKey="value"
          stroke={isPositiveEnd ? "#6366f1" : "#ef4444"}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: isPositiveEnd ? "#6366f1" : "#ef4444" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
