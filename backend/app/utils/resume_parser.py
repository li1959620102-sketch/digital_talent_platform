"""
简历解析工具
支持PDF、Word、图片等格式
"""
import os
import re
import tempfile
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


# ==================== 规则技能词典 ====================
# 用途：LLM 不可用（未配密钥 / 模型未就绪）时的降级路径也要能抽出技能。
# 否则 skills_certificates 为空，岗位匹配的硬条件过滤会把候选人整体筛掉，
# 表现为"简历解析成功但一个人也匹配不上"。
_SKILL_ASCII = (
    "Python", "Java", "JavaScript", "TypeScript", "Golang", "Go", "C++", "C#",
    "PHP", "Ruby", "Rust", "Scala", "Kotlin", "Shell", "SQL",
    "FastAPI", "Django", "Flask", "Spring Boot", "Spring Cloud", "Spring",
    "MyBatis", "Node.js", "Express", "gRPC", "RESTful", "Celery",
    "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch", "ClickHouse",
    "Hive", "Oracle", "SQL Server", "SQLite", "Milvus", "MinIO", "HBase",
    "Kafka", "RabbitMQ", "RocketMQ", "Spark", "Flink", "Hadoop", "Airflow",
    "Docker", "Kubernetes", "K8s", "Jenkins", "GitLab CI", "Nginx", "Linux",
    "Prometheus", "Grafana", "Ansible", "Terraform", "CI/CD", "DevOps",
    "PyTorch", "TensorFlow", "Keras", "scikit-learn", "Pandas", "NumPy",
    "LLM", "RAG", "LangChain", "Transformer", "BERT", "OCR",
    "React", "Vue", "Angular", "Webpack", "Vite", "HTML", "CSS", "Sass",
    "Ant Design", "Element UI",
)
_SKILL_CN = (
    "机器学习", "深度学习", "自然语言处理", "计算机视觉", "数据挖掘", "推荐系统",
    "向量数据库", "知识图谱", "大模型", "数据分析", "数据可视化", "项目管理",
    "需求分析", "产品设计", "敏捷开发", "团队管理", "市场营销", "财务分析",
    "人力资源管理", "招聘管理", "绩效考核", "薪酬管理", "小程序开发",
)

# 长词优先，避免 "Java" 抢先命中 "JavaScript"、"Spring" 抢先命中 "Spring Boot"
_ASCII_SKILL_RE = re.compile(
    r"(?<![A-Za-z0-9+#.])("
    + "|".join(re.escape(s) for s in sorted(_SKILL_ASCII, key=len, reverse=True))
    + r")(?![A-Za-z0-9+#])",
    re.IGNORECASE,
)
_SKILL_CANON = {s.lower(): s for s in _SKILL_ASCII}


def extract_skills_by_rule(text: str, limit: int = 20) -> List[str]:
    """按技能词典从文本中抽取技能（大小写不敏感，按首次出现位置排序）"""
    if not text:
        return []
    hits: Dict[int, str] = {}
    for m in _ASCII_SKILL_RE.finditer(text):
        canon = _SKILL_CANON.get(m.group(1).lower(), m.group(1))
        hits.setdefault(m.start(), canon)
    for kw in _SKILL_CN:
        idx = text.find(kw)
        if idx >= 0:
            hits.setdefault(idx, kw)
    return [hits[i] for i in sorted(hits)][:limit]


