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
    bm25_index_file: str = "bm25_index.pkl"
    supported_formats: list[str] = [".txt", ".pdf", ".docx", ".csv", ".xlsx"]


class OutlineAgentConfig(BaseModel):
    max_iterations: int = 5
    evaluation_threshold: float = 0.7


class CacheConfig(BaseModel):
    trim_max_tokens: int = 8000
    enable_node_cache: bool = True


class AgentConfig(BaseModel):
    outline: OutlineAgentConfig = OutlineAgentConfig()
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


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    rag: RAGConfig = RAGConfig()
    agent: AgentConfig = AgentConfig()
    llm: LLMConfig = LLMConfig()
    db: DBConfig = DBConfig()
