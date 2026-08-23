/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Light theme. Keeping the same token names (ink/paper/brass/vault)
        // so components don't need per-file rewrites -- only the values
        // changed, from dark-panel to a plain off-white workspace.
        ink: {
          bg: "#FAFAF8",
          panel: "#FFFFFF",
          panel2: "#F2F1EC",
          line: "#E2E0D8",
          line2: "#CFCCC0",
        },
        paper: {
          DEFAULT: "#2B2A26",
          muted: "#6B6A62",
          dim: "#8C8A80",
        },
        brass: {
          DEFAULT: "#946B2D",
          bright: "#7A5722",
          dim: "#B08A4A",
        },
        vault: {
          green: "#2F8F5B",
          blue: "#3A66C4",
          red: "#C4453A",
        },
      },
      fontFamily: {
        display: ["Georgia", "'Times New Roman'", "serif"],
        body: ["-apple-system", "'Segoe UI'", "Helvetica", "Arial", "sans-serif"],
        mono: ["Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
