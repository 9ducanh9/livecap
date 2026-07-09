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
        // Neo-Brutalist light palette
        paper: '#f3f4f6',
        'paper-warm': '#fafafa',
        ink: '#09090b',
        'ink-muted': '#71717a',
        'ink-faint': '#a1a1aa',
        // Accent
        crimson: {
          DEFAULT: '#E11D48',
          light: '#f43f5e',
          glow: 'rgba(225, 29, 72, 0.4)',
        },
        'emerald-pro': {
          DEFAULT: '#059669',
          light: '#22c55e',
          glow: 'rgba(5, 150, 105, 0.4)',
        },
      },
      fontFamily: {
        ui: ['Space Grotesk', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backdropBlur: {
        pro: '24px',
      },
      boxShadow: {
        'brutal': '4px 4px 0px 0px #09090b',
        'brutal-sm': '2px 2px 0px 0px #09090b',
        'brutal-lg': '6px 6px 0px 0px #09090b',
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
