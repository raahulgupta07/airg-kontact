<script>
  import { goto } from '$app/navigation';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PullRefresh from '$lib/components/PullRefresh.svelte';

  let batches = $state([]);
  let loading = $state(true);
  let processing = $state(false);
  let activeBatch = $state(null);
  let logs = $state([]);
  let pollTimer = $state(null);
  let errorItems = $state({});
  let expandedErrors = $state({});
  let retrying = $state(false);
  let showTerminal = $state(false);
  let expandedBatch = $state(null);
  let expandedData = $state([]);

  // Lightbox — supports PDF page navigation by grouping _pageN siblings
  let lightboxDoc = $state(null);
  let lightboxSiblings = $state([]);
  let lightboxIdx = $state(0);

  function _pdfGroupKey(fname) {
    // Returns base name without _pageN.jpg suffix, or null if not a PDF page
    if (!fname) return null;
    const m = fname.match(/^(.*?)_page\d+\.(jpe?g|png)$/i);
    return m ? m[1] : null;
  }
  function _pageNum(fname) {
    const m = (fname || '').match(/_page(\d+)\./i);
    return m ? parseInt(m[1], 10) : 0;
  }

  function openLightbox(doc) {
    // Group sibling pages from same PDF
    const grpKey = _pdfGroupKey(doc.source_file);
    if (grpKey) {
      lightboxSiblings = expandedData
        .filter(d => _pdfGroupKey(d.source_file) === grpKey)
        .sort((a, b) => _pageNum(a.source_file) - _pageNum(b.source_file));
      lightboxIdx = lightboxSiblings.findIndex(d => d.uuid === doc.uuid);
      if (lightboxIdx < 0) lightboxIdx = 0;
    } else {
      lightboxSiblings = [doc];
      lightboxIdx = 0;
    }
    lightboxDoc = lightboxSiblings[lightboxIdx];
  }
  function closeLightbox() { lightboxDoc = null; lightboxSiblings = []; }
  function lbNext() {
    if (lightboxIdx < lightboxSiblings.length - 1) {
      lightboxIdx += 1;
      lightboxDoc = lightboxSiblings[lightboxIdx];
    }
  }
  function lbPrev() {
    if (lightboxIdx > 0) {
      lightboxIdx -= 1;
      lightboxDoc = lightboxSiblings[lightboxIdx];
    }
  }
  function onLightboxKey(e) {
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowRight') lbNext();
    else if (e.key === 'ArrowLeft') lbPrev();
  }
  let toast = $state(null);

  const api = {
    async getQueueBatches() { const r = await fetch('/api/queue/batches', { credentials: 'include' }); return r.json(); },
    async processQueue(bid = null) { const r = await fetch(bid ? `/api/process/background?batch_id=${bid}` : '/api/process/background', { method: 'POST', credentials: 'include' }); if (!r.ok) { const e = await r.json().catch(() => ({ detail: 'Failed' })); throw new Error(e.detail); } return r.json(); },
    async getQueueStatus(bid = null) { const r = await fetch(bid ? `/api/queue?batch_id=${bid}` : '/api/queue', { credentials: 'include' }); return r.json(); },
    async getQueueErrors(bid = null) { const r = await fetch(bid ? `/api/queue/errors?batch_id=${bid}` : '/api/queue/errors', { credentials: 'include' }); return r.ok ? r.json() : []; },
    async retryItem(qid) { const r = await fetch(`/api/queue/retry/${qid}`, { method: 'POST', credentials: 'include' }); if (!r.ok) throw new Error('Retry failed'); return r.json(); },
    async deleteBatch(bid) { const r = await fetch(`/api/batch/${bid}`, { method: 'DELETE', credentials: 'include' }); if (!r.ok) { const e = await r.json().catch(() => ({ detail: 'Failed' })); throw new Error(e.detail); } return r.json(); }
  };

  async function fetchBatches() { loading = true; try { batches = await api.getQueueBatches(); } catch (e) { log(`ERROR: ${e.message}`); } finally { loading = false; } }
  function log(msg) { const ts = new Date().toLocaleTimeString('en-US', { hour12: false }); logs = [...logs, `[${ts}] ${msg}`]; showTerminal = true; }

  async function processAll() {
    processing = true; activeBatch = null; log('Processing all pending...');
    try {
      const result = await api.processQueue();
      if (result.status === 'complete' || result.pending === 0) {
        log('All items already processed.'); await fetchBatches(); processing = false;
      } else { startPolling(); }
    } catch (e) { log(`ERROR: ${e.message}`); processing = false; }
  }
  async function processBatch(bid) {
    processing = true; activeBatch = bid; log(`Processing [${bid}]...`);
    try {
      const result = await api.processQueue(bid);
      if (result.status === 'complete' || result.pending === 0) {
        log('Already processed.'); await fetchBatches(); processing = false; activeBatch = null;
      } else { startPolling(bid); }
    } catch (e) { log(`ERROR: ${e.message}`); processing = false; activeBatch = null; }
  }

  function showToast(message) {
    toast = message;
    setTimeout(() => { toast = null; }, 3000);
  }

  async function deleteBatch(bid) {
    if (!confirm('Delete batch?')) return;
    try { await api.deleteBatch(bid); log(`Deleted batch [${bid}]`); await fetchBatches(); } catch (e) { log(`ERROR: ${e.message}`); }
  }

  function startPolling(bid = null) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      const status = await api.getQueueStatus(bid);
      const items = Array.isArray(status) ? status : [status];
      const pending = items.filter(i => i.status === 'pending').length;
      const doneCount = items.filter(i=>i.status==='done').length;
      log(`${doneCount} done, ${pending} pending`);
      await fetchBatches();
      if (pending === 0) {
        clearInterval(pollTimer); pollTimer = null; log('Complete.'); processing = false;
        const batchName = activeBatch || 'All';
        const totalDone = status.done ?? doneCount;
        showToast(`Batch ${batchName} processed. ${totalDone} images done.`);
        activeBatch = null;
      }
    }, 3000);
  }

  async function toggleErrors(bid) {
    if (expandedErrors[bid]) { expandedErrors = { ...expandedErrors, [bid]: false }; return; }
    const items = await api.getQueueErrors(bid);
    errorItems = { ...errorItems, [bid]: items };
    expandedErrors = { ...expandedErrors, [bid]: true };
  }
  async function retryItem(qid, bid) { retrying = true; try { await api.retryItem(qid); log(`Retried #${qid}`); errorItems = { ...errorItems, [bid]: await api.getQueueErrors(bid) }; await fetchBatches(); } catch (e) { log(e.message); } finally { retrying = false; } }
  async function retryAllErrors(bid) { retrying = true; for (const i of (errorItems[bid]||[])) { try { await api.retryItem(i.id); } catch(_){} } errorItems = { ...errorItems, [bid]: await api.getQueueErrors(bid) }; await fetchBatches(); retrying = false; }

  function tryParse(val) {
    if (!val) return val;
    if (typeof val === 'string') { try { return JSON.parse(val); } catch { return val; } }
    return val;
  }

  async function toggleExpand(bid) {
    if (expandedBatch === bid) { expandedBatch = null; expandedData = []; return; }
    try {
      const r = await fetch(`/api/data?folder=${bid}`, { credentials: 'include' });
      const raw = await r.json();
      expandedData = raw.map(d => ({
        ...d,
        products: tryParse(d.products) || [],
        contact: tryParse(d.contact) || {},
        key_info: tryParse(d.key_info) || []
      }));
    } catch (e) {
      expandedData = [];
      log(`ERROR loading data: ${e.message}`);
    }
    expandedBatch = bid;
  }

  $effect(() => { fetchBatches(); return () => { if (pollTimer) clearInterval(pollTimer); if (autoPollTimer) clearInterval(autoPollTimer); }; });

  // Auto-poll while any batch has pending > 0
  let autoPollTimer = $state(null);
  $effect(() => {
    const hasPending = batches.some(b => (b.pending || 0) > 0);
    if (hasPending && !autoPollTimer) {
      autoPollTimer = setInterval(() => { fetchBatches(); }, 2500);
    } else if (!hasPending && autoPollTimer) {
      clearInterval(autoPollTimer); autoPollTimer = null;
    }
  });

  function batchPct(b) {
    if (!b || !b.total) return 0;
    return Math.round(((b.done || 0) / b.total) * 100);
  }
  function batchStatus(b) {
    if (b.errors > 0 && b.pending === 0) return 'errors';
    if (b.pending > 0) return 'processing';
    return 'done';
  }
  function totalPending() { return batches.reduce((s, b) => s + (b.pending ?? 0), 0); }
