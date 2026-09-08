import type { TrustTier } from "@/types/archivist";

const TRUST_STYLES: Record<TrustTier, string> = {
  high: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  medium: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  "medium-low": "text-orange-400 bg-orange-500/10 border-orange-500/20",
  low: "text-red-400 bg-red-500/10 border-red-500/20",
};

export function TrustBadge({ trust }: { trust: TrustTier }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono capitalize border ${TRUST_STYLES[trust]}`}
    >
      {trust}
    </span>
  );
}
