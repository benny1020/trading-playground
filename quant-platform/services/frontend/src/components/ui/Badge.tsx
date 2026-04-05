"use client";

import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "danger" | "warning" | "muted" | "primary";
  className?: string;
}

const variantStyles: Record<string, string> = {
  default: "bg-surface text-gray-300 border border-border",
  success: "bg-success/10 text-success border border-success/20",
  danger: "bg-danger/10 text-danger border border-danger/20",
  warning: "bg-warning/10 text-warning border border-warning/20",
  muted: "bg-muted/10 text-muted border border-muted/20",
  primary: "bg-primary/10 text-primary border border-primary/20",
};

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium",
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const variantMap: Record<string, "success" | "warning" | "danger" | "muted"> = {
    completed: "success",
    running: "warning",
    failed: "danger",
    pending: "muted",
  };
  const variant = variantMap[status.toLowerCase()] ?? "muted";
  return <Badge variant={variant}>{status}</Badge>;
}
