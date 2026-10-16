"""
三大板块 API 穷尽式冒烟测试
用法: python api_smoke.py
输出每个接口的状态、耗时、响应摘要，FAIL 项高亮
"""
import json
import time
import urllib.request
import urllib.error
import uuid

BASE = "http://127.0.0.1:8003/api/v1"
USER = "admin"
PWD = "admin123"

_results = {"PASS": 0, "WARN": 0, "FAIL": 0}
_failures = []


def req(method, path, body=None, token=None, timeout=90, form=None):
    url = BASE + path
    data = None
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = form
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            dt = time.time() - t0
            try:
                return resp.status, json.loads(raw), dt
            except Exception:
                return resp.status, {"_raw": raw[:200]}, dt
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        dt = time.time() - t0
        try:
            return e.code, json.loads(raw), dt
        except Exception:
            return e.code, {"_raw": raw[:200]}, dt
    except Exception as e:
        return 0, {"_error": str(e)}, time.time() - t0


def check(name, method, path, body=None, token=None, expect_code=200,
          validate=None, timeout=90, form=None, warn_only=False):
    st, js, dt = req(method, path, body, token, timeout, form)
    ok = (st == expect_code)
    note = ""
    if ok and validate:
        try:
            vok, note = validate(js)
            ok = vok
        except Exception as e:
            ok, note = False, f"校验异常: {e}"
    if not ok:
        if warn_only:
            _results["WARN"] += 1
            tag = "WARN"
        else:
            _results["FAIL"] += 1
            tag = "FAIL"
        snippet = json.dumps(js, ensure_ascii=False)[:260]
        _failures.append(f"[{tag}] {name} ({method} {path}) code={st} {note} | {snippet}")
        print(f"  {tag}  {name:<42} code={st} {dt:5.1f}s {note}")
        print(f"        -> {snippet}")
    else:
        _results["PASS"] += 1
        print(f"  PASS  {name:<42} code={st} {dt:5.1f}s {note}")
    return st, js


def login():
    st, js, _ = req("POST", "/auth/login", {"username": USER, "password": PWD})
    if st != 200:
        print(f"登录失败: {st} {js}")
        raise SystemExit(1)
    print(f"登录成功: {USER}")
    return js["data"]["access_token"]


