/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      // A matchday form guide: chalk paper, navy ink, pitch green for wins,
      // red card for losses, floodlight amber for prices. Amber is the only accent.
      colors: {
        chalk: '#EAEFEA',
        paper: '#FBFCFA', // slips and panels sit on the chalk
        ink: { DEFAULT: '#0F1F36', soft: '#47576D', faint: '#8592A4', deep: '#0A1628' },
        pitch: { DEFAULT: '#1D7449', light: '#E1EFE6', bright: '#62D097' }, // bright: on ink
        amber: { DEFAULT: '#F2B705', dark: '#8F6C00', light: '#FCF2D0' },
        red: { DEFAULT: '#C9433C', light: '#F9E4E2' },
      },
      fontFamily: {
        display: ['Archivo', 'system-ui', 'sans-serif'],
        sans: ['Archivo', 'system-ui', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        // Navy-tinted, one light source from above.
        panel: '0 1px 0 rgba(15,31,54,0.05), 0 1px 3px rgba(15,31,54,0.07)',
        lift: '0 2px 4px rgba(15,31,54,0.06), 0 12px 24px -10px rgba(15,31,54,0.22)',
        slip: '0 18px 40px -14px rgba(4,10,22,0.65), 0 2px 6px rgba(4,10,22,0.25)',
      },
      keyframes: {
        pulse_dot: { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0.25' } },
      },
      animation: {
        live: 'pulse_dot 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
