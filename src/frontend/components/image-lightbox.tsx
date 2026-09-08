"use client";

import { useEffect, useState } from "react";
import { fetchVisualDetails } from "@/lib/api";
import type { VisualCatalogItem } from "@/types/archivist";
import { CloseIcon, ImageIcon } from "@/components/icons";

export function ImageLightbox({
  imagePath,
  onClose,
}: {
  imagePath: string | null;
  onClose: () => void;
}) {
  const [details, setDetails] = useState<VisualCatalogItem | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!imagePath) {
      setDetails(null);
      return;
    }

    setIsLoading(true);
    fetchVisualDetails(imagePath)
      .then((data) => setDetails(data))
      .catch(() => setDetails(null))
      .finally(() => setIsLoading(false));

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [imagePath, onClose]);

  if (!imagePath) return null;

  const filename = imagePath.split("/").pop() || imagePath;
  const displayTitle = details?.title || filename.replace(/^plate_\d+_/, "").replace(/^atmo_[a-z]+_[a-z]+_/, "").replace(/\.png$/, "").replace(/_/g, " ");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 md:p-10">
      <div
        className="fixed inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      <div className="card-elevated relative z-10 flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl lg:flex-row">
        {/* Left / Main image view */}
        <div className="relative flex flex-1 items-center justify-center bg-background/90 p-4 sm:p-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imagePath}
            alt={displayTitle}
            className="max-h-[50vh] w-auto max-w-full rounded-lg object-contain shadow-md lg:max-h-[82vh]"
          />
        </div>

        {/* Right / Metadata Sidebar */}
        <div className="flex w-full flex-col border-t border-border bg-card lg:w-96 lg:border-t-0 lg:border-l">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <ImageIcon className="text-primary h-4.5 w-4.5" />
              <span className="font-serif text-sm font-semibold tracking-wide uppercase text-muted-foreground">
                Visual Plate Inspector
              </span>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <CloseIcon className="h-4.5 w-4.5" />
            </button>
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto p-5 space-y-5">
            <div>
              <h2 className="font-serif text-[18px] font-semibold leading-snug text-foreground capitalize">
                {displayTitle}
              </h2>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground break-all">
                {imagePath}
              </p>
            </div>

            {isLoading ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-6">
                <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                <span>Retrieving visual analysis...</span>
              </div>
            ) : details ? (
              <div className="space-y-4 text-xs">
                {details.extracted_text && (
                  <div>
                    <h3 className="font-medium text-muted-foreground uppercase tracking-wider mb-1.5 text-[11px]">
                      Inscribed Text / Data
                    </h3>
                    <div className="rounded-lg border border-border bg-muted/40 p-3 font-mono text-foreground/90 whitespace-pre-wrap">
                      {details.extracted_text}
                    </div>
                  </div>
                )}

                {details.attributes && Object.keys(details.attributes).length > 0 && (
                  <div>
                    <h3 className="font-medium text-muted-foreground uppercase tracking-wider mb-2 text-[11px]">
                      Identified Features & Attributes
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(details.attributes).map(([key, val]) => (
                        <div
                          key={key}
                          className="rounded border border-border bg-muted/30 px-2 py-1 text-[11px]"
                        >
                          <span className="text-muted-foreground">{key.replace(/_/g, " ")}: </span>
                          <span className="font-medium text-foreground">
                            {Array.isArray(val) ? val.join(", ") : String(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {details.visual_description && (
                  <div>
                    <h3 className="font-medium text-muted-foreground uppercase tracking-wider mb-1.5 text-[11px]">
                      Visual Scene Analysis
                    </h3>
                    <p className="leading-relaxed text-foreground/85 text-[13px] bg-muted/20 p-3 rounded-lg border border-border/50">
                      {details.visual_description}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground py-4">
                Canonical plate registered in the archive.
              </div>
            )}
          </div>

          <div className="border-t border-border p-3 bg-muted/20 flex justify-end">
            <a
              href={imagePath}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors underline"
            >
              Open raw file
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
