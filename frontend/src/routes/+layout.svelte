<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { theme, initTheme, toggleTheme } from '$lib/theme';
  import { auth } from '$lib/auth.svelte';
  import UploadTray from '$lib/components/UploadTray.svelte';
  import UndoStack from '$lib/components/UndoStack.svelte';
  import { uploadQueue } from '$lib/uploadQueue.svelte';

  function activeJobsForKey(key: string): number {
    if (key === 'upload' || key === 'queue') {
      return uploadQueue.jobs.filter(j =>
        j.status === 'queued' || j.status === 'uploading' || j.status === 'compressing'
      ).length;
    }
    return 0;
  }
  function needsForceCount(): number {
    return uploadQueue.jobs.filter(j => j.status === 'needs_force').length;
  }

  let { children } = $props();

  const currentPath = $derived($page.url.pathname);
  const isLoginRoute = $derived(currentPath === '/login');

  const ALL_TABS = [
    { path: '/upload', label: 'Upload', key: 'upload', adminOnly: false, superOnly: false },
    { path: '/queue',  label: 'Queue',  key: 'queue',  adminOnly: false, superOnly: false },
    { path: '/chat',   label: 'Agent',  key: 'chat',   adminOnly: false, superOnly: false },
    { path: '/data',   label: 'Data',   key: 'data',   adminOnly: false, superOnly: false },
    { path: '/sync',   label: 'Sync',     key: 'sync',  adminOnly: true,  superOnly: false },
    { path: '/more',   label: 'Settings', key: 'more',  adminOnly: true,  superOnly: true }
  ] as const;

  // Hide admin-only nav from regular users; Settings is super_admin only.
  let tabs = $derived(ALL_TABS.filter(t =>
    (t.superOnly ? auth.isSuperAdmin : (!t.adminOnly || auth.isAdmin))
  ));

  function isActive(tabPath: string): boolean {
    if (tabPath === '/upload') return currentPath === '/' || currentPath.startsWith('/upload');
    return currentPath.startsWith(tabPath);
  }

  function navigateTo(path: string) {
    goto(path);
  }

  // PWA install prompt
  let deferredInstall: any = $state(null);
  let showInstall = $state(false);
  const INSTALL_DISMISS_KEY = 'kontact-install-dismissed';

  // What's-new banner (bump version to re-show)
  const WHATS_NEW_VERSION = 'v2026-05-19';
  const WHATS_NEW_KEY = 'kontact-whats-new-dismissed';
  let showWhatsNew = $state(false);

  function dismissWhatsNew() {
    showWhatsNew = false;
    try { localStorage.setItem(WHATS_NEW_KEY, WHATS_NEW_VERSION); } catch {}
  }

  // iOS Add-to-Home-Screen hint (Safari only — no beforeinstallprompt event)
  const IOS_HINT_KEY = 'kontact-ios-hint-dismissed';
  let showIosHint = $state(false);

  function detectIosSafari(): boolean {
    if (typeof navigator === 'undefined') return false;
    const ua = navigator.userAgent;
    const isIos = /iPad|iPhone|iPod/.test(ua) && !(window as any).MSStream;
    const isSafari = /^((?!chrome|crios|fxios|edgios).)*safari/i.test(ua);
    const inStandalone = (navigator as any).standalone || window.matchMedia('(display-mode: standalone)').matches;
    return isIos && isSafari && !inStandalone;
  }
  function dismissIosHint() {
    showIosHint = false;
    try { localStorage.setItem(IOS_HINT_KEY, '1'); } catch {}
  }

  onMount(async () => {
    initTheme();
    await auth.refresh();
    if (!auth.user && !isLoginRoute) {
      goto('/login');
    }

    // PWA install hook
    try {
      const dismissed = localStorage.getItem(INSTALL_DISMISS_KEY);
      window.addEventListener('beforeinstallprompt', (e: any) => {
        e.preventDefault();
        deferredInstall = e;
        if (!dismissed) showInstall = true;
      });
    } catch {}

    // What's-new banner
    try {
      const seen = localStorage.getItem(WHATS_NEW_KEY);
      if (seen !== WHATS_NEW_VERSION) showWhatsNew = true;
    } catch {}

    // iOS install hint
    try {
      const dismissed = localStorage.getItem(IOS_HINT_KEY);
      if (!dismissed && detectIosSafari()) showIosHint = true;
    } catch {}
  });

  async function triggerInstall() {
    if (!deferredInstall) return;
    deferredInstall.prompt();
    try { await deferredInstall.userChoice; } catch {}
    deferredInstall = null;
    showInstall = false;
  }

  function dismissInstall() {
    showInstall = false;
    try { localStorage.setItem(INSTALL_DISMISS_KEY, '1'); } catch {}
  }

  // Reactive guard: kick out if session disappears
  $effect(() => {
    if (!auth.loading && !auth.user && !isLoginRoute) {
      goto('/login');
    }
  });

  function themeLabel(t: string): string {
    return t === 'light' ? 'Light' : t === 'dark' ? 'Dark' : 'Auto';
  }

  async function onSignOut() {
    await auth.logout();
  }

  // Global keyboard shortcuts
  function onGlobalKey(e: KeyboardEvent) {
    // Skip if typing in input/textarea/contenteditable
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === '/') {
      const inp = document.querySelector<HTMLInputElement>('input[type="search"], input.input, input[placeholder*="Filter"], input[placeholder*="filter"], input[placeholder*="Search"]');
      if (inp) { inp.focus(); e.preventDefault(); }
    } else if (e.key === 'n') {
      goto('/upload');
    } else if (e.key === 'g') {
      // wait for second key
      const handler = (e2: KeyboardEvent) => {
        if (e2.key === 'd') goto('/data');
        else if (e2.key === 'q') goto('/queue');
        else if (e2.key === 'c') goto('/chat');
        else if (e2.key === 'u') goto('/upload');
        window.removeEventListener('keydown', handler);
      };
      window.addEventListener('keydown', handler, { once: true });
      setTimeout(() => window.removeEventListener('keydown', handler), 1500);
    } else if (e.key === '?') {
      shortcutHelp = !shortcutHelp;
    }
  }
  let shortcutHelp = $state(false);
