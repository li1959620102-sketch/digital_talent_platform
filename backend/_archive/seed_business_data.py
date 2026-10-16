"""
业务表种子数据初始化（幂等）

为 AI数字化人才平台 所有业务表插入 30-40 条真实模拟数据，用于前端交互测试。

覆盖表：
- talents (表为空时先建 40 条演示档案；已有档案则只更新学历/状态/性别分布，不改姓名手机号)
- job_positions (新增至 35-40 条)
- questions (35-40 条)
- test_papers (8-10 条)
- assessment_tasks (8-10 条)
- assessment_results (35-40 条)
- courses (35-40 条)
- training_plans (8-10 条)
- learning_records (35-40 条)
- examination_records (35-40 条)

运行：
    C:\\Users\\Windows\\miniconda3\\envs\\ai_py311\\python.exe \\
        d:\\PythonHayson\\digital_talent_platform\\backend\\seed_business_data.py

幂等设计：插入前先按唯一业务编码检查，已存在则跳过或更新。
"""
import os
import sys
import random
import logging
from datetime import datetime, timedelta, date

# 确保 backend 目录在 sys.path（本脚本位于 backend/_archive/，需上跳一级）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_mysql_session_factory
from app.models.talent import (
    Talent, Organization,
    GenderEnum, EducationLevel, TalentStatus,
)
from app.schemas.talent import (
    TalentCreate,
    GenderEnum as SchemaGender,
    EducationLevel as SchemaEducation,
    TalentStatus as SchemaTalentStatus,
)
from app.services.talent_service import TalentService
from app.models.position import (
    JobPosition, PositionStatus, PositionLevel,
)
from app.models.assessment import (
    Question, TestPaper, AssessmentTask, AssessmentResult,
    QuestionType, AssessmentStatus, CapabilityLevel,
)
from app.models.training import (
    Course, TrainingPlan, LearningRecord, ExaminationRecord,
    CourseType, CourseCategory, TrainingStatus, LearningStatus,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("seed_business_data")

# 固定随机种子保证可重复
random.seed(20260902)


# ============================================================================
# 基础数据池（真实公司/技能/姓名/岗位）
# ============================================================================

COMPANIES = [
    "阿里巴巴", "腾讯", "字节跳动", "华为", "美团", "京东", "百度", "小米",
    "网易", "拼多多", "滴滴出行", "快手", "B站", "携程", "蚂蚁集团", "微软中国",
    "亚马逊", "谷歌中国", "中兴通讯", "大疆创新", "联想", "搜狐", "新浪", "爱奇艺",
]

MAJORS = [
    "计算机科学与技术", "软件工程", "电子信息工程", "数据科学", "人工智能",
    "信息安全", "通信工程", "自动化", "数学与应用数学", "统计学",
    "工商管理", "市场营销", "人力资源管理", "财务管理", "工业工程",
]

POSITIONS = [
    # (岗位名称, 类别, 级别, 类型, headcount, filled, 状态, 薪资下, 薪资上, 学历要求, 经验要求)
    ("Java高级工程师", "技术", "senior", "全职", 3, 1, PositionStatus.OPEN, 20000, 35000, "本科", 5),
    ("Python开发工程师", "技术", "intermediate", "全职", 2, 0, PositionStatus.OPEN, 15000, 25000, "本科", 3),
    ("Go后端工程师", "技术", "senior", "全职", 2, 0, PositionStatus.OPEN, 20000, 32000, "本科", 4),
    ("前端工程师(React)", "技术", "intermediate", "全职", 3, 1, PositionStatus.OPEN, 15000, 28000, "本科", 3),
    ("前端工程师(Vue)", "技术", "junior", "全职", 2, 0, PositionStatus.OPEN, 12000, 20000, "本科", 2),
    ("数据分析师", "技术", "intermediate", "全职", 2, 0, PositionStatus.OPEN, 15000, 25000, "本科", 3),
    ("算法工程师", "技术", "expert", "全职", 1, 0, PositionStatus.OPEN, 30000, 50000, "硕士", 3),
    ("DevOps工程师", "技术", "senior", "全职", 2, 0, PositionStatus.OPEN, 20000, 35000, "本科", 4),
    ("测试工程师", "技术", "junior", "全职", 3, 2, PositionStatus.OPEN, 10000, 18000, "本科", 1),
    ("移动端开发工程师(iOS)", "技术", "senior", "全职", 1, 0, PositionStatus.SUSPENDED, 22000, 35000, "本科", 5),
    ("移动端开发工程师(Android)", "技术", "intermediate", "全职", 2, 1, PositionStatus.OPEN, 18000, 30000, "本科", 3),
    ("数据库管理员", "技术", "senior", "全职", 1, 1, PositionStatus.CLOSED, 20000, 32000, "本科", 5),
    ("安全工程师", "技术", "senior", "全职", 1, 0, PositionStatus.OPEN, 22000, 38000, "本科", 4),
    ("全栈工程师", "技术", "intermediate", "全职", 2, 0, PositionStatus.OPEN, 18000, 30000, "本科", 3),
    ("技术总监", "技术", "director", "全职", 1, 0, PositionStatus.OPEN, 50000, 80000, "硕士", 8),
    ("架构师", "技术", "expert", "全职", 1, 0, PositionStatus.OPEN, 45000, 70000, "本科", 8),
    ("产品经理", "管理", "intermediate", "全职", 2, 1, PositionStatus.OPEN, 18000, 30000, "本科", 3),
    ("高级产品经理", "管理", "senior", "全职", 1, 0, PositionStatus.OPEN, 25000, 40000, "本科", 5),
    ("产品总监", "管理", "director", "全职", 1, 1, PositionStatus.CLOSED, 50000, 80000, "本科", 8),
    ("项目经理", "管理", "manager", "全职", 2, 1, PositionStatus.OPEN, 20000, 35000, "本科", 5),
    ("市场经理", "市场", "manager", "全职", 1, 0, PositionStatus.OPEN, 18000, 30000, "本科", 4),
    ("市场专员", "市场", "junior", "全职", 2, 0, PositionStatus.OPEN, 8000, 15000, "大专", 1),
    ("品牌总监", "市场", "director", "全职", 1, 0, PositionStatus.SUSPENDED, 40000, 65000, "本科", 8),
    ("运营经理", "运营", "manager", "全职", 1, 0, PositionStatus.OPEN, 18000, 30000, "本科", 4),
    ("运营专员", "运营", "junior", "全职", 3, 1, PositionStatus.OPEN, 8000, 15000, "大专", 1),
    ("内容运营", "运营", "intermediate", "全职", 2, 0, PositionStatus.OPEN, 12000, 22000, "本科", 2),
    ("用户运营", "运营", "intermediate", "全职", 2, 1, PositionStatus.OPEN, 12000, 22000, "本科", 2),
    ("HR经理", "人事", "manager", "全职", 1, 0, PositionStatus.OPEN, 18000, 30000, "本科", 5),
    ("招聘专员", "人事", "junior", "全职", 2, 0, PositionStatus.OPEN, 8000, 15000, "本科", 1),
    ("薪酬福利专员", "人事", "intermediate", "全职", 1, 0, PositionStatus.SUSPENDED, 12000, 20000, "本科", 3),
    ("财务经理", "财务", "manager", "全职", 1, 0, PositionStatus.OPEN, 20000, 35000, "本科", 5),
    ("会计", "财务", "junior", "全职", 2, 1, PositionStatus.OPEN, 8000, 15000, "大专", 2),
    ("财务总监", "财务", "director", "全职", 1, 1, PositionStatus.CLOSED, 40000, 65000, "本科", 8),
    ("实习生(技术)", "技术", "entry", "实习", 5, 2, PositionStatus.OPEN, 4000, 8000, "本科", 0),
    ("实习生(运营)", "运营", "entry", "实习", 3, 0, PositionStatus.OPEN, 3500, 7000, "大专", 0),
]

SKILL_POOL = [
    "Python", "Java", "Go", "JavaScript", "TypeScript", "React", "Vue",
    "Node.js", "SQL", "MySQL", "PostgreSQL", "Redis", "MongoDB",
    "Docker", "Kubernetes", "K8s", "Jenkins", "Git", "Linux",
    "Spring", "SpringBoot", "Django", "FastAPI", "Flask",
    "TensorFlow", "PyTorch", "Pandas", "NumPy", "Spark", "Hadoop",
    "Kafka", "RabbitMQ", "Elasticsearch", "GraphQL", "RESTful",
    "AWS", "阿里云", "腾讯云", "HTML5", "CSS3", "Webpack",
]

TAG_POOL = [
    "Java", "微服务", "互联网", "高并发", "大数据", "AI", "云计算",
    "中台", "电商", "金融", "SaaS", "ToB", "ToC", "DevOps",
    "全栈", "架构", "团队管理", "项目管理", "敏捷开发", "开源",
    "区块链", "物联网", "5G", "新能源", "出海", "数字化转型",
]

QUESTION_BANK = [
    # (题目类型, 分类, 题目内容, 选项, 正确答案, 解析, 分值, 难度, 能力维度)
    (QuestionType.SINGLE_CHOICE, "综合", "在团队合作中,当与同事意见不一致时,你通常会如何处理?",
     ["A. 坚持己见,据理力争", "B. 妥协退让,维持和谐", "C. 寻找共同点,协商解决", "D. 请上级领导裁决"],
     "C", "寻找共同点协商解决是最有利于团队合作的方式,体现了沟通协调能力。", 2.0, 2, "团队协作"),
    (QuestionType.SINGLE_CHOICE, "综合", "面对紧急任务和重要任务的冲突时,你会优先处理哪一个?",
     ["A. 紧急任务", "B. 重要任务", "C. 同时进行", "D. 请示上级"],
     "B", "重要任务往往对长期目标更有价值,应根据重要程度而非紧急程度排序。", 2.0, 3, "决策能力"),
    (QuestionType.SINGLE_CHOICE, "专业", "在Python中,以下哪种数据类型是不可变的?",
     ["A. list", "B. dict", "C. tuple", "D. set"],
     "C", "元组(tuple)是不可变数据类型,创建后无法修改其元素。", 2.0, 1, "编程基础"),
    (QuestionType.SINGLE_CHOICE, "专业", "在MySQL中,以下哪个存储引擎支持事务和外键?",
     ["A. MyISAM", "B. InnoDB", "C. Memory", "D. CSV"],
     "B", "InnoDB存储引擎支持事务、行级锁和外键约束。", 2.0, 2, "数据库"),
    (QuestionType.SINGLE_CHOICE, "专业", "RESTful API设计中,使用GET方法的主要目的是?",
     ["A. 创建资源", "B. 更新资源", "C. 获取资源", "D. 删除资源"],
     "C", "GET方法用于安全地获取资源表示,不应有副作用。", 2.0, 1, "API设计"),
    (QuestionType.SINGLE_CHOICE, "专业", "Docker容器与传统虚拟机相比,主要优势是?",
     ["A. 更强的隔离性", "B. 更轻量级,启动快", "C. 更高的安全性", "D. 更多的硬件支持"],
     "B", "Docker共享宿主内核,无需完整操作系统,因此更轻量启动更快。", 2.0, 2, "DevOps"),
    (QuestionType.SINGLE_CHOICE, "专业", "Kubernetes中,Pod是最小可部署单元,一个Pod可以包含?",
     ["A. 只能一个容器", "B. 一个或多个紧密耦合的容器", "C. 任意数量容器", "D. 只能无状态容器"],
     "B", "Pod可包含一个或多个紧密耦合、共享网络和存储的容器。", 2.0, 3, "云原生"),
    (QuestionType.SINGLE_CHOICE, "专业", "Java中,以下哪个关键字用于实现继承?",
     ["A. implements", "B. extends", "C. inherits", "D. super"],
     "B", "extends用于类的继承,implements用于实现接口。", 2.0, 1, "编程基础"),
    (QuestionType.SINGLE_CHOICE, "专业", "在React中,以下哪个Hook用于处理副作用?",
     ["A. useState", "B. useEffect", "C. useContext", "D. useMemo"],
     "B", "useEffect用于处理订阅、定时器、网络请求等副作用操作。", 2.0, 2, "前端开发"),
    (QuestionType.SINGLE_CHOICE, "专业", "数据结构与算法中,二分查找的时间复杂度是?",
     ["A. O(1)", "B. O(log n)", "C. O(n)", "D. O(n²)"],
     "B", "二分查找每次将搜索范围减半,时间复杂度为O(log n)。", 2.0, 2, "算法基础"),
    (QuestionType.MULTIPLE_CHOICE, "专业", "以下哪些是Java中的基本数据类型?",
     ["A. int", "B. String", "C. boolean", "D. double", "E. Integer"],
     "ACD", "Java基本类型包括byte/short/int/long/float/double/char/boolean;String和Integer是引用类型。", 3.0, 2, "编程基础"),
    (QuestionType.MULTIPLE_CHOICE, "专业", "以下哪些属于微服务架构的核心组件?",
     ["A. 服务注册发现", "B. API网关", "C. 配置中心", "D. 单体数据库", "E. 熔断器"],
     "ABCE", "微服务通常需要服务治理(注册/发现)、网关、配置中心、熔断器等;单体数据库不属于微服务组件。", 3.0, 3, "架构设计"),
    (QuestionType.MULTIPLE_CHOICE, "专业", "以下哪些是常见的消息队列产品?",
     ["A. Kafka", "B. RabbitMQ", "C. Redis", "D. RocketMQ", "E. Nginx"],
     "ABD", "Kafka/RabbitMQ/RocketMQ是消息队列;Redis是缓存;Nginx是Web服务器。", 3.0, 2, "中间件"),
    (QuestionType.MULTIPLE_CHOICE, "专业", "关于SQL优化,以下哪些做法是正确的?",
     ["A. 避免SELECT *", "B. 合理建立索引", "C. 使用子查询代替JOIN", "D. 避免在WHERE中对字段做函数运算", "E. 大事务拆小事务"],
     "ABDE", "SELECT *、未建索引、字段函数运算、大事务都影响性能;JOIN通常优于子查询。", 3.0, 3, "数据库"),
    (QuestionType.MULTIPLE_CHOICE, "团队", "团队高效协作的关键要素包括?",
     ["A. 明确的共同目标", "B. 清晰的角色分工", "C. 高效的沟通机制", "D. 个人英雄主义", "E. 定期复盘改进"],
     "ABCE", "团队协作需要共同目标、明确分工、有效沟通和持续复盘;个人英雄主义不利于协作。", 3.0, 2, "团队管理"),
    (QuestionType.TRUE_FALSE, "综合", "时间管理四象限法则是将任务按重要性和紧急性进行分类。",
     None, "正确", "四象限法则由史蒂芬·柯维提出,按重要紧急维度划分任务优先级。", 1.0, 1, "时间管理"),
    (QuestionType.TRUE_FALSE, "专业", "Python中GIL(全局解释器锁)使得多线程无法真正并行执行CPU密集型任务。",
     None, "正确", "GIL保证同一时刻只有一个线程执行Python字节码,多线程CPU密集型受限于GIL。", 1.0, 3, "Python"),
    (QuestionType.TRUE_FALSE, "专业", "HTTP协议是无状态协议,因此所有请求都需要重新建立TCP连接。",
     None, "错误", "HTTP本身无状态,但可以通过Keep-Alive复用TCP连接,无需每次重新建立。", 1.0, 2, "网络协议"),
    (QuestionType.TRUE_FALSE, "专业", "Git的分支模型中,主分支master/main应当保持随时可部署状态。",
     None, "正确", "主分支应保持稳定可部署,功能开发应在特性分支进行,通过PR合并。", 1.0, 2, "版本控制"),
    (QuestionType.TRUE_FALSE, "性格", "内向的人不适合担任管理岗位。",
     None, "错误", "内向者也可成为优秀管理者,关键在沟通方式、共情能力和决策能力,与内外向无必然联系。", 1.0, 1, "性格特质"),
    (QuestionType.TRUE_FALSE, "抗压", "在压力情境下,适度的紧张情绪有助于提升工作表现。",
     None, "正确", "耶克斯-多德森定律表明,适度压力能提升表现,但过高压力会下降,关键在管理。", 1.0, 2, "压力管理"),
    (QuestionType.FILL_BLANK, "专业", "在Linux系统中,查看进程占用情况的命令是____。",
     None, "ps / top", "ps查看静态进程,top查看动态进程占用。", 1.5, 1, "Linux运维"),
    (QuestionType.FILL_BLANK, "专业", "Java中实现多态的三个必要条件是继承、____和父类引用指向子类对象。",
     None, "重写(override)", "多态三要素:继承、方法重写、父类引用指向子类对象。", 1.5, 2, "Java"),
    (QuestionType.FILL_BLANK, "专业", "在SQL中,用于去重的关键字是____。",
     None, "DISTINCT", "SELECT DISTINCT field FROM table 用于去除重复记录。", 1.5, 1, "数据库"),
    (QuestionType.FILL_BLANK, "专业", "Git中将工作区修改添加到暂存区的命令是____。",
     None, "git add", "git add <file> 将修改加入暂存区,准备提交。", 1.5, 1, "版本控制"),
    (QuestionType.FILL_BLANK, "综合", "SWOT分析中的四个字母分别代表优势、____、机会和威胁。",
     None, "劣势(Weakness)", "SWOT:Strengths/Weaknesses/Opportunities/Threats。", 1.5, 2, "战略分析"),
    (QuestionType.SHORT_ANSWER, "性格", "请简要描述你的性格特点及其在工作中的优势。",
     None, "答案不唯一。可以从性格维度(内外向、细致/果断等)切入,结合具体工作场景说明优势。",
     "考察自我认知与性格匹配度。", 5.0, 3, "性格特质"),
    (QuestionType.SHORT_ANSWER, "抗压", "请描述一次你在高压环境下完成重要任务的经历,你是如何应对的?",
     None, "答案不唯一。应体现压力识别、情绪管理、任务拆解、求助协作等能力。",
     "考察抗压能力和问题解决能力。", 5.0, 3, "压力管理"),
    (QuestionType.SHORT_ANSWER, "团队", "如果在团队中你的方案被同事否定,你会如何处理?",
     None, "答案不唯一。应体现倾听、理性分析、寻求共识、必要时妥协或寻求上级协调。",
     "考察沟通协作和冲突管理能力。", 5.0, 3, "团队协作"),
    (QuestionType.SHORT_ANSWER, "岗位", "请描述你过往工作中最值得骄傲的一个项目,以及你在其中扮演的角色和贡献。",
     None, "答案不唯一。应包括项目背景、个人角色、具体贡献、量化成果和经验反思。",
     "考察项目经验和自我总结能力。", 5.0, 4, "项目经验"),
    (QuestionType.SHORT_ANSWER, "综合", "你认为未来3-5年内,你希望在自己的职业发展上达到什么样的目标?",
     None, "答案不唯一。应体现明确的职业规划、可量化的目标、自我提升路径。",
     "考察职业规划清晰度和自我驱动能力。", 5.0, 3, "职业规划"),
    (QuestionType.SHORT_ANSWER, "专业", "请简要说明RESTful API的设计原则及其核心约束。",
     None, "答案应包含:客户端-服务器分离、无状态、可缓存、统一接口、分层系统等约束;资源通过URL定位,用HTTP方法表达操作。",
     "考察REST架构理解深度。", 5.0, 4, "API设计"),
    (QuestionType.SHORT_ANSWER, "专业", "请描述微服务架构的优缺点及适用场景。",
     None, "答案应包含优点(独立部署/技术栈灵活/可扩展)、缺点(分布式复杂性/数据一致性/运维成本)、适用场景(大型复杂系统、需独立扩展的模块)。",
     "考察架构思维和实际取舍能力。", 5.0, 4, "架构设计"),
    (QuestionType.SINGLE_CHOICE, "综合", "在职业发展中,以下哪种做法最能体现持续学习的态度?",
     ["A. 频繁跳槽寻求更高薪资", "B. 定期参加培训并应用于工作", "C. 仅关注当前岗位任务", "D. 等待公司安排学习机会"],
     "B", "持续学习需要主动性和实践性,通过培训并将所学应用于工作最能体现这一态度。", 2.0, 2, "学习能力"),
    (QuestionType.SINGLE_CHOICE, "性格", "当面对一项全新的、没有经验的工作任务时,你的第一反应通常是?",
     ["A. 拒绝,担心做不好", "B. 焦虑但勉强接受", "C. 欣然接受,愿意挑战", "D. 推给同事"],
     "C", "积极迎接新挑战体现了成长心态和抗压能力,是岗位胜任力的重要维度。", 2.0, 2, "性格特质"),
    (QuestionType.SINGLE_CHOICE, "岗位", "应聘高级工程师岗位,以下哪项是最核心的考察维度?",
     ["A. 学历背景", "B. 工作年限", "C. 技术深度与项目落地能力", "D. 外表形象"],
     "C", "高级岗位最看重技术深度和复杂项目落地能力,学历年限是参考维度。", 2.0, 3, "岗位匹配"),
    (QuestionType.SINGLE_CHOICE, "抗压", "面对连续加班和deadline压力时,以下哪种应对方式最佳?",
     ["A. 抱怨并消极应付", "B. 直接辞职", "C. 合理排期并寻求资源支持", "D. 独自硬扛"],
     "C", "科学应对压力应合理排期、寻求团队/资源支持,而非消极或独扛。", 2.0, 2, "压力管理"),
    (QuestionType.TRUE_FALSE, "岗位", "产品经理的核心能力是熟练掌握原型设计工具。",
     None, "错误", "产品经理核心是需求洞察、商业判断和跨部门协调,原型工具只是表达手段。", 1.0, 2, "岗位认知"),
    (QuestionType.FILL_BLANK, "专业", "在Docker中,构建镜像使用的命令是____。",
     None, "docker build", "docker build -t <name>:<tag> . 用于根据Dockerfile构建镜像。", 1.5, 1, "DevOps"),
    (QuestionType.FILL_BLANK, "专业", "SQL中用于聚合分组的关键字是____。",
     None, "GROUP BY", "SELECT field, COUNT(*) FROM table GROUP BY field 用于按字段分组聚合。", 1.5, 1, "数据库"),
]

PAPER_DEFS = [
    # (名称, 类型, 描述, 时长, 难度分布, 能力维度, 题目数量)
    ("综合能力测评卷A", "综合测评", "考察候选人的综合职业素养、沟通协作、抗压能力等通用能力维度。",
     60, {"简单": 0.3, "中等": 0.5, "困难": 0.2}, ["决策能力", "团队协作", "压力管理", "学习能力"], 20),
    ("综合能力测评卷B", "综合测评", "针对管理岗位的综合素质测评,侧重决策、协调、战略思维。",
     90, {"简单": 0.2, "中等": 0.5, "困难": 0.3}, ["决策能力", "团队协作", "战略思维", "项目管理"], 25),
    ("Java专业技能测评卷", "专业技能", "Java后端开发工程师专业技能测评,涵盖基础、并发、框架、性能优化。",
     120, {"简单": 0.2, "中等": 0.5, "困难": 0.3}, ["Java基础", "并发编程", "Spring生态", "性能优化"], 30),
    ("Python专业技能测评卷", "专业技能", "Python开发工程师专业技能测评,涵盖语法、Web框架、数据处理、自动化。",
     90, {"简单": 0.25, "中等": 0.55, "困难": 0.2}, ["Python基础", "Web开发", "数据处理", "自动化测试"], 25),
    ("前端工程师技能测评卷", "专业技能", "前端工程师专业技能测评,涵盖HTML/CSS/JS、React/Vue、工程化。",
     100, {"简单": 0.25, "中等": 0.55, "困难": 0.2}, ["HTML/CSS", "JavaScript", "前端框架", "工程化"], 28),
    ("职业性格倾向测评卷", "职业性格", "MBTI/Big Five职业性格测评,评估候选人与岗位的性格匹配度。",
     45, {"简单": 0.5, "中等": 0.4, "困难": 0.1}, ["内外向", "细致度", "抗压性", "创新性"], 30),
    ("产品经理岗位适配卷", "岗位适配", "产品经理岗位胜任力测评,涵盖需求分析、商业判断、跨部门协调。",
     80, {"简单": 0.2, "中等": 0.5, "困难": 0.3}, ["需求洞察", "商业判断", "项目管理", "协调沟通"], 22),
    ("数据分析师岗位适配卷", "岗位适配", "数据分析师岗位适配测评,涵盖SQL、统计基础、业务理解、数据可视化。",
     90, {"简单": 0.25, "中等": 0.55, "困难": 0.2}, ["SQL基础", "统计分析", "业务理解", "数据可视化"], 25),
    ("运维工程师岗位适配卷", "岗位适配", "运维/DevOps岗位适配测评,涵盖Linux、Docker、K8s、监控告警。",
     90, {"简单": 0.2, "中等": 0.55, "困难": 0.25}, ["Linux", "容器化", "Kubernetes", "监控告警"], 25),
    ("管理干部综合测评卷", "综合测评", "面向管理岗位干部的综合测评,涵盖领导力、战略、组织协调。",
     100, {"简单": 0.15, "中等": 0.5, "困难": 0.35}, ["领导力", "战略思维", "组织协调", "决策能力"], 25),
]

COURSE_DEFS = [
    # (课程名称, 分类, 类型, 时长, 讲师, 评分, 评分人数, 标签)
    ("Python入门到实战", "skill", "video", 600, "李明", 4.8, 156, ["Python", "编程基础"]),
    ("Java核心技术精讲", "skill", "video", 720, "王强", 4.7, 132, ["Java", "后端开发"]),
    ("Go语言实战开发", "skill", "video", 480, "张伟", 4.6, 88, ["Go", "云原生"]),
    ("React企业级应用开发", "skill", "video", 540, "陈静", 4.9, 203, ["React", "前端"]),
    ("Vue3从入门到精通", "skill", "video", 420, "刘洋", 4.5, 121, ["Vue", "前端"]),
    ("SQL数据库性能优化", "skill", "document", 180, "赵敏", 4.4, 95, ["SQL", "MySQL", "性能优化"]),
    ("Docker容器技术实战", "skill", "video", 360, "孙磊", 4.7, 178, ["Docker", "DevOps"]),
    ("Kubernetes生产环境实践", "skill", "video", 540, "周强", 4.8, 145, ["K8s", "云原生"]),
    ("Linux系统管理与运维", "skill", "document", 240, "黄涛", 4.3, 67, ["Linux", "运维"]),
    ("数据结构与算法精讲", "skill", "courseware", 480, "吴芳", 4.6, 198, ["算法", "基础"]),
    ("Spring Boot企业开发实战", "skill", "video", 720, "郑华", 4.7, 142, ["Spring", "Java"]),
    ("FastAPI高性能API开发", "skill", "video", 360, "徐丽", 4.5, 89, ["FastAPI", "Python"]),
    ("Redis高可用与最佳实践", "skill", "document", 200, "林峰", 4.6, 102, ["Redis", "缓存"]),
    ("Kafka消息队列深入剖析", "skill", "video", 360, "谢军", 4.5, 76, ["Kafka", "消息队列"]),
    ("微服务架构设计与落地", "skill", "video", 600, "钟楠", 4.8, 156, ["微服务", "架构"]),
    ("大数据Spark原理与实战", "skill", "video", 720, "高建", 4.7, 113, ["Spark", "大数据"]),
    ("机器学习入门导论", "profession", "video", 480, "罗敏", 4.6, 134, ["机器学习", "AI"]),
    ("深度学习与PyTorch实战", "profession", "video", 720, "蔡文", 4.7, 98, ["深度学习", "PyTorch"]),
    ("数据可视化与ECharts", "skill", "video", 240, "邓芳", 4.4, 87, ["ECharts", "可视化"]),
    ("Pandas数据分析实战", "skill", "video", 360, "宋涛", 4.6, 145, ["Pandas", "数据分析"]),
    ("前端工程化与Webpack", "skill", "video", 420, "韩雪", 4.7, 167, ["Webpack", "前端工程"]),
    ("TypeScript进阶实战", "skill", "video", 360, "冯刚", 4.5, 121, ["TypeScript", "前端"]),
    ("新员工入职指南", "level", "text_image", 60, "人力资源部", 4.2, 234, ["入职", "企业文化"]),
    ("初级工程师能力提升", "level", "courseware", 300, "技术学院", 4.5, 178, ["初级", "能力提升"]),
    ("中级工程师进阶之路", "level", "video", 480, "技术学院", 4.6, 156, ["中级", "进阶"]),
    ("高级工程师架构思维", "level", "video", 600, "技术学院", 4.8, 134, ["高级", "架构"]),
    ("技术专家成长营", "level", "courseware", 720, "技术学院", 4.7, 89, ["专家", "成长"]),
    ("管理干部领导力培养", "level", "video", 480, "管理学院", 4.6, 76, ["管理", "领导力"]),
    ("产品经理岗位培训", "position", "video", 360, "产品学院", 4.5, 102, ["产品经理", "岗位培训"]),
    ("数据分析师岗位培训", "position", "video", 360, "数据学院", 4.6, 89, ["数据分析师", "岗位培训"]),
    ("运维工程师岗位培训", "position", "video", 300, "运维学院", 4.4, 67, ["运维", "岗位培训"]),
    ("测试工程师岗位培训", "position", "video", 300, "质量学院", 4.3, 78, ["测试", "岗位培训"]),
    ("市场运营岗位培训", "position", "document", 240, "市场学院", 4.2, 56, ["市场", "运营"]),
    ("HR专员岗位培训", "position", "document", 200, "人力资源部", 4.3, 45, ["HR", "岗位培训"]),
    ("财务岗专业培训", "position", "document", 240, "财务部", 4.4, 38, ["财务", "岗位培训"]),
    ("DevOps工程师进阶", "profession", "video", 540, "运维学院", 4.7, 92, ["DevOps", "进阶"]),
    ("Java高级特性实战", "profession", "video", 480, "技术学院", 4.6, 121, ["Java", "高级"]),
    ("敏捷开发与Scrum实践", "profession", "video", 360, "管理学院", 4.5, 87, ["敏捷", "Scrum"]),
    ("项目管理体系培训", "profession", "courseware", 600, "管理学院", 4.6, 76, ["项目管理", "PMP"]),
    ("数字化转型与中台战略", "profession", "video", 480, "战略学院", 4.7, 65, ["数字化转型", "中台"]),
]


# ============================================================================
# 工具函数
# ============================================================================

def _random_dt(days_back_max=180, days_back_min=1):
    """生成一个过去某时刻的 datetime(默认 1-180 天前)"""
    delta_days = random.randint(days_back_min, days_back_max)
    delta_seconds = random.randint(0, 86400 - 1)
    return datetime.now() - timedelta(days=delta_days, seconds=delta_seconds)


def _pick_n_skills(n=3):
    return [{"name": s, "level": random.choice(["了解", "熟练", "精通"])} for s in random.sample(SKILL_POOL, n)]


def _pick_n_tags(n=3):
    return random.sample(TAG_POOL, n)


# ============================================================================
# 0. talents 表 - 空库时生成演示档案
# ============================================================================

SURNAMES = [
    "张", "王", "李", "赵", "刘", "陈", "杨", "黄", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "高", "罗",
    "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹",
]

GIVEN_NAMES = [
    "伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "洋", "艳",
    "勇", "军", "杰", "娟", "涛", "明", "超", "秀英", "霞", "平",
    "刚", "桂英", "建国", "文", "辉", "雪", "岩", "鹏", "宇", "晨",
    "浩然", "思远", "佳怡", "子涵", "雨桐", "慧敏", "志强", "晓明", "建华", "淑华",
    "玉兰", "晓燕", "丹丹", "小龙", "大伟", "俊杰", "雅静", "梦琪", "欣怡", "国华",
]

CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都", "武汉", "南京", "西安", "苏州"]


def seed_talents(db: Session, target: int = 40) -> list:
    """talents 表为空时生成演示人才档案（幂等：按手机号去重）。

    原脚本的 update_talents_diversity 只做「分布更新」、不负责建档，
    因此在全新空库上必须先建档案，否则 main() 会因 talents 为空而中止。
    手机号采用 139 + 8 位序号，天然唯一，可安全重复执行。
    """
    existing = db.query(Talent).count()
    if existing >= target:
        logger.info(f"[talents] 已存在 {existing} 条档案，跳过建档")
        return db.query(Talent).order_by(Talent.id).all()

    position_titles = [p[0] for p in POSITIONS]
    created = 0
    for i in range(1, target + 1):
        phone = f"139{i:08d}"
        if db.query(Talent).filter(Talent.phone == phone).first():
            continue
        try:
            years = random.randint(0, 15)
            education = random.choices(
                [
                    SchemaEducation.HIGH_SCHOOL,
                    SchemaEducation.COLLEGE,
                    SchemaEducation.BACHELOR,
                    SchemaEducation.MASTER,
                    SchemaEducation.DOCTOR,
                ],
                weights=[4, 12, 65, 14, 5],
                k=1,
            )[0]
            company = random.choice(COMPANIES)
            title = random.choice(position_titles)
            salary_min = 8000 + years * 2200
            talent_in = TalentCreate(
                name=random.choice(SURNAMES) + random.choice(GIVEN_NAMES),
                gender=random.choice([SchemaGender.MALE, SchemaGender.FEMALE]),
                birth_date=date(
                    1985 + random.randint(0, 15),
                    random.randint(1, 12),
                    random.randint(1, 28),
                ),
                phone=phone,
                email=f"talent{i:03d}@example.com",
                address=random.choice(CITIES),
                education=education,
                major=random.choice(MAJORS),
                experience_years=years,
                current_company=company,
                current_position=title,
                expected_salary_min=salary_min,
                expected_salary_max=salary_min + random.randint(4000, 15000),
                expected_position=title,
                self_introduction=(
                    f"{years} 年{title}经验，现就职于{company}，"
                    f"熟悉{random.choice(SKILL_POOL)}、{random.choice(SKILL_POOL)}等技术栈。"
                ),
                status=SchemaTalentStatus.RESERVE,
                skills_certificates=_pick_n_skills(random.randint(3, 6)),
                tags=_pick_n_tags(random.randint(2, 4)),
            )
            TalentService.create_talent(db, talent_in)
            created += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning(f"[talents] 建档失败 phone={phone}: {str(e)[:120]}")

    total = db.query(Talent).count()
    logger.info(f"[talents] 新建档案 {created} 条，当前共 {total} 条（目标 {target} 条）")
    return db.query(Talent).order_by(Talent.id).all()


# ============================================================================
# 1. 更新 talents 表 - 多样化分布学历/状态/性别(不改姓名手机号)
# ============================================================================

def update_talents_diversity(db: Session) -> None:
    """更新现有 talents 表的学历/状态/性别字段为多样化分布(只更新这三类字段)"""
    all_talents = db.query(Talent).order_by(Talent.id).all()
    total = len(all_talents)
    if total == 0:
        logger.warning("[talents] 当前表为空,跳过更新")
        return

    # 目标分布:
    # 学历: 高中 4% / 大专 12% / 本科 65% / 硕士 14% / 博士 5%
    # 状态: active 45% / reserve 30% / resigned 15% / on_leave 10%
    # 性别: male 60% / female 40%
    edu_pool = (
        [EducationLevel.HIGH_SCHOOL] * int(total * 0.04)
        + [EducationLevel.COLLEGE] * int(total * 0.12)
        + [EducationLevel.BACHELOR] * int(total * 0.65)
        + [EducationLevel.MASTER] * int(total * 0.14)
        + [EducationLevel.DOCTOR] * int(total * 0.05)
    )
    # 用 round 补齐到 total
    while len(edu_pool) < total:
        edu_pool.append(EducationLevel.BACHELOR)
    edu_pool = edu_pool[:total]
    random.shuffle(edu_pool)

    status_pool = (
        [TalentStatus.ACTIVE] * int(total * 0.45)
        + [TalentStatus.RESERVE] * int(total * 0.30)
        + [TalentStatus.RESIGNED] * int(total * 0.15)
        + [TalentStatus.ON_LEAVE] * int(total * 0.10)
    )
    while len(status_pool) < total:
        status_pool.append(TalentStatus.ACTIVE)
    status_pool = status_pool[:total]
    random.shuffle(status_pool)

    gender_pool = (
        [GenderEnum.MALE] * int(total * 0.60)
        + [GenderEnum.FEMALE] * int(total * 0.40)
    )
    while len(gender_pool) < total:
        gender_pool.append(GenderEnum.MALE)
    gender_pool = gender_pool[:total]
    random.shuffle(gender_pool)

    updated_count = 0
    for t, edu, st, g in zip(all_talents, edu_pool, status_pool, gender_pool):
        # 只更新这三个字段
        t.education = edu
        t.status = st
        t.gender = g
        updated_count += 1

    db.commit()
    logger.info(f"[talents] 已更新 {updated_count} 条记录的学历/状态/性别分布")


# ============================================================================
# 2. JobPosition 表 - 新增到 35-40 条
# ============================================================================

def seed_job_positions(db: Session) -> list:
    """插入岗位数据,返回已存在+新建的全部岗位列表(用于后续关联)"""
    existing = db.query(JobPosition).order_by(JobPosition.id).all()
    if len(existing) >= 35:
        logger.info(f"[job_positions] 已有 {len(existing)} 条,跳过插入")
        return existing

    # 取一个组织用于关联
    org = db.query(Organization).filter(Organization.org_code == "HQ").first()

    created = []
    for idx, p in enumerate(POSITIONS, start=1):
        (name, category, level, ptype, hc, fc, status,
         smin, smax, edu_req, exp_req) = p
        code = f"POS-{idx:04d}"
        existing_one = db.query(JobPosition).filter(JobPosition.position_code == code).first()
        if existing_one:
            created.append(existing_one)
            continue

        skills = _pick_n_skills(random.randint(2, 4))
        tags = _pick_n_tags(random.randint(2, 3))
        capabilities = _pick_n_tags(2)
        publish_date = _random_dt(days_back_max=120, days_back_min=5)
        deadline = publish_date + timedelta(days=random.randint(15, 90))

        pos = JobPosition(
            position_code=code,
            position_name=name,
            department_id=org.id if org else None,
            position_category=category,
            position_level=PositionLevel(level),
            position_type=ptype,
            headcount=hc,
            filled_count=fc,
            salary_min=smin,
            salary_max=smax,
            work_location=random.choice(["北京", "上海", "深圳", "杭州", "广州", "成都", "远程"]),
            education_requirement=edu_req,
            experience_requirement=exp_req,
            skill_requirements=skills,
            capability_requirements=capabilities,
            job_description=f"{name}岗位招聘,负责相关业务模块的设计、开发与维护工作。",
            job_responsibilities=(
                f"1. 负责{name}相关的需求分析、技术方案设计与开发实现;\n"
                "2. 与产品、测试、运维紧密协作,保证项目按期高质量交付;\n"
                "3. 持续优化系统性能,提升系统稳定性与可维护性;\n"
                "4. 参与代码评审,推动技术规范落地。"
            ),
            tags=tags,
            status=status,
            publish_date=publish_date,
            deadline=deadline if status != PositionStatus.CLOSED else None,
            created_at=_random_dt(days_back_max=180, days_back_min=30),
        )
        db.add(pos)
        created.append(pos)

    db.commit()
    for p in created:
        db.refresh(p)

    # 验证至少8个 open + headcount>filled_count
    open_gap = sum(
        1 for p in created
        if p.status == PositionStatus.OPEN and p.headcount > p.filled_count
    )
    logger.info(
        f"[job_positions] 共 {len(created)} 条岗位,其中 open 且 headcount>filled 的缺口岗位 {open_gap} 个"
    )
    return created


# ============================================================================
# 3. Questions 表 - 35-40 条
# ============================================================================

def seed_questions(db: Session) -> list:
    """插入题库数据"""
    existing = db.query(Question).count()
    if existing > 0:
        logger.info(f"[questions] 已有 {existing} 条,跳过插入")
        return db.query(Question).order_by(Question.id).all()

    created = []
    for idx, q in enumerate(QUESTION_BANK, start=1):
        (qtype, category, content, options, answer, analysis,
         score, difficulty, dimension) = q
        code = f"Q-{idx:04d}"
        # 选项格式统一为 dict 列表(便于前端渲染)
        options_json = None
        if options:
            options_json = [{"label": opt.split(".")[0], "text": opt} for opt in options]
        question = Question(
            question_code=code,
            question_content=content,
            question_type=qtype,
            question_category=category,
            options=options_json,
            correct_answer=answer,
            answer_analysis=analysis,
            score_value=score,
            difficulty=difficulty,
            capability_dimension=dimension,
            tags=_pick_n_tags(2),
            status="active",
            created_at=_random_dt(days_back_max=240, days_back_min=10),
        )
        db.add(question)
        created.append(question)

    db.commit()
    for q in created:
        db.refresh(q)
    logger.info(f"[questions] 共插入 {len(created)} 条题目")
    return created


# ============================================================================
# 4. TestPapers 表 - 8-10 条
# ============================================================================

def seed_test_papers(db: Session, questions: list) -> list:
    """插入试卷数据"""
    existing = db.query(TestPaper).count()
    if existing > 0:
        logger.info(f"[test_papers] 已有 {existing} 条,跳过插入")
        return db.query(TestPaper).order_by(TestPaper.id).all()

    created = []
    for idx, p in enumerate(PAPER_DEFS, start=1):
        (name, ptype, desc, duration, diff_dist, dims, qnum) = p
        code = f"TP-{idx:03d}"
        # 随机抽 qnum 道题,记录题号与分值(每题分值=总分/题数)
        sampled = random.sample(questions, min(qnum, len(questions)))
        per_score = round(100.0 / len(sampled), 2)
        questions_meta = [
            {"question_id": q.id, "score": per_score} for q in sampled
        ]
        paper = TestPaper(
            paper_code=code,
            paper_name=name,
            paper_type=ptype,
            paper_description=desc,
            questions=questions_meta,
            total_score=100.00,
            duration_minutes=duration,
            difficulty_distribution=diff_dist,
            capability_dimensions=dims,
            status="published",
            created_at=_random_dt(days_back_max=200, days_back_min=15),
        )
        db.add(paper)
        created.append(paper)

    db.commit()
    for p in created:
        db.refresh(p)
    logger.info(f"[test_papers] 共插入 {len(created)} 条试卷")
    return created


# ============================================================================
# 5. AssessmentTasks 表 - 8-10 条
# ============================================================================

def seed_assessment_tasks(db: Session, papers: list, talents: list) -> list:
    """插入测评任务数据"""
    existing = db.query(AssessmentTask).count()
    if existing > 0:
        logger.info(f"[assessment_tasks] 已有 {existing} 条,跳过插入")
        return db.query(AssessmentTask).order_by(AssessmentTask.id).all()

    status_cycle = [
        AssessmentStatus.DRAFT, AssessmentStatus.PUBLISHED,
        AssessmentStatus.IN_PROGRESS, AssessmentStatus.COMPLETED,
    ]

    created = []
    for idx, paper in enumerate(papers, start=1):
        code = f"AT-{idx:03d}"
        status = status_cycle[(idx - 1) % len(status_cycle)]
        # 抽 5-15 个 talent 作为对象
        targets = [t.id for t in random.sample(talents, min(8, len(talents)))]
        start_time = _random_dt(days_back_max=120, days_back_min=5)
        end_time = start_time + timedelta(days=random.randint(7, 30))
        task = AssessmentTask(
            task_code=code,
            task_name=f"{paper.paper_name}·第{idx}期",
            target_type="batch",
            target_talents=targets,
            paper_id=paper.id,
            start_time=start_time,
            end_time=end_time,
            allow_retake=(status == AssessmentStatus.DRAFT),
            max_attempts=random.choice([1, 1, 2]),
            show_answer=(status == AssessmentStatus.COMPLETED),
            anti_cheating=True,
            status=status,
            created_at=_random_dt(days_back_max=120, days_back_min=5),
        )
        db.add(task)
        created.append(task)

    db.commit()
    for t in created:
        db.refresh(t)
    logger.info(f"[assessment_tasks] 共插入 {len(created)} 条任务")
    return created


# ============================================================================
# 6. AssessmentResults 表 - 35-40 条
# ============================================================================

def seed_assessment_results(db: Session, tasks: list, papers: list, talents: list) -> None:
    """插入测评结果数据"""
    existing = db.query(AssessmentResult).count()
    if existing > 0:
        logger.info(f"[assessment_results] 已有 {existing} 条,跳过插入")
        return

    cap_levels = [
        CapabilityLevel.ENTRY, CapabilityLevel.JUNIOR,
        CapabilityLevel.INTERMEDIATE, CapabilityLevel.SENIOR, CapabilityLevel.EXPERT,
    ]
    created_count = 0
    target_total = 38
    used_pairs = set()  # (talent_id, task_id) 唯一索引

    # 对每个 task 关联若干 talent,直到达到目标条数
    task_idx = 0
    while created_count < target_total and tasks:
        task = tasks[task_idx % len(tasks)]
        paper = next((p for p in papers if p.id == task.paper_id), papers[0])
        # 随机选一个 talent
        random.shuffle(talents)
        for talent in talents:
            if created_count >= target_total:
                break
            pair = (talent.id, task.id)
            if pair in used_pairs:
                continue
            used_pairs.add(pair)

            score = round(random.uniform(40, 98), 2)
            passed = score >= 60
            # 题目总数取 paper 中题目数(默认 20)
            q_count = len(paper.questions) if paper.questions else 20
            correct = int(q_count * score / 100)
            wrong = q_count - correct
            cap_level = random.choice(cap_levels)

            # 雷达图:5个维度随机分
            radar = [
                {"name": dim, "value": round(random.uniform(50, 95), 1)}
                for dim in (paper.capability_dimensions or ["决策能力", "团队协作", "抗压能力", "学习能力", "专业技能"])
            ]

            start_time = _random_dt(days_back_max=60, days_back_min=1)
            submit_time = start_time + timedelta(seconds=random.randint(600, 5400))
            duration_seconds = int((submit_time - start_time).total_seconds())

            result = AssessmentResult(
                result_code=f"AR-{created_count + 1:04d}",
                talent_id=talent.id,
                task_id=task.id,
                paper_id=paper.id,
                answers=[
                    {"question_id": q["question_id"], "correct": random.random() < (score / 100)}
                    for q in (paper.questions or [])[:5]
                ] or [{"question_id": 1, "correct": passed}],
                total_score=score,
                correct_count=correct,
                wrong_count=wrong,
                unanswered_count=0,
                capability_dimensions={
                    dim["name"]: dim["value"] for dim in radar
                },
                radar_chart_data=radar,
                report=(
                    f"本次测评总分 {score} 分,{'通过' if passed else '未通过'}。"
                    f"能力等级评估为 {cap_level.value}。"
                ),
                strengths="技术基础扎实,团队协作能力突出,在专业维度表现优秀。",
                weaknesses="在复杂场景下的综合决策能力有待提升,系统设计深度需加强。",
                suggestions="建议持续学习架构设计与系统优化,参与更多跨团队项目积累综合经验。",
                capability_level=cap_level,
                start_time=start_time,
                submit_time=submit_time,
                duration_seconds=duration_seconds,
                status="completed",
                created_at=submit_time,
            )
            db.add(result)
            created_count += 1
        task_idx += 1
        # 防止无限循环(所有 task × 所有 talent 都已用过)
        if task_idx > len(tasks) * 3:
            break

    db.commit()
    logger.info(f"[assessment_results] 共插入 {created_count} 条结果")


# ============================================================================
# 7. Courses 表 - 35-40 条
# ============================================================================

def seed_courses(db: Session) -> list:
    """插入课程数据"""
    existing = db.query(Course).count()
    if existing > 0:
        logger.info(f"[courses] 已有 {existing} 条,跳过插入")
        return db.query(Course).order_by(Course.id).all()

    created = []
    for idx, c in enumerate(COURSE_DEFS, start=1):
        (name, category, ctype, duration, instructor, rating, rating_count, tags) = c
        code = f"C-{idx:03d}"
        course = Course(
            course_code=code,
            course_name=name,
            course_category=CourseCategory(category),
            course_type=CourseType(ctype),
            course_content=(
                f"# {name}\n\n本课程系统讲解{name.replace('实战', '').replace('入门到', '')}的核心知识点,"
                "结合实际案例,帮助学员掌握关键技能并能应用于实际工作场景。\n\n"
                "## 课程大纲\n1. 基础概念与原理\n2. 核心技术详解\n3. 实战案例剖析\n4. 最佳实践总结\n"
            ),
            course_url=f"https://learn.digital-talent.com/courses/{code.lower()}",
            course_file_id=None,
            duration_minutes=duration,
            instructor=instructor,
            permissions=[{"role": "user"}],
            rating=rating,
            rating_count=rating_count,
            comments=[
                {"user": "学员A", "rating": 5, "content": "讲解清晰,案例丰富,收获很大。"},
                {"user": "学员B", "rating": 4, "content": "内容不错,期待更多实战部分。"},
            ],
            tags=tags,
            status="active",
            created_at=_random_dt(days_back_max=240, days_back_min=15),
        )
        db.add(course)
        created.append(course)

    db.commit()
    for c in created:
        db.refresh(c)
    logger.info(f"[courses] 共插入 {len(created)} 条课程")
    return created


# ============================================================================
# 8. TrainingPlans 表 - 8-10 条
# ============================================================================

def seed_training_plans(db: Session, courses: list, talents: list) -> list:
    """插入培训计划数据"""
    existing = db.query(TrainingPlan).count()
    if existing > 0:
        logger.info(f"[training_plans] 已有 {existing} 条,跳过插入")
        return db.query(TrainingPlan).order_by(TrainingPlan.id).all()

    plan_defs = [
        ("2026届新员工入职培训", TrainingStatus.COMPLETED, "level", 8),
        ("Java后端工程师专项提升", TrainingStatus.IN_PROGRESS, "skill", 6),
        ("Python开发工程师能力培养", TrainingStatus.IN_PROGRESS, "skill", 6),
        ("前端工程师技能进阶", TrainingStatus.PUBLISHED, "skill", 6),
        ("中高级工程师架构能力提升", TrainingStatus.PUBLISHED, "level", 5),
        ("数据分析师专项培养", TrainingStatus.IN_PROGRESS, "position", 5),
        ("DevOps工程师转型计划", TrainingStatus.PUBLISHED, "skill", 5),
        ("管理干部领导力培养项目", TrainingStatus.IN_PROGRESS, "level", 8),
        ("产品经理岗位赋能计划", TrainingStatus.DRAFT, "position", 5),
        ("数字化转型专题研讨班", TrainingStatus.DRAFT, "profession", 5),
    ]

    created = []
    for idx, (name, status, _, course_count) in enumerate(plan_defs, start=1):
        code = f"TP-{idx:03d}"
        sampled_courses = random.sample(courses, min(course_count, len(courses)))
        course_meta = [
            {"course_id": c.id, "course_name": c.course_name} for c in sampled_courses
        ]
        sampled_talents = random.sample(talents, min(8, len(talents)))
        targets = [t.id for t in sampled_talents]
        start_time = _random_dt(days_back_max=90, days_back_min=5)
        end_time = start_time + timedelta(days=random.randint(30, 120))

        plan = TrainingPlan(
            plan_code=code,
            plan_name=name,
            target_talents=targets,
            target_type="batch",
            courses=course_meta,
            start_time=start_time,
            end_time=end_time,
            learning_reminder=True,
            examination_required=(status != TrainingStatus.DRAFT),
            status=status,
            created_at=_random_dt(days_back_max=120, days_back_min=10),
        )
        db.add(plan)
        created.append(plan)

    db.commit()
    for p in created:
        db.refresh(p)
    logger.info(f"[training_plans] 共插入 {len(created)} 条计划")
    return created


# ============================================================================
# 9. LearningRecords 表 - 35-40 条
# ============================================================================

def seed_learning_records(db: Session, courses: list, plans: list, talents: list) -> None:
    """插入学习记录数据"""
    existing = db.query(LearningRecord).count()
    if existing > 0:
        logger.info(f"[learning_records] 已有 {existing} 条,跳过插入")
        return

    status_pool = [
        LearningStatus.NOT_STARTED, LearningStatus.IN_PROGRESS,
        LearningStatus.COMPLETED, LearningStatus.FAILED,
    ]
    # 保证至少 6 条 NOT_STARTED 用于智能预警
    target_total = 38
    used_pairs = set()  # (talent_id, course_id) 唯一索引
    created_count = 0
    not_started_count = 0

    # 先插入 6 条 not_started
    while not_started_count < 6 and created_count < target_total:
        course = random.choice(courses)
        plan = random.choice(plans)
        talent = random.choice(talents)
        pair = (talent.id, course.id)
        if pair in used_pairs:
            continue
        used_pairs.add(pair)

        rec = LearningRecord(
            record_code=f"LR-{created_count + 1:04d}",
            talent_id=talent.id,
            course_id=course.id,
            plan_id=plan.id,
            progress=0.00,
            duration_minutes=0,
            status=LearningStatus.NOT_STARTED,
            last_learning_time=None,
            completed_time=None,
            created_at=_random_dt(days_back_max=30, days_back_min=1),
        )
        db.add(rec)
        created_count += 1
        not_started_count += 1

    # 剩余随机分布
    attempts = 0
    while created_count < target_total and attempts < target_total * 5:
        attempts += 1
        course = random.choice(courses)
        plan = random.choice(plans)
        talent = random.choice(talents)
        pair = (talent.id, course.id)
        if pair in used_pairs:
            continue
        used_pairs.add(pair)

        status = random.choice(status_pool)
        if status == LearningStatus.NOT_STARTED:
            progress = 0.0
            duration = 0
            last_time = None
            completed = None
        elif status == LearningStatus.IN_PROGRESS:
            progress = round(random.uniform(10, 90), 2)
            duration = random.randint(20, 400)
            last_time = _random_dt(days_back_max=15, days_back_min=1)
            completed = None
        elif status == LearningStatus.COMPLETED:
            progress = 100.00
            duration = random.randint(course.duration_minutes or 60, (course.duration_minutes or 60) * 2)
            last_time = _random_dt(days_back_max=60, days_back_min=5)
            completed = last_time
        else:  # FAILED
            progress = round(random.uniform(40, 80), 2)
            duration = random.randint(60, 300)
            last_time = _random_dt(days_back_max=60, days_back_min=5)
            completed = None

        rec = LearningRecord(
            record_code=f"LR-{created_count + 1:04d}",
            talent_id=talent.id,
            course_id=course.id,
            plan_id=plan.id,
            progress=progress,
            duration_minutes=duration,
            status=status,
            last_learning_time=last_time,
            completed_time=completed,
            created_at=_random_dt(days_back_max=90, days_back_min=1),
        )
        db.add(rec)
        created_count += 1

    db.commit()
    logger.info(
        f"[learning_records] 共插入 {created_count} 条,其中 NOT_STARTED {not_started_count} 条"
    )


# ============================================================================
# 10. ExaminationRecords 表 - 35-40 条
# ============================================================================

def seed_examination_records(db: Session, courses: list, plans: list, talents: list) -> None:
    """插入考核记录数据"""
    existing = db.query(ExaminationRecord).count()
    if existing > 0:
        logger.info(f"[examination_records] 已有 {existing} 条,跳过插入")
        return

    target_total = 38
    created_count = 0
    attempts = 0
    used_combos = set()  # (talent_id, course_id) 非唯一,但避免完全重复

    while created_count < target_total and attempts < target_total * 5:
        attempts += 1
        course = random.choice(courses)
        plan = random.choice(plans)
        talent = random.choice(talents)
        combo = (talent.id, course.id)
        if combo in used_combos:
            # 允许重复但限制同一对最多2次
            continue
        used_combos.add(combo)

        score = round(random.uniform(40, 95), 2)
        passed = score >= 60
        start_time = _random_dt(days_back_max=60, days_back_min=1)
        submit_time = start_time + timedelta(seconds=random.randint(300, 5400))
        duration_seconds = int((submit_time - start_time).total_seconds())

        rec = ExaminationRecord(
            record_code=f"ER-{created_count + 1:04d}",
            talent_id=talent.id,
            course_id=course.id,
            plan_id=plan.id,
            answers=[
                {"question_id": i, "correct": random.random() < (score / 100)}
                for i in range(1, 6)
            ],
            score=score,
            passed=passed,
            start_time=start_time,
            submit_time=submit_time,
            duration_seconds=duration_seconds,
            created_at=submit_time,
        )
        db.add(rec)
        created_count += 1

    db.commit()
    logger.info(f"[examination_records] 共插入 {created_count} 条考核记录")


# ============================================================================
# 主流程
# ============================================================================

def _print_summary(db: Session) -> None:
    """打印各表当前总数"""
    tables = [
        ("talents", Talent),
        ("job_positions", JobPosition),
        ("questions", Question),
        ("test_papers", TestPaper),
        ("assessment_tasks", AssessmentTask),
        ("assessment_results", AssessmentResult),
        ("courses", Course),
        ("training_plans", TrainingPlan),
        ("learning_records", LearningRecord),
        ("examination_records", ExaminationRecord),
        ("organizations", Organization),
    ]
    logger.info("=" * 60)
    logger.info("各业务表当前记录总数:")
    for name, model in tables:
        try:
            cnt = db.query(model).count()
            logger.info(f"  {name:22s} : {cnt}")
        except Exception as e:
            logger.warning(f"  {name:22s} : 查询失败 {e}")
    logger.info("=" * 60)

    # 额外打印分布统计便于核对
    try:
        from sqlalchemy import func as sql_func
        edu_dist = db.query(Talent.education, sql_func.count(Talent.id)).group_by(Talent.education).all()
        logger.info(f"  学历分布: {dict(edu_dist)}")
        st_dist = db.query(Talent.status, sql_func.count(Talent.id)).group_by(Talent.status).all()
        logger.info(f"  状态分布: {dict(st_dist)}")
        g_dist = db.query(Talent.gender, sql_func.count(Talent.id)).group_by(Talent.gender).all()
        logger.info(f"  性别分布: {dict(g_dist)}")
        pos_status_dist = db.query(JobPosition.status, sql_func.count(JobPosition.id)).group_by(JobPosition.status).all()
        logger.info(f"  岗位状态分布: {dict(pos_status_dist)}")
    except Exception as e:
        logger.warning(f"  分布统计失败: {e}")


def main() -> None:
    logger.info("开始执行业务表种子数据初始化...")
    SessionFactory = get_mysql_session_factory()
    if SessionFactory is None:
        logger.error("MySQL session factory 未初始化,请确认 .env 配置正确")
        return

    db: Session = SessionFactory()
    try:
        # 0. 空库时先生成演示人才档案（幂等）
        seed_talents(db)

        # 1. 更新现有 talents 多样化分布
        update_talents_diversity(db)

        # 取出所有 talent / organization 用于后续关联
        all_talents = db.query(Talent).order_by(Talent.id).all()
        if not all_talents:
            logger.error("talents 表为空,无法继续插入业务数据")
            return

        # 2. JobPositions
        positions = seed_job_positions(db)

        # 3. Questions
        questions = seed_questions(db)

        # 4. TestPapers
        papers = seed_test_papers(db, questions)

        # 5. AssessmentTasks
        tasks = seed_assessment_tasks(db, papers, all_talents)

        # 6. AssessmentResults
        seed_assessment_results(db, tasks, papers, all_talents)

        # 7. Courses
        courses = seed_courses(db)

        # 8. TrainingPlans
        plans = seed_training_plans(db, courses, all_talents)

        # 9. LearningRecords
        seed_learning_records(db, courses, plans, all_talents)

        # 10. ExaminationRecords
        seed_examination_records(db, courses, plans, all_talents)

        logger.info("业务表种子数据初始化完成!")

        # 打印各表最终记录数
        _print_summary(db)

    except Exception as e:
        db.rollback()
        logger.error(f"种子数据初始化失败: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
