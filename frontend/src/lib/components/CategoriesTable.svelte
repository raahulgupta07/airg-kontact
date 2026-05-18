<script>
  let { categories = [] } = $props();
</script>

<div class="card table-card">
  <h2>Categories breakdown</h2>
  {#if categories.length === 0}
    <p class="muted">No categories.</p>
  {:else}
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
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 8px; font-size: 16px; font-weight: 600; color: var(--text); }
  .muted { color: var(--text-muted); font-size: 13px; }
  .table-scroll { overflow: auto; max-height: 560px; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 500px; }
  .data-table thead tr { background: var(--surface-2); }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-2); z-index: 2; white-space: nowrap; }
  .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: top; }
  .data-table tbody tr:hover { background: var(--surface-2); }
  .data-table tbody tr:last-child td { border-bottom: none; }
</style>
