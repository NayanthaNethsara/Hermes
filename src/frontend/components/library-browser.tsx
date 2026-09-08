"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, BookOpen, Image as ImageIcon, Search } from "lucide-react";
import {
  groupChunksIntoDocuments,
  isAbortError,
  searchArchive,
} from "@/lib/api";
import { LIBRARY_SEED_QUERY } from "@/lib/constants";
import { DocumentModal } from "@/components/document-modal";
import { ImageLightbox } from "@/components/image-lightbox";
import type { ArchiveDocument } from "@/types/hermes";

const ALL_CATEGORIES = "all";

function formatDocumentTitle(docId: string): string {
  return docId
    .replace(/^plate_\d+_/, "")
    .replace(/^atmo_[a-z]+_/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function DocumentTile({
  document,
  onSelectDocument,
  onSelectImage,
}: {
  document: ArchiveDocument;
  onSelectDocument: (docId: string) => void;
  onSelectImage: (imagePath: string) => void;
}) {
  const coverFigure = document.figures[0];

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-foreground/25">
      <button
        type="button"
        onClick={() => onSelectDocument(document.doc_id)}
        className="flex flex-1 flex-col items-start gap-2 p-4 text-left cursor-pointer"
      >
        <div className="flex w-full items-start justify-between gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-muted-foreground">
            {coverFigure ? <ImageIcon size={14} /> : <BookOpen size={14} />}
          </span>
          <span className="rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
            {document.category}
          </span>
        </div>

        <h2 className="line-clamp-2 text-[13.5px] font-medium leading-snug text-foreground">
          {formatDocumentTitle(document.doc_id)}
        </h2>

        <p className="line-clamp-3 text-[11.5px] leading-relaxed text-muted-foreground">
          {document.excerpt}
        </p>

        <div className="mt-auto flex w-full items-center gap-2 pt-2 font-mono text-[10px] text-muted-foreground">
          <span>
            {document.chunk_count} chunk{document.chunk_count === 1 ? "" : "s"}
          </span>
          {document.epistemic_weight !== null && (
            <>
              <span aria-hidden="true">·</span>
              <span>weight {document.epistemic_weight.toFixed(2)}</span>
            </>
          )}
        </div>
      </button>

      {coverFigure && (
        <button
          type="button"
          onClick={() => onSelectImage(coverFigure)}
          className="flex items-center gap-2 border-t border-border bg-muted/20 px-4 py-2 text-left text-[10.5px] text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors cursor-pointer"
        >
          <ImageIcon size={12} className="shrink-0" />
          <span className="truncate">
            {document.figures.length} plate
            {document.figures.length === 1 ? "" : "s"} — inspect
          </span>
        </button>
      )}
    </div>
  );
}

export function LibraryBrowser() {
  const [inputValue, setInputValue] = useState("");
  const [documents, setDocuments] = useState<ArchiveDocument[]>([]);
  const [activeCategory, setActiveCategory] = useState(ALL_CATEGORIES);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedImagePath, setSelectedImagePath] = useState<string | null>(null);

  const activeRequest = useRef<AbortController | null>(null);

  const applySearch = useCallback(
    (query: string, controller: AbortController) =>
      searchArchive(query, controller.signal)
        .then((response) => {
          setDocuments(groupChunksIntoDocuments(response.results || []));
          setActiveCategory(ALL_CATEGORIES);
          setError(null);
        })
        .catch((err: unknown) => {
          if (isAbortError(err)) return;
          setError(
            err instanceof Error ? err.message : "The archive search failed."
          );
          setDocuments([]);
        })
        .finally(() => {
          if (activeRequest.current === controller) {
            activeRequest.current = null;
            setIsLoading(false);
          }
        }),
    []
  );

  const runSearch = useCallback(
    (query: string) => {
      activeRequest.current?.abort();
      const controller = new AbortController();
      activeRequest.current = controller;
      setIsLoading(true);
      void applySearch(query, controller);
    },
    [applySearch]
  );

  useEffect(() => {
    const controller = new AbortController();
    activeRequest.current = controller;
    void applySearch(LIBRARY_SEED_QUERY, controller);
    return () => controller.abort();
  }, [applySearch]);

  const categories = [
    ALL_CATEGORIES,
    ...[...new Set(documents.map((doc) => doc.category))].sort(),
  ];

  const visibleDocuments =
    activeCategory === ALL_CATEGORIES
      ? documents
      : documents.filter((doc) => doc.category === activeCategory);

  return (
    <div className="flex h-screen w-full flex-col bg-background text-foreground">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <Link
            href="/chat"
            aria-label="Back to chat"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="flex items-baseline gap-2">
            <span className="text-[13.5px] font-medium tracking-tight text-foreground">
              Archive Library
            </span>
            <span className="text-[11px] text-muted-foreground">
              {documents.length} record{documents.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="mx-auto w-full max-w-5xl px-4 py-6 space-y-5">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const trimmed = inputValue.trim();
              if (trimmed && !isLoading) runSearch(trimmed);
            }}
            className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 focus-within:border-foreground/25 transition-colors"
          >
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
            <input
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              placeholder="Search the archive for people, places, relics..."
              aria-label="Search the archive"
              className="w-full bg-transparent text-[14px] text-foreground placeholder-muted-foreground outline-none"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || isLoading}
              className="shrink-0 rounded-md border border-border bg-muted px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
            >
              Search
            </button>
          </form>

          {categories.length > 2 && (
            <div className="flex flex-wrap gap-1.5">
              {categories.map((category) => (
                <button
                  key={category}
                  type="button"
                  onClick={() => setActiveCategory(category)}
                  className={`rounded-full border px-3 py-1 text-[11px] capitalize transition-colors cursor-pointer ${
                    activeCategory === category
                      ? "border-border bg-accent text-foreground"
                      : "border-border bg-card text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {category}
                </button>
              ))}
            </div>
          )}

          {isLoading ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div
                  key={index}
                  className="h-44 animate-pulse rounded-xl border border-border bg-card"
                />
              ))}
            </div>
          ) : error ? (
            <div className="rounded-xl border border-border bg-destructive/10 p-6 text-center">
              <p className="text-sm font-medium text-destructive">
                Archive unavailable
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{error}</p>
            </div>
          ) : visibleDocuments.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
              No records matched that search.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {visibleDocuments.map((document) => (
                <DocumentTile
                  key={document.doc_id}
                  document={document}
                  onSelectDocument={setSelectedDocId}
                  onSelectImage={setSelectedImagePath}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <DocumentModal
        docId={selectedDocId}
        onClose={() => setSelectedDocId(null)}
        onSelectImage={setSelectedImagePath}
      />

      <ImageLightbox
        imagePath={selectedImagePath}
        onClose={() => setSelectedImagePath(null)}
      />
    </div>
  );
}
