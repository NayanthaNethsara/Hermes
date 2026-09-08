"use client";

import React, { useRef, useEffect } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import type { ChatInputBarProps } from "@/types/hermes";

export function ChatInputBar({
  value,
  onChange,
  onSubmit,
  disabled = false,
  placeholder = "Ask Hermes anything about the archive...",
  className = "",
}: ChatInputBarProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) {
        onSubmit(value);
      }
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim() && !disabled) {
      onSubmit(value);
    }
  };

  const canSubmit = value.trim().length > 0 && !disabled;

  return (
    <div className={`w-full max-w-2xl mx-auto ${className}`}>
      <form
        onSubmit={handleFormSubmit}
        className={`w-full rounded-2xl p-3 shadow-xl flex flex-col justify-between transition-all duration-200 ${
          disabled
            ? "bg-[#141416]/90 border border-white/5 opacity-75 cursor-not-allowed"
            : "bg-[#161618] border border-white/10 focus-within:border-white/25"
        }`}
      >
        <div className="w-full px-1">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={disabled ? "Hermes is consulting the archive..." : placeholder}
            className={`w-full resize-none bg-transparent text-[14.5px] leading-relaxed text-[#ededed] placeholder-[#636366] outline-none min-h-[44px] max-h-[160px] py-1 font-sans ${
              disabled ? "cursor-not-allowed text-[#8e8e93]" : ""
            }`}
          />
        </div>

        <div className="flex items-center justify-end pt-2 px-1 border-t border-white/5 mt-2">
          {disabled ? (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 text-[#a1a1aa] text-[11px] font-mono cursor-not-allowed border border-white/5 select-none"
              title="Hermes is generating a response..."
            >
              <Loader2 size={12} className="animate-spin text-white/70" />
              <span>Thinking...</span>
            </div>
          ) : (
            <button
              type="submit"
              disabled={!canSubmit}
              aria-label="Send"
              className={`flex items-center justify-center h-7 w-7 rounded-full transition-colors ${
                canSubmit
                  ? "bg-white text-black hover:bg-white/90 active:scale-95 cursor-pointer"
                  : "bg-white/5 text-[#52525b] cursor-not-allowed"
              }`}
            >
              <ArrowUp size={14} strokeWidth={2.5} />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
