/*--Small helpers to show values in a readable way--*/

// 1536 -> "2 KB", 1_300_000 -> "1.2 MB"
export const readableSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.ceil(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

// "2026-11-04T08:40:12.345Z" -> "4 Nov 2026, 14:40" (in the user's own time zone)
export const readableDate = (isoDate: string | null) =>
  isoDate
    ? new Date(isoDate).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";

// "4.20" -> "4.2 s", "75" -> "1 min 15 s"
export const readableSeconds = (seconds: string | null) => {
  if (seconds === null) return "—";
  const value = Number(seconds);
  if (value < 60) return `${value.toFixed(1)} s`;
  return `${Math.floor(value / 60)} min ${Math.round(value % 60)} s`;
};

// "invoice_number" -> "Invoice number"
export const FIELD_LABELS: Record<string, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  supplier_name: "Supplier",
  customer_name: "Customer",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
  currency: "Currency",
};
export const fieldLabel = (name: string) => FIELD_LABELS[name] ?? name.replace(/_/g, " ");
