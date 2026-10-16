# -*- coding: utf-8 -*-
"""
参考曹文栋 / 黄学勤 / 许剑鸿 简历的大数据开发风格，
用 reportlab 生成 gr01.pdf ~ gr04.pdf 覆盖 golden_resumes 目录原文件。

设计要点：
1. 每人不同岗位方向/年限/姓名/学校/手机号/邮箱
2. 技能条 + 工作经历 + 2~3 个典型项目（数仓、ETL、实时、可视化）
3. 中文使用 STSong-Light 或思源黑体（reportlab 内置 CID 字体有 STSong-Light，支持中文）
"""
import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    ListFlowable, ListItem, HRFlowable, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont

# ── 注册中文字体（优先 reportlab 内置 CID 字体，STSung-Light）──
try:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    CJK_FONT = "STSong-Light"
except Exception:
    CJK_FONT = "Helvetica"
    print("WARN: STSong-Light 不可用，使用 Helvetica（中文可能无法渲染）")

OUT_DIR = Path(r"d:\PythonHayson\digital_talent_platform\golden_resumes")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 颜色 ──
BRAND = colors.HexColor("#1f6feb")
ACCENT = colors.HexColor("#0ea5e9")
DARK = colors.HexColor("#0f172a")
SUB = colors.HexColor("#475569")
DIVIDER = colors.HexColor("#e2e8f0")
SOFT_BG = colors.HexColor("#f1f5f9")

# ── 样式 ──
def make_styles():
    s = getSampleStyleSheet()
    styles = {}
    # 统一基础参数，每次单独传入避免重复关键字
    base = dict(fontName=CJK_FONT, wordWrap="CJK")
    styles["name"]      = ParagraphStyle("name",      **base, fontSize=24, leading=30, textColor=DARK,
                                         alignment=TA_LEFT, spaceAfter=2)
    styles["tagline"]   = ParagraphStyle("tagline",   **base, fontSize=11.5, leading=16,
                                         textColor=BRAND, spaceAfter=10, alignment=TA_LEFT)
    styles["section"]   = ParagraphStyle("section",   **base, fontSize=13.5, leading=22,
                                         textColor=BRAND, spaceBefore=10, spaceAfter=6)
    styles["sub"]       = ParagraphStyle("sub",       **base, fontSize=10, leading=16,
                                         textColor=SUB, alignment=TA_LEFT)
    styles["body"]      = ParagraphStyle("body",      **base, fontSize=10.5, leading=17,
                                         alignment=TA_JUSTIFY, textColor=DARK, spaceAfter=2)
    styles["skill"]     = ParagraphStyle("skill",     **base, fontSize=10.5, leading=18,
                                         alignment=TA_LEFT, textColor=DARK, spaceAfter=2)
    styles["proj_title"]= ParagraphStyle("proj_title",**base, fontSize=11.5, leading=18,
                                         textColor=DARK, spaceAfter=1)
    styles["proj_meta"] = ParagraphStyle("proj_meta", **base, fontSize=9.5, leading=14,
                                         textColor=SUB, spaceAfter=4)
    styles["company"]   = ParagraphStyle("company",   **base, fontSize=11, leading=16,
                                         textColor=DARK, spaceAfter=1)
    return styles

# ── 小节标题装饰 ──
def section_header(text, styles):
    return [
        Paragraph(f"■ {text}", styles["section"]),
        HRFlowable(width="100%", thickness=0.9, color=ACCENT,
                    spaceBefore=-3, spaceAfter=4),
    ]

