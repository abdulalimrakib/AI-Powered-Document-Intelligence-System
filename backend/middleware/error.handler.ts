import { NextFunction, Request, Response } from "express";
import { MulterError } from "multer";
import envConfig from "../config/env.config";
import { sendResponse } from "../utils/response";

/*--Unknown route--*/
export const notFound = (req: Request, res: Response) => {
  sendResponse(res, 404, `Route not found: ${req.method} ${req.originalUrl}`);
};

/*--Upload problems, in plain words--*/
const UPLOAD_ERRORS: Record<string, [number, string]> = {
  LIMIT_FILE_SIZE: [413, `A file is bigger than ${envConfig.MAX_FILE_SIZE_MB} MB. Nothing was uploaded.`],
  LIMIT_FILE_COUNT: [400, `Too many files: upload at most ${envConfig.MAX_FILES} at once. Nothing was uploaded.`],
  LIMIT_UNEXPECTED_FILE: [400, "Send the files in the form field 'files'."],
};

/*--Any error thrown in a route ends up here--*/
// Express needs all four parameters to know this is an error handler.
export const errorHandler = (err: Error, req: Request, res: Response, next: NextFunction) => {
  if (err instanceof MulterError) {
    const [statusCode, message] = UPLOAD_ERRORS[err.code] ?? [400, `Upload failed: ${err.message}`];
    return sendResponse(res, statusCode, message);
  }
  console.error(err);
  sendResponse(res, 500, "Internal server error");
};
