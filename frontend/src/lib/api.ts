// KONTACT API Client
// All endpoints proxied to same origin

// ============================================================
//  Types
// ============================================================

export interface UploadResponse {
  batch_id: string;
  files: { filename: string; status: string }[];
  message: string;
}

export interface FolderUploadResponse {
  batch_id: string;
  files_found: number;
  message: string;
}

export interface QueueItem {
  id: string;
  filename: string;
  status: string;
  batch_id: string;
  created_at: string;
  error?: string;
}

export interface QueueResponse {
  items: QueueItem[];
  total: number;
}

export interface BatchInfo {
  batch_id: string;
  total: number;
  pending: number;
  completed: number;
  failed: number;
  created_at: string;
}

export interface BatchesResponse {
  batches: BatchInfo[];
}

export interface PendingResponse {
  items: QueueItem[];
  total: number;
}

export interface ProcessResponse {
  processed: number;
  failed: number;
  message: string;
}

export interface SearchResult {
  id: string;
  filename: string;
  score: number;
  metadata: Record<string, unknown>;
  snippet?: string;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
}

export type SourceChannel = 'upload' | 'wechat' | 'email' | 'url' | 'api';

export interface AuditFields {
  created_at?: string;
  updated_at?: string;
  owner_uuid?: string;
  owner_name?: string;
  source_channel?: SourceChannel;
  edit_count?: number;
}

export interface DataItem extends AuditFields {
  id: string;
  filename: string;
  folder?: string;
  metadata: Record<string, unknown>;
  extracted_at: string;
}

export interface Document extends AuditFields {
  id?: string | number;
  uuid?: string;
  folder?: string;
  source_file?: string;
  image_type?: string;
  company?: string;
  title?: string;
  raw_text?: string;
  [k: string]: unknown;
}

export interface Contact extends AuditFields {
  uuid?: string;
  company?: string;
  person?: string;
  phone?: string;
  email?: string;
  website?: string;
  address?: string;
  [k: string]: unknown;
}

export interface Product extends AuditFields {
  uuid?: string;
  company?: string;
  name?: string;
  model?: string;
  specs?: string;
  category?: string;
  price?: string;
  [k: string]: unknown;
}

export interface DataResponse {
  items: DataItem[];
  total: number;
}

export interface DocumentMetadata {
  id?: string;
  uuid?: string;
  folder?: string;
  source_file?: string;
  gps_lat?: number;
  gps_lng?: number;
  gps_altitude?: number;
  gps_heading?: number;
  gps_speed?: number;
  gps_source?: 'exif' | 'browser' | 'ip';
  gps_accuracy?: number;
  country?: string;
  city?: string;
  address_full?: string;
  camera_make?: string;
  camera_model?: string;
  lens_model?: string;
  focal_length?: number;
  f_number?: number;
  iso?: number;
  exposure_time?: string;
  software?: string;
  sub_sec_time?: string;
  date_taken?: string;
  img_width?: number;
  img_height?: number;
  file_size_kb?: number;
  client_timezone?: string;
  client_user_agent?: string;
  client_ip?: string;
  client_timestamp?: string;
  image_phash?: string;
  blur_score?: number;
  is_blurry?: number;
  near_dup_of?: string;
  created_at?: string;
  updated_at?: string;
  owner_uuid?: string;
  owner_name?: string;
  source_channel?: SourceChannel;
  edit_count?: number;
}

export interface StatsResponse {
  total_files: number;
  total_processed: number;
  total_pending: number;
  total_failed: number;
  total_indexed: number;
  storage_used?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface ChatResponse {
  answer: string;
  session_id: string;
  sources?: { filename: string; score: number }[];
}

export interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
  message_count: number;
}

export interface ChatSessionsResponse {
  sessions: ChatSession[];
}

export interface ChatHistoryResponse {
  session_id: string;
  messages: ChatMessage[];
}

export interface ExportResponse {
  data: unknown[];
  total: number;
}

export interface IndexResponse {
  indexed: number;
  message: string;
}

