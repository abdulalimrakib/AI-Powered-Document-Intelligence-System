import fs from "fs";
import path from "path";
import type { Reporter, TestCase, TestModule } from "vitest/node";

// Test folder -> (title of the report, file name). A copy of backend/tests/plainReport.ts, with the texts for the website.
const TASKS: Record<string, [string, string]> = {
  task6: ["Task 6 — Frontend (the website)", "task6_frontend.txt"],
};
const RESULTS_FOLDER = path.join(__dirname, "..", "..", "test-results");

type Result = { step: string; description: string; outcome: string; reason: string; seconds: number };

/*--Writes an easy-to-read results file for each Task, like the Python tests do--*/
// Only when asked: npm run test:save
export default class PlainReport implements Reporter {
  onTestRunEnd(testModules: ReadonlyArray<TestModule>) {
    if (!process.env.SAVE_RESULTS) return;

    const byTask: Record<string, Result[]> = {};
    for (const testModule of testModules) {
      const task = path.basename(path.dirname(testModule.moduleId)); // e.g. "task4"
      for (const test of testModule.children.allTests()) {
        (byTask[task] ??= []).push(toResult(test, testModule));
      }
    }
    for (const [task, results] of Object.entries(byTask)) {
      if (TASKS[task]) writeReport(task, TASKS[task][0], results, path.join(RESULTS_FOLDER, TASKS[task][1]));
    }
  }
}

/*--vitest writes the $example of a test in quotes: "... ('doesn\'t exist')". We show "... (doesn't exist)".--*/
const plainName = (name: string) =>
  name.replace(/\('((?:[^'\\]|\\.)*)'\)$/, (_, example: string) => `(${example.replace(/\\'/g, "'")})`);

const toResult = (test: TestCase, testModule: TestModule): Result => {
  // The step is the outer describe(), e.g. "Step 3 — Upload API"
  let suite = test.parent;
  while (suite.type === "suite" && suite.parent.type === "suite") suite = suite.parent;
  const step = suite.type === "suite" ? suite.name : path.basename(testModule.moduleId);

  const result = test.result();
  const outcome = result.state === "passed" ? "PASS" : result.state === "failed" ? "FAIL" : "SKIP";
  let reason = "";
  if (result.state === "failed") {
    const error = result.errors?.[0];
    reason = error?.name === "AssertionError"
      ? "the result was not what the test expected"
      : `the code stopped with an error: ${error?.name ?? "Error"}: ${(error?.message ?? "").split("\n")[0]}`;
  }
  return { step, description: plainName(test.name), outcome, reason, seconds: (test.diagnostic()?.duration ?? 0) / 1000 };
};

const writeReport = (task: string, title: string, results: Result[], file: string) => {
  const count = (outcome: string) => results.filter((result) => result.outcome === outcome).length;
  const failed = count("FAIL");
  const skipped = count("SKIP");
  let summary = failed ? `${failed} OF ${results.length} TESTS FAILED` : `ALL ${count("PASS")} TESTS PASSED`;
  if (skipped) summary += `, ${skipped} SKIPPED`;
  const seconds = results.reduce((sum, result) => sum + result.seconds, 0);
  const now = new Date();
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;

  const lines = [
    `${title}: test results`,
    "=".repeat(60),
    `Date:    ${date}`,
    `Result:  ${summary}  (${seconds.toFixed(1)} seconds)`,
    "",
    "Each line below is one automatic check of the system.",
    "PASS means the system did the right thing; FAIL means it did not (the reason is shown).",
    "SKIP means the check was not run this time.",
    "Each page is shown in a pretend browser and used like a person would, with a fake backend, so no real data and no Gemini requests are used.",
  ];
  const steps = [...new Set(results.map((result) => result.step))].sort();
  for (const step of steps) {
    const stepResults = results.filter((result) => result.step === step);
    const passed = stepResults.filter((result) => result.outcome === "PASS").length;
    lines.push("", `${step}  (${passed} of ${stepResults.length} passed)`, "-".repeat(60));
    for (const result of stepResults) {
      lines.push(`  ${result.outcome}  ${result.description}`);
      if (result.reason) lines.push(`        reason: ${result.reason}`);
    }
  }
  lines.push("", "To run these checks again:", "    cd client && npm run test:save");
  if (failed) lines.push("To see the full details of a failure:", "    cd client && npm test");
  lines.push("");

  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, lines.join("\n"), "utf8");
  console.log(`Results for ${task} saved in ${path.relative(process.cwd(), file)}`);
};

const pad = (number: number) => String(number).padStart(2, "0");
