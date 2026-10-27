#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实际调用上游脚本的 homeContent / searchContent / detailContent，验证脚本是否真能取到数据。

安全提示：本工具会执行第三方代码。请只在隔离环境（Docker / 虚拟机）中运行，
并确保进程环境里没有任何密钥（GITHUB_TOKEN 等）。脚本访问内网、回环、链路本地
地址会被拦截。

输出示例：
{
  "file": "某某影视.py",
  "import_ok": true,
  "home_ok": true,
  "search_ok": true,
  "detail_ok": true,
  "home_items": 24,
  "search_items": 20,
  "play_from": 3,
  "play_episodes": 36,
  "score": 3,
  "timeout": false,
  "error": null
}
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import update_api  # noqa: E402

RUNNER = Path(__file__).resolve().with_name("_spider_runner.py")
SHIM = Path(__file__).resolve().with_name("spider_shim")
DEFAULT_OUTPUT = ROOT / "reports" / "functional-report.json"


def clean_env(workdir: Path) -> dict[str, str]:
    """只保留运行必需变量，避免把 CI 密钥带进第三方代码。"""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(workdir),
        "TMPDIR": str(workdir),
        "TMP": str(workdir),
        "TEMP": str(workdir),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    # Windows 上缺少 SYSTEMROOT/WINDIR 会导致 ssl/socket 初始化失败；
    # 缺少 APPDATA 时 Python 找不到用户级 site-packages（本机依赖常装在那里）。
    for key in (
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
    ):
        value = os.environ.get(key)
        if value:
            env[key] = value
    # 让子进程沿用父进程能看到的依赖路径（含用户级 site-packages）。
    extra_path = os.pathsep.join(p for p in sys.path if p and os.path.isdir(p))
    if extra_path:
        env["PYTHONPATH"] = extra_path
    return {key: value for key, value in env.items() if value}


def make_limits(timeout: int) -> dict[str, int] | None:
    """把资源限制交给子进程自己设置，避免在多线程父进程里用 preexec_fn。"""
    if os.name != "posix":
        return None
    return {
        "cpu": timeout + 5,
        "memory": 2 * 1024 * 1024 * 1024,
        "fsize": 20 * 1024 * 1024,
        "nofile": 256,
    }


