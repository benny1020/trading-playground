"use client";

import { cn } from "@/lib/utils";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  hoverable?: boolean;
}

export function Card({ children, className, onClick, hoverable }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "bg-surface border border-border rounded-xl p-4",
        hoverable && "hover:border-primary/40 transition-colors cursor-pointer",
        onClick && "cursor-pointer",
        className
      )}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export function CardHeader({ children, className }: CardHeaderProps) {
  return (
    <div className={cn("flex items-center justify-between mb-4", className)}>
      {children}
    </div>
  );
}

interface CardTitleProps {
  children: React.ReactNode;
  className?: string;
}

export function CardTitle({ children, className }: CardTitleProps) {
  return (
    <h3 className={cn("text-sm font-semibold text-gray-200 uppercase tracking-wider", className)}>
      {children}
    </h3>
  );
}

interface StatCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  positive?: boolean;
  negative?: boolean;
  icon?: React.ReactNode;
}

export function StatCard({ label, value, subValue, positive, negative, icon }: StatCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted uppercase tracking-wider mb-1">{label}</p>
          <p
            className={cn(
              "text-2xl font-bold",
              positive && "text-success",
              negative && "text-danger",
              !positive && !negative && "text-white"
            )}
          >
            {value}
          </p>
          {subValue && <p className="text-xs text-muted mt-1">{subValue}</p>}
        </div>
        {icon && (
          <div className="p-2 bg-primary/10 rounded-lg text-primary">{icon}</div>
        )}
      </div>
    </Card>
  );
}
