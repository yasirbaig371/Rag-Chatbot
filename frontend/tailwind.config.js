/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
      },
      boxShadow: {
        card: "0 18px 50px -24px rgba(30, 41, 59, 0.22)",
      },
    },
  },
  plugins: [],
};
