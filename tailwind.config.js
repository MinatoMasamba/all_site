module.exports = {
  content: ["templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        brun: {
          50:  '#232532',
          100: '#2b2e3d',
          200: '#3f424d',
          300: '#565a68',
          400: '#75798c',
          500: '#9397ab',
          600: '#b2b6ca',
          700: '#9184d9',
          800: '#796cbf',
          900: '#e9e9ed',
        },
        emerald: {
          50: '#12291d', 100: '#153322', 200: '#1c4a2e',
          600: '#2fae68', 700: '#3ecf80', 800: '#8fe3b3',
        },
        red: {
          50: '#2c1418', 100: '#38181e', 200: '#54222a',
          600: '#e5555a', 700: '#ff6b6b', 800: '#ffb4b4',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'fleur': '0 4px 18px rgba(0, 0, 0, 0.45)',
        'fleur-lg': '0 10px 28px rgba(0, 0, 0, 0.55)',
      },
    }
  }
}