def kill_tree(process: subprocess.Popen) -> None:
    """超时后连同子孙进程一起结束；Windows 下 kill() 只能杀掉直接子进程。"""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                timeout=15,
            )
            return
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, AttributeError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def read_result(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def run_one(
    script: Path,
    workdir: Path,
    index: int,
    keyword: str,
    timeout: int,
) -> dict[str, Any]:
    job_path = workdir / "jobs" / f"{index}.json"
    result_path = workdir / "results" / f"{index}.json"
    payload = {
        "script": str(script),
        "name": script.name,
        "shim": str(SHIM),
        "result": str(result_path),
        "keyword": keyword,
        "limits": make_limits(timeout),
    }
    job_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    script_dir = workdir / "cwd" / str(index)
    script_dir.mkdir(parents=True, exist_ok=True)
    # -P：不把脚本目录/当前目录加进 sys.path（防止脚本目录里的同名模块被优先导入）；
    # 不用 -I，因为 -I 会连带禁用用户 site-packages，本机依赖常装在那里。
    command = [sys.executable, "-P", str(RUNNER), str(job_path)]
    started = time.time()
    timed_out = False
    stdout = ""
    stderr = ""
    try:
        process = subprocess.Popen(
            command,
            cwd=str(script_dir),
            env=clean_env(script_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(process)
            out, err = process.communicate()
        stdout = out.decode("utf-8", "replace")[-2000:]
        stderr = err.decode("utf-8", "replace")[-2000:]
    except Exception as exc:  # noqa: BLE001
        result = read_result(result_path) or {"file": script.name, "score": 0}
        result.update(
            timeout=False,
            elapsed=round(time.time() - started, 2),
            error=f"启动失败: {type(exc).__name__}: {exc}",
            stage="launch_failed",
        )
        return result

    result = read_result(result_path)
    if result is None:
        result = {
            "file": script.name,
            "import_ok": False,
            "init_ok": False,
            "home_ok": False,
            "search_ok": False,
            "detail_ok": False,
            "home_items": 0,
            "search_items": 0,
            "play_from": 0,
            "play_episodes": 0,
            "sample_play_url": "",
            "score": 0,
            "stage": "no_result",
            "elapsed": round(time.time() - started, 2),
            "error": (stderr or stdout or "子进程没有写出结果")[-500:],
        }
    result["timeout"] = timed_out
    if timed_out:
        result["stage"] = "timeout"
        result["error"] = (result.get("error") or "") + " [超时被杀]"
    return result


def collect_scripts(
    config: dict[str, Any],
    source_dir: Path | None,
    cache_dir: Path | None,
    limit: int,
) -> list[Path]:
    filenames = update_api.get_upstream_filenames(config, source_dir, None)
    if limit > 0:
        filenames = filenames[:limit]
    if source_dir is not None:
        return [source_dir / name for name in filenames]

    target = cache_dir or (Path(os.environ.get("TEMP", "/tmp")) / "tvbox-py-cache")
    target.mkdir(parents=True, exist_ok=True)
    missing = [name for name in filenames if not (target / name).is_file()]
    if missing:
        workers = int(config["request"]["download_workers"])
        print(f"下载脚本到缓存 {target}（{len(missing)} 个）...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(update_api.download_script, config, name, None): name
                for name in missing
            }
            done = 0
            for future in as_completed(futures):
                name = futures[future]
                try:
                    source, _ = future.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"  下载失败 {name}: {exc}")
                    continue
                (target / name).write_text(source, encoding="utf-8")
                done += 1
            print(f"  下载完成 {done}/{len(missing)}")
    return [target / name for name in filenames if (target / name).is_file()]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "score3": 0,
        "score2": 0,
        "score1": 0,
        "score0": 0,
        "timeout": 0,
        "import_failed": 0,
    }
    for row in rows:
        score = int(row.get("score") or 0)
        summary[f"score{min(score, 3)}"] += 1
        if row.get("timeout"):
            summary["timeout"] += 1
        if not row.get("import_ok"):
            summary["import_failed"] += 1
    return summary


def analyze_streams(
    rows: list[dict[str, Any]],
    scripts: list[Path],
    config: dict[str, Any],
    workers: int,
) -> dict[str, int]:
    """对拿到播放地址的脚本做二次分析：源类型 + 广告特征。"""
    import stream_check

    by_name = {path.name: path for path in scripts}
    request_cfg = config.get("request") or {}
    max_hosts = int(request_cfg.get("max_hosts_per_script") or 8)
    max_fallback = int(request_cfg.get("max_fallback_hosts") or 3)

    def site_hosts(name: str) -> list[str]:
        path = by_name.get(name)
        if path is None:
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            hosts, _tier = update_api.extract_hosts(source, max_hosts, max_fallback)
            return hosts
        except OSError:
            return []

    targets = [
        row
        for row in rows
        if row.get("stream_url") and int(row.get("stream_parse") or 0) == 0
    ]
    if not targets:
        return {}

    print(f"分析播放地址: {len(targets)} 个，并发 {workers}")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                stream_check.analyze_stream,
                row["stream_url"],
                site_hosts(str(row.get("file") or "")),
                None,
                12.0,
            ): row
            for row in targets
        }
        for future in as_completed(futures):
            row = futures[future]
            try:
                row["stream"] = future.result()
            except Exception as exc:  # noqa: BLE001
                row["stream"] = {"grade": "D", "error": f"{type(exc).__name__}: {exc}"}
            done += 1
            if done % 20 == 0 or done == len(futures):
                print(f"  已分析 {done}/{len(futures)}")

    summary: dict[str, int] = {}
    for row in rows:
        stream = row.get("stream") or {}
        grade = stream.get("grade") or "D"
        summary[grade] = summary.get(grade, 0) + 1
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="隔离执行上游 py 脚本，做功能校验")
    parser.add_argument("--config", default=str(update_api.DEFAULT_CONFIG_PATH))
    parser.add_argument("--source-dir", help="使用本地 py 目录，不下载")
    parser.add_argument("--cache-dir", help="脚本缓存目录，默认系统临时目录")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--keyword", help="搜索关键词，默认取配置")
    parser.add_argument("--timeout", type=int, help="单个脚本超时秒数")
    parser.add_argument("--workers", type=int, help="并发数")
    parser.add_argument("--stream-workers", type=int, help="播放地址分析并发数")
    parser.add_argument("--no-stream", action="store_true", help="不分析播放地址（跳过广告/源类型判断）")
    parser.add_argument("--limit", type=int, default=0, help="只测前 N 个脚本")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = update_api.load_config(Path(args.config))
    settings = config.get("functional") or {}
    keyword = args.keyword or str(settings.get("keyword") or "庆余年")
    timeout = int(args.timeout or settings.get("timeout") or 30)
    workers = int(args.workers or settings.get("workers") or 6)
    output = Path(args.output).resolve()
    source_dir = Path(args.source_dir).resolve() if args.source_dir else None
    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None

    scripts = collect_scripts(config, source_dir, cache_dir, args.limit)
    if not scripts:
        print("没有可测试的脚本", file=sys.stderr)
        return 1

    print(f"功能校验: {len(scripts)} 个脚本，并发 {workers}，单脚本超时 {timeout}s")
    workdir = Path(os.environ.get("TEMP", "/tmp")) / f"tvbox-func-{os.getpid()}"
    (workdir / "jobs").mkdir(parents=True, exist_ok=True)
    (workdir / "results").mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_one, script, workdir, index, keyword, timeout): script
            for index, script in enumerate(scripts)
        }
        for done, future in enumerate(as_completed(futures), 1):
            script = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = {"file": script.name, "score": 0, "error": repr(exc)}
            rows.append(row)
            if done % 20 == 0 or done == len(futures):
                print(f"  已测试 {done}/{len(futures)}")

    rows.sort(key=lambda row: str(row.get("file")))

    stream_summary: dict[str, int] = {}
    if not args.no_stream:
        stream_summary = analyze_streams(rows, scripts, config, args.stream_workers or 6)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "keyword": keyword,
        "timeout": timeout,
        "workers": workers,
        "total": len(rows),
        "summary": summarize(rows),
        "stream_summary": stream_summary,
        "scripts": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    update_api.write_json(output, report, "\n")

    summary = report["summary"]
    print(
        "结果: "
        f"3分 {summary['score3']}，2分 {summary['score2']}，"
        f"1分 {summary['score1']}，0分 {summary['score0']}，"
        f"超时 {summary['timeout']}，导入失败 {summary['import_failed']}"
    )
    if stream_summary:
        print(
            "源质量: "
            f"A 自营 {stream_summary.get('A', 0)}，"
            f"B 第三方 {stream_summary.get('B', 0)}，"
            f"C 搬运/解析 {stream_summary.get('C', 0)}，"
            f"D 无法验证 {stream_summary.get('D', 0)}"
        )
    print(f"报告: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
