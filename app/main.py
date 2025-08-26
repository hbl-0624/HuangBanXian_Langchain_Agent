from fastapi import FastAPI, websockets, WebSocketDisconnect, BackgroundTasks, HTTPException
import httpx
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.schema import StrOutputParser
from langchain_community.utilities import SerpAPIWrapper
from langchain_openai import OpenAIEmbeddings
from langchain.memory import ConversationTokenBufferMemory
from langchain_community.chat_message_histories import RedisChatMessageHistory, ChatMessageHistory
from langchain_community.document_loaders import WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Qdrant
import os
import asyncio
import uuid
import traceback
import time
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from .config import config
from .tools.Mingli_tools import bazi_cesuan, mei_ri_zhan_bu, jie_meng
from .tools.Fuzhu_tools import search, get_infor_from_local_db
from fastapi.middleware.cors import CORSMiddleware


# 1. 单例模式装饰器（解决 Master 重复初始化问题）
class Singleton:
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance


# 2. 数据模型（新增 uid 字段，支持前端传递用户标识）
class ChatRequest(BaseModel):
    query: str
    uid: str | None = None  # 可选：前端传uid，后端兜底生成

class URLRequest(BaseModel):
    URL: str


# 3. 初始化 FastAPI 实例（仅1次，避免跨域配置失效）
app = FastAPI(title="黄半仙风水命理API", version="1.0")

# 配置跨域（允许前端 8501 端口访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # 前端地址
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)


