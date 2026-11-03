import { Router } from "express";
import { searchInvoices } from "../controllers/search.controller";
import { asyncHandler } from "../utils/response";

const router = Router();

/*--Search--*/
router.get("/", asyncHandler(searchInvoices));

export default router;
