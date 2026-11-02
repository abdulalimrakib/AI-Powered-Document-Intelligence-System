import dotenv from "dotenv";

// Read settings from .env.local first, then .env
dotenv.config({ path: [".env.local", ".env"], quiet: true });

const envConfig = {
  PORT: Number(process.env.PORT) || 3002,
  CORS_ORIGINS: (process.env.CORS_ORIGINS || "http://localhost:3000").split(",").map((origin) => origin.trim()),
  AI_API_URL: process.env.AI_API_URL || "http://localhost:8000",
};

export default envConfig;
