import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

const apiTarget = "http://127.0.0.1:8000"

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/generate": apiTarget,
      "/details": apiTarget,
      "/status": apiTarget,
      "/result": apiTarget,
      "/resume": apiTarget,
      "/health": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    passWithNoTests: true,
  },
})
