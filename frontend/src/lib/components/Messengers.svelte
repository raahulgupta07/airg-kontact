<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';
  import { messengerIcon } from '$lib/messenger';

  type Platform = 'whatsapp' | 'wechat' | 'viber' | 'line' | 'telegram';
  const PLATFORMS: Platform[] = ['whatsapp', 'wechat', 'viber', 'line', 'telegram'];

  let data: api.MessengersResponse = $state({ whatsapp: [], wechat: [], viber: [], line: [], telegram: [] });
  let activePlatform: Platform = $state('whatsapp');
  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      data = await api.getMessengers();
    } catch (e: any) {
      error = e?.message || 'Failed to load';
    } finally {
      loading = false;
    }
  });

  function platformUrl(p: Platform, c: api.MessengerContact): string {
    const handle = (c.handle || c.phone || '').replace(/^@/, '');
    const digits = (c.phone || c.handle || '').replace(/[^\d]/g, '');
    switch (p) {
      case 'whatsapp': return `https://wa.me/${digits}`;
      case 'wechat': return `weixin://dl/chat?${handle}`;
      case 'viber': return `viber://add?number=${digits}`;
      case 'line': return `https://line.me/ti/p/~${handle}`;
      case 'telegram': return `https://t.me/${handle}`;
    }
  }
</script>

<div class="card">
  <h2>Messengers</h2>
  <div class="sub-tabs">
    {#each PLATFORMS as p}
      <button class="sub-tab" class:active={activePlatform === p} onclick={() => (activePlatform = p)}>
        <span class="ic">{@html messengerIcon(p)}</span>
        {p}
        <span class="chip">{(data[p] || []).length}</span>
      </button>
    {/each}
  </div>

  {#if loading}
    <p class="muted">Loading...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else}
    {@const items = data[activePlatform] || []}
    {#if !items.length}
      <p class="muted">No contacts found on {activePlatform}.</p>
    {:else}
      <ul class="msg-list">
        {#each items as c}
          <li>
            <div>
              <strong>{c.person || c.company || c.handle || '?'}</strong>
              {#if c.company && c.person}<span class="muted"> · {c.company}</span>{/if}
              <div class="handle">{c.handle || c.phone || ''}</div>
            </div>
            <a class="msg-chip" href={platformUrl(activePlatform, c)} target="_blank" rel="noopener">
              {@html messengerIcon(activePlatform)} <span>Open</span>
            </a>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</div>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  .muted { color: var(--text-muted); font-size: 13px; }
  .sub-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
  .sub-tab { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-pill); font-size: 12px; color: var(--text-muted); cursor: pointer; text-transform: capitalize; font-family: inherit; }
  .sub-tab.active { background: var(--accent-soft); color: var(--accent-ink); border-color: var(--accent); }
  .ic { display: inline-flex; }
  .chip { padding: 1px 7px; border-radius: var(--r-pill); background: var(--surface); font-size: 11px; }
  .msg-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
  .msg-list li { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); font-size: 13px; gap: 8px; }
  .handle { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); margin-top: 2px; }
  .msg-chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--accent-soft); color: var(--accent-ink); border-radius: var(--r-pill); text-decoration: none; font-size: 12px; font-weight: 500; }
  .msg-chip:hover { background: var(--accent); color: #fff; }
</style>
