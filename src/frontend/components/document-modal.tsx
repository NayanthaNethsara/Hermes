"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchDocumentDetails } from "@/lib/api";
import type { DocumentDetails } from "@/types/hermes";
import { BookOpen, X, Image as ImageIcon } from "lucide-react";
import { cleanWikilinks } from "@/lib/utils";
import { useModalFocus } from "@/lib/use-modal-focus";

export function DocumentModal({
  docId,
  onClose,
  onSelectImage,
}: {
  docId: string | null;
  onClose: () => void;
  onSelectImage?: (imagePath: string) => void;
}) {
  const [doc, setDoc] = useState<DocumentDetails | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useModalFocus<HTMLDivElement>(Boolean(docId), onClose);

  useEffect(() => {
    if (!docId) return;

    let isCancelled = false;
    const loadDocument = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await fetchDocumentDetails(docId);
        if (!isCancelled) setDoc(data);
      } catch (err) {
        if (!isCancelled) {
          setError(err instanceof Error ? err.message : "Failed to load document");
        }
      } finally {
        if (!isCancelled) setIsLoading(false);
      }
    };

    void loadDocument();

    return () => {
      isCancelled = true;
    };
  }, [docId]);

  if (!docId) return null;

  const displayTitle = docId.replace(/_/g, " ");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 md:p-10">
      <div
        className="fixed inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-modal-title"
        tabIndex={-1}
        className="card-elevated relative z-10 flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl outline-none"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-muted/20">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/60 text-primary">
              <BookOpen size={16} />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2
                  id="document-modal-title"
                  className="font-serif text-[17px] font-semibold text-foreground capitalize"
                >
                  {displayTitle}
                </h2>
                {doc && (
                  <span className="rounded border border-border bg-muted/80 px-2 py-0.5 text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
                    {doc.source_category}
                  </span>
                )}
                {doc && (
                  <span className="rounded border border-border bg-background px-2 py-0.5 font-mono text-[10.5px] text-muted-foreground">
                    Auth: {doc.epistemic_weight}
                  </span>
                )}
              </div>
              <p className="font-mono text-[11px] text-muted-foreground mt-0.5">
                doc_id: {docId} {doc && `• ${doc.total_chunks} chunks indexed`}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close document"
            data-autofocus
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
              <span className="h-6 w-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              <p className="text-sm">Loading archive record...</p>
            </div>
          ) : error ? (
            <div className="rounded-xl border border-border bg-destructive/10 p-6 text-center text-sm text-foreground/80">
              <p className="font-medium text-destructive mb-1">Document Unavailable</p>
              <p className="text-xs text-muted-foreground">{error}</p>
            </div>
          ) : doc ? (
            <div className="space-y-6">
              {doc.chunks.map((chunk, index) => (
                <article
                  key={chunk.chunk_id || index}
                  className="rounded-xl border border-border bg-background/50 p-5 space-y-3 transition-colors hover:border-border/80"
                >
                  <div className="flex items-center justify-between border-b border-border/40 pb-2">
                    <h3 className="font-serif text-[15px] font-semibold text-foreground/95">
                      {chunk.section_title || `Section ${index + 1}`}
                    </h3>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      Chunk {index + 1} of {doc.total_chunks}
                    </span>
                  </div>

                  <div className="text-[14px] leading-relaxed text-[#d4d4d8] space-y-2 font-sans">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h1: ({ children }) => (
                          <h1 className="text-[17px] font-medium text-white mt-3 mb-1.5">
                            {children}
                          </h1>
                        ),
                        h2: ({ children }) => (
                          <h2 className="text-[15.5px] font-medium text-white mt-2.5 mb-1">
                            {children}
                          </h2>
                        ),
                        h3: ({ children }) => (
                          <h3 className="text-[14.5px] font-medium text-[#e4e4e7] mt-2 mb-1">
                            {children}
                          </h3>
                        ),
                        p: ({ children }) => (
                          <div className="leading-relaxed text-[#d4d4d8] mb-2 last:mb-0">
                            {children}
                          </div>
                        ),
                        strong: ({ children }) => (
                          <strong className="font-medium text-white">{children}</strong>
                        ),
                        ul: ({ children }) => (
                          <ul className="my-2 list-disc pl-5 space-y-1 text-[13.5px]">
                            {children}
                          </ul>
                        ),
                        ol: ({ children }) => (
                          <ol className="my-2 list-decimal pl-5 space-y-1 text-[13.5px]">
                            {children}
                          </ol>
                        ),
                        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                        table: ({ children }) => (
                          <div className="my-3 overflow-x-auto rounded-lg border border-white/10 bg-[#161618]">
                            <table className="w-full border-collapse text-left text-[13px]">
                              {children}
                            </table>
                          </div>
                        ),
                        th: ({ children }) => (
                          <th className="border-b border-white/10 bg-white/5 px-3 py-2 font-medium text-white">
                            {children}
                          </th>
                        ),
                        td: ({ children }) => (
                          <td className="border-b border-white/5 px-3 py-2 text-[#a1a1aa] last:border-b-0">
                            {children}
                          </td>
                        ),
                        code: ({ children }) => (
                          <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12.5px] font-mono text-[#f4f4f5]">
                            {children}
                          </code>
                        ),
                      }}
                    >
                      {cleanWikilinks(chunk.content)}
                    </ReactMarkdown>
                  </div>

                  {chunk.figures && chunk.figures.length > 0 && (
                    <div className="pt-2 border-t border-border/30">
                      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                        <ImageIcon size={14} />
                        Associated Visual Plates
                      </p>
                      <div className="flex flex-wrap gap-2.5">
                        {chunk.figures.map((fig, figIdx) => (
                          <button
                            key={figIdx}
                            type="button"
                            onClick={() => onSelectImage && onSelectImage(fig)}
                            className="group flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-left hover:border-foreground/40 transition-colors"
                          >
                            <span className="h-8 w-8 rounded overflow-hidden bg-background shrink-0 flex items-center justify-center border border-border/60">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={fig}
                                alt="Plate"
                                className="max-h-full max-w-full object-contain"
                              />
                            </span>
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-foreground group-hover:text-primary transition-colors truncate">
                                {fig.split("/").pop()}
                              </p>
                              <p className="text-[10px] text-muted-foreground">
                                Click to inspect plate
                              </p>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : null}
        </div>

        <div className="border-t border-border px-6 py-3 bg-muted/20 flex items-center justify-between text-xs text-muted-foreground">
          <span>Press ESC or click outside to return to chat</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border bg-card px-3 py-1.5 font-medium hover:bg-muted text-foreground transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
