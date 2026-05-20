<script lang="ts">
  // Lightweight pull-to-refresh wrapper. Mobile-only (touch events).
  // Usage: <PullRefresh onrefresh={async () => { await reload(); }}>...content...</PullRefresh>

  let { onrefresh, threshold = 70, children } = $props<{
    onrefresh: () => Promise<void> | void;
    threshold?: number;
    children: any;
  }>();

  let startY = 0;
  let pullY = $state(0);
  let pulling = $state(false);
  let refreshing = $state(false);

  function onTouchStart(e: TouchEvent) {
    if (refreshing) return;
    if (window.scrollY > 4) return;
    startY = e.touches[0].clientY;
    pulling = true;
  }
  function onTouchMove(e: TouchEvent) {
    if (!pulling || refreshing) return;
    const dy = e.touches[0].clientY - startY;
    if (dy > 0) {
      pullY = Math.min(dy, threshold * 1.5);
      if (window.scrollY === 0) e.preventDefault();
    }
  }
  async function onTouchEnd() {
    if (!pulling) return;
    pulling = false;
    if (pullY >= threshold) {
      refreshing = true;
      try { await onrefresh(); } finally {
        refreshing = false;
        pullY = 0;
      }
    } else {
      pullY = 0;
    }
  }
</script>

<div
  class="ptr-wrap"
  ontouchstart={onTouchStart}
  ontouchmove={onTouchMove}
  ontouchend={onTouchEnd}
  ontouchcancel={onTouchEnd}
>
  <div class="ptr-indicator" style="height: {pullY}px" class:spin={refreshing}>
    {#if refreshing}↻ Refreshing…
    {:else if pullY >= threshold}↑ Release to refresh
    {:else if pullY > 0}↓ Pull to refresh
    {/if}
  </div>
  <div style="transform: translateY({pullY}px); transition: {pulling ? 'none' : 'transform 0.25s'}">
    {@render children()}
  </div>
</div>

<style>
  .ptr-wrap { position: relative; }
  .ptr-indicator {
    position: absolute; top: -2px; left: 0; right: 0;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-muted); font-size: 13px; overflow: hidden;
    transition: height 0.05s linear;
  }
  .ptr-indicator.spin { animation: ptr-spin 1s linear infinite; }
  @keyframes ptr-spin { from { opacity: 0.6; } to { opacity: 1; } }
</style>
