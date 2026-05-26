import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      boxShadow: {
        soft: "0 1px 2px rgb(15 23 42 / 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
