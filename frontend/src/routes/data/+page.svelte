<script>
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import * as api from '$lib/api';
  import { shortDate, relativeDate } from '$lib/utils';
  import { buildMessengerLinks, messengerIcon } from '$lib/messenger';
  import ProductsTable from '$lib/components/ProductsTable.svelte';
  import ContactsTable from '$lib/components/ContactsTable.svelte';
  import CompaniesTable from '$lib/components/CompaniesTable.svelte';
  import CategoriesTable from '$lib/components/CategoriesTable.svelte';
  import SpecsTable from '$lib/components/SpecsTable.svelte';
  import Gallery from '$lib/components/Gallery.svelte';
  import LocationsMap from '$lib/components/LocationsMap.svelte';
  import Timeline from '$lib/components/Timeline.svelte';
  import Countries from '$lib/components/Countries.svelte';
  import Messengers from '$lib/components/Messengers.svelte';
  import QrCodes from '$lib/components/QrCodes.svelte';
  import Quality from '$lib/components/Quality.svelte';
  import Duplicates from '$lib/components/Duplicates.svelte';
  import SyncSources from '$lib/components/SyncSources.svelte';
  import Cameras from '$lib/components/Cameras.svelte';
  import Pricing from '$lib/components/Pricing.svelte';
  import Tags from '$lib/components/Tags.svelte';
  import Notes from '$lib/components/Notes.svelte';
  import Meetings from '$lib/components/Meetings.svelte';
  import MergeProposals from '$lib/components/MergeProposals.svelte';
  import MergeClusters from '$lib/components/MergeClusters.svelte';
  import AuditLog from '$lib/components/AuditLog.svelte';

  const API = '';

  // ---- Tabs (grouped into sections) ----
  const SECTION_TABS = {
    catalog: ['cards','contacts','products','companies','categories','specs','gallery'],
    insights: ['locations','timeline','countries','messengers','qr','quality','duplicates','sync','cameras','pricing'],
    workspace: ['tags','notes','meetings','merges','audit']
  };
  const SECTIONS = ['catalog','insights','workspace'];
  const SECTION_LABELS = { catalog: 'Catalog', insights: 'Insights', workspace: 'Workspace' };
  const TABS = [...SECTION_TABS.catalog, ...SECTION_TABS.insights, ...SECTION_TABS.workspace];
  const TAB_TO_SECTION = {};
  for (const s of SECTIONS) for (const t of SECTION_TABS[s]) TAB_TO_SECTION[t] = s;

  const TAB_LABELS = {
    cards: 'Cards', contacts: 'Contacts', products: 'Products',
    companies: 'Companies', categories: 'Categories', specs: 'Specs', gallery: 'Gallery',
    locations: '📍 Locations', timeline: '🗓 Timeline', countries: '🌍 Countries',
    messengers: '💬 Messengers', qr: '🔗 QR', quality: '⚠ Quality',
    duplicates: '🔁 Duplicates', sync: '📨 Sources', cameras: '📷 Cameras',
    pricing: '💰 Pricing', tags: '🏷 Tags', notes: '📝 Notes', meetings: '🤝 Meetings',
    merges: '🔀 Pending Merges', audit: '📜 Audit Log'
  };
  let activeTab = $state('cards');
  let activeSection = $state('catalog');

  $effect(() => {
    const s = TAB_TO_SECTION[activeTab];
    if (s) activeSection = s;
  });

  function setTab(t) {
    if (!TABS.includes(t)) return;
    activeTab = t;
    try { history.replaceState(null, '', `#${t}`); } catch {}
  }

  function selectSection(s) {
    if (!SECTION_TABS[s]) return;
    activeSection = s;
    setTab(SECTION_TABS[s][0]);
  }

  // ---- Modal/Edit state ----
  let editContact = $state(null);
  let editProduct = $state(null);
  let mergePicker = $state(null);
  let mergeTarget = $state('');
  let rescanBusy = $state({});
  let toast = $state('');

  function showToast(msg) { toast = msg; setTimeout(() => toast = '', 2400); }

  // ── Double-confirm delete ──────────────────────────────────────────
  let deleteTarget = $state(null);       // doc pending delete
  let deleteConfirmText = $state('');    // user must type DELETE
  let deleting = $state(false);

  function requestDelete(doc) {
    deleteTarget = doc;
    deleteConfirmText = '';
  }
  function cancelDelete() { deleteTarget = null; deleteConfirmText = ''; }

  async function confirmDelete() {
    if (!deleteTarget || deleteConfirmText.trim().toUpperCase() !== 'DELETE') return;
    deleting = true;
    try {
      const r = await fetch(`/api/documents/${deleteTarget.uuid}`, {
        method: 'DELETE', credentials: 'include',
      });
      if (r.ok) {
        showToast('Deleted');
        // remove from local lists
        docs = docs.filter(d => d.uuid !== deleteTarget.uuid);
        applyFilters();
        deleteTarget = null;
        deleteConfirmText = '';
      } else if (r.status === 403) {
        showToast('Not allowed — only the uploader or an admin can delete');
      } else if (r.status === 404) {
        showToast('Already deleted');
        docs = docs.filter(d => d.uuid !== deleteTarget.uuid);
        applyFilters();
        deleteTarget = null;
      } else {
        showToast('Delete failed: ' + r.status);
      }
    } catch (e) {
      showToast('Delete error: ' + e.message);
    } finally {
      deleting = false;
    }
  }

  // Editor opened from card view (uses doc + nested contact)
  function openContactEditor(doc) {
    const c = doc.contact || {};
    editContact = {
      doc_uuid: doc.uuid,
      uuid: c.uuid || doc.uuid,
      fields: {
        company: doc.company || c.company || '',
        person: c.person || '',
        phone: c.phone || '',
        email: c.email || '',
        website: c.website || '',
        address: c.address || '',
        wechat_id: c.wechat_id || c.wechat || '',
        whatsapp: c.whatsapp || '',
        telegram: c.telegram || c.telegram_id || '',
        line_id: c.line_id || c.line || '',
        viber: c.viber || '',
        signal: c.signal || '',
        zalo: c.zalo || ''
      }
    };
  }

  // Editor opened from contacts table (flat row)
  function openContactEditorFromRow(c) {
    editContact = {
      uuid: c.uuid,
      fields: {
        company: c.company || '',
        person: c.person || c.name || '',
        phone: c.phone || '',
        email: c.email || '',
        website: c.website || '',
        address: c.address || '',
        wechat_id: c.wechat_id || '',
        whatsapp: c.whatsapp || '',
        telegram: c.telegram || '',
        line_id: c.line_id || '',
        viber: c.viber || '',
        signal: c.signal || '',
        zalo: c.zalo || ''
      }
    };
  }

  function openProductEditor(prod, doc) {
    editProduct = {
      uuid: prod.uuid || '',
      doc_uuid: doc?.uuid,
      fields: {
        name: prod.name || '',
        model: prod.model || '',
        specs: typeof prod.specs === 'string' ? prod.specs : JSON.stringify(prod.specs || ''),
        category: prod.category || '',
        price: prod.price || ''
      }
    };
  }

  function openProductEditorFromRow(p) {
    editProduct = {
      uuid: p.uuid || '',
      fields: {
        name: p.name || '',
        model: p.model || '',
        specs: typeof p.specs === 'string' ? p.specs : '',
        category: p.category || '',
        price: p.price || ''
      }
    };
  }

  async function saveContact() {
    if (!editContact) return;
    try {
      await api.updateContact(editContact.uuid, editContact.fields);
      showToast('Contact saved');
      editContact = null;
      reloadDocs();
      reloadTables();
    } catch (e) { showToast('Save failed: ' + e.message); }
  }

  async function saveProduct() {
    if (!editProduct) return;
    try {
      await api.updateProduct(editProduct.uuid, editProduct.fields);
      showToast('Product saved');
      editProduct = null;
      reloadDocs();
      reloadTables();
    } catch (e) { showToast('Save failed: ' + e.message); }
  }

  async function doDownloadVcard(contactUuid) {
    try { await api.downloadVcard(contactUuid); }
    catch (e) { showToast('vCard failed: ' + e.message); }
  }

  function openMergePicker(uuid) {
    mergePicker = { keepUuid: uuid };
    mergeTarget = '';
  }

  async function doMerge() {
    if (!mergePicker || !mergeTarget.trim()) return;
    try {
      await api.mergeContacts(mergePicker.keepUuid, mergeTarget.trim());
      showToast('Merged');
      mergePicker = null;
      reloadDocs();
      reloadTables();
    } catch (e) { showToast('Merge failed: ' + e.message); }
  }

  async function doRescanQr(docId) {
    rescanBusy = { ...rescanBusy, [docId]: true };
    try {
      const r = await api.rescanQr(docId);
      showToast(r.message || 'QR rescanned');
      reloadDocs();
    } catch (e) { showToast('Rescan failed: ' + e.message); }
    finally { rescanBusy = { ...rescanBusy, [docId]: false }; }
  }

  async function reloadDocs() {
    try {
      const res = await fetch(`${API}/api/data`);
      const raw = await res.json();
      docs = (Array.isArray(raw) ? raw : []).map(d => ({
        ...d,
        products: tryParse(d.products) || [],
        contact: tryParse(d.contact) || {},
        key_info: tryParse(d.key_info) || []
      }));
      applyFilters();
    } catch {}
  }

  // ---- Card view state ----
  let docs = $state([]);
  let filtered = $state([]);
  let expandedId = $state(null);
  // Lightbox for data card thumbnails
  let lightboxDoc = $state(null);
  function openImageLightbox(doc, e) {
    if (e) { e.stopPropagation(); e.preventDefault(); }
    lightboxDoc = doc;
  }
  function closeLightbox() { lightboxDoc = null; }
  function onLightboxKey(e) {
    if (e.key === 'Escape') closeLightbox();
  }
  let loading = $state(true);

  let folderFilter = $state('All');
  let typeFilter = $state('All');
  let sortOption = $state('newest');
  let folders = $state([]);
  let imageTypes = $state([]);
  let copyFeedback = $state({});

  // ---- Table data state ----
  let products = $state([]);
  let contacts = $state([]);
  let companies = $state([]);
  let documentsMeta = $state([]);

  let categoryBreakdown = $derived.by(() => {
    const map = new Map();
    for (const p of products) {
      const cat = p.category || 'Uncategorized';
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat).push(p.name || 'Unnamed');
    }
    return Array.from(map.entries())
      .map(([category, names]) => ({
        category,
        count: names.length,
        examples: names.slice(0, 3).join(', ')
      }))
      .sort((a, b) => b.count - a.count);
  });

  function tryParse(val) {
    if (!val) return val;
    if (typeof val === 'string') { try { return JSON.parse(val); } catch { return val; } }
    return val;
  }

  function formatTimestamp(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ', ' +
           d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  }

  function applySorting(arr) {
    const sorted = [...arr];
    switch (sortOption) {
      case 'newest':
        sorted.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
        break;
      case 'oldest':
        sorted.sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
        break;
      case 'type':
        sorted.sort((a, b) => (a.image_type || '').localeCompare(b.image_type || ''));
        break;
      case 'company':
        sorted.sort((a, b) => (a.company || '').localeCompare(b.company || ''));
        break;
      case 'folder':
        sorted.sort((a, b) => (a.folder || '').localeCompare(b.folder || ''));
        break;
    }
    return sorted;
  }

  async function reloadTables() {
    try {
      const [p, c, dash, dm] = await Promise.all([
        fetch(`${API}/api/products`).then(r => r.json()).catch(() => []),
        fetch(`${API}/api/contacts`).then(r => r.json()).catch(() => []),
        fetch(`${API}/api/dashboard`).then(r => r.json()).catch(() => ({})),
        fetch(`${API}/api/documents/metadata`).then(r => r.json()).catch(() => [])
      ]);
      products = (Array.isArray(p) ? p : []).map(pp => ({
        uuid: pp.uuid || '',
        company: pp.company || '',
        name: pp.name || pp.product_name || '',
        model: pp.model || '',
        specs: pp.specs || '',
        category: pp.category || '',
        price: pp.price || '',
        folder: pp.folder || '',
        created_at: pp.created_at || '',
        updated_at: pp.updated_at || '',
        owner_uuid: pp.owner_uuid || '',
        owner_name: pp.owner_name || '',
        source_channel: pp.source_channel || '',
        edit_count: pp.edit_count || 0
      }));
      contacts = Array.isArray(c) ? c : (c.contacts || c.data || []);
      companies = dash?.companies_with_counts || [];
      documentsMeta = Array.isArray(dm) ? dm : [];
    } catch (e) { console.error('Failed to load tables', e); }
  }

  onMount(async () => {
    // hash sync
    const h = location.hash.slice(1);
    if (TABS.includes(h)) activeTab = h;
    window.addEventListener('hashchange', () => {
      const h2 = location.hash.slice(1);
      if (TABS.includes(h2)) activeTab = h2;
    });

    try {
      const res = await fetch(`${API}/api/data`);
      const raw = await res.json();
      docs = (Array.isArray(raw) ? raw : []).map(d => ({
        ...d,
        products: tryParse(d.products) || [],
        contact: tryParse(d.contact) || {},
        key_info: tryParse(d.key_info) || []
      }));

      const folderSet = new Set();
      const typeSet = new Set();
      for (const d of docs) {
        if (d.folder) folderSet.add(d.folder);
        if (d.image_type) typeSet.add(d.image_type);
      }
      folders = [...folderSet].sort();
      imageTypes = [...typeSet].sort();

      applyFilters();
    } catch (e) {
      console.error('Failed to load data:', e);
    } finally {
      loading = false;
    }

    // load table data in parallel (non-blocking)
    reloadTables();
  });

  let cardSearch = $state('');

  function _docMatchesSearch(d, q) {
    if (!q) return true;
    const hay = [
      d.company, d.title, d.source_file, d.folder, d.image_type, d.trade_show,
      d.raw_text, d.country, d.city,
    ];
    // products + contact JSON
    let prods = d.products;
    if (typeof prods === 'string') { try { prods = JSON.parse(prods); } catch { prods = []; } }
    if (Array.isArray(prods)) for (const p of prods) hay.push(p?.name, p?.product_name, p?.model, p?.category, p?.price);
    let c = d.contact;
    if (typeof c === 'string') { try { c = JSON.parse(c); } catch { c = {}; } }
    if (c) hay.push(c.person, c.phone, c.email, c.website, c.company);
    return hay.some(v => v && String(v).toLowerCase().includes(q));
  }

  function applyFilters() {
    const q = cardSearch.trim().toLowerCase();
    let result = docs.filter(d => {
      if (folderFilter !== 'All' && d.folder !== folderFilter) return false;
      if (typeFilter !== 'All' && d.image_type !== typeFilter) return false;
      if (q && !_docMatchesSearch(d, q)) return false;
      return true;
    });
    filtered = applySorting(result);
  }

  let _searchDebounce;
  function onCardSearch(e) {
    cardSearch = e.target.value;
    clearTimeout(_searchDebounce);
    _searchDebounce = setTimeout(applyFilters, 180);
  }
  function onFolderChange(e) { folderFilter = e.target.value; applyFilters(); }
  function onTypeChange(e) { typeFilter = e.target.value; applyFilters(); }
  function onSortChange(e) { sortOption = e.target.value; applyFilters(); }
  function toggleExpand(id) { expandedId = expandedId === id ? null : id; }

  let showRawText = $state({});
  let showJson = $state({});
  function toggleRaw(id) { showRawText = { ...showRawText, [id]: !showRawText[id] }; }
  function toggleJson(id) { showJson = { ...showJson, [id]: !showJson[id] }; }

  async function copyDocText(doc, docId) {
    const lines = [];
    lines.push(`Title: ${doc.title || doc.source_file || 'Untitled'}`);
    if (doc.company) lines.push(`Company: ${doc.company}`);
    lines.push(`Type: ${doc.image_type || 'unknown'}`);
    lines.push(`Source: ${doc.source_file} / ${doc.folder}`);
    if (doc.created_at) lines.push(`Created: ${formatTimestamp(doc.created_at)}`);
    if (doc.products?.length) {
      lines.push('\nProducts:');
      for (const p of doc.products) {
        lines.push(`  - ${p.name || 'Unnamed'}${p.model ? ' (' + p.model + ')' : ''}${p.category ? ' [' + p.category + ']' : ''}`);
      }
    }
    if (doc.contact && Object.values(doc.contact).some(v => v)) {
      lines.push('\nContact:');
      for (const [k, v] of Object.entries(doc.contact)) {
        if (v) lines.push(`  ${k}: ${v}`);
      }
    }
    if (doc.key_info?.length) {
      lines.push('\nKey Info:');
      for (const info of doc.key_info) lines.push(`  - ${info}`);
    }
    if (doc.raw_text) lines.push(`\nRaw Text:\n${doc.raw_text}`);
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      copyFeedback = { ...copyFeedback, [docId]: true };
      setTimeout(() => { copyFeedback = { ...copyFeedback, [docId]: false }; }, 1500);
    } catch (e) {
      console.error('Copy failed', e);
    }
  }

  function saveJson(doc) {
    const json = JSON.stringify(doc, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(doc.source_file || 'document').replace(/\.[^.]+$/, '')}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
</script>

<svelte:head><title>Data | KONTACT</title></svelte:head>

<div class="page">
  <header class="page-head">
    <div class="head-left">
      <h1 class="page-title">Data browser</h1>
      {#if activeTab === 'cards'}
        <span class="head-count">{filtered.length} of {docs.length} documents</span>
      {/if}
    </div>
    <div class="head-right">
      {#if activeTab === 'cards'}
        <select class="input sort-select" onchange={onSortChange} value={sortOption}>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="type">By type</option>
          <option value="company">By company</option>
          <option value="folder">By folder</option>
        </select>
      {/if}
      <a class="xl-btn" href={`/api/export/xlsx?tab=${activeTab}`} title="Download as Excel">
        ⬇ Excel
      </a>
    </div>
  </header>

  <!-- TAB STRIP (grouped) -->
  <div class="nav-stack">
    <div class="section-bar" role="tablist" aria-label="Sections">
      {#each SECTIONS as s}
        <button
          class="section-pill"
          class:active={activeSection === s}
          onclick={() => selectSection(s)}
          role="tab"
          aria-selected={activeSection === s}
        >{SECTION_LABELS[s]}</button>
      {/each}
    </div>
    <div class="subtabs" role="tablist" aria-label="Sub tabs">
      {#each SECTION_TABS[activeSection] as t}
        <button
          class="subtab"
          class:active={activeTab === t}
          onclick={() => setTab(t)}
          role="tab"
          aria-selected={activeTab === t}
        >{TAB_LABELS[t]}</button>
      {/each}
    </div>
  </div>

  {#if activeTab === 'cards'}
    <div class="filter-bar">
      <div class="filter-group grow">
        <label>Search</label>
        <input
          type="search"
          class="input"
          placeholder="Search company, person, product, file, text…"
          value={cardSearch}
          oninput={onCardSearch}
        />
      </div>
      <div class="filter-group">
        <label>Folder</label>
        <select class="input" onchange={onFolderChange} value={folderFilter}>
          <option value="All">All folders</option>
          {#each folders as f}<option value={f}>{f}</option>{/each}
        </select>
      </div>
      <div class="filter-group">
        <label>Type</label>
        <select class="input" onchange={onTypeChange} value={typeFilter}>
          <option value="All">All types</option>
          {#each imageTypes as t}<option value={t}>{t}</option>{/each}
        </select>
      </div>
    </div>
    {#if cardSearch.trim()}
      <p class="search-count">{filtered.length} match{filtered.length === 1 ? '' : 'es'} for "{cardSearch.trim()}"</p>
    {/if}

    {#if loading}
      <div class="loading">Loading documents...</div>
    {:else if filtered.length === 0}
      <div class="loading">No documents found.</div>
    {:else}
      <div class="card-list">
        {#each filtered as doc, i}
          {@const docId = doc.id ?? i}
          <div class="card doc-card" class:expanded={expandedId === docId}>
            <button class="card-header" onclick={() => toggleExpand(docId)}>
              <div class="card-header-row">
                <!-- svelte-ignore a11y_click_events_have_key_events -->
                <!-- svelte-ignore a11y_no_static_element_interactions -->
                <img
                  src={`/api/thumb/${doc.folder}/${doc.source_file}?w=256`}
                  alt={doc.source_file}
                  class="card-thumb clickable"
                  loading="lazy"
                  decoding="async"
                  onclick={(e) => openImageLightbox(doc, e)}
                  onerror={(e) => e.target.style.display='none'}
                />
                <div class="card-header-info">
                  <div class="card-top-row">
                    <span class="chip chip-accent">{doc.image_type || 'unknown'}</span>
                    <span class="card-index">#{i + 1}</span>
                  </div>
                  <h3 class="card-title">{doc.title || doc.source_file || 'Untitled'}</h3>
                  {#if doc.company}<p class="card-company">{doc.company}</p>{/if}
                  <p class="card-source">{doc.source_file} · {doc.folder}</p>
                  <div class="card-meta-row">
                    {#if doc.img_width && doc.img_height}<span class="meta-tag">{doc.img_width}x{doc.img_height}</span>{/if}
                    {#if doc.file_size_kb}<span class="meta-tag">{doc.file_size_kb} KB</span>{/if}
                    {#if doc.uuid}<span class="meta-tag uuid">{doc.uuid.slice(0, 8)}</span>{/if}
                    {#if doc.gps_lat && doc.gps_lng}<span class="meta-tag gps">{doc.gps_lat}, {doc.gps_lng}</span>{/if}
                    {#if doc.date_taken}<span class="meta-tag">{doc.date_taken}</span>{/if}
                    {#if doc.camera_make}<span class="meta-tag">{doc.camera_make} {doc.camera_model || ''}</span>{/if}
                    {#if doc.gps_lat}
                      <span class="meta-chip">&#128205; {doc.city || `${doc.gps_lat.toFixed(3)}, ${doc.gps_lng.toFixed(3)}`}</span>
                    {/if}
                    {#if doc.country}<span class="meta-chip">&#127757; {doc.country}</span>{/if}
                    {#if doc.camera_model}<span class="meta-chip">&#128247; {doc.camera_model}</span>{/if}
                    {#if doc.lens_model}<span class="meta-chip">&#128270; {doc.lens_model}</span>{/if}
                    {#if doc.iso}<span class="meta-chip">ISO {doc.iso}</span>{/if}
                    {#if doc.f_number}<span class="meta-chip">f/{doc.f_number}</span>{/if}
                    {#if doc.exposure_time}<span class="meta-chip">{doc.exposure_time}s</span>{/if}
                    {#if doc.focal_length}<span class="meta-chip">{doc.focal_length}mm</span>{/if}
                    {#if doc.software}<span class="meta-chip">{doc.software}</span>{/if}
                    {#if doc.is_blurry}<span class="meta-chip warn">&#9888; Blurry</span>{/if}
                    {#if doc.near_dup_of}<span class="meta-chip warn">&#128257; Near-duplicate</span>{/if}
                  </div>
                  {#if doc.created_at}
                    <p class="card-timestamp">{formatTimestamp(doc.created_at)}</p>
                  {/if}
                  {#if doc.owner_name || doc.created_at || doc.updated_at || doc.source_channel || doc.edit_count}
                    <div class="card-audit">
                      {#if doc.owner_name}<span class="audit-label">By</span> <strong>{doc.owner_name}</strong>{/if}
                      {#if doc.created_at}<span class="audit-sep">·</span><span>{shortDate(doc.created_at)}</span>{/if}
                      {#if doc.updated_at && doc.updated_at !== doc.created_at}
                        <span class="audit-sep">·</span><span>edited {relativeDate(doc.updated_at)}</span>
                      {/if}
                      {#if doc.source_channel}<span class="audit-sep">·</span><span class="src-chip src-{doc.source_channel}">{doc.source_channel}</span>{/if}
                      {#if doc.edit_count > 0}<span class="audit-sep">·</span><span class="muted">{doc.edit_count} edit{doc.edit_count === 1 ? '' : 's'}</span>{/if}
                    </div>
                  {/if}
                </div>
              </div>
            </button>

            {#if expandedId === docId}
              <div class="card-details">
                <div class="action-bar">
                  <button class="btn-ghost sm" onclick={() => copyDocText(doc, docId)}>
                    {copyFeedback[docId] ? 'Copied' : 'Copy'}
                  </button>
                  <button class="btn-ghost sm" onclick={() => saveJson(doc)}>Save JSON</button>
                  <button class="btn-ghost sm" onclick={() => doRescanQr(docId)} disabled={rescanBusy[docId]}>
                    {rescanBusy[docId] ? 'Scanning...' : 'Rescan QR'}
                  </button>
                  {#if doc.contact && (doc.contact.phone || doc.contact.email || doc.contact.person)}
                    <button class="btn-ghost sm" onclick={() => doDownloadVcard(doc.contact?.uuid || doc.uuid)}>Download .vcf</button>
                  {/if}
                  <button class="btn-danger sm" onclick={() => requestDelete(doc)}>🗑 Delete</button>
                </div>

                <div class="detail-section">
                  <h4>File info</h4>
                  <div class="meta-grid">
                    {#if doc.uuid}<div class="meta-item"><span class="meta-label">UUID</span><span class="meta-value">{doc.uuid}</span></div>{/if}
                    {#if doc.img_width}<div class="meta-item"><span class="meta-label">Dimensions</span><span class="meta-value">{doc.img_width} x {doc.img_height} px</span></div>{/if}
                    {#if doc.file_size_kb}<div class="meta-item"><span class="meta-label">File size</span><span class="meta-value">{doc.file_size_kb} KB</span></div>{/if}
                    {#if doc.gps_lat && doc.gps_lng}<div class="meta-item"><span class="meta-label">GPS</span><span class="meta-value">{doc.gps_lat}, {doc.gps_lng}</span></div>{/if}
                    {#if doc.date_taken}<div class="meta-item"><span class="meta-label">Date taken</span><span class="meta-value">{doc.date_taken}</span></div>{/if}
                    {#if doc.camera_make}<div class="meta-item"><span class="meta-label">Camera</span><span class="meta-value">{doc.camera_make} {doc.camera_model || ''}</span></div>{/if}
                    {#if doc.created_at}<div class="meta-item"><span class="meta-label">Imported</span><span class="meta-value">{formatTimestamp(doc.created_at)}</span></div>{/if}
                    <div class="meta-item"><span class="meta-label">Folder</span><span class="meta-value">{doc.folder}</span></div>
                    <div class="meta-item"><span class="meta-label">Type</span><span class="meta-value">{doc.image_type}</span></div>
                  </div>
                </div>

                {#if doc.products?.length}
                  <div class="detail-section">
                    <h4>Products</h4>
                    {#each doc.products as prod}
                      <div class="product-item">
                        <div class="prod-head">
                          <strong>{prod.name || 'Unnamed product'}</strong>
                          {#if prod.uuid}
                            <button class="btn-ghost xs" onclick={() => openProductEditor(prod, doc)}>Edit</button>
                          {/if}
                        </div>
                        {#if prod.model}<div class="prod-field">Model: {prod.model}</div>{/if}
                        {#if prod.category}<div class="prod-field">Category: {prod.category}</div>{/if}
                        {#if prod.specs}
                          <div class="prod-field">Specs: {typeof prod.specs === 'string' ? prod.specs : JSON.stringify(prod.specs)}</div>
                        {/if}
                        {#if prod.price}<div class="prod-field">Price: {prod.price}</div>{/if}
                      </div>
                    {/each}
                  </div>
                {/if}

                {#if doc.contact && (doc.contact.phone || doc.contact.email || doc.contact.website || doc.contact.address || doc.contact.person)}
                  <div class="detail-section">
                    <div class="section-header">
                      <h4>Contact</h4>
                      <div class="contact-actions">
                        <button class="btn-ghost xs" onclick={() => openContactEditor(doc)}>Edit</button>
                        <button class="btn-ghost xs" onclick={() => openMergePicker(doc.contact?.uuid || doc.uuid)}>Merge</button>
                      </div>
                    </div>
                    {#if doc.contact.person}<div class="contact-item">Person: {doc.contact.person}</div>{/if}
                    {#if doc.contact.phone}<div class="contact-item">Phone: {doc.contact.phone}</div>{/if}
                    {#if doc.contact.email}<div class="contact-item">Email: {doc.contact.email}</div>{/if}
                    {#if doc.contact.website}<div class="contact-item">Website: {doc.contact.website}</div>{/if}
                    {#if doc.contact.address}<div class="contact-item">Address: {doc.contact.address}</div>{/if}

                    {#if doc.contact}
                      {@const links = buildMessengerLinks({ ...doc.contact, phone: doc.contact.phone, email: doc.contact.email })}
                      {#if links.length}
                        <div class="messenger-row">
                          {#each links as ln}
                            <a class="msg-chip" href={ln.url} target="_blank" rel="noopener" title={ln.label}>
                              {@html messengerIcon(ln.kind)}
                              <span class="msg-label">{ln.label}</span>
                            </a>
                          {/each}
                        </div>
                      {/if}
                    {/if}
                  </div>
                {/if}

                {#if doc.key_info?.length}
                  <div class="detail-section">
                    <h4>Key info</h4>
                    <ul class="key-info-list">
                      {#each doc.key_info as info}
                        <li>{info}</li>
                      {/each}
                    </ul>
                  </div>
                {/if}

                {#if doc.raw_text}
                  <div class="detail-section">
                    <button class="collapse-toggle" onclick={() => toggleRaw(docId)}>
                      {showRawText[docId] ? '−' : '+'} Raw text
                    </button>
                    {#if showRawText[docId]}
                      <div class="code-block">
                        <pre>{doc.raw_text}</pre>
                      </div>
                    {/if}
                  </div>
                {/if}

                <div class="detail-section">
                  <button class="collapse-toggle" onclick={() => toggleJson(docId)}>
                    {showJson[docId] ? '−' : '+'} Full JSON
                  </button>
                  {#if showJson[docId]}
                    <div class="code-block">
                      <pre>{JSON.stringify(doc, null, 2)}</pre>
                    </div>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {:else if activeTab === 'contacts'}
    <ContactsTable {contacts} onEdit={openContactEditorFromRow} onMerge={openMergePicker} />
  {:else if activeTab === 'products'}
    <ProductsTable {products} onEdit={openProductEditorFromRow} />
  {:else if activeTab === 'companies'}
    <CompaniesTable {companies} />
  {:else if activeTab === 'categories'}
    <CategoriesTable categories={categoryBreakdown} documents={docs} />
  {:else if activeTab === 'specs'}
    <SpecsTable specs={products} />
  {:else if activeTab === 'gallery'}
    <Gallery documents={docs} />
  {:else if activeTab === 'locations'}
    <LocationsMap />
  {:else if activeTab === 'timeline'}
    <Timeline />
  {:else if activeTab === 'countries'}
    <Countries />
  {:else if activeTab === 'messengers'}
    <Messengers />
  {:else if activeTab === 'qr'}
    <QrCodes />
  {:else if activeTab === 'quality'}
    <Quality />
  {:else if activeTab === 'duplicates'}
    <Duplicates />
  {:else if activeTab === 'sync'}
    <SyncSources />
  {:else if activeTab === 'cameras'}
    <Cameras />
  {:else if activeTab === 'pricing'}
    <Pricing />
  {:else if activeTab === 'tags'}
    <Tags />
  {:else if activeTab === 'notes'}
    <Notes />
  {:else if activeTab === 'meetings'}
    <Meetings />
  {:else if activeTab === 'merges'}
    <MergeClusters />
  {:else if activeTab === 'audit'}
    <AuditLog />
  {/if}
</div>

{#if toast}
  <div class="toast">{toast}</div>
{/if}

{#if deleteTarget}
  <div class="modal-backdrop" onclick={cancelDelete} role="button" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && cancelDelete()}>
    <div class="modal del-modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Confirm delete">
      <h3>⚠️ Delete this document?</h3>
      <p class="del-name">{deleteTarget.title || deleteTarget.company || deleteTarget.source_file || deleteTarget.uuid?.slice(0,8)}</p>
      <p class="del-warn">
        This permanently removes the document, its products, contacts, image file, and search index entry.
        <strong>This cannot be undone.</strong>
      </p>
      <p class="del-prompt">Type <code>DELETE</code> to confirm:</p>
      <input
        class="input"
        type="text"
        bind:value={deleteConfirmText}
        placeholder="DELETE"
        autocomplete="off"
        onkeydown={(e) => { if (e.key === 'Enter' && deleteConfirmText.trim().toUpperCase() === 'DELETE') confirmDelete(); }}
      />
      <div class="del-actions">
        <button class="btn-ghost" onclick={cancelDelete}>Cancel</button>
        <button
          class="btn-danger"
          disabled={deleting || deleteConfirmText.trim().toUpperCase() !== 'DELETE'}
          onclick={confirmDelete}
        >{deleting ? 'Deleting…' : 'Delete permanently'}</button>
      </div>
    </div>
  </div>
{/if}

{#if editContact}
  <div class="modal-backdrop" onclick={() => editContact = null} role="button" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (editContact = null)}>
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog">
      <div class="modal-head">
        <h3>Edit contact</h3>
        <button class="modal-close" onclick={() => editContact = null} aria-label="close">&times;</button>
      </div>
      <div class="modal-grid">
        {#each Object.keys(editContact.fields) as k}
          <label>{k.replace(/_/g, ' ')}
            <input class="input" bind:value={editContact.fields[k]} />
          </label>
        {/each}
      </div>
      <div class="modal-actions">
        <button class="btn-ghost" onclick={() => editContact = null}>Cancel</button>
        <button class="send-btn" onclick={saveContact}>Save</button>
      </div>
    </div>
  </div>
{/if}

{#if editProduct}
  <div class="modal-backdrop" onclick={() => editProduct = null} role="button" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (editProduct = null)}>
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog">
      <div class="modal-head">
        <h3>Edit product</h3>
        <button class="modal-close" onclick={() => editProduct = null} aria-label="close">&times;</button>
      </div>
      <div class="modal-grid">
        {#each Object.keys(editProduct.fields) as k}
          <label>{k}
            {#if k === 'specs'}
              <textarea class="input" rows="3" bind:value={editProduct.fields[k]}></textarea>
            {:else}
              <input class="input" bind:value={editProduct.fields[k]} />
            {/if}
          </label>
        {/each}
      </div>
      <div class="modal-actions">
        <button class="btn-ghost" onclick={() => editProduct = null}>Cancel</button>
        <button class="send-btn" onclick={saveProduct}>Save</button>
      </div>
    </div>
  </div>
{/if}

{#if mergePicker}
  <div class="modal-backdrop" onclick={() => mergePicker = null} role="button" tabindex="-1" onkeydown={(e) => e.key === 'Escape' && (mergePicker = null)}>
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog">
      <div class="modal-head">
        <h3>Merge contact</h3>
        <button class="modal-close" onclick={() => mergePicker = null} aria-label="close">&times;</button>
      </div>
      <p class="merge-hint">Keep: <code>{mergePicker.keepUuid.slice(0, 8)}</code>. Paste another contact UUID to merge into it.</p>
      <label class="modal-label-block">Other contact UUID
        <input class="input" bind:value={mergeTarget} placeholder="paste uuid to absorb" />
      </label>
      <div class="modal-actions">
        <button class="btn-ghost" onclick={() => mergePicker = null}>Cancel</button>
        <button class="send-btn" onclick={doMerge} disabled={!mergeTarget.trim()}>Merge</button>
      </div>
    </div>
  </div>
{/if}

<svelte:window onkeydown={onLightboxKey} />
{#if lightboxDoc}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="img-lb-backdrop" onclick={closeLightbox}>
    <div class="img-lb-modal" onclick={(e) => e.stopPropagation()}>
      <button class="img-lb-close" onclick={closeLightbox} aria-label="Close">×</button>
      <img class="img-lb-img" src={`/api/image/${lightboxDoc.folder}/${lightboxDoc.source_file}`} alt={lightboxDoc.source_file} />
      <div class="img-lb-foot">
        <span class="img-lb-name">{lightboxDoc.source_file}</span>
        <a class="img-lb-dl" href={`/api/image/${lightboxDoc.folder}/${lightboxDoc.source_file}`} download={lightboxDoc.source_file}>Download</a>
      </div>
    </div>
  </div>
{/if}

<style>
  .card-thumb.clickable { cursor: zoom-in; }
  .card-thumb.clickable:hover { box-shadow: 0 0 0 2px var(--accent); }
  .xl-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    background: var(--accent);
    color: white;
    text-decoration: none;
    border-radius: var(--r-md);
    font-size: 13px;
    font-weight: 600;
    border: 1px solid var(--accent);
  }
  .xl-btn:hover { filter: brightness(1.05); }
  .head-right { display: flex; gap: 8px; align-items: center; }

  .img-lb-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.78);
    display: flex; align-items: center; justify-content: center;
    z-index: 250; padding: 16px;
  }
  .img-lb-modal {
    position: relative;
    background: var(--surface);
    border-radius: var(--r-lg);
    overflow: hidden;
    max-width: 95vw;
    max-height: 95vh;
    box-shadow: 0 24px 64px rgba(0,0,0,0.5);
    display: flex; flex-direction: column;
  }
  .img-lb-img {
    max-width: 95vw;
    max-height: calc(95vh - 60px);
    object-fit: contain;
    background: #000;
    display: block;
  }
  .img-lb-close {
    position: absolute; top: 8px; right: 8px;
    width: 36px; height: 36px;
    background: rgba(0,0,0,0.55);
    color: white; border: none; border-radius: 50%;
    font-size: 22px; cursor: pointer; z-index: 3;
  }
  .img-lb-foot {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px;
    border-top: 1px solid var(--border);
  }
  .img-lb-name { flex: 1; font-size: 13px; word-break: break-all; }
  .img-lb-dl {
    background: var(--accent); color: white;
    padding: 6px 14px; border-radius: var(--r-sm);
    text-decoration: none; font-size: 12px; font-weight: 600;
  }

  .page {
    max-width: 1100px;
    margin: 0 auto;
    padding: 16px 16px 64px;
    font-family: var(--font-sans);
  }

  .page-head {
    display: flex; justify-content: space-between;
    align-items: flex-end; gap: 12px;
    margin-bottom: 16px; flex-wrap: wrap;
  }
  .head-left { display: flex; flex-direction: column; gap: 4px; }
  .page-title { margin: 0; font-size: 24px; font-weight: 600; color: var(--text); }
  .head-count { font-size: 13px; color: var(--text-muted); }

  .sort-select { min-width: 180px; width: auto; cursor: pointer; }

  /* Grouped tab strip */
  .nav-stack {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--bg);
    padding: 8px 0 4px;
    margin-bottom: 16px;
  }
  .section-bar {
    display: flex;
    gap: 6px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .section-pill {
    padding: 8px 18px;
    background: none;
    border: 1px solid transparent;
    border-radius: var(--r-pill);
    font-size: 14px;
    font-weight: 600;
    color: var(--text-muted);
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s, color 0.15s;
  }
  .section-pill:hover { color: var(--text); }
  .section-pill.active {
    background: var(--accent);
    color: #fff;
  }
  .subtabs {
    display: flex;
    gap: 2px;
    padding: 10px 0 0;
    overflow-x: auto;
    scrollbar-width: thin;
  }
  .subtab {
    padding: 7px 12px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-muted);
    background: none;
    border: none;
    border-radius: var(--r-md);
    cursor: pointer;
    white-space: nowrap;
    font-family: inherit;
    transition: background 0.15s, color 0.15s;
  }
  .subtab:hover { background: var(--surface-2); color: var(--text); }
  .subtab.active {
    background: var(--accent-soft);
    color: var(--accent);
  }

  .filter-bar {
    display: flex; gap: 12px;
    margin-bottom: 16px;
  }
  .filter-group {
    flex: 1; display: flex; flex-direction: column; gap: 4px;
  }
  .filter-group.grow { flex: 2; }
  .filter-group label {
    font-size: 12px; color: var(--text-muted); font-weight: 500;
  }
  .search-count { font-size: 12px; color: var(--text-muted); margin: -8px 0 12px; }

  .loading {
    text-align: center;
    padding: 48px 16px;
    color: var(--text-muted);
  }

  .card-list { display: flex; flex-direction: column; gap: 12px; }

  .doc-card { padding: 0; overflow: hidden; transition: box-shadow 0.15s, border-color 0.15s; }
  .doc-card.expanded { border-color: var(--border-strong); box-shadow: var(--shadow-md); }

  .card-header {
    display: block; width: 100%;
    text-align: left; background: none;
    border: none; padding: 14px 16px;
    cursor: pointer; font-family: inherit; font-size: inherit;
    color: var(--text);
  }
  .card-header:hover { background: var(--surface-2); }

  .card-header-row { display: flex; gap: 12px; align-items: flex-start; }
  .card-thumb {
    width: 64px; height: 64px;
    object-fit: cover;
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    flex-shrink: 0;
  }
  .card-header-info { flex: 1; min-width: 0; }

  .card-top-row {
    display: flex; justify-content: space-between;
    align-items: center; gap: 8px; margin-bottom: 4px;
  }
  .card-index { font-size: 12px; color: var(--text-faint); }

  .card-title { margin: 2px 0 0; font-size: 15px; line-height: 1.3; font-weight: 600; }
  .card-company { margin: 2px 0 0; font-size: 13px; color: var(--text-muted); font-weight: 500; }
  .card-source { margin: 2px 0 0; font-size: 12px; color: var(--text-faint); word-break: break-all; }
  .card-timestamp { margin: 4px 0 0; font-size: 11px; color: var(--text-faint); }

  .card-meta-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
  .meta-tag {
    font-size: 11px;
    padding: 2px 8px;
    background: var(--surface-2);
    border-radius: var(--r-pill);
    color: var(--text-muted);
    font-family: var(--font-mono);
  }
  .meta-tag.uuid { color: var(--accent); background: var(--accent-soft); }
  .meta-tag.gps { color: var(--success); background: rgba(90,143,61,0.12); }

  .meta-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    font-size: 11px;
    border-radius: var(--r-pill);
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text-muted);
    white-space: nowrap;
  }
  .meta-chip.warn { background: rgba(181,133,61,0.1); border-color: var(--warning); color: var(--warning); }

  .card-audit {
    font-size: 11px;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .audit-label { text-transform: uppercase; letter-spacing: 0.04em; font-size: 10px; opacity: 0.7; }
  .audit-sep { opacity: 0.4; }
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
  .muted { color: var(--text-muted); }

  .card-details {
    border-top: 1px solid var(--border);
    padding: 16px;
    background: var(--surface);
  }

  .action-bar {
    display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap;
  }
  .btn-ghost.sm { padding: 6px 12px; font-size: 12px; min-height: 30px; }
  .btn-ghost.xs { padding: 3px 8px; font-size: 11px; min-height: 24px; }
  .btn-danger {
    padding: 8px 14px; border-radius: var(--r-sm); cursor: pointer; font-family: inherit;
    background: transparent; border: 1px solid #d4564b; color: #d4564b; font-weight: 600;
  }
  .btn-danger:hover:not(:disabled) { background: #d4564b; color: white; }
  .btn-danger.sm { padding: 6px 12px; font-size: 12px; min-height: 30px; }
  .btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

  .del-modal { max-width: 420px; padding: 24px; }
  .del-modal h3 { margin: 0 0 12px; font-size: 17px; }
  .del-name { font-weight: 600; padding: 8px 10px; background: var(--surface-2, rgba(0,0,0,0.04)); border-radius: var(--r-sm); margin: 0 0 12px; word-break: break-word; }
  .del-warn { font-size: 13px; color: var(--text-muted); line-height: 1.5; margin: 0 0 14px; }
  .del-warn strong { color: #d4564b; }
  .del-prompt { font-size: 13px; margin: 0 0 6px; }
  .del-prompt code { background: var(--surface-2, rgba(0,0,0,0.06)); padding: 1px 6px; border-radius: 4px; font-weight: 700; }
  .del-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }

  .detail-section { margin-bottom: 16px; }
  .detail-section h4 {
    margin: 0 0 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
  }

  .product-item {
    padding: 10px 12px;
    margin-bottom: 6px;
    background: var(--surface-2);
    border-radius: var(--r-sm);
    font-size: 13px;
  }
  .prod-head {
    display: flex; justify-content: space-between;
    align-items: center; gap: 6px;
  }
  .prod-field { font-size: 12px; color: var(--text-muted); margin-top: 3px; }

  .contact-item { font-size: 13px; padding: 3px 0; color: var(--text); }

  .key-info-list { margin: 0; padding-left: 20px; font-size: 13px; color: var(--text); }
  .key-info-list li { margin-bottom: 3px; }

  .collapse-toggle {
    background: none; border: none;
    font-family: inherit; font-size: 13px;
    font-weight: 500; color: var(--text-muted);
    cursor: pointer; padding: 4px 0;
  }
  .collapse-toggle:hover { color: var(--text); }

  .code-block {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    padding: 10px 12px;
    margin-top: 6px;
    overflow-x: auto;
    max-height: 320px;
    overflow-y: auto;
  }
  .code-block pre {
    margin: 0; font-family: var(--font-mono);
    font-size: 12px; line-height: 1.5;
    white-space: pre-wrap; word-break: break-all;
    color: var(--text);
  }

  .meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .meta-item {
    display: flex; flex-direction: column; gap: 2px;
    padding: 6px 10px;
    background: var(--surface-2);
    border-radius: var(--r-sm);
  }
  .meta-label {
    font-size: 11px; font-weight: 500;
    color: var(--text-muted);
  }
  .meta-value {
    font-size: 13px;
    font-family: var(--font-mono);
    word-break: break-all;
    color: var(--text);
  }
  @media (max-width: 640px) { .meta-grid { grid-template-columns: 1fr; } }

  .messenger-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .msg-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px;
    background: var(--accent-soft);
    color: var(--accent-ink);
    font-size: 12px;
    font-weight: 500;
    text-decoration: none;
    border-radius: var(--r-pill);
    transition: background 0.15s;
  }
  .msg-chip:hover { background: var(--accent); color: #fff; }

  .section-header {
    display: flex; justify-content: space-between;
    align-items: center; gap: 6px; margin-bottom: 6px;
  }
  .section-header h4 { margin: 0; }
  .contact-actions { display: flex; gap: 4px; }

  /* Modal */
  .modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(44, 43, 38, 0.4);
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
    display: flex; align-items: center; justify-content: center;
    z-index: 300; padding: 16px;
  }
  .modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--shadow-lg);
    padding: 20px;
    width: 100%;
    max-width: 560px;
    max-height: 90vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .modal-head {
    display: flex; justify-content: space-between;
    align-items: center;
  }
  .modal h3 { margin: 0; font-size: 16px; font-weight: 600; }
  .modal-close {
    background: none; border: none;
    font-size: 22px; line-height: 1;
    cursor: pointer; color: var(--text-muted);
    padding: 0 4px;
  }
  .modal-close:hover { color: var(--text); }
  .modal-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  @media (max-width: 540px) { .modal-grid { grid-template-columns: 1fr; } }
  .modal-grid label, .modal-label-block {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 12px; font-weight: 500;
    color: var(--text-muted);
    text-transform: capitalize;
  }
  .modal-actions {
    display: flex; gap: 8px; justify-content: flex-end;
    margin-top: 4px;
  }
  .merge-hint { font-size: 13px; color: var(--text-muted); margin: 0; }
  .merge-hint code { font-family: var(--font-mono); background: var(--surface-2); padding: 1px 6px; border-radius: var(--r-sm); }

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
