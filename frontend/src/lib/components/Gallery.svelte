<script lang="ts">
  let { documents = [] } = $props();
  const API = '';

  let lightboxDoc = $state<any>(null);
  let lbIdx = $state(0);
  let selected = $state<Record<string, boolean>>({});
  let selectMode = $state(false);
  let groupMode = $state<'none' | 'category' | 'company' | 'show'>('none');

  function imageDocs() {
    return documents.filter((d: any) => d.source_file && d.folder);
  }

  function docCategory(d: any): string {
    let prods = d.products;
    if (typeof prods === 'string') {
      try { prods = JSON.parse(prods); } catch { prods = []; }
    }
    if (Array.isArray(prods) && prods.length > 0) {
      const c = (prods[0] && prods[0].category) ? String(prods[0].category).trim() : '';
      if (c) return c;
    }
    return d.image_type || 'Uncategorized';
  }

  function groupKey(d: any): string {
    if (groupMode === 'category') return docCategory(d);
    if (groupMode === 'company') return (d.company || '').trim() || 'Unknown';
    if (groupMode === 'show') return (d.trade_show || '').trim() || 'No trade show';
    return '';
  }

  function groupedDocs(): Array<{ key: string; docs: any[] }> {
    const list = imageDocs();
    if (groupMode === 'none') return [{ key: '', docs: list }];
    const map: Record<string, any[]> = {};
    for (const d of list) {
      const k = groupKey(d);
      (map[k] ||= []).push(d);
    }
    return Object.keys(map).sort().map(k => ({ key: k, docs: map[k] }));
  }

  let aiBusy = $state(false);
  async function autoCategorize() {
    if (aiBusy) return;
    aiBusy = true;
    try {
      const r = await fetch('/api/categories/auto', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (r.ok) {
        groupMode = 'category';
        setTimeout(() => location.reload(), 800);
      }
    } finally {
      aiBusy = false;
    }
  }

  function openLightbox(doc: any, idx: number) {
    if (selectMode) {
      toggleSelect(doc);
      return;
    }
    lightboxDoc = doc;
    lbIdx = idx;
  }
  function closeLightbox() { lightboxDoc = null; }
  function lbNext() {
    const list = imageDocs();
    if (lbIdx < list.length - 1) { lbIdx += 1; lightboxDoc = list[lbIdx]; }
  }
  function lbPrev() {
    const list = imageDocs();
    if (lbIdx > 0) { lbIdx -= 1; lightboxDoc = list[lbIdx]; }
  }
  function onKey(e: KeyboardEvent) {
    if (!lightboxDoc) return;
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowRight') lbNext();
    else if (e.key === 'ArrowLeft') lbPrev();
  }

  function toggleSelect(doc: any) {
    const k = doc.uuid || `${doc.folder}/${doc.source_file}`;
    selected = { ...selected, [k]: !selected[k] };
  }
  function isSelected(doc: any): boolean {
    const k = doc.uuid || `${doc.folder}/${doc.source_file}`;
    return !!selected[k];
  }
  function selectAll() {
    const next: Record<string, boolean> = {};
    for (const d of imageDocs()) {
      const k = d.uuid || `${d.folder}/${d.source_file}`;
      next[k] = true;
    }
    selected = next;
  }
  function clearSelection() { selected = {}; }
  function selectedCount(): number {
    return Object.values(selected).filter(Boolean).length;
  }

  async function downloadSelected() {
    const list = imageDocs().filter(isSelected);
    if (!list.length) return;
    for (const d of list) {
      const url = `${API}/api/image/${d.folder}/${d.source_file}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = d.source_file;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Tiny delay to avoid browser blocking sequential downloads
      await new Promise(r => setTimeout(r, 120));
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="card">
  <div class="gallery-head">
    <h2>Image gallery <span class="muted">({imageDocs().length})</span></h2>
    <div class="actions">
      <div class="group-pills" role="tablist" aria-label="Group by">
        <button class="gp" class:active={groupMode === 'none'} onclick={() => groupMode = 'none'}>All</button>
        <button class="gp" class:active={groupMode === 'category'} onclick={() => groupMode = 'category'}>By category</button>
        <button class="gp" class:active={groupMode === 'company'} onclick={() => groupMode = 'company'}>By company</button>
        <button class="gp" class:active={groupMode === 'show'} onclick={() => groupMode = 'show'}>By show</button>
      </div>
      <button class="btn-ai xs" onclick={autoCategorize} disabled={aiBusy} title="Use AI to fill missing categories">
        {aiBusy ? '⏳' : '✨ AI categorize'}
      </button>
      <button class="btn-ghost xs" onclick={() => { selectMode = !selectMode; if (!selectMode) clearSelection(); }}>
        {selectMode ? 'Done' : 'Select'}
      </button>
      {#if selectMode}
        <button class="btn-ghost xs" onclick={selectAll}>All</button>
        <button class="btn-ghost xs" onclick={clearSelection}>None</button>
        <button class="btn-primary xs" onclick={downloadSelected} disabled={selectedCount() === 0}>
          Download {selectedCount() > 0 ? `(${selectedCount()})` : ''}
        </button>
      {/if}
    </div>
  </div>

  {#if documents.length === 0}
    <p class="muted">Loading images…</p>
  {:else}
    {#each groupedDocs() as group (group.key)}
      {#if groupMode !== 'none'}
        <div class="group-header">
          <span class="group-title">{group.key}</span>
          <span class="group-count">{group.docs.length}</span>
        </div>
      {/if}
      <div class="gallery-grid">
        {#each group.docs as doc, i (doc.uuid || doc.source_file)}
          <button
            type="button"
            class="gallery-thumb"
            class:selected={isSelected(doc)}
            onclick={() => openLightbox(doc, imageDocs().indexOf(doc))}
            title={doc.source_file}
          >
            <img
              src="{API}/api/thumb/{doc.folder}/{doc.source_file}?w=256"
              alt={doc.source_file}
              loading="lazy"
              decoding="async"
              onerror={(e) => {
                const t = e.currentTarget as HTMLImageElement;
                t.style.opacity = '0.15';
                t.dataset.failed = '1';
              }}
              onload={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '1'; }}
            />
            {#if groupMode === 'none'}
              {@const cat = docCategory(doc)}
              {#if cat && cat !== 'Uncategorized'}
                <span class="cat-tag">{cat}</span>
              {/if}
            {/if}
            {#if selectMode}
              <span class="check" class:on={isSelected(doc)}>{isSelected(doc) ? '✓' : ''}</span>
            {/if}
          </button>
        {/each}
      </div>
    {/each}
  {/if}
</div>

{#if lightboxDoc}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="lb-backdrop" onclick={closeLightbox}>
    <div class="lb-modal" onclick={(e) => e.stopPropagation()}>
      <button class="lb-close" onclick={closeLightbox} aria-label="Close">×</button>
      {#if imageDocs().length > 1}
        <button class="lb-arrow left" onclick={lbPrev} disabled={lbIdx === 0} aria-label="Prev">◀</button>
        <button class="lb-arrow right" onclick={lbNext} disabled={lbIdx === imageDocs().length - 1} aria-label="Next">▶</button>
        <span class="lb-counter">{lbIdx + 1} / {imageDocs().length}</span>
      {/if}
      <img class="lb-img" src="{API}/api/image/{lightboxDoc.folder}/{lightboxDoc.source_file}" alt={lightboxDoc.source_file} />
      <div class="lb-meta">
        <h3>{lightboxDoc.source_file}</h3>
        <div class="meta-row">
          {#if lightboxDoc.company}<span>{lightboxDoc.company}</span>{/if}
          {#if lightboxDoc.trade_show}<span class="show">{lightboxDoc.trade_show}</span>{/if}
        </div>
        {#if lightboxDoc.owner_name}<div class="m">By {lightboxDoc.owner_name}</div>{/if}
        {#if lightboxDoc.created_at}<div class="m">Uploaded {new Date(lightboxDoc.created_at).toLocaleString()}</div>{/if}
        <a class="lb-download" href="{API}/api/image/{lightboxDoc.folder}/{lightboxDoc.source_file}" download={lightboxDoc.source_file}>Download original</a>
      </div>
    </div>
  </div>
{/if}

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .gallery-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  .gallery-head h2 { margin: 0; font-size: 16px; font-weight: 600; }
  .actions { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .group-pills {
    display: inline-flex;
    background: var(--surface-2, rgba(0,0,0,0.04));
    border-radius: 999px;
    padding: 3px;
    gap: 0;
  }
  .gp {
    border: none; background: transparent;
    padding: 4px 10px;
    font-size: 12px;
    color: var(--text-muted);
    cursor: pointer;
    border-radius: 999px;
    font-family: inherit;
    transition: background 0.12s, color 0.12s;
  }
  .gp:hover { color: var(--text); }
  .gp.active { background: var(--accent); color: white; font-weight: 600; }
  .btn-ai.xs {
    background: var(--accent);
    color: white;
    border: 1px solid var(--accent);
    padding: 5px 10px;
    border-radius: var(--r-sm);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
  }
  .btn-ai.xs:disabled { opacity: 0.6; cursor: not-allowed; }
  .group-header {
    display: flex; align-items: center; gap: 8px;
    margin: 14px 0 8px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--border);
  }
  .group-title { font-weight: 600; font-size: 14px; color: var(--text); }
  .group-count {
    background: var(--accent-soft, rgba(201,100,66,0.1));
    color: var(--accent);
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
  }
  .cat-tag {
    position: absolute; bottom: 4px; left: 4px; right: 4px;
    background: rgba(0,0,0,0.75); color: white;
    padding: 2px 6px; border-radius: var(--r-sm);
    font-size: 10px; font-weight: 600;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .muted { color: var(--text-muted); font-size: 13px; font-weight: 400; }

  .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; }
  .gallery-thumb {
    position: relative;
    aspect-ratio: 1;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    background: var(--surface-2, var(--surface));
    cursor: zoom-in;
    transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s;
    padding: 0;
  }
  .gallery-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .gallery-thumb:hover { border-color: var(--accent); transform: scale(1.03); }
  .gallery-thumb.selected { border: 2px solid var(--accent); box-shadow: 0 0 0 2px var(--accent-soft, rgba(201,100,66,0.2)); }
  .check {
    position: absolute; top: 6px; right: 6px;
    width: 22px; height: 22px;
    border-radius: 50%;
    background: var(--surface); border: 1px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 700; color: var(--accent);
  }
  .check.on { background: var(--accent); border-color: var(--accent); color: white; }

  .btn-ghost.xs, .btn-primary.xs {
    padding: 5px 10px;
    border-radius: var(--r-sm);
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
  }
  .btn-ghost.xs { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-primary.xs { background: var(--accent); border: 1px solid var(--accent); color: white; font-weight: 600; }
  .btn-primary.xs:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Lightbox */
  .lb-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.78);
    display: flex; align-items: center; justify-content: center;
    z-index: 200; padding: 16px;
  }
  .lb-modal {
    position: relative;
    max-width: 95vw;
    max-height: 95vh;
    display: grid;
    grid-template-rows: 1fr auto;
    gap: 0;
    background: var(--surface);
    border-radius: var(--r-lg);
    overflow: hidden;
    box-shadow: 0 24px 64px rgba(0,0,0,0.5);
  }
  .lb-img {
    max-width: 95vw;
    max-height: calc(95vh - 140px);
    object-fit: contain;
    background: #000;
    display: block;
  }
  .lb-close {
    position: absolute; top: 8px; right: 8px;
    width: 36px; height: 36px;
    background: rgba(0,0,0,0.55);
    color: white; border: none;
    border-radius: 50%; font-size: 22px;
    cursor: pointer; z-index: 3;
  }
  .lb-arrow {
    position: absolute;
    top: 50%; transform: translateY(-50%);
    width: 44px; height: 44px;
    border-radius: 50%;
    background: rgba(0,0,0,0.55);
    color: white; border: none;
    font-size: 16px;
    cursor: pointer; z-index: 3;
  }
  .lb-arrow:disabled { opacity: 0.25; cursor: not-allowed; }
  .lb-arrow.left { left: 12px; }
  .lb-arrow.right { right: 12px; }
  .lb-counter {
    position: absolute; top: 12px; left: 50%;
    transform: translateX(-50%);
    background: rgba(0,0,0,0.55); color: white;
    padding: 4px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 600;
    z-index: 3;
  }
  .lb-meta { padding: 14px 18px; font-size: 13px; }
  .lb-meta h3 { margin: 0 0 6px; font-size: 15px; word-break: break-all; }
  .meta-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
  .meta-row span { background: var(--surface-2, rgba(0,0,0,0.04)); padding: 2px 8px; border-radius: 999px; font-size: 12px; }
  .meta-row .show { background: var(--accent-soft, rgba(201,100,66,0.12)); color: var(--accent); }
  .m { color: var(--text-muted); font-size: 12px; }
  .lb-download {
    display: inline-block;
    margin-top: 8px;
    padding: 6px 12px;
    background: var(--accent);
    color: white; text-decoration: none;
    border-radius: var(--r-sm);
    font-size: 12px; font-weight: 600;
  }
</style>