class ResumeParser:
    """简历解析器"""
    
    def __init__(self):
        self.supported_formats = ['.pdf', '.doc', '.docx', '.txt', '.jpg', '.jpeg', '.png']
    
    async def parse(
        self,
        file_path: str,
        file_name: str
    ) -> Dict[str, Any]:
        """
        解析简历文件
        
        Args:
            file_path: 文件路径
            file_name: 文件名
            
        Returns:
            解析结果字典
        """
        try:
            # 获取文件扩展名
            ext = Path(file_name).suffix.lower()
            
            if ext not in self.supported_formats:
                raise ValueError(f"不支持的文件格式: {ext}")
            
            # 根据文件类型选择解析方法
            if ext == '.pdf':
                text = await self._parse_pdf(file_path)
            elif ext in ['.doc', '.docx']:
                text = await self._parse_word(file_path)
            elif ext in ['.jpg', '.jpeg', '.png']:
                text = await self._parse_image(file_path)
            elif ext == '.txt':
                text = await self._parse_text(file_path)
            else:
                raise ValueError(f"未知的文件格式: {ext}")
            
            # 结构化抽取（规则基线；LLM 语义抽取见 resume_parser_agent）
            talent_data = await self._extract_info(text)

            # 置信度按核心字段命中率计算，而不是写死 0.85
            core_fields = ("name", "phone", "email", "education", "experience_years")
            hit = sum(1 for f in core_fields if talent_data.get(f))
            confidence = round(0.5 + 0.5 * hit / len(core_fields), 4)

            return {
                "success": True,
                "text": text,
                "talent_data": talent_data,
                "confidence": confidence
            }
            
        except Exception as e:
            logger.error(f"简历解析失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "talent_data": None,
                "confidence": 0
            }
    
    async def _parse_pdf(self, file_path: str) -> str:
        """解析PDF文件"""
        try:
            import pymupdf as fitz  # PyMuPDF (新API，解决旧fitz在部分环境下的路径问题)
            
            text = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            
            return text.strip()
            
        except ImportError:
            logger.warning("PyMuPDF未安装，尝试使用pdfplumber")
            import pdfplumber
            
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            
            return text.strip()
    
    async def _parse_word(self, file_path: str) -> str:
        """解析Word文件"""
        try:
            from docx import Document
            
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            
            return text.strip()
            
        except ImportError:
            logger.error("python-docx未安装")
            raise ImportError("需要安装python-docx库: pip install python-docx")
    
    async def _parse_image(self, file_path: str) -> str:
        """解析图片文件（OCR）"""
        try:
            import pytesseract
            from PIL import Image
            
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            
            return text.strip()
            
        except ImportError:
            logger.error("pytesseract或PIL未安装")
            raise ImportError("需要安装pytesseract和Pillow库")
    
    async def _parse_text(self, file_path: str) -> str:
        """解析文本文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    
    async def _extract_info(self, text: str) -> Dict[str, Any]:
        """
        规则基线抽取：从简历文本中抽取结构化字段。

        这是一个**毫秒级、零依赖、永不失败**的快速基线——文件上传后立刻就能得到一份
        可用的结构化结果，保证"没有模型也能建档"。

        精度更高的 LLM 语义抽取位于 app/agents/resume_parser_agent.py 的 extract_info
        节点（LangGraph 工作流内，优先 SiliconFlow，未配密钥时自动回退本地 Ollama），
        其输出会覆盖/补全本方法的结果。两级分工，互不阻塞。

        Args:
            text: 简历文本

        Returns:
            结构化人才数据（无法抽取的字段为 None）
        """
        import re

        talent_data = {
            "name": None,
            "gender": None,
            "phone": None,
            "email": None,
            "education": None,
            "major": None,
            "experience_years": None,
            "current_company": None,
            "current_position": None,
            "skills": [],
            "self_introduction": None
        }

        if not text:
            return talent_data

        # 手机号：优先带标签，其次裸 11 位（前后不允许再跟数字，避免截断长串）
        phone_match = (
            re.search(r'(?:手机|电话|联系方式|联系电话)[：:\s]*(\d{11})', text)
            or re.search(r'(?<!\d)(1[3-9]\d{9})(?!\d)', text)
        )
        if phone_match:
            talent_data["phone"] = phone_match.group(1)

        # 邮箱
        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+', text)
        if email_match:
            talent_data["email"] = email_match.group(0)

        # 姓名：优先"姓名：XXX"标签；否则取首行纯中文短串
        name_match = re.search(r'(?:姓名|姓\s*名)[：:\s]*([\u4e00-\u9fa5·]{2,4})', text)
        if name_match:
            talent_data["name"] = name_match.group(1)
        else:
            first_line = text.split('\n')[0].strip()
            if 2 <= len(first_line) <= 4 and re.fullmatch(r'[\u4e00-\u9fa5·]+', first_line):
                talent_data["name"] = first_line

        # 性别
        gender_match = re.search(r'性别[：:\s]*(男|女)', text)
        if gender_match:
            talent_data["gender"] = gender_match.group(1)

        # 学历：取最高学历（按 博士 > 硕士 > 本科 > 大专 > 高中 顺序命中）
        for edu in ("博士", "硕士", "本科", "大专", "高中"):
            if edu in text:
                talent_data["education"] = edu
                break

        # 专业
        major_match = re.search(r'专业[：:\s]*([\u4e00-\u9fa5A-Za-z]{2,20})', text)
        if major_match:
            talent_data["major"] = major_match.group(1).strip()

        # 工作年限："X年工作经验"/"X年以上经验" 或 "工作年限：X 年"
        exp_match = (
            re.search(r'(\d{1,2})\s*年(?:以上)?(?:工作)?(?:经验|经历)', text)
            or re.search(r'(?:工作年限|工作经历)[：:\s]*(\d{1,2})\s*年', text)
        )
        if exp_match:
            talent_data["experience_years"] = int(exp_match.group(1))

        # 当前公司
        company_match = re.search(
            r'(?:现就职于|任职于|所在公司|公司名称|工作单位)[：:\s]*([\u4e00-\u9fa5A-Za-z0-9（）()]{2,30})',
            text
        )
        if company_match:
            talent_data["current_company"] = company_match.group(1).strip()

        # 当前职位
        position_match = re.search(r'(?:职位|岗位|职务)[：:\s]*([\u4e00-\u9fa5A-Za-z0-9]{2,20})', text)
        if position_match:
            talent_data["current_position"] = position_match.group(1).strip()

        # 自我评价：标签后同行的内容
        intro_match = re.search(r'(?:自我评价|个人简介|自我介绍)[：:\s]*([^\n]{0,200})', text)
        if intro_match and intro_match.group(1).strip():
            talent_data["self_introduction"] = intro_match.group(1).strip()

        # 技能：词典命中（LLM 降级路径的兜底，保证建档即有技能可用于匹配）
        talent_data["skills"] = extract_skills_by_rule(text)

        return talent_data


# 全局实例
resume_parser = ResumeParser()
