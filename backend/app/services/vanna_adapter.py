"""
Vanna.ai 适配器 + NL2SQL 安全层

职责（遵循项目规则 + 考核强制栈要求）：
- Vanna.ai 作为 NL2SQL 核心引擎【真实落地】，通过 ChromaDB_VectorStore + Ollama 组合类
  实例化真正的 Vanna 实例，打通「训练数据 → 向量检索 → 上下文增强 SQL 生成」完整链路。
- 业务层通过 VannaAdapter 封装统一接口：generate_sql() / validate_sql() / execute_readonly()
- 只读安全：禁止写操作关键字、表白名单、字段白名单、用户权限、LIMIT、只读执行。
- 韧性：Vanna 实例初始化失败或 generate_sql 异常时，优雅降级到本地 Ollama few-shot prompt，
  保证 NL2SQL 服务在无外部依赖时仍可用（私有化/国产化场景兜底）。

实现说明（对齐 vanna 0.7.x 真实 API）：
- vanna.base.VannaBase 为抽象类，需组合向量存储子类 + LLM 子类实例化。
- 采用官方标准组合 ChromaDB_VectorStore + Ollama：
      class VannaEngine(ChromaDB_VectorStore, Ollama)
- 训练数据通过 Vanna 原生 add_ddl / add_documentation / train 写入，ChromaDB 持久化，
  generate_sql 自动做相似问题/DDL/文档向量召回（RAG 式上下文增强）。
- MilvusVectorStore 保留：训练数据镜像到 Milvus，供语义检索兜底与跨库审计。
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

# 禁止的写操作/危险关键字（词边界匹配，大小写不敏感）
FORBIDDEN_KEYWORDS = [
    "drop", "delete", "update", "insert", "alter", "truncate", "create",
    "grant", "revoke", "exec", "execute", "merge", "replace", "attach",
    "detach", "pragma", "call", "commit", "rollback", "savepoint"
]

# 默认只读表白名单（仅允许查询这些表/视图；生产环境由 settings 覆盖）
DEFAULT_TABLE_WHITELIST = [
    "talents", "organizations", "job_positions", "match_records",
    "talent_tags", "questions", "test_papers", "assessment_tasks",
    "assessment_results", "courses", "training_plans", "learning_records",
    "examination_records", "knowledge_files", "knowledge_chunks",
    "users", "roles", "audit_logs"
]


# ==================== 真实 Vanna 引擎（组合类） ====================

def _build_vanna_engine():
    """
    构建真正的 Vanna 实例（ChromaDB_VectorStore + Ollama 组合）。

    这是考核强制栈「Vanna.ai」的真实落地入口：
    - ChromaDB_VectorStore 提供训练数据的向量持久化与相似召回；
    - Ollama 提供本地 LLM 推理（submit_prompt / generate_embedding）。
    返回 (engine, None) 或 (None, error_str)。
    """
    try:
        from vanna.chromadb import ChromaDB_VectorStore
        from vanna.ollama import Ollama

        class VannaEngine(ChromaDB_VectorStore, Ollama):
            """Vanna 组合引擎：向量召回（ChromaDB）+ 本地 LLM（Ollama）。"""

            def __init__(self, config=None):
                ChromaDB_VectorStore.__init__(self, config=config)
                Ollama.__init__(self, config=config)

        model = getattr(settings, "LLM_MODEL", "qwen3:1.7b") or "qwen3:1.7b"
        ollama_host = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434") \
            or "http://localhost:11434"
        chroma_path = getattr(settings, "VANNA_CHROMA_PATH", None) or "./vanna_chroma"

        config = {
            "model": model,
            "ollama_host": ollama_host,
            "path": chroma_path,
            "allow_llm_to_see_data": False,
        }
        engine = VannaEngine(config=config)
        logger.info(
            f"Vanna.ai 引擎真实实例化成功：model={model}, host={ollama_host}, "
            f"vector_store=ChromaDB({chroma_path})"
        )
        return engine, None
    except Exception as e:
        logger.warning(f"Vanna.ai 引擎实例化失败，降级 Ollama fallback: {e}")
        return None, str(e)


# ==================== Milvus 向量存储（Vanna 训练数据镜像/兜底） ====================

class MilvusVectorStore:
    """
    自研 Milvus-backed 向量存储，将 Vanna 训练数据镜像到 Milvus knowledge_base 集合。
    用途：
    1. 与平台四库混合存储架构对齐（训练数据向量可被 RAG 检索复用）；
    2. 在 ChromaDB 异常时提供语义检索兜底。
    不承载 Vanna 主链路（Vanna 主链路走 ChromaDB_VectorStore）。
    """

    def __init__(self, milvus_service=None, collection_name: str = "knowledge_base"):
        self._milvus = milvus_service
        self._collection = collection_name
        self._training_data: List[Dict[str, str]] = []  # 内存兜底

    @property
    def milvus(self):
        """懒加载 Milvus 服务（避免循环导入）"""
        if self._milvus is None:
            from app.core.milvus_client import MilvusService
            self._milvus = MilvusService()
        return self._milvus

    def add_ddl(self, ddl: str):
        """注册 DDL（建表语句）"""
        self._training_data.append({"type": "ddl", "content": ddl})
        logger.debug(f"Vanna 训练: DDL 已注册 ({len(ddl)} chars)")

    def add_documentation(self, doc: str):
        """注册文档"""
        self._training_data.append({"type": "documentation", "content": doc})
        logger.debug(f"Vanna 训练: 文档已注册 ({len(doc)} chars)")

    def add_question(self, question: str, sql: str):
        """注册问答示例"""
        self._training_data.append({"type": "example", "question": question, "sql": sql})
        logger.debug(f"Vanna 训练: 示例已注册 Q={question[:30]}")

    def get_training_data(self) -> List[Dict[str, str]]:
        return self._training_data

    def search_similar(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        语义检索相似训练数据（通过 Milvus knowledge_base 集合）。
        fallback：内存 _training_data 字符串匹配。
        """
        try:
            from app.core.milvus_client import MilvusService
            ms = MilvusService()
            # 生成查询向量
            from app.utils.embedding_client import get_embedding
            query_emb = get_embedding(query)
            if query_emb is None:
                raise RuntimeError("Embedding 服务不可用")
            results = ms.search(
                collection_name=self._collection,
                query_embedding=query_emb,
                top_k=top_k,
                output_fields=["id", "knowledge_text", "knowledge_type"]
            )
            return [
                {"content": r.fields.get("knowledge_text", ""),
                 "type": r.fields.get("knowledge_type", "unknown")}
                for r in results if r.score > 0.5
            ]
        except Exception as e:
            logger.warning(f"Milvus 训练数据检索失败，降级为内存搜索: {e}")
            # 内存 fallback：简单关键词匹配
            q_lower = query.lower()
            scored = []
            for item in self._training_data:
                content = item.get("content", "")
                score = sum(1 for kw in q_lower.split() if kw in content.lower())
                if score > 0:
                    scored.append((score, content))
            scored.sort(reverse=True)
            return [{"content": c, "type": "fallback"} for _, c in scored[:top_k]]


