<script>
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import * as api from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import AdminInsights from '$lib/components/AdminInsights.svelte';
  import UsersManager from '$lib/components/UsersManager.svelte';

  const API = '';

  let toast = $state('');
  function showToast(msg) { toast = msg; setTimeout(() => toast = '', 2400); }

  let stats = $state(null);
  let modelConfig = $state(null);
  let searchQuery = $state('');
  let searchResults = $state(null);
  let searching = $state(false);
  let indexing = $state(false);
  let indexResult = $state(null);

  // Tabs — only Tools and Stats remain; tables now live on /data
  let activeTab = $state('tools');
  let tabs = $derived([
    { id: 'tools', label: 'Tools' },
    { id: 'stats', label: 'Stats' },
    ...(auth.isAdmin ? [
      { id: 'users', label: '👥 Users' },
      { id: 'admin', label: '⚙ Admin Insights' },
    ] : []),
  ]);

  onMount(async () => {
    try {
      const [statsRes, configRes] = await Promise.all([
        fetch(`${API}/api/stats`),
        fetch(`${API}/api/config`)
      ]);
      stats = await statsRes.json();
      modelConfig = await configRes.json();
    } catch (e) {
      console.error('Failed to load stats:', e);
    }
  });

  async function doSearch() {
    if (!searchQuery.trim()) return;
    searching = true;
    searchResults = null;
    try {
      const [textRes, semRes] = await Promise.all([
        fetch(`${API}/api/search?q=${encodeURIComponent(searchQuery)}`),
        fetch(`${API}/api/search/semantic?q=${encodeURIComponent(searchQuery)}`)
      ]);
      const textData = await textRes.json();
      const semData = await semRes.json();
      searchResults = { text: textData, semantic: semData };
    } catch (e) {
      searchResults = { error: String(e) };
    } finally {
      searching = false;
    }
  }

  async function doReindex() {
    indexing = true;
    indexResult = null;
    try {
      const res = await fetch(`${API}/api/index`, { method: 'POST' });
      indexResult = await res.json();
    } catch (e) {
      indexResult = { error: String(e) };
    } finally {
      indexing = false;
    }
  }
</script>

<svelte:head><title>Settings | KONTACT</title></svelte:head>

