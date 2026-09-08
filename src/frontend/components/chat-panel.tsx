"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatTurn } from "@/types/hermes";
import { AnswerCard } from "@/components/answer-card";
import { ChatInputBar } from "@/components/chat-input-bar";

import { SUGGESTED_QUERIES } from "@/lib/constants";

export function ChatPanel({
  turns,
  onSubmit,
  disabled,
  onSelectDocument,
  onSelectImage,
}: {
  turns: ChatTurn[];
  onSubmit: (text: string) => void;
  disabled?: boolean;
  onSelectDocument?: (docId: string) => void;
  onSelectImage?: (imagePath: string) => void;
}) {
  const [inputValue, setInputValue] = useState("");
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const handleSubmit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setInputValue("");
  };

  return (
    <div className="flex h-full w-full flex-col overflow-hidden relative">
      {turns.length === 0 ? (
        <div className="flex-1 overflow-y-auto scrollbar-thin flex flex-col items-center justify-center px-4 py-12 max-w-2xl mx-auto w-full">
          <div className="text-center mb-8 space-y-1">
            <h1 className="text-2xl font-medium tracking-tight text-white">
              Hermes
            </h1>
            <p className="text-[#8e8e93] text-sm">
              Historical archive intelligence by TheKade.
            </p>
          </div>

          <div className="w-full mb-6">
            <ChatInputBar
              value={inputValue}
              onChange={setInputValue}
              onSubmit={handleSubmit}
              disabled={disabled}
            />
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2 max-w-xl">
            {SUGGESTED_QUERIES.map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => handleSubmit(item.query)}
                disabled={disabled}
                className={`h-7 px-3 rounded-full bg-white/5 text-xs transition-colors border border-white/5 ${
                  disabled
                    ? "opacity-40 cursor-not-allowed text-[#71717a]"
                    : "hover:bg-white/10 text-[#a1a1aa] hover:text-white cursor-pointer"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 flex flex-col">
          <div className="w-full max-w-2xl mx-auto space-y-8 flex-1">
            {turns.map((turn, i) => (
              <AnswerCard
                key={i}
                question={turn.question}
                response={turn.response}
                statusMessage={turn.statusMessage}
                isStreaming={turn.isStreaming}
                onSelectDocument={onSelectDocument}
                onSelectImage={onSelectImage}
              />
            ))}
            <div ref={scrollEndRef} />
          </div>

          <div className="sticky bottom-0 pt-3 pb-4 bg-gradient-to-t from-[#0d0d0f] via-[#0d0d0f]/90 to-transparent backdrop-blur-xs mt-4">
            <ChatInputBar
              value={inputValue}
              onChange={setInputValue}
              onSubmit={handleSubmit}
              disabled={disabled}
            />
          </div>
        </div>
      )}
    </div>
  );
}