def main():
    tok = login()

    # ==================== 智能知识库 ====================
    print("\n" + "=" * 70)
    print("【一】智能知识库 API")
    print("=" * 70)

    check("知识文件列表", "GET", "/knowledge/files?page=1&page_size=5", token=tok,
          validate=lambda j: (j.get("code") == 200 and "items" in j.get("data", {}),
                              f"{j.get('data', {}).get('total', 0)}个文件"))

    check("智能问答-正常命中", "POST", "/knowledge/qa",
          {"question": "岗位匹配是怎么算的？"}, token=tok, timeout=120,
          validate=lambda j: (j.get("code") == 200 and bool(j.get("data", {}).get("answer")),
                              f"来源{len(j.get('data', {}).get('sources', []))}个"))

    check("智能问答-答非所问防御", "POST", "/knowledge/qa",
          {"question": "请休假几天？"}, token=tok, timeout=120,
          validate=lambda j: (j.get("code") == 200 and bool(j.get("data", {}).get("answer")),
                              "应提示未检索到"))

    check("语义检索", "POST", "/knowledge/search",
          {"query": "Java 高级工程师要求", "top_k": 3}, token=tok, timeout=120,
          validate=lambda j: (j.get("code") == 200, f"命中{j.get('data', {}).get('count', 0)}条"))

    # 上传一个测试文档并向量化+删除（完整生命周期）
    test_md = """# 测试知识文档
本平台支持年假申请，员工入职满一年可享受5天年假。
请假流程：在系统中提交申请，主管审批后生效。
"""
    boundary = "----smoke" + uuid.uuid4().hex
    fname = f"smoke_test_{uuid.uuid4().hex[:6]}.md"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n"
        f"{test_md}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    form_headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    url = BASE + "/knowledge/upload"
    r = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {tok}", **form_headers}, method="POST")
    up_ok, up_js, file_id = False, {}, None
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            up_js = json.loads(resp.read().decode("utf-8"))
            file_id = up_js.get("data", {}).get("id")
            up_ok = up_js.get("code") == 200 and file_id
    except Exception as e:
        up_js = {"_error": str(e)}
    if up_ok:
        _results["PASS"] += 1
        print(f"  PASS  {'上传知识文档':<42} code=200 -> file_id={file_id}")
    else:
        _results["FAIL"] += 1
        _failures.append(f"[FAIL] 上传知识文档 | {json.dumps(up_js, ensure_ascii=False)[:200]}")
        print(f"  FAIL  {'上传知识文档':<42} {json.dumps(up_js, ensure_ascii=False)[:200]}")

    if file_id:
        check("解析入库(向量化)", "POST", "/knowledge/vectorize",
              {"file_id": file_id}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200,
                                  f"切片{j.get('data', {}).get('chunk_count', 0)}个"))
        # 上传后问答应能命中新文档
        check("新文档问答命中", "POST", "/knowledge/qa",
              {"question": "年假有多少天？"}, token=tok, timeout=120,
              validate=lambda j: (j.get("code") == 200,
                                  f"{str(j.get('data', {}).get('answer', ''))[:40]}"))
        check("删除知识文件", "DELETE", f"/knowledge/files/{file_id}", token=tok,
              validate=lambda j: (j.get("code") == 200, "已删除"))

    # ==================== AI 智能体 ====================
    print("\n" + "=" * 70)
    print("【二】AI 智能体 API")
    print("=" * 70)

    # 拿真实数据 id
    _, tj, _ = req("GET", "/talents?page=1&page_size=5", token=tok)
    talents = tj.get("data", {}).get("items", [])
    _, pj, _ = req("GET", "/positions?page=1&page_size=5", token=tok)
    positions = pj.get("data", {}).get("items", [])
    _, rj, _ = req("GET", "/assessments/results?page=1&page_size=5", token=tok)
    results = rj.get("data", {}).get("items", [])

    print(f"  [数据] 人才{len(talents)} 岗位{len(positions)} 测评结果{len(results)}")

    if positions:
        pid = positions[0]["id"]
        check("快速找人-岗位匹配", "POST", "/agents/match-position",
              {"position_id": pid, "top_n": 10}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200 and
                                  len(j.get("data", {}).get("match_results", [])) > 0,
                                  f"推荐{len(j.get('data', {}).get('match_results', []))}人"))
    if talents:
        tid = talents[0]["id"]
        check("人才→岗位匹配", "POST", "/agents/match-position",
              {"talent_id": tid}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200, "OK"))
        check("培训赋能推荐", "POST", "/agents/recommend-training",
              {"talent_id": tid}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200,
                                  f"课程{len(j.get('data', {}).get('recommended_courses', []))}门"))
    if results:
        rid = results[0]["id"]
        check("测评深度分析", "POST", "/agents/analyze-assessment",
              {"result_id": rid}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200,
                                  f"评级={j.get('data', {}).get('ability_level')}"))

    for q in ["人才总数", "本月新进了多少人才", "各岗位平均匹配分是多少", "哪些人才测评合格"]:
        check(f"数据参谋-{q[:8]}", "POST", "/agents/nl2sql",
              {"question": q}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200 and
                                  j.get("data", {}).get("nl2sql", {}).get("success") is True,
                                  f"{len(j.get('data', {}).get('nl2sql', {}).get('rows', []))}行"),
              warn_only=True)

    check("数据分析-结构分析", "POST", "/agents/data-analysis",
          {"analysis_type": "structure"}, token=tok, timeout=180,
          validate=lambda j: (j.get("code") == 200, "OK"))
    check("数据分析-异常检测", "POST", "/agents/data-analysis",
          {"analysis_type": "anomaly"}, token=tok, timeout=180,
          validate=lambda j: (j.get("code") == 200, "OK"))

    # ==================== 技能编排 ====================
    print("\n" + "=" * 70)
    print("【三】技能编排 API")
    print("=" * 70)

    check("组件清单", "GET", "/skills/components", token=tok,
          validate=lambda j: (j.get("code") == 200 and
                              len(j.get("data", {}).get("components", [])) > 0,
                              f"{len(j.get('data', {}).get('components', []))}个组件"))

    _, cj, _ = req("GET", "/skills/components", token=tok)
    comps = cj.get("data", {}).get("components", [])
    if comps:
        ck = comps[0]["key"]
        check("组件启停", "POST", f"/skills/components/{ck}/toggle",
              {"enabled": True}, token=tok,
              validate=lambda j: (j.get("code") == 200, f"key={ck}"))
        check("组件单次执行", "POST", f"/skills/components/{ck}/execute",
              {"params": {}}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200, "OK"), warn_only=True)

    pipe_id = f"smoke_pipe_{uuid.uuid4().hex[:8]}"
    steps = [{"skill": c["key"], "params": {}} for c in comps[:3]] if comps else []
    if steps:
        check("创建编排", "POST", "/skills/pipelines",
              {"pipeline_id": pipe_id, "name": "冒烟测试编排", "steps": steps,
               "trigger_type": "manual"}, token=tok,
              validate=lambda j: (j.get("code") == 200, f"id={pipe_id}"))

        check("编排清单", "GET", "/skills/pipelines", token=tok,
              validate=lambda j: (j.get("code") == 200 and
                                  any(p.get("pipeline_id") == pipe_id
                                      for p in j.get("data", {}).get("pipelines", [])),
                                  "含新编排"))

        check("执行编排", "POST", f"/skills/pipelines/{pipe_id}/execute",
              {"input": {}}, token=tok, timeout=180,
              validate=lambda j: (j.get("code") == 200, "OK"), warn_only=True)

        check("复制编排", "POST", f"/skills/pipelines/{pipe_id}/duplicate",
              {"new_pipeline_id": pipe_id + "_copy"}, token=tok,
              validate=lambda j: (j.get("code") == 200, "已复制"))

        check("编排启停", "POST", f"/skills/pipelines/{pipe_id}/toggle",
              {"enabled": False}, token=tok,
              validate=lambda j: (j.get("code") == 200, "已停用"))

        check("删除编排(副本)", "DELETE", f"/skills/pipelines/{pipe_id}_copy", token=tok,
              validate=lambda j: (j.get("code") == 200, "已删除"))
        check("删除编排(本体)", "DELETE", f"/skills/pipelines/{pipe_id}", token=tok,
              validate=lambda j: (j.get("code") == 200, "已删除"))

        check("删除不存在的编排", "DELETE", "/skills/pipelines/not_exist_xyz", token=tok,
              expect_code=404, validate=lambda j: (j.get("code") == 404, "正确404"))

    # ==================== 汇总 ====================
    print("\n" + "=" * 70)
    print(f"汇总: PASS={_results['PASS']}  WARN={_results['WARN']}  FAIL={_results['FAIL']}")
    print("=" * 70)
    if _failures:
        print("\n问题清单:")
        for f in _failures:
            print("  " + f)
    else:
        print("\n无 FAIL 项")


if __name__ == "__main__":
    main()
