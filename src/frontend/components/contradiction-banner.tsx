import type { Contradiction } from "@/types/archivist";
import { AlertIcon } from "@/components/icons";

export function ContradictionBanner({
  contradictions,
}: {
  contradictions: Contradiction[];
}) {
  if (contradictions.length === 0) return null;

  return (
    <div className="mb-2.5 flex gap-2.5 rounded-lg border border-amber-500/25 bg-amber-500/8 py-2.5 pr-3.5 pl-3">
      <AlertIcon className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
      <div className="space-y-1 text-[13px] leading-relaxed text-amber-200/90">
        {contradictions.map((c, i) => (
          <p key={`${c.topic}-${i}`}>
            <span className="font-semibold text-amber-300">
              Sources disagree on {c.topic}:
            </span>{" "}
            {c.sources_disagree.join(" vs. ")}
          </p>
        ))}
      </div>
    </div>
  );
}
