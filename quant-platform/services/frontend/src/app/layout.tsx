import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import {
  BarChart2,
  BrainCircuit,
  FlaskConical,
  LayoutDashboard,
  LineChart,
  TrendingUp,
} from "lucide-react";

export const metadata: Metadata = {
  title: "QuantLab",
  description: "Quantitative Trading Platform",
};

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/strategies", label: "Strategies", icon: BrainCircuit },
  { href: "/backtests", label: "Backtests", icon: BarChart2 },
  { href: "/research", label: "Research", icon: FlaskConical },
  { href: "/market-data", label: "Market Data", icon: TrendingUp },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-background text-gray-200 min-h-screen flex">
        {/* Sidebar */}
        <aside className="w-56 shrink-0 h-screen sticky top-0 bg-surface border-r border-border flex flex-col">
          {/* Logo */}
          <div className="px-5 py-5 border-b border-border">
            <Link href="/" className="flex items-center gap-2.5 group">
              <div className="p-1.5 bg-primary/20 rounded-lg group-hover:bg-primary/30 transition-colors">
                <LineChart size={18} className="text-primary" />
              </div>
              <span className="text-white font-bold text-base tracking-tight">
                QuantLab
              </span>
            </Link>
          </div>

          {/* Nav */}
          <nav className="flex-1 px-3 py-4 space-y-0.5">
            {navItems.map(({ href, label, icon: Icon }) => (
              <NavItem key={href} href={href} label={label} Icon={Icon} />
            ))}
          </nav>

          {/* Footer */}
          <div className="px-5 py-4 border-t border-border">
            <p className="text-xs text-muted">v0.1.0</p>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 min-h-screen overflow-y-auto">
          {children}
        </main>
      </body>
    </html>
  );
}

function NavItem({
  href,
  label,
  Icon,
}: {
  href: string;
  label: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
}) {
  // Using a plain anchor for simplicity; active state requires client component
  return (
    <Link
      href={href}
      className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-all group"
    >
      <Icon size={16} className="shrink-0 group-hover:text-primary transition-colors" />
      {label}
    </Link>
  );
}