export interface ApiError {
  detail: string;
  status: number;
}

// ============================================================
//  Helper
// ============================================================

class KontactApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'KontactApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {})
  };

  // Don't set Content-Type for FormData (browser sets boundary automatically)
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(url, {
    credentials: 'include',
    ...options,
    headers
  });

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const err = await res.json();
      detail = err.detail || err.message || detail;
    } catch {
      // response body wasn't JSON
    }
    throw new KontactApiError(res.status, detail);
  }

  // Handle empty responses (204 No Content)
  if (res.status === 204) {
    return {} as T;
  }

  return res.json();
}

function qs(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string] => entry[1] !== undefined
  );
  if (entries.length === 0) return '';
  return '?' + new URLSearchParams(entries).toString();
}

// ============================================================
//  Upload
// ============================================================

/** Upload files via FormData */
export async function upload(files: File[], batchName?: string): Promise<UploadResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  if (batchName) {
    formData.append('batch_id', batchName);
  }
  return request<UploadResponse>('/api/upload', {
    method: 'POST',
    body: formData
  });
}

/** Alias for backward compat */
export const uploadFiles = upload;

/** Upload from a server-side folder path */
export async function uploadFolder(folderPath: string): Promise<FolderUploadResponse> {
  return request<FolderUploadResponse>(
    `/api/upload/folder?folder_path=${encodeURIComponent(folderPath)}`,
    { method: 'POST' }
  );
}

// ============================================================
//  Queue
// ============================================================

/** Get queue items, optionally filtered by batch_id */
export async function getQueue(batchId?: string): Promise<QueueResponse> {
  return request<QueueResponse>(`/api/queue${qs({ batch_id: batchId })}`);
}

/** Get all batches */
export async function getBatches(): Promise<BatchesResponse> {
  return request<BatchesResponse>('/api/queue/batches');
}

/** Get pending items, optionally filtered by batch_id */
export async function getPending(batchId?: string): Promise<PendingResponse> {
  return request<PendingResponse>(`/api/queue/pending${qs({ batch_id: batchId })}`);
}

// ============================================================
//  Processing
// ============================================================

/** Process queued items (foreground) */
export async function processQueue(batchId?: string): Promise<ProcessResponse> {
  return request<ProcessResponse>(`/api/process${qs({ batch_id: batchId })}`, {
    method: 'POST'
  });
}

/** Process queued items (background) */
export async function processBackground(batchId?: string): Promise<ProcessResponse> {
  return request<ProcessResponse>(`/api/process/background${qs({ batch_id: batchId })}`, {
    method: 'POST'
  });
}

// ============================================================
//  Search
// ============================================================

