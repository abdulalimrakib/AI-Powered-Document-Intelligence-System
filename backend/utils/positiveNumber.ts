/*--"12" -> 12. Anything that is not a whole number from 1 (e.g. "abc", "0", "1.5") -> null--*/
// Used for ids and page numbers that come from the URL.
export const positiveNumber = (value: unknown): number | null => {
  const text = String(value);
  return /^[1-9][0-9]{0,8}$/.test(text) ? Number(text) : null;
};
