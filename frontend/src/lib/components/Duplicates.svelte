<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let clusters: api.DuplicateCluster[] = $state([]);
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      const r = await api.getDuplicates();
      clusters = r.clusters || [];
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  function thumbUrl(folder: string, file: string) {
    return `/api/image/${folder}/${file}`;
  }
</script>

<div class="card">
  <h2>Duplicate clusters</h2>
  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !clusters.length}
    <p class="muted">No duplicates detected.</p>
  {:else}
    {#each clusters as c}
      <div class="cluster">
        <div class="cluster-head">
          <strong>Cluster {c.cluster_id.slice(0, 8)}</strong>
          <span class="chip">{c.items.length} items</span>
        </div>
        <div class="thumbs">
          {#each c.items as it}
            <div class="thumb-cell">
              <img src={thumbUrl(it.folder, it.source_file)} alt={it.source_file} loading="lazy" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = 'none')} />
              <div class="thumb-name">{it.source_file}</div>
              <div class="thumb-actions">
                <button class="btn-ghost xs">Keep</button>
                <button class="btn-ghost xs danger">Delete</button>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/each}
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .cluster { border: 1px solid var(--border); border-radius: var(--r-md); padding: 12px; margin-bottom: 12px; background: var(--surface-2); }
  .cluster-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
  .chip { display: inline-block; padding: 2px 10px; border-radius: var(--r-pill); background: var(--accent-soft); color: var(--accent-ink); font-size: 11px; }
  .thumbs { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 4px; }
  .thumb-cell { width: 140px; flex-shrink: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-md); padding: 6px; display: flex; flex-direction: column; gap: 6px; }
  .thumb-cell img { width: 100%; height: 100px; object-fit: cover; border-radius: var(--r-sm); border: 1px solid var(--border); }
  .thumb-name { font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .thumb-actions { display: flex; gap: 4px; }
  .btn-ghost.xs { padding: 4px 8px; font-size: 11px; min-height: 24px; flex: 1; }
  .btn-ghost.xs.danger { color: var(--danger); border-color: var(--danger); }
</style>
