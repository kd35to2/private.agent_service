export interface User {
  id: string;
  username: string;
  created_at: string;
}
export interface KnowledgeDocument {
  id: string;
  name: string;
  status: string;
  version: number | null;
  chunk_count: number;
  versions: {
    id: string;
    number: number;
    status: string;
    error: string | null;
  }[];
}
export interface Chunk {
  id: string;
  index: number;
  page: number | null;
  start_index: number;
  characters: number;
  text: string;
}
export interface Evidence {
  citation: number;
  document_id: string;
  document_name: string;
  version: number;
  version_id: string;
  chunk_id: string;
  chunk_index: number;
  page: number | null;
  start_index: number;
  text: string;
  fusion_score: number;
  rerank_score: number | null;
  source_url: string;
}
export interface SearchResult {
  query: string;
  results: Evidence[];
  degraded: boolean;
  notices: string[];
}
export interface ChatMessage {
  type: "human" | "ai" | "tool" | "custom";
  content: string;
  tool_calls?: { name: string; args: unknown; id: string }[];
  custom_data?: {
    citations?: Evidence[];
    degraded?: boolean;
    notices?: string[];
  };
}
export interface Thread {
  thread_id: string;
  title: string | null;
  updated_at: string | null;
}
export interface ServiceInfo {
  models: string[];
  default_model: string;
  default_agent: string;
}
export interface UploadResult {
  document_id: string;
  duplicate: boolean;
  version?: number;
  chunk_count?: number;
}
export interface SourceChunk {
  document_name: string;
  version: number;
  chunk_index: number;
  page: number | null;
  text: string;
  current: boolean;
}
