import type { ReasoningStep } from "@/constants/mock/mockResponses";
import { CompassIcon } from "@/components/icons";

export function ReasoningTracePanel({
  steps,
}: {
  steps: ReasoningStep[] | null;
}) {
  return (
    <aside className="card-elevated flex h-full w-80 shrink-0 flex-col overflow-hidden rounded-xl">
      <div className="border-border flex items-center gap-2 border-b px-5 py-4">
        <CompassIcon className="text-primary h-4.5 w-4.5" />
        <h2 className="font-serif text-[15px] font-semibold tracking-tight">
          Reasoning Trace
        </h2>
      </div>
      <div className="scrollbar-thin flex-1 overflow-y-auto p-4">
        {!steps || steps.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-3 py-12 text-center">
            <span className="border-border bg-muted text-muted-foreground/70 flex h-11 w-11 items-center justify-center rounded-full border">
              <CompassIcon className="h-5 w-5" />
            </span>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Reasoning steps will appear here once you ask a question.
            </p>
          </div>
        ) : (
          <ol>
            {steps.map((step, i) => (
              <li key={step.step} className="relative flex gap-3.5 pb-7 last:pb-0">
                {i !== steps.length - 1 && (
                  <span className="bg-border absolute top-8 bottom-0 left-3.75 w-px" />
                )}
                <span className="border-primary/40 bg-primary text-primary-foreground ring-background relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ring-4">
                  {step.step}
                </span>
                <div className="pt-1 pb-1">
                  <p className="text-[13.5px] leading-snug font-medium">
                    {step.action}
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                    {step.found}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