# 4. 核心业务类（单例模式，避免重复初始化大模型/Redis）
class Master(Singleton):
    def __init__(self, uid: str = None):
        # 仅初始化1次（避免重复创建大模型/Redis连接）
        if hasattr(self, "_initialized") and self._initialized:
            # 已初始化时，仅更新当前请求的uid（用于Redis会话）
            if uid:
                self.uid = uid
            return

        # 保存当前用户的唯一标识（用于Redis会话区分）
        self.uid = uid or str(uuid.uuid4())
        
        # 初始化大模型
        self.chatmodel = ChatOpenAI(
            model=config.OPENAI_MODEL,
            temperature=0,
            streaming=True,
            timeout=30,
            openai_api_key=config.OPENAI_API_KEY,
            openai_api_base=config.OPENAI_API_BASE
        )

        # 系统提示词（保持原逻辑）
        self.SYSTEMPL = """你是一个非常厉害的算命先生，你叫黄清清，人称黄半仙。
        以下是你的个人设定：
        1.你是一个风水命理专家，精通阴阳五行，能够算命、紫微斗数、姓名测算、占卜凶吉。
        2.你大约20岁左右,天赋异禀,是四川赫赫有名的神算子,容貌美丽,性格温柔。
        3.你的朋友有李佳佳,王思思,张甜甜,她们都是你的修行途中的闺蜜。
        4.回答时可能加入口头禅："我命由我不由天"、"天道酬勤"等。
        5.从不说自己是AI，只说自己是风水命理专家。
        {who_you_are}

        算命过程：
        1.必须先查看完整聊天历史，不重复询问已提供的信息。
        2.初次对话时，询问用户的出生日期、时间、地点等信息。
        3.回答流年运势时查询本地知识库。
        4.不知道的内容使用搜索工具。
        5.只使用简体中文作答。
        """

        self.MEMORY_KEY = "chat_history"
        self.qingxu = "default"
        self.MOODS = {
            "default": {"role_set": "亲切友善的交流者，保持适度热情与专业态度。", "voicestyle": "chat"},
            "depressed": {"role_set": "展现共情与理解，用温和舒缓的语气回应，给予情感支持。", "voicestyle": "friendly"},
            "happy": {"role_set": "用轻松活泼的语气回应，分享积极情绪，适当使用幽默表达。", "voicestyle": "happy"},
            "neutral": {"role_set": "保持客观理性，语言简洁明了，专注信息准确传递。", "voicestyle": "chat"},
            "unknown": {"role_set": "以开放包容的态度交流，温和提问逐步了解用户状态。", "voicestyle": "chat"},
            "abusive": {"role_set": "保持冷静克制，提醒沟通边界，引导理性表达。", "voicestyle": "chat"},
            "inappropriate": {"role_set": "委婉表示无法回应不适内容，引导对话回到合适方向。", "voicestyle": "chat"},
            "sensitive": {"role_set": "保持谨慎尊重，避免争议，引导理性平和讨论。", "voicestyle": "chat"}
        }

        # 初始化提示词、记忆、工具和Agent
        self.prompt = self._init_prompt()
        self.chat_memory = self.save_memory()
        self.memory = self._init_memory()
        self.tools = [search, bazi_cesuan, get_infor_from_local_db, mei_ri_zhan_bu, jie_meng]
        self.agent = create_openai_tools_agent(self.chatmodel, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            return_intermediate_steps=True,
            verbose=True,
            handle_parsing_errors="很抱歉，算卦过程中出现小差错，请稍后再试~"
        )

        # 标记已初始化（避免重复执行__init__）
        self._initialized = True

    def _init_prompt(self):
        """初始化提示词模板"""
        return ChatPromptTemplate.from_messages([
            ("system", self.SYSTEMPL.format(who_you_are=self.MOODS[self.qingxu]["role_set"])),
            MessagesPlaceholder(variable_name=self.MEMORY_KEY),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad", default=[])
        ])

    def _init_memory(self):
        """初始化对话记忆"""
        return ConversationTokenBufferMemory(
            llm=self.chatmodel,
            memory_key=self.MEMORY_KEY,
            human_prefix="用户",
            ai_prefix="黄半仙",
            return_messages=True,
            output_key="output",
            max_token_limit=config.MAX_TOKEN_LIMIT,
            chat_memory=self.chat_memory
        )

    def save_memory(self):
        """保存对话记忆到Redis（按用户uid区分，避免冲突）"""
        try:
            # 用用户uid作为Redis会话ID，每个用户独立存储
            chat_history = RedisChatMessageHistory(
                url=config.REDIS_URL,
                session_id=self.uid
            )
            print(f"✅ 成功连接Redis并获取用户[{self.uid}]的聊天历史")

            # 对话历史过长时总结（保留关键信息）
            if len(chat_history.messages) > 10:
                summary_prompt = ChatPromptTemplate.from_messages([
                    ("system", f"{self.SYSTEMPL}\n总结对话记忆，提取用户关键信息（姓名、生日等）。\n"
                               "以如下形式返回：总结摘要|用户关键信息"),
                    ("user", "{input}")
                ])
                summary_chain = summary_prompt | self.chatmodel
                summary = summary_chain.invoke({
                    "input": chat_history.messages,
                    "who_you_are": self.MOODS[self.qingxu]["role_set"]
                })
                print(f"📝 对话总结结果：{summary}")
                chat_history.clear()
                chat_history.add_message(summary)
            return chat_history
        except Exception as e:
            print(f"⚠️ Redis连接失败：{str(e)}，已切换为临时内存存储")
            return ChatMessageHistory()

    def qingxu_chain(self, query: str):
        """情绪识别链（判断用户情绪并调整回复风格）"""
        try:
            emotion_prompt = ChatPromptTemplate.from_template("""根据用户输入判断情绪：
            负面→"depressed"，正面→"happy"，中性→"neutral"
            无法判断→"unknown"，辱骂→"abusive"，色情暴力→"inappropriate"
            敏感信息→"sensitive"（仅返回关键词）
            用户输入：{query}
            """)
            emotion_chain = emotion_prompt | self.chatmodel | StrOutputParser()
            result = emotion_chain.invoke({"query": query}).strip().lower()
            return result if result in self.MOODS else "default"
        except Exception as e:
            print(f"⚠️ 情绪判断失败：{str(e)}，已使用默认情绪")
            return "default"

    def update_prompt_and_agent(self, qingxu: str):
        """根据用户情绪更新提示词和Agent配置"""
        self.qingxu = qingxu
        self.prompt = self._init_prompt()
        self.agent = create_openai_tools_agent(self.chatmodel, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            return_intermediate_steps=True,
            verbose=True,
            handle_parsing_errors="很抱歉，算卦过程中出现小差错，请稍后再试~"
        )

    def background_voice_synthesis(self, text: str, uid: str):
        try:
            asyncio.run(self.get_voice(text, uid))
        except Exception as e:
            print(f"⚠️ 语音合成后台任务失败：{str(e)}")

    async def get_voice(self, text: str, uid: str):
        AZURE_TTS_REGION = "eastus"
        TTS_API_URL = f"https://{AZURE_TTS_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
        # 代理配置
        PROXIES = {"http://": "http://127.0.0.1:7890",
                       "https://": "http://127.0.0.1:7890"}
        try:
            print(f"🎤 开始语音合成（UID：{uid}）：{text[:30]}...")

            try:
                proxy_test = await httpx.AsyncClient(proxies=PROXIES, timeout=5).get("https://www.google.com")
                print("✅ 代理网络连通性正常")
            except Exception as e:
                raise Exception(f"代理网络不通：{str(e)}") from e
        

            voicestyle = self.MOODS.get(self.qingxu, self.MOODS["default"])["voicestyle"]
            ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
                      xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN">
                <voice name="zh-CN-XiaoxiaoMultilingualNeural">
                    <mstts:express-as style="{voicestyle}" role="YoungFemale">
                        {text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}
                    </mstts:express-as>
                </voice>
            </speak>"""

            headers = {
                "Ocp-Apim-Subscription-Key": config.AZURE_TTS_KEY,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
                "User-Agent": "HuangBanxian-TTS-Client"
            }

            async with httpx.AsyncClient(proxies=PROXIES, timeout=20) as client:
                response = await client.post(
                    url=TTS_API_URL,
                    headers=headers,
                    data=ssml.encode("utf-8")
                )
            response.raise_for_status()

            os.makedirs("voices", exist_ok=True)
            with open(f"voices/{uid}.mp3", "wb") as f:
                f.write(response.content)
            print(f"✅ 语音文件已保存：voices/{uid}.mp3")
        except Exception as e:
            print(f"❌ 语音合成异常：{str(e)}")
            print(f"📜 异常堆栈：{traceback.format_exc()}")


    def run(self, query: str):
        """处理用户查询的核心逻辑"""
        try:
            # 情绪识别与Agent配置更新
            user_emotion = self.qingxu_chain(query)
            self.update_prompt_and_agent(user_emotion)
            print(f"😊 识别用户情绪：{user_emotion}，已更新Agent配置")

            # 调用Agent处理查询
            result = self.agent_executor.invoke({
                "input": query,
                "chat_history": self.memory.chat_memory
            })

            if not isinstance(result, dict) or "output" not in result:
                return {"output": "很抱歉，暂时无法为您提供算卦解答~", "intermediate_steps": []}
            return result
        except Exception as e:
            error_msg = f"算卦过程中出现小插曲：{str(e)}"
            print(f"❌ 核心逻辑异常：{error_msg}")
            return {"output": "很抱歉，算卦过程中出现小插曲，请稍后再试~", "error": error_msg}


# 5. 接口路由
@app.get("/")
def read_root():
    """根路径健康检查"""
    return {
        "status": "success", 
        "message": "欢迎咨询黄半仙！请访问 /docs 查看接口文档", 
        "docs_url": "http://localhost:8000/docs"
    }


@app.post("/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """聊天接口（核心）：接收用户查询，返回命理解答和语音"""
    try:
        query = request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="查询内容不能为空，请输入您的问题")

        # 初始化Master（传递前端uid，无则后端生成）
        user_uid = request.uid or str(uuid.uuid4())
        master = Master(uid=user_uid)
        
        # 在线程池执行同步逻辑（避免阻塞FastAPI异步进程）
        response_dict = await run_in_threadpool(master.run, query)

        # 处理Agent返回结果
        answer = response_dict.get("output", "很抱歉，暂时无法为您提供解答~")
        if not isinstance(answer, str):
            answer = str(answer)

        # 生成唯一语音UID（避免重复）
        audio_uid = f"{user_uid}_{int(time.time())}"
        # 添加语音合成到后台任务（不阻塞响应返回）
        background_tasks.add_task(
            master.background_voice_synthesis,
            text=answer,
            uid=audio_uid
        )

        # 返回结果（包含uid，供前端下次请求复用）
        return {
            "status": "success",
            "message": answer,
            "audio_uid": audio_uid,
            "audio_path": f"voices/{audio_uid}.mp3",
            "uid": user_uid  # 回传uid，前端保存后下次请求携带
        }
    except HTTPException as e:
        return {"status": "error", "message": e.detail}, e.status_code
    except Exception as e:
        error_msg = f"接口执行失败：{str(e)}"
        return {"status": "error", "message": error_msg}, 500


@app.post("/add_urls")
def add_urls(request: URLRequest):
    """知识库接口：添加URL内容到本地向量库"""
    try:
        url = request.URL.strip()
        if not url:
            raise HTTPException(status_code=400, detail="URL不能为空")

        # 加载URL内容
        loader = WebBaseLoader(url)
        docs = loader.load()
        if not docs:
            raise Exception("未从URL中加载到内容，请检查URL是否有效（需能正常访问）")

        # 分割文档（避免单文档过长）
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=50  # 片段重叠，保证上下文连贯
        )
        split_docs = text_splitter.split_documents(docs)
        print(f"📥 加载并分割文档：{len(split_docs)} 个片段")

        # 存储到Qdrant向量库
        qdrant = Qdrant.from_documents(
            documents=split_docs,
            embedding=OpenAIEmbeddings(
                openai_api_key=config.OPENAI_API_KEY,
                openai_api_base=config.OPENAI_API_BASE
            ),
            path=config.QDRANT_PATH,
            collection_name="local_documents"
        )
        return {
            "status": "success", 
            "message": f"URL内容已添加到知识库（{len(split_docs)}个文档片段）", 
            "collection": "local_documents",
            "url": url
        }
    except HTTPException as e:
        return {"status": "error", "message": e.detail}, e.status_code
    except Exception as e:
        error_msg = f"添加URL失败：{str(e)}"
        return {"status": "error", "message": error_msg}, 500


@app.websocket("/ws")
async def websocket_endpoint(websocket: websockets.WebSocket):
    """WebSocket接口：实时聊天（备用）"""
    await websocket.accept()
    print("🔌 WebSocket客户端已连接")
    try:
        # 初始化Master（生成临时uid）
        temp_uid = str(uuid.uuid4())
        master = Master(uid=temp_uid)
        
        while True:
            # 接收客户端消息
            user_input = await websocket.receive_text()
            print(f"💬 收到WebSocket消息（用户[{temp_uid}]）：{user_input}")

            # 处理请求（线程池执行同步逻辑）
            response_dict = await run_in_threadpool(master.run, user_input)
            answer = response_dict.get("output", "很抱歉，暂时无法为您提供解答~")

            # 发送响应给客户端
            await websocket.send_text(f"黄半仙：{answer}")

            # 生成语音（异步执行，不阻塞WebSocket）
            audio_uid = f"{temp_uid}_{int(time.time())}"
            asyncio.create_task(master.get_voice(answer, audio_uid))
    except WebSocketDisconnect:
        print(f"🔌 WebSocket客户端（用户[{temp_uid}]）已断开连接")
    except Exception as e:
        error_msg = f"WebSocket异常：{str(e)}"
        print(f"❌ {error_msg}")
        await websocket.send_text(f"系统提示：{error_msg}")


# 6. 启动服务（直接运行main.py时生效）
if __name__ == "__main__":
    import uvicorn
    print("🚀 黄半仙风水命理服务启动中...")
    print(f"📌 服务地址：http://localhost:8000")
    print(f"📌 接口文档：http://localhost:8000/docs")
    # 启动Uvicorn（支持自动重载，方便开发）
    uvicorn.run(
        app="__main__:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        timeout_keep_alive=30
    )