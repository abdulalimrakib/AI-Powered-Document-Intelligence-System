import envConfig from "./config/env.config";

import express, { Request, Response } from "express";
import cors from "cors";
import { errorHandler, notFound } from "./middleware/error.handler";

const app = express();

app.use(express.json({ limit: "1mb" }));
app.use(
  cors({
    origin: envConfig.CORS_ORIGINS,
    methods: ["GET", "POST", "PATCH", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Accept"],
  })
);

app.get("/health", (req: Request, res: Response) => {
  res.json({ status: "ok" });
});

app.use(notFound);
app.use(errorHandler);

export default app;
