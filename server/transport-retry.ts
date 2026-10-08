import {isContextOverflow,isRetryableAssistantError} from '@earendil-works/pi-ai';
import type {ExtensionFactory,SettingsManager} from '@earendil-works/pi-coding-agent';

export const TRANSPORT_RETRY={enabled:true,maxRetries:3,baseDelayMs:2000,maxAgentDelayMs:8000};

// Only assistant/provider failures reach here, never tool/business results. Explicit
// auth, quota, request and certificate errors win over incidental transport wording.
export function transientTransportError(error:string):boolean{
 if(/\b(?:400|401|402|403|404|422|429)\b|insufficient[_ ](?:quota|balance)|quota exceeded|out of budget|billing|usage limit|available balance|invalid[_ ](?:api[_ ]key|request)|authentication|permission denied|context[_ ](?:length|window)|maximum context|unsupported|not implemented|certificate|CERT_|self.signed/i.test(error))return false;
 return /stream (?:closed before response\.completed|disconnected before completion|ended before (?:message_stop|a terminal response event)|ended without)|\b(?:HTTP(?:\/\d(?:\.\d)?)?\s+|status(?: code)?[\s:="']+)[5]\d\d\b|^\s*5\d\d\b|"status"\s*:\s*5\d\d\b|\b(?:server[_ ]overloaded|overloaded_error|service unavailable|internal server error)\b|\b(?:ECONNRESET|EPIPE|ETIMEDOUT|EAI_AGAIN)\b|fetch failed|network error|connection (?:reset|lost|closed)|socket hang up|other side closed|TLS[^\n]*(?:error|failed|closed|reset|timeout|timed out)|(?:SSL|TLS) handshake/i.test(error);
}

export function transportRetryExtension(settings:SettingsManager):ExtensionFactory{
 return pi=>{
  pi.on('message_end',(event,ctx)=>{
   const message=event.message;if(message.role!=='assistant')return;
   const retry=message.stopReason==='error'&&transientTransportError(message.errorMessage||'');
   // Overflow has a separate native compaction path; don't disable summary recovery.
   settings.setRetryEnabled(message.stopReason!=='error'||retry||isContextOverflow(message,ctx.model?.contextWindow));
   // Pi 1.0.0 lacks a public classifier override. Its documented message replacement
   // hook supplies a truthful category prefix, retaining the original error verbatim.
   if(retry&&!isRetryableAssistantError(message))return {message:{...message,errorMessage:'Network error: '+message.errorMessage}};
  });
 };
}