/** Keyword search */
export async function search(query: string): Promise<SearchResponse> {
  return request<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`);
}

/** Semantic / vector search */
export async function semanticSearch(query: string): Promise<SearchResponse> {
  return request<SearchResponse>(`/api/search/semantic?q=${encodeURIComponent(query)}`);
}

// ============================================================
//  Data
// ============================================================

/** Get extracted data, optionally filtered by folder */
export async function getData(folder?: string): Promise<DataResponse> {
  return request<DataResponse>(`/api/data${qs({ folder })}`);
}

/** Get system stats */
export async function getStats(): Promise<StatsResponse> {
  return request<StatsResponse>('/api/stats');
}

// ============================================================
//  Chat
// ============================================================

/** Send a chat message */
export async function sendChat(
  question: string,
  sessionId?: string
): Promise<ChatResponse> {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      question,
      session_id: sessionId
    })
  });
}

/** Get all chat sessions */
export async function getChatSessions(): Promise<ChatSessionsResponse> {
  return request<ChatSessionsResponse>('/api/chat/sessions');
}

/** Get chat history for a session */
export async function getChatHistory(sessionId: string): Promise<ChatHistoryResponse> {
  return request<ChatHistoryResponse>(`/api/chat/history/${encodeURIComponent(sessionId)}`);
}

/** Delete a chat session */
export async function deleteChatSession(sessionId: string): Promise<void> {
  await request<Record<string, never>>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE'
  });
}

// ============================================================
//  Export
// ============================================================

/** Export data as JSON */
export async function exportJson(): Promise<ExportResponse> {
  return request<ExportResponse>('/api/export/json');
}

/** Export data as CSV (returns blob URL) */
export async function exportCsv(): Promise<string> {
  const res = await fetch('/api/export/csv', { credentials: 'include' });
  if (!res.ok) {
    throw new KontactApiError(res.status, 'Export failed');
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

// ============================================================
//  Index
// ============================================================

/** Trigger re-indexing */
export async function reindex(): Promise<IndexResponse> {
  return request<IndexResponse>('/api/index', {
    method: 'POST'
  });
}

// ============================================================
//  WeChat Desktop Sync
// ============================================================

export interface WechatStatus {
  watching: boolean;
  folder?: string;
  last_sync?: string;
  files_seen?: number;
}

export interface WechatChat {
  chat_hash: string;
  vendor_company?: string;
  contact_uuid?: string;
  file_count: number;
  last_message?: string;
}

export async function getWechatStatus(): Promise<WechatStatus> {
  return request<WechatStatus>('/api/sync/wechat/status');
}

export async function startWechatWatcher(folder: string): Promise<WechatStatus> {
  return request<WechatStatus>('/api/sync/wechat/start', {
    method: 'POST',
    body: JSON.stringify({ folder })
  });
}

export async function stopWechatWatcher(): Promise<WechatStatus> {
  return request<WechatStatus>('/api/sync/wechat/stop', { method: 'POST' });
}

export async function scanWechatFolder(folder: string, vendor?: string): Promise<{ files_scanned: number; message: string }> {
  return request('/api/sync/wechat-folder', {
    method: 'POST',
    body: JSON.stringify({ folder, vendor })
  });
}

export async function listWechatChats(): Promise<{ chats: WechatChat[] }> {
  return request<{ chats: WechatChat[] }>('/api/sync/wechat/chats');
}

export async function assignWechatChat(chatHash: string, vendor: string, contactUuid?: string): Promise<WechatChat> {
  return request<WechatChat>(`/api/sync/wechat/chats/${encodeURIComponent(chatHash)}/assign`, {
    method: 'POST',
    body: JSON.stringify({ vendor_company: vendor, contact_uuid: contactUuid })
  });
}

export async function deleteWechatChat(chatHash: string): Promise<void> {
  await request(`/api/sync/wechat/chats/${encodeURIComponent(chatHash)}`, { method: 'DELETE' });
}

// ============================================================
//  Email Sync
// ============================================================

export interface EmailConfig {
  host: string;
  user: string;
  app_password: string;
  interval_minutes?: number;
}

export interface EmailStatus {
  polling: boolean;
  host?: string;
  user?: string;
  last_poll?: string;
  messages_seen?: number;
  interval_minutes?: number;
}

export async function startEmailPoll(cfg: EmailConfig): Promise<EmailStatus> {
  return request<EmailStatus>('/api/sync/email/start', {
    method: 'POST',
    body: JSON.stringify(cfg)
  });
}

export async function stopEmailPoll(): Promise<EmailStatus> {
  return request<EmailStatus>('/api/sync/email/stop', { method: 'POST' });
}

export async function getEmailStatus(): Promise<EmailStatus> {
  return request<EmailStatus>('/api/sync/email/status');
}

// ============================================================
//  URL Ingest
// ============================================================

export interface UrlIngestResponse {
  document_uuid?: string;
  title?: string;
  preview?: string;
  message: string;
}

export async function ingestUrl(url: string, vendor?: string): Promise<UrlIngestResponse> {
  return request<UrlIngestResponse>('/api/ingest/url', {
    method: 'POST',
    body: JSON.stringify({ url, vendor })
  });
}

// ============================================================
//  vCard
// ============================================================

export async function downloadVcard(contactUuid: string): Promise<void> {
  const res = await fetch(`/api/contacts/${encodeURIComponent(contactUuid)}/vcard`, { credentials: 'include' });
  if (!res.ok) throw new KontactApiError(res.status, 'vCard download failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `contact-${contactUuid.slice(0, 8)}.vcf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function downloadAllVcardsZip(): Promise<void> {
  const res = await fetch('/api/contacts/vcards.zip', { credentials: 'include' });
  if (!res.ok) throw new KontactApiError(res.status, 'vCard zip download failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'kontact-vcards.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ============================================================
//  Manual edit + merge + rescan
// ============================================================

export async function updateContact(uuid: string, fields: Record<string, unknown>): Promise<{ uuid: string; message: string }> {
  return request(`/api/contacts/${encodeURIComponent(uuid)}`, {
    method: 'PATCH',
    body: JSON.stringify(fields)
  });
}

export async function updateProduct(uuid: string, fields: Record<string, unknown>): Promise<{ uuid: string; message: string }> {
  return request(`/api/products/${encodeURIComponent(uuid)}`, {
    method: 'PATCH',
    body: JSON.stringify(fields)
  });
}

export async function mergeContacts(keepUuid: string, mergeUuid: string): Promise<{ uuid: string; message: string }> {
  return request('/api/contacts/merge', {
    method: 'POST',
    body: JSON.stringify({ keep_uuid: keepUuid, merge_uuid: mergeUuid })
  });
}

export async function rescanQr(docId: string | number): Promise<{ message: string; qr_data?: string }> {
  return request(`/api/documents/${encodeURIComponent(String(docId))}/rescan-qr`, {
    method: 'POST'
  });
}

// ============================================================
//  Messenger deeplink (server-resolved)
// ============================================================

export type MessengerPlatform =
  | 'whatsapp' | 'viber' | 'telegram' | 'line' | 'wechat' | 'signal' | 'zalo'
  | 'phone' | 'email';

export async function openMessengerDeeplink(uuid: string, platform: MessengerPlatform): Promise<{ url: string }> {
  return request<{ url: string }>(
    `/api/contacts/${encodeURIComponent(uuid)}/deeplink?platform=${encodeURIComponent(platform)}`
  );
}

// ============================================================
//  Aggregations
// ============================================================

export interface LocationStat {
  country: string | null;
  city: string | null;
  doc_count: number;
  lat_center: number | null;
  lng_center: number | null;
}

export interface MapPoint {
  doc_uuid: string;
  lat: number;
  lng: number;
  city?: string;
  country?: string;
  source_file?: string;
  folder?: string;
  company?: string;
}

export interface CountryStat {
  country: string;
  doc_count: number;
}

export interface TimelineGroup {
  date: string;
  doc_count: number;
  batches: { batch_id: string; count: number }[];
}

export interface CameraStat {
  camera_make: string | null;
  camera_model: string | null;
  doc_count: number;
}

export interface MessengerContact {
  uuid: string;
  company?: string;
  person?: string;
  handle?: string;
  phone?: string;
}

export interface MessengersResponse {
  whatsapp: MessengerContact[];
  wechat: MessengerContact[];
  viber: MessengerContact[];
  line: MessengerContact[];
  telegram: MessengerContact[];
  signal?: MessengerContact[];
  zalo?: MessengerContact[];
}

export interface QrItem {
  doc_uuid?: string;
  source_file?: string;
  folder?: string;
  qr_type?: string;
  qr_raw?: string;
  qr_parsed?: unknown;
}

export interface QualityResponse {
  blurry: number;
  low_res: number;
  near_dups: number;
  items: {
    doc_uuid?: string;
    source_file?: string;
    folder?: string;
    blur_score?: number;
    img_width?: number;
    img_height?: number;
    near_dup_of?: string;
    reason?: string;
  }[];
}

export interface DuplicateCluster {
  cluster_id: string;
  items: {
    doc_uuid: string;
    source_file: string;
    folder: string;
    phash?: string;
  }[];
}

export interface DuplicatesResponse {
  clusters: DuplicateCluster[];
}

export interface SyncSourceStat {
  source: string;
  doc_count: number;
}

export interface PricingRow {
  company?: string;
  category?: string;
  min_price?: number | string;
  max_price?: number | string;
  median_price?: number | string;
  count: number;
}

export function getLocations() { return request<LocationStat[]>('/api/aggregations/locations'); }
export function getMapPoints() { return request<MapPoint[]>('/api/aggregations/map-points'); }
export function getCountries() { return request<CountryStat[]>('/api/aggregations/countries'); }
export function getTimeline() { return request<TimelineGroup[]>('/api/aggregations/timeline'); }
export function getCameras() { return request<CameraStat[]>('/api/aggregations/cameras'); }
export function getMessengers() { return request<MessengersResponse>('/api/aggregations/messengers'); }
export function getQrCodes() { return request<QrItem[]>('/api/aggregations/qr-codes'); }
export function getQuality() { return request<QualityResponse>('/api/aggregations/quality'); }
export function getDuplicates() { return request<DuplicatesResponse>('/api/aggregations/duplicates'); }
export function getSyncSources() { return request<SyncSourceStat[]>('/api/aggregations/sync-sources'); }
export function getPricing() { return request<PricingRow[]>('/api/aggregations/pricing'); }

// ============================================================
//  Tags
// ============================================================

export interface Tag {
  uuid: string;
  name: string;
  color?: string;
  doc_count?: number;
}

export function getTags() { return request<Tag[]>('/api/tags'); }
export function createTag(name: string, color?: string) {
  return request<Tag>('/api/tags', { method: 'POST', body: JSON.stringify({ name, color }) });
}
export function deleteTag(uuid: string) {
  return request<void>(`/api/tags/${encodeURIComponent(uuid)}`, { method: 'DELETE' });
}
export function assignTag(docUuid: string, tagUuid: string) {
  return request<void>(`/api/documents/${encodeURIComponent(docUuid)}/tags`, {
    method: 'POST',
    body: JSON.stringify({ tag_uuid: tagUuid })
  });
}
export function unassignTag(docUuid: string, tagUuid: string) {
  return request<void>(`/api/documents/${encodeURIComponent(docUuid)}/tags/${encodeURIComponent(tagUuid)}`, {
    method: 'DELETE'
  });
}

// ============================================================
//  Notes
// ============================================================

export interface Note {
  uuid: string;
  entity_type: string;
  entity_uuid: string;
  body: string;
  created_at?: string;
  updated_at?: string;
}

export function getNotes(entityType?: string, entityUuid?: string) {
  return request<Note[]>(`/api/notes${qs({ entity_type: entityType, entity_uuid: entityUuid })}`);
}
export function createNote(payload: { entity_type: string; entity_uuid: string; body: string }) {
  return request<Note>('/api/notes', { method: 'POST', body: JSON.stringify(payload) });
}
export function updateNote(uuid: string, payload: Partial<Note>) {
  return request<Note>(`/api/notes/${encodeURIComponent(uuid)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}
export function deleteNote(uuid: string) {
  return request<void>(`/api/notes/${encodeURIComponent(uuid)}`, { method: 'DELETE' });
}

// ============================================================
//  Meetings
// ============================================================

export interface Meeting {
  uuid: string;
  contact_uuid?: string;
  contact_name?: string;
  date?: string;
  location?: string;
  notes?: string;
  outcome?: string;
  created_at?: string;
}

export function getMeetings() { return request<Meeting[]>('/api/meetings'); }
export function createMeeting(payload: Partial<Meeting>) {
  return request<Meeting>('/api/meetings', { method: 'POST', body: JSON.stringify(payload) });
}
export function updateMeeting(uuid: string, payload: Partial<Meeting>) {
  return request<Meeting>(`/api/meetings/${encodeURIComponent(uuid)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
}
export function deleteMeeting(uuid: string) {
  return request<void>(`/api/meetings/${encodeURIComponent(uuid)}`, { method: 'DELETE' });
}
