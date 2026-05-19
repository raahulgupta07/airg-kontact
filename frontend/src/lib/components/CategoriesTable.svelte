<script lang="ts">
  let { categories = [], documents = [] } = $props();

  // Build category -> [documents]
  function docsByCategory() {
    const map: Record<string, any[]> = {};
    for (const d of documents) {
      let prods = d.products;
      if (typeof prods === 'string') {
        try { prods = JSON.parse(prods); } catch { prods = []; }
      }
      if (!Array.isArray(prods)) continue;
      for (const p of prods) {
        if (!p || typeof p !== 'object') continue;
        const cat = (p.category || 'Uncategorized').trim() || 'Uncategorized';
        if (!map[cat]) map[cat] = [];
        if (!map[cat].some(x => x.uuid === d.uuid || x.source_file === d.source_file)) {
          map[cat].push(d);
        }
      }
    }
    // Also include docs with image_type alone (no products extracted) under their image_type
    for (const d of documents) {
      if (!Array.isArray(d.products) || d.products.length === 0) {
        const t = d.image_type || 'other';
        if (!map[t]) map[t] = [];
        if (!map[t].some(x => x.uuid === d.uuid || x.source_file === d.source_file)) {
          map[t].push(d);
        }
      }
    }
    return map;
  }

  // Lightbox
  let lightboxDoc: any = $state(null);
  let lbList: any[] = $state([]);
  let lbIdx = $state(0);
  function openLB(list: any[], idx: number) {
    lbList = list;
    lbIdx = idx;
    lightboxDoc = list[idx];
  }
  function closeLB() { lightboxDoc = null; }
  function lbNext() { if (lbIdx < lbList.length - 1) { lbIdx++; lightboxDoc = lbList[lbIdx]; } }
  function lbPrev() { if (lbIdx > 0) { lbIdx--; lightboxDoc = lbList[lbIdx]; } }
  function onKey(e: KeyboardEvent) {
    if (!lightboxDoc) return;
    if (e.key === 'Escape') closeLB();
    if (e.key === 'ArrowRight') lbNext();
    if (e.key === 'ArrowLeft') lbPrev();
  }

  // Collapsible per-category
  let openCats: Record<string, boolean> = $state({});
  function toggleCat(c: string) { openCats = { ...openCats, [c]: !openCats[c] }; }
</script>

<svelte:window onkeydown={onKey} />

