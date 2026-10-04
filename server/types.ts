export interface LlmConfig { provider: 'openai-compatible'; baseUrl: string; model: string; apiKey: string; contextWindow: number; maxTokens: number; inputPricePerMillionUsd?: number; outputPricePerMillionUsd?: number }
export interface SearchConfig { provider:'tavily'|'brave'; baseUrl:string; apiKey:string; maxResults:number }
export interface ContextCompactionSettings { enabled:boolean; targetTokens:number; keepRecentTokens:number; summaryMaxTokens:number }
export const DEFAULT_CONTEXT_COMPACTION:ContextCompactionSettings={enabled:true,targetTokens:96000,keepRecentTokens:24000,summaryMaxTokens:8192};
export interface Settings { llm: LlmConfig; embedding: { enabled: boolean; baseUrl: string; model: string; apiKey: string; dimensions?: number }; ocr: { mode: 'local'|'api'; baseUrl: string; model: string; apiKey: string }; search?:SearchConfig; runtime: { maxToolCalls: number; timeoutSeconds: number; budgetCny?: number; usdToCny?: number; contextCompaction?:ContextCompactionSettings } }
export interface Source { documentId: string; page?: number; tableId?: string; cell?: string; sheet?: string; quote?: string; sourceId?: string; url?:string; title?:string; snapshotUrl?:string }
export interface Artifact { id: string; name: string; mimeType: string; url: string }
export interface MessageAnnotation { id: string; messageId: string; role: 'user'|'assistant'; text: string; comment: string; occurrence?: number }
export interface Message { id: string; role: 'user'|'assistant'; content: string; createdAt: string; attachments?: string[]; annotations?: MessageAnnotation[]; sources?: Source[]; artifacts?: Artifact[]; status?: string; tools?: ToolEvent[]; runId?: string }
export interface Conversation { id: string; projectId: string; title: string; messages: Message[]; createdAt: string; updatedAt: string; evaluationProfile?:'financial'|'generic' }
export interface ToolEvent { name: string; status: string; summary?: string; toolCallId?: string; timestamp: string }
export interface Run { id: string; conversationId: string; projectId: string; status: 'queued'|'running'|'completed'|'failed'|'cancelled'; stage: string; createdAt: string; finishedAt?: string; error?: string; tools: ToolEvent[]; usage: { input: number; output: number; calls: number; costUsd: number | null }; model: string; configHash: string; messageId: string; evaluation?:import('./evaluation-budget.js').BudgetSnapshot }
export interface Envelope<T = any> { status: string; data: T; source_refs?: any[]; warnings?: string[]; trace_id?: string; error?: any }
