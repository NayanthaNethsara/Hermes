"use client";

import Link from "next/link";
import { MessageSquare, Plus, Trash2, X } from "lucide-react";
import type { SessionSummary } from "@/types/hermes";

interface ChatSidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string;
  isOpen: boolean;
  onClose: () => void;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => void;
}

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "";
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffSeconds < 60) return "Just now";
    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  isOpen,
  onClose,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}: ChatSidebarProps) {
  if (!isOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-30 sm:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <aside className="fixed sm:static inset-y-0 left-0 z-40 w-64 sm:w-60 shrink-0 flex flex-col bg-[#111114] border-r border-white/5 transition-all duration-200 select-none">
        <div className="flex h-12 items-center justify-between px-3 border-b border-white/5">
          <Link
            href="/chat"
            onClick={onClose}
            className="flex-1 flex items-center gap-2 h-8 px-2.5 rounded-md bg-white/5 hover:bg-white/10 text-xs text-white transition-colors cursor-pointer border border-white/5"
          >
            <Plus className="w-3.5 h-3.5 text-[#a1a1aa]" />
            <span>New Chat</span>
          </Link>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close sidebar"
            className="sm:hidden p-1.5 ml-1 text-[#8e8e93] hover:text-white rounded-md cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
          <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-[#71717a]">
            Past Investigations
          </div>

          {sessions.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-[#71717a]">
              No previous chats yet.
            </div>
          ) : (
            sessions.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <Link
                  key={session.id}
                  href={`/chat/${session.id}`}
                  onClick={onClose}
                  className={`group relative flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg text-xs cursor-pointer transition-colors ${
                    isActive
                      ? "bg-white/10 text-white font-medium"
                      : "text-[#a1a1aa] hover:bg-white/5 hover:text-[#ededed]"
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <MessageSquare className="w-3.5 h-3.5 shrink-0 text-[#71717a]" />
                    <span className="truncate">{session.title}</span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] text-[#71717a] group-hover:hidden">
                      {formatRelativeTime(session.updated_at)}
                    </span>
                    <button
                      type="button"
                      aria-label="Delete chat"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onDeleteSession(session.id);
                      }}
                      className="hidden group-hover:flex items-center justify-center p-1 rounded hover:bg-red-500/20 text-[#71717a] hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </Link>
              );
            })
          )}
        </div>
      </aside>
    </>
  );
}
