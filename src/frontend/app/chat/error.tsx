"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";

export default function ChatError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error("chat_render_error", error);
  }, [error]);

  return (
    <div className="flex h-full w-full items-center justify-center bg-background p-6">
      <div className="w-full max-w-md space-y-4 rounded-2xl border border-border bg-card p-6 text-center shadow-2xl">
        <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-border bg-muted text-destructive">
          <AlertTriangle size={18} />
        </span>

        <div className="space-y-1.5">
          <h1 className="text-[15px] font-medium text-foreground">
            This conversation could not be displayed
          </h1>
          <p className="text-xs leading-relaxed text-muted-foreground">
            The archive is still reachable. Retrying usually restores the view,
            and your chat history is unaffected.
          </p>
        </div>

        {error.message && (
          <p className="max-h-24 overflow-y-auto rounded-lg border border-border bg-background px-3 py-2 text-left font-mono text-[11px] leading-relaxed text-muted-foreground">
            {error.message}
            {error.digest && (
              <span className="mt-1 block text-[10px] opacity-70">
                digest: {error.digest}
              </span>
            )}
          </p>
        )}

        <div className="flex items-center justify-center gap-2 pt-1">
          <button
            type="button"
            onClick={retry}
            className="rounded-md border border-border bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:opacity-90 cursor-pointer"
          >
            Try again
          </button>
          <Link
            href="/chat"
            className="rounded-md border border-border bg-muted px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
          >
            Start a new chat
          </Link>
        </div>
      </div>
    </div>
  );
}
