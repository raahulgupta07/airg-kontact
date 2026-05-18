<script>
  let { companies = [] } = $props();
</script>

<div class="card table-card">
  <h2>Companies</h2>
  {#if companies.length === 0}
    <p class="muted">Loading companies...</p>
  {:else}
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr><th>Company</th><th>Documents</th><th>Products</th></tr></thead>
        <tbody>
          {#each companies as c}
            <tr>
              <td>{c.company || c.name || ''}</td>
              <td>{c.documents ?? c.doc_count ?? c.document_count ?? ''}</td>
              <td>{c.products ?? c.product_count ?? ''}</td>
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
  .table-scroll { overflow: auto; max-height: 560px; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 500px; }
  .data-table thead tr { background: var(--surface-2); }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-2); z-index: 2; white-space: nowrap; }
  .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: top; }
  .data-table tbody tr:hover { background: var(--surface-2); }
  .data-table tbody tr:last-child td { border-bottom: none; }
</style>
