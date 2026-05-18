<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';

  const FLAGS: Record<string, string> = {
    'China': '🇨🇳', 'United States': '🇺🇸', 'USA': '🇺🇸', 'United Kingdom': '🇬🇧', 'UK': '🇬🇧',
    'Germany': '🇩🇪', 'France': '🇫🇷', 'Italy': '🇮🇹', 'Spain': '🇪🇸', 'Japan': '🇯🇵',
    'South Korea': '🇰🇷', 'Korea': '🇰🇷', 'India': '🇮🇳', 'Russia': '🇷🇺', 'Brazil': '🇧🇷',
    'Canada': '🇨🇦', 'Australia': '🇦🇺', 'Mexico': '🇲🇽', 'Indonesia': '🇮🇩', 'Vietnam': '🇻🇳',
    'Thailand': '🇹🇭', 'Singapore': '🇸🇬', 'Malaysia': '🇲🇾', 'Philippines': '🇵🇭', 'Taiwan': '🇹🇼',
    'Hong Kong': '🇭🇰', 'Turkey': '🇹🇷', 'Netherlands': '🇳🇱', 'Switzerland': '🇨🇭',
    'Sweden': '🇸🇪', 'Norway': '🇳🇴', 'Denmark': '🇩🇰', 'Poland': '🇵🇱',
    'UAE': '🇦🇪', 'Myanmar': '🇲🇲', 'Cambodia': '🇰🇭', 'Bangladesh': '🇧🇩'
  };

  let countries: api.CountryStat[] = $state([]);
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      countries = await api.getCountries();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  function flagFor(name: string) {
    return FLAGS[name] || '🏳️';
  }
</script>

<div class="card">
  <h2>Countries</h2>
  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if !countries.length}
    <p class="muted">No country data yet.</p>
  {:else}
    <div class="grid">
      {#each countries as c}
        <div class="country-card">
          <div class="flag">{flagFor(c.country)}</div>
          <div class="meta">
            <div class="name">{c.country}</div>
            <div class="count">{c.doc_count}</div>
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
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
  .country-card { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); }
  .flag { font-size: 28px; line-height: 1; }
  .meta { flex: 1; min-width: 0; }
  .name { font-size: 13px; font-weight: 500; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .count { font-size: 12px; color: var(--accent); font-weight: 600; }
</style>
