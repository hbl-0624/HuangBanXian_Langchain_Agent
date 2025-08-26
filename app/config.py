import os
from dotenv import load_dotenv

# 加载环境变量（确保.env文件被正确读取）
load_dotenv(override=True)

class Config:
    """项目配置类"""

    # OpenAI配置
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # 必须在.env中配置
    OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.chatanywhere.tech/v1")  # 可自定义代理
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    # 第三方API配置
    SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
    YUAN_MENG_JU_API_KEY = os.getenv("YUAN_MENG_JU_API_KEY")

    # Azure TTS配置
    AZURE_TTS_KEY = os.getenv("AZURE_TTS_KEY")
    AZURE_TTS_REGION = os.getenv("AZURE_TTS_REGION", "eastus")
    TTS_API_URL = f"https://{AZURE_TTS_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

    # 代理配置：针对国际版 Azure，正确格式（键带 //）
    HTTP_PROXY = os.getenv("HTTP_PROXY", "").strip()  # 从.env加载 HTTP_PROXY
    HTTPS_PROXY = os.getenv("HTTPS_PROXY", "").strip()  # 从.env加载 HTTPS_PROXY

    # 逻辑：仅当代理地址有效时，生成正确格式的代理字典
    if HTTP_PROXY and HTTPS_PROXY:
        # 正确格式：键是 "http://"/"https://"，值是代理地址（带 http://）
        PROXIES = {
            "http://": HTTP_PROXY,  # 例："http://127.0.0.1:7890"
            "https://": HTTPS_PROXY  # 例："http://127.0.0.1:7890"
        }
        print(f"✅ 已加载代理配置（国际版 Azure 专用）：{PROXIES}")  # 新增：打印代理，确认格式
    else:
        PROXIES = {}  # 无代理时为空字典，避免报错
    # 路径配置（以本文件上级目录为根）
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    VOICES_DIR = os.path.join(BASE_DIR, "voices")
    QDRANT_PATH = os.path.join(BASE_DIR, "local_qdrant")

    # 应用配置
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    SESSION_ID = "huangbanxian_chat_session"
    MAX_TOKEN_LIMIT = 1000
    TTS_WAIT_TIMEOUT = 10  # 语音生成最大等待时间(秒)

# 创建配置实例
config = Config()

# 确保目录存在
os.makedirs(config.VOICES_DIR, exist_ok=True)
os.makedirs(config.QDRANT_PATH, exist_ok=True)
