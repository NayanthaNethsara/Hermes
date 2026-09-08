"use client";

import { useState } from "react";
import { askHermes, HermesApiError } from "@/lib/api";
import { ChatPanel } from "@/components/chat-panel";
import { DocumentModal } from "@/components/document-modal";
import { ImageLightbox } from "@/components/image-lightbox";
import type { ChatTurn } from "@/types/hermes";

export function HermesApp() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedImagePath, setSelectedImagePath] = useState<string | null>(null);

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
      const response = await askHermes(question);
      setLastResponse(response);
    } catch (error) {
      const message =
        error instanceof HermesApiError
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

  const handleReset = () => {
    setTurns([]);
  };

  return (
    <div className="flex h-screen w-screen flex-col bg-[#0d0d0f] text-[#ededed] overflow-hidden">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/5 px-4 sm:px-6 bg-[#0d0d0f]/80 backdrop-blur-xs z-10">
        <div className="flex items-baseline gap-2">
          <span className="text-[13.5px] font-medium tracking-tight text-white">
            Hermes
          </span>
          <span className="text-[11px] text-[#71717a] font-normal">
            by TheKade
          </span>
        </div>

        {turns.length > 0 && (
          <button
            type="button"
            onClick={handleReset}
            className="text-xs text-[#8e8e93] hover:text-white transition-colors cursor-pointer"
          >
            New chat
          </button>
        )}
      </header>

      <main className="flex-1 min-h-0 flex flex-col relative overflow-hidden">
        <ChatPanel
          turns={turns}
          onSubmit={handleSubmit}
          disabled={isThinking}
          onSelectDocument={(docId) => setSelectedDocId(docId)}
          onSelectImage={(img) => setSelectedImagePath(img)}
        />
      </main>

      <DocumentModal
        docId={selectedDocId}
        onClose={() => setSelectedDocId(null)}
        onSelectImage={(img) => setSelectedImagePath(img)}
      />

      <ImageLightbox
        imagePath={selectedImagePath}
        onClose={() => setSelectedImagePath(null)}
      />
    </div>
  );
}
