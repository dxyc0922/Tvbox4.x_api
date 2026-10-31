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
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LOG_DIR = ROOT / "logs"
OUTPUT = ROOT / "接口.json"
# 远程直链版（生成站点用 gh-proxy 绝对链接），与 接口.json 同步生成，需一起提交。
REMOTE_OUTPUT = ROOT / "接口-remote.json"
SPIDER_DIR = ROOT / "脚本"
FUNCTIONAL_REPORT = ROOT / "reports" / "functional-report.json"
# 功能校验下载好的脚本缓存，生成阶段直接复用，避免重复下载 200+ 个文件。
SCRIPT_CACHE = Path(tempfile.gettempdir()) / "tvbox-py-cache"
# 本机定时任务的通知配置（config.json 的 notify 段；留空只写日志）。
NOTIFY_CONFIG = SCRIPTS / "config.json"


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
    if git("add", "--", OUTPUT.name, REMOTE_OUTPUT.name, SPIDER_DIR.name) != 0:
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


def load_notify_config() -> dict[str, object]:
    """读取 config.json 的 notify 段；缺失或非法时返回空（只写日志，不通知）。"""
    try:
        data = json.loads(NOTIFY_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    notify = data.get("notify") if isinstance(data, dict) else None
    return notify if isinstance(notify, dict) else {}


def send_notification(logger: Logger, title: str, body: str) -> None:
    """把运行结果推送到配置的 webhook / Telegram。配置为空则只写日志。

    webhook：POST JSON `{"title": ..., "body": ...}`（适合 Discord 嵌入 / 企业微信 / 自建）。
    telegram：`https://api.telegram.org/bot<token>/sendMessage` 发纯文本。
    任何失败都只写日志，不中断主流程。
    """
    cfg = load_notify_config()
    webhook = str(cfg.get("webhook") or "").strip()
    tg = cfg.get("telegram") if isinstance(cfg.get("telegram"), dict) else {}
    token = str(tg.get("bot_token") or "").strip()
    chat_id = str(tg.get("chat_id") or "").strip()
    if not webhook and not (token and chat_id):
        logger.write(f"\n[通知] {title}：{body}\n")
        logger.write("[通知] 未配置通知渠道（config.json notify），只写日志\n")
        return

    text = f"{title}\n{body}"
    for attempt in (1, 2):
        try:
            if webhook:
                payload = json.dumps({"title": title, "body": body}).encode("utf-8")
                req = urllib.request.Request(
                    webhook, data=payload, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = int(resp.status or 0)
                logger.write(f"[通知] webhook 已发送（HTTP {status}）\n")
            if token and chat_id:
                payload = urllib.parse.urlencode(
                    {"chat_id": chat_id, "text": text[:4000]}
                ).encode("utf-8")
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                req = urllib.request.Request(url, data=payload)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = int(resp.status or 0)
                logger.write(f"[通知] Telegram 已发送（HTTP {status}）\n")
            return
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                logger.write(f"[通知] 发送失败（已重试）: {type(exc).__name__}: {exc}\n")
            else:
                time.sleep(2)


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
    parser.add_argument(
        "--notify",
        action="store_true",
        help="发送成功/失败通知（读取 config.json 的 notify 段；未配置则只写日志）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logger = Logger(LOG_DIR / f"local-run-{stamp}.log")
    logger.write(f"===== 本机更新开始 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    logger.write(f"仓库: {ROOT}\n")

    def notify(title: str, body: str) -> None:
        if args.notify:
            send_notification(logger, title, body)

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
            notify(
                "❌ TVBox 接口更新失败",
                f"仓库: {ROOT}\nupdate_api 退出码非 0，本次不提交。\n请查看最近日志: {LOG_DIR}",
            )
            return 1

        if args.dry_run:
            logger.write("\ndry-run: 不提交、不推送\n")
            notify("🖥️ TVBox 接口 dry-run 完成", f"仓库: {ROOT}")
            return 0
        if args.no_push:
            logger.write("\n--no-push: 不提交、不推送\n")
            notify("🖥️ TVBox 接口生成完成（未推送）", f"仓库: {ROOT}")
            return 0

        message = f"chore: 自动更新接口.json ({datetime.now():%Y-%m-%d})"
        ok = commit_and_push(logger, message, args.retries)
        if ok:
            notify(
                "✅ TVBox 接口更新完成",
                f"仓库: {ROOT}\n已提交并推送: {message}",
            )
            return 0
        notify(
            "⚠️ TVBox 接口已生成但推送失败",
            f"仓库: {ROOT}\n提交保存在本地，下次运行会自动带上。\n"
            f"手动: git push origin HEAD:main\n最近日志: {LOG_DIR}",
        )
        return 2
    except Exception:  # noqa: BLE001
        logger.write("\n未捕获异常:\n" + traceback.format_exc())
        notify(
            "❌ TVBox 接口更新异常",
            f"仓库: {ROOT}\n{traceback.format_exc()[-800:]}\n最近日志: {LOG_DIR}",
        )
        return 1
    finally:
        logger.write(f"===== 结束 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        logger.write(f"日志: {logger.path}\n")
        logger.close()
        prune_logs()


if __name__ == "__main__":
    raise SystemExit(main())
