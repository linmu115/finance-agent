export interface Project { id: string; name: string; createdAt?: string; documentCount?: number; document_count?: number }
export interface Source {
  id?: string; source_id?: string; sourceId?: string; tableId?: string; documentId?: string; document_id?: string;
  page?: number; pageNumber?: number; name?: string; title?: string; table_id?: string; column?: number;
  quote?: string; text?: string; sheet?: string; cell?: string; row?: number; url?:string; snapshotUrl?:string;
}
export interface Artifact {
  producedAt?: number;
  id: string; name: string; mimeType?: string; url?: string; type?: string;
  columns?: string[]; rows?: unknown[][]; data?: unknown;
}
export interface Document {
  id: string; name: string; status: string; pageCount?: number; warnings?: string[];
  size?: number; mimeType?: string; error?: string; createdAt?: string; tableCount?: number; factCount?: number;
  tables?: { name?: string; sheet?: string; columns?: string[]; headers?: string[]; rows?: unknown[][]; rowCount?: number }[];
  pages?: { page?: number; text?: string }[];
  facts?: unknown[]; chunks?: unknown[]; metadata?: Record<string, unknown>;
}
export interface Message {
  usage?:UsageTotals;
  id: string; role: 'user' | 'assistant' | 'system'; content: string; createdAt?: string;
  attachments?: (Document | string)[]; documentIds?: string[]; sources?: Source[];
  artifacts?: Artifact[]; status?: string; tools?: ToolEvent[];
  annotations?: Annotation[];
}
export interface UsageTotals {input:number;output:number;calls:number;costUsd:number|null;uncachedInput?:number;cacheRead?:number;cacheWrite?:number;reasoning?:number;unknownCalls?:number;cacheUnknownCalls?:number;costUnknownCalls?:number;cacheKnownInput?:number;costCnyMin?:number;costCnyMax?:number;priceSource?:string;phases?:Record<string,UsageTotals>}
export interface Annotation { id: string; messageId: string; role: 'user'|'assistant'; text: string; comment: string; occurrence?: number }
export interface Conversation {
  id: string; projectId: string; title: string; messages?: Message[];
  updatedAt?: string; createdAt?: string; activeRunId?: string;
}
export interface ToolEvent { name: string; status: string; summary?: string; toolCallId?: string; timestamp?: string }
export interface APISection { baseUrl: string; model: string; apiKey?: string; hasKey?: boolean }
export interface Settings {
  llm: APISection & { provider: string; contextWindow?: number; maxTokens?: number; inputPricePerMillionUsd?: number; cacheReadPricePerMillionUsd?:number; outputPricePerMillionUsd?: number };
  embedding: APISection & { enabled: boolean; dimensions?: number };
  ocr: APISection & { mode: 'local' | 'api' };
  search: {provider:'tavily'|'brave';baseUrl:string;apiKey?:string;hasKey?:boolean;maxResults:number};
  runtime: { timeoutSeconds: number; budgetCny?: number; usdToCny?: number; contextCompaction?:{enabled:boolean;mode?:"auto"|"manual";targetTokens:number;keepRecentTokens:number} };
}
export interface Health {
  status?: string; configured?: boolean; llmConfigured?: boolean;
  services?: Record<string, unknown>; sandbox?: unknown; [key: string]: unknown;
}
export interface BenchmarkResults { runs: Record<string, unknown>[]; runtime: Record<string, unknown>[] }
export const emptySettings: Settings = {
  llm: { provider: 'openai-compatible', baseUrl: '', model: '', hasKey: false, contextWindow: 128000, maxTokens: 8192 },
  embedding: { enabled: false, baseUrl: '', model: '', hasKey: false },
  ocr: { mode: 'local', baseUrl: '', model: '', hasKey: false },
  search: {provider:'tavily',baseUrl:'https://api.tavily.com',maxResults:6,hasKey:false},
  runtime: { timeoutSeconds: 120,contextCompaction:{enabled:true,mode:"auto",targetTokens:96000,keepRecentTokens:24000} },
};
