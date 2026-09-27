import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteChatSession,
  fetchChatMessages,
  fetchChatSessions,
  sendMessage,
} from "@/api/chat";
import type { ChatMessage, ChatSession } from "@/types/chat";

export function useChatSessions() {
  return useQuery<ChatSession[]>({
    queryKey: ["chat", "sessions"],
    queryFn: fetchChatSessions,
  });
}

export function useChatMessages(sessionId: number | null) {
  return useQuery<ChatMessage[]>({
    queryKey: ["chat", "messages", sessionId],
    queryFn: () => fetchChatMessages(sessionId!),
    enabled: sessionId !== null,
  });
}

export function useSendChatMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: sendMessage,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
      queryClient.invalidateQueries({
        queryKey: ["chat", "messages", data.session_id],
      });
      // Chat actions (create/delete transaction, category, account) mutate the
      // same data the rest of the app reads — without this the Transactions
      // page keeps showing a stale list until a manual reload.
      const actions = data.message?.actions ?? [];
      const touchesTransactions = actions.some((a) =>
        ["create_transaction", "delete_transaction"].includes(a.type)
      );
      const touchesCatalog = actions.some((a) =>
        ["create_category", "create_account"].includes(a.type)
      );
      if (touchesTransactions) {
        queryClient.invalidateQueries({ queryKey: ["transactions"] });
        queryClient.invalidateQueries({ queryKey: ["transaction-years"] });
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
        queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
        queryClient.invalidateQueries({ queryKey: ["cash-flow"] });
        queryClient.invalidateQueries({ queryKey: ["budget-status"] });
        queryClient.invalidateQueries({ queryKey: ["category-spending-report"] });
        queryClient.invalidateQueries({ queryKey: ["category-ranking"] });
        queryClient.invalidateQueries({ queryKey: ["financial-alerts"] });
        queryClient.invalidateQueries({ queryKey: ["advice"] });
      }
      if (touchesCatalog) {
        queryClient.invalidateQueries({ queryKey: ["accounts"] });
        queryClient.invalidateQueries({ queryKey: ["categories"] });
      }
    },
  });
}

export function useDeleteChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteChatSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
    },
  });
}

/**
 * Combines session list + messages + send into a single hook
 * for the ChatPage component to consume.
 */
export function useChat() {
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  // The just-sent message, echoed locally while the request is in flight —
  // otherwise the user's own bubble only appears after the whole backend
  // turn (LLM round-trips can take seconds).
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  // Last message that failed to send — kept so the user can resend it
  // without retyping (e.g. after a provider rate-limit error).
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);
  const sessions = useChatSessions();
  const messages = useChatMessages(activeSessionId);
  const sendMutation = useSendChatMessage();
  const deleteMutation = useDeleteChatSession();

  const handleSend = useCallback(
    (message: string, attachment_ids?: number[]) => {
      setPendingMessage(message);
      setLastFailedMessage(null);
      sendMutation.mutate(
        { message, session_id: activeSessionId ?? undefined, attachment_ids },
        {
          onSuccess: (data) => {
            setPendingMessage(null);
            setActiveSessionId(data.session_id);
          },
          onError: () => {
            setPendingMessage(null);
            setLastFailedMessage(message);
          },
        }
      );
    },
    [activeSessionId, sendMutation]
  );

  const handleResend = useCallback(() => {
    if (lastFailedMessage) {
      handleSend(lastFailedMessage);
    }
  }, [lastFailedMessage, handleSend]);

  const handleNewSession = useCallback(() => {
    setActiveSessionId(null);
  }, []);

  const handleSelectSession = useCallback((id: number) => {
    setActiveSessionId(id);
  }, []);

  const handleDeleteSession = useCallback(
    (id: number) => {
      deleteMutation.mutate(id, {
        onSuccess: () => {
          if (activeSessionId === id) {
            setActiveSessionId(null);
          }
        },
      });
    },
    [activeSessionId, deleteMutation]
  );

  return {
    sessions: sessions.data ?? [],
    messages: messages.data ?? [],
    isLoadingSessions: sessions.isLoading,
    isLoadingMessages: messages.isLoading,
    isSending: sendMutation.isPending,
    pendingMessage,
    error: sendMutation.error,
    lastFailedMessage,
    activeSessionId,
    handleSend,
    handleResend,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
  };
}
