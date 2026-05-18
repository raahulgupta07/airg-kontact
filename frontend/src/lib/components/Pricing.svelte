<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let rows: api.PricingRow[] = $state([]);
  let loading = $state(true);
  let error = $state('');
  let search = $state('');

  onMount(async () => {
    try {
      rows = await api.getPricing();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  const filtered = $derived.by(() => {
    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (r.company || '').toLowerCase().includes(q) ||
      (r.category || '').toLowerCase().includes(q)
    );
  });
</script>

<div class="card">
  <h2>Pricing summary</h2>
  <div class="toolbar">
    <input class="input" placeholder="Filter by company or category..." bind:value={search} />
    <span class="muted">{filtered.length} rows</span>
  </div>

  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !filtered.length}
    <p class="muted">No pricing data yet.</p>
  {:else}
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr><th>Company</th><th>Category</th><th>Min</th><th>Median</th><th>Max</th><th>Count</th></tr>
        </thead>
        <tbody>
          {#each filtered as r}
            <tr>
              <td>{r.company || ''}</td>
              <td>{r.category || ''}</td>
              <td>{r.min_price ?? ''}</td>
              <td>{r.median_price ?? ''}</td>
              <td>{r.max_price ?? ''}</td>
              <td>{r.count}</td>
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
  .muted { color: var(--text-muted); font-size: 13px; }
  .toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
  .toolbar .input { flex: 1; }
  .table-scroll { overflow: auto; max-height: 560px; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; background: var(--surface-2); border-bottom: 1px solid var(--border); position: sticky; top: 0; }
  .data-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
</style>