# ── 生成单个 PDF ──
def build_resume(info, filename):
    styles = make_styles()
    path = OUT_DIR / filename
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=1.6*cm, rightMargin=1.6*cm,
        topMargin=1.5*cm, bottomMargin=1.4*cm,
        title=f"{info['name']}-个人简历",
        author=info["name"],
    )
    story = []

    # ── 头部：姓名 + 标签 + 基本信息（双列） ──
    left_rows = [
        [Paragraph(info["name"], styles["name"])],
        [Paragraph(info["tagline"], styles["tagline"])],
    ]
    right_rows = [
        [Paragraph(f"📞 {info['phone']}", styles["sub"])],
        [Paragraph(f"✉ {info['email']}", styles["sub"])],
        [Paragraph(f"🎂 {info['age']}岁 · {info['gender']} · 工作 {info['years']} 年", styles["sub"])],
        [Paragraph(f"🏫 {info['school']} · {info['degree']}", styles["sub"])],
        [Paragraph(f"📍 {info['location']}", styles["sub"])],
    ]
    inner_l = Table(left_rows, colWidths=[10.2*cm], hAlign="LEFT")
    inner_r = Table(right_rows, colWidths=[6.6*cm], hAlign="LEFT")
    inner_l.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    inner_r.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    outer = Table([[inner_l, inner_r]], colWidths=[10.2*cm, 6.6*cm], hAlign="LEFT")
    outer.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(outer)
    story.append(HRFlowable(width="100%", thickness=1.3, color=BRAND, spaceBefore=4, spaceAfter=6))

    # ── 教育背景 ──
    story.extend(section_header("教育背景", styles))
    edu = info["education"]
    story.append(Paragraph(
        f"<b>{edu['time']}</b>　{edu['school']}　{edu['major']}（{edu['degree']}）",
        styles["body"]
    ))
    if edu.get("honors"):
        story.append(Paragraph(f"🎖 {edu['honors']}", styles["sub"]))
    story.append(Spacer(1, 6))

    # ── 个人技能 ──
    story.extend(section_header("个人技能", styles))
    for idx, sk in enumerate(info["skills"], start=1):
        name, desc = sk
        story.append(Paragraph(
            f"<b>{idx:02d} | {name}：</b>{desc}",
            styles["skill"]
        ))
    story.append(Spacer(1, 4))

    # ── 工作经历 ──
    story.extend(section_header("工作经历", styles))
    for wk in info["works"]:
        story.append(Paragraph(
            f"<b>{wk['time']}</b>　{wk['company']}　｜　<b>{wk['title']}</b>",
            styles["company"],
        ))
        if wk.get("desc"):
            story.append(Paragraph(wk["desc"], styles["body"]))
    story.append(Spacer(1, 4))

    # ── 项目经历 ──
    story.extend(section_header("项目经历", styles))
    for p in info["projects"]:
        proj_meta = (
            f"<b>{p['time']}</b>　｜　{p.get('position', '大数据开发工程师')}　｜　"
            f"技术栈：{p['tech']}"
        )
        story.append(Paragraph(p["name"], styles["proj_title"]))
        story.append(Paragraph(proj_meta, styles["proj_meta"]))
        story.append(Paragraph(f"■ 项目背景：{p['background']}", styles["body"]))
        story.append(Paragraph("■ 主要职责 / 成果：", styles["body"]))
        for bullet in p["responsibilities"]:
            story.append(Paragraph(f"　　• {bullet}", styles["body"]))
        story.append(Spacer(1, 4))

    # ── 自我评价 ──
    if info.get("self_eval"):
        story.extend(section_header("自我评价", styles))
        story.append(Paragraph(info["self_eval"], styles["body"]))

    doc.build(story)
    size_kb = path.stat().st_size // 1024
    print(f"✔ 生成: {filename:<10s} ({size_kb:>5d} KB)  {info['name']} · {info['tagline_short']}")


# ════════════════════════════════════════════
#  4 份模拟简历（参考曹/黄/许 大数据开发风格）
# ════════════════════════════════════════════

