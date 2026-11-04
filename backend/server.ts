import app from "./app";
import envConfig from "./config/env.config";
import { setupDatabase } from "./lib/db";
import { fillMissingEmbeddings } from "./lib/embeddings";
import { checkQueue, queueUnfinishedDocuments, startWorker } from "./lib/queue";

/*--Create Server--*/
const start = async () => {
  try {
    await setupDatabase();
    await checkQueue();
  } catch (error) {
    console.error("Could not connect to the database or Redis. Are they running? Start them with: docker compose up -d");
    console.error(error);
    process.exit(1);
  }

  // The background worker runs in this same program, so one "npm run dev" starts everything.
  const worker = startWorker();
  const waiting = await queueUnfinishedDocuments();
  if (waiting) console.log(`${waiting} unfinished document(s) put back in the queue`);

  // Invoices that are not in meaning search yet (an earlier try failed): add them now
  fillMissingEmbeddings().then(({ saved, error }) => {
    if (saved) console.log(`${saved} invoice(s) added to meaning search`);
    if (error) console.log(`Meaning search: could not add invoices yet (${error})`);
  });

  app.listen(envConfig.PORT, () => {
    console.log(`Server running on port ${envConfig.PORT}!`);
  });

  // When the server is stopped, stop the worker at once. A job that was not finished is
  // picked up again by the queue after the restart (BullMQ calls it a "stalled" job).
  const stop = async () => {
    await worker.close(true);
    process.exit(0);
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
};

start();
