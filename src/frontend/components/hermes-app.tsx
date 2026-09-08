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
  isAbortError,
} from "@/lib/api";
import { ChatPanel } from "@/components/chat-panel";
import { ChatSidebar } from "@/components/chat-sidebar";
import { DocumentModal } from "@/components/document-modal";
import { ImageLightbox } from "@/components/image-lightbox";
import type { ChatTurn, SessionSummary } from "@/types/hermes";

interface HermesAppProps {
  initialSessionId?: string;
}

interface PendingDeletion {
  session: SessionSummary;
  wasActive: boolean;
  timer: ReturnType<typeof setTimeout>;
}

function generateSessionId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `session_${Date.now()}`;
}

function sortSessionsByUpdatedAt(sessions: SessionSummary[]): SessionSummary[] {
  return [...sessions].sort((a, b) => {
    const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0;
    const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0;
    return bTime - aTime;
  });
}

function DeleteSessionDialog({
  session,
  onCancel,
  onConfirm,
}: {
  session: SessionSummary | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!session) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onCancel}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-session-title"
        className="relative z-10 w-full max-w-sm rounded-xl border border-white/10 bg-[#18181b] p-5 shadow-2xl"
      >
        <div className="space-y-2">
          <h2 id="delete-session-title" className="text-sm font-medium text-white">
            Delete this chat?
          </h2>
          <p className="text-xs leading-relaxed text-[#a1a1aa]">
            This will remove &quot;{session.title}&quot; from your chat history.
          </p>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-[#d4d4d8] hover:bg-white/10 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md border border-red-500/30 bg-red-500/15 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-500/25 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

export function HermesApp({ initialSessionId }: HermesAppProps) {
  const router = useRouter();

  const [sessionId] = useState<string>(
    () => initialSessionId || generateSessionId()
  );
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedImagePath, setSelectedImagePath] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<SessionSummary | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<PendingDeletion | null>(null);

  const hasRedirected = useRef(false);
  const pendingDeletionId = useRef<string | null>(null);
  const activeStreamController = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      activeStreamController.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!initialSessionId && !hasRedirected.current) {
      hasRedirected.current = true;
      router.replace(`/chat/${sessionId}`);
    }
  }, [initialSessionId, sessionId, router]);

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
    setSessions(
      pendingDeletionId.current
        ? list.filter((session) => session.id !== pendingDeletionId.current)
        : list
    );
  };

  useEffect(() => {
    let cancelled = false;
    fetchSessions().then((list) => {
      if (!cancelled) {
        setSessions(list);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (question: string) => {
    if (isThinking) return;

    activeStreamController.current?.abort();
    const controller = new AbortController();
    activeStreamController.current = controller;

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
      }, sessionId, controller.signal);
    } catch (error) {
      if (isAbortError(error)) {
        setTurns((prev) => {
          if (prev.length === 0) return prev;
          const next = [...prev];
          const lastIndex = next.length - 1;
          const currentTurn = next[lastIndex];
          const previousResponse = currentTurn.response;
          const stoppedAnswer = previousResponse?.answer
            ? `${previousResponse.answer}\n\n_Response stopped._`
            : "Response stopped.";

          next[lastIndex] = {
            ...currentTurn,
            isStreaming: false,
            statusMessage: undefined,
            response: {
              answer: stoppedAnswer,
              reasoning_steps: previousResponse?.reasoning_steps || [],
              sources: previousResponse?.sources || [],
              contradictions: previousResponse?.contradictions || [],
              referenced_figures: previousResponse?.referenced_figures || [],
              citations: previousResponse?.citations || [],
            },
          };
          return next;
        });
        return;
      }

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
      if (activeStreamController.current === controller) {
        activeStreamController.current = null;
      }
      setIsThinking(false);
      refreshSessions();
    }
  };

  const handleStopResponse = () => {
    activeStreamController.current?.abort();
  };

  const handleReset = () => {
    router.push("/chat");
  };

  const handleDeleteSession = (targetSessionId: string) => {
    const target = sessions.find((session) => session.id === targetSessionId);
    if (target) {
      setDeleteCandidate(target);
    }
  };

  const confirmDeleteSession = () => {
    if (!deleteCandidate) return;

    const target = deleteCandidate;
    const wasActive = sessionId === target.id;

    setDeleteCandidate(null);
    setSessions((prev) => prev.filter((s) => s.id !== target.id));

    if (wasActive) {
      router.push("/chat");
    }

    if (pendingDeletion) {
      clearTimeout(pendingDeletion.timer);
      void deleteSession(pendingDeletion.session.id);
    }

    pendingDeletionId.current = target.id;

    const timer = setTimeout(() => {
      void deleteSession(target.id).then(() => {
        setPendingDeletion((current) =>
          current?.session.id === target.id ? null : current
        );
        if (pendingDeletionId.current === target.id) {
          pendingDeletionId.current = null;
        }
      });
    }, 5000);

    setPendingDeletion({ session: target, wasActive, timer });
  };

  const undoDeleteSession = () => {
    if (!pendingDeletion) return;

    clearTimeout(pendingDeletion.timer);
    pendingDeletionId.current = null;
    setSessions((prev) => {
      if (prev.some((session) => session.id === pendingDeletion.session.id)) {
        return prev;
      }
      return sortSessionsByUpdatedAt([pendingDeletion.session, ...prev]);
    });

    if (pendingDeletion.wasActive) {
      router.push(`/chat/${encodeURIComponent(pendingDeletion.session.id)}`);
    }

    setPendingDeletion(null);
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
          onDeleteSession={handleDeleteSession}
        />
        <main className="flex-1 min-h-0 flex flex-col relative overflow-hidden">
          <ChatPanel
            turns={turns}
            onSubmit={handleSubmit}
            onStop={handleStopResponse}
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

      <DeleteSessionDialog
        session={deleteCandidate}
        onCancel={() => setDeleteCandidate(null)}
        onConfirm={confirmDeleteSession}
      />

      {pendingDeletion && (
        <div className="fixed bottom-4 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#18181b] px-4 py-3 text-xs text-[#d4d4d8] shadow-2xl sm:left-auto sm:right-4 sm:translate-x-0">
          <span className="min-w-0 truncate">
            Deleted &quot;{pendingDeletion.session.title}&quot;
          </span>
          <button
            type="button"
            onClick={undoDeleteSession}
            className="shrink-0 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 font-medium text-white hover:bg-white/10 transition-colors"
          >
            Undo
          </button>
        </div>
      )}
    </div>
  );
}
