"use client";

import { useState } from "react";
import { askHermesStream, HermesApiError } from "@/lib/api";
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
    setTurns((prev) => [
      ...prev,
      {
        question,
        response: null,
        statusMessage: "Searching archive with hybrid vector search...",
        isStreaming: true,
      },
    ]);
    setIsThinking(true);

    try {
      await askHermesStream(question, {
        onStatus: (status) => {
          setTurns((prev) => {
            if (prev.length === 0) return prev;
            const next = [...prev];
            const lastIndex = next.length - 1;
            next[lastIndex] = {
              ...next[lastIndex],
              statusMessage: status.message,
            };
            return next;
          });
        },
        onMetadata: (metadata) => {
          setTurns((prev) => {
            if (prev.length === 0) return prev;
            const next = [...prev];
            const lastIndex = next.length - 1;
            const currentTurn = next[lastIndex];
            next[lastIndex] = {
              ...currentTurn,
              response: {
                answer: currentTurn.response?.answer || "",
                sources: metadata.sources,
                referenced_figures: metadata.referenced_figures,
                citations: metadata.citations,
                reasoning_steps: metadata.reasoning_steps,
                contradictions: [],
              },
            };
            return next;
          });
        },
        onToken: (delta) => {
          setTurns((prev) => {
            if (prev.length === 0) return prev;
            const next = [...prev];
            const lastIndex = next.length - 1;
            const currentTurn = next[lastIndex];
            const prevResponse = currentTurn.response;
            next[lastIndex] = {
              ...currentTurn,
              statusMessage: undefined,
              response: {
                answer: (prevResponse?.answer || "") + delta,
                sources: prevResponse?.sources || [],
                referenced_figures: prevResponse?.referenced_figures || [],
                citations: prevResponse?.citations || [],
                reasoning_steps: prevResponse?.reasoning_steps || [],
                contradictions: prevResponse?.contradictions || [],
              },
            };
            return next;
          });
        },
        onDone: (payload) => {
          setTurns((prev) => {
            if (prev.length === 0) return prev;
            const next = [...prev];
            const lastIndex = next.length - 1;
            const currentTurn = next[lastIndex];
            next[lastIndex] = {
              ...currentTurn,
              isStreaming: false,
              statusMessage: undefined,
              response: {
                answer: payload.answer || currentTurn.response?.answer || "",
                sources: payload.sources || currentTurn.response?.sources || [],
                referenced_figures: payload.referenced_figures || currentTurn.response?.referenced_figures || [],
                citations: payload.citations || currentTurn.response?.citations || [],
                reasoning_steps: payload.reasoning_steps || currentTurn.response?.reasoning_steps || [],
                contradictions: payload.contradictions || [],
              },
            };
            return next;
          });
        },
      });
    } catch (error) {
      const message =
        error instanceof HermesApiError
          ? error.message
          : "Sorry, something went wrong answering that question.";
      setTurns((prev) => {
        if (prev.length === 0) return prev;
        const next = [...prev];
        const lastIndex = next.length - 1;
        next[lastIndex] = {
          ...next[lastIndex],
          isStreaming: false,
          statusMessage: undefined,
          response: {
            answer: message,
            reasoning_steps: [],
            sources: [],
            contradictions: [],
          },
        };
        return next;
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
