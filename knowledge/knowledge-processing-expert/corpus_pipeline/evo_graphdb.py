# -*- coding: utf-8 -*-
"""evo_graphdb —— EvoOntology workspace 的 DuckDB 图查询层（三个能力）。

## 为什么不是图数据库

440 terms / 718 relations —— JSON 内存加载 < 100ms，比任何图库都快。
但缺三种**关系型 SQL 天然擅长**的查询：

    ① 反向索引    这条 evidence / 这个节点，被哪些东西引用
    ② 依赖闭包    算 A 需要哪些叶子输入（WITH RECURSIVE）
    ③ 路径查询    从 A 到 B 经过哪些边（WITH RECURSIVE + path）

DuckDB 单文件、无服务、支持递归 CTE —— 正好。

## 用法

    from corpus_pipeline.evo_graphdb import GraphDB
    db = GraphDB.build(workspace, version, db_path)
    db.reverse("ev_inv_civil_rows")          # 反向索引
    db.closure("total_investment", depth=3)   # 依赖闭包
    db.path("civil_works", "clause_slot_ref_std_001", max_depth=4)  # 路径
"""
from __future__ import annotations
import json
from pathlib import Path

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None


SCHEMA = """
CREATE OR REPLACE TABLE nodes (
  id VARCHAR PRIMARY KEY, type VARCHAR, name VARCHAR, definition VARCHAR,
  scope VARCHAR, source_type VARCHAR, node_role VARCHAR,
  must_input BOOLEAN, caliber_status VARCHAR, missing_reason VARCHAR
);
CREATE OR REPLACE TABLE edges (
  id VARCHAR PRIMARY KEY, src VARCHAR, rel_type VARCHAR, tgt VARCHAR,
  condition_json VARCHAR, description VARCHAR
);
CREATE OR REPLACE TABLE node_evidence (node_id VARCHAR, evidence_id VARCHAR);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_tgt ON edges(tgt);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(rel_type);
CREATE INDEX IF NOT EXISTS idx_ne_ev ON node_evidence(evidence_id);
"""


