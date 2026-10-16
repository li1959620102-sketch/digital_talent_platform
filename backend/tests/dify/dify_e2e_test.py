#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dify E2E 端到端验证脚本（重导 YAML 后）。
流程：登录 → 用 Dify 中台调用 5 个 Agent 接口 → 验证返回结构。
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8003/api/v1"

# ── 1. 登录 ────────────────────────────────────────────────
print("=" * 60)
print("Step 1: 登录 admin/admin123")
print("=" * 60)
req = urllib.request.Request(
    f"{BASE}/auth/login",
    data=json.dumps({"username": "admin", "password": "admin123"}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        login_data = json.loads(resp.read().decode("utf-8"))
    token = login_data["data"]["access_token"]
    print(f"[OK] 登录成功，token 前20位: {token[:20]}...")
except Exception as e:
    print(f"[FAIL] 登录失败: {e}")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

def call(method, path, payload=None, timeout=120):
    url = f"{BASE}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return json.loads(body, errors="replace"), e.code
    except Exception as e:
        return {"error": str(e)}, 0

# ── 2. 获取一个人才 ID 和一个岗位 ID ────────────────────────
print("\n" + "=" * 60)
print("Step 2: 获取测试数据（人才 + 岗位）")
print("=" * 60)

talents, code = call("GET", "/talents?page=1&page_size=1")
if code == 200 and talents["data"]["total"] > 0:
    talent_id = talents["data"]["items"][0]["id"]
    print(f"[OK] 取到人才 id={talent_id}, name={talents['data']['items'][0].get('name','?')}")
else:
    print(f"⚠️ 人才列表获取异常: {talents}")
    talent_id = 1  # fallback

positions, code = call("GET", "/positions?page=1&page_size=1")
if code == 200 and positions["data"]["total"] > 0:
    position_id = positions["data"]["items"][0]["id"]
    print(f"[OK] 取到岗位 id={position_id}, name={positions['data']['items'][0].get('name','?')}")
else:
    print(f"⚠️ 岗位列表获取异常: {positions}")
    position_id = 1

# ── 3. 逐个 Agent 调用 ────────────────────────────────────
agents = [
    {
        "name": "档案解析 Agent",
        "path": "/agents/parse-resume",
        "method": "POST",
        "payload": {"file_path": "uploads/resume_44b28c2b84f1476da2f8e049c98702d0.pdf"},
    },
    {
        "name": "测评分析 Agent",
        "path": "/agents/assessment",
        "method": "POST",
        "payload": {"talent_id": talent_id},
    },
    {
        "name": "岗位匹配 Agent",
        "path": "/agents/matching",
        "method": "POST",
        "payload": {"position_id": position_id, "top_n": 3},
    },
    {
        "name": "培训赋能 Agent",
        "path": "/agents/training",
        "method": "POST",
        "payload": {"talent_id": talent_id},
    },
    {
        "name": "数据决策 Agent",
        "path": "/agents/data-analysis",
        "method": "POST",
        "payload": {"analysis_type": "structure"},
    },
]

results = []
for agent in agents:
    print(f"\n{'─' * 60}")
    print(f"Calling: {agent['name']}")
    print(f"{'─' * 60}")

    body, status = call(agent["method"], agent["path"], agent["payload"], timeout=120)

    passed = status == 200 and body.get("code") == 200
    result = {
        "name": agent["name"],
        "status": status,
        "code": body.get("code"),
        "passed": passed,
        "body_preview": json.dumps(body, ensure_ascii=False)[:300],
    }
    results.append(result)

    if passed:
        print(f"[OK] 通过 (code={body['code']}, msg={body.get('message','')})")
        data = body.get("data", {})
        if isinstance(data, dict):
            # 打印关键信息
            for k, v in data.items():
                if k in ("total_talents", "talent_id", "position_id", "success", "match_score"):
                    print(f"   {k} = {v}")
                elif k == "by_education":
                    print(f"   {k} = {v}")
    else:
        print(f"[FAIL] 未通过 (status={status}, code={body.get('code')})")
        print(f"   响应: {json.dumps(body, ensure_ascii=False)[:400]}")

# ── 4. 汇总 ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Dify E2E 验证结果汇总")
print("=" * 60)
passed_count = sum(1 for r in results if r["passed"])
total_count = len(results)
for r in results:
    icon = "[OK]" if r["passed"] else "[FAIL]"
    print(f"  {icon} {r['name']}: status={r['status']}, code={r['code']}")

print(f"\n总计: {passed_count}/{total_count} 通过")
sys.exit(0 if passed_count == total_count else 1)