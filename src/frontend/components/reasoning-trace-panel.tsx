import type { ReasoningStep } from "@/types/archivist";
import { Workflow } from "lucide-react";

export function ReasoningTracePanel({
  steps,
}: {
  steps: ReasoningStep[] | null;
}) {
  return (
    <div className="w-full rounded-2xl border border-white/10 bg-[#1e1f20] overflow-hidden flex flex-col">
      <div className="flex items-center gap-2 border-b border-white/5 px-4 py-3 bg-[#18191a] text-white text-xs font-semibold uppercase tracking-wider">
        <Workflow size={14} className="text-[#7cacf8]" />
        <span>Agent Reasoning Trace</span>
      </div>

      <div className="p-3">
        {!steps || steps.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-[#9aa0a6]">
            <Workflow size={24} className="opacity-40" />
            <p className="text-xs">No active reasoning trace.</p>
          </div>
        ) : (
          <ol className="space-y-3">
            {steps.map((step) => (
              <li key={step.step} className="flex gap-2.5 text-xs">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#7cacf8]/15 text-[#7cacf8] font-mono font-medium text-[10.5px]">
                  {step.step}
                </span>
                <div className="space-y-0.5">
                  <p className="font-medium text-white text-[12px]">{step.action}</p>
                  <p className="text-[#9aa0a6] text-[11px] leading-relaxed">{step.found}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
