/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        mint: {
          DEFAULT: '#94D1BE',
          light: '#c4e8dd',
          dark: '#6bb89e',
          hover: '#7ec4ad',
        },
      },
    },
  },
  plugins: [],
}
