#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在本机（Windows 服务器 / Linux）跑完整流程，替代 GitHub Actions 定时任务。

流程：
1. git pull --rebase（尽力而为，失败不影响生成）；
2. 可选：functional_check.py 功能校验（默认关闭，见 README 的安全说明）；
3. update_api.py 拉取脚本、校验 host、重建 接口.json；
4. 有变化就提交并推送（失败会重试，仍失败则保留提交，下次运行再推）。

用法：
    python scripts/run_local.py                 # 校验 + 生成 + 推送
    python scripts/run_local.py --dry-run       # 只校验，不写文件、不推送
    python scripts/run_local.py --functional    # 额外跑功能校验（会执行第三方代码）
    python scripts/run_local.py --no-push       # 只生成，不提交推送
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LOG_DIR = ROOT / "logs"
OUTPUT = ROOT / "接口.json"
SPIDER_DIR = ROOT / "脚本"
FUNCTIONAL_REPORT = ROOT / "reports" / "functional-report.json"
# 功能校验下载好的脚本缓存，生成阶段直接复用，避免重复下载 200+ 个文件。
SCRIPT_CACHE = Path(tempfile.gettempdir()) / "tvbox-py-cache"


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


class Logger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(path, "a", encoding="utf-8")
        self.path = path

    def write(self, text: str) -> None:
        self.handle.write(text)
        self.handle.flush()
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (UnicodeEncodeError, ValueError):
            sys.stdout.write(text.encode("ascii", "replace").decode("ascii"))

    def close(self) -> None:
        self.handle.close()


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def run_step(logger: Logger, title: str, command: list[str], cwd: Path = ROOT) -> int:
    logger.write(f"\n$ {' '.join(command)}\n")
    started = time.time()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        logger.write(f"[{title}] 找不到命令: {command[0]}\n")
        return 127

    assert process.stdout is not None
    for line in process.stdout:
        logger.write(line)
    code = process.wait()
    logger.write(f"[{title}] 退出码 {code}，耗时 {time.time() - started:.1f}s\n")
    return code


def git_output(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env(),
        )
        return result.stdout.strip()
    except OSError:
        return ""


def git(*args: str) -> int:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env(),
        )
    except OSError:
        return 127
    if result.returncode != 0:
        sys.stdout.write((result.stderr or result.stdout)[-800:])
    return result.returncode


def pull(logger: Logger) -> None:
    if git("rev-parse", "--git-dir") != 0:
        logger.write("不是 git 仓库，跳过 pull/push\n")
        return
    logger.write("\n拉取远端最新提交（失败忽略）...\n")
    if git("pull", "--rebase", "--autostash") != 0:
        # rebase 中断会留下状态，先恢复干净再继续生成。
        git("rebase", "--abort")
        logger.write("pull 失败，继续使用本地版本\n")


def commit_and_push(logger: Logger, message: str, retries: int) -> bool:
    logger.write("\n提交并推送...\n")
    if git("add", "--", OUTPUT.name, SPIDER_DIR.name) != 0:
        logger.write("git add 失败\n")
        return False
    if git("diff", "--cached", "--quiet") == 0:
        logger.write("接口.json 与本地脚本没有变化，跳过提交\n")
        return True
    if git("commit", "-m", message) != 0:
        logger.write("git commit 失败\n")
        return False

    for attempt in range(1, retries + 1):
        if git("push", "origin", "HEAD:main") == 0:
            logger.write(f"推送成功（第 {attempt} 次尝试）\n")
            return True
        if attempt < retries:
            wait = 30 * attempt
            logger.write(f"推送失败，{wait}s 后重试（{attempt}/{retries}）\n")
            time.sleep(wait)
    logger.write(
        "推送失败，提交已保存在本地；下次运行会自动带上。\n"
        "也可以手动执行: git push origin HEAD:main\n"
    )
    return False


def prune_logs(keep: int = 30) -> None:
    try:
        files = sorted(LOG_DIR.glob("local-run-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本机定时更新 接口.json")
    parser.add_argument("--functional", action="store_true", help="先跑功能校验（会执行第三方代码）")
    parser.add_argument("--functional-limit", type=int, default=0, help="功能校验只测前 N 个脚本")
    parser.add_argument("--dry-run", action="store_true", help="只校验，不写文件、不提交")
    parser.add_argument("--no-push", action="store_true", help="只生成，不提交推送")
    parser.add_argument("--force", action="store_true", help="跳过可用站点骤降保护")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个脚本")
    parser.add_argument("--retries", type=int, default=3, help="推送失败重试次数")
    parser.add_argument("--config", default=str(SCRIPTS / "config.json"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logger = Logger(LOG_DIR / f"local-run-{stamp}.log")
    logger.write(f"===== 本机更新开始 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    logger.write(f"仓库: {ROOT}\n")

    try:
        if not args.dry_run and not args.no_push:
            pull(logger)

        if args.functional:
            command = [
                sys.executable,
                str(SCRIPTS / "functional_check.py"),
                "--config",
                args.config,
                "--cache-dir",
                str(SCRIPT_CACHE),
                "--output",
                str(FUNCTIONAL_REPORT),
            ]
            if args.functional_limit:
                command += ["--limit", str(args.functional_limit)]
            if run_step(logger, "功能校验", command) != 0:
                logger.write("功能校验失败，继续只用 host 校验结果\n")

        command = [sys.executable, str(SCRIPTS / "update_api.py"), "--config", args.config]
        # 功能校验已经把脚本下到缓存里了，直接复用，省掉一次全量下载。
        if args.functional and SCRIPT_CACHE.is_dir() and any(SCRIPT_CACHE.glob("*.py")):
            command += ["--source-dir", str(SCRIPT_CACHE)]
            logger.write(f"复用脚本缓存: {SCRIPT_CACHE}\n")
        if args.dry_run:
            command.append("--dry-run")
        if args.force:
            command.append("--force")
        if args.limit:
            command += ["--limit", str(args.limit)]
        if FUNCTIONAL_REPORT.exists():
            command += ["--functional-report", str(FUNCTIONAL_REPORT)]

        if run_step(logger, "更新接口.json", command) != 0:
            logger.write("更新失败，本次不提交\n")
            return 1

        if args.dry_run:
            logger.write("\ndry-run: 不提交、不推送\n")
            return 0
        if args.no_push:
            logger.write("\n--no-push: 不提交、不推送\n")
            return 0

        message = f"chore: 自动更新接口.json ({datetime.now():%Y-%m-%d})"
        ok = commit_and_push(logger, message, args.retries)
        return 0 if ok else 2
    except Exception:  # noqa: BLE001
        logger.write("\n未捕获异常:\n" + traceback.format_exc())
        return 1
    finally:
        logger.write(f"===== 结束 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        logger.write(f"日志: {logger.path}\n")
        logger.close()
        prune_logs()


if __name__ == "__main__":
    raise SystemExit(main())
