import os, uuid
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from PIL import Image

from .models import settings, UPLOAD_DIR
from .utils import read_text_file, read_pdf, read_docx, is_text_file, is_image_file, chunk_text_by_tokens

_chroma_client = chromadb.PersistentClient(
    path=settings.embed_store_path,
    settings=ChromaSettings(
        allow_reset=True,
        anonymized_telemetry=False  # prevent PostHog telemetry errors in restricted environments
    )
)
_collection = _chroma_client.get_or_create_collection(
    name="rag_collection",
    metadata={"hnsw:space": "cosine"}
)

_model_cache: Dict[str, SentenceTransformer] = {}

def _model_name_pair():
    if settings.embed_mode == "gpu":
        return settings.text_embed_model_gpu, settings.image_embed_model_gpu
    else:
        return settings.text_embed_model_cpu, settings.image_embed_model_cpu

def get_text_embedder() -> SentenceTransformer:
    text_name, _ = _model_name_pair()
    if text_name not in _model_cache:
        _model_cache[text_name] = SentenceTransformer(text_name)
    return _model_cache[text_name]

def get_image_embedder() -> SentenceTransformer:
    _, image_name = _model_name_pair()
    if image_name not in _model_cache:
        _model_cache[image_name] = SentenceTransformer(image_name)
    return _model_cache[image_name]

def collection_size() -> int:
    try:
        return _collection.count()
    except Exception:
        return 0

def reset_collection():
    global _collection
    try:
        _chroma_client.reset()
    except Exception:
        pass
    _collection = _chroma_client.get_or_create_collection(
        name="rag_collection",
        metadata={"hnsw:space":"cosine"}
    )

def add_documents(files: List[str]) -> Dict[str, Any]:
    text_embedder = get_text_embedder()
    image_embedder = get_image_embedder()
    max_tokens = int(settings.chunk_size_tokens)
    overlap = 0.2

    docs, metadatas, ids = [], [], []
    for fpath in files:
        if not os.path.exists(fpath):
            continue
        ext = os.path.splitext(fpath)[1].lower()
        base_meta = {"source": os.path.basename(fpath), "path": fpath}

        if is_text_file(fpath):
            if ext in {".pdf"}:
                text = read_pdf(fpath)
            elif ext in {".docx"}:
                text = read_docx(fpath)
            else:
                text = read_text_file(fpath)

            chunks = chunk_text_by_tokens(text, max_tokens, overlap_ratio=overlap)
            for i, chunk in enumerate(chunks):
                docs.append(chunk)
                metadatas.append({**base_meta, "type": "text", "chunk_index": i})
                ids.append(str(uuid.uuid4()))

        elif is_image_file(fpath):
            docs.append(f"[IMAGE]{os.path.basename(fpath)}")
            metadatas.append({**base_meta, "type": "image"})
            ids.append(str(uuid.uuid4()))

    text_indices = [i for i, m in enumerate(metadatas) if m["type"] == "text"]
    img_indices = [i for i, m in enumerate(metadatas) if m["type"] == "image"]
    embs = [None] * len(docs)

    if text_indices:
        texts = [docs[i] for i in text_indices]
        text_embs = text_embedder.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False
        )
        for idx, vec in zip(text_indices, text_embs):
            embs[idx] = vec

    if img_indices:
        imgs = [Image.open(metadatas[i]["path"]).convert("RGB") for i in img_indices]
        img_embs = image_embedder.encode(
            imgs,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False
        )
        for img in imgs:
            img.close()
        for idx, vec in zip(img_indices, img_embs):
            embs[idx] = vec

    if not ids:
        return {"added": 0}

    # Chroma expects plain Python lists, not numpy arrays, for embeddings
    prepared_embs = [vec.tolist() if hasattr(vec, "tolist") else vec for vec in embs]

    _collection.add(
        ids=ids,
        embeddings=prepared_embs,
        documents=docs,
        metadatas=metadatas
    )

    return {"added": len(ids)}

def add_documents_incremental(files: List[str], progress_cb=None) -> Dict[str, Any]:
    total_added = 0
    total = len(files) if files else 0
    for i, f in enumerate(files):
        stats = add_documents([f])
        total_added += stats.get("added", 0)
        if progress_cb:
            pct = int(((i + 1) / max(1, total)) * 100)
            progress_cb(pct, current=f)
    return {"added": total_added}

def similarity_search(query: str, top_k: int = 5):
    text_embedder = get_text_embedder()
    q_emb = text_embedder.encode(
        [query], normalize_embeddings=True, convert_to_numpy=True
    )[0]
    results = _collection.query(
        query_embeddings=[q_emb.tolist()],
        n_results=top_k,
        include=["distances", "metadatas", "documents"]
    )
    out = []
    for i in range(len(results["ids"][0])):
        out.append({
            "id": results["ids"][0][i],
            "doc": results["documents"][0][i],
            "meta": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if "distances" in results else None
        })
    return out

def save_upload(file_obj: bytes, filename: str) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fpath = os.path.join(UPLOAD_DIR, filename)
    with open(fpath, "wb") as f:
        f.write(file_obj)
    return fpath
