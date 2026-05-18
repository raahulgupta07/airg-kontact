<script>
  import { shortDate, relativeDate } from '$lib/utils';
  let { products = [], onEdit = (_p) => {} } = $props();

  const MAX_PRODUCT_ROWS = 50;
  let productSearch = $state('');

  function fmtDate(d) {
    if (!d) return '';
    try { return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch { return d; }
  }

  let filteredProducts = $derived.by(() => {
    if (!productSearch.trim()) return products;
    const q = productSearch.toLowerCase();
    return products.filter(p =>
      (p.company || '').toLowerCase().includes(q) ||
      (p.name || '').toLowerCase().includes(q) ||
      (p.model || '').toLowerCase().includes(q) ||
      (p.specs || '').toLowerCase().includes(q) ||
      (p.category || '').toLowerCase().includes(q) ||
      (p.price || '').toLowerCase().includes(q)
    );
  });
</script>

<div class="card table-card">
  <div class="table-head">
    <h2>Products</h2>
    <button class="send-btn" onclick={() => window.open('/api/export/xlsx')}>Export XLSX</button>
  </div>
  <div class="table-toolbar">
    <input type="text" class="input" placeholder="Filter products..." bind:value={productSearch} />
    <span class="table-count">{Math.min(MAX_PRODUCT_ROWS, filteredProducts.length)} of {filteredProducts.length}</span>
  </div>
  {#if products.length === 0}
    <p class="muted">Loading products...</p>
  {:else}
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>UUID</th><th>Company</th><th>Product</th><th>Model</th>
            <th>Specs</th><th>Category</th><th>Price</th>
            <th>Created</th><th>Updated</th><th>Owner</th><th>Source</th><th></th>
          </tr>
        </thead>
        <tbody>
          {#each filteredProducts.slice(0, MAX_PRODUCT_ROWS) as p}
            <tr>
              <td class="uuid-cell">{(p.uuid || '').slice(0, 8)}</td>
              <td>{p.company}</td>
              <td>{p.name}</td>
              <td>{p.model}</td>
              <td class="specs-cell">{p.specs}</td>
              <td>{p.category}</td>
              <td>{p.price}</td>
              <td class="date-cell">{shortDate(p.created_at)}</td>
              <td class="date-cell">{relativeDate(p.updated_at)}</td>
              <td class="owner-cell">{p.owner_name || ''}</td>
              <td>{#if p.source_channel}<span class="src-chip src-{p.source_channel}">{p.source_channel}</span>{/if}</td>
              <td><button class="btn-ghost xs" disabled={!p.uuid} onclick={() => onEdit(p)}>Edit</button></td>
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
  .table-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .table-toolbar { display: flex; align-items: center; gap: 8px; margin: 8px 0 12px; flex-wrap: wrap; }
  .table-toolbar .input { flex: 1; min-width: 160px; }
  .table-count { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
  .table-scroll { overflow: auto; max-height: 560px; -webkit-overflow-scrolling: touch; border: 1px solid var(--border); border-radius: var(--r-md); }
  .data-table { width: 100%; border-collapse: collapse; font-family: var(--font-sans); font-size: 13px; min-width: 500px; }
  .data-table thead tr { background: var(--surface-2); }
  .data-table th { padding: 10px 12px; font-size: 12px; font-weight: 500; color: var(--text-muted); text-align: left; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-2); z-index: 2; white-space: nowrap; }
  .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: top; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .data-table tbody tr:hover { background: var(--surface-2); }
  .data-table tbody tr:last-child td { border-bottom: none; }
  .uuid-cell { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); max-width: 80px; }
  .date-cell { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
  .owner-cell { font-size: 12px; color: var(--text-muted); max-width: 140px; }
  .src-chip {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: var(--r-pill);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
  }
  .src-upload { background: var(--accent-soft); color: var(--accent); }
  .src-wechat { background: rgba(7,193,96,0.1); color: #07c160; }
  .src-email { background: rgba(66,133,244,0.1); color: #4285f4; }
  .src-url { background: rgba(155,89,182,0.1); color: #9b59b6; }
  .src-api { background: var(--surface-2); color: var(--text-muted); }
  .specs-cell { max-width: 260px; }
  .btn-ghost.xs { padding: 4px 10px; font-size: 11px; min-height: 24px; margin-right: 4px; }
</style>
