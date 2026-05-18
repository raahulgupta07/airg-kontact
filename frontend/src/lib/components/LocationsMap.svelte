<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import * as api from '$lib/api';

  let mapEl: HTMLDivElement;
  let map: any;
  let points: api.MapPoint[] = $state([]);
  let locations: api.LocationStat[] = $state([]);
  let error = $state('');

  onMount(async () => {
    try {
      const L = (await import('leaflet')).default;
      await import('leaflet/dist/leaflet.css');
      map = L.map(mapEl).setView([22.5, 114], 5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap',
        maxZoom: 19
      }).addTo(map);
      try {
        points = await api.getMapPoints();
      } catch { points = []; }
      try {
        locations = await api.getLocations();
      } catch { locations = []; }
      points.forEach((p) => {
        L.marker([p.lat, p.lng])
          .addTo(map)
          .bindPopup(
            `<strong>${p.company || p.source_file || ''}</strong><br>${p.city || ''}, ${p.country || ''}`
          );
      });
      if (points.length) {
        const lats = points.map((p) => p.lat);
        const lngs = points.map((p) => p.lng);
        map.fitBounds(
          [
            [Math.min(...lats), Math.min(...lngs)],
            [Math.max(...lats), Math.max(...lngs)]
          ],
          { padding: [40, 40] }
        );
      }
    } catch (e: any) {
      error = e?.message || 'Map failed to load';
    }
  });
  onDestroy(() => {
    if (map) map.remove();
  });
</script>

<div class="locations-wrap">
  <div bind:this={mapEl} class="map"></div>
  <aside class="map-side">
    <h3>By location</h3>
    {#each locations as loc}
      <div class="loc-row">
        <div><strong>{loc.city || 'Unknown'}</strong> · {loc.country || ''}</div>
        <span class="chip chip-accent">{loc.doc_count}</span>
      </div>
    {/each}
    {#if !locations.length}
      <p class="muted">No GPS data yet. Upload photos with location to populate.</p>
    {/if}
    {#if error}<p class="muted">{error}</p>{/if}
  </aside>
</div>

<style>
  .locations-wrap {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: 16px;
    min-height: 600px;
  }
  @media (max-width: 900px) {
    .locations-wrap { grid-template-columns: 1fr; }
    .map-side { max-height: 400px; overflow: auto; }
  }
  .map {
    border-radius: var(--r-lg);
    border: 1px solid var(--border);
    min-height: 600px;
  }
  .map-side {
    padding: 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
  }
  .map-side h3 {
    margin: 0 0 12px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .loc-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
  }
  .muted { color: var(--text-faint); font-size: 13px; }
</style>
