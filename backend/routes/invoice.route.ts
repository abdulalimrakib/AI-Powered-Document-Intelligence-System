import { Router } from "express";
import { correctInvoice } from "../controllers/invoice.controller";
import { asyncHandler } from "../utils/response";

const router = Router();

/*--Invoices--*/
router.patch("/:id", asyncHandler(correctInvoice));

export default router;