# -------- gr01：偏曹文栋风格 — 实时数仓 + Doris/Flink + 离线湖仓 --------
gr01 = dict(
    name="李子墨",
    tagline="实时数据开发 / 湖仓一体工程师 · 随时到岗",
    tagline_short="实时+离线数仓",
    phone="18829531140",
    email="lizimo_databricks@163.com",
    age=28, gender="男", years="6",
    school="武汉理工大学", degree="本科", location="湖北武汉",
    education=dict(
        time="2017.09 - 2021.06",
        school="武汉理工大学",
        major="计算机科学与技术",
        degree="统招全日制本科",
        honors="国家励志奖学金、优秀毕业生、数学建模省三等奖",
    ),
    skills=[
        ("关系型数据库与 SQL",
         "熟悉 MySQL / PostgreSQL / Oracle，具备复杂 SQL、索引优化、执行计划分析能力，独立支撑过亿级表性能调优。"),
        ("Hadoop 生态与数据仓库",
         "熟悉 HDFS / YARN / MapReduce / Hive 原理与生产调优，熟练使用 Hive SQL 与 Tez 引擎。"),
        ("实时计算与湖仓一体",
         "熟练使用 Spark / Flink 实时计算，了解 Doris / StarRocks / Iceberg，有 Flink SQL + Doris 实时报表落地经验。"),
        ("ETL 工具",
         "能使用 DataX / Sqoop / Flume / Kafka Connect 完成异构数据源全量、增量、CDC 采集。"),
        ("调度与监控",
         "熟练使用 Azkaban / DolphinScheduler 编排任务、配置告警与重试，保障数据任务按时稳定产出。"),
        ("Linux 与脚本",
         "熟悉 Linux 常用命令，具备 Shell / Python 脚本开发能力，完成数据抽取、质量校验、文件传输等自动化。"),
        ("数据可视化",
         "有 FineReport / DataV / Superset 报表开发经验，能独立完成看板开发、权限、发布全流程。"),
        ("数据建模与治理",
         "掌握 ODS-DWD-DWS-ADS 分层建模与维度建模（星型/雪花），了解数据治理、元数据管理方法论。"),
    ],
    works=[
        dict(time="2023.05 - 至今", company="云盛互娱科技股份有限公司",
             title="大数据开发工程师",
             desc="负责核心业务离线+实时数仓建设，承接游戏付费行为、登录留存、广告投放回收共 12 个主题域的数据生产。"),
        dict(time="2021.07 - 2023.04", company="数匠信息科技（武汉）有限公司",
             title="数据开发工程师",
             desc="参与电商 SaaS 平台离线数仓搭建、口径梳理、报表开发，服务 80+ 商家运营看板。"),
    ],
    projects=[
        dict(
            time="2024.03 - 2025.02",
            name="游戏实时运营看板（Flink + Doris 方案）",
            tech="Flink / Kafka / Doris / DataHub / DataV / Python",
            background="离线报表仅能 T+1 查看付费、留存，运营无法感知活动期实时回收与异常波动，急需构建实时大屏，支撑秒级告警与投放决策。",
            responsibilities=[
                "主导方案选型对比（Flink+Doris vs ClickHouse），基于人力成本与查询性能最终确定 Doris 做 ADS 层；",
                "基于 Flink CDC 采集 MySQL 业务库 Binlog 至 Kafka，完成实时 ODS→DWD 数据清洗、去重、宽表拼接；",
                "负责 18 张实时报表 ADS 层建模，包括实时 ARPU、LTV、7日留存、活动回收 ROI 等核心指标计算；",
                "使用 DataV 构建 3 个运营大屏，对 top 看板建立异常阈值并接入飞书告警；",
                "通过维表关联优化、Checkpoint 调参、Flink RocksDB StateBackend 优化，端到端平均延迟从 48s 降至 11s。",
            ]
        ),
        dict(
            time="2022.08 - 2023.03",
            name="电商 SaaS 离线数仓重构（Hive + DolphinScheduler）",
            tech="Hadoop / Hive / Spark SQL / DataX / DolphinScheduler / Superset",
            background="原数仓任务零散、口径不一致，运营数据可信度低，需要按 ODS-DWD-DWS-ADS 分层重构并统一指标口径。",
            responsibilities=[
                "梳理业务指标 90+ 个，完成指标字典、口径文档与 DWS 主题宽表设计；",
                "按用户、商品、订单、营销、店铺主题进行维度建模，构建 6 个累积型快照事实表与 8 张维度表；",
                "使用 DolphinScheduler 编排全链路 180+ 任务，设计重跑方案与依赖策略，保障凌晨 D+1 报表在 06:00 前产出；",
                "配合 DataX 完成 6 个业务库增量同步，落地日增量数据 3.2 亿条，处理成功率 ≥ 99.6%。",
            ]
        ),
    ],
    self_eval="6 年数据开发沉淀，具备 0→1 数仓搭建成败经验，既了解离线 Hive 生态也具备实时 Flink+Doris 落地能力。性格严谨、对数据准确性敏感，乐于和业务沟通拆解需求，主动承担线上值班与问题排查，希望加入高成长团队共同构建高可用的数据基础设施。",
)

