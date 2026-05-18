<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let sources: api.SyncSourceStat[] = $state([]);
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      sources = await api.getSyncSources();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  const total = $derived(sources.reduce((a, s) => a + (s.doc_count || 0), 0));
</script>

<div class="card">
  <h2>Sync sources</h2>
  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !sources.length}
    <p class="muted">No source data yet.</p>
  {:else}
    <div class="bars">
      {#each sources as s}
        {@const pct = total ? (s.doc_count / total) * 100 : 0}
        <div class="row">
          <div class="row-head">
            <strong>{s.source}</strong>
            <span class="muted">{s.doc_count} ({pct.toFixed(1)}%)</span>
          </div>
          <div class="bar">
            <div class="bar-fill" style:width={pct + '%'}></div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .bars { display: flex; flex-direction: column; gap: 12px; }
  .row { display: flex; flex-direction: column; gap: 5px; }
  .row-head { display: flex; justify-content: space-between; font-size: 13px; text-transform: capitalize; }
  .bar { height: 8px; background: var(--surface-2); border-radius: var(--r-pill); overflow: hidden; }
  .bar-fill { height: 100%; background: var(--accent); transition: width 0.3s; }
</style>
