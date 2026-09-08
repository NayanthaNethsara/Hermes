"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { HermesResponse } from "@/types/hermes";
import { ContradictionBanner } from "@/components/contradiction-banner";
import { TrustBadge } from "@/components/trust-badge";
import { cleanWikilinks } from "@/lib/utils";

function formatFigureCaption(path: string): string {
  const filename = path.split("/").pop() || path;
  return filename
    .replace(/^plate_\d+_/, "")
    .replace(/^atmo_[a-z]+_[a-z]+_/, "")
    .replace(/^atmo_[a-z]+_/, "")
    .replace(/\.png$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function AnswerCard({
  question,
  response,
  statusMessage,
  isStreaming,
  onSelectDocument,
  onSelectImage,
}: {
  question: string;
  response: HermesResponse | null;
  statusMessage?: string;
  isStreaming?: boolean;
  onSelectDocument?: (docId: string) => void;
  onSelectImage?: (imagePath: string) => void;
}) {
  const [showSources, setShowSources] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);

  const answerText = response?.answer || "";
  const standaloneFigures = (response?.referenced_figures || []).filter((figureUrl) => {
    const filename = figureUrl.split("/").pop() || figureUrl;
    return !answerText.includes(figureUrl) && !answerText.includes(filename);
  });

  const hasContent = Boolean(
    response && (response.answer || (response.sources && response.sources.length > 0))
  );

  return (
    <div className="space-y-4 w-full max-w-2xl mx-auto py-1">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-[#1c1c1f] text-[#ededed] px-4 py-2.5 text-[14px] leading-relaxed border border-white/5">
          {question}
        </div>
      </div>

      <div className="space-y-4">
        {!hasContent ? (
          <div className="space-y-4 py-2">
            <div className="flex items-center gap-2.5 text-xs text-[#a1a1aa] font-mono">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white/40 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-white/80" />
              </span>
              <span>{statusMessage || "Searching archive with hybrid vector search..."}</span>
            </div>

            <div className="space-y-2.5 pt-1 max-w-xl">
              <div className="h-3.5 w-11/12 rounded bg-white/[0.06] animate-pulse" />
              <div className="h-3.5 w-full rounded bg-white/[0.04] animate-pulse" />
              <div className="h-3.5 w-4/5 rounded bg-white/[0.05] animate-pulse" />
            </div>
          </div>
        ) : (
          <div className="space-y-3.5">
            {isStreaming && !response?.answer && (
              <div className="space-y-4 py-2">
                <div className="flex items-center gap-2.5 text-xs text-[#a1a1aa] font-mono">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white/40 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-white/80" />
                  </span>
                  <span>{statusMessage || "Synthesizing answer from archive sources..."}</span>
                </div>

                <div className="space-y-2.5 pt-1 max-w-xl">
                  <div className="h-3.5 w-11/12 rounded bg-white/[0.06] animate-pulse" />
                  <div className="h-3.5 w-full rounded bg-white/[0.04] animate-pulse" />
                  <div className="h-3.5 w-4/5 rounded bg-white/[0.05] animate-pulse" />
                </div>
              </div>
            )}

            <div className="text-[14.5px] leading-relaxed text-[#d4d4d8] space-y-3 font-sans">
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
                    <div className="leading-relaxed text-[#d4d4d8] mb-2.5 last:mb-0">
                      {children}
                    </div>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-medium text-white">
                      {children}
                    </strong>
                  ),
                  ul: ({ children }) => (
                    <ul className="my-2 list-disc pl-5 space-y-1 text-[14px]">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="my-2 list-decimal pl-5 space-y-1 text-[14px]">
                      {children}
                    </ol>
                  ),
                  li: ({ children }) => (
                    <li className="leading-relaxed">{children}</li>
                  ),
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
                  blockquote: ({ children }) => (
                    <blockquote className="my-2 border-l-2 border-white/20 pl-3 italic text-[#a1a1aa]">
                      {children}
                    </blockquote>
                  ),
                  code: ({ children }) => (
                    <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12.5px] font-mono text-[#f4f4f5]">
                      {children}
                    </code>
                  ),
                  img: ({ src, alt }) => (
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={() => {
                        if (typeof src === "string" && onSelectImage) {
                          onSelectImage(src);
                        }
                      }}
                      onKeyDown={(e) => {
                        if ((e.key === "Enter" || e.key === " ") && typeof src === "string" && onSelectImage) {
                          e.preventDefault();
                          onSelectImage(src);
                        }
                      }}
                      className="group my-3 block max-w-md mx-auto overflow-hidden rounded-xl border border-white/10 bg-[#141416] cursor-pointer hover:border-white/20 transition-colors shadow-lg"
                      title="Inspect plate"
                    >
                      {src && (
                        <div className="h-64 sm:h-72 w-full bg-black/30 flex items-center justify-center p-2">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={src}
                            alt={alt || "Archive Visual"}
                            className="max-h-full max-w-full object-contain block drop-shadow-md"
                          />
                        </div>
                      )}
                      <span className="border-t border-white/5 bg-[#121214] px-3.5 py-2 flex items-center justify-between text-[11px] text-[#71717a]">
                        <span className="font-medium text-white truncate max-w-[280px]">
                          {alt || "Visual Evidence"}
                        </span>
                        <span className="text-[#a1a1aa] shrink-0">Click to inspect</span>
                      </span>
                    </span>
                  ),
                }}
              >
                {response?.answer ? cleanWikilinks(response.answer) : ""}
              </ReactMarkdown>
              {isStreaming && response?.answer && (
                <span className="inline-block w-1.5 h-3.5 ml-1 bg-white/70 animate-pulse align-middle" />
              )}
            </div>

            <ContradictionBanner
              contradictions={response?.contradictions || []}
              sources={response?.sources || []}
              onSelectDocument={onSelectDocument}
            />

            {!isStreaming && standaloneFigures.length > 0 && (
              <div className="pt-3 border-t border-white/5 space-y-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto">
                  {standaloneFigures.map((figureUrl, index) => (
                    <button
                      key={index}
                      type="button"
                      onClick={() => onSelectImage && onSelectImage(figureUrl)}
                      className="group flex flex-col overflow-hidden rounded-xl border border-white/10 bg-[#141416] hover:border-white/20 text-left cursor-pointer transition-colors shadow-lg"
                    >
                      <div className="h-44 w-full bg-black/30 flex items-center justify-center p-2">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={figureUrl}
                          alt={formatFigureCaption(figureUrl)}
                          className="max-h-full max-w-full object-contain block drop-shadow-md"
                        />
                      </div>
                      <div className="border-t border-white/5 px-3 py-2 bg-[#121214] flex items-center justify-between">
                        <p className="text-[11.5px] font-medium text-white truncate">
                          {formatFigureCaption(figureUrl)}
                        </p>
                        <span className="text-[10px] text-[#71717a]">Inspect</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="pt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
              {response?.citations && response.citations.length > 0 ? (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-[#71717a]">Sources:</span>
                  {response.citations.map((cite, index) => (
                    <button
                      key={index}
                      type="button"
                      onClick={() => onSelectDocument && onSelectDocument(cite)}
                      className="px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 text-[11px] font-mono text-[#a1a1aa] hover:text-white transition-colors cursor-pointer"
                      title="View document record"
                    >
                      {cite}
                    </button>
                  ))}
                </div>
              ) : <div />}

              <div className="flex items-center gap-2">
                {response?.sources && response.sources.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowSources(!showSources)}
                    className="text-[11.5px] text-[#71717a] hover:text-white transition-colors cursor-pointer"
                  >
                    {showSources ? "Hide sources" : `${response.sources.length} sources`}
                  </button>
                )}

                {response?.reasoning_steps && response.reasoning_steps.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowReasoning(!showReasoning)}
                    className="text-[11.5px] text-[#71717a] hover:text-white transition-colors cursor-pointer"
                  >
                    {showReasoning ? "Hide trace" : `Trace (${response.reasoning_steps.length} steps)`}
                  </button>
                )}
              </div>
            </div>

            {showSources && response?.sources && response.sources.length > 0 && (
              <div className="rounded-xl border border-white/5 bg-[#141416] p-3 space-y-2.5 text-xs">
                {response.sources.map((src, i) => (
                  <div
                    key={i}
                    onClick={() => onSelectDocument && onSelectDocument(src.title)}
                    className="p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors cursor-pointer space-y-1.5 border border-white/5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-white text-[12px] truncate">
                        {src.title.replace(/_/g, " ")}
                      </span>
                      <TrustBadge trust={src.trust} />
                    </div>
                    <div className="text-[#a1a1aa] leading-relaxed text-[11.5px]">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ children }) => (
                            <h4 className="text-[12px] font-semibold text-white mt-1 mb-0.5">
                              {children}
                            </h4>
                          ),
                          h2: ({ children }) => (
                            <h5 className="text-[11.5px] font-semibold text-white mt-1 mb-0.5">
                              {children}
                            </h5>
                          ),
                          h3: ({ children }) => (
                            <h6 className="text-[11px] font-medium text-[#e4e4e7] mt-0.5 mb-0.5">
                              {children}
                            </h6>
                          ),
                          p: ({ children }) => (
                            <div className="mb-1 last:mb-0 leading-relaxed text-[#a1a1aa]">
                              {children}
                            </div>
                          ),
                          strong: ({ children }) => (
                            <strong className="font-medium text-white">
                              {children}
                            </strong>
                          ),
                          ul: ({ children }) => (
                            <ul className="my-1 list-disc pl-4 space-y-0.5 text-[11px]">
                              {children}
                            </ul>
                          ),
                          ol: ({ children }) => (
                            <ol className="my-1 list-decimal pl-4 space-y-0.5 text-[11px]">
                              {children}
                            </ol>
                          ),
                          li: ({ children }) => (
                            <li className="leading-relaxed">{children}</li>
                          ),
                          table: ({ children }) => (
                            <div className="my-1.5 overflow-x-auto rounded border border-white/10 bg-black/20">
                              <table className="w-full border-collapse text-left text-[11px]">
                                {children}
                              </table>
                            </div>
                          ),
                          th: ({ children }) => (
                            <th className="border-b border-white/10 bg-white/5 px-2.5 py-1 font-medium text-white">
                              {children}
                            </th>
                          ),
                          td: ({ children }) => (
                            <td className="border-b border-white/5 px-2.5 py-1 text-[#a1a1aa] last:border-b-0">
                              {children}
                            </td>
                          ),
                          code: ({ children }) => (
                            <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[10.5px] text-white">
                              {children}
                            </code>
                          ),
                        }}
                      >
                        {cleanWikilinks(src.snippet.replace(/!\[.*?\]\(.*?\)/g, ""))}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {showReasoning && response?.reasoning_steps && response.reasoning_steps.length > 0 && (
              <div className="rounded-xl border border-white/10 bg-[#121214] p-3.5 space-y-3 text-xs">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <span className="text-[11px] font-medium text-white/80 uppercase tracking-wider font-mono">
                    Agent Investigation Trace
                  </span>
                  <span className="text-[10px] text-emerald-400 font-mono bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                    {response.reasoning_steps.length} Steps
                  </span>
                </div>
                <div className="space-y-3 relative before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-px before:bg-white/10">
                  {response.reasoning_steps.map((step) => (
                    <div key={step.step} className="relative flex items-start gap-3 pl-0 text-[11.5px]">
                      <span className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#1e1e22] border border-white/20 font-mono text-[10px] text-white font-medium">
                        {step.step}
                      </span>
                      <div className="flex-1 min-w-0 space-y-1">
                        <p className="text-white font-medium text-[12px]">{step.action}</p>
                        <div className="text-[#a1a1aa] text-[11px] leading-relaxed bg-white/[0.02] p-2 rounded-lg border border-white/5">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              p: ({ children }) => <span>{children}</span>,
                              code: ({ children }) => (
                                <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[10.5px] text-white">
                                  {children}
                                </code>
                              ),
                            }}
                          >
                            {cleanWikilinks(step.found)}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
