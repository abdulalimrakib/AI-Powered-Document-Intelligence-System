/*--Check files before they are uploaded--*/
// The same rules as the backend (backend/lib/upload.ts and config/env.config.ts). This check is only for
// comfort: the user sees a problem at once instead of after the upload. The backend still checks everything,
// because a website can always be bypassed.

export const SUPPORTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"];
export const MAX_FILE_SIZE_MB = 50;
export const MAX_FILES = 20; // in one upload

export type RejectedFile = { name: string; reason: string };

// "Invoice.PDF" -> ".pdf"
const extensionOf = (name: string) => {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
};

/*--Which of the new files can be added to the ones already chosen?--*/
export const checkFiles = (newFiles: File[], alreadyChosen: File[]) => {
  const accepted: File[] = [];
  const rejected: RejectedFile[] = [];

  for (const file of newFiles) {
    const sameFile = (other: File) => other.name === file.name && other.size === file.size;
    if (!SUPPORTED_EXTENSIONS.includes(extensionOf(file.name))) {
      rejected.push({ name: file.name, reason: "This file type is not supported. Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV." });
    } else if (file.size === 0) {
      rejected.push({ name: file.name, reason: "The file is empty." });
    } else if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      rejected.push({ name: file.name, reason: `The file is bigger than ${MAX_FILE_SIZE_MB} MB.` });
    } else if (alreadyChosen.some(sameFile) || accepted.some(sameFile)) {
      rejected.push({ name: file.name, reason: "This file is already in the list." });
    } else if (alreadyChosen.length + accepted.length >= MAX_FILES) {
      rejected.push({ name: file.name, reason: `At most ${MAX_FILES} files can be uploaded at once.` });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
};
