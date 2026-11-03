import envConfig from "./config/env.config";

import express, { Request, Response } from "express";
import cors from "cors";
import { errorHandler, notFound } from "./middleware/error.handler";
import documentRoutes from "./routes/document.route";
import invoiceRoutes from "./routes/invoice.route";
import searchRoutes from "./routes/search.route";

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

/*--API routes--*/
app.use("/api/v1/documents", documentRoutes);
app.use("/api/v1/invoices", invoiceRoutes);
app.use("/api/v1/search", searchRoutes);

app.use(notFound);
app.use(errorHandler);

export default app;