<div class="card table-card">
  <h2>Categories</h2>
  {#if categories.length === 0 && documents.length === 0}
    <p class="muted">No categories yet.</p>
  {:else}
    {@const byCat = docsByCategory()}
    <div class="cat-sections">
      {#each Object.keys(byCat).sort() as cat (cat)}
        {@const list = byCat[cat]}
        <div class="cat-section">
          <button class="cat-head" onclick={() => toggleCat(cat)}>
            <span class="cat-caret">{openCats[cat] ? '▾' : '▸'}</span>
            <span class="cat-name">{cat}</span>
            <span class="cat-count">{list.length} image{list.length !== 1 ? 's' : ''}</span>
          </button>
          {#if openCats[cat] !== false}
            <div class="cat-grid">
              {#each list as doc, i (doc.uuid || doc.source_file)}
                {#if doc.source_file && doc.folder}
                  <button
                    type="button"
                    class="cat-thumb"
                    onclick={() => openLB(list, i)}
                    title={doc.title || doc.source_file}
                  >
                    <img
                      src={`/api/image/${doc.folder}/${doc.source_file}`}
                      alt={doc.source_file}
                      loading="lazy"
                      onerror={(e) => (e.currentTarget as HTMLImageElement).style.opacity = '0.2'}
                    />
                    {#if doc.company}<span class="thumb-tag">{doc.company}</span>{/if}
                  </button>
                {/if}
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    {#if categories.length > 0}
      <details class="cat-breakdown">
        <summary>Numerical breakdown</summary>
        <div class="table-scroll">
          <table class="data-table">
            <thead><tr><th>Category</th><th>Count</th><th>Examples</th></tr></thead>
            <tbody>
              {#each categories as row}
                <tr><td>{row.category}</td><td>{row.count}</td><td>{row.examples}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
      </details>
    {/if}
  {/if}
</div>

{#if lightboxDoc}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="lb-backdrop" onclick={closeLB}>
    <div class="lb-modal" onclick={(e) => e.stopPropagation()}>
      <button class="lb-close" onclick={closeLB} aria-label="Close">×</button>
      {#if lbList.length > 1}
        <button class="lb-arrow left" onclick={lbPrev} disabled={lbIdx === 0}>◀</button>
        <button class="lb-arrow right" onclick={lbNext} disabled={lbIdx === lbList.length - 1}>▶</button>
        <span class="lb-counter">{lbIdx + 1} / {lbList.length}</span>
      {/if}
      <img class="lb-img" src={`/api/image/${lightboxDoc.folder}/${lightboxDoc.source_file}`} alt={lightboxDoc.source_file} />
      <div class="lb-foot">
        <span>{lightboxDoc.title || lightboxDoc.source_file}</span>
        <a class="lb-dl" href={`/api/image/${lightboxDoc.folder}/${lightboxDoc.source_file}`} download={lightboxDoc.source_file}>Download</a>
      </div>
    </div>
  </div>
{/if}

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; color: var(--text); }
  .muted { color: var(--text-muted); font-size: 13px; }

  .cat-sections { display: flex; flex-direction: column; gap: 12px; }
  .cat-section { border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden; }
  .cat-head {
    width: 100%;
    display: flex; align-items: center; gap: 8px;
    padding: 10px 14px;
    background: var(--surface-2, rgba(0,0,0,0.02));
    border: none;
    cursor: pointer;
    font-family: inherit;
    color: var(--text);
    text-align: left;
  }
  .cat-head:hover { background: var(--surface); }
  .cat-caret { color: var(--text-muted); font-size: 11px; width: 14px; }
  .cat-name { font-weight: 600; font-size: 14px; flex: 1; }
  .cat-count {
    background: var(--accent-soft, rgba(201,100,66,0.1));
    color: var(--accent);
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
  }
  .cat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 8px;
    padding: 12px;
  }
  .cat-thumb {
    position: relative;
    aspect-ratio: 1;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    background: var(--surface);
    cursor: zoom-in;
    transition: border-color 0.15s, transform 0.1s;
    padding: 0;
  }
  .cat-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .cat-thumb:hover { border-color: var(--accent); transform: scale(1.03); }
  .thumb-tag {
    position: absolute; bottom: 4px; left: 4px; right: 4px;
    background: rgba(0,0,0,0.7); color: white;
    padding: 2px 6px; border-radius: var(--r-sm);
    font-size: 10px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  .cat-breakdown {
    margin-top: 16px;
    border-top: 1px solid var(--border);
    padding-top: 12px;
  }
  .cat-breakdown summary {
    cursor: pointer;
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 500;
    padding: 4px 0;
    list-style: none;
  }
  .cat-breakdown summary::-webkit-details-marker { display: none; }
  .cat-breakdown summary::before { content: '▸'; margin-right: 6px; }
  .cat-breakdown[open] summary::before { content: '▾'; }
  .table-scroll { overflow: auto; max-height: 400px; border: 1px solid var(--border); border-radius: var(--r-md); margin-top: 8px; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 500px; }
  .data-table thead tr { background: var(--surface-2); }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-2); z-index: 2; }
  .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: top; }
  .data-table tbody tr:hover { background: var(--surface-2); }

  /* Lightbox */
  .lb-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.78);
    display: flex; align-items: center; justify-content: center;
    z-index: 250; padding: 16px;
  }
  .lb-modal {
    position: relative;
    background: var(--surface);
    border-radius: var(--r-lg);
    overflow: hidden;
    max-width: 95vw; max-height: 95vh;
    box-shadow: 0 24px 64px rgba(0,0,0,0.5);
    display: flex; flex-direction: column;
  }
  .lb-img {
    max-width: 95vw; max-height: calc(95vh - 56px);
    object-fit: contain; background: #000;
  }
  .lb-close, .lb-arrow {
    position: absolute;
    background: rgba(0,0,0,0.55); color: white;
    border: none; border-radius: 50%;
    cursor: pointer; z-index: 3;
  }
  .lb-close { top: 8px; right: 8px; width: 36px; height: 36px; font-size: 22px; }
  .lb-arrow { top: 50%; transform: translateY(-50%); width: 44px; height: 44px; font-size: 16px; }
  .lb-arrow:disabled { opacity: 0.25; }
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
  .lb-foot {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px;
    border-top: 1px solid var(--border);
    font-size: 13px;
  }
  .lb-foot > span { flex: 1; word-break: break-all; }
  .lb-dl {
    background: var(--accent); color: white;
    padding: 6px 12px; border-radius: var(--r-sm);
    text-decoration: none; font-size: 12px; font-weight: 600;
  }
</style>
