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


# ==================== 解析结果规范化 ====================
# 为什么要这一层：LLM 节点的输出**不能直接入库**。实测踩到的三个坑——
#   1) 手机号：规则层正则能从"138-0013-8001"正确抽出 13800138001，但 LLM 层
#      会原样返回带分隔符的字符串并覆盖规则层结果，入库成非法手机号；
#   2) 学历：LLM 会返回"本科/硕士"这种非枚举值，调用方 if 判空后直接丢弃，
#      导致明明有学历却存成 NULL；
#   3) 工作年限：简历里大量使用中文数字（"五年后端研发经验"），LLM 识别不出就
#      漏填或给出错值。
# 这里的职责就是把不可控的 LLM 输出收敛成可直接入库的规范值。


_CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

# 学历等级：用于从一个包含多个学历的表述里取最高的那一个
_EDU_RANK = {
    "高中": 1, "中专": 1, "职高": 1,
    "大专": 2, "专科": 2,
    "本科": 3, "学士": 3,
    "硕士": 4, "研究生": 4,
    "博士": 5,
}
# 非枚举别名归一到 EducationLevel 的合法取值
_EDU_CANON = {"专科": "大专", "学士": "本科", "中专": "高中",
              "职高": "高中", "研究生": "硕士"}


def _cn_to_int(s: str) -> Optional[int]:
    """中文数字转整数，覆盖一到九十九（简历年限场景足够）。"""
    if not s:
        return None
    if s == "十":
        return 10
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    total = 0
    for ch in s:
        if ch not in _CN_DIGITS:
            return None
        total = total * 10 + _CN_DIGITS[ch]
    return total


def normalize_phone(raw: Any) -> Optional[str]:
    """手机号规范化：138-0013-8001 / +86 13800138001 / 138 0013 8001 → 13800138001。

    剥不干净或位数不对时返回 None，交由调用方决定是否降级建档。
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    if len(digits) == 11 and digits[0] == "1" and digits[1] in "3456789":
        return digits
    return None


def extract_phone_from_text(text: str) -> Optional[str]:
    """从任意简历文本里捞出手机号并规范化（容忍分隔符与 86 区号）。

    为什么需要：调用链里的兜底正则只认「裸 11 位」，而真实简历里大量写成
    "138-0013-8001""138 0013 8001"。实测 LLM 输出不稳定（有几次完全不给 phone），
    一旦兜底正则也抓不到，简历就完全无法建档——这里放宽匹配把这条退路堵上。
    """
    if not text:
        return None
    for m in re.finditer(r"1[3-9]\d(?:[\s\-]?\d){8}", text):
        got = normalize_phone(m.group(0))
        if got:
            return got
    return None


def normalize_education(raw: Any) -> Optional[str]:
    """学历规范化：从"本科/硕士"、"硕士及以上"、"本科在读"、"大专"中取最高学历。

    取不到任何已知学历关键词时返回 None（交由调用方降级）。
    """
    if not raw:
        return None
    text = str(raw)
    best, best_rank = None, 0
    for key, rank in _EDU_RANK.items():
        if key in text and rank > best_rank:
            best, best_rank = key, rank
    if best is None:
        return None
    return _EDU_CANON.get(best, best)


def normalize_experience_years(raw: Any, fallback_text: str = "") -> Optional[int]:
    """工作年限规范化：5 / "五年" / "5年工作经验" → 5。

    **取值优先级：原文规则提取 > LLM 推断值。**
    实测教训：简历里写的是"五年后端研发经验"，LLM 却返回 7。若直接采信 LLM 的
    数字，错误值会一路写进库且无法事后分辨来源。规则层是直接从原文正则匹配出来的，
    更贴近候选人自己声明的事实；只有原文里根本没提年限（如应届生、简历极简）时，
    才退回使用 LLM 的推断值。
    """
    # 1) 先从原文规则提取（更可信）
    if fallback_text:
        # 「年」与「经验/经历」之间允许少量修饰词（实测简历里常见
        # "五年后端研发经验""三年Java开发经历"这类写法），但不允许跨句号，
        # 避免把不相干的句子粘进来。
        # 前置 (?<!\d) 很关键：没有它，"2019年工作经验" 会被从 "9" 处起匹配成 9 年。
        m = re.search(r"(?<!\d)(\d{1,2})\s*年[^，。；、\n]{0,12}?(?:经验|经历)",
                      fallback_text)
        if m:
            return int(m.group(1))
        m = re.search(r"(?<![\d一二两三四五六七八九十])([一二两三四五六七八九十]{1,3})"
                      r"\s*年[^，。；、\n]{0,12}?(?:经验|经历)", fallback_text)
        if m:
            return _cn_to_int(m.group(1))

    # 2) 原文未声明 → 才用 LLM 的推断值
    if raw is not None:
        if isinstance(raw, bool):
            pass
        elif isinstance(raw, (int, float)):
            return max(0, int(raw))
        else:
            text = str(raw)
            m = re.search(r"\d+", text)
            if m:
                return int(m.group())
            m = re.search(r"([一二两三四五六七八九十]{1,3})\s*年", text)
            if m:
                return _cn_to_int(m.group(1))
    return None


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
