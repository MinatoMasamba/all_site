module.exports = {
  content: ["templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        /* Mapped to Nocturne's CSS custom properties (static/css/nocturne.css)
           instead of static hex, so pages built with Tailwind utilities react
           to the light/dark theme toggle ([data-theme] on <html>) exactly like
           the hand-styled Nocturne pages do. */
        brun: {
          50:  'var(--color-surface)',
          100: 'var(--color-surface-hover)',
          200: 'var(--color-divider)',
          300: 'var(--color-neutral-700)',
          400: 'var(--color-neutral-600)',
          500: 'var(--color-neutral-500)',
          600: 'var(--color-neutral-400)',
          700: 'var(--color-accent)',
          800: 'var(--color-accent-600)',
          900: 'var(--color-text)',
        },
        emerald: {
          50: 'var(--color-success-bg)', 100: 'var(--color-success-bg)', 200: 'var(--color-success-border)',
          600: 'var(--color-success)', 700: 'var(--color-success-text)', 800: 'var(--color-success-text)',
        },
        red: {
          50: 'var(--color-danger-bg)', 100: 'var(--color-danger-bg)', 200: 'var(--color-danger-border)',
          600: 'var(--color-danger)', 700: 'var(--color-danger-text)', 800: 'var(--color-danger-text)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'fleur': 'var(--shadow-md)',
        'fleur-lg': 'var(--shadow-lg)',
      },
    }
  }
}
