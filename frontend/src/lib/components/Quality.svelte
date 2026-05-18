<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let data: api.QualityResponse = $state({ blurry: 0, low_res: 0, near_dups: 0, items: [] });
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      data = await api.getQuality();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });
</script>

<div class="card">
  <h2>Image quality</h2>
  <div class="stats">
    <div class="stat-card">
      <div class="stat-num warn">{data.blurry}</div>
      <div class="stat-label">Blurry</div>
    </div>
    <div class="stat-card">
      <div class="stat-num warn">{data.low_res}</div>
      <div class="stat-label">Low-res</div>
    </div>
    <div class="stat-card">
      <div class="stat-num warn">{data.near_dups}</div>
      <div class="stat-label">Near-duplicates</div>
    </div>
  </div>

  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !data.items.length}
    <p class="muted">No quality issues found.</p>
  {:else}
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr><th>File</th><th>Blur score</th><th>Dimensions</th><th>Near-dup of</th><th>Reason</th></tr>
        </thead>
        <tbody>
          {#each data.items as it}
            <tr>
              <td>{it.source_file || ''}</td>
              <td>{it.blur_score?.toFixed?.(2) ?? it.blur_score ?? ''}</td>
              <td>{it.img_width || ''} × {it.img_height || ''}</td>
              <td class="uuid-cell">{(it.near_dup_of || '').slice(0, 8)}</td>
              <td>{it.reason || ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
  .stat-card { padding: 14px; background: var(--surface-2); border-radius: var(--r-md); border: 1px solid var(--border); }
  .stat-num { font-size: 26px; font-weight: 700; color: var(--text); }
  .stat-num.warn { color: var(--warning); }
  .stat-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .table-scroll { overflow: auto; max-height: 480px; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; background: var(--surface-2); border-bottom: 1px solid var(--border); position: sticky; top: 0; }
  .data-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
  .uuid-cell { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
</style>
