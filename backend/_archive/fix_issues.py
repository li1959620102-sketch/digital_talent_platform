"""
一次性修复脚本：
1. 删除知识库失败状态文件 (P7)
2. 新增20条测评题目 (P4)
3. 检查岗位学历要求取值 (P5调试)
4. 测试岗位分页 (P3调试)
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://root:password@localhost:3307/digital_talent?charset=utf8mb4"
engine = create_engine(DB_URL)

# ============================================================
# P7: 删除知识库失败状态文件
# ============================================================
print("=" * 80)
print("P7: 删除知识库失败状态文件")
print("=" * 80)

FAILED_FILE_CODES = [
    "KF1788168063528DDB0AA",
    "KF1788168028957058BCA",
]

codes_str = ",".join([f"'{c}'" for c in FAILED_FILE_CODES])

with engine.connect() as conn:
    rows = conn.execute(text(
        f"SELECT id, file_code, file_name, status FROM knowledge_files WHERE file_code IN ({codes_str})"
    )).fetchall()
    print(f"  找到 {len(rows)} 条失败文件:")
    for r in rows:
        print(f"    id={r[0]}, code={r[1]}, name={r[2]}, status={r[3]}")

    if rows:
        file_ids = [r[0] for r in rows]
        ids_str = ",".join([str(i) for i in file_ids])

        del_chunks = conn.execute(text(
            f"DELETE FROM knowledge_chunks WHERE file_id IN ({ids_str})"
        ))
        print(f"  删除关联 chunks: {del_chunks.rowcount} 行")

        del_files = conn.execute(text(
            f"DELETE FROM knowledge_files WHERE id IN ({ids_str})"
        ))
        print(f"  删除知识文件: {del_files.rowcount} 行")
        conn.commit()
        print("  删除完成")

# ============================================================
# P5调试: 检查岗位学历要求取值
# ============================================================
print()
print("=" * 80)
print("P5调试: 检查岗位学历要求取值")
print("=" * 80)

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT education_requirement, COUNT(*) as cnt FROM job_positions "
        "GROUP BY education_requirement ORDER BY cnt DESC"
    )).fetchall()
    for r in rows:
        print(f"  education_requirement='{r[0]}', count={r[1]}")

# ============================================================
# P3调试: 测试岗位分页
# ============================================================
print()
print("=" * 80)
print("P3调试: 测试岗位分页")
print("=" * 80)

with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM job_positions")).scalar()
    print(f"  岗位总数: {total}")

    for pg, ps in [(1, 10), (2, 10), (3, 10), (4, 10)]:
        offset = (pg - 1) * ps
        rows = conn.execute(text(
            f"SELECT id, position_code, position_name FROM job_positions "
            f"ORDER BY id LIMIT {ps} OFFSET {offset}"
        )).fetchall()
        print(f"  第{pg}页(page_size={ps}): {len(rows)}条")
        for r in rows[:3]:
            print(f"    id={r[0]}, code={r[1]}, name={r[2]}")
        if len(rows) > 3:
            print(f"    ... (共{len(rows)}条)")

# ============================================================
# P4: 新增20条测评题目
# ============================================================
print()
print("=" * 80)
print("P4: 新增20条测评题目")
print("=" * 80)

with engine.connect() as conn:
    existing = conn.execute(text("SELECT COUNT(*) FROM questions")).scalar()
    print(f"  现有题目数: {existing}")

if existing > 0:
    print("  已有题目，跳过新增")
else:
    ts = int(datetime.now().timestamp() * 1000)
    # 20条题目：10单选 + 5多选 + 5判断
    questions = [
        # ── 单选题 ──
        ("single_choice", "技术基础",
         "Python中以下哪个是不可变数据类型？",
         json.dumps({"A": "list", "B": "dict", "C": "tuple", "D": "set"}, ensure_ascii=False),
         "C", "tuple是不可变序列，list/dict/set都是可变的", 5, 1),
        ("single_choice", "数据库",
         "SQL中用于去重的关键字是？",
         json.dumps({"A": "UNIQUE", "B": "DISTINCT", "C": "GROUP BY", "D": "ORDER BY"}, ensure_ascii=False),
         "B", "DISTINCT用于SELECT结果去重", 5, 1),
        ("single_choice", "网络协议",
         "以下哪个不是HTTP标准请求方法？",
         json.dumps({"A": "GET", "B": "POST", "C": "SEND", "D": "DELETE"}, ensure_ascii=False),
         "C", "HTTP标准方法包括GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS，SEND不是", 5, 1),
        ("single_choice", "工具使用",
         "Git中撤销已暂存（staged）但未提交的文件，应使用哪个命令？",
         json.dumps({"A": "git checkout", "B": "git reset", "C": "git revert", "D": "git rm"}, ensure_ascii=False),
         "B", "git reset HEAD <file>可以将已暂存的文件移出暂存区", 5, 2),
        ("single_choice", "DevOps",
         "Docker容器与虚拟机的主要区别是？",
         json.dumps({"A": "容器需要完整OS", "B": "容器共享宿主机内核", "C": "虚拟机更轻量", "D": "容器不能联网"}, ensure_ascii=False),
         "B", "Docker容器共享宿主机内核，不需要完整OS", 5, 2),
        ("single_choice", "网络协议",
         "RESTful API中，HTTP状态码404表示？",
         json.dumps({"A": "服务器内部错误", "B": "请求成功", "C": "资源未找到", "D": "未授权"}, ensure_ascii=False),
         "C", "404 Not Found表示请求的资源不存在", 5, 1),
        ("single_choice", "技术基础",
         "Python中列表推导式 [x*2 for x in range(5)] 的结果是？",
         json.dumps({"A": "[0,1,2,3,4]", "B": "[0,2,4,6,8]", "C": "[2,4,6,8,10]", "D": "[1,2,3,4,5]"}, ensure_ascii=False),
         "B", "range(5)生成0-4，每个乘2得到[0,2,4,6,8]", 5, 2),
        ("single_choice", "数据分析",
         "以下哪个是Pandas中读取CSV文件的函数？",
         json.dumps({"A": "pandas.load_csv()", "B": "pandas.read_csv()", "C": "pandas.open_csv()", "D": "pandas.import_csv()"}, ensure_ascii=False),
         "B", "pandas.read_csv()是读取CSV的标准函数", 5, 1),
        ("single_choice", "机器学习",
         "在机器学习中，过拟合（Overfitting）是指？",
         json.dumps({"A": "模型在训练集表现差", "B": "模型在训练集好但测试集差", "C": "模型在所有数据上都差", "D": "模型训练速度慢"}, ensure_ascii=False),
         "B", "过拟合指模型过于复杂，在训练集表现好但测试集泛化能力差", 5, 2),
        ("single_choice", "DevOps",
         "Kubernetes中Deployment的主要作用是？",
         json.dumps({"A": "管理Pod副本和滚动更新", "B": "提供存储", "C": "网络路由", "D": "日志收集"}, ensure_ascii=False),
         "A", "Deployment管理Pod的副本数、滚动更新和回滚", 5, 2),
        # ── 多选题 ──
        ("multiple_choice", "技术基础",
         "以下哪些是Python的内置数据结构？（多选）",
         json.dumps({"A": "list", "B": "tuple", "C": "dict", "D": "DataFrame"}, ensure_ascii=False),
         "A,B,C", "list/tuple/dict是Python内置，DataFrame属于Pandas库", 10, 2),
        ("multiple_choice", "系统架构",
         "以下哪些属于微服务架构的优点？（多选）",
         json.dumps({"A": "独立部署", "B": "技术栈灵活", "C": "数据一致性简单", "D": "故障隔离"}, ensure_ascii=False),
         "A,B,D", "微服务独立部署、技术栈灵活、故障隔离，但数据一致性更复杂", 10, 3),
        ("multiple_choice", "数据库",
         "以下哪些是常见的NoSQL数据库？（多选）",
         json.dumps({"A": "MongoDB", "B": "Redis", "C": "MySQL", "D": "Cassandra"}, ensure_ascii=False),
         "A,B,D", "MongoDB(文档)/Redis(KV)/Cassandra(列族)是NoSQL，MySQL是关系型", 10, 2),
        ("multiple_choice", "项目管理",
         "敏捷开发中的核心价值观包括哪些？（多选）",
         json.dumps({"A": "个体互动高于流程工具", "B": "可工作软件高于详尽文档", "C": "客户合作高于合同谈判", "D": "严格遵循计划"}, ensure_ascii=False),
         "A,B,C", "敏捷宣言四条价值观，前三条是正向价值，D选项与之相反", 10, 3),
        ("multiple_choice", "数据分析",
         "数据仓库架构中常见的建模方式有哪些？（多选）",
         json.dumps({"A": "星型模型", "B": "雪花模型", "C": "第三范式", "D": "宽表模型"}, ensure_ascii=False),
         "A,B,D", "星型/雪花/宽表是数仓常见建模方式，3NF是OLTP建模", 10, 3),
        # ── 判断题 ──
        ("true_false", "技术基础",
         "Python中的GIL（全局解释器锁）保证了同一时刻只有一个线程执行Python字节码。",
         json.dumps({"A": "正确", "B": "错误"}, ensure_ascii=False),
         "A", "GIL确保同一时刻只有一个线程执行Python字节码", 5, 3),
        ("true_false", "数据库",
         "Redis是单线程的，因此无法处理高并发请求。",
         json.dumps({"A": "正确", "B": "错误"}, ensure_ascii=False),
         "B", "Redis核心是单线程但利用IO多路复用，可以处理高并发", 5, 3),
        ("true_false", "数据库",
         "在关系型数据库中，外键约束可以保证参照完整性。",
         json.dumps({"A": "正确", "B": "错误"}, ensure_ascii=False),
         "A", "外键约束确保子表外键值在父表中存在", 5, 2),
        ("true_false", "DevOps",
         "Kafka中的Partition数量不影响消费者并发度。",
         json.dumps({"A": "正确", "B": "错误"}, ensure_ascii=False),
         "B", "Kafka消费者并发度受Partition数量限制", 5, 3),
        ("true_false", "网络协议",
         "RESTful API必须使用JSON格式传输数据。",
         json.dumps({"A": "正确", "B": "错误"}, ensure_ascii=False),
         "B", "REST是架构风格，不限定数据格式", 5, 2),
    ]

    inserted = 0
    with engine.begin() as conn:
        for i, (qtype, category, content, options, answer, analysis, score, difficulty) in enumerate(questions):
            code = f"Q{ts}{i+1:04d}"
            conn.execute(text(
                "INSERT INTO questions (question_code, question_content, question_type, "
                "question_category, options, correct_answer, answer_analysis, score_value, difficulty, status, created_at) "
                "VALUES (:code, :content, :qtype, :category, :options, :answer, :analysis, :score, :difficulty, 'active', NOW())"
            ), {
                "code": code,
                "content": content,
                "qtype": qtype,
                "category": category,
                "options": options,
                "answer": answer,
                "analysis": analysis,
                "score": score,
                "difficulty": difficulty,
            })
            inserted += 1

    print(f"  成功插入 {inserted} 条题目")

    # 验证
    with engine.connect() as conn:
        final_count = conn.execute(text("SELECT COUNT(*) FROM questions")).scalar()
        print(f"  当前题目总数: {final_count}")
        rows = conn.execute(text(
            "SELECT question_type, COUNT(*) FROM questions GROUP BY question_type"
        )).fetchall()
        for r in rows:
            print(f"    type={r[0]}, count={r[1]}")

engine.dispose()
print()
print("=" * 80)
print("全部完成")
print("=" * 80)
