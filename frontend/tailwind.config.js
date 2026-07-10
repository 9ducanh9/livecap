/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Structural Aurora Palette
        'navy-pro': '#011F5B',
        'verdigris': '#00A693',
        'baby-blue': '#89CFF0',
        'lavender-pro': '#B57EDC',
        // Legacy dark mode (kept for dashboard)
        obsidian: '#09090b',
        'zinc-dark': '#18181B',
        // Shared LiveCap workspace palette
        paper: '#f7f8fc',
        'paper-warm': '#ffffff',
        ink: '#102247',
        'ink-muted': '#52647f',
        'ink-faint': '#8795aa',
        // Accent
        crimson: {
          DEFAULT: '#e54868',
          light: '#f46b85',
          glow: 'rgba(229, 72, 104, 0.3)',
        },
        'emerald-pro': {
          DEFAULT: '#0a9c88',
          light: '#35bea9',
          glow: 'rgba(10, 156, 136, 0.28)',
        },
      },
      fontFamily: {
        ui: ['Be Vietnam Pro', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backdropBlur: {
        pro: '24px',
      },
      boxShadow: {
        'brutal': '0 12px 30px rgba(16, 34, 71, 0.08)',
        'brutal-sm': '0 6px 16px rgba(16, 34, 71, 0.08)',
        'brutal-lg': '0 20px 48px rgba(16, 34, 71, 0.12)',
      },
      backgroundImage: {
        'grid-light': "linear-gradient(rgba(0,0,0,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.05) 1px, transparent 1px)",
      },
      backgroundSize: {
        'grid': '40px 40px',
      },
    },
  },
  plugins: [],
};
