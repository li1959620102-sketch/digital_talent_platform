# -*- coding: utf-8 -*-
"""
Dify 5 大智能体端到端验证脚本（P1 第4项：YAML 重导入后跑通）

链路：本脚本 → Dify /v1/workflows/run (Bearer App Key)
      → Dify Workflow 内部 HTTP 调后端 /api/v1/agents/* (Bearer DIFY_BACKEND_TOKEN)
      → 后端 Agent 执行（本地 LangGraph + SiliconFlow + Milvus）
      → Dify LLM 节点（阿里百炼 qwen3.7-max）加工报告
      → 返回 {status, outputs}

证据落盘：backend/_dify_workflows_test_result.json
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（脚本在 tests/dify/，需上溯到 backend/ 目录）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # tests/dify/ → tests/ → backend/
load_dotenv(BACKEND_DIR / ".env", override=False)

# 从环境变量读 5 个 App Key + API base
import os
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://127.0.0.1:80/v1").rstrip("/")
APP_KEYS = {
    "resume":         os.getenv("DIFY_APP_KEY_RESUME", ""),
    "assessment":     os.getenv("DIFY_APP_KEY_ASSESSMENT", ""),
    "matching":       os.getenv("DIFY_APP_KEY_MATCHING", ""),
    "training":       os.getenv("DIFY_APP_KEY_TRAINING", ""),
    "data_decision":  os.getenv("DIFY_APP_KEY_DATA_DECISION", ""),
}

# 5 个 Workflow 的 inputs（用真实/示例数据触发后端 Agent）
SAMPLE_RESUME = """
张明，男，35岁，本科毕业，计算机科学与技术专业。
联系方式：13800138000，邮箱：zhangming@example.com
现任公司：字节跳动科技有限公司，职位：高级前端工程师，工作年限：10年。
技能：React, TypeScript, Vue, Node.js, Webpack, 性能优化, 团队管理。
项目经验：主导字节内部 ERP 系统前端重构，团队 8 人，性能提升 40%。
"""

WORKFLOWS = [
    {
        "agent": "resume",
        "name": "档案解析智能体",
        "inputs": {"resume_text": SAMPLE_RESUME, "file_name": "zhangming_resume.txt"},
        "output_key": "resume_report",
    },
    {
        "agent": "assessment",
        "name": "测评分析智能体",
        "inputs": {"talent_id": "1", "assessment_result_id": "1"},
        "output_key": "assessment_report",
    },
    {
        "agent": "matching",
        "name": "岗位匹配智能体",
        "inputs": {"talent_id": "1"},
        "output_key": "match_report",
    },
    {
        "agent": "training",
        "name": "培训赋能智能体",
        "inputs": {"talent_id": "1"},
        "output_key": "training_report",
    },
    {
        "agent": "data_decision",
        "name": "数据决策智能体",
        "inputs": {"analysis_type": "structure"},
        "output_key": "structure_result",
    },
]


def call_dify_workflow(api_key: str, inputs: dict, timeout: int = 180) -> dict:
    """调用 Dify /v1/workflows/run，返回完整响应。"""
    url = f"{DIFY_API_BASE}/workflows/run"
    payload = {
        "inputs": inputs,
        "response_mode": "blocking",
        "user": "dify-workflows-test",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"_http_error": e.code, "_body": body[:500]}
    except Exception as e:
        return {"_exception": str(e)}


def main():
    print(f"=" * 70)
    print(f"Dify 5 大智能体端到端验证")
    print(f"API Base: {DIFY_API_BASE}")
    print(f"App Keys: " + ", ".join(f"{a}={'set' if k else 'MISSING'}" for a, k in APP_KEYS.items()))
    print(f"=" * 70)

    results = []
    for wf in WORKFLOWS:
        agent, name, inputs, out_key = wf["agent"], wf["name"], wf["inputs"], wf["output_key"]
        api_key = APP_KEYS.get(agent, "")
        print(f"\n[{agent}] {name}")
        print(f"  inputs: {inputs}")
        if not api_key:
            print(f"  ✗ 跳过：App Key 未配置")
            results.append({"agent": agent, "name": name, "status": "skip_no_key",
                            "inputs": inputs, "error": "App Key 未配置"})
            continue

        t0 = time.time()
        resp = call_dify_workflow(api_key, inputs, timeout=180)
        elapsed = round(time.time() - t0, 2)

        if "_http_error" in resp or "_exception" in resp:
            print(f"  ✗ 调用失败 ({elapsed}s): {resp}")
            results.append({"agent": agent, "name": name, "status": "fail",
                            "inputs": inputs, "elapsed_s": elapsed, "error": resp})
            continue

        # Dify workflow 响应：{task_id, workflow_run_id, data: {id, workflow_id, status, outputs, ...}}
        data = resp.get("data", {})
        run_status = data.get("status", "unknown")
        outputs = data.get("outputs", {})
        error_msg = data.get("error", "")
        # 提取报告文本
        report_text = outputs.get(out_key) or outputs.get("text") or ""

        ok = run_status == "succeeded" and bool(report_text)
        mark = "✓" if ok else "✗"
        print(f"  {mark} status={run_status} elapsed={elapsed}s")
        print(f"  outputs keys: {list(outputs.keys())}")
        if report_text:
            preview = report_text[:200].replace("\n", " ")
            print(f"  report preview: {preview}...")
        if error_msg:
            print(f"  error: {error_msg[:300]}")

        results.append({
            "agent": agent, "name": name, "status": "pass" if ok else "fail",
            "run_status": run_status, "elapsed_s": elapsed,
            "inputs": inputs, "outputs_keys": list(outputs.keys()),
            "report_preview": report_text[:500] if report_text else "",
            "error": error_msg[:500] if error_msg else "",
            "raw_data_id": data.get("id", ""),
        })

    # 汇总
    passed = sum(1 for r in results if r["status"] == "pass")
    total = len(results)
    print(f"\n{'=' * 70}")
    print(f"汇总: {passed}/{total} 通过")
    for r in results:
        mark = "✓" if r["status"] == "pass" else "✗"
        elapsed = r.get("elapsed_s", "?")
        print(f"  {mark} [{r['agent']}] {r['name']} ({r['status']}, {elapsed}s)")
        if r["status"] != "pass" and r.get("error"):
            err = r['error']
            err_str = json.dumps(err, ensure_ascii=False)[:200] if isinstance(err, dict) else str(err)[:200]
            print(f"      error: {err_str}")

    # 落盘
    out_path = BACKEND_DIR / "_dify_workflows_test_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "api_base": DIFY_API_BASE,
            "app_keys_configured": {a: bool(k) for a, k in APP_KEYS.items()},
            "summary": {"passed": passed, "total": total},
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n证据落盘: {out_path}")


if __name__ == "__main__":
    main()
