"use client";

import { useState } from "react";
import Link from "next/link";
import { MessageSquare, Plus, Search, Trash2, X } from "lucide-react";
import type { SessionSummary } from "@/types/hermes";

interface ChatSidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string;
  isOpen: boolean;
  onClose: () => void;
  onDeleteSession: (sessionId: string) => void;
}

const DAY_MS = 86400000;

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function groupLabel(isoDateString?: string | null): string {
  if (!isoDateString) return "Older";

  const updated = new Date(isoDateString);
  if (Number.isNaN(updated.getTime())) return "Older";

  const daysApart = Math.round(
    (startOfDay(new Date()) - startOfDay(updated)) / DAY_MS
  );

  if (daysApart <= 0) return "Today";
  if (daysApart === 1) return "Yesterday";
  if (daysApart < 7) return "Previous 7 days";
  if (daysApart < 30) return "Previous 30 days";
  return "Older";
}

const GROUP_ORDER = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Previous 30 days",
  "Older",
];

function formatRelativeTime(isoDateString?: string | null): string {
  if (!isoDateString) return "";

  const date = new Date(isoDateString);
  if (Number.isNaN(date.getTime())) return "";

  const diffMins = Math.floor((Date.now() - date.getTime()) / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function SessionRow({
  session,
  isActive,
  onClose,
  onDeleteSession,
}: {
  session: SessionSummary;
  isActive: boolean;
  onClose: () => void;
  onDeleteSession: (sessionId: string) => void;
}) {
  return (
    <div
      className={`group flex items-center gap-2 pr-2 rounded-lg text-xs transition-colors ${
        isActive
          ? "bg-white/10 text-white font-medium"
          : "text-[#a1a1aa] hover:bg-white/5 hover:text-[#ededed]"
      }`}
    >
      <Link
        href={`/chat/${encodeURIComponent(session.id)}`}
        onClick={onClose}
        className="flex items-center gap-2 min-w-0 flex-1 pl-2.5 py-2 cursor-pointer"
      >
        <MessageSquare className="w-3.5 h-3.5 shrink-0 text-[#71717a]" />
        <span className="truncate">{session.title}</span>
      </Link>

      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-[10px] text-[#71717a] group-hover:hidden group-focus-within:hidden">
          {session.turn_count > 0
            ? `${session.turn_count} turn${session.turn_count === 1 ? "" : "s"}`
            : formatRelativeTime(session.updated_at)}
        </span>
        <button
          type="button"
          aria-label={`Delete chat: ${session.title}`}
          onClick={() => onDeleteSession(session.id)}
          className="hidden group-hover:flex group-focus-within:flex items-center justify-center p-1 rounded hover:bg-red-500/20 text-[#71717a] hover:text-red-400 transition-colors"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  isOpen,
  onClose,
  onDeleteSession,
}: ChatSidebarProps) {
  const [filterText, setFilterText] = useState("");

  if (!isOpen) return null;

  const normalizedFilter = filterText.trim().toLowerCase();
  const matchingSessions = normalizedFilter
    ? sessions.filter((session) =>
        session.title.toLowerCase().includes(normalizedFilter)
      )
    : sessions;

  const grouped = new Map<string, SessionSummary[]>();
  for (const session of matchingSessions) {
    const label = groupLabel(session.updated_at);
    const bucket = grouped.get(label);
    if (bucket) bucket.push(session);
    else grouped.set(label, [session]);
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-30 sm:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <aside className="fixed sm:static inset-y-0 left-0 z-40 w-64 sm:w-60 shrink-0 flex flex-col bg-[#111114] border-r border-white/5 select-none">
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

        {sessions.length > 0 && (
          <div className="px-3 pt-3">
            <div className="flex items-center gap-2 rounded-md border border-white/5 bg-white/5 px-2 py-1.5 focus-within:border-white/20 transition-colors">
              <Search className="h-3 w-3 shrink-0 text-[#71717a]" />
              <input
                value={filterText}
                onChange={(event) => setFilterText(event.target.value)}
                placeholder="Search chats"
                aria-label="Search chats"
                className="w-full bg-transparent text-[11.5px] text-[#ededed] placeholder-[#71717a] outline-none"
              />
              {filterText && (
                <button
                  type="button"
                  onClick={() => setFilterText("")}
                  aria-label="Clear chat search"
                  className="shrink-0 text-[#71717a] hover:text-white transition-colors cursor-pointer"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto scrollbar-thin px-2 py-3 space-y-3">
          {sessions.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-[#71717a]">
              No previous chats yet.
            </div>
          ) : matchingSessions.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-[#71717a]">
              No chats match &quot;{filterText.trim()}&quot;.
            </div>
          ) : (
            GROUP_ORDER.filter((label) => grouped.has(label)).map((label) => (
              <div key={label} className="space-y-1">
                <div className="px-2 pb-0.5 text-[10.5px] font-medium uppercase tracking-wider text-[#71717a]">
                  {label}
                </div>
                {grouped.get(label)?.map((session) => (
                  <SessionRow
                    key={session.id}
                    session={session}
                    isActive={session.id === activeSessionId}
                    onClose={onClose}
                    onDeleteSession={onDeleteSession}
                  />
                ))}
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  );
}
