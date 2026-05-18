<script>
  let { documents = [] } = $props();
  const API = '';
</script>

<div class="card">
  <h2>Image gallery</h2>
  {#if documents.length === 0}
    <p class="muted">Loading images...</p>
  {:else}
    <div class="gallery-grid">
      {#each documents as doc}
        {#if doc.source_file && doc.folder}
          <a class="gallery-thumb" href="{API}/api/image/{doc.folder}/{doc.source_file}" target="_blank" rel="noopener" title={doc.source_file}>
            <img src="{API}/api/image/{doc.folder}/{doc.source_file}" alt={doc.source_file} loading="lazy" />
          </a>
        {/if}
      {/each}
    </div>
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 8px; font-size: 16px; font-weight: 600; color: var(--text); }
  .muted { color: var(--text-muted); font-size: 13px; }
  .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 8px; margin-top: 8px; }
  .gallery-thumb { display: block; aspect-ratio: 1; overflow: hidden; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface-2); transition: border-color 0.15s, box-shadow 0.15s; }
  .gallery-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .gallery-thumb:hover { border-color: var(--accent); box-shadow: var(--shadow-sm); }
</style>
