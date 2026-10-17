"""
应用配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 显式加载 .env（pydantic-settings 2.x 不再自动调用 load_dotenv）
# 路径取 config.py 同级父目录（backend/app/core/ → backend/）
_CONFIG_DIR = Path(__file__).resolve().parent  # .../backend/app/core/
_BACKEND_DIR = _CONFIG_DIR.parent.parent         # .../backend/
load_dotenv(_BACKEND_DIR / ".env", override=False)

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import List, Optional


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"  # 允许额外字段
    )

    # 应用基础配置
    APP_NAME: str = "AI数字化人才平台"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "企业级AI原生数字化人才智能平台"
    DEBUG: bool = True
    VERSION: str = "1.0.0"  # 兼容.env

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1
    KEEP_ALIVE: int = 60

    # CORS配置
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:8080"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = ["*"]
    CORS_ALLOW_HEADERS: list = ["*"]

    # API配置
    API_V1_PREFIX: str = "/api/v1"
    API_PREFIX: str = "/api/v1"  # 兼容main.py

    # JWT配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_SECURE: bool = False

    # 安全策略（P0 安全加固）
    # 是否开放游客自助注册。默认关闭 —— 账号只能由管理员在后台创建，
    # 避免任何人自助开户绕过 RBAC 第一道门。改为 true 可恢复自助注册。
    ALLOW_SELF_REGISTER: bool = False
    INITIAL_ADMIN_USERNAME: str = "admin"
    INITIAL_ADMIN_PASSWORD: str = ""

    # 数据库配置
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "root"
    MYSQL_DATABASE: str = "digital_talent"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DATABASE: str = "talent_analytics"

    # Redis配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: int = 30
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 10

    # Milvus配置
    MILVUS_URI: str = "http://localhost:19530"
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_DB: str = "default"
    MILVUS_COLLECTION: str = "talent_vectors"
    MILVUS_ALIAS: str = "default"
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""
    MILVUS_COLLECTION_TALENT: str = "talent_resume"
    MILVUS_COLLECTION_JOB: str = "job_position"
    MILVUS_COLLECTION_KNOWLEDGE: str = "knowledge_base"
    EMBEDDING_DIM: int = 1024  # bge-m3 向量维度（与 EMBEDDING_MODEL 保持一致）

    # 文件上传配置
    MAX_UPLOAD_SIZE: int = 52428800  # 50MB
    UPLOAD_DIR: str = "./uploads"
    MEDIA_ROOT: str = "./media"
    MEDIA_URL: str = "/media"

    # MinIO对象存储配置（宿主机端口：9100=API，9101=Console）
    MINIO_ENDPOINT: str = "localhost:9100"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "resumes"
    MINIO_SECURE: bool = False

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    # AI配置
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "qwen3:1.7b"
    EMBEDDING_MODEL: str = "bge-m3:latest"
    # 本地 Ollama 推理超时（秒）。2026-10-15 实测：qwen3:1.7b 在纯 CPU 上
    # 冷启动 + 生成 128 token 需 ≈98s，原硬编码 timeout=60 必然超时 →
    # RAG 问答恒定降级为"仅返回检索片段"。改为可配置，默认 300s。
    OLLAMA_CHAT_TIMEOUT: int = 300
    OLLAMA_EMBED_TIMEOUT: int = 60
    # 单次生成的 token 上限。2026-10-17 实测：不设上限时，简历解析 Agent 的
    # 一次调用在本地 CPU 上持续生成到 3586 token 仍未结束（≈7.5 token/s → 478s），
    # 必然撞穿 Nginx `proxy_read_timeout 300s`，表现为「简历解析 504/不可用」。
    # 这里设硬上限，让失控生成变成"被截断 → extract_json 失败 → 规则层兜底"，
    # 即失败降级为秒级，而不是卡满网关超时。1024 足够容纳该 prompt 要求的
    # talent + tags + portrait 三段 JSON（有富余）。
    OLLAMA_NUM_PREDICT: int = 1024

    # Vanna NL2SQL 引擎（ChromaDB_VectorStore + Ollama 组合）
    VANNA_CHROMA_PATH: str = "./vanna_chroma"
    # 引擎按需构建的超时（秒）：过短会在 ChromaDB 初始化稍慢时误判为不可用
    VANNA_INIT_TIMEOUT: int = 15

    # LLM策略：ollama | silicon_flow（简历解析+NL2SQL用）
    LLM_STRATEGY: str = "ollama"  # 主推理策略
    # SiliconFlow（用于简历解析、NL2SQL等高精度任务）
    SILICON_FLOW_API_KEY: str = ""
    SILICON_FLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    SILICON_FLOW_MODEL: str = "deepseek-ai/DeepSeek-V4-Flash"
    # 阿里百炼（已注释 2026-09-02：实际未使用——Dify中台5大智能体全部用 workflow 模式，
    # Workflow 内部 LLM 在 Dify 控制台配置，不在本项目代码中调 LLM）
    # 原始字段定义保留备查，便于回滚：
    # ALI_BAILIAN_API_KEY: str = ""
    # ALI_BAILIAN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # ALI_BAILIAN_MODEL: str = "qwen3.8-max"

    # Dify 中台配置（AI应用中台/Prompt管理/模型路由/知识库运营；不承载核心业务Agent编排）
    DIFY_ENABLED: bool = False
    DIFY_API_BASE: str = "http://localhost/v1"
    DIFY_API_KEY: str = ""
    DIFY_APP_MODE: str = "workflow"  # completion | chat | workflow
    # 五大 Agent 对应的 Dify Chatflow/Workflow App Key（导入后回填）
    DIFY_APP_KEY_RESUME: str = ""        # 档案解析智能体
    DIFY_APP_KEY_ASSESSMENT: str = ""    # 测评分析智能体
    DIFY_APP_KEY_MATCHING: str = ""      # 岗位匹配智能体
    DIFY_APP_KEY_TRAINING: str = ""      # 培训赋能智能体
    DIFY_APP_KEY_DATA_DECISION: str = "" # 数据决策智能体
    # Dify 工作流调用后端 /api/v1/agents/* 时使用的长期 Service Token（Bearer，避免 30min 过期）
    DIFY_BACKEND_TOKEN: str = ""

    @model_validator(mode="after")
    def validate_security_settings(self):
        """生产模式拒绝弱密钥和弱初始管理员密码。"""
        if not self.DEBUG:
            if (
                len(self.SECRET_KEY) < 32
                or self.SECRET_KEY == "your-secret-key-change-in-production"
                or "CHANGE_ME" in self.SECRET_KEY
            ):
                raise ValueError("生产模式必须配置至少 32 位的随机 SECRET_KEY")
            if self.INITIAL_ADMIN_PASSWORD and (
                len(self.INITIAL_ADMIN_PASSWORD) < 12
                or "CHANGE_ME" in self.INITIAL_ADMIN_PASSWORD
            ):
                raise ValueError("INITIAL_ADMIN_PASSWORD 必须是至少 12 位的非示例密码")
            weak_secrets = {
                "MYSQL_PASSWORD": self.MYSQL_PASSWORD,
                "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD,
                "REDIS_PASSWORD": self.REDIS_PASSWORD,
                "MINIO_SECRET_KEY": self.MINIO_SECRET_KEY,
            }
            for name, value in weak_secrets.items():
                if len(value or "") < 12 or "CHANGE_ME" in (value or ""):
                    raise ValueError(f"生产模式必须为 {name} 配置至少 12 位的非示例密码")
            if not self.AUTH_COOKIE_SECURE:
                raise ValueError("生产模式必须启用 AUTH_COOKIE_SECURE 并通过 HTTPS 提供服务")
            if not self.CORS_ORIGINS or any(
                origin == "*" or "localhost" in origin or "127.0.0.1" in origin
                for origin in self.CORS_ORIGINS
            ):
                raise ValueError("生产模式必须将 CORS_ORIGINS 配置为真实 HTTPS 站点")
        return self

    @property
    def MYSQL_URI(self) -> str:
        """MySQL连接URI"""
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def MYSQL_ASYNC_URI(self) -> str:
        """MySQL异步连接URI"""
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def POSTGRES_URI(self) -> str:
        """PostgreSQL连接URI"""
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"

    @property
    def POSTGRES_ASYNC_URI(self) -> str:
        """PostgreSQL异步连接URI"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"

    @property
    def REDIS_URI(self) -> str:
        """Redis连接URI"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# 全局配置实例
settings = Settings()
