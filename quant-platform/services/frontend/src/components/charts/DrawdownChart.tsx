"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { formatDate } from "@/lib/utils";

interface DrawdownPoint {
  date: string;
  drawdown: number;
}

interface DrawdownChartProps {
  data: DrawdownPoint[];
  height?: number;
}

function computeDrawdown(equityCurve: { date: string; value: number }[]): DrawdownPoint[] {
  let peak = equityCurve[0]?.value ?? 0;
  return equityCurve.map((point) => {
    if (point.value > peak) peak = point.value;
    const dd = peak === 0 ? 0 : ((point.value - peak) / peak) * 100;
    return { date: point.date, drawdown: dd };
  });
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: any[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const value = payload[0].value as number;
  return (
    <div className="bg-[#1a1d27] border border-[#2a2d3e] rounded-lg px-3 py-2 shadow-xl text-xs">
      <p className="text-gray-400 mb-1">{label ? formatDate(label) : ""}</p>
      <p className="text-[#ef4444] font-semibold">
        {value.toFixed(2)}%
      </p>
    </div>
  );
}

export function DrawdownChart({ data, height = 200 }: DrawdownChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center text-muted text-sm"
      >
        No drawdown data
      </div>
    );
  }

  const minDrawdown = Math.min(...data.map((d) => d.drawdown));
  const domainMin = minDrawdown * 1.1;

  const tickCount = Math.min(8, data.length);
  const step = Math.floor(data.length / tickCount);
  const ticks = data
    .filter((_, i) => i % step === 0 || i === data.length - 1)
    .map((d) => d.date);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart
        data={data}
        margin={{ top: 5, right: 10, left: 10, bottom: 0 }}
      >
        <defs>
          <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
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
          domain={[domainMin, 0]}
          tick={{ fill: "#6b7280", fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(val) => `${val.toFixed(0)}%`}
          width={50}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke="#2a2d3e" />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke="#ef4444"
          strokeWidth={1.5}
          fill="url(#drawdownGradient)"
          dot={false}
          activeDot={{ r: 3, fill: "#ef4444" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export { computeDrawdown };
