import streamlit as st
import requests
import os
import json
import base64
import time
from datetime import datetime
from streamlit.components.v1 import html
import sys
from pathlib import Path

# 添加项目根目录到Python路径（确保能导入config）
sys.path.append(str(Path(__file__).parent.parent))
from app.config import config


# 1. 页面基础配置
st.set_page_config(
    page_title="黄半仙风水命理助手",
    page_icon="🔮",
    layout="wide"
)


# 2. 初始化会话状态（保存聊天历史、API地址、用户uid等）
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []  # 聊天历史
    if "api_url" not in st.session_state:
        st.session_state.api_url = "http://localhost:8000"  # 后端API地址
    if "current_audio_uid" not in st.session_state:
        st.session_state.current_audio_uid = None  # 当前语音UID
    if "user_uid" not in st.session_state:
        st.session_state.user_uid = None  # 后端回传的用户唯一标识（复用会话）

init_session_state()


# 3. 语音自动播放函数（修正路径拼接，支持轮询检测文件生成）
def auto_play_audio(audio_uid):
    """自动播放语音，轮询检测文件是否生成，超时显示手动播放按钮"""
    # 拼接语音文件路径（项目根目录/voices/xxx.mp3）
    project_root = Path(__file__).parent.parent  # 项目根目录（如：G:\code\HuangBanxian_Langchain_Agent）
    audio_path = project_root / "voices" / f"{audio_uid}.mp3"

    # 轮询检测语音文件（最多等待 config.TTS_WAIT_TIMEOUT 秒）
    wait_time = 0
    while not audio_path.exists() and wait_time < config.TTS_WAIT_TIMEOUT:
        time.sleep(0.5)
        wait_time += 0.5
        # 每2秒提示一次进度
        if int(wait_time) % 2 == 0:
            st.toast(f"正在准备语音回复（已等待 {int(wait_time)} 秒）...")

    # 处理超时/文件存在情况
    if not audio_path.exists():
        st.warning("语音生成超时，可点击下方按钮手动播放")
        st.audio(str(audio_path), format="audio/mp3")
        return

    # 读取文件并转为Base64（支持前端直接播放）
    try:
        audio_bytes = audio_path.read_bytes()
        audio_b64 = base64.b64encode(audio_bytes).decode()
    except Exception as e:
        st.error(f"读取语音文件失败：{str(e)}")
        st.audio(str(audio_path), format="audio/mp3")
        return

    # 嵌入HTML实现自动播放（兼容浏览器自动播放策略）
    html_content = f"""
    <script>
        // 创建音频元素
        const audio = new Audio("data:audio/mp3;base64,{audio_b64}");
        
        // 尝试自动播放（需用户交互，浏览器限制）
        function playAudio() {{
            audio.play().then(() => {{
                console.log("语音自动播放成功（UID：{audio_uid}）");
            }}).catch(error => {{
                console.log("自动播放需用户交互，显示手动播放按钮：", error);
                // 创建手动播放按钮
                const audioContainer = document.createElement('div');
                audioContainer.style.marginTop = '10px';
                const audioElement = document.createElement('audio');
                audioElement.controls = true;
                audioElement.src = "data:audio/mp3;base64,{audio_b64}";
                audioElement.title = "黄半仙语音回复";
                audioContainer.appendChild(audioElement);
                document.body.appendChild(audioContainer);
            }});
        }}
        
        // 页面加载完成后触发播放（或等待用户交互）
        window.addEventListener('load', playAudio);
        // 兼容Streamlit的交互事件（点击页面后触发）
        document.addEventListener('click', playAudio, {{once: true}});
    </script>
    """
    html(html_content, height=80)  # 渲染HTML音频播放器


# 4. 页面主体内容（标题、侧边栏、聊天区域）
def render_page():
    # 页面标题与分割线
    st.title("🔮 黄半仙风水命理助手")
    st.markdown("---")

    # 侧边栏（功能设置、知识库管理、帮助信息）
    with st.sidebar:
        st.header("⚙️ 功能设置")
        
        # 后端API地址配置（支持用户修改）
        api_url = st.text_input("后端API地址", value=st.session_state.api_url)
        if api_url != st.session_state.api_url:
            st.session_state.api_url = api_url.strip()
            st.success(f"API地址已更新为：{st.session_state.api_url}")
        
        # 知识库管理（添加风水知识URL）
        st.subheader("📚 知识库管理")
        url_input = st.text_input("添加风水知识URL", placeholder="https://example.com/fengshui.html")
        if st.button("添加到知识库", key="add_url_btn"):
            if url_input.strip():
                add_url_to_knowledge_base(url_input.strip())
            else:
                st.warning("请输入有效的URL（如：https://xxx.com/fengshui.html）")
        
        # 功能说明
        st.subheader("❓ 支持功能")
        st.info("""
        - **八字排盘**：需提供姓名、出生年月日时（精确到小时）
        - **每日占卜抽签**：随机生成当日运势签文
        - **周公解梦**：需详细描述梦境内容（如：梦到天上飞）
        - **2025年运势**：结合五行命理分析全年运势
        - **风水咨询**：家居/办公风水布局建议
        """)
        
        # 免责声明
        st.subheader("⚠️ 免责声明")
        st.caption("""
        本工具仅供娱乐参考，所有命理分析结果不构成专业指导。
        人生运势需靠自身努力，请勿过度迷信或依赖！
        """)

    # 聊天历史显示区域
    st.subheader("💬 聊天记录")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # 显示语音（若有）
            if "audio_path" in message:
                audio_file = Path(__file__).parent.parent / message["audio_path"]
                if audio_file.exists():
                    st.audio(str(audio_file), format="audio/mp3")

    # 用户输入区域（聊天输入框）
    if prompt := st.chat_input("请输入您想咨询的问题（例如：帮我排一下八字）"):
        handle_user_input(prompt.strip())


