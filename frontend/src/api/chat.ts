import { api } from "@/api/client";
import type { ChatAttachment, ChatMessage, ChatRequest, ChatResponse, ChatSession } from "@/types/chat";

export function sendMessage(input: ChatRequest) {
  return api.post<ChatResponse>("/chat", input);
}

export function fetchChatSessions() {
  return api.get<ChatSession[]>("/chat/sessions");
}

export function fetchChatMessages(sessionId: number) {
  return api.get<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`);
}

export function deleteChatSession(sessionId: number) {
  return api.delete<void>(`/chat/sessions/${sessionId}`);
}

export function uploadAttachment(file: File): Promise<ChatAttachment> {
  const formData = new FormData();
  formData.append("file", file);
  return api.post<ChatAttachment>("/chat/attachments/upload", formData);
}

export function downloadAttachmentUrl(attachmentId: number): string {
  return `/api/chat/attachments/${attachmentId}/download`;
}
