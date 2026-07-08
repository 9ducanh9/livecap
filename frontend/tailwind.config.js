/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        obsidian: '#09090B',
        'zinc-dark': '#18181B',
        crimson: {
          DEFAULT: '#E11D48',
          glow: 'rgba(225, 29, 72, 0.4)',
        },
        'emerald-pro': {
          DEFAULT: '#059669',
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
    },
  },
  plugins: [],
};
