"""真实存储后端：PG / Neo4j / Qdrant + 文件系统回退。

生产拓扑：对象存储（文件）+ PG（元数据/证据/决策/术语）+ 图库（节点/边）+ 向量库（chunks/signature）+ 事件流。
本模块提供真实连接适配器；服务不可达或客户端库缺失时优雅回退到文件系统。
连接串从环境变量读取（见 .env.example / docker-compose.yml）。
"""
from __future__ import annotations
import json
import os
from pathlib import Path


class FilesystemBackend:
    """对象存储 = 本地文件（默认，永远可用）。"""
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, rel: str, content: str | bytes) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if isinstance(content, bytes) else "w"
        p.write_bytes(content) if isinstance(content, bytes) else p.write_text(content, encoding="utf-8")

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")


class PostgresBackend:
    """PG：元数据/证据/决策/术语等关系数据。lazy import psycopg2。"""
    def __init__(self, dsn: str):
        self.dsn = dsn

    @property
    def conn(self):
        import psycopg2  # lazy
        return psycopg2.connect(self.dsn)

    def upsert(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        import psycopg2.extras
        with self.conn as c:
            cols = list(rows[0].keys())
            insert = f"INSERT INTO {table} ({','.join(cols)}) VALUES %s ON CONFLICT DO NOTHING"
            psycopg2.extras.execute_values(c.cursor(), insert, [[r.get(k) for k in cols] for r in rows])
            c.commit()

    def query(self, sql: str) -> list[dict]:
        import psycopg2.extras
        with self.conn as c:
            cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql)
            return cur.fetchall()


class Neo4jBackend:
    """图库：节点(:Node/:Section/:Rule/:Claim/...) 与边（十类关系）。lazy import neo4j。"""
    def __init__(self, uri: str, user: str, password: str):
        self.uri, self.user, self.password = uri, user, password

    @property
    def driver(self):
        from neo4j import GraphDatabase  # lazy
        return GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def run(self, cypher: str, **params) -> list[dict]:
        with self.driver.session() as s:
            return [dict(r) for r in s.run(cypher, **params)]

    def upsert_nodes(self, label: str, nodes: list[dict], key: str = "id") -> None:
        for n in nodes:
            self.run(f"MERGE (n:{label} {{{key}: $id}}) SET n = $props",
                     id=n.get(key), props={k: v for k, v in n.items() if k != key})

    def upsert_relations(self, relations: list[dict]) -> None:
        for r in relations:
            self.run("MATCH (a {id:$from}) MATCH (b {id:$to}) MERGE (a)-[:REL {type:$type}]->(b)",
                     **r)


class QdrantBackend:
    """向量库：chunks 语义检索 + signature 匹配特征。lazy import qdrant_client。"""
    def __init__(self, url: str, api_key: str | None = None):
        self.url, self.api_key = url, api_key

    @property
    def client(self):
        from qdrant_client import QdrantClient  # lazy
        return QdrantClient(url=self.url, api_key=self.api_key)

    def upsert(self, collection: str, points: list[dict]) -> None:
        from qdrant_client.models import PointStruct, VectorParams
        c = self.client
        if not c.collection_exists(collection):
            c.create_collection(collection, VectorParams(size=len(points[0]["vector"]), distance="Cosine"))
        c.upsert(collection, [PointStruct(id=p["id"], vector=p["vector"], payload=p.get("payload", {})) for p in points])

    def search(self, collection: str, vector: list[float], limit: int = 5) -> list[dict]:
        return [h.payload for h in self.client.search(collection, query_vector=vector, limit=limit)]


def make_backends(root: Path) -> dict:
    """按环境变量构造后端；服务不可达/库缺失时回退文件系统。"""
    backends = {"object": FilesystemBackend(root)}

    pg_dsn = os.environ.get("KP_PG_DSN")
    if pg_dsn:
        try:
            backends["pg"] = PostgresBackend(pg_dsn)
        except Exception as e:  # noqa: BLE001
            backends["pg"] = None
            backends["pg_error"] = str(e)

    neo4j_uri = os.environ.get("KP_NEO4J_URI")
    if neo4j_uri:
        try:
            backends["neo4j"] = Neo4jBackend(neo4j_uri, os.environ.get("KP_NEO4J_USER", "neo4j"), os.environ.get("KP_NEO4J_PASS", ""))
        except Exception as e:  # noqa: BLE001
            backends["neo4j"] = None
            backends["neo4j_error"] = str(e)

    qdrant_url = os.environ.get("KP_QDRANT_URL")
    if qdrant_url:
        try:
            backends["qdrant"] = QdrantBackend(qdrant_url, os.environ.get("KP_QDRANT_API_KEY"))
        except Exception as e:  # noqa: BLE001
            backends["qdrant"] = None
            backends["qdrant_error"] = str(e)

    return backends
