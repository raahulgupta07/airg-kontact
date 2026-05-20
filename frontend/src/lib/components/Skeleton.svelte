<script lang="ts">
  let { rows = 5, kind = 'list' } = $props<{ rows?: number; kind?: 'list' | 'grid' | 'card' }>();
</script>

{#if kind === 'grid'}
  <div class="sk-grid">
    {#each Array(rows) as _}<div class="sk-tile shimmer"></div>{/each}
  </div>
{:else if kind === 'card'}
  <div class="sk-cards">
    {#each Array(rows) as _}
      <div class="sk-card">
        <div class="sk-thumb shimmer"></div>
        <div class="sk-lines">
          <div class="sk-line shimmer" style="width: 60%"></div>
          <div class="sk-line shimmer" style="width: 40%"></div>
        </div>
      </div>
    {/each}
  </div>
{:else}
  <div class="sk-list">
    {#each Array(rows) as _, i}
      <div class="sk-row shimmer" style="width: {100 - (i * 5)}%"></div>
    {/each}
  </div>
{/if}

<style>
  .shimmer {
    background: linear-gradient(90deg, var(--surface-2, rgba(0,0,0,0.04)) 25%, rgba(150,150,150,0.12) 50%, var(--surface-2, rgba(0,0,0,0.04)) 75%);
    background-size: 200% 100%;
    animation: sk-shimmer 1.4s ease-in-out infinite;
    border-radius: var(--r-sm, 6px);
  }
  @keyframes sk-shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  .sk-list { display: flex; flex-direction: column; gap: 8px; padding: 12px 0; }
  .sk-row { height: 16px; }
  .sk-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; }
  .sk-tile { aspect-ratio: 1; }
  .sk-cards { display: flex; flex-direction: column; gap: 10px; }
  .sk-card { display: flex; gap: 12px; padding: 10px; border: 1px solid var(--border); border-radius: var(--r-md); }
  .sk-thumb { width: 80px; height: 80px; flex-shrink: 0; }
  .sk-lines { flex: 1; display: flex; flex-direction: column; gap: 8px; padding: 8px 0; }
  .sk-line { height: 12px; }
</style>
