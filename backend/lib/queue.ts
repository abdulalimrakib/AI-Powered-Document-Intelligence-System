import { Queue, Worker } from "bullmq";
import envConfig from "../config/env.config";
import { query } from "./db";
import { processDocument } from "./processDocument";

/*--Connection to Redis, where the queue is kept--*/
const redisUrl = new URL(envConfig.REDIS_URL);
const connection = {
  host: redisUrl.hostname,
  port: Number(redisUrl.port) || 6379,
  maxRetriesPerRequest: null, // BullMQ needs this: it waits for Redis instead of giving up
};

/*--The queue: a to-do list of documents to process--*/
export const documentQueue = new Queue(envConfig.QUEUE_NAME, {
  connection,
  defaultJobOptions: {
    attempts: envConfig.RETRY_ATTEMPTS,
    backoff: { type: "exponential", delay: envConfig.RETRY_WAIT_SECONDS * 1000 }, // wait 10 s, then 20 s ...
    removeOnComplete: true, // finished jobs are removed from Redis; the result is in Postgres
    removeOnFail: true,
  },
});

/*--Add a document to the queue--*/
// The job id is based on the document id, so the same document is never in the queue twice.
export const addDocumentJob = (documentId: number) =>
  documentQueue.add("process", { documentId }, { jobId: `document-${documentId}` });

/*--The worker: takes jobs from the queue, one at a time--*/
// One at a time, so we don't use up the free Gemini limit (about 20 requests a day per model) in parallel.
export const startWorker = () => {
  const worker = new Worker(
    envConfig.QUEUE_NAME,
    (job) => processDocument(job.data.documentId, job.attemptsMade + 1, job.opts.attempts ?? 1),
    { connection, concurrency: 1 }
  );
  worker.on("failed", (job, error) => {
    console.error(`Document ${job?.data.documentId}: attempt ${job?.attemptsMade} failed: ${error.message}`);
  });
  return worker;
};

/*--After a restart: put unfinished documents back in the queue--*/
// e.g. when Redis was down during an upload, or the server stopped in the middle of a job.
export const queueUnfinishedDocuments = async () => {
  const unfinished = await query("SELECT id FROM documents WHERE status IN ('pending', 'processing') ORDER BY id");
  for (const row of unfinished.rows) {
    await addDocumentJob(row.id); // ignored when the job is still in the queue
  }
  return unfinished.rows.length;
};

/*--Check that Redis is reachable (wait at most 5 seconds)--*/
export const checkQueue = () =>
  Promise.race([
    documentQueue.waitUntilReady(),
    new Promise((resolve, reject) => setTimeout(() => reject(new Error("Redis did not answer within 5 seconds")), 5000)),
  ]);
