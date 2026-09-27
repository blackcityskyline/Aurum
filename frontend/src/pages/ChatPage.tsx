import { useEffect, useRef, useState } from "react";
import { Brain, MessageSquare, PanelLeftClose, PanelLeftOpen, Paperclip, Plus, Send, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { useChat } from "@/hooks/useChat";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { useTranslation } from "@/lib/i18n";
import { uploadAttachment, downloadAttachmentUrl } from "@/api/chat";
import type { ChatAction, ChatAttachment, ChatMessage } from "@/types/chat";

const ACTION_COLORS: Record<string, string> = {
  executed: "bg-success/15 text-success",
  failed: "bg-danger/15 text-danger",
  pending: "bg-warning/15 text-warning",
  simulated: "bg-info/15 text-info",
};

// First-visit default for the history column, read once at load: a wide
// screen shows it as a column, a narrow one keeps it tucked away (it can
// only appear there as an overlay). After that the stored choice wins.
const IS_WIDE_SCREEN =
  typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches;

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

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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
        {msg.attachments.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {msg.attachments.map((att) => (
              <a
                key={att.id}
                href={downloadAttachmentUrl(att.id)}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs transition-colors ${
                  isUser
                    ? "bg-white/20 text-white hover:bg-white/30"
                    : "bg-surface-1 text-text-secondary hover:bg-surface-0"
                }`}
              >
                <Paperclip size={12} />
                <span className="max-w-[120px] truncate">{att.filename}</span>
                <span className={isUser ? "text-white/60" : "text-text-muted"}>
                  ({formatFileSize(att.size)})
                </span>
              </a>
            ))}
          </div>
        )}
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

/** One shared Card holds the history column *and* the conversation, so the
 * two read as a single surface instead of two floating boxes: the column is
 * just a border-right inside the card, and the toggle in the header hides
 * it (inline on desktop, overlay + backdrop on mobile). */
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
    lastFailedMessage,
    activeSessionId,
    handleSend,
    handleResend,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
  } = useChat();

  const [input, setInput] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<ChatAttachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showReasoning, setShowReasoning] = useLocalStorageState(
    "aurum:chat-show-reasoning",
    false
  );
  // First visit opens the column on desktop (where it fits next to the
  // chat) and keeps it hidden on mobile (where it can only appear as an
  // overlay covering the conversation); the stored choice wins afterwards.
  const [historyOpen, setHistoryOpen] = useLocalStorageState(
    "aurum:chat-history-open",
    IS_WIDE_SCREEN
  );
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingMessage, isSending]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if ((!trimmed && pendingAttachments.length === 0) || isSending) return;
    handleSend(trimmed, pendingAttachments.map((a) => a.id));
    setInput("");
    setPendingAttachments([]);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    
    // Check file size (10 MB)
    if (file.size > 10 * 1024 * 1024) {
      setUploadError(t("chat.attachmentTooLarge", { size: "10 MB" }));
      return;
    }
    
    setIsUploading(true);
    setUploadError(null);
    try {
      const attachment = await uploadAttachment(file);
      setPendingAttachments((prev) => [...prev, attachment]);
    } catch (err) {
      setUploadError(t("chat.attachmentUploadError"));
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemoveAttachment = (id: number) => {
    setPendingAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const historyToggleLabel = historyOpen ? t("chat.historyCollapse") : t("chat.historyExpand");

  return (
    <div className="flex h-[calc(100vh-8rem)]">
      <Card className="relative flex min-w-0 flex-1 overflow-hidden">
        {/* Mobile: the open column floats over the conversation, so it needs
            something to tap to close it again. Desktop has the header toggle. */}
        {historyOpen && (
          <button
            type="button"
            aria-label={t("chat.historyCollapse")}
            onClick={() => setHistoryOpen(false)}
            className="absolute inset-0 z-20 bg-black/40 md:hidden"
          />
        )}

        {/* Sessions history — a column inside the same card as the chat */}
        <aside
          aria-label={t("chat.historyTitle")}
          className={`w-64 shrink-0 flex-col border-r border-border bg-surface-1 max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:z-30 ${
            historyOpen ? "flex" : "hidden"
          }`}
        >
          <div className="flex items-center gap-2 border-b border-border p-3">
            <button
              onClick={handleNewSession}
              className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm text-text-primary hover:bg-surface-2"
            >
              <Plus size={16} />
              {t("chat.newChat")}
            </button>
            {/* Collapse from inside the column too — on mobile this is the
                only close affordance next to tapping the backdrop. */}
            <button
              type="button"
              onClick={() => setHistoryOpen(false)}
              title={t("chat.historyCollapse")}
              aria-label={t("chat.historyCollapse")}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-text-muted hover:bg-surface-2 hover:text-text-primary"
            >
              <PanelLeftClose size={16} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
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
        </aside>

        {/* Chat area */}
        <div className="flex min-w-0 flex-1 flex-col">
          <CardHeader className="flex-wrap">
            <div className="flex min-w-0 items-center gap-2">
              <button
                type="button"
                onClick={() => setHistoryOpen(!historyOpen)}
                title={historyToggleLabel}
                aria-label={historyToggleLabel}
                aria-expanded={historyOpen}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                {historyOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
              </button>
              <CardTitle className="truncate">
                {activeSessionId ? t("chat.title") : t("chat.newChat")}
              </CardTitle>
            </div>
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
              <div className="mb-2 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">
                <p>{error instanceof Error ? error.message : t("chat.sendError")}</p>
                {lastFailedMessage && (
                  <button
                    onClick={handleResend}
                    disabled={isSending}
                    className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-danger/20 px-2 py-1 font-medium text-danger transition-colors hover:bg-danger/30 disabled:opacity-50"
                  >
                    <Send size={12} />
                    {t("chat.resend")}
                  </button>
                )}
              </div>
            )}

            {/* Pending attachments */}
            {pendingAttachments.length > 0 && (
              <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                {pendingAttachments.map((att) => (
                  <span
                    key={att.id}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-surface-2 px-2.5 py-1.5 text-xs text-text-secondary"
                  >
                    <Paperclip size={12} />
                    <span className="max-w-[120px] truncate">{att.filename}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveAttachment(att.id)}
                      className="text-text-muted hover:text-danger"
                      aria-label={t("chat.removeAttachment")}
                    >
                      <Trash2 size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {uploadError && (
              <p className="mt-1 text-xs text-danger">{uploadError}</p>
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
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                className="hidden"
                accept=".pdf,.csv,.json,.txt,.xlsx,.xls,.png,.jpg,.jpeg,.gif,.webp"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSending || isUploading}
                title={t("chat.attach")}
                aria-label={t("chat.attach")}
                className="inline-flex items-center justify-center rounded-lg border border-border bg-surface-0 px-3 py-2.5 text-text-muted transition-colors hover:bg-surface-2 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Paperclip size={15} />
              </button>
              <button
                type="submit"
                disabled={isSending || (!input.trim() && pendingAttachments.length === 0)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Send size={15} />
                {isSending ? t("chat.sending") : t("chat.send")}
              </button>
            </form>
          </CardContent>
        </div>
      </Card>
    </div>
  );
}
