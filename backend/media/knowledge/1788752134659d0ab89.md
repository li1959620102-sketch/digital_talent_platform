# Dify Workflow 编排与自定义 AI Agent 指南

> 版本：v1.0 · 更新日期：2026-09 · 适用角色：super_admin / admin / 开发者

## 一、AI 架构总览

本平台 AI 能力分为 **6 大业务 Agent** + **1 个 RAG 检索层** + **1 个 Dify Workflow 中台** + **2 种 LLM 策略**，采用「业务代码不直接写 Prompt，全部沉淀到 Dify YAML」的原则：

```
前端页面
  ↓ HTTP
后端 FastAPI（app/api/v1/* + app/agents/*）
  ↓ dify_adapter.py
Dify Workflow（dify_chatflows/*.yaml）
  ↓ 
LLM 策略路由（llm_factory.py → ollama / silicon_flow）
  ├─ Ollama (本地 qwen3:1.7b / bge-m3)
  └─ SiliconFlow (云端 DeepSeek-V4-Flash)
Milvus 向量数据库 ← 检索增强 (RAG)
PgSQL 数据分析库 ← NL2SQL
```

- **Dify_APP_MODE = workflow**：所有 Agent 通过 Dify Workflow 调用，不使用 Chatflow
- **Llm_Strategy 可配置**：`ollama`（本地，隐私优先）或 `silicon_flow`（云端，精度优先），切换无需改代码
- **阿里百炼已弃用**：旧 `.env` 中 `DASHSCOPE_API_KEY` 等项已注释，不再接入

## 二、6 大业务 Agent 说明

### 2.1 Agent 目录与 YAML 映射

| 序号 | Python Agent | Dify YAML | 核心功能 | 典型输入 | 典型输出 |
|------|-------------|-----------|---------|---------|---------|
| 01 | resume_parser_agent.py | 01_档案解析智能体.yaml | PDF/Word 简历 → 结构化 JSON | 简历文件 Base64 + 文件名 | {name, education, skills, projects...} |
| 02 | assessment_agent.py | 02_测评分析智能体.yaml | 答题记录 → 能力分析报告 | {user_id, answers[]} | 雷达图数据 + 文字点评 |
| 03 | matching_agent.py | 03_岗位匹配智能体.yaml | 岗位+人才池 → TopN 推荐 | {position_id, top_n} | [{talent_id, score, reason}...] |
| 04 | training_agent.py | 04_培训赋能智能体.yaml | 人才标签 → 个性化课程推荐 | {talent_id, plan_id} | [{course_id, priority, reason}...] |
| 05 | data_decision_agent.py | 05_数据决策智能体.yaml | 自然语言 → PgSQL NL2SQL | "Q3 各部门招聘完成率？" | {sql, result_table, chart_config} |
| 06 | （knowledge 模块） | RAG 内置流程 | 知识文档切片 + 问答 | 用户问题 | {answer, references[]} |

### 2.2 自定义 Agent 步骤

1. **在 Dify 控制台新建 Workflow**
   - 画布上拖拽节点：`开始 → 知识检索(可选) → LLM → 结束`
   - 输入变量命名：如 `resume_text`, `position_id`, `question`
   - 输出变量命名：如 `result_json`, `analysis_text`
   - 开启 **流式返回** 视业务需要

2. **导出 YAML**：Dify → 工作流 → 导出 → 保存为 `NN_名称.yaml`，放入 `backend/dify_chatflows/`

3. **写 Python Agent Wrapper**（放到 `app/agents/xxx_agent.py`）
   ```python
   # 模板（摘自 resume_parser_agent 的最小实现）
   from app.services.dify_adapter import DifyAdapter
   
   class ResumeParserAgent:
       def __init__(self):
           self.dify = DifyAdapter()
           self.workflow_id = "resume_parser_v1"  # 与 Dify YAML name 对应
       
       async def parse(self, file_bytes: bytes, filename: str) -> dict:
           payload = {"inputs": {"filename": filename, "file_b64": to_b64(file_bytes)}}
           return await self.dify.run_workflow(self.workflow_id, payload)
   ```

4. **注册 API 路由**：在 `app/api/v1/agent.py` 新增 `POST /agents/{id}/run`，或新建专用路由

5. **加回归测试**：在 `tests/dify/dify_workflows_test.py` 追加 test case，确保输出字段与预期 schema 一致

## 三、Dify Workflow 最佳实践

### 3.1 Prompt 工程要点
- 所有 Prompt 首行必须包含 **角色**：`你是一名资深的人力资源专家...`
- 输出强制 **JSON Schema**：在 Prompt 结尾写「返回 JSON，字段名严格为 xxx，不要任何 Markdown」
- 对不确定的信息返回 `null`，不要编造：`若无法确认，则将 skills 字段置为 []`

### 3.2 稳定性保护
- Dify 调用端 `dify_adapter.py` 自带 **3 次重试 + 指数退避**（默认 2s/4s/8s）
- 所有 Agent 结果必须经过 `json_utils.safe_parse_json` 二次清洗，防止 LLM 输出 ```json ``` 包裹
- 长文本（>8K 字）先本地切片 + 摘要，再送 Dify，避免 token 超限

### 3.3 健康度监控
每个 Agent 维护以下 3 指标：
```
成功调用率（≥ 95% 正常，<90% 告警）
平均延迟（p95 < 10s 正常，>30s 告警）
结果有效率（解析成功率，空字段占比 > 20% 告警）
```
管理员可在「AI 智能体中心」页面查看 7 日趋势。

## 四、知识库 / RAG 切分策略

| 策略名 | 适用文档 | 切片方式 | 元数据 |
|--------|---------|---------|--------|
| jieba_chunking | 中文长文（制度、手册） | 按段落 + 句子边界，chunk_size=512 | {title, category, page} |
| fixed_size_chunk | 代码/配置 | 定长 1024，重叠 128 | {extension, lang} |
| structured_chunk | Excel/CSV/多维表 | 按行 + 表头注入 | {columns, row_index} |

向量化模型：`bge-m3:latest`（维度 1024），存储集合：`knowledge_base`。

## 五、故障排查

| 现象 | 常见根因 | 排查命令 |
|------|---------|---------|
| Agent 全部返回 timeout | Dify 服务未启动/端口错 | `curl http://{DIFY_HOST}/v1/ping` |
| 个别 Agent 500 | YAML 更新后未重新导入 | 在 Dify 控制台重新 import 对应 YAML |
| 返回结果非 JSON | Prompt 未约束格式 | 在 Dify 端直接试运行，查看原始输出 |
| 知识库命中率低 | 切片过大/停用词多 | 调小 chunk_size，检查 Jieba 词典是否包含业务词汇 |
| Ollama 速度慢 | 机器 CPU 弱 | 切 strategy = silicon_flow |

---

*配套：`backend/dify_chatflows/*.yaml` 为全部 Agent 的可导入 YAML，执行 `tests/dify/dify_workflows_test.py` 即可一键跑通 P1 级冒烟。*
