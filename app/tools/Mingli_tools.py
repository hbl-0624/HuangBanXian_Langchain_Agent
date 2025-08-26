from langchain.agents import tool
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_openai import ChatOpenAI
import requests
import json
import os
from ..config import config


@tool
def bazi_cesuan(query: str):
    "只有做八字排盘的时候才会使用到这个工具，需要输入用户姓名和出生年月日时，如果缺少则不可用"
    url = "https://api.yuanfenju.com/index.php/v1/Bazi/paipan"
    prompt = ChatPromptTemplate.from_template(
        """根据用户输入提取参数并按JSON格式返回：
        -"api_key":"{api_key}"
        -"name":"姓名"
        -"sex":"性别，0男1女，未提供时根据姓名判断"
        -"type":"0农历，1公历，默认1"
        -"year"："出生年份"
        -"month":"出生月份"
        -"day":"出生日期"
        -"hours":"出生小时，默认0"
        -"minute":"出生分钟，默认0"
        缺少参数则提醒用户补充，只返回数据结构。
        {format_instructions}
        用户输入：{query}
        """)
    parser = JsonOutputParser()
    prompt = prompt.partial(
        format_instructions=parser.get_format_instructions(),
        api_key=config.YUAN_MENG_JU_API_KEY
    )
    
    # 初始化模型
    llm = ChatOpenAI(
        model=config.OPENAI_MODEL,
        temperature=0.3,
        openai_api_key=config.OPENAI_API_KEY,
        openai_api_base=config.OPENAI_API_BASE
    )
    
    chain = prompt | llm | parser
    data = chain.invoke({"query": query})
    
    try:
        result = requests.post(url, data=data, proxies=config.PROXIES)
        
        if result.status_code == 200:
            print("============八字排盘返回数据===========")
            print(result.json())
            try:
                json_data = result.json()
                if json_data.get("errcode") == 0 and "data" in json_data:
                    returnstring = f"八字为：{json_data['data']['bazi_info']['bazi']}\n"
                    #returnstring += f"五行分布：{json_data['data']['bazi_info']['wuxing']}\n"
                    #returnstring += f"命局分析：{json_data['data']['analysis'][:200]}..."
                    return returnstring
                else:
                    return f"八字排盘失败：{json_data.get('msg', '未知错误')}"
            except Exception as e:
                print("解析返回数据时出错：", e)
                return "八字排盘失败，数据解析错误，请补充信息后重试"
        else:
            print(f"请求失败，状态码：{result.status_code}，响应：{result.text}")
            return f"八字排盘失败，服务器返回状态码：{result.status_code}"
    except Exception as e:
        print(f"八字排盘请求异常：{str(e)}")
        return "八字排盘失败，网络异常，请稍后重试"


@tool
def mei_ri_zhan_bu():
    """只有用户想要每日占卜抽签的时候才会使用到这个工具，其他时候不可用"""
    try:
        url = "https://api.yuanfenju.com/index.php/v1/Zhanbu/meiri"
        result = requests.post(
            url, 
            data={"api_key": config.YUAN_MENG_JU_API_KEY},
            proxies=config.PROXIES
        )
        
        if result.status_code == 200:
            print("============每日占卜返回数据===========")
            print(result.json())
            try:
                json_data = result.json()
                if json_data.get("errcode") == 0 and "data" in json_data:
                    data = json_data["data"]
                    returnstring = data
                    return returnstring
                else:
                    return f"每日占卜失败：{json_data.get('msg', '未知错误')}"
            except Exception as e:
                print("解析返回数据时出错：", e)
                return "每日占卜失败，数据解析错误，请稍后重试"
        else:
            print(f"请求失败，状态码：{result.status_code}")
            return f"每日占卜失败，服务器返回状态码：{result.status_code}"
    except Exception as e:
        print(f"每日占卜请求异常：{str(e)}")
        return "每日占卜失败，网络异常，请稍后重试"


@tool
def jie_meng(query: str):
    """只有用户想要解梦的时候才会使用，需要输入梦境内容，缺少则不可用"""
    try:
        url = "https://api.yuanfenju.com/index.php/v1/Gongju/zhougong"
        
        # 提取梦境关键词
        llm = ChatOpenAI(
            model=config.OPENAI_MODEL,
            temperature=0,
            openai_api_key=config.OPENAI_API_KEY,
            openai_api_base=config.OPENAI_API_BASE
        )
        
        prompt = PromptTemplate.from_template(
            """提取梦境关键词，只返回最多3个关键词（英文逗号分隔）：
            例如："梦见,可爱的,婴儿"
            用户输入：{query}
            """
        )
        parser = StrOutputParser()
        chain = prompt | llm | parser
        keywords = chain.invoke({"query": query})
        print("梦境关键词：", keywords)
        
        # 调用解梦API
        result = requests.post(
            url, 
            data={
                "api_key": config.YUAN_MENG_JU_API_KEY,
                "title_zhougong": keywords
            },
            proxies=config.PROXIES
        )
        
        if result.status_code == 200:
            print("============解梦返回数据===========")
            print(result.json())
            try:
                json_data = result.json()
                if json_data.get("errcode") == 0 and "data" in json_data:
                    return f"梦境解析结果：{json_data['data']}"
                else:
                    return f"解梦失败：{json_data.get('msg', '未知错误')}"
            except Exception as e:
                print("解析返回数据时出错：", e)
                return "解梦失败，数据解析错误，请重新描述梦境"
        else:
            print(f"请求失败，状态码：{result.status_code}")
            return f"解梦失败，服务器返回状态码：{result.status_code}"
    except Exception as e:
        print(f"解梦请求异常：{str(e)}")
        return "解梦失败，网络异常，请稍后重试"
    