# -------- gr02：偏黄学勤风格 — 商城数仓 + 性能优化 + 可视化 FineBI --------
gr02 = dict(
    name="陈予安",
    tagline="数据仓库工程师 / BI 报表开发 · 随时到岗",
    tagline_short="数仓+BI可视化",
    phone="17681240677",
    email="chenyuan_bi@126.com",
    age=26, gender="男", years="4",
    school="青岛工学院", degree="本科", location="广东深圳",
    education=dict(
        time="2018.09 - 2022.06",
        school="青岛工学院",
        major="软件工程（大数据方向）",
        degree="统招全日制本科",
        honors="校级一等奖学金、ACM 校赛银奖、三好学生",
    ),
    skills=[
        ("Hadoop 与 Hive 离线",
         "熟悉 Hadoop 原理与 Hive 底层执行机制，熟练使用 Hive / Spark SQL 实现离线计算。"),
        ("ETL 与调度工具",
         "熟练运用 Sqoop / DataX / Kettle 做 ETL 开发，熟悉 Azkaban / DolphinScheduler 调度使用。"),
        ("维度建模",
         "掌握维度建模理论，能按业务域划分主题、构建概念/逻辑/物理模型、拉链表/累积快照设计。"),
        ("BI 可视化",
         "熟练使用 FineReport / FineBI 实现报表与自助分析，复杂大屏、权限、发布流程经验丰富。"),
        ("数据库原理与优化",
         "熟悉 Oracle / MySQL 底层原理，参与过数据库性能调优、备份恢复、索引重构。"),
        ("PL/SQL 与存储过程",
         "能用 PL/SQL 编写复杂存储过程、函数、包实现数据加工。"),
        ("Shell / Python",
         "熟练编写 Shell 脚本实现自动化，使用 Python pandas 做数据探查与离线分析。"),
        ("问题抽象与协作",
         "逻辑思维清晰，能对实际问题做抽象建模，沟通协作主动、学习速度快。"),
    ],
    works=[
        dict(time="2022.07 - 至今", company="擎科生物科技（深圳）有限公司",
             title="大数据开发工程师 / BI 开发",
             desc="负责电商子公司科技邦商城的数仓建设与BI看板，承接供需、营收、用户、活动四大主题。"),
    ],
    projects=[
        dict(
            time="2023.09 - 2024.06",
            name="科技邦商城商品营收可视化大屏",
            tech="Hadoop / Hive / Oracle / Sqoop / Shell / FineBI",
            background="公司管理层希望实时掌握商品营收、订单、用户、渠道数据，支撑周会、月会决策与运营复盘。",
            responsibilities=[
                "与运营深度沟通后整理需求文档并完成数仓分层设计，按销售域/渠道域/会员域划分主题；",
                "使用 Sqoop 将业务 Oracle 数据迁移至 HDFS，Shell 脚本封装抽取并通过 Azkaban 调度；",
                "DWD 层贴近业务层做数据清洗、标准化，解决 Hive 数据倾斜（广播 join / 动态分区）；",
                "确认 DWS 主题建立方案，按业务需求加工 14 张 ADS 指标表；",
                "协助 BI 工程师在 FineBI 完成 7 块看板、20+ 报表组件，支撑决策层日常数据使用。",
            ]
        ),
        dict(
            time="2022.10 - 2023.08",
            name="科技邦供需平台专项性能优化",
            tech="Hadoop / Hive / Oracle / PLSQL / Sqoop / Kettle / FineReport",
            background="供需平台随着订单数据激增出现报表查询慢、Hive 任务超时、Oracle I/O 瓶颈等问题。",
            responsibilities=[
                "对平台进行全面性能盘点（SQL 运行时长 / 资源利用率 / 数据量增长曲线），定位关键瓶颈；",
                "重构 Oracle 索引与分区策略，关键查询平均时长从 38s 降至 4.2s；",
                "优化 Sqoop / Kettle 抽取流程，使用 merge + direct 模式，传输效率提升 47%；",
                "引入缓存层（Redis + 物化视图）减少重复计算，报表并发量由 30 QPS 提升至 120+ QPS；",
                "开展 PL/SQL 代码审查，消除冗余 cursor 与 8 处嵌套循环写法，整体批处理窗口缩短 35%。",
            ]
        ),
        dict(
            time="2022.03 - 2022.09",
            name="商城日志行为离线分析系统",
            tech="Hadoop / Hive / Sqoop / MySQL / FineBI",
            background="从埋点日志 + 业务数据推演用户留存率、沉默用户、新增设备等指标，辅助活动效果复盘。",
            responsibilities=[
                "负责埋点日志解析脚本开发，字段抽取、反爬清洗、非法设备过滤；",
                "按 ODS-DWD-DWS-ADS 分层设计，完成漏斗分析、留存率、GMV 等指标计算；",
                "输出每日用户画像宽表，接入活动运营做人群圈选，活动转化提升约 18%。",
            ]
        ),
    ],
    self_eval="4 年数据开发，兼具数仓建设与 BI 双栈能力，擅长从 0 到 1 构建企业级数据仓库与可视化体系。沟通能力强，能充分理解业务痛点并转化为数据方案。多次主导性能专项优化，对数据质量与指标口径一致性高度敏感。",
)

