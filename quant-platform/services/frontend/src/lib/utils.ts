import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatNumber(value: number, decimals = 2): string {
  return value.toFixed(decimals);
}

export function formatPercent(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatKRW(value: number): string {
  if (Math.abs(value) >= 1_0000_0000) {
    return `${(value / 1_0000_0000).toFixed(1)}억원`;
  } else if (Math.abs(value) >= 10_000) {
    return `${(value / 10_000).toFixed(1)}만원`;
  }
  return `${value.toLocaleString()}원`;
}

export function formatUSD(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatCurrency(value: number, market: string): string {
  if (market === "KRX" || market === "KOSPI" || market === "KOSDAQ") {
    return formatKRW(value);
  }
  return formatUSD(value);
}

export function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "completed":
      return "text-success bg-success/10";
    case "running":
      return "text-warning bg-warning/10";
    case "failed":
      return "text-danger bg-danger/10";
    case "pending":
      return "text-muted bg-muted/10";
    default:
      return "text-muted bg-muted/10";
  }
}
