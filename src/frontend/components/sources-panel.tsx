import type { Source } from "@/types/archivist";
import { TrustBadge } from "@/components/trust-badge";
import { BookOpen, Image as ImageIcon, Scroll } from "lucide-react";

export function SourcesPanel({
  sources,
  onSelectDocument,
  onSelectImage,
}: {
  sources: Source[] | null;
  onSelectDocument?: (docId: string) => void;
  onSelectImage?: (imagePath: string) => void;
}) {
  return (
    <div className="w-full rounded-2xl border border-white/10 bg-[#1e1f20] overflow-hidden flex flex-col">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3 bg-[#18191a]">
        <div className="flex items-center gap-2 text-white text-xs font-semibold uppercase tracking-wider">
          <Scroll size={14} className="text-[#7cacf8]" />
          <span>Retrieved Sources</span>
        </div>
        {sources && sources.length > 0 && (
          <span className="rounded-full bg-white/5 px-2 py-0.5 font-mono text-[10.5px] text-[#9aa0a6]">
            {sources.length} matched
          </span>
        )}
      </div>

      <div className="p-3">
        {!sources || sources.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-[#9aa0a6]">
            <Scroll size={24} className="opacity-40" />
            <p className="text-xs">No active sources loaded.</p>
          </div>
        ) : (
          <ul className="space-y-2.5">
            {sources.map((source, i) => (
              <li
                key={`${source.title}-${i}`}
                onClick={() => onSelectDocument && onSelectDocument(source.title)}
                className="group cursor-pointer rounded-xl border border-white/5 bg-[#18191a] p-3 transition-all hover:border-white/20"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-white group-hover:text-[#7cacf8] transition-colors truncate">
                    {source.title.replace(/_/g, " ")}
                  </span>
                  {source.category && (
                    <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9.5px] font-mono text-[#9aa0a6] uppercase shrink-0">
                      {source.category}
                    </span>
                  )}
                </div>

                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <TrustBadge trust={source.trust} />
                  {source.vector_score !== undefined && source.vector_score !== null && (
                    <span className="rounded bg-black/40 px-1.5 py-0.5 text-[10px] font-mono text-[#9aa0a6]">
                      Sim: {source.vector_score.toFixed(2)}
                    </span>
                  )}
                </div>

                <p className="text-[#9aa0a6] mt-2 line-clamp-2 text-[11.5px] leading-relaxed">
                  {source.snippet}
                </p>

                {source.figures && source.figures.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-white/5 flex items-center gap-2">
                    <span className="text-[10px] text-[#9aa0a6] flex items-center gap-1">
                      <ImageIcon size={11} /> {source.figures.length} figure{source.figures.length > 1 ? "s" : ""}:
                    </span>
                    <div className="flex gap-1 overflow-hidden">
                      {source.figures.map((fig, figIdx) => (
                        <button
                          key={figIdx}
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (onSelectImage) onSelectImage(fig);
                          }}
                          className="h-5 w-5 rounded border border-white/10 bg-black/40 overflow-hidden hover:scale-110 transition-transform shrink-0"
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={fig}
                            alt="thumb"
                            className="h-full w-full object-contain"
                          />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-2 flex items-center justify-end text-[10.5px] text-[#7cacf8] opacity-0 group-hover:opacity-100 transition-opacity gap-1">
                  <BookOpen size={11} />
                  <span>Open record</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
