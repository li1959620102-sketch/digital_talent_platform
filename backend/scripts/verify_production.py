"""生产部署验收脚本。

用法：
    python scripts/verify_production.py --base-url http://127.0.0.1:8000

脚本只做只读检查，不会创建、修改或删除业务数据。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def request_json(url: str, timeout: float) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"body": body}
        return exc.code, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 数字化人才平台生产只读验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    checks = [("存活探针", "/health"), ("严格就绪探针", "/health/ready?strict=true")]
    failed = False
    for name, path in checks:
        try:
            status, payload = request_json(base + path, args.timeout)
            ok = status == 200 and payload.get("status") in {"healthy", "ready"}
            print(f"{'PASS' if ok else 'FAIL'} {name}: HTTP {status} {json.dumps(payload, ensure_ascii=False)}")
            failed = failed or not ok
        except Exception as exc:
            print(f"FAIL {name}: {exc}")
            failed = True

    if failed:
        print("生产验收失败：请先修复上述依赖或配置，再接收外部流量。")
        return 1
    print("生产验收通过：核心数据库、缓存、向量库、对象存储和模型链路均已就绪。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
