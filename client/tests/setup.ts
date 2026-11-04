import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// After each test: remove what it showed, and undo fake timers and the fake backend
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
