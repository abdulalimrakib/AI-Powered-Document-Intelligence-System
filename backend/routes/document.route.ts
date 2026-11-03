import { Router } from "express";
import { getDocument, listDocuments, reprocessDocument, uploadDocuments } from "../controllers/document.controller";
import { upload } from "../lib/upload";
import { asyncHandler } from "../utils/response";

const router = Router();

/*--Documents--*/
router.post("/", upload.array("files"), asyncHandler(uploadDocuments));
router.get("/", asyncHandler(listDocuments));
router.get("/:id", asyncHandler(getDocument));
router.post("/:id/reprocess", asyncHandler(reprocessDocument));

export default router;
