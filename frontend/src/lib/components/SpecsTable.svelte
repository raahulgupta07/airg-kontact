<script>
  let { specs = [] } = $props();
  let specsSearch = $state('');

  let filteredSpecs = $derived.by(() => {
    const base = specs.filter(p => p.specs);
    if (!specsSearch.trim()) return base.slice(0, 30);
    const q = specsSearch.toLowerCase();
    return base.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.model || '').toLowerCase().includes(q) ||
      (p.specs || '').toLowerCase().includes(q) ||
      (p.company || '').toLowerCase().includes(q)
    ).slice(0, 30);
  });
</script>

<div class="card table-card">
  <h2>Product specs</h2>
  <div class="table-toolbar">
    <input type="text" class="input" placeholder="Filter specs..." bind:value={specsSearch} />
  </div>
  {#if filteredSpecs.length === 0}
    <p class="muted">No products with specs found.</p>
  {:else}
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr><th>Product</th><th>Model</th><th>Specs</th><th>Category</th><th>Company</th></tr></thead>
        <tbody>
          {#each filteredSpecs as p}
            <tr>
              <td>{p.name}</td><td>{p.model}</td>
              <td class="specs-cell-wide">{p.specs}</td>
              <td>{p.category}</td><td>{p.company}</td>
            </tr>
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
  .table-toolbar { display: flex; align-items: center; gap: 8px; margin: 8px 0 12px; flex-wrap: wrap; }
  .table-toolbar .input { flex: 1; min-width: 160px; }
  .table-scroll { overflow: auto; max-height: 560px; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 500px; }
  .data-table thead tr { background: var(--surface-2); }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-2); z-index: 2; white-space: nowrap; }
  .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: top; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .data-table tbody tr:hover { background: var(--surface-2); }
  .data-table tbody tr:last-child td { border-bottom: none; }
  .specs-cell-wide { max-width: 320px; white-space: normal; word-wrap: break-word; }
</style>
