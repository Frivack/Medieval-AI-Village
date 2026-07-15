# backend/memory/store.py
# Long-term memory: ChromaDB vector store with semantic retrieval
# (Generative Agents style). chromadb is an OPTIONAL dependency — it
# pulls in onnxruntime etc., far too heavy for the 1 GB deployment box.
# When it isn't installed (or VECTOR_MEMORY=0), the sim silently runs
# on short-term memory alone via the null store.
import logging
import uuid

from backend.config import CHROMA_DIR, VECTOR_MEMORY

log = logging.getLogger(__name__)


class NullMemoryStore:
    """No-op stand-in when chromadb is unavailable or disabled."""
    enabled = False

    def add(self, agent_id: str, tick: int, text: str) -> None:
        pass

    def query(self, agent_id: str, text: str, k: int = 3) -> list[str]:
        return []


class ChromaMemoryStore:
    enabled = True

    def __init__(self):
        import chromadb  # deferred: optional dependency
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._collection = self._client.get_or_create_collection("agent_memories")

    def add(self, agent_id: str, tick: int, text: str) -> None:
        self._collection.add(
            ids=[uuid.uuid4().hex],
            documents=[text],
            metadatas=[{"agent_id": agent_id, "tick": tick}],
        )

    def query(self, agent_id: str, text: str, k: int = 3) -> list[str]:
        res = self._collection.query(
            query_texts=[text], n_results=k, where={"agent_id": agent_id}
        )
        docs = res.get("documents") or []
        return docs[0] if docs else []


def _make_store():
    if not VECTOR_MEMORY:
        return NullMemoryStore()
    try:
        store = ChromaMemoryStore()
        log.info("vector memory enabled (chromadb at %s)", CHROMA_DIR)
        return store
    except Exception as exc:  # ImportError, model download failure, ...
        log.info("vector memory disabled (%s); using short-term only", exc)
        return NullMemoryStore()


memory_store = _make_store()
