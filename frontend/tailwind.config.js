/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      // Betting-shop form guide: chalk paper, navy ink, pitch green for wins,
      // red card for losses, referee-card amber for prices.
      colors: {
        chalk: '#EEF2EE',
        ink: { DEFAULT: '#13233A', soft: '#4A5A70', faint: '#8794A6' },
        pitch: { DEFAULT: '#1F7A4D', light: '#E3F1E8' },
        amber: { DEFAULT: '#F2B705', dark: '#9A7400', light: '#FDF4D3' },
        red: { DEFAULT: '#D64545', light: '#FBE6E6' },
      },
      fontFamily: {
        display: ['"Barlow Condensed"', 'Barlow', 'system-ui', 'sans-serif'],
        sans: ['Barlow', 'system-ui', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
