import json, os, time
import numpy as np
import httpx
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
import config

CHROMA_DIR = os.path.join(config.DATA_DIR, "chroma")
COLLECTION_NAME = "catalog_docs"


class OpenRouterEmbeddingFunction(EmbeddingFunction):
    """Embedding function via OpenRouter (supports OpenAI + Gemini models)."""

    def __init__(self, model: str = None):
        self.model = model or config.EMBEDDING_MODEL
        self.url = config.OPENROUTER_EMBED_BASE
        self.headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

    def _call_api(self, texts: list[str], retries: int = 5) -> list:
        for attempt in range(retries):
            payload = {"model": self.model, "input": texts}
            with httpx.Client(timeout=120) as client:
                r = client.post(self.url, json=payload, headers=self.headers)
            data = r.json()
            if "data" in data:
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                return [np.array(item["embedding"], dtype=np.float32) for item in sorted_data]
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1, 2, 4, 8s backoff
        raise ValueError(f"Embedding API failed after {retries} retries: {str(data)[:200]}")

    def __call__(self, input: Documents) -> Embeddings:
        texts = [t[:8000] if isinstance(t, str) else str(t) for t in input]
        return self._call_api(texts)


_client = chromadb.PersistentClient(path=CHROMA_DIR)
_embed_fn = OpenRouterEmbeddingFunction()
collection = _client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=_embed_fn)


def reset_collection():
    """Delete and recreate collection (call when embedding model changes or re-indexing)."""
    global collection
    try:
        _client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass
    collection = _client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=_embed_fn)


def _build_product_chunk(product: dict, company: str = "", folder: str = "") -> str:
    """Build a focused chunk for a single product."""
    parts = []
    if company:
        parts.append(f"Company: {company}")
    if product.get("name"):
        parts.append(f"Product: {product['name']}")
    if product.get("model"):
        parts.append(f"Model: {product['model']}")
    if product.get("specs"):
        parts.append(f"Specs: {product['specs']}")
    if product.get("category"):
        parts.append(f"Category: {product['category']}")
    if product.get("price"):
        parts.append(f"Price: {product['price']}")
    if product.get("image_desc"):
        parts.append(f"Appearance: {product['image_desc']}")
    return "\n".join(parts)


def _build_page_text(record: dict) -> str:
    """Build a summary text for the whole page (non-product info)."""
    parts = []
    if record.get("company"):
        parts.append(f"Company: {record['company']}")
    if record.get("title"):
        parts.append(f"Title: {record['title']}")
    if record.get("profile"):
        p = record["profile"]
        if p.get("description"):
            parts.append(p["description"])
        if p.get("certifications"):
            parts.append(f"Certifications: {', '.join(p['certifications'])}")
        if p.get("key_services"):
            parts.append(f"Services: {', '.join(p['key_services'])}")
    if record.get("contact"):
        ct = record["contact"]
        for k, v in ct.items():
            if v:
                parts.append(f"{k}: {v}")
    for info in record.get("key_info", []):
        parts.append(info)
    if record.get("raw_text"):
        parts.append(record["raw_text"])
    return "\n".join(parts)


def index_record(folder: str, record: dict):
    source = record.get("source_file", "unknown")
    company = record.get("company") or ""
    base_meta = {
        "folder": folder,
        "source_file": source,
        "image_type": record.get("image_type", ""),
        "company": company,
    }

    products = record.get("products", [])
    if products:
        # Index each product as its own chunk for precise search
        for i, prod in enumerate(products):
            chunk_id = f"{folder}/{source}/product_{i}"
            text = _build_product_chunk(prod, company, folder)
            if not text.strip():
                continue
            meta = {**base_meta, "chunk_type": "product", "product_name": prod.get("name", "")}
            collection.upsert(ids=[chunk_id], documents=[text], metadatas=[meta])

    # Index page-level info (contact, company profile, raw text)
    page_text = _build_page_text(record)
    if page_text.strip():
        page_id = f"{folder}/{source}/page"
        page_meta = {**base_meta, "chunk_type": "page"}
        collection.upsert(ids=[page_id], documents=[page_text], metadatas=[page_meta])


def prune_orphans(valid_folders: set, valid_sources: set = None) -> int:
    """Delete vectors whose folder is no longer in the documents table.

    Call periodically (e.g. daily cron) to bound ChromaDB growth.
    Returns the number of vectors deleted.
    """
    try:
        total = collection.count()
    except Exception:
        return 0
    if not total:
        return 0
    try:
        all_meta = collection.get(include=["metadatas"])
    except Exception:
        return 0
    ids_to_delete = []
    for vid, meta in zip(all_meta.get("ids", []), all_meta.get("metadatas", [])):
        if not isinstance(meta, dict):
            continue
        folder = meta.get("folder")
        if folder and folder not in valid_folders:
            ids_to_delete.append(vid)
    if ids_to_delete:
        try:
            collection.delete(ids=ids_to_delete)
        except Exception:
            return 0
    return len(ids_to_delete)


def delete_by_folder(folder: str) -> int:
    """Delete every vector tied to a folder. Called on batch deletion."""
    try:
        collection.delete(where={"folder": folder})
        return 1
    except Exception:
        return 0


def index_all_from_json():
    reset_collection()
    ext_dir = config.EXTRACTIONS_DIR
    count = 0
    for fname in os.listdir(ext_dir):
        if fname == "all_extractions.json" or not fname.endswith(".json"):
            continue
        folder = fname.replace(".json", "")
        with open(os.path.join(ext_dir, fname)) as f:
            records = json.load(f)
        for r in records:
            index_record(folder, r)
            count += 1
    return count


def query(text: str, n_results: int = 5) -> list:
    if collection.count() == 0:
        return []
    n = min(n_results, collection.count())
    results = collection.query(query_texts=[text], n_results=n)
    out = []
    for i, doc_id in enumerate(results["ids"][0]):
        out.append({
            "id": doc_id,
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })
    return out
