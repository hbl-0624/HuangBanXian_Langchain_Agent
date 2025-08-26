import pytest
import os
from pathlib import Path
import sys

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))
from app.tools.Mingli_tools import bazi_cesuan, mei_ri_zhan_bu, jie_meng
from app.tools.Fuzhu_tools import search, get_infor_from_local_db
from app.config import config

class TestTools:
    """测试工具函数功能"""
    
    def test_bazi_cesuan_missing_info(self):
        """测试缺少信息的八字测算"""
        result = bazi_cesuan("帮我算八字")
        assert "缺少参数" in result or "请补充" in result
    
    def test_mei_ri_zhan_bu(self):
        """测试每日占卜工具"""
        if not config.YUAN_MENG_JU_API_KEY:
            pytest.skip("缺少API密钥，跳过测试")
            
        result = mei_ri_zhan_bu()
        assert len(result) > 0
        assert ("签文" in result) or ("解签" in result)
    
    def test_jie_meng_basic(self):
        """测试解梦工具基本功能"""
        if not config.YUAN_MENG_JU_API_KEY:
            pytest.skip("缺少API密钥，跳过测试")
            
        result = jie_meng("我梦见自己在飞")
        assert len(result) > 0
        assert "解析" in result
    
    def test_search_tool(self):
        """测试搜索工具"""
        if not config.SERPAPI_API_KEY:
            pytest.skip("缺少API密钥，跳过测试")
            
        result = search("2025年农历新年是哪一天")
        assert len(result) > 0
        assert "2025" in result
    
    def test_local_db_tool_without_data(self):
        """测试本地知识库（无数据时）"""
        result = get_infor_from_local_db("2025年运势")
        assert "未找到相关信息" in result or "知识库" in result

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(config.QDRANT_PATH, "local_documents")),
        reason="本地知识库无数据，跳过测试"
    )
    def test_local_db_tool_with_data(self):
        """测试本地知识库（有数据时）"""
        result = get_infor_from_local_db("2025年运势")
        assert "知识库信息" in result
        assert len(result) > 50
