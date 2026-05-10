import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./v2/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        mono: ["DM Mono", "monospace"],
      },
      colors: {
        lh: {
          bg: "hsl(var(--lh-bg))",
          surface: "hsl(var(--lh-surface))",
          card: "hsl(var(--lh-card))",
          border: "hsl(var(--lh-border))",
          text: "hsl(var(--lh-text))",
          "text-sec": "hsl(var(--lh-text-sec))",
          accent: "hsl(var(--lh-accent))",
          "accent-light": "hsl(var(--lh-accent-light))",
          success: "hsl(var(--lh-success))",
          warning: "hsl(var(--lh-warning))",
          danger: "hsl(var(--lh-danger))",
          info: "hsl(var(--lh-info))",
          sidebar: "hsl(var(--lh-sidebar))",
          "sidebar-text": "hsl(var(--lh-sidebar-text))",
        },
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
