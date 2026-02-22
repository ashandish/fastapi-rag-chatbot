from typing import List, Dict, Any
from .embeddings import similarity_search, collection_size
from .models import settings
import httpx
from sentence_transformers import CrossEncoder

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a helpful RAG chatbot. Use the provided context snippets to answer accurately. "
    "If the answer is not contained in the context, say you don't know and suggest building more context."
)

_reranker = None
def get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker

def rerank(query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    model = get_reranker()
    pairs = [(query, c["doc"]) for c in candidates]
    scores = model.predict(pairs).tolist()
    for c, s in zip(candidates, scores):
        c["rerank_score"] = s
    candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return candidates[:top_k]

def synthesize_answer(question: str, topk: List[Dict[str, Any]]) -> str:
    context_blocks = []
    for i, item in enumerate(topk, start=1):
        meta = item.get("meta", {}) or {}
        src = meta.get("source", "unknown")
        content = item.get("doc", "")
        context_blocks.append(f"[{i}] Source: {src}\n{content}\n")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nContext:\n" + "\n---\n".join(context_blocks)},
    ]

    # Pick endpoint/model depending on provider.
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            return "OpenAI API key not configured. Set OPENAI_API_KEY."
        url = OPENAI_API_URL
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        model_name = settings.llm_model_openai
    else:
        # OpenAI-compatible local server (e.g., Ollama or llama.cpp server).
        base = settings.local_llm_endpoint.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {}
        model_name = (
            settings.local_llm_model_large
            if settings.local_llm_size == "large"
            else settings.local_llm_model_small
        )

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"LLM request failed: {exc}"

def answer_question(q: str) -> str:
    if collection_size() == 0:
        return (
            "Retrieval database is not built yet. Please visit /admin/login and then /embeddings "
            "to add documents and generate embeddings."
        )
    initial = similarity_search(q, top_k=settings.top_k_initial)
    final = rerank(q, initial, settings.top_k_reranked) if settings.rerank_enabled else initial[:settings.top_k_reranked]
    return synthesize_answer(q, final)
