import dotenv from "dotenv";
import path from "path";

// Read settings from .env.local first, then .env
dotenv.config({ path: [".env.local", ".env"], quiet: true });

const envConfig = {
  PORT: Number(process.env.PORT) || 3002,
  CORS_ORIGINS: (process.env.CORS_ORIGINS || "http://localhost:3000").split(",").map((origin) => origin.trim()),
  AI_API_URL: process.env.AI_API_URL || "http://localhost:8000",
  // Postgres and Redis run in Docker (docker-compose.yml in the project root)
  DATABASE_URL: process.env.DATABASE_URL || "postgres://docintel:docintel@localhost:5440/docintel",
  REDIS_URL: process.env.REDIS_URL || "redis://localhost:6380",
  // Uploaded files are saved here (kept out of git), so a file can be processed again later
  BACKEND_FOLDER: path.join(__dirname, ".."),
  UPLOAD_FOLDER: process.env.UPLOAD_FOLDER || path.join(__dirname, "..", "storage", "uploads"),
  MAX_FILE_SIZE_MB: 50, // the same limit as the AI service
  MAX_FILES: 20, // files in one upload
  // Background processing
  QUEUE_NAME: process.env.QUEUE_NAME || "documents", // the tests use their own queue
  AI_TIMEOUT_MINUTES: 30, // the longest we wait for the AI service to read one file
  RETRY_ATTEMPTS: 3, // how often we try when the AI service can't be reached
  RETRY_WAIT_SECONDS: Number(process.env.RETRY_WAIT_SECONDS) || 10, // the first wait (then 20 s, 40 s ...)
};

export default envConfig;
