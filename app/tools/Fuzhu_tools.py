from langchain.agents import tool
from langchain_community.utilities import SerpAPIWrapper
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from langchain_openai import OpenAIEmbeddings
from ..config import config


@tool
def search(query: str):
    '''只有需要了解实时信息或者不知道的事情时才会使用这个工具'''
    try:
        serp = SerpAPIWrapper(
            serpapi_api_key=config.SERPAPI_API_KEY,
            params={"no_cache": "true"}
        )
        result = serp.run(query)
        print(f"实时搜索结果（{query}）：{result[:100]}...")
        return result
    except Exception as e:
        print(f"搜索工具异常：{str(e)}")
        return f"搜索失败：{str(e)}，请尝试其他问题"


@tool
def get_infor_from_local_db(query: str):
    '''只有回答与2025年运势或者2025年相关问题才使用这个工具，从本地知识库中获取信息'''
    try:
        # 连接本地向量库
        client = Qdrant(
            QdrantClient(path=config.QDRANT_PATH),
            "local_documents",
            OpenAIEmbeddings(
                openai_api_key=config.OPENAI_API_KEY,
                openai_api_base=config.OPENAI_API_BASE
            )
        )
        
        # 检索相关文档
        retriever = client.as_retriever(search_type="mmr")
        result = retriever.get_relevant_documents(query)
        
        # 格式化结果
        if result:
            return "\n\n".join([f"知识库信息：{doc.page_content[:300]}..." for doc in result[:3]])
        else:
            return "本地知识库中未找到相关信息"
    except Exception as e:
        print(f"本地知识库查询异常：{str(e)}")
        return f"知识库查询失败：{str(e)}"
    