<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { theme, initTheme, toggleTheme } from '$lib/theme';
  import { auth } from '$lib/auth.svelte';

  let { children } = $props();

  const currentPath = $derived($page.url.pathname);
  const isLoginRoute = $derived(currentPath === '/login');

  const tabs = [
    { path: '/upload', label: 'Upload', key: 'upload' },
    { path: '/queue',  label: 'Queue',  key: 'queue'  },
    { path: '/chat',   label: 'Agent',  key: 'chat'   },
    { path: '/data',   label: 'Data',   key: 'data'   },
    { path: '/sync',   label: 'Sync',   key: 'sync'   },
    { path: '/more',   label: 'More',   key: 'more'   }
  ] as const;

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
</script>

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
        </button>
      {/each}

      {#if auth.isAdmin}
        <button
          class="nav-item"
          class:active={currentPath.startsWith('/users')}
          onclick={() => navigateTo('/users')}
          aria-label="Users"
        >
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          <span class="nav-label">Users</span>
        </button>
      {/if}
    </nav>

    <div class="sidebar-footer">
      {#if auth.user}
        <div class="user-card">
          <div class="user-name" title={auth.user.name}>{auth.user.name}</div>
          <div class="user-meta" title={auth.user.email || auth.user.phone_e164 || ''}>
            {auth.user.email || auth.user.phone_e164 || ''}
          </div>
          <button class="btn-ghost xs signout-btn" onclick={onSignOut}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Sign out
          </button>
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
        </button>
      {/each}
    </nav>
  </div>
</div>
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
