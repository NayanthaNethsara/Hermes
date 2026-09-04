"use client";

import { useState } from "react";
import { askArchivist, ArchivistApiError } from "@/lib/api";
import { ChatPanel, type ChatTurn } from "@/components/chat-panel";
import { SourcesPanel } from "@/components/sources-panel";
import { ReasoningTracePanel } from "@/components/reasoning-trace-panel";
import { FlameIcon } from "@/components/icons";

export function ArchivistApp() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isThinking, setIsThinking] = useState(false);

  const handleSubmit = async (question: string) => {
    setTurns((prev) => [...prev, { question, response: null }]);
    setIsThinking(true);

    const setLastResponse = (response: ChatTurn["response"]) => {
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = { question, response };
        return next;
      });
    };

    try {
      const response = await askArchivist(question);
      setLastResponse(response);
    } catch (error) {
      const message =
        error instanceof ArchivistApiError
          ? error.message
          : "Sorry, something went wrong answering that question.";
      setLastResponse({
        answer: message,
        reasoning_steps: [],
        sources: [],
        contradictions: [],
      });
    } finally {
      setIsThinking(false);
    }
  };

  const latestAnswered = [...turns].reverse().find((t) => t.response);
  const latestResponse = latestAnswered?.response ?? null;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <header className="border-border flex shrink-0 items-center gap-3 border-b px-6 py-4">
        <span className="border-border text-muted-foreground flex h-9 w-9 shrink-0 items-center justify-center rounded-full border">
          <FlameIcon className="h-4.5 w-4.5" />
        </span>
        <div>
          <h1 className="font-serif text-[19px] leading-none font-semibold tracking-tight">
            The Archivist
          </h1>
          <p className="text-muted-foreground mt-1 text-[12px] tracking-wide">
            Ashen Era Archive research assistant
          </p>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 gap-5 overflow-hidden p-5">
        <SourcesPanel sources={latestResponse?.sources ?? null} />
        <ChatPanel turns={turns} onSubmit={handleSubmit} disabled={isThinking} />
        <ReasoningTracePanel steps={latestResponse?.reasoning_steps ?? null} />
      </div>
    </div>
  );
}
