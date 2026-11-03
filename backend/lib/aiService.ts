import envConfig from "../config/env.config";

/*--What the AI service's POST /extract gives back for one file (see AI/extract_invoices.py)--*/
export type AiField = { value: string | null; status: string; evidence: string | null; note: string | null };

export type AiInvoice = {
  source: string;
  method: string;
  ai_model: string | null;
  error: string | null;
  fields: Record<string, AiField>;
  line_items: {
    description: string | null;
    quantity: string | null;
    unit_price: string | null;
    amount: string | null;
    evidence: string | null;
    problems: string[];
  }[];
  validation_errors: { field: string | null; rule: string; message: string }[];
  needs_review: boolean;
  warnings: string[];
  text: string; // the invoice's text, as read from the file
};

export type AiFileResult = {
  filename: string;
  file_type: string | null;
  invoice_count: number;
  invoices: AiInvoice[];
  warnings: string[];
  error: string | null; // set when the file itself could not be read (broken, unsupported ...)
  processing_seconds: number;
};

/*--Send one file to the AI service and get its invoices back--*/
// Throws when the AI service can't be reached or crashes; the queue then tries again later.
// A file the AI can't read is NOT an exception: it comes back with `error` set.
export const extractWithAi = async (data: Buffer, filename: string): Promise<AiFileResult> => {
  const form = new FormData();
  form.append("files", new Blob([new Uint8Array(data)]), filename);

  let response: Response;
  try {
    response = await fetch(`${envConfig.AI_API_URL}/extract`, {
      method: "POST",
      body: form,
      // A big scanned PDF can take many minutes (OCR + one Gemini request per invoice)
      signal: AbortSignal.timeout(envConfig.AI_TIMEOUT_MINUTES * 60 * 1000),
    });
  } catch (error) {
    // fetch only says "fetch failed"; say what it means
    if (error instanceof Error && error.name === "TimeoutError") {
      throw new Error(`the AI service did not answer within ${envConfig.AI_TIMEOUT_MINUTES} minutes`);
    }
    throw new Error(`the AI service is not running at ${envConfig.AI_API_URL}`);
  }
  if (!response.ok) {
    throw new Error(`the AI service answered with error ${response.status}`);
  }
  const results: AiFileResult[] = await response.json();
  return results[0];
};

/*--A corrected value the AI service could not understand (e.g. "abc" as a total)--*/
export class CorrectionRejected extends Error {}

/*--Check an invoice again after a person corrected some values (AI service: POST /validate)--*/
// The cleaning and checking rules live only in the AI service (Python), so they are never written twice.
export const validateWithAi = async (
  invoice: { fields: Record<string, AiField>; line_items: unknown[]; text: string | null },
  corrections: Record<string, string | null>
): Promise<AiInvoice> => {
  let response: Response;
  try {
    response = await fetch(`${envConfig.AI_API_URL}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invoice, corrections }),
      signal: AbortSignal.timeout(30 * 1000),
    });
  } catch {
    throw new Error(`the AI service is not running at ${envConfig.AI_API_URL}`);
  }
  if (response.status === 400) {
    const answer = await response.json();
    throw new CorrectionRejected(answer.detail);
  }
  if (!response.ok) {
    throw new Error(`the AI service answered with error ${response.status}`);
  }
  return response.json();
};
