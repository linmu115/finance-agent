import {AsyncLocalStorage} from 'node:async_hooks';
import type {Conversation} from './types.js';

/** Trusted run context, never a model-supplied tool argument. Undefined keeps product sharing. */
export const evaluationIsolation = new AsyncLocalStorage<string|undefined>();
export const visibleInEvaluation = (value:{isolation_key?:string}) =>
 evaluationIsolation.getStore()===undefined || value.isolation_key===evaluationIsolation.getStore();

export function bindEvaluationIsolation(chat:Conversation,key?:string){
 if(chat.messages.length && chat.evaluationIsolationKey!==key)
  throw Object.assign(new Error('evaluation_conversation_isolation_conflict'),{status:409});
 if(key!==undefined)chat.evaluationIsolationKey=key;
}