</script>

<svelte:head><title>Queue | KONTACT</title></svelte:head>

<div class="q-page">
  {#if toast}
    <div class="q-toast">{toast}</div>
  {/if}
  <div class="q-header">
    <div class="q-title-row">
      <h1 class="page-title">Queue</h1>
      <span class="q-count">{batches.length} batches · {batches.reduce((s,b) => s + (b.done??0) + (b.pending??0) + (b.errors??0), 0)} images</span>
    </div>
    <div class="q-actions">
      <button class="btn-ghost" onclick={fetchBatches} disabled={loading}>{loading ? '...' : 'Refresh'}</button>
      {#if totalPending() > 0}
        <button class="send-btn" onclick={processAll} disabled={processing}>{processing ? 'Processing...' : `Process all (${totalPending()})`}</button>
      {/if}
    </div>
  </div>

  {#if loading && batches.length === 0}
    <Skeleton kind="card" rows={4} />
  {:else if batches.length === 0}
    <EmptyState
      icon="📦"
      title="No batches yet"
      hint="Photos you upload appear here. Each upload becomes a batch you can track from queue → extracted → searchable."
      cta="Upload your first batch"
      oncta={() => goto('/upload')}
    />
  {:else}
    <div class="q-list">
      {#each batches as batch (batch.batch_id)}
        {@const total = (batch.done ?? 0) + (batch.pending ?? 0) + (batch.errors ?? 0)}
        {@const pct = total > 0 ? Math.round(((batch.done ?? 0) / total) * 100) : 0}
        <div class="card q-row">
          <div class="q-row-main">
            <div class="q-row-left">
              <span class="q-row-icon" class:q-complete={pct === 100}>
                {#if processing && activeBatch === batch.batch_id}
                  <span class="q-spinner"></span>
                {:else if pct === 100}
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M8 12l3 3 5-5"/></svg>
                {:else}
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>
                {/if}
              </span>
              <div class="q-row-info">
                <span class="q-row-name">{batch.batch_id}</span>
                <span class="q-row-detail">
                  {total} images · {pct}% done
                  {#if batch.owner_name} · by <strong>{batch.owner_name}</strong>{/if}
                  {#if batch.trade_show} · <em>{batch.trade_show}</em>{/if}
                  {#if batch.created} · {new Date(batch.created.replace(' ', 'T') + 'Z').toLocaleString()}{/if}
                </span>
                <div class="q-progress" class:processing={batch.pending > 0} class:has-errors={batch.errors > 0 && batch.pending === 0}>
                  <div class="q-progress-fill" style="width:{pct}%"></div>
                </div>
              </div>
            </div>
            <div class="q-row-right">
              <div class="q-tags">
                {#if (batch.done ?? 0) > 0}<span class="chip chip-done">{batch.done} done</span>{/if}
                {#if (batch.pending ?? 0) > 0}<span class="chip">{batch.pending} pending</span>{/if}
                {#if (batch.errors ?? 0) > 0}<span class="chip chip-error">{batch.errors} errors</span>{/if}
              </div>
              <div class="q-row-btns">
                {#if (batch.pending ?? 0) > 0}
                  <button class="q-btn-sm send-btn" onclick={() => processBatch(batch.batch_id)} disabled={processing}>Process</button>
                {/if}
                {#if (batch.errors ?? 0) > 0}
                  <button class="q-btn-sm btn-danger" onclick={() => toggleErrors(batch.batch_id)}>{expandedErrors[batch.batch_id] ? 'Hide' : 'Errors'}</button>
                {/if}
                <button class="q-btn-sm btn-ghost" onclick={() => toggleExpand(batch.batch_id)}>{expandedBatch === batch.batch_id ? 'Collapse' : 'Expand'}</button>
                <button class="q-btn-sm btn-ghost q-icon-btn" onclick={() => deleteBatch(batch.batch_id)} title="Delete batch" aria-label="delete">&times;</button>
              </div>
            </div>
          </div>
          <div class="q-progress"><div class="q-progress-fill" style="width:{pct}%"></div></div>

          {#if expandedErrors[batch.batch_id] && errorItems[batch.batch_id]?.length}
            <div class="q-errors">
              <div class="q-errors-head">
                <span class="chip chip-error">Failed</span>
                <button class="q-btn-sm btn-danger" onclick={() => retryAllErrors(batch.batch_id)} disabled={retrying}>Retry all</button>
              </div>
              {#each errorItems[batch.batch_id] as item}
                <div class="q-error-row">
                  <span class="q-error-name">{item.file_name}</span>
                  <span class="q-error-msg">{item.error || 'Unknown'}</span>
                  <button class="q-btn-sm btn-danger" onclick={() => retryItem(item.id, batch.batch_id)} disabled={retrying}>Retry</button>
                </div>
              {/each}
            </div>
          {/if}

          {#if expandedBatch === batch.batch_id}
            <div class="q-expand">
              {#if expandedData.length === 0}
                <div class="q-expand-empty">No documents found for this batch.</div>
              {:else}
                {#each expandedData as doc, i}
                  <div class="q-doc-row">
                    <button
                      type="button"
                      class="q-doc-thumb"
                      onclick={() => openLightbox(doc)}
                      aria-label={`Open ${doc.source_file}`}
                    >
                      <div class="q-thumb-skeleton"></div>
                      <img
                        src={`/api/thumb/${doc.folder}/${doc.source_file}?w=256`}
                        alt={doc.source_file}
                        loading="lazy"
                        decoding="async"
                        onload={(e) => { e.target.style.opacity = '1'; e.target.previousElementSibling.style.display = 'none'; }}
                        onerror={(e) => { e.target.style.display = 'none'; e.target.previousElementSibling.style.background = 'var(--surface-2)'; }}
                      />
                    </button>
                    <div class="q-doc-meta">
                      <div class="q-doc-top">
                        <span class="q-doc-filename">{doc.source_file}</span>
                        {#if doc.image_type}
                          <span class="chip">{doc.image_type}</span>
                        {/if}
                      </div>
                      {#if doc.title}
                        <div class="q-doc-title">{doc.title}</div>
                      {/if}
                      {#if doc.products && doc.products.length > 0}
                        <div class="q-doc-products">
                          {doc.products.slice(0, 5).map(p => typeof p === 'string' ? p : (p.name || p.product_name || '')).filter(Boolean).join(', ')}
                          {#if doc.products.length > 5}
                            <span class="q-doc-more">+{doc.products.length - 5} more</span>
                          {/if}
                        </div>
                      {/if}
                      {#if doc.company}
                        <div class="q-doc-company">{typeof doc.company === 'string' ? doc.company : (doc.company.name || doc.company.company_name || '')}</div>
                      {/if}
                      {#if doc.contact}
                        <div class="q-doc-contact">
                          {#if doc.contact.phone}{doc.contact.phone}{/if}
                          {#if doc.contact.phone && doc.contact.email} · {/if}
                          {#if doc.contact.email}{doc.contact.email}{/if}
                        </div>
                      {/if}
                      <div class="q-doc-foot">
                        {#if doc.owner_name}by {doc.owner_name}{/if}
                        {#if doc.created_at}
                          {#if doc.owner_name} · {/if}{new Date(doc.created_at).toLocaleString()}
                        {/if}
                      </div>
                    </div>
                  </div>
                  {#if i < expandedData.length - 1}
                    <div class="q-doc-sep"></div>
                  {/if}
                {/each}
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  {#if logs.length > 0}
    <div class="q-terminal card">
      <div class="q-terminal-head">
        <span class="q-terminal-title">terminal</span>
        <button class="q-terminal-clear" onclick={() => { logs = []; showTerminal = false; }}>Clear</button>
      </div>
      <div class="q-terminal-body">
        {#each logs.slice(-8) as line}
          <div class="q-terminal-line">{line}</div>
        {/each}
        {#if processing}<div class="q-terminal-line q-blink">_ processing...</div>{/if}
      </div>
    </div>
  {/if}
</div>

<svelte:window onkeydown={onLightboxKey} />

{#if lightboxDoc}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="lb-backdrop" onclick={closeLightbox}>
    <div class="lb-modal" onclick={(e) => e.stopPropagation()}>
      <button class="lb-close" onclick={closeLightbox} aria-label="Close">×</button>
      {#if lightboxSiblings.length > 1}
        <div class="lb-pager">
          <button class="lb-nav" onclick={lbPrev} disabled={lightboxIdx === 0} aria-label="Previous page">◀</button>
          <span class="lb-page-info">Page {lightboxIdx + 1} of {lightboxSiblings.length}</span>
          <button class="lb-nav" onclick={lbNext} disabled={lightboxIdx === lightboxSiblings.length - 1} aria-label="Next page">▶</button>
        </div>
      {/if}
      <img
        class="lb-img"
        src={`/api/image/${lightboxDoc.folder}/${lightboxDoc.source_file}`}
        alt={lightboxDoc.source_file}
      />
      <div class="lb-meta">
        <h3 class="lb-title">{lightboxDoc.source_file}</h3>
        <div class="lb-row">
          {#if lightboxDoc.image_type}<span class="chip">{lightboxDoc.image_type}</span>{/if}
          {#if lightboxDoc.company}<span class="lb-tag">{lightboxDoc.company}</span>{/if}
          {#if lightboxDoc.trade_show}<span class="lb-tag lb-show">{lightboxDoc.trade_show}</span>{/if}
        </div>
        {#if lightboxDoc.title}<p class="lb-desc">{lightboxDoc.title}</p>{/if}
        {#if lightboxDoc.contact}
          <div class="lb-contact">
            {#if lightboxDoc.contact.person}<div><b>{lightboxDoc.contact.person}</b></div>{/if}
            {#if lightboxDoc.contact.phone}<div>📞 {lightboxDoc.contact.phone}</div>{/if}
            {#if lightboxDoc.contact.email}<div>✉ {lightboxDoc.contact.email}</div>{/if}
            {#if lightboxDoc.contact.address}<div>📍 {lightboxDoc.contact.address}</div>{/if}
            {#if lightboxDoc.contact.website}<div>🌐 {lightboxDoc.contact.website}</div>{/if}
          </div>
        {/if}
        {#if lightboxDoc.products && lightboxDoc.products.length}
          <div class="lb-products">
            <div class="lb-section-h">Products ({lightboxDoc.products.length})</div>
            {#each lightboxDoc.products.slice(0, 8) as p}
              <div class="lb-prod">
                {typeof p === 'string' ? p : (p.name || p.product_name || '')}
                {#if p && typeof p === 'object' && p.price}<span class="lb-price">{p.price}</span>{/if}
              </div>
            {/each}
          </div>
        {/if}
        {#if lightboxDoc.gps_lat}
          <div class="lb-meta-row">GPS: {lightboxDoc.gps_lat}, {lightboxDoc.gps_lng} {#if lightboxDoc.city}— {lightboxDoc.city}, {lightboxDoc.country}{/if}</div>
        {/if}
        {#if lightboxDoc.camera_make}
          <div class="lb-meta-row">Camera: {lightboxDoc.camera_make} {lightboxDoc.camera_model || ''}</div>
        {/if}
        {#if lightboxDoc.date_taken}
          <div class="lb-meta-row">Taken: {lightboxDoc.date_taken}</div>
        {/if}
        {#if lightboxDoc.created_at}
          <div class="lb-meta-row">Uploaded: {new Date(lightboxDoc.created_at).toLocaleString()}</div>
        {/if}
        {#if lightboxDoc.owner_name}
          <div class="lb-meta-row">By: {lightboxDoc.owner_name}</div>
        {/if}
        {#if lightboxDoc.blur_score != null}
          <div class="lb-meta-row">Sharpness score: {lightboxDoc.blur_score.toFixed(1)} {lightboxDoc.is_blurry ? '(blurry)' : '(sharp)'}</div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .q-page { width:100%; padding:16px; font-family: var(--font-sans); max-width: 920px; margin: 0 auto; }

  .q-header { display:flex; justify-content:space-between; align-items:flex-end; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
  .q-title-row { display:flex; flex-direction:column; gap:4px; }
  .page-title { margin:0; font-size:24px; font-weight:600; color:var(--text); letter-spacing:0; }
  .q-count { font-size:13px; color:var(--text-muted); }
  .q-actions { display:flex; gap:8px; }

  .q-btn-sm { padding: 6px 12px; min-height: 30px; font-size: 12px; }
  .q-icon-btn { font-size: 16px; padding: 6px 10px; }

  .q-list { display:flex; flex-direction:column; gap:10px; }
  .q-row { padding:0; overflow:hidden; }

  .q-row-main { display:flex; justify-content:space-between; align-items:center; padding:14px 16px; gap:12px; }
  .q-row-left { display:flex; align-items:center; gap:12px; min-width:0; }
  .q-row-icon { flex-shrink:0; width:20px; height:20px; display:flex; align-items:center; justify-content:center; }
  .q-row-info { display:flex; flex-direction:column; gap:4px; min-width:0; flex:1; }
  .q-progress {
    width: 100%;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 4px;
  }
  .q-progress-fill {
    height: 100%;
    background: var(--success, #22c55e);
    transition: width 0.3s ease;
  }
  .q-progress.processing .q-progress-fill { background: var(--accent); }
  .q-progress.has-errors .q-progress-fill { background: var(--danger); }
  @keyframes q-stripes {
    0% { background-position: 0 0; }
    100% { background-position: 14px 0; }
  }
  .q-progress.processing .q-progress-fill {
    background-image: linear-gradient(45deg, rgba(255,255,255,0.18) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.18) 50%, rgba(255,255,255,0.18) 75%, transparent 75%, transparent);
    background-size: 14px 14px;
    animation: q-stripes 0.6s linear infinite;
  }
  .q-row-name { font-weight:600; font-size:14px; color:var(--text); font-family: var(--font-mono); }
  .q-row-detail { font-size:12px; color:var(--text-muted); }

  .q-row-right { display:flex; align-items:center; gap:10px; flex-shrink:0; flex-wrap:wrap; }
  .q-tags { display:flex; gap:4px; flex-wrap:wrap; }
  .q-row-btns { display:flex; gap:6px; flex-wrap:wrap; }

  .chip-done { background: rgba(90,143,61,0.15); color: var(--success); }
  .chip-error { background: rgba(181,69,61,0.12); color: var(--danger); }

  .q-progress { height:3px; background:var(--surface-2); }
  .q-progress-fill { height:100%; background:var(--accent); transition:width 0.4s ease; }

  .q-spinner { width:14px; height:14px; border:2px solid var(--border); border-top-color:var(--accent); border-radius:50%; animation:qspin 0.7s linear infinite; display:block; }
  @keyframes qspin { to { transform:rotate(360deg); } }

  .q-errors { padding:10px 16px; background:rgba(181,69,61,0.05); border-top:1px solid var(--border); }
  .q-errors-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  .q-error-row { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--border); font-size:12px; }
  .q-error-row:last-child { border-bottom: none; }
  .q-error-name { font-family:var(--font-mono); font-weight:500; font-size:12px; min-width:0; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .q-error-msg { font-size:11px; color:var(--danger); flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; word-break:break-word; }
  @media (max-width:640px) { .q-error-msg { white-space:normal; } .q-error-row { flex-wrap:wrap; } }

  .q-expand { border-top:1px solid var(--border); padding:14px 16px; background:var(--surface-2); }
  .q-expand-empty { font-size:13px; color:var(--text-muted); padding:8px 0; }

  .q-doc-row { display:flex; gap:12px; align-items:flex-start; padding:10px 0; }
  .q-doc-thumb { flex-shrink:0; width:56px; height:56px; overflow:hidden; border:1px solid var(--border); border-radius: var(--r-sm); position:relative; padding:0; background:none; cursor:zoom-in; transition: border-color 0.15s, transform 0.15s; }
  .q-doc-thumb:hover { border-color: var(--accent); transform: scale(1.04); }
  .q-doc-thumb img { width:100%; height:100%; object-fit:cover; display:block; opacity:0; transition:opacity 0.2s; position:relative; z-index:1; }
  .q-thumb-skeleton { position:absolute; inset:0; background:var(--surface-2); animation:q-pulse 1.2s ease-in-out infinite; z-index:0; }
  @keyframes q-pulse { 0%,100% { opacity:0.4; } 50% { opacity:1; } }

  .q-doc-meta { flex:1; min-width:0; display:flex; flex-direction:column; gap:3px; }
  .q-doc-top { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
  .q-doc-filename { font-family:var(--font-mono); font-weight:500; font-size:13px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .q-doc-title { font-size:13px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .q-doc-products { font-size:12px; color:var(--text-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .q-doc-more { color:var(--accent); margin-left:4px; }
  .q-doc-company { font-size:12px; color:var(--text-muted); font-weight:500; }
  .q-doc-contact { font-size:11px; color:var(--text-faint); font-family:var(--font-mono); }
  .q-doc-foot { font-size:11px; color:var(--text-faint); margin-top:4px; }

  .q-doc-sep { border-bottom:1px solid var(--border); margin:0; }

  .q-terminal { margin-top:16px; padding: 0; overflow: hidden; }
  .q-terminal-head { display:flex; justify-content:space-between; align-items:center; padding:8px 14px; background:var(--surface-2); border-bottom: 1px solid var(--border); }
  .q-terminal-title { font-size:12px; font-weight:500; color:var(--text-muted); font-family:var(--font-mono); }
  .q-terminal-clear { background:none; border:none; color:var(--text-muted); font-family:inherit; font-size:12px; cursor:pointer; }
  .q-terminal-clear:hover { color:var(--text); }
  .q-terminal-body { background:var(--surface-2); color:var(--text); font-family:var(--font-mono); font-size:12px; line-height:1.6; padding:10px 14px; max-height:160px; overflow-y:auto; }
  .q-terminal-line { white-space:pre-wrap; color: var(--text-muted); }
  .q-blink { animation:qblink 1s step-end infinite; color: var(--accent); }
  @keyframes qblink { 50% { opacity:0; } }

  .q-toast { position:fixed; bottom:24px; right:24px; background:var(--accent); color:#fff; padding:10px 16px; font-size:13px; font-weight:500; z-index:9999; border-radius:var(--r-md); box-shadow:var(--shadow-md); animation:q-toast-in 0.25s ease-out; }
  @keyframes q-toast-in { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }

  .q-empty { display:flex; flex-direction:column; align-items:center; gap:12px; padding:48px 16px; text-align:center; color:var(--text-muted); }

  @media (max-width:640px) {
    .q-row-main { flex-direction:column; align-items:stretch; gap:10px; }
    .q-row-right { flex-wrap:wrap; justify-content: space-between; }
    .q-doc-row { flex-direction:column; gap:6px; }
    .q-doc-thumb { width:48px; height:48px; }
  }

  /* Lightbox */
  .lb-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.72);
    display: flex; align-items: center; justify-content: center;
    z-index: 200; padding: 16px;
    animation: lb-fade 0.18s ease;
  }
  @keyframes lb-fade { from { opacity: 0; } to { opacity: 1; } }
  .lb-modal {
    background: var(--surface);
    border-radius: var(--r-lg, 14px);
    max-width: 960px; width: 100%; max-height: 92vh;
    display: grid; grid-template-columns: minmax(280px, 1.2fr) minmax(280px, 1fr);
    overflow: hidden;
    box-shadow: 0 24px 80px rgba(0,0,0,0.5);
    position: relative;
  }
  .lb-img {
    width: 100%; height: 100%; max-height: 92vh;
    object-fit: contain; background: #000;
    display: block;
  }
  .lb-close {
    position: absolute; top: 10px; right: 10px;
    background: rgba(0,0,0,0.55); color: #fff;
    border: none; width: 36px; height: 36px; border-radius: 50%;
    font-size: 22px; line-height: 1; cursor: pointer; z-index: 2;
  }
  .lb-meta {
    padding: 18px 22px; overflow-y: auto;
    display: flex; flex-direction: column; gap: 10px;
    font-size: 14px; color: var(--text);
  }
  .lb-title {
    font-size: 16px; font-weight: 600; margin: 0;
    word-break: break-all;
  }
  .lb-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .lb-tag {
    font-size: 12px; padding: 3px 8px;
    background: var(--surface-2, var(--surface));
    border: 1px solid var(--border);
    border-radius: 999px; color: var(--text-muted);
  }
  .lb-show { background: var(--accent-soft, rgba(201, 100, 66, 0.12)); color: var(--accent); border-color: var(--accent); }
  .lb-desc { margin: 0; color: var(--text-muted); }
  .lb-contact {
    display: flex; flex-direction: column; gap: 4px;
    padding: 8px 10px;
    background: var(--surface-2, rgba(0,0,0,0.03));
    border-radius: var(--r-md, 8px);
    font-size: 13px;
  }
  .lb-section-h {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    color: var(--text-muted); letter-spacing: 0.04em; margin-bottom: 4px;
  }
  .lb-products { display: flex; flex-direction: column; gap: 4px; }
  .lb-prod { font-size: 13px; display: flex; justify-content: space-between; gap: 8px; }
  .lb-price { color: var(--accent); font-weight: 600; }
  .lb-meta-row { font-size: 12px; color: var(--text-muted); }

  @media (max-width: 720px) {
    .lb-modal { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
    .lb-img { max-height: 50vh; }
  }
  .lb-pager {
    position: absolute;
    top: 10px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 3;
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgba(0,0,0,0.55);
    color: white;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 13px;
  }
  .lb-nav {
    background: none;
    border: none;
    color: white;
    font-size: 16px;
    cursor: pointer;
    padding: 2px 6px;
  }
  .lb-nav:disabled { opacity: 0.3; cursor: not-allowed; }
  .lb-page-info { font-weight: 600; font-size: 12px; }
</style>
