import type { Source } from "@/constants/mock/mockResponses";
import { TrustBadge } from "@/components/trust-badge";
import { ScrollIcon } from "@/components/icons";

export function SourcesPanel({ sources }: { sources: Source[] | null }) {
  return (
    <aside className="card-elevated flex h-full w-72 shrink-0 flex-col overflow-hidden rounded-xl">
      <div className="border-border flex items-center gap-2 border-b px-5 py-4">
        <ScrollIcon className="text-primary h-4.5 w-4.5" />
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
                </div>
                <div className="mt-2">
                  <TrustBadge trust={source.trust} />
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
