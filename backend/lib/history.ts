import { PoolClient } from "pg";
import { query } from "./db";

/*--Write one line in a document's history (processing_history)--*/
// e.g. addHistory(5, "done", "Done in 4.2 seconds: 2 invoices found, 1 need review")
// Pass `client` when it must be part of a transaction.
export const addHistory = (documentId: number, step: string, message: string, client?: PoolClient,
                           invoiceId: number | null = null, details: unknown = null) =>
  (client ?? { query }).query(
    "INSERT INTO processing_history (document_id, step, message, invoice_id, details) VALUES ($1, $2, $3, $4, $5)",
    [documentId, step, message, invoiceId, details === null ? null : JSON.stringify(details)]);