<div class="page">
  <header class="page-head">
    <h1 class="page-title">Settings</h1>
    <p class="page-sub">Tools, users, and admin controls</p>
  </header>

  <!-- TAB SWITCHER -->
  <div class="tabs" role="tablist">
    {#each tabs as t}
      <button
        class="tab"
        class:active={activeTab === t.id}
        onclick={() => activeTab = t.id}
        role="tab"
        aria-selected={activeTab === t.id}
      >{t.label}</button>
    {/each}
  </div>

  <!-- TOOLS -->
  {#if activeTab === 'tools'}
    <div class="cards">
      <button class="card link-card" onclick={() => goto('/data')}>
        <div class="link-card-body">
          <h2>Browse data tables on the Data tab &rarr;</h2>
          <p>Cards, Contacts, Products, Companies, Categories, Specs, Gallery.</p>
        </div>
        <span class="link-arrow">&rarr;</span>
      </button>

      <div class="card">
        <h2>Search</h2>
        <div class="search-row">
          <input type="text" class="input" placeholder="Search documents..." bind:value={searchQuery} onkeydown={(e) => e.key === 'Enter' && doSearch()} />
          <button class="send-btn" onclick={doSearch} disabled={searching}>
            {searching ? '...' : 'Go'}
          </button>
        </div>
        {#if searchResults?.error}
          <p class="error-text">{searchResults.error}</p>
        {/if}
        {#if searchResults && !searchResults.error}
          <div class="results">
            {#if searchResults.text?.length}
              <div class="result-group-label">Text matches ({searchResults.text.length})</div>
              {#each searchResults.text.slice(0, 5) as item}
                <div class="result-item">
                  <strong>{item.title || item.source_file || 'Untitled'}</strong>
                  {#if item.company}<span class="chip">{item.company}</span>{/if}
                </div>
              {/each}
            {/if}
            {#if searchResults.semantic?.length}
              <div class="result-group-label">Semantic ({searchResults.semantic.length})</div>
              {#each searchResults.semantic.slice(0, 5) as item}
                <div class="result-item">
                  <strong>{item.title || item.source_file || item.text?.slice(0, 60) || 'Match'}</strong>
                  {#if item.score}<span class="chip">{(item.score * 100).toFixed(0)}%</span>{/if}
                </div>
              {/each}
            {/if}
            {#if !searchResults.text?.length && !searchResults.semantic?.length}
              <p class="muted">No results found.</p>
            {/if}
          </div>
        {/if}
      </div>

      <button class="card link-card" onclick={() => window.open(`${API}/api/export/xlsx`)}>
        <div class="link-card-body">
          <h2>Export XLSX</h2>
          <p>Download products, contacts, and summary as Excel.</p>
        </div>
        <span class="link-arrow">&darr;</span>
      </button>

      <button class="card link-card" onclick={() => window.open(`${API}/api/export/json`)}>
        <div class="link-card-body">
          <h2>Export JSON</h2>
          <p>Download all extractions as JSON.</p>
        </div>
        <span class="link-arrow">&darr;</span>
      </button>

      <button class="card link-card" onclick={() => window.open(`${API}/api/export/csv`)}>
        <div class="link-card-body">
          <h2>Export CSV</h2>
          <p>Download flat table as CSV.</p>
        </div>
        <span class="link-arrow">&darr;</span>
      </button>

      <div class="card">
        <h2>Re-index</h2>
        <p class="muted">Rebuild database + vector index from JSON files.</p>
        <div style="margin-top:8px;">
          <button class="send-btn" onclick={doReindex} disabled={indexing}>
            {indexing ? 'Indexing...' : 'Run re-index'}
          </button>
        </div>
        {#if indexResult}
          <div class="index-result" class:error={indexResult.error}>
            {#if indexResult.error}
              Error: {indexResult.error}
            {:else}
              DB: {indexResult.db_records} records · Vectors: {indexResult.vector_records} records
            {/if}
          </div>
        {/if}
      </div>

      <div class="card">
        <h2>Models</h2>
        {#if modelConfig}
          <div class="stat-row"><span class="stat-label">Vision / Chat</span><span class="chip chip-accent">{modelConfig.vision_model}</span></div>
          <div class="stat-row"><span class="stat-label">Embeddings</span><span class="chip">{modelConfig.embedding_model}</span></div>
          <div class="stat-row"><span class="stat-label">Provider</span><span class="chip">{modelConfig.provider}</span></div>
          <p class="muted small">
            Classifier, extractor and chat use the vision model. Embeddings power vector search via OpenRouter.
          </p>
        {:else}
          <p class="muted">Loading...</p>
        {/if}
      </div>
    </div>
  {/if}

  <!-- STATS -->
  {#if activeTab === 'stats'}
    <div class="card">
      <h2>Stats</h2>
      {#if stats}
        <div class="stat-row"><span class="stat-label">Total documents</span><span class="stat-value">{stats.total_docs ?? stats.total ?? '?'}</span></div>
        <div class="stat-row"><span class="stat-label">Folders</span><span class="stat-value">{stats.folders?.length ?? stats.folder_count ?? '?'}</span></div>
        {#if stats.folders?.length}
          <div class="stat-tags">
            {#each stats.folders as folder}<span class="chip">{folder}</span>{/each}
          </div>
        {/if}
        {#if stats.companies?.length}
          <div class="stat-row"><span class="stat-label">Companies</span><span class="stat-value">{stats.companies.length}</span></div>
          <div class="stat-tags">
            {#each stats.companies as company}<span class="chip chip-accent">{company}</span>{/each}
          </div>
        {/if}
      {:else}
        <p class="muted">Loading stats...</p>
      {/if}
    </div>
  {/if}

  <!-- USERS (admin only) -->
  {#if activeTab === 'users' && auth.isAdmin}
    <UsersManager />
  {/if}

  <!-- ADMIN INSIGHTS (admin/super-admin only) -->
  {#if activeTab === 'admin' && auth.isAdmin}
    <AdminInsights />
  {/if}
</div>

{#if toast}<div class="toast">{toast}</div>{/if}

<style>
  .page {
    max-width: 1100px;
    margin: 0 auto;
    padding: 16px 16px 64px;
    font-family: var(--font-sans);
  }
  .page-head { margin-bottom: 16px; }
  .page-title { font-size: 24px; font-weight: 600; color: var(--text); margin: 0; }
  .page-sub { font-size: 14px; color: var(--text-muted); margin: 4px 0 0; }

  .tabs {
    display: flex; gap: 6px;
    margin-bottom: 16px;
    flex-wrap: wrap;
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .tab {
    background: transparent;
    border: 1px solid var(--border);
    padding: 6px 14px;
    font-family: inherit; font-size: 13px;
    font-weight: 500;
    color: var(--text-muted);
    border-radius: var(--r-pill);
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .tab:hover { color: var(--text); }
  .tab.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }

  .cards { display: flex; flex-direction: column; gap: 12px; }
  .card h2 { margin: 0 0 8px; font-size: 16px; font-weight: 600; color: var(--text); }
  .card p { font-size: 13px; color: var(--text-muted); margin: 0; }

  .link-card {
    display: flex; align-items: center;
    gap: 12px; cursor: pointer;
    text-align: left; width: 100%;
    font-family: inherit;
  }
  .link-card:hover { background: var(--surface-2); }
  .link-card-body { flex: 1; }
  .link-card-body h2 { margin: 0 0 2px; }
  .link-card-body p { margin: 0; }
  .link-arrow {
    font-size: 18px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .search-row { display: flex; gap: 8px; margin-top: 6px; }
  .search-row .input { flex: 1; }

  .results { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
  .result-group-label { font-size: 12px; color: var(--text-muted); font-weight: 500; margin-top: 4px; }
  .result-item {
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    display: flex; align-items: center; gap: 8px;
    flex-wrap: wrap;
  }

  .index-result {
    margin-top: 10px;
    padding: 8px 12px;
    background: rgba(90,143,61,0.1);
    border: 1px solid var(--success);
    color: var(--success);
    border-radius: var(--r-md);
    font-size: 13px;
  }
  .index-result.error {
    background: rgba(181,69,61,0.08);
    border-color: var(--danger);
    color: var(--danger);
  }

  .stat-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
  }
  .stat-row:last-child { border-bottom: none; }
  .stat-label { color: var(--text-muted); }
  .stat-value { font-weight: 500; color: var(--text); }
  .stat-tags { padding: 6px 0; display: flex; flex-wrap: wrap; gap: 6px; }

  .muted { color: var(--text-muted); font-size: 13px; }
  .small { font-size: 12px; margin-top: 8px; }
  .error-text { color: var(--danger); font-size: 13px; }

  .toast {
    position: fixed;
    bottom: 24px; right: 24px;
    background: var(--accent);
    color: #fff;
    padding: 10px 16px;
    font-size: 13px; font-weight: 500;
    border-radius: var(--r-md);
    box-shadow: var(--shadow-md);
    z-index: 400;
  }
</style>
