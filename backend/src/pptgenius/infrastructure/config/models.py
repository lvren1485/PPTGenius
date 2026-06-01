from pydantic import BaseModel


class AppConfig(BaseModel):
    name: str = "PPTGenius"
    version: str = "0.1.0"


class WorkspaceConfig(BaseModel):
    root: str = "./data/workspace"
    input_dir: str = "input"
    output_dir: str = "output"
    knowledge_dir: str = "knowledge"
    logs_dir: str = "logs"


class RAGConfig(BaseModel):
    algorithm: str = "bm25"
    top_k: int = 5
    supported_formats: list[str] = [".txt", ".pdf", ".docx", ".csv", ".xlsx"]


class OutlineAgentConfig(BaseModel):
    mode: str = "mix"  # max_iteration | pass_score | mix
    max_iterations: int = 5
    pass_score: float = 8.0  # 0-10, used by pass_score / mix modes
    evaluation_threshold: float = 0.7


class PPTAgentConfig(BaseModel):
    mode: str = "sub_agent"  # sub_agent | freedom | super_freedom
    max_retries_per_slide: int = 3
    slide_timeout_seconds: int = 120


class CacheConfig(BaseModel):
    trim_max_tokens: int = 8000
    enable_node_cache: bool = True


class AgentConfig(BaseModel):
    outline: OutlineAgentConfig = OutlineAgentConfig()
    ppt: PPTAgentConfig = PPTAgentConfig()
    cache: CacheConfig = CacheConfig()


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-v4-flash"
    temperature: float = 0.7
    max_tokens: int = 50000


class DBConfig(BaseModel):
    type: str = "mysql"
    url: str = "mysql+asyncmy://root:root@localhost:3306/pptgenius"


class LogConfig(BaseModel):
    level: str = "INFO"
    fmt: str = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    file_enabled: bool = True
    file_path: str = "logs/app.log"
    file_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    file_backup_count: int = 5


class WebSearchConfig(BaseModel):
    enabled: bool = True
    engine: str = "duckduckgo"
    max_results: int = 5
    timeout: int = 15
    # API keys for paid engines go in config.local.yaml
    bing_api_key: str = ""
    google_api_key: str = ""
    google_cx: str = ""
    tavily_api_key: str = ""
    searxng_base_url: str = ""


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    rag: RAGConfig = RAGConfig()
    agent: AgentConfig = AgentConfig()
    llm: LLMConfig = LLMConfig()
    db: DBConfig = DBConfig()
    log: LogConfig = LogConfig()
    web_search: WebSearchConfig = WebSearchConfig()
