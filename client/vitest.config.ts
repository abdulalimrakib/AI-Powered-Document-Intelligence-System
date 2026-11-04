import path from "path";
import { defineConfig } from "vitest/config";

// The website's tests: each page is shown in a pretend browser (jsdom) and used like a person would,
// with a fake backend (tests/task6/fakeBackend.ts). No real backend, database or Gemini is needed.
export default defineConfig({
  esbuild: { jsx: "automatic" }, // so .tsx files work without importing React
  resolve: { alias: { "@": path.resolve(__dirname, "src") } }, // the same "@/..." imports as the website
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/setup.ts"],
    reporters: ["default", "./tests/plainReport.ts"], // plainReport writes test-results/ (npm run test:save)
  },
});
