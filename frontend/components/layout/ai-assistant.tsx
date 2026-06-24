"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, Sparkles, Wand2 } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ASSISTANT_CAPABILITIES, ASSISTANT_SUGGESTIONS } from "@/lib/mock";

interface Msg {
  role: "user" | "assistant";
  text: string;
}

export function AiAssistantFab({ onClick }: { onClick: () => void }) {
  return (
    <Button
      onClick={onClick}
      aria-label="Open AI assistant"
      className="fixed right-5 bottom-5 z-30 size-12 rounded-full shadow-card-lg lg:right-8 lg:bottom-8"
    >
      <Sparkles className="size-5" />
    </Button>
  );
}

export function AiAssistant({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const router = useRouter();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const send = (text: string) => {
    const q = text.trim();
    if (!q) return;
    setMessages((m) => [
      ...m,
      { role: "user", text: q },
      {
        role: "assistant",
        text: "I'm a preview of your AI recruiting copilot. Once connected, I'll search candidates, draft outreach, summarize resumes, and schedule interviews from here. Try a suggestion below to jump into a live workflow.",
      },
    ]);
    setInput("");
    setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <div className="flex items-center gap-2.5">
            <div className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-xl">
              <Wand2 className="size-5" />
            </div>
            <div>
              <SheetTitle className="flex items-center gap-2">
                AI Assistant
                <Badge variant="info" className="text-[10px]">
                  Preview
                </Badge>
              </SheetTitle>
              <SheetDescription>Your recruiting copilot</SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                {ASSISTANT_CAPABILITIES.map((c) => (
                  <div key={c.title} className="bg-muted/50 rounded-lg border p-3">
                    <p className="text-sm font-medium">{c.title}</p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {c.description}
                    </p>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="space-y-3">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex",
                    m.role === "user" ? "justify-end" : "justify-start",
                  )}
                >
                  <div
                    className={cn(
                      "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm",
                      m.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "bg-muted rounded-bl-sm",
                    )}
                  >
                    {m.text}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </div>

        <div className="space-y-3 border-t p-4">
          <div className="flex flex-wrap gap-1.5">
            {ASSISTANT_SUGGESTIONS.map((s) => (
              <button
                key={s.label}
                onClick={() => {
                  if (s.href) {
                    onOpenChange(false);
                    router.push(s.href);
                  } else {
                    send(s.prompt);
                  }
                }}
                className="bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground rounded-full border px-2.5 py-1 text-xs font-medium transition-colors"
              >
                {s.label}
              </button>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="border-input focus-within:ring-ring/40 flex items-center gap-2 rounded-xl border px-3 py-2 focus-within:ring-[3px]"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything about hiring…"
              className="placeholder:text-muted-foreground flex-1 bg-transparent text-sm outline-none"
            />
            <Button type="submit" size="icon-sm" disabled={!input.trim()}>
              <ArrowUp className="size-4" />
            </Button>
          </form>
        </div>
      </SheetContent>
    </Sheet>
  );
}
