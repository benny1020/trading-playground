import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        background: "#0f1117",
        surface: "#1a1d27",
        border: "#2a2d3e",
        primary: "#6366f1",
        success: "#22c55e",
        danger: "#ef4444",
        warning: "#f59e0b",
        muted: "#6b7280",
      }
    }
  },
  plugins: []
};
export default config;
