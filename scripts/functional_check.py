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
import hashlib
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
DEFAULT_CACHE = ROOT / "reports" / "functional-cache.json"


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


# ---------------------------------------------------------------------------
# P1 增量缓存：上游脚本没变（sha256 一致）且上次结果「干净」的源，复用上次的
# 功能字段 + 线路分析，跳过子进程和逐线路重测。每 2 轮强制重测一次，避免
# 服务端悄悄劣化而永远被旧结果掩盖。线路 URL 逐集带 token 会过期，但 update_api
# 只用 line_streams 的 stream 判定、lines 只取长度，复用过期的 URL 字符串无害。
# ---------------------------------------------------------------------------

# 复用的结果必须干净：连续 2 轮（跨一复用）强制重测，防止坏源靠旧结果一直留存。
REUSE_MAX_AGE_ROUNDS = 2


def load_cache(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"round": 0, "entries": {}}
    if not isinstance(data, dict):
        return {"round": 0, "entries": {}}
    data.setdefault("round", 0)
    data.setdefault("entries", {})
    return data


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    update_api.write_json(path, cache, "\n")


def source_hash(script: Path) -> str:
    try:
        data = script.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()


def line_clean(stream: dict[str, Any], config: dict[str, Any]) -> bool:
    """一条线路采样是否干净：没有 4xx、广告、低码率、慢速（未知的按干净处理）。"""
    status = int(stream.get("status") or 0)
    if status >= 400:
        return False
    if int(stream.get("ad_score") or 0) >= 3:
        return False
    kind = str(stream.get("kind") or "")
    if kind not in update_api.VIDEO_KINDS:
        return True  # 非视频（解析/页面/未知）不参与码率判定
    bitrate = int(stream.get("bitrate_kbps") or 0)
    if bitrate <= 0:
        return True  # 没测到码率，未知，不动
    limit = stream_bitrate_limit(stream, config)
    if bitrate < limit:
        return False
    min_speed = float((config.get("quality") or {}).get("min_speed_ratio") or 0)
    speed = float(stream.get("speed_ratio") or 0)
    if min_speed > 0 and speed > 0 and speed < min_speed:
        return False
    return True


def stream_bitrate_limit(stream: dict[str, Any], config: dict[str, Any]) -> float:
    """按配置计算一条采样的有效码率下限（含 bpp 校正）。"""
    quality_cfg = config.get("quality") or {}
    min_kbps = float(quality_cfg.get("min_bitrate_kbps") or 0)
    min_bpp = float(quality_cfg.get("min_bpp") or 0)
    thresholds = dict(update_api.DEFAULT_BITRATE_THRESHOLDS)
    thresholds.update(quality_cfg.get("bitrate_thresholds") or {})
    limit = update_api.resolution_threshold(stream, min_kbps, thresholds)
    if min_bpp > 0 and stream.get("width") and stream.get("height"):
        limit = max(
            limit,
            min_bpp
            * int(stream["width"])
            * int(stream["height"])
            * update_api.stream_fps(stream)
            / 1000.0,
        )
    return limit


def line_critical(stream: dict[str, Any], config: dict[str, Any]) -> bool:
    """线路采样是否落在「临界区」，需要第 2 集二次确认。

    两种情况需要复测：
    - **4xx/5xx**：单集 token 过期是 403/404 误报（华谊 K蓝光某集 403、换集就 200），
      一次采样判死会误伤，用第 2 集确认线路是否真的不通。
    - **码率/速度落在阈值 ±10%**：单集波动（某集恰好是低码率转码）会让一次采样
      误判成低质，用第 2 集区分「线路真的差」和「只是这一集差」。
    """
    if int(stream.get("status") or 0) >= 400:
        return True
    kind = str(stream.get("kind") or "")
    if kind not in update_api.VIDEO_KINDS:
        return False
    bitrate = int(stream.get("bitrate_kbps") or 0)
    if bitrate > 0:
        limit = stream_bitrate_limit(stream, config)
        if limit > 0 and abs(bitrate - limit) / limit <= 0.10:
            return True
    min_speed = float((config.get("quality") or {}).get("min_speed_ratio") or 0)
    speed = float(stream.get("speed_ratio") or 0)
    if min_speed > 0 and speed > 0 and abs(speed - min_speed) / min_speed <= 0.10:
        return True
    return False