</script>

<svelte:window onkeydown={onGlobalKey} />

{#if isLoginRoute}
  {@render children()}
{:else if auth.loading}
  <div class="loading-shell">Loading…</div>
{:else if !auth.user}
  <div class="loading-shell">Redirecting…</div>
{:else}
{#if showInstall}
  <div class="install-banner" role="region" aria-label="Install Kontact">
    <span>Install Kontact for one-tap camera access</span>
    <div class="install-actions">
      <button class="install-btn" onclick={triggerInstall}>Install</button>
      <button class="install-dismiss" onclick={dismissInstall} aria-label="dismiss">×</button>
    </div>
  </div>
{/if}
{#if showIosHint}
  <div class="ios-hint" role="region" aria-label="Add to Home Screen">
    <span class="ios-icon">📲</span>
    <div class="ios-text">
      Install KONTACT on iPhone — tap
      <span class="ios-share-icon" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
      </span>
      then "Add to Home Screen"
    </div>
    <button class="install-dismiss" onclick={dismissIosHint} aria-label="dismiss">×</button>
  </div>
{/if}
{#if shortcutHelp}
  <div class="sk-backdrop" onclick={() => shortcutHelp = false} role="presentation">
    <div class="sk-modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Keyboard shortcuts">
      <h3>Keyboard shortcuts</h3>
      <dl>
        <dt><kbd>/</kbd></dt><dd>Focus search</dd>
        <dt><kbd>n</kbd></dt><dd>New upload</dd>
        <dt><kbd>g</kbd> <kbd>d</kbd></dt><dd>Go to Data</dd>
        <dt><kbd>g</kbd> <kbd>q</kbd></dt><dd>Go to Queue</dd>
        <dt><kbd>g</kbd> <kbd>c</kbd></dt><dd>Go to Chat</dd>
        <dt><kbd>g</kbd> <kbd>u</kbd></dt><dd>Go to Upload</dd>
        <dt><kbd>?</kbd></dt><dd>Toggle this help</dd>
        <dt><kbd>Esc</kbd></dt><dd>Close modals</dd>
      </dl>
      <button class="install-btn" onclick={() => shortcutHelp = false}>Close</button>
    </div>
  </div>
{/if}
{#if showWhatsNew}
  <div class="whatsnew-banner" role="region" aria-label="What's new">
    <span class="wn-icon">✨</span>
    <div class="wn-text">
      <strong>What's new</strong> — Company names auto-filled · Photos load faster · New Pending Merges tab to review duplicates
    </div>
    <button class="wn-dismiss" onclick={dismissWhatsNew} aria-label="dismiss">×</button>
  </div>
{/if}
<div class="app-shell">
  <!-- Desktop Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-logo">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="3"/>
        <path d="M3 9h18"/>
        <path d="M9 9v12"/>
      </svg>
      <span>Kontact</span>
    </div>

    <div class="sidebar-divider"></div>

    <nav class="sidebar-nav">
      {#each tabs as tab}
        <button
          class="nav-item"
          class:active={isActive(tab.path)}
          onclick={() => navigateTo(tab.path)}
          aria-label={tab.label}
        >
          {#if tab.key === 'upload'}
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          {:else if tab.key === 'queue'}
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="8" y1="6" x2="21" y2="6"/>
              <line x1="8" y1="12" x2="21" y2="12"/>
              <line x1="8" y1="18" x2="21" y2="18"/>
              <circle cx="4" cy="6" r="1"/>
              <circle cx="4" cy="12" r="1"/>
              <circle cx="4" cy="18" r="1"/>
            </svg>
          {:else if tab.key === 'chat'}
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          {:else if tab.key === 'data'}
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <ellipse cx="12" cy="5" rx="9" ry="3"/>
              <path d="M3 5v6c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
              <path d="M3 11v6c0 1.66 4 3 9 3s9-1.34 9-3v-6"/>
            </svg>
          {:else if tab.key === 'sync'}
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="23 4 23 10 17 10"/>
              <polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          {:else}
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="5" cy="12" r="1.4"/>
              <circle cx="12" cy="12" r="1.4"/>
              <circle cx="19" cy="12" r="1.4"/>
            </svg>
          {/if}
          <span class="nav-label">{tab.label}</span>
          {#if activeJobsForKey(tab.key) > 0}
            <span class="nav-badge spin" title="{activeJobsForKey(tab.key)} upload(s) in progress">{activeJobsForKey(tab.key)}</span>
          {:else if tab.key === 'upload' && needsForceCount() > 0}
            <span class="nav-badge warn" title="{needsForceCount()} need(s) confirmation">!</span>
          {/if}
        </button>
      {/each}

    </nav>

    <div class="sidebar-footer">
      {#if auth.user}
        <div class="user-card">
          <button class="user-link" onclick={() => navigateTo('/profile')} title="View profile">
            <div class="user-name">{auth.user.name}</div>
            <div class="user-meta">{auth.user.email || auth.user.phone_e164 || ''}</div>
          </button>
          <div class="user-actions">
            <button class="btn-ghost xs" onclick={() => navigateTo('/profile')} title="Profile">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              Profile
            </button>
            <button class="btn-ghost xs signout-btn" onclick={onSignOut}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              Sign out
            </button>
          </div>
        </div>
      {/if}

      <button
        class="theme-toggle"
        onclick={toggleTheme}
        title="Theme: {themeLabel($theme)} (click to cycle)"
        aria-label="Toggle theme. Current: {themeLabel($theme)}"
      >
        {#if $theme === 'light'}
          <svg class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="4"/>
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
          </svg>
        {:else if $theme === 'dark'}
          <svg class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        {:else}
          <svg class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9"/>
            <path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/>
          </svg>
        {/if}
        <span class="theme-label">Theme</span>
        <span class="theme-value">{themeLabel($theme)}</span>
      </button>
    </div>
  </aside>

  <div class="app-main">
    <!-- Mobile header -->
    <header class="mobile-header">
      <div class="mobile-logo">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="3"/>
          <path d="M3 9h18"/>
          <path d="M9 9v12"/>
        </svg>
        <span>Kontact</span>
      </div>
      <div class="mobile-actions">
        {#if auth.user}
          <button
            class="mobile-theme-btn"
            onclick={onSignOut}
            aria-label="Sign out"
            title="Sign out"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        {/if}
        <button
          class="mobile-theme-btn"
          onclick={toggleTheme}
          aria-label="Toggle theme. Current: {themeLabel($theme)}"
          title="Theme: {themeLabel($theme)}"
        >
          {#if $theme === 'light'}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
            </svg>
          {:else if $theme === 'dark'}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          {:else}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9"/>
              <path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/>
            </svg>
          {/if}
        </button>
      </div>
    </header>

    <main class="page-content" class:is-chat={currentPath.startsWith('/chat')}>
      {@render children()}
    </main>

    <!-- Mobile bottom nav -->
    <nav class="nav-bottom">
      {#each tabs as tab}
        <button
          class:active={isActive(tab.path)}
          onclick={() => navigateTo(tab.path)}
          aria-label={tab.label}
        >
          {#if tab.key === 'upload'}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          {:else if tab.key === 'queue'}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="8" y1="6" x2="21" y2="6"/>
              <line x1="8" y1="12" x2="21" y2="12"/>
              <line x1="8" y1="18" x2="21" y2="18"/>
              <circle cx="4" cy="6" r="1"/>
              <circle cx="4" cy="12" r="1"/>
              <circle cx="4" cy="18" r="1"/>
            </svg>
          {:else if tab.key === 'chat'}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          {:else if tab.key === 'data'}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <ellipse cx="12" cy="5" rx="9" ry="3"/>
              <path d="M3 5v6c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
              <path d="M3 11v6c0 1.66 4 3 9 3s9-1.34 9-3v-6"/>
            </svg>
          {:else if tab.key === 'sync'}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="23 4 23 10 17 10"/>
              <polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          {:else}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="5" cy="12" r="1.4"/>
              <circle cx="12" cy="12" r="1.4"/>
              <circle cx="19" cy="12" r="1.4"/>
            </svg>
          {/if}
          <span>{tab.label}</span>
          {#if activeJobsForKey(tab.key) > 0}
            <span class="mob-badge spin">{activeJobsForKey(tab.key)}</span>
          {:else if tab.key === 'upload' && needsForceCount() > 0}
            <span class="mob-badge warn">!</span>
          {/if}
        </button>
      {/each}
    </nav>
  </div>
</div>
<UploadTray />
<UndoStack />
{/if}

<style>
  /* ── App Shell ── */
  .app-shell {
    display: flex;
    height: 100vh;
    height: 100dvh;
    overflow: hidden;
    background: var(--bg, var(--color-surface));
    color: var(--text, var(--color-on-surface));
  }

  .app-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100vh;
    height: 100dvh;
    min-width: 0;
    overflow: hidden;
  }

  .page-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    padding-bottom: calc(64px + 16px + env(safe-area-inset-bottom, 0px));
  }

  .page-content.is-chat {
    padding: 0;
    overflow: hidden;
    position: relative;
  }

  .loading-shell {
    min-height: 100vh;
    min-height: 100dvh;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    background: var(--bg);
    font-size: 14px;
  }

  /* ── Sidebar (desktop only) ── */
  .sidebar {
    display: none;
  }

  /* ── Mobile header ── */
  .mobile-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    flex-shrink: 0;
    background: var(--sidebar-bg, var(--color-surface));
    border-bottom: 1px solid var(--border, rgba(0,0,0,0.08));
    color: var(--text, var(--color-on-surface));
  }

  .mobile-logo {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 17px;
    font-weight: 600;
    color: var(--text, var(--color-on-surface));
  }

  .mobile-actions {
    display: flex;
    gap: 8px;
  }

  .mobile-theme-btn {
    background: transparent;
    border: 1px solid var(--border, rgba(0,0,0,0.1));
    color: var(--text-muted, var(--color-on-surface-dim));
    width: 36px;
    height: 36px;
    min-height: 36px;
    border-radius: var(--r-md, 8px);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }
  .mobile-theme-btn:hover {
    background: var(--surface, rgba(0,0,0,0.04));
    color: var(--text, var(--color-on-surface));
  }

  /* ── Desktop ── */
  @media (min-width: 768px) {
    .sidebar {
      display: flex;
      flex-direction: column;
      width: 240px;
      flex-shrink: 0;
      background: var(--sidebar-bg, var(--color-surface));
      color: var(--text, var(--color-on-surface));
      border-right: 1px solid var(--border, rgba(0,0,0,0.08));
    }

    .sidebar-logo {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 16px;
      font-size: 18px;
      font-weight: 600;
      color: var(--text, var(--color-on-surface));
      font-family: ui-serif, Georgia, 'Times New Roman', serif;
    }

    .sidebar-divider {
      height: 1px;
      background: var(--border, rgba(0,0,0,0.08));
      margin: 0 12px;
    }

    .sidebar-nav {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 12px 0;
      overflow-y: auto;
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      margin: 2px 8px;
      border-radius: var(--r-md, 8px);
      background: transparent;
      border: none;
      color: var(--text-muted, var(--color-on-surface-dim));
      font-family: inherit;
      font-size: 14px;
      font-weight: 500;
      text-transform: none;
      letter-spacing: normal;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
      min-height: 36px;
      position: relative;
      text-align: left;
    }

    .nav-icon {
      width: 16px;
      height: 16px;
      flex-shrink: 0;
    }

    .nav-badge {
      margin-left: auto;
      min-width: 18px;
      height: 18px;
      padding: 0 5px;
      border-radius: 9px;
      background: var(--accent, #c96442);
      color: white;
      font-size: 10px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
    }
    .nav-badge.warn { background: #e0a800; }
    .nav-badge.spin { animation: nav-pulse 1.4s ease-in-out infinite; }
    .mob-badge {
      position: absolute; top: 4px; right: 8px;
      min-width: 16px; height: 16px; padding: 0 4px;
      border-radius: 8px; background: var(--accent, #c96442); color: white;
      font-size: 9px; font-weight: 700;
      display: inline-flex; align-items: center; justify-content: center;
    }
    .mob-badge.warn { background: #e0a800; }
    .mob-badge.spin { animation: nav-pulse 1.4s ease-in-out infinite; }
    @keyframes nav-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(201,100,66,0.5); }
      50% { box-shadow: 0 0 0 4px rgba(201,100,66,0); }
    }

    .nav-item:hover {
      background: var(--surface, rgba(0,0,0,0.04));
      color: var(--text, var(--color-on-surface));
    }

    .nav-item.active {
      background: var(--accent-soft, rgba(200, 110, 70, 0.12));
      color: var(--accent, var(--color-primary));
    }

    .nav-item.active::before {
      content: '';
      position: absolute;
      left: 0;
      top: 8px;
      bottom: 8px;
      width: 3px;
      background: var(--accent, var(--color-primary));
      border-radius: 2px;
    }

    .sidebar-footer {
      padding: 12px;
      border-top: 1px solid var(--border, rgba(0,0,0,0.08));
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .user-card {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 10px 12px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--r-md);
    }
    .user-name {
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .user-meta {
      font-size: 11px;
      color: var(--text-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .signout-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      margin-top: 4px;
      padding: 6px 10px;
      font-size: 12px;
      min-height: 30px;
      border-radius: var(--r-sm);
    }
    .user-link {
      background: none; border: none; padding: 0; cursor: pointer;
      text-align: left; width: 100%;
      font-family: inherit;
    }
    .user-link:hover .user-name { color: var(--accent); }
    .user-actions {
      display: flex; gap: 6px; margin-top: 6px;
    }
    .user-actions .btn-ghost {
      flex: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      padding: 6px 8px;
      font-size: 12px;
      min-height: 30px;
      border-radius: var(--r-sm);
    }

    .theme-toggle {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      padding: 8px 12px;
      background: transparent;
      border: 1px solid var(--border, rgba(0,0,0,0.08));
      border-radius: var(--r-md, 8px);
      color: var(--text-muted, var(--color-on-surface-dim));
      font-family: inherit;
      font-size: 13px;
      font-weight: 500;
      text-transform: none;
      letter-spacing: normal;
      cursor: pointer;
      transition: background 0.15s, color 0.15s, border-color 0.15s;
      min-height: 38px;
    }

    .theme-toggle:hover {
      background: var(--surface, rgba(0,0,0,0.04));
      color: var(--text, var(--color-on-surface));
    }

    .theme-icon {
      width: 16px;
      height: 16px;
      flex-shrink: 0;
    }

    .theme-label {
      flex: 1;
      text-align: left;
    }

    .theme-value {
      font-size: 12px;
      font-weight: 500;
      color: var(--text, var(--color-on-surface));
      opacity: 0.8;
    }

    .mobile-header {
      display: none;
    }

    .page-content {
      padding: 24px 32px;
      padding-bottom: 32px;
    }
  }

  @media (min-width: 1200px) {
    .sidebar {
      width: 260px;
    }
  }

  /* ── Mobile bottom nav ── */
  .nav-bottom {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--sidebar-bg, var(--color-surface));
    border-top: 1px solid var(--border, rgba(0,0,0,0.08));
    display: flex;
    justify-content: space-around;
    padding: 8px 4px;
    padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px));
    z-index: 100;
  }

  .nav-bottom button {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    background: none;
    border: none;
    color: var(--text-muted, var(--color-on-surface-dim));
    font-family: inherit;
    font-size: 10px;
    font-weight: 500;
    text-transform: none;
    letter-spacing: normal;
    padding: 4px 6px;
    min-height: 44px;
    flex: 1;
    cursor: pointer;
    border-radius: var(--r-md, 8px);
    transition: color 0.15s, background 0.15s;
  }

  .nav-bottom button.active {
    color: var(--accent, var(--color-primary));
  }

  .nav-bottom button.active svg {
    color: var(--accent, var(--color-primary));
  }

  @media (min-width: 768px) {
    .nav-bottom {
      display: none;
    }
  }

  /* Hide labels on very small screens, keep icons */
  @media (max-width: 380px) {
    .nav-bottom button span {
      display: none;
    }
  }

  .sk-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 200;
    display: flex; align-items: center; justify-content: center;
  }
  .sk-modal {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg);
    padding: 20px; max-width: 360px; box-shadow: 0 10px 32px rgba(0,0,0,0.2);
  }
  .sk-modal h3 { margin: 0 0 12px; font-size: 16px; }
  .sk-modal dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 12px; margin: 0 0 16px; font-size: 13px; }
  .sk-modal dt { display: flex; gap: 4px; }
  .sk-modal dd { margin: 0; color: var(--text-muted); }
  kbd {
    display: inline-block; padding: 2px 6px; border: 1px solid var(--border);
    border-bottom-width: 2px; border-radius: 4px; font-size: 11px; font-family: var(--font-mono);
    background: var(--surface-2, var(--surface));
  }

  .whatsnew-banner {
    position: sticky;
    top: 0;
    z-index: 99;
    background: linear-gradient(90deg, rgba(201,100,66,0.12), rgba(201,100,66,0.04));
    border-bottom: 1px solid var(--accent);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
  }
  .wn-icon { font-size: 16px; }
  .wn-text { flex: 1; color: var(--text); }
  .wn-dismiss {
    background: transparent; border: none; color: var(--text-muted);
    font-size: 20px; cursor: pointer; padding: 0 6px;
  }
  .wn-dismiss:hover { color: var(--text); }

  .ios-hint {
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: var(--r-lg, 12px);
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    box-shadow: 0 10px 28px rgba(0,0,0,0.18);
    z-index: 101;
    font-size: 14px;
    max-width: 92vw;
  }
  .ios-icon { font-size: 20px; }
  .ios-text { flex: 1; line-height: 1.4; }
  .ios-share-icon {
    display: inline-flex; vertical-align: middle;
    color: var(--accent);
    margin: 0 2px;
  }

  .install-banner {
    position: fixed;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: var(--r-lg, 12px);
    padding: 10px 14px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    z-index: 100;
    font-size: 14px;
    max-width: 90vw;
  }
  .install-actions { display: flex; gap: 8px; align-items: center; }
  .install-btn {
    background: var(--accent);
    color: white;
    border: none;
    padding: 6px 14px;
    border-radius: var(--r-md, 8px);
    font-weight: 600;
    cursor: pointer;
  }
  .install-dismiss {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 20px;
    line-height: 1;
    cursor: pointer;
    padding: 0 4px;
  }
</style>
