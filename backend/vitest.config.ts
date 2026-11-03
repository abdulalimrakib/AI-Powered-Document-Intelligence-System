import path from "path";
import { defineConfig } from "vitest/config";

// The tests never touch your real data: they use their own database, queue and upload folder,
// and a fake AI service (so no Gemini requests are used).
export const TEST_DATABASE_URL = "postgres://docintel:docintel@localhost:5440/docintel_test";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    globalSetup: ["tests/globalSetup.ts"], // creates the test database once
    env: {
      DATABASE_URL: TEST_DATABASE_URL,
      AI_API_URL: "http://localhost:8999", // the fake AI service in tests/task4/helpers.ts
      QUEUE_NAME: "documents-test",
      UPLOAD_FOLDER: path.resolve("storage", "test-uploads"),
      RETRY_WAIT_SECONDS: "0.2", // retry after 0.2 s instead of 10 s, so the tests are fast
    },
    fileParallelism: false, // the test files share one database, so they run one after another
    testTimeout: 20_000,
    hookTimeout: 20_000,
    reporters: ["default", "./tests/plainReport.ts"], // plainReport writes test-results/ (npm run test:save)
  },
});