def result_clean(row: dict[str, Any], config: dict[str, Any]) -> bool:
    """整个结果是否干净：至少有一条线路分析结果，且每条都达标。"""
    streams = row.get("line_streams") or []
    if not streams:
        return False  # 没有分析结果的不缓存（便宜，且避免漏检）
    return all(line_clean((entry.get("stream") or {}), config) for entry in streams)


def reusable_from_cache(
    script: Path, entry: dict[str, Any], config: dict[str, Any], round_num: int
) -> bool:
    """缓存结果是否可复用：脚本没变、上次分析干净、且未超过强制重测周期。"""
    if not isinstance(entry, dict):
        return False
    if entry.get("sha256") != source_hash(script):
        return False
    last = int(entry.get("last_analyzed_round") or 0)
    if last <= 0 or round_num - last >= REUSE_MAX_AGE_ROUNDS:
        return False
    return result_clean(entry.get("result") or {}, config)


def run_one(
    script: Path,
    workdir: Path,
    index: int,
    keyword: str,
    timeout: int,
    adult_probe: list[str] | None = None,
    max_lines: int = 4,
) -> dict[str, Any]:
    job_path = workdir / "jobs" / f"{index}.json"
    result_path = workdir / "results" / f"{index}.json"
    payload = {
        "script": str(script),
        "name": script.name,
        "shim": str(SHIM),
        "result": str(result_path),
        "keyword": keyword,
        "timeout": timeout,
        "adult_probe": adult_probe or [],
        "max_lines": max_lines,
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
    all_names = list(filenames)
    if limit > 0:
        filenames = filenames[:limit]
    if source_dir is not None:
        return [source_dir / name for name in filenames]

    target = cache_dir or (Path(os.environ.get("TEMP", "/tmp")) / "tvbox-py-cache")
    target.mkdir(parents=True, exist_ok=True)
    # 上游已删除的脚本要同步清掉，否则 update_api --source-dir 会带上过期文件。
    wanted = set(all_names)
    stale = 0
    for path in target.glob("*.py"):
        if path.name not in wanted:
            try:
                path.unlink()
                stale += 1
            except OSError:
                pass
    if stale:
        print(f"缓存清理 {stale} 个已下线的脚本")
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


def better_stream(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    """两样本取更好的一条作判定流，避免单集波动把好线路误判成低质。

    优先看码率（更高更好），再比速度比，最后比等级；未知（0/空）按不参与比较。
    返回更优的样本 dict；两者等价（或都不可比）时返回 None 表示维持原样。
    """
    def rank(stream: dict[str, Any]) -> tuple[float, float, int]:
        bitrate = float(stream.get("bitrate_kbps") or 0)
        speed = float(stream.get("speed_ratio") or 0)
        grade = str(stream.get("grade") or "").upper()
        return (bitrate, speed, {"A": 3, "B": 2, "C": 1, "D": 0}.get(grade, -1))

    ra = rank(a)
    rb = rank(b)
    if ra == rb:
        return None
    # 有码率数据的那方优先：码率更高的更好；都没码率时比速度。
    if ra[0] > 0 or rb[0] > 0:
        if ra[0] > rb[0]:
            return a
        if rb[0] > ra[0]:
            return b
    if ra[1] > 0 or rb[1] > 0:
        if ra[1] > rb[1]:
            return a
        if rb[1] > ra[1]:
            return b
    if ra[2] != rb[2]:
        return a if ra[2] > rb[2] else b
    return None


def analyze_streams(
    rows: list[dict[str, Any]],
    scripts: list[Path],
    config: dict[str, Any],
    workers: int,
    skip: set[str] | None = None,
) -> dict[str, int]:
    """对拿到播放地址的脚本做二次分析：源类型 + 广告特征 + 码率。

    每条线路各取第一集分析（上限 quality.max_lines），结果写进 line_streams；
    stream 仍保留第一条线路的结果，兼容旧报告和等级判定。
    skip 里的文件名跳过（复用缓存结果，已有 line_streams/stream）。
    """
    import stream_check

    stream_check.AD_HOSTS = tuple(
        str(h) for h in ((config.get("filters") or {}).get("ad_hosts") or []) if str(h).strip()
    )

    skip = skip or set()
    by_name = {path.name: path for path in scripts}
    request_cfg = config.get("request") or {}
    max_hosts = int(request_cfg.get("max_hosts_per_script") or 8)
    max_fallback = int(request_cfg.get("max_fallback_hosts") or 3)
    max_lines = int((config.get("quality") or {}).get("max_lines") or 4)

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

    jobs: list[tuple[dict[str, Any], int, str, str, str, list[str]]] = []
    for row in rows:
        if str(row.get("file") or "") in skip:
            continue
        picked: list[tuple[int, str, str, str]] = []
        for index, line in enumerate((row.get("lines") or [])[:max_lines]):
            url = str(line.get("url") or "")
            if not url:
                continue
            try:
                parse = int(line.get("parse") or 0)
            except (TypeError, ValueError):
                parse = -1
            if parse != 0:
                continue
            picked.append(
                (index, str(line.get("flag") or ""), url, str(line.get("alt_url") or ""))
            )
        if not picked:
            url = str(row.get("stream_url") or "")
            if url and int(row.get("stream_parse") or 0) == 0:
                picked = [(0, str(row.get("play_flag") or ""), url, "")]
        if not picked:
            continue
        hosts = site_hosts(str(row.get("file") or ""))
        row["line_streams"] = []
        for index, flag, url, alt_url in picked:
            jobs.append((row, index, flag, url, alt_url, hosts))

    if not jobs:
        return {}

    sources = len({id(job[0]) for job in jobs})
    print(f"分析播放地址: {len(jobs)} 条线路（{sources} 个源），并发 {workers}")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                stream_check.analyze_stream,
                url,
                hosts,
                None,
                12.0,
            ): (row, index, flag, url)
            for row, index, flag, url, alt_url, hosts in jobs
        }
        for future in as_completed(futures):
            row, index, flag, url = futures[future]
            try:
                stream = future.result()
            except Exception as exc:  # noqa: BLE001
                stream = {"grade": "D", "error": f"{type(exc).__name__}: {exc}"}
            row["line_streams"].append(
                {
                    "flag": flag,
                    "index": index,
                    "url": url[:300],
                    "stream": stream,
                }
            )
            # 第一条线路的结果同时写进 stream，保持原有等级判定口径。
            if index == 0 and not row.get("stream"):
                row["stream"] = stream
            done += 1
            if done % 20 == 0 or done == len(futures):
                print(f"  已分析 {done}/{len(futures)}")

    # N2 单轮临界线路复测：码率/速度落在阈值 ±10% 的线路，用第 2 集再测一次。
    # 单集波动（某集恰好是低码率转码）会让一次采样误判成低质；二次采样能区分
    # 「线路真的差」（两集都差）和「只是这一集差」（另一集达标）。取两样本中
    # 更好的作为判定流，避免误删好线路。
    retest_jobs: list[tuple[dict[str, Any], int, str, str, list[str]]] = []
    for row in rows:
        if str(row.get("file") or "") in skip:
            continue
        for entry in row.get("line_streams") or []:
            index = int(entry.get("index") or -1)
            lines = row.get("lines") or []
            if index < 0 or index >= len(lines):
                continue
            alt_url = str(lines[index].get("alt_url") or "")
            if not alt_url:
                continue
            stream = entry.get("stream") or {}
            if not line_critical(stream, config):
                continue
            hosts = site_hosts(str(row.get("file") or ""))
            retest_jobs.append((row, index, str(entry.get("flag") or ""), alt_url, hosts))

    if retest_jobs:
        print(f"  临界线路复测: {len(retest_jobs)} 条（阈值 ±10% 内，用第 2 集确认）")
        retest_done = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    stream_check.analyze_stream,
                    url,
                    hosts,
                    None,
                    12.0,
                ): (row, index, flag)
                for row, index, flag, url, hosts in retest_jobs
            }
            for future in as_completed(futures):
                row, index, flag = futures[future]
                try:
                    alt_stream = future.result()
                except Exception as exc:  # noqa: BLE001
                    alt_stream = {"grade": "D", "error": f"{type(exc).__name__}: {exc}"}
                for entry in row.get("line_streams") or []:
                    if int(entry.get("index") or -1) == index:
                        entry["alt_url"] = (row.get("lines") or [])[index].get("alt_url", "")[:300]
                        entry["alt_stream"] = alt_stream
                        # 取两样本中更好的一条作判定：任一集达标，线路就不算差。
                        better = better_stream(entry.get("stream") or {}, alt_stream)
                        if better is not None:
                            entry["stream"] = better
                        entry["retested"] = True
                        break
                retest_done += 1
                if retest_done % 20 == 0 or retest_done == len(futures):
                    print(f"    已复测 {retest_done}/{len(futures)}")

    for row in rows:
        lines = row.get("line_streams")
        if lines:
            row["line_streams"] = sorted(lines, key=lambda item: item.get("index", 0))

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
    parser.add_argument("--cache", help="增量缓存路径（默认 reports/functional-cache.json）")
    parser.add_argument("--no-cache", action="store_true", help="禁用增量缓存，全量重测")
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
    probes = [str(k) for k in (settings.get("adult_probe_keywords") or []) if str(k).strip()]
    max_lines = int((config.get("quality") or {}).get("max_lines") or 4)

    # P1 增量缓存：脚本没变且上次结果干净的源复用，跳过子进程与逐线路重测。
    use_cache = not args.no_cache and not args.no_stream
    cache: dict[str, Any] = {"round": 0, "entries": {}}
    reuse: set[str] = set()
    if use_cache:
        cache_path = (
            Path(args.cache).resolve()
            if args.cache
            else DEFAULT_CACHE
        )
        cache = load_cache(cache_path)
        cache["round"] = int(cache.get("round") or 0) + 1
        round_num = int(cache["round"])
        entries = cache.setdefault("entries", {})
        for script in scripts:
            if reusable_from_cache(script, entries.get(script.name), config, round_num):
                reuse.add(script.name)
        if reuse:
            print(f"增量缓存: 复用 {len(reuse)} 个未变化且结果干净的源（每 {REUSE_MAX_AGE_ROUNDS} 轮强制重测）")
    else:
        cache_path = None
        round_num = 0

    to_run = [script for script in scripts if script.name not in reuse]
    print(f"功能校验: {len(scripts)} 个脚本（重测 {len(to_run)} + 复用 {len(reuse)}），并发 {workers}，单脚本超时 {timeout}s")
    workdir = Path(os.environ.get("TEMP", "/tmp")) / f"tvbox-func-{os.getpid()}"
    (workdir / "jobs").mkdir(parents=True, exist_ok=True)
    (workdir / "results").mkdir(parents=True, exist_ok=True)

    fresh: dict[str, dict[str, Any]] = {}
    if to_run:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    run_one, script, workdir, index, keyword, timeout, probes, max_lines
                ): script
                for index, script in enumerate(to_run)
            }
            for done, future in enumerate(as_completed(futures), 1):
                script = futures[future]
                try:
                    row = future.result()
                except Exception as exc:  # noqa: BLE001
                    row = {"file": script.name, "score": 0, "error": repr(exc)}
                fresh[script.name] = row
                if done % 20 == 0 or done == len(futures):
                    print(f"  已测试 {done}/{len(futures)}")

    for script in scripts:
        if script.name in reuse:
            entry = cache["entries"][script.name]
            row = dict(entry.get("result") or {})
            row["file"] = script.name
            rows.append(row)
        else:
            rows.append(fresh[script.name])

    rows.sort(key=lambda row: str(row.get("file")))

    stream_summary: dict[str, int] = {}
    if not args.no_stream:
        stream_workers = int(
            args.stream_workers or settings.get("stream_workers") or 12
        )
        stream_summary = analyze_streams(rows, scripts, config, stream_workers, skip=reuse)

    # 保存增量缓存：本轮重测的源写入结果并记录分析轮次；复用的源不更新（保持强制重测周期）。
    if use_cache:
        entries = cache.setdefault("entries", {})
        wanted = {script.name for script in scripts}
        for name in list(entries):
            if name not in wanted:
                del entries[name]
        for row in rows:
            name = str(row.get("file") or "")
            if not name or name in reuse:
                continue
            try:
                script = next(s for s in scripts if s.name == name)
                hash_value = source_hash(script)
            except StopIteration:
                hash_value = ""
            entries[name] = {
                "sha256": hash_value,
                "last_analyzed_round": round_num,
                "result": row,
            }
        try:
            save_cache(cache_path, cache)
            print(f"增量缓存已更新: {cache_path}（{len(entries)} 个源）")
        except OSError as exc:  # 只读挂载（CI 的 /work:ro）等场景写不了就跳过
            print(f"增量缓存写入失败（跳过，不影响结果）: {exc}", file=sys.stderr)

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
