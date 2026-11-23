import type { ConversationDetail, ConversationList, ConversationSummary, QuotaState } from "../types/api";
import { apiRequest } from "./http";

/** Taille de page maximale autorisée par le contrat (conception §3.4). */
export const PAGE_SIZE = 50;

export function listConversations(token: string, cursor?: string): Promise<ConversationList> {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) query.set("cursor", cursor);
  return apiRequest(`/conversations?${query}`, { token });
}

export function getConversation(token: string, id: string): Promise<ConversationDetail> {
  return apiRequest(`/conversations/${id}`, { token });
}

export function renameConversation(token: string, id: string, title: string): Promise<ConversationSummary> {
  return apiRequest(`/conversations/${id}`, { method: "PATCH", token, body: { title } });
}

export function deleteConversation(token: string, id: string): Promise<void> {
  return apiRequest(`/conversations/${id}`, { method: "DELETE", token });
}

export function getQuota(token: string): Promise<QuotaState> {
  return apiRequest("/me/quota", { token });
}
