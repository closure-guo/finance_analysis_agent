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
        // shadcn semantic tokens（refactor-ui-design-system）
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: { DEFAULT: 'var(--card)', foreground: 'var(--card-foreground)' },
        popover: { DEFAULT: 'var(--popover)', foreground: 'var(--popover-foreground)' },
        primary: { DEFAULT: 'var(--primary)', foreground: 'var(--primary-foreground)' },
        secondary: { DEFAULT: 'var(--secondary)', foreground: 'var(--secondary-foreground)' },
        muted: { DEFAULT: 'var(--muted)', foreground: 'var(--muted-foreground)' },
        accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-foreground)' },
        destructive: { DEFAULT: 'var(--destructive)', foreground: 'var(--destructive-foreground)' },
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
      },
      borderRadius: {
        '8': '8px',
        '12': '12px',
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
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