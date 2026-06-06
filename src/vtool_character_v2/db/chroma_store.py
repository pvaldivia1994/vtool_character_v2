import uuid
from pathlib import Path
from typing import Callable, Optional, List, Dict

try:
    import chromadb
    from chromadb.utils import embedding_functions as chroma_ef
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

def _resolve_default_embedding():
    """Intenta crear embedding function por defecto."""
    try:
        return chroma_ef.DefaultEmbeddingFunction()
    except Exception:
        return None

class ChromaStore:
    """Maneja el almacenamiento vectorial genérico."""

    def __init__(self, db_path: Path, collection_name: str, log_fn: Optional[Callable] = None):
        self._db_path = db_path
        self._collection_name = collection_name
        self._log = log_fn or (lambda msg: None)
        self._client = None
        self._collection = None
        self._embedding_fn = _resolve_default_embedding()

    @property
    def chroma_path(self) -> Path:
        return self._db_path

    @property
    def is_available(self) -> bool:
        return HAS_CHROMA and self._collection is not None

    def initialize(self) -> bool:
        """Inicializa o abre la base de datos ChromaDB."""
        if not HAS_CHROMA:
            self._log("WARN: chromadb no instalado. Usando fallback sin busqueda semantica.")
            return False

        try:
            self._db_path.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(path=str(self._db_path))
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            return True
        except Exception as e:
            self._log(f"WARN: Error iniciando ChromaDB ({self._collection_name}): {e}")
            return False

    def count(self) -> int:
        if not self.is_available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def add_document(self, doc_id: str, document: str, metadata: dict) -> None:
        """Guarda un documento como embedding semantico."""
        if not self.is_available:
            return
        try:
            self._collection.add(
                ids=[doc_id],
                documents=[document],
                metadatas=[metadata],
            )
        except Exception as e:
            self._log(f"WARN: Error guardando documento en ChromaDB ({self._collection_name}): {e}")

    def add_documents_batch(self, documents_data: List[Dict]) -> None:
        """Guarda multiples documentos en batch. Cada dict debe tener 'id', 'document', 'metadata'."""
        if not self.is_available or not documents_data:
            return
        ids = []
        documents = []
        metadatas = []
        for doc in documents_data:
            ids.append(doc.get("id", uuid.uuid4().hex[:12]))
            documents.append(doc.get("document", ""))
            metadatas.append(doc.get("metadata", {}))
        try:
            self._collection.add(ids=ids, documents=documents, metadatas=metadatas)
        except Exception as e:
            self._log(f"WARN: Error en batch insert ChromaDB ({self._collection_name}): {e}")

    def search(self, query: str, top_k: int = 5, where: Optional[dict] = None) -> List[Dict]:
        """Busqueda semantica de documentos."""
        if not self.is_available:
            self._log(f"[CHROMA] {self._collection_name}: ChromaDB no disponible")
            return []
        try:
            kwargs = {
                "query_texts": [query],
                "n_results": min(top_k, 20),
            }
            if where:
                kwargs["where"] = where
                self._log(f"[CHROMA] {self._collection_name}: query='{query[:80]}...' where={where}")
            else:
                self._log(f"[CHROMA] {self._collection_name}: query='{query[:80]}...' (sin filtro)")

            results = self._collection.query(**kwargs)

            docs_list = []
            ids = results.get("ids", [[]])[0]
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]

            for i in range(len(ids)):
                similarity = 1.0 - dists[i] if i < len(dists) else 0.0
                docs_list.append({
                    "id": ids[i],
                    "document": docs[i] if i < len(docs) else "",
                    "metadata": metas[i] if i < len(metas) else {},
                    "similarity": similarity,
                })
                self._log(f"[CHROMA] {self._collection_name}: resultado #{i} sim={similarity:.3f} id={ids[i]} doc='{(docs[i] or '')[:60]}...'")

            if not docs_list:
                self._log(f"[CHROMA] {self._collection_name}: sin resultados")

            return docs_list
        except Exception as e:
            self._log(f"[CHROMA] {self._collection_name}: Error en busqueda: {e}")
            return []

    def clear(self) -> None:
        """Limpia todos los documentos de la coleccion."""
        if not self.is_available:
            return
        try:
            existing = self._collection.get()
            if existing and existing.get("ids"):
                self._collection.delete(ids=existing["ids"])
        except Exception:
            pass

    def delete_ids(self, ids: list[str]) -> None:
        """Elimina documentos específicos por ID."""
        if not self.is_available or not ids:
            return
        try:
            self._collection.delete(ids=ids)
        except Exception as e:
            self._log(f"WARN: Error eliminando documentos de ChromaDB: {e}")

    def get_all_documents(self) -> list[dict]:
        """Retorna todos los documentos de la colección."""
        if not self.is_available:
            return []
        try:
            existing = self._collection.get()
            if not existing or not existing.get("ids"):
                return []
            result = []
            for i in range(len(existing["ids"])):
                result.append({
                    "id": existing["ids"][i],
                    "document": existing["documents"][i] if i < len(existing.get("documents", [])) else "",
                    "metadata": existing["metadatas"][i] if i < len(existing.get("metadatas", [])) else {},
                })
            return result
        except Exception as e:
            self._log(f"WARN: Error obteniendo documentos de ChromaDB: {e}")
            return []

    def close(self) -> None:
        """Cierra la conexión con ChromaDB y libera recursos.

        No borra la colección persistente — solo cierra el cliente.
        Usar drop_collection() si se necesita eliminar los datos.
        """
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._collection = None

    def drop_collection(self) -> None:
        """Elimina la colección persistente y cierra recursos.

        Útil para limpieza total. No llamar en close() normal.
        """
        if self._client and self._collection:
            try:
                self._client.delete_collection(self._collection_name)
            except Exception:
                pass
        self.close()


