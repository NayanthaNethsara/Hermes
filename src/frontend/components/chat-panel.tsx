"use client";

import { useEffect, useRef, useState } from "react";
import type { ArchivistResponse } from "@/constants/mock/mockResponses";
import { AnswerCard } from "@/components/answer-card";
import { ChatIcon, SearchIcon, SendIcon } from "@/components/icons";

const QUICK_ACTIONS = [
  "Trace a chain of events",
  "Check for conflicting sources",
  "Search the archive",
];

export interface ChatTurn {
  question: string;
  response: ArchivistResponse | null;
}

export function ChatPanel({
  turns,
  onSubmit,
  disabled,
}: {
  turns: ChatTurn[];
  onSubmit: (text: string) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
  };

  return (
    <section className="card-elevated flex h-full min-w-0 flex-1 flex-col overflow-hidden rounded-xl">
      <div className="border-border flex items-center gap-2 border-b px-5 py-4">
        <ChatIcon className="text-primary h-4.5 w-4.5" />
        <h2 className="font-serif text-[15px] font-semibold tracking-tight">Chat</h2>
      </div>

      <div ref={scrollRef} className="scrollbar-thin flex-1 overflow-y-auto px-5 py-5">
        {turns.length === 0 ? (
          <div className="mx-auto flex h-full max-w-lg flex-col justify-center gap-6">
            <div>
              <h1 className="font-serif text-[28px] leading-tight font-semibold tracking-tight text-balance">
                Let&apos;s search the archive&hellip;
              </h1>
              <p className="text-muted-foreground mt-3 text-[14.5px] leading-relaxed">
                This is your space to ask questions about the Ashen Era
                Archive and see how the answer was found — which sources were
                used, how trustworthy they are, and where they disagree.
              </p>
            </div>
            <div className="flex flex-wrap gap-2.5">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action}
                  type="button"
                  onClick={() => submit(action)}
                  className="border-border bg-background hover:border-primary/40 hover:bg-primary/10 group inline-flex items-center gap-2 rounded-full border px-4 py-2 text-[13.5px] font-medium transition-colors"
                >
                  <SearchIcon className="text-muted-foreground group-hover:text-primary h-3.5 w-3.5 transition-colors" />
                  {action}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {turns.map((turn, i) => (
              <AnswerCard key={i} question={turn.question} response={turn.response} />
            ))}
          </div>
        )}
      </div>

      <div className="border-border shrink-0 border-t p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(value);
          }}
          className="flex items-end gap-2.5"
        >
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(value);
              }
            }}
            placeholder="Ask a question about the archive..."
            rows={1}
            disabled={disabled}
            className="border-border bg-background focus:border-primary focus:ring-primary/30 max-h-32 min-h-11 flex-1 resize-none rounded-lg border px-3.5 py-2.5 text-[14px] outline-none transition-colors focus:ring-2 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={disabled || !value.trim()}
            aria-label="Ask"
            className="bg-primary text-primary-foreground flex h-11 w-11 shrink-0 items-center justify-center rounded-lg shadow-sm transition-all hover:brightness-110 active:scale-95 disabled:pointer-events-none disabled:opacity-40"
          >
            <SendIcon className="h-4.5 w-4.5" />
          </button>
        </form>
        <p className="text-muted-foreground/70 mt-2.5 text-center font-serif text-[12px] italic">
          The Archivist can be inaccurate; check the sources shown.
        </p>
      </div>
    </section>
  );
}
