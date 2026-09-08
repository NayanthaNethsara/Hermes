"use client";

import React from "react";
import { BorderBeam } from "@/components/ui/border-beam";
import { AtSign, ChevronDown, ArrowUp } from "lucide-react";

const CHIP: React.CSSProperties = {
  borderRadius: 36,
  background: "rgba(255,255,255,0.04)",
  boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.02), inset 0 1px 0 0 rgba(255,255,255,0.04)",
};

function ChatInput() {
  return (
    <div
      style={{
        width: 348,
        maxWidth: "100%",
        borderRadius: 20,
        background: "#1d1d1d",
        boxShadow: "inset 0 0 0 1px rgba(44,47,54,0.52), inset 0 0 50px 0 rgba(255,255,255,0.02)",
        overflow: "hidden",
        position: "relative",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <div style={{ padding: "7px 7px 8px", display: "flex", flexDirection: "column", height: 122 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            width: "fit-content",
            height: 24,
            padding: "0 4px",
            marginLeft: 1,
            ...CHIP,
          }}
        >
          <AtSign size={16} className="text-[#808388]" />
        </div>
        <div style={{ fontSize: 13, lineHeight: "16px", color: "#4e4e4e", padding: "16px 4px 0" }}>Build anything...</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: "auto" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 4, height: 24, padding: "0 6px 0 8px", fontSize: 12, lineHeight: "14px", color: "#caccd2", marginLeft: 1, ...CHIP }}>
            Agent
            <ChevronDown size={14} className="text-[#8B9099] opacity-60" />
          </div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 4, height: 24, padding: "0 6px 0 8px", fontSize: 12, lineHeight: "14px", color: "#caccd2", ...CHIP }}>
            Auto
            <ChevronDown size={14} className="text-[#8B9099] opacity-60" />
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 28, height: 28, marginLeft: "auto", padding: "0 8px", ...CHIP }}>
            <ArrowUp size={16} className="text-[#8B8B8B]" />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Default() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 600,
        maxWidth: "100%",
        minHeight: 360,
        margin: "0 auto",
        background: "#0d0d0f",
        borderRadius: 24,
      }}
    >
      <BorderBeam size="md" colorVariant="colorful">
        <ChatInput />
      </BorderBeam>
    </div>
  );
}
