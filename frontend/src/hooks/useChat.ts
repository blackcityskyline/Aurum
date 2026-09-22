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
  const sessions = useChatSessions();
  const messages = useChatMessages(activeSessionId);
  const sendMutation = useSendChatMessage();
  const deleteMutation = useDeleteChatSession();

  const handleSend = useCallback(
    (message: string) => {
      sendMutation.mutate(
        { message, session_id: activeSessionId ?? undefined },
        {
          onSuccess: (data) => {
            setActiveSessionId(data.session_id);
          },
        }
      );
    },
    [activeSessionId, sendMutation]
  );

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
    error: sendMutation.error,
    activeSessionId,
    handleSend,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
  };
}