class GraphDB:
    def __init__(self, con):
        self.con = con

    # ---------- 构建 ----------
    @classmethod
    def build(cls, workspace, version: str = "", db_path=None, *, memory=False):
        """从 workspace 建图库。memory=True 则不落盘。"""
        if duckdb is None:
            raise RuntimeError("需要 duckdb：pip install duckdb")
        ws = Path(workspace)
        ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
        src = ws/"versions"/ver
        terms = json.loads((src/"terms.json").read_text(encoding="utf-8"))
        rels = json.loads((src/"relations.json").read_text(encoding="utf-8"))

        con = duckdb.connect(":memory:" if memory or not db_path else str(db_path))
        con.execute(SCHEMA)

        con.executemany(
            "INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(t.get("id"), t.get("type"), t.get("name"),
              (t.get("definition") or "")[:2000], t.get("scope"),
              t.get("source_type"), t.get("node_role"),
              t.get("must_input"), t.get("caliber_status"), t.get("missing_reason"))
             for t in terms])
        con.executemany(
            "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?)",
            [(r.get("id"), r.get("source"), r.get("relation_type"), r.get("target"),
              json.dumps(r.get("connection_condition"), ensure_ascii=False)
                if isinstance(r.get("connection_condition"), (dict, list)) else (r.get("connection_condition") or ""),
              (r.get("description") or "")[:500])
             for r in rels])
        ev = []
        for t in terms:
            for e in (t.get("evidence") or []):
                ev.append((t.get("id"), e))
        for r in rels:
            for e in (r.get("evidence") or r.get("evidence_refs") or []):
                ev.append((r.get("id"), e))
        if ev:
            con.executemany("INSERT INTO node_evidence VALUES (?,?)", ev)
        return cls(con)

    # ---------- ① 反向索引 ----------
    def reverse(self, key: str, kind: str = "auto") -> dict:
        """某个 evidence / 节点 被谁引用。"""
        q = self.con
        out = {"key": key, "as_evidence": [], "as_source": [], "as_target": []}
        out["as_evidence"] = [r[0] for r in q.execute(
            "SELECT DISTINCT node_id FROM node_evidence WHERE evidence_id = ? LIMIT 50",
            [key]).fetchall()]
        out["as_source"] = [r[0] for r in q.execute(
            "SELECT id FROM edges WHERE src = ? LIMIT 50", [key]).fetchall()]
        out["as_target"] = [r[0] for r in q.execute(
            "SELECT id FROM edges WHERE tgt = ? LIMIT 50", [key]).fetchall()]
        out["total"] = len(out["as_evidence"]) + len(out["as_source"]) + len(out["as_target"])
        return out

    # ---------- ② 依赖闭包 ----------
    def closure(self, node_id: str, depth: int = 5,
                rel_types=("derivation", "composition")) -> dict:
        """算 node_id 需要哪些上游输入（沿 derivation/composition 反向）。"""
        ph = ",".join("?" * len(rel_types))
        sql = f"""
        WITH RECURSIVE up(id, depth, path) AS (
          SELECT ?, 0, CAST(? AS VARCHAR)
          UNION ALL
          SELECT e.src, u.depth + 1, u.path || ' <- ' || e.src
          FROM edges e JOIN up u ON e.tgt = u.id
          WHERE e.rel_type IN ({ph}) AND u.depth < ?
            AND instr(u.path, e.src) = 0
        )
        SELECT id, MIN(depth) AS depth FROM up GROUP BY id ORDER BY depth, id
        """
        rows = self.con.execute(sql, [node_id, node_id, *rel_types, depth]).fetchall()

        # 叶子 = 在闭包里但自己不是任何 derivation/composition 的 src
        sql2 = f"""
        SELECT n.id, n.name, n.source_type, n.node_role, n.must_input
        FROM nodes n
        WHERE n.id IN ({",".join("?" * len(rows))})
          AND n.id NOT IN (SELECT DISTINCT src FROM edges WHERE rel_type IN ({ph}))
        """
        leaves = []
        if rows:
            ids = [r[0] for r in rows]
            leaves = self.con.execute(sql2, [*ids, *rel_types]).fetchall()
        return {"node": node_id, "depth": depth,
                "closure": [{"id": r[0], "depth": r[1]} for r in rows],
                "leaves": [{"id": r[0], "name": r[1], "source_type": r[2],
                            "node_role": r[3], "must_input": r[4]} for r in leaves],
                "leaf_count": len(leaves)}

    # ---------- ③ 路径查询 ----------
    def path(self, src: str, tgt: str, max_depth: int = 4) -> list:
        """从 src 到 tgt 的所有路径（限深）。"""
        sql = """
        WITH RECURSIVE p(cur, hops, path) AS (
          SELECT ?, 0, CAST(? AS VARCHAR)
          UNION ALL
          SELECT e.tgt, p.hops + 1, p.path || ' -[' || e.rel_type || ']-> ' || e.tgt
          FROM edges e JOIN p ON e.src = p.cur
          WHERE p.hops < ? AND instr(p.path, e.tgt) = 0
        )
        SELECT path, hops FROM p WHERE cur = ? ORDER BY hops LIMIT 20
        """
        return [{"path": r[0], "hops": r[1]}
                for r in self.con.execute(sql, [src, src, max_depth, tgt]).fetchall()]

    # ---------- 附加：按类型统计 ----------
    def stats(self) -> dict:
        q = self.con
        return {
            "nodes": q.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY 2 DESC").fetchall(),
            "edges": q.execute("SELECT rel_type, COUNT(*) FROM edges GROUP BY rel_type ORDER BY 2 DESC").fetchall(),
            "must_input": q.execute("SELECT COUNT(*) FROM nodes WHERE must_input").fetchone()[0],
            "ambiguous": q.execute("SELECT COUNT(*) FROM nodes WHERE caliber_status='ambiguous'").fetchone()[0],
        }

    def close(self):
        self.con.close()
