# -*- coding: utf-8 -*-
"""
探测大模型是否支持关闭思考链（thinking）。

背景：application.yaml 里 custom-parameters.thinking.type=disabled 被 glm-5.2（ark coding 端点）
拒绝（400 InvalidParameter）。本脚本对每个候选模型逐一发最小请求，测三种关思考写法是否被接受，
并顺带探测「不传思考参数时模型是否默认输出 reasoning_content」。

用法：
  python probe_thinking.py                          # 用脚本内默认模型清单
  python probe_thinking.py -m glm-5.2,glm-4.6       # 指定模型
  python probe_thinking.py --base-url https://... --api-key xxx -m ...

判定说明：
  OK     端点接受该参数（HTTP 200）。是否真把思考关掉，看 reasoning 列：
         no（响应无 reasoning_content）= 思考确实关了；yes = 参数被忽略，仍在思考
  REJECT 端点拒绝该参数（4xx），错误摘要会打印出来
  FAIL   网络/超时等异常
输出列：模型 | baseline(不传参) | thinking:disabled | enable_thinking:false | baseline是否带reasoning
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"
# 默认取 application.yaml 里的 key，可用环境变量 SEE_ARK_KEY 或 --api-key 覆盖
DEFAULT_API_KEY = "ark-70179204-5484-4c58-bd3a-2077510f4acd-099e6"

# 默认探测清单：ark 上常见的思考开关候选（不存在的模型会得到 404/InvalidModel，属于探测结果之一）
DEFAULT_MODELS = [
    "glm-5.2",
    "glm-4.7",
    "glm-4.6",
    "doubao-seed-1.6",
    "doubao-seed-1.6-flash",
    "doubao-seed-1-6-250615",
]

PROMPT = "1+1等于几？直接给答案，不要解释。"


def call(base_url, api_key, model, extra_body, timeout):
    """发一次最小 chat completion，返回 (status, message_dict, error_summary)。"""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 128,
    }
    body.update(extra_body)
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return 200, data, None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")
            msg = json.loads(detail).get("error", {}).get("message", detail)
        except Exception:
            msg = str(e)
        return e.code, None, msg
    except Exception as e:  # 超时 / 连接失败
        return -1, None, str(e)


def has_reasoning(data):
    """响应里是否出现思考链字段（reasoning_content / reasoning）。"""
    if not data:
        return "-"
    msg = (data.get("choices") or [{}])[0].get("message", {})
    if msg.get("reasoning_content") or msg.get("reasoning"):
        return "yes"
    return "no"


def probe_variant(base_url, api_key, model, extra_body, label, timeout):
    """测一种写法，返回 (verdict, reasoning, note)。"""
    status, data, err = call(base_url, api_key, model, extra_body, timeout)
    if status == 200:
        return "OK", has_reasoning(data), ""
    if status > 0:
        note = err if len(err) <= 80 else err[:80] + "..."
        return "REJECT", "-", "%s %s" % (status, note)
    return "FAIL", "-", err[:80]


def main():
    ap = argparse.ArgumentParser(description="探测模型是否支持关闭思考链")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--api-key", default=DEFAULT_API_KEY,
                    help="默认读脚本内常量，可改环境变量 SEE_ARK_KEY")
    ap.add_argument("-m", "--models", default=",".join(DEFAULT_MODELS),
                    help="逗号分隔的模型名清单")
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()

    import os
    api_key = os.environ.get("SEE_ARK_KEY", args.api_key)
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    variants = [
        ("baseline", {}),                                  # 不传思考参数（对照）
        ("think:off", {"thinking": {"type": "disabled"}}),  # Anthropic/ark 风格
        ("qwen:off", {"enable_thinking": False}),           # Qwen/DashScope 风格
    ]

    print("端点: %s" % args.base_url)
    print("模型数: %d，每个模型发 3 次最小请求（max_tokens=128）\n" % len(models))

    header = ("%-28s %-14s %-14s %-14s" %
              ("model", "thinking:off", "enable_think:off", "base_reason"))
    print(header)
    print("-" * len(header))

    for model in models:
        cells, notes = [], []
        base_reason = "-"
        for label, body in variants:
            verdict, reasoning, note = probe_variant(
                args.base_url, api_key, model, body, label, args.timeout)
            if label == "baseline":
                base_reason = reasoning  # 对照列：不传思考参数时是否默认输出思考链
            else:
                cells.append(verdict + ("/" + reasoning if reasoning != "-" else ""))
            if note:
                notes.append("  [%s] %s" % (label, note))
        print("%-28s %-14s %-14s %-14s" %
              (model, cells[0], cells[1], base_reason))
        for n in notes:
            print(n)

    print("""
判读：
  thinking:off 列为 OK       -> 恢复 application.yaml 里注释的 custom-parameters 即可关思考
  OK 但 base_reason=yes      -> 参数被接受但可能没生效，关思考后需再核对 reasoning_content
  全列 REJECT InvalidModel   -> 该端点没有此模型，从清单里剔除
""")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
