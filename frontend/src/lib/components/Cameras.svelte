<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  let cameras: api.CameraStat[] = $state([]);
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      cameras = await api.getCameras();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  const max = $derived(Math.max(1, ...cameras.map((c) => c.doc_count || 0)));
</script>

<div class="card">
  <h2>Cameras</h2>
  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !cameras.length}
    <p class="muted">No camera metadata yet.</p>
  {:else}
    <div class="bars">
      {#each cameras as c}
        {@const pct = (c.doc_count / max) * 100}
        <div class="row">
          <div class="row-head">
            <strong>{c.camera_make || 'Unknown'} {c.camera_model || ''}</strong>
            <span class="muted">{c.doc_count}</span>
          </div>
          <div class="bar"><div class="bar-fill" style:width={pct + '%'}></div></div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .bars { display: flex; flex-direction: column; gap: 10px; }
  .row { display: flex; flex-direction: column; gap: 5px; }
  .row-head { display: flex; justify-content: space-between; font-size: 13px; }
  .bar { height: 8px; background: var(--surface-2); border-radius: var(--r-pill); overflow: hidden; }
  .bar-fill { height: 100%; background: var(--accent); }
</style>
