import crypto from "crypto";
import fs from "fs";
import path from "path";
import multer from "multer";
import envConfig from "../config/env.config";

// The file types the AI service can read. The AI service also checks the file's real content.
const SUPPORTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"];

export const isSupported = (filename: string) => SUPPORTED_EXTENSIONS.includes(path.extname(filename).toLowerCase());

fs.mkdirSync(envConfig.UPLOAD_FOLDER, { recursive: true });

/*--Where and under which name a file is saved--*/
// We never use the user's file name on disk: a name like "../../app.ts" could overwrite our own files,
// and two users can upload "invoice.pdf". A random name is always safe and unique.
const storage = multer.diskStorage({
  destination: envConfig.UPLOAD_FOLDER,
  filename: (req, file, save) => {
    const extension = isSupported(file.originalname) ? path.extname(file.originalname).toLowerCase() : "";
    save(null, `${crypto.randomUUID()}${extension}`);
  },
});

/*--Receives the files of an upload--*/
export const upload = multer({
  storage,
  defParamCharset: "utf8", // keep names like "Rechnung-Müller.pdf" as they are
  limits: {
    fileSize: envConfig.MAX_FILE_SIZE_MB * 1024 * 1024,
    files: envConfig.MAX_FILES,
  },
});
