"""
测试 QA 问答客户问题清单
从 docs/QA问答_客户问题清单.md 提取问题并测试
"""
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# 问题列表（从文档手动提取）
QUESTIONS = [
    # 场景 A：产品价值与适用场景
    {"id": 1, "scenario": "A-产品价值", "question": "ChatBI 能为我们业务带来什么具体收益？有没有行业内的成功案例？"},
    {"id": 2, "scenario": "A-产品价值", "question": "对零售/制造/金融等不同行业，默认支持的典型场景有哪些？"},
    {"id": 3, "scenario": "A-产品价值", "question": "如果没有现成知识库，只用现有 PPT/文档，能多快搭出可用问答？"},

    # 场景 B：功能与体验
    {"id": 4, "scenario": "B-功能体验", "question": "用户可以通过哪些入口提问（Web、移动、钉钉/企业微信、内嵌组件）？"},
    {"id": 5, "scenario": "B-功能体验", "question": "支持多轮对话和追问吗？能否引用来源页号或原文片段？"},
    {"id": 6, "scenario": "B-功能体验", "question": "对模糊问题或拼写错误（中英文混输）系统如何处理？"},

    # 场景 C：数据安全与合规
    {"id": 7, "scenario": "C-安全合规", "question": "我们的数据会不会上传到第三方？默认的数据存储位置在哪里？"},
    {"id": 8, "scenario": "C-安全合规", "question": "是否支持私有化部署或 VPC 隔离？密钥与访问控制怎么做？"},
    {"id": 9, "scenario": "C-安全合规", "question": "敏感字段（如客户姓名、合同金额）能否自动脱敏？日志里会不会留存明文？"},

    # 场景 D：集成与上线
    {"id": 10, "scenario": "D-集成上线", "question": "和现有知识库/文档管理/CRM/ERP 如何集成？有无标准 API 或 SDK？"},
    {"id": 11, "scenario": "D-集成上线", "question": "知识库更新后，向量索引多久能同步？是否需要停机重建？"},
    {"id": 12, "scenario": "D-集成上线", "question": "前端样式可以自定义吗？支持多语言界面和问答吗？"},

    # 场景 E：成本与 ROI
    {"id": 13, "scenario": "E-成本ROI", "question": "计费方式是什么（按调用量/席位/并发）？有没有最低采购量或试用期？"},
    {"id": 14, "scenario": "E-成本ROI", "question": "平均每次问答的模型成本是多少？缓存能节省多少费用？"},
    {"id": 15, "scenario": "E-成本ROI", "question": "需要投入多少人力维护？上线到稳定运行的典型周期是多久？"},

    # 场景 F：性能与可靠性
    {"id": 16, "scenario": "F-性能可靠", "question": "单次问答的典型响应时间是多少？高峰期会不会变慢？"},
    {"id": 17, "scenario": "F-性能可靠", "question": "断网或第三方模型不可用时，系统如何降级？会影响在线用户吗？"},
    {"id": 18, "scenario": "F-性能可靠", "question": "有哪些可观测指标（命中率、延迟、错误率）和告警方式？"},

    # 场景 G：运维与支持
    {"id": 19, "scenario": "G-运维支持", "question": "遇到回答不准时，业务团队如何自助调优？有无可视化的反馈或标注工具？"},
    {"id": 20, "scenario": "G-运维支持", "question": "提供哪些支持服务（SLA、响应时间、值班方式）？升级迭代的节奏和变更通知渠道是什么？"},
]

def run_qa_query(question: str, project: str = "ChatBI", top_k: int = 8, top_n: int = 5, tau: float = 0.5) -> Dict[str, Any]:
    """运行单个 QA 查询"""
    cmd = [
        "python", "-m", "src.scripts.qa_cli",
        "-q", question,
        "-p", project,
        "--config", "config/settings.yaml",
        "--top-k", str(top_k),
        "--top-n", str(top_n),
        "--tau", str(tau)
    ]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            encoding='utf-8'
        )
        elapsed = time.time() - start_time

        # 解析输出
        output = result.stdout
        cache_hit = "[cache hit" in output.lower()
        cache_level = None
        if cache_hit:
            match = re.search(r'\[cache hit/(\w+)\]', output, re.IGNORECASE)
            if match:
                cache_level = match.group(1)

        return {
            "success": result.returncode == 0,
            "elapsed_seconds": round(elapsed, 2),
            "cache_hit": cache_hit,
            "cache_level": cache_level,
            "output": output,
            "error": result.stderr if result.returncode != 0 else None,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "elapsed_seconds": 60.0,
            "cache_hit": False,
            "cache_level": None,
            "output": None,
            "error": "Timeout after 60 seconds",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "elapsed_seconds": time.time() - start_time,
            "cache_hit": False,
            "cache_level": None,
            "output": None,
            "error": str(e),
            "returncode": -1
        }

def main():
    """运行所有测试问题"""
    print(f"开始测试 {len(QUESTIONS)} 个问题...")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"配置: project=ChatBI, top_k=8, top_n=5, tau=0.5\n")

    results = []

    for i, q in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] 场景 {q['scenario']} - 问题 {q['id']}")
        print(f"问题: {q['question']}")

        result = run_qa_query(q['question'])

        test_result = {
            "question_id": q['id'],
            "scenario": q['scenario'],
            "question": q['question'],
            "timestamp": datetime.now().isoformat(),
            "config": {
                "project": "ChatBI",
                "top_k": 8,
                "top_n": 5,
                "tau": 0.5
            },
            **result
        }

        results.append(test_result)

        # 打印简要结果
        status = "✓" if result['success'] else "✗"
        cache_info = f" [缓存命中/{result['cache_level']}]" if result['cache_hit'] else ""
        print(f"结果: {status} {result['elapsed_seconds']}s{cache_info}\n")

        # 避免请求过快
        time.sleep(1)

    # 保存结果
    output_dir = Path("tests/qa_test_results")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"qa_test_{timestamp}.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_run": {
                "timestamp": datetime.now().isoformat(),
                "total_questions": len(QUESTIONS),
                "config": {"project": "ChatBI", "top_k": 8, "top_n": 5, "tau": 0.5}
            },
            "results": results,
            "summary": {
                "total": len(results),
                "success": sum(1 for r in results if r['success']),
                "failed": sum(1 for r in results if not r['success']),
                "cache_hits": sum(1 for r in results if r['cache_hit']),
                "avg_elapsed": round(sum(r['elapsed_seconds'] for r in results) / len(results), 2)
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"\n测试完成！结果已保存到: {output_file}")

    # 打印汇总
    summary = {
        "总问题数": len(results),
        "成功": sum(1 for r in results if r['success']),
        "失败": sum(1 for r in results if not r['success']),
        "缓存命中": sum(1 for r in results if r['cache_hit']),
        "平均耗时": f"{sum(r['elapsed_seconds'] for r in results) / len(results):.2f}s"
    }

    print("\n=== 测试汇总 ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