# -------- gr03：偏许剑鸿风格 — 金融数仓 + 风控 + 保险车险 + Oracle/PLSQL --------
gr03 = dict(
    name="周亦辰",
    tagline="金融大数据开发 / ETL 工程师 · 可接受出差",
    tagline_short="金融风控+保险数仓",
    phone="15921407813",
    email="zhouyichen_fin@163.com",
    age=28, gender="男", years="5",
    school="东莞理工学院", degree="本科", location="上海",
    education=dict(
        time="2017.09 - 2021.06",
        school="东莞理工学院",
        major="软件工程",
        degree="统招全日制本科",
        honors="CET-4、计算机二级、HarmonyOS 应用开发者高级认证",
    ),
    skills=[
        ("关系型数据库与 PL/SQL",
         "熟悉 Oracle / MySQL，精通 PL/SQL 存储过程、函数、包的编写与调优。"),
        ("Hadoop / Spark",
         "熟悉 HDFS / YARN / MapReduce / Spark，能以 Scala 编写 Spark 作业。"),
        ("ETL 工具",
         "熟练使用 Sqoop / Kettle / DataX，完成 Oracle / MySQL 到 Hive 的抽取与清洗。"),
        ("Hive SQL / Spark SQL",
         "熟练 Hive SQL / Spark SQL，具备 count(distinct)、join、数据倾斜等调优经验。"),
        ("数仓建模",
         "熟悉数据仓库建模流程与维度建模，参与过金融 3 大域（信贷/交易/客户）主题建模。"),
        ("脚本能力",
         "熟悉 Linux 命令，熟练 Scala / Python / Shell 脚本并完成自动化工单。"),
        ("调度工具",
         "熟悉 Azkaban / DolphinScheduler / XXL-JOB 等调度工具的使用与运维。"),
        ("报表与可视化",
         "熟练使用 FineReport 实现监管报表与高管看板。"),
    ],
    works=[
        dict(time="2023.05 - 至今", company="上海艾融软件股份有限公司",
             title="大数据开发工程师",
             desc="在银行端驻场，支撑信用卡风控账管系统与额度调升决策引擎。"),
        dict(time="2020.11 - 2023.04", company="深圳智企数字科技有限公司",
             title="大数据开发工程师",
             desc="参与保险 / 证券 / 银行等多行业客户的数仓交付与报表开发。"),
    ],
    projects=[
        dict(
            time="2023.06 - 2024.05",
            name="某银行信用卡风控账管决策系统",
            tech="Scala / Spark / XXL-JOB / Python / Yarn / Oracle",
            background="结合客户账单、逾期、卡核心评分等信息，做客户级汇总与预警，并对额度调升申请给出规则码与处置建议。",
            responsibilities=[
                "负责 DWS 客户行为宽表 Spark SQL 开发，覆盖最大逾期期数、近一年透支金额、近三月套现平均分等 35+ 核心指标；",
                "编写测试环境造数脚本，完成 3 轮 UAT 验证与对账，准确率通过客户行方验收；",
                "独立完成 5 个 Python 脚本用于规则命中明细抽取，支持行方业务排查；",
                "负责日常批跑监控、失败重跑、SLA 保障，批处理窗口稳定控制在 2.5 小时以内；",
                "协同上游信审、下游催收对齐指标口径，输出统一字典文档 2 份。",
            ]
        ),
        dict(
            time="2022.05 - 2023.03",
            name="云创空间商品营销数仓项目",
            tech="MySQL / Sqoop / HDFS / Shell / YARN / MapReduce / FineReport",
            background="采集埋点与业务数据，围绕用户、下单、活动等主题构建营销决策数据底座，支撑活动投放与效果归因。",
            responsibilities=[
                "与业务沟通指标口径并输出《指标字典 v1.2》；",
                "封装 Sqoop 抽取 SQL 到 Shell，按日从业务库 MySQL 同步至 HDFS；",
                "参与设备、商品主题维度建模，完成 ODS→DWD 解析与清洗；",
                "按日/月汇总构建设备/商品 DWS、DWT 主题宽表共 12 张；",
                "完成新增用户、留存率、商品销量排名等 16 个核心指标，报表通过 FineReport 发布。",
            ]
        ),
        dict(
            time="2021.08 - 2022.04",
            name="中华联合保险天津分公司车险数仓项目",
            tech="MySQL / DataX / Maxwell / Shell / Hadoop / Hive / DolphinScheduler / FineReport",
            background="对接总公司下发的车险数据，构建集中式车险数仓，支持车险分析报告与决策。",
            responsibilities=[
                "参与前期业务指标梳理，完成 8 大场景、42 项指标口径；",
                "使用 DataX + Maxwell 完成增量 CDC 数据从 MySQL 导入 Hive ODS；",
                "负责 DWD / DIM 交易域维度建模、事实表与维度表装载；",
                "独立完成 DWS / ADS 交易域指标开发，支持产品交易统计、城市交易统计、承保理赔看板。",
            ]
        ),
    ],
    self_eval="5 年金融 / 保险领域数据开发，熟悉行方交付流程、监管要求和指标口径管理，对风控、营销、交易三大域有较深沉淀。工作认真、抗压能力强，长期担任值班岗位，对 SLA、质量、合规问题零容忍。乐于沉淀文档、协助团队新人，擅长使用 FineReport 做结果可视化交付。",
)

