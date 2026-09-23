import { useEffect, useRef, useState } from "react";
import { Brain, MessageSquare, Plus, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { useChat } from "@/hooks/useChat";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { useTranslation } from "@/lib/i18n";
import type { ChatAction, ChatMessage } from "@/types/chat";

const ACTION_COLORS: Record<string, string> = {
  executed: "bg-success/15 text-success",
  failed: "bg-danger/15 text-danger",
  pending: "bg-warning/15 text-warning",
  simulated: "bg-info/15 text-info",
};

function ActionBadge({ action }: { action: ChatAction }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${ACTION_COLORS[action.status] ?? "bg-surface-2 text-text-muted"}`}>
      {action.type}
      {action.status === "executed" && " ✓"}
      {action.status === "failed" && " ✗"}
    </span>
  );
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Bouncing-dots "assistant is working" bubble — shown for the whole
 * backend turn, since responses aren't streamed. */
function ThinkingIndicator() {
  const { t } = useTranslation();
  return (
    <div className="flex justify-start chat-message-in">
      <div className="flex items-center gap-2 rounded-xl bg-surface-2 px-4 py-3">
        <span className="flex gap-1">
          <span className="chat-dot h-1.5 w-1.5 rounded-full bg-text-muted" />
          <span className="chat-dot chat-dot-2 h-1.5 w-1.5 rounded-full bg-text-muted" />
          <span className="chat-dot chat-dot-3 h-1.5 w-1.5 rounded-full bg-text-muted" />
        </span>
        <span className="text-xs text-text-muted">{t("chat.thinking")}</span>
      </div>
    </div>
  );
}

function MessageBubble({
  msg,
  showReasoning,
}: {
  msg: ChatMessage;
  showReasoning: boolean;
}) {
  const { t } = useTranslation();
  const isUser = msg.role === "user";
  return (
    <div className={`flex chat-message-in ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm ${
          isUser ? "bg-primary text-white" : "bg-surface-2 text-text-primary"
        }`}
      >
        {showReasoning && msg.reasoning && (
          <details className="mb-2 rounded-lg bg-surface-1/70 p-2 text-xs text-text-secondary">
            <summary className="flex cursor-pointer items-center gap-1 text-text-muted">
              <Brain size={12} />
              {t("chat.reasoning")}
            </summary>
            <p className="mt-1 whitespace-pre-wrap">{msg.reasoning}</p>
          </details>
        )}
        <p className="whitespace-pre-wrap">{msg.content}</p>
        {msg.actions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {msg.actions.map((a, i) => (
              <ActionBadge key={i} action={a} />
            ))}
          </div>
        )}
        <p className={`mt-1 text-xs ${isUser ? "text-white/60" : "text-text-muted"}`}>
          {formatTime(msg.created_at)}
        </p>
      </div>
    </div>
  );
}

export function ChatPage() {
  const { t } = useTranslation();
  const {
    sessions,
    messages,
    isLoadingSessions,
    isLoadingMessages,
    isSending,
    pendingMessage,
    error,
    activeSessionId,
    handleSend,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
  } = useChat();

  const [input, setInput] = useState("");
  const [showReasoning, setShowReasoning] = useLocalStorageState(
    "aurum:chat-show-reasoning",
    false
  );
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingMessage, isSending]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSending) return;
    handleSend(trimmed);
    setInput("");
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Sessions sidebar */}
      <div className="hidden w-64 shrink-0 flex-col gap-2 md:flex">
        <button
          onClick={handleNewSession}
          className="flex items-center gap-2 rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm text-text-primary hover:bg-surface-2"
        >
          <Plus size={16} />
          {t("chat.newChat")}
        </button>

        <div className="flex-1 overflow-y-auto">
          {isLoadingSessions ? (
            <p className="py-4 text-center text-xs text-text-muted">{t("common.loading")}</p>
          ) : sessions.length === 0 ? (
            <p className="py-4 text-center text-xs text-text-muted">{t("chat.noSessions")}</p>
          ) : (
            <div className="space-y-1">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className={`group flex items-center gap-2 rounded-lg px-3 py-2 text-sm cursor-pointer ${
                    activeSessionId === s.id
                      ? "bg-primary/10 text-primary"
                      : "text-text-secondary hover:bg-surface-2"
                  }`}
                  onClick={() => handleSelectSession(s.id)}
                >
                  <MessageSquare size={14} className="shrink-0" />
                  <span className="flex-1 truncate">{s.title ?? t("chat.untitled")}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteSession(s.id); }}
                    className="hidden text-text-muted hover:text-danger group-hover:block"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Chat area */}
      <Card className="flex min-w-0 flex-1 flex-col">
        <CardHeader className="flex-wrap">
          <CardTitle>{activeSessionId ? t("chat.title") : t("chat.newChat")}</CardTitle>
          <div className="flex items-center gap-3">
            <label
              className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary"
              title={t("chat.showReasoningHint")}
            >
              <input
                type="checkbox"
                checked={showReasoning}
                onChange={(e) => setShowReasoning(e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--series-1)]"
              />
              <Brain size={13} />
              {t("chat.showReasoning")}
            </label>
            <ModelPicker />
          </div>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto space-y-4 pb-4">
            {isLoadingMessages && activeSessionId ? (
              <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
            ) : messages.length === 0 && !pendingMessage ? (
              <div className="flex flex-col items-center justify-center py-16 text-text-muted">
                <MessageSquare size={48} strokeWidth={1} className="mb-4 opacity-30" />
                <p className="text-sm">{t("chat.empty")}</p>
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} msg={msg} showReasoning={showReasoning} />
                ))}
                {pendingMessage && (
                  <div className="flex justify-end chat-message-in">
                    <div className="max-w-[80%] rounded-xl bg-primary px-4 py-2.5 text-sm text-white chat-pulse">
                      <p className="whitespace-pre-wrap">{pendingMessage}</p>
                    </div>
                  </div>
                )}
                {isSending && <ThinkingIndicator />}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>

          {error && (
            <p className="mb-2 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">
              {error instanceof Error ? error.message : t("chat.sendError")}
            </p>
          )}

          {/* Input */}
          <form onSubmit={handleSubmit} className="flex gap-2 border-t border-border pt-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("chat.placeholder")}
              disabled={isSending}
              className="flex-1 rounded-lg border border-border bg-surface-0 px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none"
            />
            <button
              type="submit"
              disabled={isSending || !input.trim()}
              className="rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
            >
              {isSending ? t("chat.sending") : t("chat.send")}
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
