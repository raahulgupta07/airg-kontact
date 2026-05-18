<script>
  import { onMount } from 'svelte';
  import { markdownToHtml } from '$lib/markdown';

  let messages = $state([]);
  let input = $state('');
  let sessionId = $state(null);
  let sessions = $state([]);
  let loading = $state(false);
  let showHistory = $state(false);
  let modelConfig = $state(null);
  let streamingText = $state('');
  let toolSteps = $state([]);
  let abortController = $state(null);
  let expandedImg = $state(null);
  let historyFilter = $state('');
  let isListening = $state(false);

  let chatContainer = $state(null);
  let textareaEl = $state(null);
  let copiedIdx = $state(-1);
  let feedbackState = $state({});

  function getTimestamp() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  function timeAgo(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'Z');
    const diff = Math.floor((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  async function copyText(text, idx) {
    try { await navigator.clipboard.writeText(text); copiedIdx = idx; setTimeout(() => { copiedIdx = -1; }, 1500); } catch (err) { console.error('Copy failed:', err); }
  }
  function exportCSV(text) {
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'kontact-response.txt'; a.click(); URL.revokeObjectURL(url);
  }
  function exportChatMarkdown() {
    if (messages.length === 0) return;
    const lines = messages.map(msg => {
      if (msg.role === 'user') return `> ${msg.content}`;
      return msg.content;
    });
    const md = lines.join('\n\n---\n\n');
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `kontact-chat-${new Date().toISOString().slice(0,10)}.md`; a.click(); URL.revokeObjectURL(url);
  }
  async function submitFeedback(idx, rating) {
    if (feedbackState[idx]) return;
    const msg = messages[idx];
    let question = '';
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { question = messages[i].content; break; }
    }
    try {
      await fetch('/api/feedback', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId || '', question, answer: msg.content, rating })
      });
      feedbackState = { ...feedbackState, [idx]: rating };
    } catch (err) { console.error('Feedback error:', err); }
  }

  const defaultChips = [
    'Who did I meet?',
    'Show WhatsApp contacts',
    'Catalogs from Acme',
    'Recent uploads'
  ];

  $effect(() => { if (typeof localStorage !== 'undefined') localStorage.setItem('kontact-showHistory', String(showHistory)); });
  $effect(() => { document.body.style.overflow = expandedImg ? 'hidden' : 'auto'; });
  $effect(() => {
    if (chatContainer && (messages.length || streamingText || toolSteps.length))
      requestAnimationFrame(() => { chatContainer.scrollTop = chatContainer.scrollHeight; });
  });
  function autoGrow() { if (!textareaEl) return; textareaEl.style.height = 'auto'; textareaEl.style.height = Math.min(textareaEl.scrollHeight, 160) + 'px'; }

  async function send(text) {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    input = ''; if (textareaEl) textareaEl.style.height = 'auto';
    messages = [...messages, { role: 'user', content: question, timestamp: getTimestamp() }];
    loading = true; streamingText = ''; toolSteps = [];
    abortController = new AbortController();
    let streamTimeout = null;
    let receivedContent = false;
    function resetStreamTimeout() {
      if (streamTimeout) clearTimeout(streamTimeout);
      streamTimeout = setTimeout(() => {
        if (!receivedContent && abortController) {
          abortController.abort();
          messages = [...messages, { role: 'assistant', content: streamingText || 'Request timed out. The server took too long to respond.', sources: [], timestamp: getTimestamp() }];
          streamingText = ''; loading = false; toolSteps = []; abortController = null;
        }
      }, 60000);
    }
    resetStreamTimeout();
    try {
      const res = await fetch('/api/chat/stream', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, session_id: sessionId }), signal: abortController.signal });
      const reader = res.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        resetStreamTimeout();
        buffer += decoder.decode(value, { stream: true }); const lines = buffer.split('\n'); buffer = lines.pop() || '';
        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim(); }
          else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (currentEvent === 'session') sessionId = data.session_id;
              else if (currentEvent === 'status') { toolSteps = toolSteps.map(s => ({ ...s, done: true })); toolSteps = [...toolSteps, { text: data.step, done: false }]; }
              else if (currentEvent === 'content') { receivedContent = true; if (toolSteps.length && !toolSteps[toolSteps.length - 1].done) toolSteps = toolSteps.map(s => ({ ...s, done: true })); streamingText += data.text; }
              else if (currentEvent === 'done') {
                const rawSources = data.sources ?? [];
                const seen = new Set();
                const uniqueSources = rawSources.filter(s => { const key = `${s.folder}/${s.file}`; if (seen.has(key)) return false; seen.add(key); return true; });
                messages = [...messages, { role: 'assistant', content: streamingText, sources: uniqueSources, timestamp: getTimestamp() }]; streamingText = '';
              }
            } catch (_) {}
          }
        }
      }
    } catch (err) {
      console.error('Chat error:', err);
      if (err.name !== 'AbortError') messages = [...messages, { role: 'assistant', content: streamingText || 'Sorry, something went wrong.', sources: [], timestamp: getTimestamp() }];
      streamingText = '';
    } finally { if (streamTimeout) clearTimeout(streamTimeout); loading = false; toolSteps = []; abortController = null; }
  }

  let filteredSessions = $derived(
    historyFilter.trim()
      ? sessions.filter(s => (s.preview || '').toLowerCase().includes(historyFilter.trim().toLowerCase()))
      : sessions
  );

  function toggleVoice() {
    if (isListening) { isListening = false; return; }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { alert('Speech recognition not supported in this browser.'); return; }
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => { const transcript = event.results[0][0].transcript; input = input ? input + ' ' + transcript : transcript; };
    recognition.onend = () => { isListening = false; };
    recognition.onerror = () => { isListening = false; };
    recognition.start();
    isListening = true;
  }

  function stopStreaming() { if (abortController) abortController.abort(); }
  function handleKeydown(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }

  async function loadSession(sid) {
    sessionId = sid;
    const res = await fetch(`/api/chat/history/${sid}`, { credentials: 'include' }); if (!res.ok) return;
    const history = await res.json();
    messages = history.map(h => ({ role: h.role, content: h.content, sources: [], timestamp: '' }));
  }
  async function newSession() { sessionId = null; messages = []; }
  async function deleteSession(sid) {
    await fetch(`/api/chat/sessions/${sid}`, { method: 'DELETE', credentials: 'include' });
    sessions = sessions.filter(s => s.session_id !== sid);
    if (sessionId === sid) { sessionId = null; messages = []; }
  }
  async function refreshSessions() { const res = await fetch('/api/chat/sessions', { credentials: 'include' }); if (res.ok) sessions = await res.json(); }

  onMount(async () => {
    const saved = localStorage.getItem('kontact-showHistory');
    if (saved === 'true') showHistory = true;
    await refreshSessions();
    try { const res = await fetch('/api/config', { credentials: 'include' }); modelConfig = await res.json(); } catch {}
  });
