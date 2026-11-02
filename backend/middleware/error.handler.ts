import { NextFunction, Request, Response } from "express";

/*--Unknown route--*/
export const notFound = (req: Request, res: Response) => {
  res.status(404).json({
    success: false,
    message: `Route not found: ${req.method} ${req.originalUrl}`,
    statusCode: 404,
    data: null,
  });
};

/*--Any error thrown in a route ends up here--*/
// Express needs all four parameters to know this is an error handler.
export const errorHandler = (err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error(err);
  res.status(500).json({
    success: false,
    message: "Internal server error",
    statusCode: 500,
    data: null,
  });
};