# -------- gr04：复合型 — 数据湖 + 数据治理 + Python 自动化 + 指标平台，拓宽岗位覆盖面 --------
gr04 = dict(
    name="苏星辞",
    tagline="数据平台工程师 / 数据治理与湖仓架构 · 可接受短期出差",
    tagline_short="数据湖+治理+指标平台",
    phone="13520897164",
    email="suxingci_data@163.com",
    age=29, gender="男", years="7",
    school="南京邮电大学", degree="硕士", location="北京朝阳",
    education=dict(
        time="2016.09 - 2020.06",
        school="南京邮电大学",
        major="信息与计算科学（本） + 大数据技术（硕）",
        degree="硕士（保送本校）",
        honors="连续三学年一等学业奖学金、研究生国家奖学金、IEEE BigData 2019 Student Paper（共同作者）",
    ),
    skills=[
        ("湖仓架构与数据湖",
         "熟悉 HDFS / OSS / MinIO 对象存储作为数据湖底座，掌握 Hudi / Iceberg 表格式，支持 CDC 入湖与增量快照。"),
        ("计算引擎与 SQL 调优",
         "熟练使用 Spark / Flink / Presto / Trino，对 Catalyst / Flink Checkpoint / Presto 分片调优有实战经验。"),
        ("数据治理",
         "搭建过 DataHub + Apache Atlas 元数据管理体系，实施血缘、质量规则、数据分级与权限策略。"),
        ("指标平台",
         "主导过指标语义层设计，能基于 Cube + Druid + 自研 DSL 完成公司级统一指标平台建设（450+ 指标）。"),
        ("ETL / CDC / ELT",
         "熟悉 DataX / SeaTunnel / Flink CDC / Debezium，完成 MySQL / MongoDB / Kafka → 数仓全链路采集。"),
        ("调度与工作流",
         "熟练 Airflow / DolphinScheduler，能做 DAG 可视化、SLA 告警、回填（Backfill）与级联失败策略。"),
        ("脚本与工程化",
         "熟练 Python / PySpark / Scala / Shell；完成过 12 个数据工程脚手架与批量治理脚本的工程化。"),
        ("云原生与容器",
         "熟悉 Kubernetes 部署大数据组件（Spark on K8s、Flink on K8s），具备基础 Docker 镜像制作经验。"),
    ],
    works=[
        dict(time="2022.08 - 至今", company="中安信联科技集团",
             title="高级数据平台工程师",
             desc="负责公司数据中台升级（湖仓一体 + 指标平台），对接 4 条业务线的数仓与报表消费。"),
        dict(time="2020.07 - 2022.07", company="博睿数据（北京）有限公司",
             title="大数据开发工程师",
             desc="参与 APM 产品海量指标数据采集链路与多租户查询引擎优化。"),
    ],
    projects=[
        dict(
            time="2023.02 - 2024.09",
            name="湖仓一体数据中台升级（Hudi + Iceberg）",
            tech="Spark / Flink / Hudi / Iceberg / MinIO / Presto / Kafka / Airflow",
            background="原有 Hive 数仓无法高效支持 CDC 近实时入湖、ACID 写入、Schema 演进，无法支撑分钟级自助分析。",
            responsibilities=[
                "负责湖仓底座选型与试点：按场景拆分（事务型→Hudi、分析型→Iceberg），完成 4 条业务线 80+ 表的迁移；",
                "基于 Flink CDC + Schema Registry 构建统一 CDC 入湖链路，端到端延迟 < 90s，支持 Schema 自动演进；",
                "搭建 Presto + 统一 Hive Metastore 分析层，自助查询 P95 时长由 28s 降至 6.5s；",
                "完成权限、血缘、质量、生命周期管理 4 个治理模块落地，非法写入同比下降 73%；",
                "主导 Spark 相关参数与 Shuffle 调优，全月作业平均时长下降 29%，节省约 22% 的计算资源成本。",
            ]
        ),
        dict(
            time="2022.10 - 2023.07",
            name="公司级统一指标平台",
            tech="Cube / Druid / MySQL / ClickHouse / React + Go 自研前端 / dbt",
            background="指标分散在各业务看板，口径不一致、重复建设严重，领导要求建设统一指标平台。",
            responsibilities=[
                "牵头设计指标语义层 DSL，支持派生指标、复合指标、同比/环比、维度筛选等 20+ 语法；",
                "完成指标注册、审批、发布、下线全生命周期流程，支撑 450+ 指标统一管控；",
                "使用 ClickHouse + Druid 组合作为查询加速层，多维查询 P95 响应 < 2.2s；",
                "推广至 4 条业务线 120+ 用户，下线重复报表 60+，指标一致性问题工单清零。",
            ]
        ),
        dict(
            time="2021.03 - 2022.06",
            name="APM 海量指标查询优化（Druid + ClickHouse）",
            tech="Kafka / Flink / Druid / ClickHouse / Grafana / Go",
            background="APM 探针每日上报 30 亿指标点，原 InfluxDB 成本高、查询慢，需构建高并发低延迟的指标查询平台。",
            responsibilities=[
                "完成 Flink 预处理（聚合+降采样）→ Druid 写入链路，日均指标降为 3 亿；",
                "基于 ClickHouse 建立明细与聚合双层存储，支撑任意维度 1 年范围秒级查询；",
                "统一 Grafana 数据源插件，接入 180+ 监控大盘，查询平均耗时从 4.8s 降至 0.9s。",
            ]
        ),
    ],
    self_eval="7 年数据工程经验，对数据平台四大件（存储 / 计算 / 治理 / 可视化）均有独立设计与落地经验。既能深入底层做引擎调优，也能跳出技术视角做业务指标治理与成本优化。喜欢搭框架、写规范、做工程化，乐于带团队、沉淀最佳实践。期待加入追求长期技术价值的团队，一起把数据平台做得更稳、更快、更易用。",
)


if __name__ == "__main__":
    print(f"输出目录: {OUT_DIR}")
    print(f"字体: {CJK_FONT}\n")
    build_resume(gr01, "gr01.pdf")
    build_resume(gr02, "gr02.pdf")
    build_resume(gr03, "gr03.pdf")
    build_resume(gr04, "gr04.pdf")
    print("\n全部完成。请使用 PDF 阅读器检查中文渲染效果。")