</script>

<svelte:head><title>KONTACT Agent</title></svelte:head>

{#if expandedImg}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="lightbox" onclick={() => expandedImg = null} onkeydown={(e) => e.key === 'Escape' && (expandedImg = null)}>
    <img src={expandedImg.src} alt={expandedImg.alt} class="lightbox-img" />
    <div class="lightbox-caption">{expandedImg.alt}</div>
    <button class="lightbox-close" aria-label="Close image" onclick={() => expandedImg = null}>&times;</button>
  </div>
{/if}

<div class="chat-page">
  <header class="chat-header">
    <h1>KONTACT Agent</h1>
    <div class="header-actions">
      <button class="icon-btn mobile-only" class:active={showHistory} title="History" aria-label="History" onclick={() => { showHistory = !showHistory; if (showHistory) refreshSessions(); }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>
      </button>
      <button class="icon-btn" title="New chat" aria-label="New chat" onclick={newSession}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
      {#if messages.length > 0}
        <button class="icon-btn" title="Export chat" aria-label="Export chat" onclick={exportChatMarkdown}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        </button>
      {/if}
    </div>
  </header>

  <div class="chat-body">
    <aside class="history-panel" class:show-mobile={showHistory}>
      <div class="history-title">Chat history</div>
      <div class="history-search-wrap">
        <input class="history-search" type="text" bind:value={historyFilter} placeholder="Search sessions" />
      </div>
      {#each filteredSessions as s}
        <div class="history-item" class:active={sessionId === s.session_id}>
          <button class="history-item-btn" onclick={() => loadSession(s.session_id)}>
            <span class="history-preview">{s.preview || s.session_id}{#if s.preview && s.preview.length >= 50}...{/if}</span>
            <span class="history-meta">{timeAgo(s.last_msg)}</span>
          </button>
          <button class="history-delete" onclick={() => deleteSession(s.session_id)} aria-label="Delete session" title="Delete">&times;</button>
        </div>
      {/each}
      {#if filteredSessions.length === 0}<p class="history-empty">{historyFilter.trim() ? 'No matching sessions' : 'No sessions yet'}</p>{/if}
    </aside>

    <div class="messages-wrap" bind:this={chatContainer}>
      <div class="messages-col">
        {#if messages.length === 0 && !loading}
          <div class="empty-state">
            <h2 class="empty-title">How can I help with your catalogs?</h2>
            <p class="empty-sub">Ask anything about uploaded catalogs, contacts, or products.</p>
            <div class="chip-row">
              {#each defaultChips as chip}
                <button class="prompt-chip" onclick={() => send(chip)}>{chip}</button>
              {/each}
            </div>
          </div>
        {/if}

        {#each messages as msg, idx}
          {#if msg.role === 'user'}
            <div class="row row-user animate-fade-up">
              <div class="bubble-user-c">{msg.content}</div>
            </div>
          {:else}
            <div class="row row-assistant animate-fade-up">
              <div class="bubble-assistant-c">
                <div class="prose-chat">{@html markdownToHtml(msg.content)}</div>

                {#if msg.sources?.length > 0}
                  <div class="cite-strip">
                    {#each msg.sources as src, si}
                      <button class="cite-chip" onclick={() => expandedImg = { src: `/api/image/${src.folder}/${src.file}`, alt: `${src.folder} · ${src.file}${src.company ? ' · ' + src.company : ''}` }} title="Click to enlarge">
                        <img src={`/api/image/${src.folder}/${src.file}`} alt={src.file} class="cite-thumb-img" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                        <span class="cite-info">
                          <span class="cite-company">{src.company || src.folder}</span>
                          <span class="cite-folder">{src.folder}</span>
                        </span>
                      </button>
                    {/each}
                  </div>
                {/if}

                <div class="msg-actions">
                  <button class="ghost-icon" class:fb-up={feedbackState[idx] === 'up'} title="Helpful" aria-label="Helpful" disabled={!!feedbackState[idx]} onclick={() => submitFeedback(idx, 'up')}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill={feedbackState[idx] === 'up' ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.8"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
                  </button>
                  <button class="ghost-icon" class:fb-down={feedbackState[idx] === 'down'} title="Not helpful" aria-label="Not helpful" disabled={!!feedbackState[idx]} onclick={() => submitFeedback(idx, 'down')}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill={feedbackState[idx] === 'down' ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.8"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>
                  </button>
                  <button class="ghost-icon" title={copiedIdx === idx ? 'Copied' : 'Copy'} aria-label="Copy response" onclick={() => copyText(msg.content, idx)}>
                    {#if copiedIdx === idx}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"/></svg>
                    {:else}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    {/if}
                  </button>
                  <button class="ghost-icon" title="Save" aria-label="Save response" onclick={() => exportCSV(msg.content)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  </button>
                </div>
              </div>
            </div>
          {/if}
        {/each}

        {#if loading && toolSteps.length > 0}
          <div class="row row-assistant animate-fade-up">
            <div class="tool-block">
              <div class="tool-pill">
                <span class="tool-spinner"></span>
                <span>RAG analyzing</span>
              </div>
              <details class="tool-details">
                <summary>Show details</summary>
                <div class="tool-steps">
                  {#each toolSteps as step}
                    <div class="tool-step">
                      {#if step.done}
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg>
                      {:else}
                        <span class="tool-spinner small"></span>
                      {/if}
                      <span class:tool-done={step.done}>{step.text}</span>
                    </div>
                  {/each}
                </div>
              </details>
            </div>
          </div>
        {/if}

        {#if streamingText}
          <div class="row row-assistant animate-fade-up">
            <div class="bubble-assistant-c">
              <div class="prose-chat">{@html markdownToHtml(streamingText)}</div>
            </div>
          </div>
        {/if}

        {#if loading && !streamingText && toolSteps.length === 0}
          <div class="row row-assistant animate-fade-up">
            <div class="tool-pill"><span class="tool-spinner"></span><span>Thinking</span></div>
          </div>
        {/if}
      </div>
    </div>
  </div>

  <div class="input-wrap">
    <div class="input-shell">
      <textarea bind:this={textareaEl} bind:value={input} oninput={autoGrow} onkeydown={handleKeydown} placeholder="Ask about your catalogs..." rows="1" disabled={loading}></textarea>
      <div class="input-actions">
        <button class="ghost-icon" class:voice-active={isListening} onclick={toggleVoice} disabled={loading} title={isListening ? 'Stop listening' : 'Voice input'} aria-label="Voice input">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="2" width="6" height="11" rx="3"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
        </button>
        {#if loading}
          <button class="round-btn stop" onclick={stopStreaming} title="Stop" aria-label="Stop generating">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
          </button>
        {:else}
          <button class="round-btn" onclick={() => send()} disabled={!input.trim()} aria-label="Send message" title="Send">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
          </button>
        {/if}
      </div>
    </div>
    <div class="footer-disclaimer">KONTACT can make mistakes. Verify critical information.</div>
  </div>
</div>

<style>
  @keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  .animate-fade-up { animation: fadeUp 0.25s ease-out both; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .chat-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    max-height: 100%;
    overflow: hidden;
    font-family: var(--font-sans);
    color: var(--text);
    background: var(--bg);
    padding-bottom: 56px;
    box-sizing: border-box;
  }
  @media (min-width: 768px) { .chat-page { padding-bottom: 0; } }

  .chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--bg);
    flex-shrink: 0;
  }
  .chat-header h1 {
    font-size: 16px;
    font-weight: 600;
    margin: 0;
    color: var(--text);
    letter-spacing: 0;
  }
  .header-actions { display: flex; gap: 4px; }

  .icon-btn {
    width: 32px;
    height: 32px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-muted);
    border-radius: var(--r-md);
    cursor: pointer;
    transition: background-color 0.15s, color 0.15s;
  }
  .icon-btn:hover, .icon-btn.active {
    background: var(--surface-2);
    color: var(--text);
  }
  @media (min-width: 768px) { .mobile-only { display: none; } }

  .chat-body { flex: 1; display: flex; overflow: hidden; min-height: 0; }

  /* Sidebar / history */
  .history-panel {
    width: 240px;
    flex-shrink: 0;
    border-right: 1px solid var(--border);
    background: var(--sidebar-bg);
    overflow-y: auto;
    display: none;
    padding: 12px 8px;
  }
  @media (min-width: 768px) { .history-panel { display: block; } }
  .history-panel.show-mobile { display: block; }
  .history-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    padding: 4px 8px 8px;
    letter-spacing: 0;
  }
  .history-search-wrap { padding: 4px 4px 8px; }
  .history-search {
    width: 100%;
    font-family: var(--font-sans);
    font-size: 13px;
    padding: 8px 10px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    border-radius: var(--r-md);
    box-sizing: border-box;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .history-search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .history-search::placeholder { color: var(--text-faint); }

  .history-item {
    display: flex;
    align-items: center;
    border-radius: var(--r-md);
    margin-bottom: 2px;
  }
  .history-item:hover { background: var(--surface); }
  .history-item.active { background: var(--surface); }
  .history-item-btn {
    flex: 1;
    text-align: left;
    padding: 8px 10px;
    background: none;
    border: none;
    cursor: pointer;
    font-family: inherit;
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: var(--text);
    min-width: 0;
  }
  .history-preview {
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 180px;
    color: var(--text);
  }
  .history-meta { font-size: 11px; color: var(--text-faint); }
  .history-delete {
    background: none;
    border: none;
    font-size: 18px;
    padding: 6px 8px;
    cursor: pointer;
    color: var(--text-faint);
    border-radius: var(--r-sm);
  }
  .history-delete:hover { color: var(--danger); background: var(--surface-2); }
  .history-empty { font-size: 13px; color: var(--text-muted); padding: 12px 10px; margin: 0; }

  /* Messages */
  .messages-wrap {
    flex: 1;
    overflow-y: auto;
    scroll-behavior: smooth;
    width: 100%;
    box-sizing: border-box;
  }
  .messages-col {
    max-width: 760px;
    margin: 0 auto;
    padding: 32px 20px 48px;
    display: flex;
    flex-direction: column;
    gap: 0;
    width: 100%;
    box-sizing: border-box;
  }

  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    text-align: center;
    padding: 80px 16px 32px;
  }
  .empty-title {
    font-family: var(--font-serif);
    font-size: 24px;
    font-weight: 500;
    color: var(--text);
    margin: 0;
    letter-spacing: 0;
  }
  .empty-sub {
    font-size: 14px;
    color: var(--text-muted);
    margin: 0 0 16px;
  }
  .chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    max-width: 560px;
  }
  .prompt-chip {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 500;
    padding: 8px 14px;
    cursor: pointer;
    border-radius: var(--r-pill);
    transition: background-color 0.15s, border-color 0.15s;
  }
  .prompt-chip:hover {
    background: var(--surface-2);
    border-color: var(--border-strong);
  }

  /* Row layouts */
  .row { display: flex; margin-bottom: 16px; }
  .row-user { justify-content: flex-end; }
  .row-assistant { justify-content: flex-start; }

  /* User bubble */
  .bubble-user-c {
    background: var(--accent-soft);
    color: var(--accent-ink);
    border-radius: var(--r-lg);
    padding: 12px 16px;
    max-width: 80%;
    font-size: 15px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-wrap: break-word;
  }

  /* Assistant bubble — bordered card */
  .bubble-assistant-c {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--shadow-sm);
    padding: 14px 18px;
    width: 100%;
    font-size: 15px;
    line-height: 1.6;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  /* Prose styles inside assistant */
  .prose-chat :global(p) { margin: 0.6em 0; }
  .prose-chat :global(p:first-child) { margin-top: 0; }
  .prose-chat :global(p:last-child) { margin-bottom: 0; }
  .prose-chat :global(strong) { font-weight: 600; color: var(--text); }
  .prose-chat :global(em) { font-style: italic; }
  .prose-chat :global(a) {
    color: var(--accent);
    text-decoration: underline;
    text-decoration-thickness: 1px;
    text-underline-offset: 2px;
  }
  .prose-chat :global(a:hover) { color: var(--accent-hover); }
  .prose-chat :global(ul), .prose-chat :global(ol) {
    margin: 0.6em 0;
    padding-left: 1.2em;
  }
  .prose-chat :global(li) { margin: 0.2em 0; }
  .prose-chat :global(hr) {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1em 0;
  }
  .prose-chat :global(blockquote) {
    border-left: 3px solid var(--accent);
    padding-left: 12px;
    color: var(--text-muted);
    margin: 0.6em 0;
  }
  .prose-chat :global(h1), .prose-chat :global(h2), .prose-chat :global(h3) {
    font-weight: 600;
    margin: 1em 0 0.4em;
    color: var(--text);
  }
  .prose-chat :global(h1) { font-size: 18px; }
  .prose-chat :global(h2) { font-size: 16px; }
  .prose-chat :global(h3) { font-size: 15px; }
  .prose-chat :global(h1:first-child),
  .prose-chat :global(h2:first-child),
  .prose-chat :global(h3:first-child) { margin-top: 0; }

  .prose-chat :global(code) {
    background: var(--surface-2);
    color: var(--accent-ink);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 13px;
    border: none;
  }
  .prose-chat :global(pre) {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    padding: 14px 16px;
    font-family: var(--font-mono);
    font-size: 13px;
    overflow-x: auto;
    margin: 0.8em 0;
    position: relative;
  }
  .prose-chat :global(pre code) {
    background: none;
    border: none;
    padding: 0;
    color: var(--text);
    font-size: 13px;
  }

  /* Tables */
  .prose-chat :global(table) {
    border-collapse: collapse;
    width: 100%;
    margin: 0.8em 0;
    font-size: 14px;
    display: block;
    overflow-x: auto;
  }
  .prose-chat :global(th) {
    text-align: left;
    color: var(--text-muted);
    font-weight: 500;
    padding: 8px;
    border-bottom: 1px solid var(--border);
    background: transparent;
  }
  .prose-chat :global(td) {
    padding: 8px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
  }

  /* Collapsible code block (from markdown.ts) */
  .prose-chat :global(details.code-collapse) {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    margin: 0.8em 0;
    overflow: hidden;
  }
  .prose-chat :global(details.code-collapse summary.code-collapse-header) {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
    list-style: none;
    user-select: none;
  }
  .prose-chat :global(details.code-collapse summary::-webkit-details-marker) { display: none; }
  .prose-chat :global(details.code-collapse[open] summary.code-collapse-header) { border-bottom: 1px solid var(--border); }
  .prose-chat :global(.code-collapse-arrow) {
    font-size: 9px;
    color: var(--text-faint);
    transition: transform 0.15s;
  }
  .prose-chat :global(details.code-collapse[open] .code-collapse-arrow) { transform: rotate(90deg); }
  .prose-chat :global(.code-collapse-lang) {
    font-weight: 600;
    color: var(--text);
    text-transform: lowercase;
  }
  .prose-chat :global(.code-collapse-info) {
    color: var(--text-faint);
    margin-right: auto;
  }
  .prose-chat :global(.code-collapse-copy) {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-family: var(--font-sans);
    font-size: 11px;
    font-weight: 500;
    padding: 3px 8px;
    border-radius: var(--r-sm);
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s, background-color 0.15s;
  }
  .prose-chat :global(details.code-collapse:hover .code-collapse-copy) { opacity: 1; }
  .prose-chat :global(.code-collapse-copy:hover) { background: var(--surface); color: var(--text); }
  .prose-chat :global(.code-collapse-pre) {
    background: var(--surface-2);
    margin: 0;
    padding: 14px 16px;
    border: none;
    border-radius: 0;
    font-family: var(--font-mono);
    font-size: 13px;
    overflow-x: auto;
  }
  .prose-chat :global(.code-collapse-pre code) {
    background: none;
    border: none;
    padding: 0;
    color: var(--text);
  }

  /* Citation chips */
  .cite-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }
  .cite-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-pill);
    padding: 4px 12px 4px 4px;
    cursor: pointer;
    transition: background-color 0.15s, border-color 0.15s;
    max-width: 260px;
  }
  .cite-chip:hover {
    background: var(--surface);
    border-color: var(--border-strong);
  }
  .cite-thumb-img {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
  }
  .cite-info {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    min-width: 0;
    overflow: hidden;
  }
  .cite-company {
    font-size: 12px;
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 180px;
  }
  .cite-folder {
    font-size: 11px;
    color: var(--text-faint);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 180px;
  }

  /* Message actions row */
  .msg-actions {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-top: 10px;
    padding-top: 6px;
  }
  .ghost-icon {
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--text-muted);
    border-radius: var(--r-sm);
    cursor: pointer;
    transition: background-color 0.15s, color 0.15s;
  }
  .ghost-icon:hover:not(:disabled) {
    background: var(--surface-2);
    color: var(--text);
  }
  .ghost-icon:disabled { cursor: default; }
  .ghost-icon.fb-up, .ghost-icon.fb-down { color: var(--accent); }
  .ghost-icon.voice-active { color: var(--danger); background: var(--accent-soft); }

  /* Tool / RAG steps */
  .tool-block { width: 100%; }
  .tool-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 12px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-pill);
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 8px;
  }
  .tool-spinner {
    width: 12px;
    height: 12px;
    border: 1.8px solid var(--border-strong);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    display: inline-block;
  }
  .tool-spinner.small { width: 12px; height: 12px; }
  .tool-details {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    padding: 8px 12px;
    font-size: 13px;
    color: var(--text-muted);
  }
  .tool-details summary {
    cursor: pointer;
    font-size: 12px;
    color: var(--text-muted);
    list-style: none;
  }
  .tool-details summary::-webkit-details-marker { display: none; }
  .tool-details[open] summary { margin-bottom: 8px; }
  .tool-steps { display: flex; flex-direction: column; gap: 6px; }
  .tool-step { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); }
  .tool-done { color: var(--text-muted); }

  /* Lightbox */
  .lightbox {
    position: fixed;
    inset: 0;
    background: rgba(20, 19, 16, 0.86);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    gap: 12px;
    cursor: pointer;
  }
  .lightbox-img {
    max-width: 90vw;
    max-height: 80vh;
    object-fit: contain;
    border-radius: var(--r-md);
    box-shadow: var(--shadow-lg);
  }
  .lightbox-caption {
    color: #fff;
    font-size: 13px;
    font-weight: 500;
    font-family: var(--font-sans);
    opacity: 0.9;
  }
  .lightbox-close {
    position: absolute;
    top: 20px;
    right: 20px;
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.3);
    color: #fff;
    font-size: 20px;
    width: 36px;
    height: 36px;
    cursor: pointer;
    border-radius: var(--r-pill);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .lightbox-close:hover { background: rgba(255,255,255,0.2); }

  /* Input area */
  .input-wrap {
    flex-shrink: 0;
    background: var(--bg);
    padding: 8px 16px 12px;
  }
  .input-shell {
    max-width: 760px;
    margin: 0 auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--shadow-sm);
    padding: 10px 12px 8px;
    transition: border-color 0.15s, box-shadow 0.15s;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .input-shell:focus-within {
    border-color: var(--border-strong);
    box-shadow: var(--shadow-md);
  }
  .input-shell textarea {
    width: 100%;
    background: transparent;
    border: none;
    outline: none;
    font-family: var(--font-sans);
    font-size: 15px;
    line-height: 1.5;
    color: var(--text);
    padding: 4px 4px 0;
    resize: none;
    min-height: 24px;
    max-height: 160px;
    box-sizing: border-box;
  }
  .input-shell textarea::placeholder { color: var(--text-faint); }
  .input-shell textarea:disabled { opacity: 0.5; }
  .input-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
  }
  .round-btn {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    border: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background-color 0.15s, opacity 0.15s;
    flex-shrink: 0;
  }
  .round-btn:hover:not(:disabled) { background: var(--accent-hover); }
  .round-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .round-btn.stop { background: var(--danger); }

  .footer-disclaimer {
    text-align: center;
    font-size: 11px;
    color: var(--text-faint);
    padding: 6px 16px 0;
  }
  @media (max-width: 767px) { .footer-disclaimer { display: none; } }

  /* Responsive */
  @media (max-width: 640px) {
    .history-panel { width: 220px; }
    .history-preview { max-width: 160px; }
    .bubble-user-c { max-width: 88%; font-size: 14px; }
    .bubble-assistant-c { font-size: 14px; padding: 12px 14px; }
    .messages-col { padding: 20px 14px 32px; }
    .empty-state { padding: 48px 12px 24px; }
    .empty-title { font-size: 20px; }
  }
</style>
