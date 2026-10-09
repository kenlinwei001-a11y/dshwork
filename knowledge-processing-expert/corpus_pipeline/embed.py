"""嵌入层（向量化）：用 fastembed（ONNX，无 torch）把 chunk 文本向量化。

对应 30 契约 #11 chunks/embeddings.parquet（向量库）。
模型：paraphrase-multilingual-MiniLM-L12-v2（多语，支持中文，384 维）。
"""
from __future__ import annotations
from pathlib import Path

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def embed_texts(texts: list[str], model_name: str = DEFAULT_MODEL) -> list[list[float]]:
    """把文本批量向量化，返回 list[vector]。"""
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=model_name)
    return [list(v) for v in model.embed(texts)]


def build_embeddings(chunks: list[dict], root: Path, model_name: str = DEFAULT_MODEL) -> dict:
    """向量化所有 chunk，严格写 chunks/embeddings.parquet（pyarrow）。"""
    root = Path(root)
    if not chunks:
        return {"model": model_name, "count": 0, "dim": 0, "file": None}
    ids = [c["id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts, model_name)
    dim = len(vectors[0]) if vectors else 0

    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({
        "id": pa.array(ids, type=pa.string()),
        "vector": pa.array([list(map(float, v)) for v in vectors], type=pa.list_(pa.float32())),
    })
    table = table.replace_schema_metadata({"model": model_name, "dim": str(dim)})

    (root / "chunks").mkdir(parents=True, exist_ok=True)
    out = root / "chunks" / "embeddings.parquet"
    pq.write_table(table, out)
    return {"model": model_name, "count": len(vectors), "dim": dim, "file": str(out)}
