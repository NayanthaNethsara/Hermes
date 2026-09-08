import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ArchivistResponse } from "@/types/archivist";
import { ContradictionBanner } from "@/components/contradiction-banner";
import { ImageIcon } from "@/components/icons";

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
}: {
  question: string;
  response: ArchivistResponse | null;
}) {
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <p className="max-w-[80%] rounded-2xl rounded-br-md bg-stone-700 px-4 py-2.5 text-[14px] leading-relaxed font-medium text-stone-50 shadow-sm">
          {question}
        </p>
      </div>

      <div className="flex flex-col items-start">
        {!response ? (
          <div className="border-border bg-card flex max-w-[80%] items-center gap-1.5 rounded-2xl rounded-bl-md border px-4 py-3.5">
            <span className="bg-muted-foreground/50 h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
            <span className="bg-muted-foreground/50 h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
            <span className="bg-muted-foreground/50 h-1.5 w-1.5 animate-bounce rounded-full" />
          </div>
        ) : (
          <div className="w-full max-w-[85%] space-y-3">
            <ContradictionBanner contradictions={response.contradictions} />

            <div className="border-border bg-card rounded-2xl rounded-bl-md border px-5 py-4 text-[14.5px] leading-relaxed shadow-sm">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({ children }) => (
                    <h1 className="font-serif text-[18px] font-semibold tracking-tight text-foreground my-2.5">
                      {children}
                    </h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="font-serif text-[16px] font-semibold tracking-tight text-foreground my-2">
                      {children}
                    </h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="font-serif text-[15px] font-medium text-foreground my-1.5">
                      {children}
                    </h3>
                  ),
                  p: ({ children }) => (
                    <p className="mb-3 text-[14.5px] leading-relaxed text-foreground/90 last:mb-0">
                      {children}
                    </p>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-semibold text-foreground">
                      {children}
                    </strong>
                  ),
                  ul: ({ children }) => (
                    <ul className="my-2.5 list-disc pl-5 space-y-1 text-[14px] text-foreground/90">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="my-2.5 list-decimal pl-5 space-y-1 text-[14px] text-foreground/90">
                      {children}
                    </ol>
                  ),
                  li: ({ children }) => (
                    <li className="leading-relaxed">{children}</li>
                  ),
                  table: ({ children }) => (
                    <div className="my-3.5 overflow-x-auto rounded-lg border border-border bg-muted/20">
                      <table className="w-full border-collapse text-left text-[13.5px]">
                        {children}
                      </table>
                    </div>
                  ),
                  th: ({ children }) => (
                    <th className="border-b border-border bg-muted/60 px-3.5 py-2 font-medium text-foreground">
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="border-b border-border/40 px-3.5 py-2 text-foreground/80 last:border-b-0">
                      {children}
                    </td>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="my-2.5 border-l-2 border-primary/60 pl-3.5 italic text-muted-foreground">
                      {children}
                    </blockquote>
                  ),
                  code: ({ children }) => (
                    <code className="rounded border border-border bg-muted px-1.5 py-0.5 text-[13px] font-mono text-primary">
                      {children}
                    </code>
                  ),
                  img: ({ src, alt }) => (
                    <div className="my-3 overflow-hidden rounded-lg border border-border bg-muted/30">
                      {src && (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                          src={src}
                          alt={alt || "Archive Visual"}
                          className="max-h-72 w-full object-contain"
                        />
                      )}
                      {alt && (
                        <p className="border-t border-border/50 px-3 py-1.5 text-center text-xs text-muted-foreground">
                          {alt}
                        </p>
                      )}
                    </div>
                  ),
                }}
              >
                {response.answer}
              </ReactMarkdown>

              {response.referenced_figures && response.referenced_figures.length > 0 && (
                <div className="mt-4 pt-3 border-t border-border/60">
                  <div className="flex items-center gap-1.5 mb-2.5 text-muted-foreground text-xs font-medium uppercase tracking-wider">
                    <ImageIcon className="h-3.5 w-3.5" />
                    <span>Referenced Visual Evidence</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {response.referenced_figures.map((figureUrl, index) => (
                      <a
                        key={index}
                        href={figureUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="group flex flex-col overflow-hidden rounded-lg border border-border bg-muted/20 hover:border-foreground/30 transition-colors"
                      >
                        <div className="h-40 w-full overflow-hidden bg-background/50 flex items-center justify-center p-2">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={figureUrl}
                            alt={formatFigureCaption(figureUrl)}
                            className="max-h-full max-w-full object-contain group-hover:scale-105 transition-transform duration-200"
                          />
                        </div>
                        <div className="border-t border-border px-3 py-2 bg-card">
                          <p className="text-xs font-medium text-foreground truncate">
                            {formatFigureCaption(figureUrl)}
                          </p>
                          <p className="text-[10px] text-muted-foreground font-mono truncate">
                            {figureUrl}
                          </p>
                        </div>
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {response.citations && response.citations.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-1.5 pt-2 border-t border-border/40 text-xs text-muted-foreground">
                  <span className="text-[11px] font-medium">Citations:</span>
                  {response.citations.map((cite, index) => (
                    <span
                      key={index}
                      className="border-border bg-muted/40 rounded border px-1.5 py-0.5 font-mono text-[10.5px]"
                    >
                      {cite}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