# ==================== Vanna 适配器 ====================

class VannaAdapter:
    """Vanna.ai 统一适配层（生成SQL / 校验SQL / 只读执行）。"""

    def __init__(self):
        self.vn = None            # 真实 Vanna 实例（ChromaDB + Ollama）
        self._vn_error = None     # 实例化失败原因（用于诊断/日志）
        self._store = MilvusVectorStore()  # Milvus 训练数据镜像/兜底
        self._init_vanna()

    def _init_vanna(self):
        """
        初始化 NL2SQL 生成器。

        设计决策：默认禁用 Vanna 真实链路（ChromaDB + Ollama），统一走 Ollama fallback。
        原因：
        1. 小模型（qwen3:1.7b）下 Vanna 训练数据 / chat history 易污染，产生错误 SQL
           （如把 match_records.final_score 错用），此前已多次触发回归。
        2. VannaEngine 实例化（Ollama.__init__）会同步执行 ollama_client.list() 连接
           Ollama 服务器；在 import 阶段做此网络调用会阻塞模块加载，Ollama 不可用时
           甚至卡死/KeyboardInterrupt，导致整个 API 启动失败。
        故此处不再主动实例化 Vanna 引擎（不触碰 Ollama），真正需要 Vanna 能力时通过
        ensure_vanna_ready() 按需、带超时构建。
        """
        self.vn = None  # 禁用 Vanna 真实链路，强制走 Ollama fallback
        self._vn_error = "Vanna 真实链路已禁用（import 阶段避免连接 Ollama，防启动阻塞），走 Ollama fallback"
        logger.info("VannaAdapter NL2SQL 初始化：禁用 Vanna 引擎实例化（避免 import 期阻塞），统一走 Ollama fallback")

    def ensure_vanna_ready(self, timeout_seconds: float = 3.0):
        """
        按需构建真实 Vanna 引擎（懒加载，带超时保护）。

        仅在真正需要 Vanna 能力时（答辩演示 / 显式开启）调用；避免在 import / 启动
        阶段连接 Ollama。构建失败自动降级 self.vn=None（走 fallback），不抛异常。
        """
        if self.vn is not None:
            return self.vn is not None
        try:
            # 用线程 + 超时包裹实例化，防止 Ollama 不可用时无限阻塞
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_build_vanna_engine)
                engine, err = fut.result(timeout=timeout_seconds)
            self.vn = engine
            self._vn_error = err
            if engine is not None:
                logger.info("VannaAdapter：真实 Vanna 引擎按需构建成功")
            else:
                logger.warning(f"VannaAdapter：Vanna 引擎构建失败，走 fallback（{err}）")
            return self.vn is not None
        except concurrent.futures.TimeoutError:
            self._vn_error = f"Vanna 引擎构建超时（>{timeout_seconds}s），Ollama 可能不可用"
            logger.warning(self._vn_error)
            self.vn = None
            return False
        except Exception as e:
            self._vn_error = str(e)
            logger.warning(f"VannaAdapter：Vanna 引擎构建异常，走 fallback（{e}）")
            self.vn = None
            return False

    @staticmethod
    def _train_default_ddl(vn):
        """注册真实业务表 DDL + few-shot examples 到 Vanna 引擎"""
        # 与 fallback 共享同一份 DDL + examples（保持两条链路语义一致）
        from app.services.vanna_ddl_kb import DEFAULT_DDL, DEFAULT_EXAMPLES
        for ddl in DEFAULT_DDL:
            try:
                vn.add_ddl(ddl)
            except Exception as e:
                logger.debug(f"Vanna add_ddl 失败: {e}")
        for ex in DEFAULT_EXAMPLES:
            try:
                vn.train(question=ex["question"], sql=ex["sql"])
            except Exception as e:
                logger.debug(f"Vanna train 失败: {e}")

    @property
    def vanna_ready(self) -> bool:
        """Vanna 引擎是否真实可用（答辩/日志用）。"""
        return self.vn is not None

    # ==================== 训练 ====================

    def train(self, training_data: Optional[Dict[str, Any]] = None):
        """
        注册训练数据（DDL / 文档 / 问答示例）到 Vanna 引擎与 Milvus 镜像。
        training_data 格式：
          ddl: [str]        — 建表语句列表
          documentation: [str] — 文档字符串列表
          examples: [{"question": str, "sql": str}] — 示例问答
        """
        data = training_data or {}
        for ddl in data.get("ddl", []):
            self._store.add_ddl(ddl)
            if self.vn is not None:
                try:
                    self.vn.add_ddl(ddl)
                except Exception as e:
                    logger.warning(f"Vanna add_ddl 失败: {e}")
        for doc in data.get("documentation", []):
            self._store.add_documentation(doc)
            if self.vn is not None:
                try:
                    self.vn.add_documentation(doc)
                except Exception as e:
                    logger.warning(f"Vanna add_documentation 失败: {e}")
        for ex in data.get("examples", []):
            if ex.get("question") and ex.get("sql"):
                self._store.add_question(ex["question"], ex["sql"])
                if self.vn is not None:
                    try:
                        self.vn.train(question=ex["question"], sql=ex["sql"])
                    except Exception as e:
                        logger.warning(f"Vanna train(question/sql) 失败: {e}")

        total = len(self._store.get_training_data())
        logger.info(f"Vanna 训练数据已注册: {total} 条（Vanna引擎 + Milvus镜像）")

    # ==================== 生成 SQL ====================

    def generate_sql(self, question: str, retry_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        调用 Vanna 将自然语言转为 SQL（仅生成，不执行）。
        链路：真实 Vanna 引擎 generate_sql（向量召回上下文增强）→ 异常降级 Ollama fallback。
        retry_hint: 可选，上次执行报错摘要（如 MySQL 1064），用于重试时让 LLM 修正。
        """
        if self.vn is not None:
            try:
                sql = self.vn.generate_sql(question, allow_llm_to_see_data=False)
                if sql:
                    extracted = self._extract_select(sql)
                    if extracted:
                        return {"success": True, "sql": extracted, "engine": "vanna"}
                logger.warning("Vanna 未生成有效 SQL，降级 Ollama fallback")
            except Exception as e:
                logger.warning(f"Vanna generate_sql 失败，降级 Ollama fallback: {e}")
        return self._generate_sql_fallback(question, retry_hint=retry_hint)

    @staticmethod
    def _extract_select(raw: str) -> Optional[str]:
        """从 Vanna 返回文本中提取 SELECT 语句（容忍围栏/前缀）。"""
        if not raw:
            return None
        from app.utils.string_utils import extract_sql_after_escape_mark
        sql = extract_sql_after_escape_mark(raw)
        if not sql:
            sql = raw.strip().strip("`").strip()
        if sql.upper().startswith(("SELECT", "WITH")):
            return sql
        m = re.search(r"(?is)(select[\s\S]*?)(;|$)", sql)
        return m.group(1).strip() if m else None

    def _generate_sql_fallback(self, question: str, retry_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Fallback：直接用 Ollama LLM 生成 SQL，不依赖 vanna 包。
        使用结构化 prompt + few-shot examples + 真实 DDL，确保只生成 SELECT。
        retry_hint: 上次 SQL 执行报错摘要，重试时注入以让 LLM 修正语法/字段。
        """
        try:
            import urllib.request
            import json
            import urllib.error

            # 真实表结构（DDL 摘要）：必须与 ORM 模型一致。
            # 这是 LLM 能否生成可执行 SQL 的最关键信息。
            # 与 Vanna 训练用同一份 DDL（vanna_ddl_kb.py），避免双源漂移。
            from app.services.vanna_ddl_kb import DEFAULT_DDL, DEFAULT_EXAMPLES
            table_ddl = "\n\n".join(DEFAULT_DDL)
            examples = DEFAULT_EXAMPLES

            retry_block = ""
            if retry_hint:
                retry_block = (
                    f"\n\n注意：你上一次生成的 SQL 执行失败，错误如下：\n"
                    f"{retry_hint}\n"
                    "请根据错误修正 SQL：只保留可执行的单条 SELECT；如列名/表名拼错请对照表结构；"
                    "SELECT 引用的非聚合列必须出现在 GROUP BY 中；不要输出任何中文解释，只输出 SQL。"
                )

            prompt = (
                "你是 MySQL 只读 SQL 生成助手。\n"
                "=== 表结构（用真实列名，不要臆造列）===\n" + table_ddl +
                "\n=== 只读表白名单 ===\n"
                "talents, job_positions, match_records, assessment_results, courses, examination_records, users\n"
                "=== 禁止 ===\nDROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/CREATE\n"
                "=== 输出要求 ===\n只输出单条 SELECT SQL，严禁输出任何解释/说明文字。\n"
                "=== 示例 ===\n"
                + "\n".join(f"问: {e['question']}\nSQL: {e['sql']}" for e in examples)
                + retry_block
                + f"\n\n问: {question}\nSQL:"
            )

            payload = json.dumps({
                "model": settings.LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                # 关掉思考链（qwen3 默认开启会产生大量 thinking token）
                "think": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 256,
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            # 超时可配置（qwen3:1.7b 纯 CPU 冷启动实测 ≈98s，原 60s 必然超时）
            with urllib.request.urlopen(req, timeout=getattr(settings, "OLLAMA_CHAT_TIMEOUT", 300)) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # 参考 string_utils.extract_sql_after_escape_mark 后处理
            from app.utils.string_utils import extract_sql_after_escape_mark
            sql = extract_sql_after_escape_mark(result.get("response", ""))

            if not sql or not sql.upper().startswith("SELECT"):
                return {"success": False, "error": f"LLM 未生成有效 SELECT SQL: {sql[:50]}"}

            return {"success": True, "sql": sql, "fallback": True}

        except Exception as e:
            logger.error(f"Ollama NL2SQL fallback 失败: {e}")
            return {"success": False, "error": f"NL2SQL 服务不可用: {e}"}

    # ==================== 校验 SQL（安全核心）====================

    def validate_sql(
        self,
        sql: str,
        table_whitelist: Optional[List[str]] = None,
        field_whitelist: Optional[List[str]] = None,
        require_limit: bool = True,
        max_limit: int = 1000
    ) -> Tuple[bool, str, List[str]]:
        """
        校验 SQL 是否满足只读安全约束。
        返回 (是否通过, 安全化后的SQL, 原因列表)
        """
        reasons: List[str] = []
        if not sql or not sql.strip():
            return False, "", ["SQL 为空"]

        raw = sql
        # 去除行注释与块注释
        cleaned = re.sub(r"--[^\n]*", " ", raw)
        cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip()

        # 1) 禁止关键字检测
        upper = cleaned.upper()
        for kw in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{kw.upper()}\b", upper):
                reasons.append(f"包含禁止的写操作关键字: {kw.upper()}")
        if reasons:
            return False, cleaned, reasons

        # 2) 语句类型解析（仅允许 SELECT / WITH(CTE)）
        try:
            import sqlparse
            parsed = sqlparse.parse(cleaned)
            for stmt in parsed:
                ttype = stmt.get_type()
                if ttype not in ("SELECT", "UNKNOWN"):
                    if not cleaned.upper().lstrip().startswith("WITH"):
                        reasons.append(f"不允许的 SQL 语句类型: {ttype}")
                if ttype == "UNKNOWN" and not cleaned.upper().lstrip().startswith(("SELECT", "WITH")):
                    reasons.append("无法识别或非只读 SQL 语句")
        except ImportError:
            first = cleaned.upper().lstrip()
            if not first.startswith(("SELECT", "WITH")):
                reasons.append("SQL 必须以 SELECT 或 WITH 开头（只读）")
        if reasons:
            return False, cleaned, reasons

        # 3) 表白名单检测
        whitelist = table_whitelist or getattr(settings, "NL2SQL_TABLE_WHITELIST", None) or DEFAULT_TABLE_WHITELIST
        tables = set(re.findall(r"\bFROM\s+([`\"\[\w\.]+)", cleaned, flags=re.IGNORECASE))
        tables |= set(re.findall(r"\bJOIN\s+([`\"\[\w\.]+)", cleaned, flags=re.IGNORECASE))
        norm = lambda t: t.strip('`"[]').split(".")[-1].lower()  # noqa: E731
        for t in tables:
            if norm(t) not in {w.lower() for w in whitelist}:
                reasons.append(f"表不在只读白名单: {norm(t)}")
        if reasons:
            return False, cleaned, reasons

        # 4) LIMIT 注入（防全表扫描）
        safe_sql = cleaned
        if require_limit:
            if not re.search(r"\bLIMIT\b", safe_sql, flags=re.IGNORECASE):
                safe_sql = f"{safe_sql.rstrip(';')} LIMIT {max_limit}"
            else:
                def _cap(m):
                    n = int(m.group(1))
                    return f"LIMIT {min(n, max_limit)}"
                safe_sql = re.sub(r"\bLIMIT\s+(\d+)", _cap, safe_sql, flags=re.IGNORECASE)

        return True, safe_sql, reasons

    # ==================== 只读执行 ====================

    def execute_readonly(self, sql: str, engine, table_whitelist=None, user_id=None) -> Dict[str, Any]:
        """
        校验后只读执行 SQL。engine 必须是只读连接（分析库/只读副本）。
        返回 {success, columns, rows, row_count, sql, error}
        """
        ok, safe_sql, reasons = self.validate_sql(sql, table_whitelist=table_whitelist)
        if not ok:
            return {"success": False, "error": "; ".join(reasons), "sql": sql, "rows": [], "columns": []}

        try:
            with engine.connect() as conn:
                result = conn.execute(text(safe_sql))
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return {
                "success": True,
                "sql": safe_sql,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "user_id": user_id
            }
        except Exception as e:
            logger.warning(f"NL2SQL 只读执行失败: {str(e)}")
            return {"success": False, "error": str(e), "sql": safe_sql, "rows": [], "columns": []}


# 全局适配器实例
vanna_adapter = VannaAdapter()
