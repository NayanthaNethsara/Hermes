import type { Contradiction } from "@/types/hermes";

export function ContradictionBanner({
  contradictions,
}: {
  contradictions: Contradiction[];
}) {
  if (contradictions.length === 0) return null;

  const uniqueContradictions = contradictions.filter(
    (item, index, self) =>
      index ===
      self.findIndex(
        (target) =>
          target.topic.trim().toLowerCase() === item.topic.trim().toLowerCase()
      )
  );

  return (
    <div className="mb-3 rounded-r-lg border-l-2 border-amber-500/60 bg-amber-500/5 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-amber-200/90">
      {uniqueContradictions.map((c, i) => (
        <p key={`${c.topic}-${i}`}>
          <span className="font-medium text-amber-300">Disagreement on {c.topic}:</span>{" "}
          {c.sources_disagree.join(" vs. ")}
        </p>
      ))}
    </div>
  );
}
