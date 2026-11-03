import { NextFunction, Request, Response } from "express";

/*--Send a response in the shape every API uses--*/
// { success, message, statusCode, data }
export const sendResponse = (res: Response, statusCode: number, message: string, data: unknown = null) => {
  return res.status(statusCode).json({ success: statusCode < 400, message, statusCode, data });
};

/*--Catch errors in async routes--*/
// Express 4 does not see errors thrown inside an async function. This passes them to the error handler,
// so a database error gives a clean 500 response instead of a request that hangs forever.
export const asyncHandler =
  (route: (req: Request, res: Response, next: NextFunction) => Promise<unknown>) =>
  (req: Request, res: Response, next: NextFunction) => {
    route(req, res, next).catch(next);
  };
