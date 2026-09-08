import { z } from "zod";
import { QUERY_CONSTRAINTS } from "@/lib/constants";

export const AskQuerySchema = z.object({
  question: z
    .string()
    .trim()
    .min(QUERY_CONSTRAINTS.MIN_LENGTH, "Question cannot be empty.")
    .max(
      QUERY_CONSTRAINTS.MAX_LENGTH,
      `Question is too long (maximum ${QUERY_CONSTRAINTS.MAX_LENGTH} characters).`
    ),
});

export type AskQueryInput = z.infer<typeof AskQuerySchema>;

export const DocumentIdSchema = z
  .string()
  .trim()
  .min(1, "Document ID cannot be empty.")
  .regex(/^[a-zA-Z0-9_\-.]+$/, "Invalid document ID format.");

export const VisualFilenameSchema = z
  .string()
  .trim()
  .min(1, "Visual filename cannot be empty.");
