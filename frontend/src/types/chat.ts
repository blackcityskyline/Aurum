export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  // Model's chain-of-thought — present only for backends that expose it.
  reasoning?: string | null;
  actions: ChatAction[];
  created_at: string;
}

export interface ChatAction {
  type: string;
  params: Record<string, unknown>;
  status: "pending" | "executed" | "failed" | "simulated";
  result?: string;
  error?: string;
}

export interface ChatSession {
  id: number;
  title: string | null;
  created_at: string;
  message_count: number;
}

export interface ChatRequest {
  message: string;
  session_id?: number;
}

export interface ChatResponse {
  session_id: number;
  message: ChatMessage;
  reply: string;
}
