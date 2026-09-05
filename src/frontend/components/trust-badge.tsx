import type { TrustTier } from "@/types/archivist";
import { Dot } from "@/components/icons";

const TRUST_STYLES: Record<TrustTier, string> = {
  high: "bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/25",
  medium: "bg-yellow-400/10 text-yellow-300 ring-1 ring-yellow-400/25",
  "medium-low": "bg-orange-400/10 text-orange-300 ring-1 ring-orange-400/25",
  low: "bg-red-400/10 text-red-300 ring-1 ring-red-400/25",
};

const DOT_STYLES: Record<TrustTier, string> = {
  high: "text-emerald-400",
  medium: "text-yellow-400",
  "medium-low": "text-orange-400",
  low: "text-red-400",
};

export function TrustBadge({ trust }: { trust: TrustTier }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium tracking-wide capitalize ${TRUST_STYLES[trust]}`}
    >
      <Dot className={`h-1.5 w-1.5 ${DOT_STYLES[trust]}`} />
      {trust}
    </span>
  );
}