# 5. 处理用户输入（发送请求到后端，更新聊天历史）- 核心修改：禁用代理+添加跨域头
def handle_user_input(prompt):
    """处理用户输入，调用后端API，更新会话状态和UI"""
    # 1. 显示用户消息到UI
    with st.chat_message("user"):
        st.markdown(prompt)
    # 2. 保存用户消息到会话历史
    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    # 3. 调用后端API（带加载动画）- 关键修改：禁用代理+添加跨域兼容头
    with st.spinner("🔮 黄半仙正在为您测算..."):
        try:
            # 构造请求参数（传递用户uid，保持会话连续）
            request_data = {
                "query": prompt,
                "uid": st.session_state.user_uid  # 后端回传的uid，首次为None
            }

            # 关键修改1：强制禁用代理（避免系统代理拦截请求）
            proxies = {
                "http": None,
                "https": None
            }

            # 关键修改2：添加跨域兼容请求头（与后端跨域配置匹配）
            headers = {
                "Content-Type": "application/json",
                "Origin": "http://localhost:8501",  # 明确前端来源，匹配后端跨域allow_origins
                "Referer": "http://localhost:8501/"  # 补充Referer，增强跨域兼容性
            }

            # 发送POST请求（集成修改：禁用代理+添加请求头）
            response = requests.post(
                url=f"{st.session_state.api_url}/chat",
                json=request_data,
                headers=headers,
                proxies=proxies,
                timeout=30,  # 超时时间延长到30秒，避免后端处理慢导致超时
                verify=False  # 临时关闭SSL验证（若后端无HTTPS，避免不必要的SSL错误，仅开发环境用）
            )

            # 检查响应状态码（非200时抛出异常，进入except处理）
            response.raise_for_status()

            # 关键修改3：强制解析响应编码（避免中文乱码导致JSON解析失败）
            response.encoding = "utf-8"
            response_data = response.json()

            # 4. 处理后端成功响应（逻辑不变）
            if response_data.get("status") == "success":
                answer = response_data.get("message", "暂无回应")
                audio_uid = response_data.get("audio_uid", "")
                audio_path = response_data.get("audio_path", "")
                # 保存后端回传的uid（下次请求复用）
                if "uid" in response_data:
                    st.session_state.user_uid = response_data["uid"]

                # 显示AI回复到UI
                with st.chat_message("assistant"):
                    st.markdown(answer)
                    # 自动播放语音（若有）
                    if audio_uid:
                        st.session_state.current_audio_uid = audio_uid
                        auto_play_audio(audio_uid)

                # 保存AI回复到会话历史
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "audio_path": audio_path,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

            # 5. 处理后端错误响应（逻辑不变）
            else:
                error_msg = response_data.get("message", "请求失败，暂无原因")
                with st.chat_message("assistant"):
                    st.error(f"❌ {error_msg}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ 错误：{error_msg}",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

        # 6. 处理网络/解析等异常（细化错误提示，方便定位）
        except requests.exceptions.ProxyError:
            error_msg = "连接后端失败：代理服务异常（已强制禁用代理，若需代理请检查配置）"
        except requests.exceptions.ConnectTimeout:
            error_msg = "连接后端失败：请求超时（后端可能处理较慢，或网络不稳定）"
        except requests.exceptions.ConnectionError:
            error_msg = "连接后端失败：无法连接到后端（请确认后端已启动，API地址正确）"
        except requests.exceptions.HTTPError as e:
            # 后端返回4xx/5xx错误时，获取详细响应内容
            try:
                err_response = response.json()
                error_msg = f"后端返回错误：{err_response.get('message', '未知错误')}（状态码：{response.status_code}）"
            except:
                error_msg = f"后端返回错误：{str(e)}（状态码：{response.status_code}）"
        except json.JSONDecodeError:
            error_msg = f"后端返回非JSON数据：{response.text[:100]}（可能接口路径错误或后端异常）"
        except Exception as e:
            error_msg = f"未知错误：{str(e)}"
        
        # 显示异常信息（逻辑不变）
        if "error_msg" in locals():
            with st.chat_message("assistant"):
                st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"❌ 错误：{error_msg}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })


# 7. 辅助函数：添加URL到知识库（同步禁用代理）
def add_url_to_knowledge_base(url):
    """调用后端/add_urls接口，添加URL内容到知识库"""
    try:
        # 同步修改：禁用代理+添加跨域头
        proxies = {"http": None, "https": None}
        headers = {
            "Content-Type": "application/json",
            "Origin": "http://localhost:8501",
            "Referer": "http://localhost:8501/"
        }

        response = requests.post(
            url=f"{st.session_state.api_url}/add_urls",
            json={"URL": url},
            headers=headers,
            proxies=proxies,
            timeout=20,
            verify=False
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        response_data = response.json()
        
        if response_data.get("status") == "success":
            st.success(f"✅ {response_data.get('message')}")
        else:
            st.error(f"❌ 添加失败：{response_data.get('message', '未知错误')}")
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 网络错误：{str(e)}（请检查后端是否启动，API地址是否正确）")
    except Exception as e:
        st.error(f"❌ 未知错误：{str(e)}")


# 8. 启动页面渲染
if __name__ == "__main__":
    render_page()