/*--The filters of the search: ?date_from=2026-01-01&total_min=500&currency=USD&supplier=acme&needs_review=true--*/
// Reads them from the URL, checks them, and turns them into SQL conditions.
// The values always go in separately ($3, $4 ...), never glued into the SQL, so they can't change the query.

const MAX_SUPPLIER_LENGTH = 200;

type Filters = {
  conditions: string[]; // e.g. ["invoice_date >= $3::date", "upper(currency) = $4"]
  values: unknown[]; // e.g. ["2026-01-01", "USD"]
  used: Record<string, string>; // the filters that were given, sent back so the website can show them
};

/*--"2026-02-30" is not a real date, so we also check that the day exists--*/
const isDate = (text: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
  const date = new Date(`${text}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(text);
};

/*--"500", "499.99" or "-20.50" (a credit note). At most 2 decimals, like the money columns.--*/
const isAmount = (text: string) => /^-?\d{1,12}(\.\d{1,2})?$/.test(text);

/*--"499.9" -> 49990 cents, to compare two amounts exactly (no floats)--*/
const toCents = (text: string) => {
  const negative = text.startsWith("-");
  const [whole, decimals = ""] = text.replace("-", "").split(".");
  const cents = BigInt(whole) * 100n + BigInt(decimals.padEnd(2, "0"));
  return negative ? -cents : cents;
};

/*--In a LIKE pattern, % and _ are wildcards: "50%" should mean the text "50%", so we escape them--*/
export const containsPattern = (text: string) => `%${text.replace(/[\\%_]/g, (character) => "\\" + character)}%`;

/*--Read the filters. Gives back { error } when one is wrong, so the user gets a clear message.--*/
// firstNumber: the SQL placeholder number for the first value (the search already uses $1 and $2).
export const readFilters = (query: Record<string, unknown>, firstNumber: number): Filters | { error: string } => {
  const filters: Filters = { conditions: [], values: [], used: {} };

  // Every filter is optional. It must be one piece of text (not given twice, like ?currency=USD&currency=EUR).
  const text: Record<string, string> = {};
  for (const name of ["date_from", "date_to", "total_min", "total_max", "currency", "supplier", "needs_review"]) {
    const value = query[name];
    if (value === undefined) continue;
    if (typeof value !== "string") return { error: `${name} can only be given once` };
    if (value.trim() !== "") text[name] = value.trim();
  }

  for (const name of ["date_from", "date_to"]) {
    if (text[name] && !isDate(text[name])) return { error: `${name} must be a date like 2026-01-31` };
  }
  for (const name of ["total_min", "total_max"]) {
    if (text[name] && !isAmount(text[name])) return { error: `${name} must be an amount like 500 or 499.99` };
  }
  if (text.date_from && text.date_to && text.date_from > text.date_to) {
    return { error: "date_from must be on or before date_to" };
  }
  if (text.total_min && text.total_max && toCents(text.total_min) > toCents(text.total_max)) {
    return { error: "total_min must not be bigger than total_max" };
  }
  if (text.currency && !/^[A-Za-z]{3}$/.test(text.currency)) {
    return { error: "currency must be a 3-letter code like USD" };
  }
  if (text.supplier && text.supplier.length > MAX_SUPPLIER_LENGTH) {
    return { error: `supplier is too long (at most ${MAX_SUPPLIER_LENGTH} characters)` };
  }
  if (text.needs_review && !["true", "false"].includes(text.needs_review)) {
    return { error: "needs_review must be true or false" };
  }

  /*--Add one SQL condition per filter--*/
  // "$" + number is the placeholder for the value we add at the same time
  const add = (name: string, sql: (placeholder: string) => string, value: unknown) => {
    filters.values.push(value);
    filters.conditions.push(sql(`$${firstNumber + filters.values.length - 1}`));
    filters.used[name] = text[name];
  };
  // An invoice without a date (or total) can't be "after 2026-01-01", so date and amount filters leave it out.
  if (text.date_from) add("date_from", (p) => `invoice_date >= ${p}::date`, text.date_from);
  if (text.date_to) add("date_to", (p) => `invoice_date <= ${p}::date`, text.date_to);
  // Amounts go to Postgres as text and are compared as exact numeric values
  if (text.total_min) add("total_min", (p) => `total >= ${p}::numeric`, text.total_min);
  if (text.total_max) add("total_max", (p) => `total <= ${p}::numeric`, text.total_max);
  if (text.currency) {
    text.currency = text.currency.toUpperCase(); // "usd" is the same as "USD"
    add("currency", (p) => `upper(currency) = ${p}`, text.currency);
  }
  // Part of the name is enough: "acme" finds "Acme Ltd"
  if (text.supplier) add("supplier", (p) => `supplier_name ILIKE ${p}`, containsPattern(text.supplier));
  if (text.needs_review) add("needs_review", (p) => `needs_review = ${p}::boolean`, text.needs_review === "true");

  return filters;
};
