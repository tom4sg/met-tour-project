import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "met-red": "#E31837",
        "met-cream": "#F5F0E8",
        "met-charcoal": "#1A1A1A",
        "met-gold": "#C9A84C",
      },
    },
  },
  plugins: [],
};

export default config;
