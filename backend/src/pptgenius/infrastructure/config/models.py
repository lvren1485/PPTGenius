from pydantic import BaseModel, Field


class WorkspaceConfig(BaseModel):
    root: str = "./data/workspace"
    input_dir: str = "input"
    output_dir: str = "output"
    knowledge_dir: str = "knowledge"


class RAGConfig(BaseModel):
    top_k: int = Field(default=5, description="BM25 检索返回条数")


class OutlineAgentConfig(BaseModel):
    generator_max_retries: int = Field(default=3, description="大纲生成单 section 失败最大重试次数")


class CacheConfig(BaseModel):
    trim_max_tokens: int = Field(default=8000, description="上下文超出时裁剪阈值")
    enable_node_cache: bool = Field(default=True, description="启用 LangGraph 节点缓存")
    summarize_threshold: float = Field(default=0.7, description="context_usage > 此值触发对话历史摘要")


class AgentConfig(BaseModel):
    outline: OutlineAgentConfig = OutlineAgentConfig()
    cache: CacheConfig = CacheConfig()


class LLMConfig(BaseModel):
    provider: str = Field(default="deepseek", description="仅支持: deepseek")
    base_url: str = Field(default="https://api.deepseek.com/v1")
    api_key: str = Field(default="")
    model: str = Field(default="deepseek-v4-flash")
    temperature: float = Field(default=0.7, description="0.0 ~ 2.0")
    max_tokens: int = Field(default=50000)


class DBConfig(BaseModel):
    url: str = "mysql+asyncmy://root:root@localhost:3306/pptgenius"


class LogConfig(BaseModel):
    level: str = Field(default="INFO", description="仅支持: DEBUG | INFO | WARNING | ERROR | CRITICAL")
    fmt: str = Field(default="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    datefmt: str = Field(default="%Y-%m-%d %H:%M:%S")
    file_enabled: bool = Field(default=True)
    file_path: str = Field(default="logs/app.log")
    file_max_bytes: int = Field(default=10 * 1024 * 1024, description="10 MB")
    file_backup_count: int = Field(default=5)


class WebSearchConfig(BaseModel):
    enabled: bool = Field(default=True)
    engine: str = Field(default="duckduckgo", description="仅支持: duckduckgo | searxng")
    max_results: int = Field(default=5)
    timeout: int = Field(default=15, description="单次搜索/抓取超时秒数")
    searxng_base_url: str = Field(default="", description="engine=searxng 时必须填写")


class Settings(BaseModel):
    workspace: WorkspaceConfig = WorkspaceConfig()
    rag: RAGConfig = RAGConfig()
    agent: AgentConfig = AgentConfig()
    llm: LLMConfig = LLMConfig()
    db: DBConfig = DBConfig()
    log: LogConfig = LogConfig()
    web_search: WebSearchConfig = WebSearchConfig()
