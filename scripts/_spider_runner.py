#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子进程入口：加载单个上游脚本，依次调用 homeContent / searchContent / detailContent。

只由 functional_check.py 调用，不单独使用。结果分阶段写入 result 文件，
父进程超时被杀时仍能拿到已完成阶段的数据。
"""

from __future__ import annotations

import importlib.util
import inspect
import ipaddress
import json
import os
import socket
import sys
import time
import traceback
from typing import Any


def guard_network() -> None:
    """禁止访问内网/回环/链路本地地址，防止脚本探测 CI 内网或云元数据。"""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def check(address: Any) -> None:
        if not isinstance(address, tuple) or not address:
            return
        host = address[0]
        try:
            ip = ipaddress.ip_address(str(host))
        except ValueError:
            return
        if not ip.is_global:
            raise OSError(f"blocked non-public address: {host}")

    def connect(self: socket.socket, address: Any) -> Any:
        check(address)
        return original_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        try:
            check(address)
        except OSError:
            return 1
        return original_connect_ex(self, address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]


def load_module(path: str):
    spec = importlib.util.spec_from_file_location("spider_under_test", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["spider_under_test"] = module
    spec.loader.exec_module(module)
    return module


def positional_limit(fn: Any) -> int | None:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    count = 0
    for param in signature.parameters.values():
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            count += 1
        elif param.kind is inspect.Parameter.VAR_POSITIONAL:
            return None
    return count


def call(fn: Any, args: list[Any]) -> Any:
    limit = positional_limit(fn)
    if limit is not None:
        args = args[:limit]
    return fn(*args)


def video_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("list", "data", "videos", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def pick_id(item: dict[str, Any]) -> str | None:
    for key in ("vod_id", "id", "vodId", "ids"):
        value = item.get(key)
        if value:
            return str(value)
    return None


def play_stats(vod: dict[str, Any]) -> tuple[int, int, str]:
    raw = vod.get("vod_play_url") or ""
    if not isinstance(raw, str) or not raw.strip():
        return 0, 0, ""
    lines = [part for part in raw.split("$$$") if part.strip()]
    episodes = 0
    first = ""
    for line in lines:
        for item in line.split("#"):
            if "$" in item:
                episodes += 1
                if not first:
                    first = item.split("$", 1)[1]
    return len(lines), episodes, first


class Reporter:
    def __init__(self, path: str, name: str) -> None:
        self.path = path
        self.data: dict[str, Any] = {
            "file": name,
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
            "stage": "start",
            "elapsed": 0.0,
            "error": None,
            "traceback": None,
        }
        self.started = time.time()
        self.flush()

    def set(self, **kwargs: Any) -> None:
        self.data.update(kwargs)

    def flush(self) -> None:
        self.data["elapsed"] = round(time.time() - self.started, 2)
        self.data["score"] = sum(
            1 for key in ("home_ok", "search_ok", "detail_ok") if self.data[key]
        )
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, ensure_ascii=False)
        os.replace(temporary, self.path)


def apply_limits(limits: Any) -> None:
    if os.name != "posix" or not isinstance(limits, dict):
        return
    try:
        import resource

        cpu = int(limits.get("cpu") or 0)
        memory = int(limits.get("memory") or 0)
        fsize = int(limits.get("fsize") or 0)
        nofile = int(limits.get("nofile") or 0)
        if cpu > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        if memory > 0:
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        if fsize > 0:
            resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        if nofile > 0:
            resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as handle:
        job = json.load(handle)

    apply_limits(job.get("limits"))
    guard_network()
    sys.path.insert(0, job["shim"])

    reporter = Reporter(job["result"], job["name"])
    try:
        reporter.set(stage="import")
        module = load_module(job["script"])
        reporter.set(import_ok=True)
        reporter.flush()

        spider_class = getattr(module, "Spider", None)
        if spider_class is None:
            raise RuntimeError("没有 class Spider")

        reporter.set(stage="init")
        spider = spider_class()
        init = getattr(spider, "init", None)
        if callable(init):
            try:
                call(init, [""])
            except Exception as exc:  # noqa: BLE001
                reporter.set(error=f"init: {type(exc).__name__}: {exc}")
        reporter.set(init_ok=True)
        reporter.flush()

        home_items: list[dict[str, Any]] = []
        reporter.set(stage="home")
        try:
            home = getattr(spider, "homeContent", None)
            if callable(home):
                home_items = video_list(call(home, [False]))
            reporter.set(home_items=len(home_items), home_ok=bool(home_items))
        except Exception as exc:  # noqa: BLE001
            reporter.set(error=f"home: {type(exc).__name__}: {exc}")
        reporter.flush()

        search_items: list[dict[str, Any]] = []
        reporter.set(stage="search")
        try:
            search = getattr(spider, "searchContent", None)
            if callable(search):
                search_items = video_list(call(search, [job["keyword"], False, "1"]))
            reporter.set(search_items=len(search_items), search_ok=bool(search_items))
        except Exception as exc:  # noqa: BLE001
            current = reporter.data.get("error")
            reporter.set(error=f"{current}; search: {type(exc).__name__}: {exc}" if current else f"search: {type(exc).__name__}: {exc}")
        reporter.flush()

        vod_id = None
        for item in home_items + search_items:
            vod_id = pick_id(item)
            if vod_id:
                break

        reporter.set(stage="detail")
        try:
            detail = getattr(spider, "detailContent", None)
            if callable(detail) and vod_id:
                payload = call(detail, [[vod_id]])
                videos = video_list(payload)
                if videos:
                    froms, episodes, sample = play_stats(videos[0])
                    reporter.set(
                        play_from=froms,
                        play_episodes=episodes,
                        sample_play_url=sample[:200],
                        detail_ok=episodes > 0,
                    )
                else:
                    current = reporter.data.get("error")
                    message = "detail 返回空列表"
                    reporter.set(error=f"{current}; {message}" if current else message)
            elif not vod_id:
                current = reporter.data.get("error")
                message = "home/search 都没有可用的 vod_id"
                reporter.set(error=f"{current}; {message}" if current else message)
        except Exception as exc:  # noqa: BLE001
            current = reporter.data.get("error")
            message = f"detail: {type(exc).__name__}: {exc}"
            reporter.set(error=f"{current}; {message}" if current else message)
        reporter.set(stage="done")
        reporter.flush()
        return 0
    except Exception as exc:  # noqa: BLE001
        current = reporter.data.get("error")
        message = f"{type(exc).__name__}: {exc}"
        reporter.set(
            error=f"{current}; {message}" if current else message,
            traceback=traceback.format_exc()[-2000:],
            stage="aborted",
        )
        reporter.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
