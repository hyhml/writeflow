"""
素材库 - 素材存储和检索
"""
from __future__ import annotations

import json
import sqlite3
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


class MaterialDB:
    """
    素材库数据库

    功能：
    1. 素材存储（SQLite）
    2. 按主题/类型/标签检索
    3. 去重检测
    4. 素材关联分析
    """

    def __init__(self, db_path: str = "materials.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                material_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                reliability REAL DEFAULT 0.5,
                relevance REAL DEFAULT 0.5,
                tags TEXT,
                potential_bias TEXT,
                created_at TEXT NOT NULL,
                last_used_at TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_topic ON materials(topic)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_type ON materials(material_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags ON materials(tags)
        """)

        conn.commit()
        conn.close()

    def add_material(
        self,
        topic: str,
        material_type: str,
        content: str,
        source: str = "",
        reliability: float = 0.5,
        relevance: float = 0.5,
        tags: List[str] = None,
        potential_bias: str = "",
    ) -> str:
        """添加素材"""
        if tags is None:
            tags = []

        material_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO materials
            (id, topic, material_type, content, source, reliability, relevance, tags, potential_bias, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            material_id,
            topic,
            material_type,
            content,
            source,
            reliability,
            relevance,
            json.dumps(tags),
            potential_bias,
            now,
        ))

        conn.commit()
        conn.close()

        return material_id

    def get_materials(
        self,
        topic: Optional[str] = None,
        material_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_reliability: float = 0.0,
        min_relevance: float = 0.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """检索素材"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        conditions = []
        params = []

        if topic:
            conditions.append("topic LIKE ?")
            params.append(f"%{topic}%")

        if material_type:
            conditions.append("material_type = ?")
            params.append(material_type)

        if tags:
            for tag in tags:
                conditions.append("tags LIKE ?")
                params.append(f"%{tag}%")

        if min_reliability > 0:
            conditions.append("reliability >= ?")
            params.append(min_reliability)

        if min_relevance > 0:
            conditions.append("relevance >= ?")
            params.append(min_relevance)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(f"""
            SELECT * FROM materials
            WHERE {where_clause}
            ORDER BY reliability DESC, relevance DESC
            LIMIT ?
        """, (*params, limit))

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            r = dict(row)
            r["tags"] = json.loads(r["tags"])
            results.append(r)

        return results

    def check_duplicate(self, content: str, threshold: float = 0.8) -> Optional[str]:
        """
        检查重复素材

        Args:
            content: 新素材内容
            threshold: 相似度阈值

        Returns:
            重复素材ID，如果无重复则返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, content FROM materials")
        rows = cursor.fetchall()
        conn.close()

        content_words = set(content.lower().split())

        for material_id, existing_content in rows:
            existing_words = set(existing_content.lower().split())
            intersection = content_words & existing_words
            union = content_words | existing_words

            if union and len(intersection) / len(union) >= threshold:
                return material_id

        return None

    def update_last_used(self, material_id: str) -> None:
        """更新最后使用时间"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE materials
            SET last_used_at = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), material_id))

        conn.commit()
        conn.close()

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM materials")
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT material_type, COUNT(*) as count
            FROM materials
            GROUP BY material_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT AVG(reliability) FROM materials
        """)
        avg_reliability = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "total_materials": total,
            "by_type": by_type,
            "avg_reliability": avg_reliability,
        }

    def delete_old_materials(self, days: int = 90) -> int:
        """删除旧素材"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM materials
            WHERE last_used_at IS NULL
            AND created_at < datetime('now', ? || ' days')
        """, (-days,))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted


class MaterialCache:
    """素材缓存 - 内存中的素材库"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    def get(self, topic: str) -> List[Dict[str, Any]]:
        """获取主题相关的素材"""
        return self._cache.get(topic, [])

    def set(self, topic: str, materials: List[Dict[str, Any]]) -> None:
        """设置主题素材"""
        if len(self._cache) >= self.max_size:
            # 删除最旧的
            oldest = min(self._cache.keys(), key=lambda k: self._cache[k][0].get("_added_at", ""))
            del self._cache[oldest]

        for m in materials:
            m["_added_at"] = datetime.utcnow().isoformat()

        self._cache[topic] = materials

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
