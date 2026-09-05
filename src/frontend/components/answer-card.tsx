import type { ArchivistResponse } from "@/types/archivist";
import { ContradictionBanner } from "@/components/contradiction-banner";

export function AnswerCard({
  question,
  response,
}: {
  question: string;
  response: ArchivistResponse | null;
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex justify-end">
        <p className="max-w-[80%] rounded-2xl rounded-br-md bg-stone-700 px-4 py-2.5 text-[14px] leading-relaxed font-medium text-stone-50 shadow-sm">
          {question}
        </p>
      </div>

      <div className="flex flex-col items-start">
        {!response ? (
          <div className="border-border bg-card flex max-w-[80%] items-center gap-1.5 rounded-2xl rounded-bl-md border px-4 py-3.5">
            <span className="bg-muted-foreground/50 h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
            <span className="bg-muted-foreground/50 h-1.5 w-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
            <span className="bg-muted-foreground/50 h-1.5 w-1.5 animate-bounce rounded-full" />
          </div>
        ) : (
          <div className="max-w-[80%]">
            <ContradictionBanner contradictions={response.contradictions} />
            <p className="border-border bg-card rounded-2xl rounded-bl-md border px-4 py-3 text-[14.5px] leading-relaxed whitespace-pre-wrap">
              {response.answer}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
