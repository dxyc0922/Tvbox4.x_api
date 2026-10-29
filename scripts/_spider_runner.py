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


def category_names(payload: Any) -> list[str]:
    """从 homeContent 的 class / filters 里取出分类名，用于识别成人站点。"""
    names: list[str] = []
    if not isinstance(payload, dict):
        return names
    classes = payload.get("class") or payload.get("classes") or []
    if isinstance(classes, list):
        for item in classes:
            if isinstance(item, dict):
                value = item.get("type_name") or item.get("name")
                if value:
                    names.append(str(value))
            elif isinstance(item, str):
                names.append(item)
    filters = payload.get("filters")
    if isinstance(filters, dict):
        for entries in filters.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("key") or "") != "分类":
                    continue
                for value in entry.get("value") or []:
                    if isinstance(value, dict) and value.get("n"):
                        names.append(str(value["n"]))
    return names


def item_labels(item: dict[str, Any]) -> list[str]:
    labels = []
    for key in ("vod_class", "type_name", "class", "vod_tag", "vod_name", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            labels.append(value.strip())
    return labels


def pick_id(item: dict[str, Any]) -> str | None:
    for key in ("vod_id", "id", "vodId", "ids"):
        value = item.get(key)
        if value:
            return str(value)
    return None


def play_stats(vod: dict[str, Any]) -> tuple[int, int, str, str]:
    """返回 (线路数, 集数, 第一个播放地址, 第一条线路的 flag)。"""
    raw = vod.get("vod_play_url") or ""
    froms = vod.get("vod_play_from") or ""
    if not isinstance(raw, str) or not raw.strip():
        return 0, 0, "", ""
    lines = [part for part in raw.split("$$$") if part.strip()]
    flags = [part for part in str(froms).split("$$$")] if froms else []
    episodes = 0
    first = ""
    first_flag = flags[0] if flags else ""
    for line in lines:
        for item in line.split("#"):
            if "$" in item:
                episodes += 1
                if not first:
                    first = item.split("$", 1)[1]
    return len(lines), episodes, first, first_flag


def line_samples(vod: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """每条线路取第一集的播放地址，最多取 limit 条。

    vod_play_url 用 `$$$` 分隔线路、`#` 分隔集数、`$` 分隔名称和地址，
    vod_play_from 用 `$$$` 分隔线路名，两者顺序一一对应。
    """
    raw = vod.get("vod_play_url") or ""
    froms = vod.get("vod_play_from") or ""
    if not isinstance(raw, str) or not raw.strip():
        return []
    lines = [part for part in raw.split("$$$") if part.strip()]
    flags = [part for part in str(froms).split("$$$")] if froms else []
    samples: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        first = ""
        for item in line.split("#"):
            if "$" in item:
                first = item.split("$", 1)[1]
                break
        if not first:
            continue
        samples.append(
            {
                "flag": flags[index] if index < len(flags) else "",
                "url": first,
                "index": index,
            }
        )
        if len(samples) >= max(limit, 1):
            break
    return samples


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
            "play_flag": "",
            "stream_url": "",
            "stream_parse": -1,
            "stream_header": {},
            "lines": [],
            "classes": [],
            "probe_hits": 0,
            "probe_labels": [],
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
                payload = call(home, [False])
                home_items = video_list(payload)
                classes = category_names(payload)
                if classes:
                    reporter.set(classes=classes[:80])
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

        # 成人内容探针：只对首页正常的站点跑，且只取分类/标签，不判断标题。
        probes = [str(k) for k in (job.get("adult_probe") or []) if str(k).strip()]
        if probes and reporter.data.get("home_ok"):
            budget = float(job.get("timeout") or 0)
            reporter.set(stage="adult_probe")
            labels: list[str] = []
            hits = 0
            try:
                search = getattr(spider, "searchContent", None)
                if callable(search):
                    for probe in probes[:3]:
                        if budget and float(reporter.data.get("elapsed") or 0) > budget * 0.6:
                            break
                        items = video_list(call(search, [probe, False, "1"]))
                        if not items:
                            continue
                        hits += len(items)
                        for item in items[:20]:
                            labels.extend(item_labels(item))
                        if len(labels) >= 40:
                            break
            except Exception:  # noqa: BLE001
                pass
            if labels:
                unique: list[str] = []
                for value in labels:
                    if value not in unique:
                        unique.append(value)
                reporter.set(probe_hits=hits, probe_labels=unique[:40])
            reporter.flush()

        vod_id = None
        for item in home_items + search_items:
            vod_id = pick_id(item)
            if vod_id:
                break

        reporter.set(stage="detail")
        vod: dict[str, Any] | None = None
        try:
            detail = getattr(spider, "detailContent", None)
            if callable(detail) and vod_id:
                payload = call(detail, [[vod_id]])
                videos = video_list(payload)
                if videos:
                    vod = videos[0]
                    froms, episodes, sample, flag = play_stats(vod)
                    reporter.set(
                        play_from=froms,
                        play_episodes=episodes,
                        sample_play_url=sample[:200],
                        play_flag=str(flag)[:40],
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
        reporter.flush()

        # 逐线路取第一集调 playerContent，拿到每条线路的真实播放地址。
        # 只测前 max_lines 条，并用剩余时间预算保护，避免把整个脚本跑超时。
        if vod is not None:
            samples = line_samples(vod, int(job.get("max_lines") or 4))
            if samples:
                reporter.set(stage="player")
                budget = float(job.get("timeout") or 0)
                player = getattr(spider, "playerContent", None)
                rows: list[dict[str, Any]] = []
                for sample in samples:
                    if budget and float(reporter.data.get("elapsed") or 0) > budget * 0.85:
                        break
                    row: dict[str, Any] = {
                        "flag": str(sample["flag"])[:40],
                        "url": sample["url"][:600],
                        "parse": -1,
                    }
                    if callable(player):
                        try:
                            resolved = call(player, [sample["flag"], sample["url"], []])
                            if isinstance(resolved, dict):
                                row["url"] = str(resolved.get("url") or sample["url"])[:600]
                                try:
                                    row["parse"] = int(resolved.get("parse", 0) or 0)
                                except (TypeError, ValueError):
                                    row["parse"] = -1
                                header = resolved.get("header") or {}
                                if isinstance(header, dict) and header:
                                    row["header"] = {
                                        str(key): str(value) for key, value in header.items()
                                    }
                        except Exception as exc:  # noqa: BLE001
                            row["error"] = f"{type(exc).__name__}: {exc}"[:200]
                    else:
                        row["error"] = "没有 playerContent"
                    rows.append(row)
                    if row.get("url") and row.get("parse") == 0 and not reporter.data.get("stream_url"):
                        reporter.set(
                            stream_url=row["url"],
                            stream_parse=0,
                            stream_header=row.get("header") or {},
                        )
                if rows:
                    reporter.set(lines=rows)
                reporter.flush()

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
