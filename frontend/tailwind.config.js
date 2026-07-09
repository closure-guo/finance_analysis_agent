/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // TRAE Work semantic tokens
        'bg-base': 'var(--bg-base-default)',
        'bg-secondary': 'var(--bg-base-secondary)',
        'bg-overlay': {
          1: 'var(--bg-overlay-l1)',
          2: 'var(--bg-overlay-l2)',
          3: 'var(--bg-overlay-l3)',
        },
        brand: {
          DEFAULT: '#4B3FE3',
          hover: '#3D32C7',
          popup: 'rgba(75, 63, 227, 0.08)',
        },
        'txt': {
          DEFAULT: 'var(--text-default)',
          secondary: 'var(--text-secondary)',
          tertiary: 'var(--text-tertiary)',
        },
        'bdr': {
          DEFAULT: 'var(--border-neutral-l1)',
          strong: 'var(--border-neutral-l2)',
        },
      },
      borderRadius: {
        '8': '8px',
        '12': '12px',
      },
      fontFamily: {
        default: ['SF Pro Text', 'PingFang SC', 'system-ui', 'sans-serif'],
        heading: ['SF Pro Display', 'PingFang SC', 'system-ui', 'sans-serif'],
        metric: ['SF Pro Display', 'PingFang SC', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Cascadia Code', 'monospace'],
      },
    },
  },
  plugins: [],
}