const $ = id => document.getElementById(id);
let status, tools = [], offset = 0, source = '', busy = 0;
const examples = {
  rag_search: {query: 'retrieval augmented generation', k: 5, mode: 'hybrid'},
  rag_answer: {query: 'How does retrieval work?', k: 4},
  rag_load: {prefix: '0_dev/0_AI'}, rag_status: {},
  rag_ingest: {collection: 'scratch', documents: [{id: 'example', content: 'Your text here', metadata: {source: 'manual'}}]},
  rag_list: {collection: 'papers', limit: 30}, rag_remove: {doc_id: 'example', collection: 'scratch'},
  rag_clear: {}, rag_chunks: {source: '', limit: 30}, rag_sources: {prefix: '0_dev/0_AI/'}, rag_logs: {limit: 100}
};
function notice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
async function call(tool, args = {}, confirm = '') {
  const response = await fetch('/api/call', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tool, arguments: args, confirm})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
async function run(action) {
  notice(''); busy++;
  document.querySelectorAll('button[type=submit], #answer').forEach(b => b.disabled = true);
  try { await action(); } catch (error) { notice(error.message); }
  finally { if (!--busy) document.querySelectorAll('button[type=submit], #answer').forEach(b => b.disabled = false); }
}
function element(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function passages(container, items) {
  container.replaceChildren();
  if (!items.length) { container.append(element('p', 'No chunks found. Try another query, collection, or source.', 'empty')); return; }
  for (const item of items) {
    const m = item.metadata || {}, card = element('article', undefined, 'passage');
    card.append(element('h3', m.heading || m.source || item.source || item.id));
    const meta = element('div', undefined, 'metadata');
    for (const value of [m.source, item.score !== undefined ? `Similarity ${item.score}` : '', item.match ? `Matched by ${item.match}` : '', m.chunk !== undefined ? `Chunk ${m.chunk + 1}` : '', m.tokens ? `${m.tokens} tokens` : '', m.split_reason ? `Split: ${m.split_reason}` : '', m.chunker || '']) if (value) meta.append(element('span', value));
    card.append(meta, element('pre', item.text || item.snippet || ''), element('span', item.id, 'chunk-id'));
    container.append(card);
  }
}
async function refresh() {
  status = await call('rag_status');
  $('health').textContent = `${status.docs.toLocaleString()} vault chunks · ${status.tracked_files} notes`;
  $('sync').textContent = status.vault_sync.last_error || `Last sync ${status.vault_sync.last_ok || 'pending'}`;
  $('sync').className = status.vault_sync.last_error ? 'error' : '';
  for (const select of document.querySelectorAll('.collections')) {
    const value = select.value;
    select.replaceChildren(...Object.keys(status.collections).filter(x => x !== 'error').map(name => { const o = element('option', name); o.value = name; return o; }));
    select.value = value && [...select.options].some(o => o.value === value) ? value : 'documents';
  }
  $('answer').title = status.answer_available ? 'Answer using retrieved passages' : 'Set LLM_API_KEY on the RAG service to enable generated answers';
}
async function retrieve(answer = false) {
  const query = $('query').value.trim();
  if (!query) { $('query').focus(); throw new Error('Enter a question or search phrase.'); }
  if (answer && !status.answer_available) throw new Error('Generated answers require LLM_API_KEY on the service. Retrieval works without it.');
  if (answer && $('search-collection').value !== 'documents') throw new Error('Generated answers currently use the documents collection.');
  const result = await call(answer ? 'rag_answer' : 'rag_search', answer ? {query, k: +$('k').value} : {query, k: +$('k').value, mode: $('mode').value, collection: $('search-collection').value});
  const items = result.results || result.chunks || [];
  $('answer-result').hidden = !answer; $('answer-result').textContent = result.answer || '';
  passages($('results'), items); $('result-count').textContent = `${items.length} chunks`;
}
async function loadSources() {
  const result = await call('rag_sources', {collection: $('browse-collection').value, prefix: $('source-filter').value.trim()});
  $('source-count').textContent = `${result.sources.length} notes`;
  $('sources').replaceChildren();
  if (!result.sources.length) $('sources').append(element('p', 'No indexed notes match this path.'));
  for (const item of result.sources) {
    const b = element('button', `${item.source} (${item.chunks})`); b.type = 'button'; b.className = item.source === source ? 'selected' : '';
    b.onclick = () => run(async () => {source = item.source; offset = 0; await loadChunks(); document.querySelectorAll('.source-list button').forEach(x => x.classList.toggle('selected', x === b));});
    $('sources').append(b);
  }
}
async function loadChunks() {
  const result = await call('rag_chunks', {collection: $('browse-collection').value, source, offset, limit: 30});
  $('selected-source').textContent = source || 'All chunks';
  passages($('chunks'), result.items); $('page').textContent = result.count ? `${offset + 1}–${offset + result.count}` : 'No chunks';
  $('previous').hidden = offset === 0; $('next').hidden = !result.has_more;
}
async function logs() {
  const result = await call('rag_logs', {date: $('log-date').value, limit: 150});
  $('log-file').textContent = result.file; $('events').replaceChildren();
  if (!result.events.length) $('events').append(element('p', 'No recorded activity for this date.'));
  for (const row of result.events) {
    const d = element('details');
    d.append(element('summary', `${row.timestamp}  ${row.tool || row.source || ''}  ${row.event}${row.status ? ` (${row.status})` : ''}${row.duration_ms !== undefined ? `  ${row.duration_ms} ms` : ''}`, row.event === 'tool_error' ? 'error' : ''), element('pre', JSON.stringify(row, null, 2)));
    $('events').append(d);
  }
}
function selectTool() {
  const name = $('tool').value;
  $('arguments').value = JSON.stringify(examples[name] || {}, null, 2);
  $('tool-description').textContent = tools.find(t => t.name === name)?.description || '';
}
document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => run(async () => {
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b === button));
  document.querySelectorAll('.view').forEach(v => v.hidden = v.id !== button.dataset.view);
  if (button.dataset.view === 'browse') {await loadSources(); await loadChunks();}
  if (button.dataset.view === 'logs') await logs();
}));
$('search-form').onsubmit = e => {e.preventDefault(); run(() => retrieve());};
$('answer').onclick = () => run(() => retrieve(true));
$('refresh').onclick = () => run(refresh);
$('sources-refresh').onclick = () => run(loadSources);
$('source-filter').onkeydown = e => {if (e.key === 'Enter') run(loadSources);};
$('browse-collection').onchange = () => run(async () => {source = ''; offset = 0; await loadSources(); await loadChunks();});
$('previous').onclick = () => run(async () => {offset = Math.max(0, offset - 30); await loadChunks();});
$('next').onclick = () => run(async () => {offset += 30; await loadChunks();});
$('logs-refresh').onclick = () => run(logs);
$('tool').onchange = selectTool;
$('tool-form').onsubmit = e => { e.preventDefault(); run(async () => {
  const tool = $('tool').value, args = JSON.parse($('arguments').value);
  if (['rag_clear', 'rag_remove'].includes(tool) && !window.confirm(tool === 'rag_clear' ? 'Delete the entire vault index? This cannot be undone.' : `Remove indexed chunk ${args.doc_id}?`)) return;
  $('tool-result').textContent = 'Running…';
  try { $('tool-result').textContent = JSON.stringify(await call(tool, args, tool), null, 2); }
  catch (error) { $('tool-result').textContent = error.message; throw error; }
});};
const now = new Date(); $('log-date').value = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
run(async () => { await refresh(); const response = await fetch('/api/tools'); if (!response.ok) throw new Error('Could not load tools'); tools = (await response.json()).tools; $('tool').replaceChildren(...tools.map(t => {const o = element('option', t.name); o.value = t.name; return o;})); selectTool(); });
