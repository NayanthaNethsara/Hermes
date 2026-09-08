"use client";

import React, { useRef, useEffect } from "react";
import { BorderBeam } from "@/components/ui/border-beam";
import { ArrowUp, ChevronDown } from "lucide-react";

interface ChatInputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

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
      <BorderBeam size="md" colorVariant="mono" active={disabled || value.length > 0}>
        <form
          onSubmit={handleFormSubmit}
          className="w-full rounded-2xl bg-[#161618] border border-white/10 p-3 shadow-xl flex flex-col justify-between focus-within:border-white/20 transition-colors"
        >
          <div className="w-full px-1">
            <textarea
              ref={textareaRef}
              rows={1}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={disabled}
              placeholder={placeholder}
              className="w-full resize-none bg-transparent text-[14.5px] leading-relaxed text-[#ededed] placeholder-[#636366] outline-none min-h-[44px] max-h-[160px] py-1 font-sans disabled:opacity-50"
            />
          </div>

          <div className="flex items-center justify-between gap-2 pt-2 px-1 border-t border-white/5 mt-2">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full bg-white/5 text-[11.5px] text-[#a1a1aa] font-medium hover:bg-white/10 transition-colors cursor-default">
                Agent
                <ChevronDown size={12} className="opacity-60" />
              </span>
              <span className="inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full bg-white/5 text-[11.5px] text-[#a1a1aa] font-medium hover:bg-white/10 transition-colors cursor-default">
                Auto
                <ChevronDown size={12} className="opacity-60" />
              </span>
            </div>

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
          </div>
        </form>
      </BorderBeam>
    </div>
  );
}
