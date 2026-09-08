"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PanelLeft } from "lucide-react";
import {
  askHermesStream,
  deleteSession,
  fetchSessionDetails,
  fetchSessions,
  HermesApiError,
} from "@/lib/api";
import { ChatPanel } from "@/components/chat-panel";
import { ChatSidebar } from "@/components/chat-sidebar";
import { DocumentModal } from "@/components/document-modal";
import { ImageLightbox } from "@/components/image-lightbox";
import type { ChatTurn, SessionSummary } from "@/types/hermes";

interface HermesAppProps {
  initialSessionId?: string;
}

function generateSessionId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `session_${Date.now()}`;
}

export function HermesApp({ initialSessionId }: HermesAppProps) {
  const router = useRouter();

  const [sessionId, setSessionId] = useState<string>(
    () => initialSessionId || generateSessionId()
  );
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedImagePath, setSelectedImagePath] = useState<string | null>(null);

  const hasRedirected = useRef(false);

  useEffect(() => {
    if (!initialSessionId && !hasRedirected.current) {
      hasRedirected.current = true;
      router.replace(`/chat/${sessionId}`);
    }
  }, [initialSessionId, sessionId, router]);

  useEffect(() => {
    if (initialSessionId && initialSessionId !== sessionId) {
      setSessionId(initialSessionId);
    }
  }, [initialSessionId]);

  useEffect(() => {
    if (!initialSessionId) return;

    let cancelled = false;

    (async () => {
      setIsThinking(true);
      const details = await fetchSessionDetails(initialSessionId);
      if (cancelled) return;

      if (details && details.turns && details.turns.length > 0) {
        const loadedTurns: ChatTurn[] = details.turns.map((t) => ({
          question: t.question,
          response: t.response,
          isStreaming: false,
        }));
        setTurns(loadedTurns);
      } else {
        setTurns([]);
      }
      setIsThinking(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [initialSessionId]);

  const refreshSessions = async () => {
    const list = await fetchSessions();
    setSessions(list);
  };

  useEffect(() => {
    refreshSessions();
  }, []);

  const handleSubmit = async (question: string) => {
    const initialStatus = "Searching archive with hybrid vector search...";

    setTurns((prev) => [
      ...prev,
      {
        question,
        response: null,
        statusMessage: initialStatus,
        isStreaming: true,
      },
    ]);
    setIsThinking(true);

    try {
      await askHermesStream(
        question,
        {
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
      }, sessionId);
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
      refreshSessions();
    }
  };

  const handleReset = () => {
    router.push("/chat");
  };

  const handleSelectSession = (targetSessionId: string) => {
    if (targetSessionId === sessionId) return;
    router.push(`/chat/${targetSessionId}`);
  };

  const handleDeleteSession = async (targetSessionId: string) => {
    await deleteSession(targetSessionId);
    setSessions((prev) => prev.filter((s) => s.id !== targetSessionId));
    if (sessionId === targetSessionId) {
      router.push("/chat");
    }
  };

  return (
    <div className="flex h-screen w-screen flex-col bg-[#0d0d0f] text-[#ededed] overflow-hidden">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-white/5 px-4 sm:px-6 bg-[#0d0d0f]/80 backdrop-blur-xs z-10">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setIsSidebarOpen((prev) => !prev)}
            aria-label="Toggle chat history"
            className={`p-1.5 rounded-md transition-colors cursor-pointer ${
              isSidebarOpen
                ? "text-white bg-white/10"
                : "text-[#8e8e93] hover:text-white hover:bg-white/5"
            }`}
          >
            <PanelLeft className="w-4 h-4" />
          </button>
          <div className="flex items-baseline gap-2">
            <span className="text-[13.5px] font-medium tracking-tight text-white">
              Hermes
            </span>
            <span className="text-[11px] text-[#71717a] font-normal">
              by TheKade
            </span>
          </div>
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

      <div className="flex-1 min-h-0 flex relative overflow-hidden">
        <ChatSidebar
          sessions={sessions}
          activeSessionId={sessionId}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          onSelectSession={handleSelectSession}
          onNewChat={handleReset}
          onDeleteSession={handleDeleteSession}
        />
        <main className="flex-1 min-h-0 flex flex-col relative overflow-hidden">
          <ChatPanel
            turns={turns}
            onSubmit={handleSubmit}
            disabled={isThinking}
            onSelectDocument={(docId) => setSelectedDocId(docId)}
            onSelectImage={(img) => setSelectedImagePath(img)}
          />
        </main>
      </div>

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
