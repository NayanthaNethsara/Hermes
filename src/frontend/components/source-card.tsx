"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "@/types/hermes";
import { TrustBadge } from "@/components/trust-badge";
import { cleanWikilinks } from "@/lib/utils";

function formatScore(score: number): string {
  return score.toFixed(2);
}

function ScoreMeter({ relevance }: { relevance: number }) {
  const percentage = Math.round(Math.min(Math.max(relevance, 0), 1) * 100);

  return (
    <div
      className="h-1 w-full overflow-hidden rounded-full bg-white/5"
      role="meter"
      aria-valuenow={percentage}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Relevance after reranking"
    >
      <div
        className="h-full rounded-full bg-white/40"
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

export function SourceCard({
  source,
  onSelectDocument,
}: {
  source: Source;
  onSelectDocument?: (docId: string) => void;
}) {
  const metaParts = [
    source.section,
    source.category,
    source.epistemic_weight !== undefined
      ? `weight ${formatScore(source.epistemic_weight)}`
      : null,
  ].filter(Boolean) as string[];

  const scoreParts = [
    source.vector_score != null ? `vec ${formatScore(source.vector_score)}` : null,
    source.keyword_score != null ? `kw ${formatScore(source.keyword_score)}` : null,
  ].filter(Boolean) as string[];

  return (
    <div className="overflow-hidden rounded-lg border border-white/5 bg-white/5">
      <button
        type="button"
        onClick={() => onSelectDocument?.(source.title)}
        title="View document record"
        className="w-full px-3 pt-2.5 pb-2 text-left hover:bg-white/5 transition-colors cursor-pointer"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-[12px] font-medium text-white">
            {source.title.replace(/_/g, " ")}
          </span>
          <TrustBadge trust={source.trust} />
        </div>

        {metaParts.length > 0 && (
          <div className="mt-1 truncate text-[10.5px] text-[#71717a]">
            {metaParts.join(" · ")}
          </div>
        )}
      </button>

      {source.relevance_score !== undefined && (
        <div className="space-y-1 px-3 pb-2">
          <ScoreMeter relevance={source.relevance_score} />
          <div className="flex items-center justify-between gap-2 font-mono text-[10px] text-[#71717a]">
            <span className="truncate">{scoreParts.join(" · ")}</span>
            <span className="shrink-0 text-[#a1a1aa]">
              match {formatScore(source.relevance_score)}
            </span>
          </div>
        </div>
      )}

      <div className="px-3 pb-2.5 text-[11.5px] leading-relaxed text-[#a1a1aa]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h4 className="mt-1 mb-0.5 text-[12px] font-semibold text-white">
                {children}
              </h4>
            ),
            h2: ({ children }) => (
              <h5 className="mt-1 mb-0.5 text-[11.5px] font-semibold text-white">
                {children}
              </h5>
            ),
            h3: ({ children }) => (
              <h6 className="mt-0.5 mb-0.5 text-[11px] font-medium text-[#e4e4e7]">
                {children}
              </h6>
            ),
            p: ({ children }) => (
              <div className="mb-1 leading-relaxed text-[#a1a1aa] last:mb-0">
                {children}
              </div>
            ),
            strong: ({ children }) => (
              <strong className="font-medium text-white">{children}</strong>
            ),
            ul: ({ children }) => (
              <ul className="my-1 list-disc space-y-0.5 pl-4 text-[11px]">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="my-1 list-decimal space-y-0.5 pl-4 text-[11px]">
                {children}
              </ol>
            ),
            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
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
          {cleanWikilinks(source.snippet.replace(/!\[.*?\]\(.*?\)/g, ""))}
        </ReactMarkdown>
      </div>
    </div>
  );
}
