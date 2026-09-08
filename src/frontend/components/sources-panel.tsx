import type { Source } from "@/types/archivist";
import { TrustBadge } from "@/components/trust-badge";
import { ScrollIcon } from "@/components/icons";

export function SourcesPanel({ sources }: { sources: Source[] | null }) {
  return (
    <aside className="card-elevated flex h-full w-72 shrink-0 flex-col overflow-hidden rounded-xl">
      <div className="border-border flex items-center gap-2 border-b px-5 py-4">
        <ScrollIcon className="text-muted-foreground h-4.5 w-4.5" />
        <h2 className="font-serif text-[15px] font-semibold tracking-tight">
          Sources
        </h2>
      </div>
      <div className="scrollbar-thin flex-1 overflow-y-auto p-4">
        {!sources || sources.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-3 py-12 text-center">
            <span className="border-border bg-muted text-muted-foreground/70 flex h-11 w-11 items-center justify-center rounded-full border">
              <ScrollIcon className="h-5 w-5" />
            </span>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Sources will appear here once you ask a question.
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {sources.map((source, i) => (
              <li
                key={`${source.title}-${i}`}
                className="card-elevated rounded-lg p-3.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-serif text-[13.5px] leading-snug font-semibold">
                    {source.title}
                  </span>
                  {source.category && (
                    <span className="border-border bg-muted/50 text-muted-foreground rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider">
                      {source.category}
                    </span>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <TrustBadge trust={source.trust} />
                  {source.vector_score !== undefined && source.vector_score !== null && (
                    <span className="border-border bg-background text-muted-foreground rounded border px-1.5 py-0.5 text-[10.5px] font-mono">
                      Sim: {source.vector_score.toFixed(3)}
                    </span>
                  )}
                  {source.epistemic_weight !== undefined && (
                    <span className="border-border bg-background text-muted-foreground rounded border px-1.5 py-0.5 text-[10.5px] font-mono">
                      Auth: {source.epistemic_weight}
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground mt-2.5 line-clamp-3 text-xs leading-relaxed">
                  {source.snippet}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
