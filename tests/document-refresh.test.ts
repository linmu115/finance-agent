import test from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import { affectsDocuments, coalesce } from '../web/src/document-refresh.js';

test('only tool events that can change the document list ask for a refresh', () => {
  const refresh = (name: string, status: string) => affectsDocuments({ name, status });
  // Reads never change documents, whatever their status.
  for (const name of ['get_data_catalog', 'get_cleaning_result', 'get_source_page', 'get_analysis_status', 'query_financial_data', 'query_research_records',
    'search_evidence', 'search_web', 'list_documents', 'read_research_source', 'read_project_skill', 'calculate_financial_metrics', 'inspect_document_routing', 'compare_financial_models']) {
    for (const status of ['started', 'progress', 'completed', 'failed']) assert.equal(refresh(name, status), false, name + ' ' + status);
  }
  // Anything else may: ingestion, commits, profile changes, downloads that register a file, database operations.
  for (const name of ['process_documents', 'prepare_document_sources', 'commit_cleaning_result', 'run_cleaning_script', 'save_research_claims', 'set_document_profile',
    'fetch_research_source', 'request_database_operation', 'run_analysis', 'run_financial_model', 'a_tool_added_later']) {
    assert.equal(refresh(name, 'started'), false, name);
    for (const status of ['progress', 'completed', 'failed']) assert.equal(refresh(name, status), true, name + ' ' + status);
  }
});

test('a burst of requests becomes one refresh per project, and later bursts refresh again', async () => {
  const calls: (string | undefined)[] = [];
  const request = coalesce((id: string | undefined) => { calls.push(id); }, 20);
  for (let i = 0; i < 50; i++) { request('a'); request('b'); request(undefined); }
  assert.deepEqual(calls, []);
  await delay(60);
  assert.deepEqual(calls, ['a', 'b', undefined]);
  request('a');
  await delay(60);
  assert.deepEqual(calls, ['a', 'b', undefined, 'a']);
  request('a'); request.cancel();
  await delay(60);
  assert.equal(calls.length, 4);
});
