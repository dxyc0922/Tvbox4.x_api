#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定期从 wzxxcz/wzxxcz 的 py 目录拉取脚本，校验脚本里的 host，重建 接口.json。

规则：
- 接口.json 中 api 以 ./ 开头（或不是 http/https）的站点原样保留；
- 所有 http/https 站点删除后，用校验通过的上游脚本重新生成；
- host 返回 2xx/3xx/4xx 视为可达，5xx、DNS 失败、连接超时视为失效；
- 只接受定义了 Spider 类的脚本，错误页/命令行脚本会被跳过；
- 代码内容相同的脚本只保留一个；
- 只读取/解析上游脚本，不执行任何上游代码。
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import time
import tokenize
import urllib.error
import urllib.parse
import urllib.request
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import stream_check  # noqa: E402  # grade_of 按画质+速度重算等级
import resource_station  # noqa: E402  # 资源站（采集站）线路检测：基本是低质源

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "scripts" / "config.json"

# 按分辨率定最低码率，单位 kbps。阈值取在实测数据的空档里：
# 按分辨率返回「最低达标码率」档位表。
# 键 = **长边（max(宽,高)）**，决定码率门槛（码率需求随像素数/数据量增长）：
#   3840 = 4K、2560 = 1440p、1920 = 1080p、1280 = 720p、854 = 480p、640 = 360p。
# 用长边而非短边：2.35:1 电影（1280x544）长边 1280 属 720p 类（69.6 万像素），
# 短边 544 会误判成 480p 档（只要求 1000kbps，1831kbps 虚高达标）；
# 竖屏短剧（720x1280）长边 1280 属 720p 类，按垂直高度会误判成 1440p 档。
# 注意：码率门槛看长边/像素数，与画质分级 grade_of 的**短边**清晰度判档是两个
# 维度——清晰度看短边（1920x1080=1080p），码率看数据量，两者不矛盾。
# 值 = 「好画质」最低线（用户实测 1280x544@1831 不达标，故 1280 宽档 ≥2000）。
# 再叠加 min_bpp（每像素密度）挡「1080p 但码率低」的廉价转码。
DEFAULT_BITRATE_THRESHOLDS: dict[str, int] = {
    "3840": 6000,
    "2560": 3500,
    "1920": 2000,
    "1280": 2000,
    "854": 1000,
    "640": 700,
}

# 每像素每帧最低码率（bits per pixel）。分辨率分档只能挡住「低分辨率高码率」，
# 挡不住「1080p 但码率只有 1.6–1.8 Mbps」的廉价转码，所以再加一层 bpp 下限：
#   最低码率 = max(分辨率档阈值, min_bpp × 宽 × 高 × fps / 1000)
# 0.05 落在实测 1080p 的 2309 → 2488 kbps 空档里：拦掉 0.035–0.046 这一档
# 「1080p 但码率 1.8–2.3 Mbps」的低质第三方源（采集聚合/达达兔/短剧等），
# 只留 bpp≥0.05（1080p24 约 2488 kbps 以上）的真正高码率源。
DEFAULT_MIN_BPP = 0.05

# 加载速度：线路实测下载速度 / 码率。低于这个倍数说明 CDN 吐得比播放快不了多少，
# 播放器会反复缓冲；0.7 留了约 40% 的余量。所有采样线路都低于它才剔除源。
DEFAULT_MIN_SPEED_RATIO = 0.7
# 播放列表 + 首个分片首字节的总耗时上限（毫秒）。超过说明「点开要等太久」，
# 即使后续吞吐正常也算慢线路。取 12 秒：实测同一条线路的启动耗时能波动 2 倍
# （麒麟/独播库一次 4 秒、一次 9 秒），阈值太低会按瞬时网络抖动误删。
DEFAULT_MAX_STARTUP_MS = 12000

DEFAULT_CONFIG: dict[str, Any] = {
    "upstream": {
        "owner": "wzxxcz",
        "repo": "wzxxcz",
        "branch": "maing",
        "path": "py",
    },
    "output": "接口.json",
    "accelerator": "https://gh-proxy.com/",
    "self_repo": {
        "owner": "dxyc0922",
        "repo": "Tvbox4.x_api",
        "branch": "main"
    },
    # 从 jsm.json 同步顶层字段。只同步用户明确要的 hosts/doh/rules/ads；
    # lives/wallpaper 是用户自定义（广东IPTV组播.txt、深色壁纸），保留 existing 原值，
    # 不从 jsm 覆盖。拉取失败时回退 existing，不中断。url 为空或 enabled=false 跳过。
    "jsm_sync": {
        "enabled": True,
        "url": "https://gh-proxy.com/https://raw.githubusercontent.com/qist/tvbox/master/jsm.json",
        "fields": ["hosts", "doh", "rules", "ads"],
    },
    "auto_key_prefix": "wzxxcz_",
    "preserve_api_prefixes": ["./"],
    "preserve_non_http": True,
    "exclude_scripts": [],
    "exclude_names": [],
    "filters": {
        "require_spider_class": True,
        "dedupe_identical_scripts": True,
        "exclude_adult": True,
        "adult_keywords": [],
        "adult_title_keywords": [],
        "adult_allow": [],
        # 已知广告/贴片域名片段（如 "adcdn"、"ads.example.com"）；命中即记广告分。
        "ad_hosts": [],
    },
    "functional": {
        "enabled": False,
        "report": "reports/functional-report.json",
        "min_score": 0,
        "keyword": "庆余年",
        "timeout": 30,
        "workers": 12,
        "stream_workers": 12,
    },
    "quality": {
        "min_grade": "",
        "drop_unverified": False,
        "min_bitrate_kbps": 800,
        "min_bpp": DEFAULT_MIN_BPP,
        "min_speed_ratio": DEFAULT_MIN_SPEED_RATIO,
        "max_startup_ms": DEFAULT_MAX_STARTUP_MS,
        "bitrate_thresholds": dict(DEFAULT_BITRATE_THRESHOLDS),
        "max_lines": 4,
        "bitrate_allow": [],
        "speed_allow": [],
        # 线路级裁减：把脚本里「不通 / 明显低于质量线」的线路从播放列表里去掉。
        "line_prune": {
            "enabled": False,
            # HTTP 状态码 >= 此值算不可用（400 token 过期、404 失效等）。
            "dead_status_min": 400,
            # 手动指定要剔除的线路名，键是脚本文件名。
            "blacklist": {},
        },
    },
    "local_spider_dir": "",
    "safety": {
        "min_previous_ratio": 0.5,
        "max_download_failure_ratio": 0.2,
    },
    "request": {
        "timeout": 10,
        "retries": 1,
        "workers": 20,
        "download_workers": 12,
        "accept_4xx": True,
        "accept_5xx": False,
        "max_hosts_per_script": 8,
        "max_fallback_hosts": 3,
    },
    # 运行结果通知：webhook 是任意 POST 地址（如 Discord/企业微信机器人），
    # telegram 用 bot_token + chat_id 发 Bot API 消息。留空则只写日志，无行为变化。
    "notify": {
        "webhook": "",
        "telegram": {"bot_token": "", "chat_id": ""},
    },
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

URL_RE = re.compile(r"https?://[^\s\"'\)\]\},;<>\\]+")
DK8_RE = re.compile(r"_dk8\(\s*(['\"])(.*?)\1\s*\)")
ASSET_EXT_RE = re.compile(
    r"\.(?:png|jpe?g|gif|webp|svg|ico|bmp|css|js|woff2?|ttf|eot|"
    r"mp4|m3u8|ts|flv|mkv|avi|apk|zip|rar|7z)(?:$|[?#])",
    re.IGNORECASE,
)
AD_SUFFIX_RE = re.compile(r"🍀\s*TG\s*@\S+", re.IGNORECASE)
AD_SUFFIX_RE2 = re.compile(r"🍀\s*TG\S*", re.IGNORECASE)

# host 变量优先级：0 最高。只有最高非空层级会被用于校验，避免把第三方 API
# 误当成站点主域名。
HOST_TIERS: dict[str, int] = {
    "host": 0,
    "hosts": 0,
    "host_url": 0,
    "xurl": 0,
    "xurl1": 0,
    "site": 0,
    "site_url": 0,
    "siteurl": 0,
    "domain": 0,
    "root": 0,
    "root_url": 0,
    "base": 1,
    "base_url": 1,
    "baseurl": 1,
    "url_base": 1,
    "server": 1,
    "server_url": 1,
    "api_base": 1,
    "api": 2,
    "api_url": 2,
    "api_urls": 2,
    "apis": 2,
}

# 兜底选择 host 时降低这些静态资源/客服/对象存储域名的权重。
PENALIZED_DOMAINS = {
    "raw.githubusercontent.com",
    "github.com",
    "gitee.com",
    "aliyuncs.com",
    "myqcloud.com",
    "byteimg.com",
    "msstatic.com",
    "7moor-fs1.com",
    "wsrv.nl",
    "baidu.com",
}

PROBE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "close",
}

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

DOWNLOAD_OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=SSL_CONTEXT)
)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """校验时只关心 host 是否响应，不跟随重定向（也避免被重定向到内网）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


PROBE_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=SSL_CONTEXT),
    NoRedirectHandler(),
)

_DNS_CACHE: dict[tuple[str, int], bool] = {}


@dataclass
class ProbeResult:
    ok: bool
    status: int | None = None
    url: str | None = None
    error: str | None = None


@dataclass
class ScriptResult:
    filename: str
    name: str
    status: str  # pending / valid / invalid / no_host / skipped / download_failed / duplicate / excluded / excluded_adult / functional_fail / low_quality / low_bitrate / slow_stream / resource_station / parse_required
    hosts: list[str] = field(default_factory=list)
    tier: str = ""
    checked_host: str | None = None
    http_status: int | None = None
    error: str | None = None
    entry: dict[str, Any] | None = None
    fingerprint: str = ""
    quality: dict[str, Any] | None = None
    source: str = ""
    strike: int = 0
    pending: str = ""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_CONFIG
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"配置文件不是 JSON 对象: {path}")
    return deep_merge(DEFAULT_CONFIG, data)


def fetch_bytes(
    url: str,
    timeout: float,
    retries: int = 1,
    headers: dict[str, str] | None = None,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with DOWNLOAD_OPENER.open(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            try:
                exc.close()
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001 - 网络错误类型很多
            last_error = exc
        if attempt < retries:
            time.sleep(1 + attempt)
    assert last_error is not None
    raise last_error


def fetch_json(
    url: str,
    timeout: float,
    retries: int = 1,
    headers: dict[str, str] | None = None,
) -> Any:
    raw = fetch_bytes(url, timeout=timeout, retries=retries, headers=headers)
    return json.loads(raw.decode("utf-8-sig"))


def decode_python(data: bytes) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    except Exception:
        encoding = "utf-8"
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def upstream_list(config: dict[str, Any]) -> list[dict[str, Any]]:
    """返回上游配置列表（兼容单个 dict 或 list）。"""
    up = config.get("upstream")
    if isinstance(up, list):
        return [u for u in up if isinstance(u, dict)]
    if isinstance(up, dict):
        return [up]
    return []


def upstream_raw_url(config: dict[str, Any], filename: str, src: int = 0) -> str:
    ups = upstream_list(config)
    if not ups:
        raise RuntimeError("upstream 配置为空")
    up = ups[src] if src < len(ups) else ups[0]
    quoted = urllib.parse.quote(filename, safe="/")
    return (
        f"https://raw.githubusercontent.com/{up['owner']}/{up['repo']}/"
        f"{up['branch']}/{up['path']}/{quoted}"
    )


def accelerator_list(config: dict[str, Any]) -> list[str]:
    """返回国内 GitHub 加速镜像列表（多个，按优先级）。

    用户反馈：不要只依赖单一加速（gh-proxy.com 挂掉就完了），有很多国内
    镜像可用。config.accelerators 是列表（优先）；config.accelerator 旧单值
    只在 accelerators 为空时兜底。每个都归一化成以 / 结尾，去重。
    """
    accels: list[str] = []
    raw_accels = config.get("accelerators") or []
    if isinstance(raw_accels, str):
        raw_accels = [raw_accels]
    for a in raw_accels:
        a = str(a).strip().rstrip("/")
        if a and a + "/" not in accels:
            accels.append(a + "/")
    if not accels:
        old = str(config.get("accelerator") or "").strip().rstrip("/")
        if old and old + "/" not in accels:
            accels.append(old + "/")
    return accels


def upstream_api_url(config: dict[str, Any], filename: str, src: int = 0) -> str:
    accels = accelerator_list(config)
    raw = upstream_raw_url(config, filename, src)
    if not accels:
        return raw
    return accels[0] + raw


def local_api_to_remote(config: dict[str, Any], api: str) -> str:
    """把本地 `./脚本/x.py` 链接转成仓库自身的绝对直链（用于 接口-remote.json）。

    手动保留的自定义站点（豆瓣/哔哩）不在上游仓库里，无法用 upstream_api_url；
    但脚本提交在本仓库 脚本/ 下，可用 self_repo 配置拼 raw 地址。没配 self_repo
    时原样返回（保持相对路径，仍可随仓库一起托管）。
    """
    if not api.startswith("./"):
        return api
    self_repo = config.get("self_repo") or {}
    owner = str(self_repo.get("owner") or "").strip()
    repo = str(self_repo.get("repo") or "").strip()
    branch = str(self_repo.get("branch") or "main").strip()
    if not owner or not repo:
        return api
    rel = urllib.parse.quote(api[2:].strip("/"), safe="/")
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rel}"
    accels = accelerator_list(config)
    if not accels:
        return raw
    return accels[0] + raw


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": "Tvbox4.x_api-sync/1.0",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def upstream_files_from_github_tree(
    config: dict[str, Any], token: str | None, up: dict[str, Any]
) -> list[str]:
    url = (
        f"https://api.github.com/repos/{up['owner']}/{up['repo']}/"
        f"git/trees/{up['branch']}?recursive=1"
    )
    data = fetch_json(url, timeout=20, retries=1, headers=github_headers(token))
    if data.get("truncated"):
        raise RuntimeError("GitHub tree 结果被截断")
    prefix = str(up["path"]).strip("/") + "/"
    files = [
        item["path"][len(prefix) :]
        for item in data.get("tree", [])
        if item.get("type") == "blob"
        and item.get("path", "").startswith(prefix)
        and item.get("path", "").endswith(".py")
    ]
    return sorted(files)


def upstream_files_from_github_contents(
    config: dict[str, Any], token: str | None, up: dict[str, Any]
) -> list[str]:
    url = (
        f"https://api.github.com/repos/{up['owner']}/{up['repo']}/"
        f"contents/{up['path']}?ref={up['branch']}"
    )
    data = fetch_json(url, timeout=20, retries=1, headers=github_headers(token))
    if not isinstance(data, list):
        raise RuntimeError("GitHub contents 返回格式异常")
    return sorted(
        item["name"]
        for item in data
        if item.get("type") == "file" and item.get("name", "").endswith(".py")
    )


def upstream_files_from_jsdelivr(
    config: dict[str, Any], up: dict[str, Any]
) -> list[str]:
    url = (
        f"https://data.jsdelivr.com/v1/packages/gh/{up['owner']}/{up['repo']}"
        f"@{up['branch']}?structure=flat"
    )
    data = fetch_json(url, timeout=20, retries=1)
    prefix = "/" + str(up["path"]).strip("/") + "/"
    files = []
    for item in data.get("files", []):
        name = item.get("name", "")
        if name.startswith(prefix) and name.endswith(".py"):
            files.append(name[len(prefix) :])
    return sorted(files)


def get_upstream_filenames(
    config: dict[str, Any], source_dir: Path | None, token: str | None
) -> dict[str, int]:
    """返回 {上游脚本相对路径: 来源序号}，多上游按文件名去重（保留首个来源）。

    返回 dict 以记录每个文件来自哪个上游（download_script 用它拼对 URL）。
    """
    if source_dir is not None:
        if not source_dir.is_dir():
            raise RuntimeError(f"本地 py 目录不存在: {source_dir}")
        files = sorted(
            path.relative_to(source_dir).as_posix()
            for path in source_dir.rglob("*.py")
        )
        # 若 functional_check 写过 sources.json，恢复来源映射（接口-remote 需要真实上游）。
        src_map: dict[str, int] = {}
        src_file = source_dir / "sources.json"
        if src_file.is_file():
            try:
                data = json.loads(src_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    src_map = {str(k): int(v) for k, v in data.items()}
            except (OSError, ValueError):
                src_map = {}
        if src_map:
            return {f: src_map.get(f, 0) for f in files}
        return {f: 0 for f in files}

    ups = upstream_list(config)
    if not ups:
        raise RuntimeError("upstream 配置为空")

    errors: list[str] = []
    seen: dict[str, tuple[str, int]] = {}
    for src, up in enumerate(ups):
        got = False
        label_ok = ""
        for label, loader in (
            ("GitHub tree", lambda: upstream_files_from_github_tree(config, token, up)),
            ("GitHub contents", lambda: upstream_files_from_github_contents(config, token, up)),
            ("jsDelivr", lambda: upstream_files_from_jsdelivr(config, up)),
        ):
            try:
                files = loader()
                if files:
                    print(
                        f"上游[{src}] {up['owner']}/{up['repo']}@{up['branch']}: "
                        f"{label} ({len(files)} 个 .py)"
                    )
                    got = True
                    label_ok = label
                    break
                errors.append(f"上游[{src}] {up['owner']}/{up['repo']} {label}: 没有找到 .py")
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"上游[{src}] {up['owner']}/{up['repo']} {label}: {type(exc).__name__}: {exc}"
                )
        if not got:
            print(
                f"警告: 上游[{src}] {up['owner']}/{up['repo']} 获取文件列表失败，跳过",
                file=sys.stderr,
            )
            continue
        for f in files:
            base = f.rsplit("/", 1)[-1]
            if base not in seen:
                seen[base] = (f, src)
    if not seen:
        raise RuntimeError("无法获取上游 py 文件列表:\n  " + "\n  ".join(errors))
    return {f: src for f, src in seen.values()}


def download_script(
    config: dict[str, Any], filename: str, source_dir: Path | None, src: int = 0
) -> tuple[str, str]:
    if source_dir is not None:
        path = source_dir / filename
        return decode_python(path.read_bytes()), str(path)

    ups = upstream_list(config)
    up = ups[src] if src < len(ups) else ups[0]
    quoted = urllib.parse.quote(filename, safe="/")
    raw = (
        f"https://raw.githubusercontent.com/{up['owner']}/{up['repo']}/"
        f"{up['branch']}/{up['path']}/{quoted}"
    )
    jsdelivr = (
        f"https://cdn.jsdelivr.net/gh/{up['owner']}/{up['repo']}@"
        f"{up['branch']}/{up['path']}/{quoted}"
    )
    # 国内加速优先（用户反馈：国内直连 raw.githubusercontent 慢/不通，先试加速）。
    # 多个镜像按优先级降级（gh-proxy.com 挂了换 ghfast.top 等），全失败才 jsdelivr/raw。
    accels = accelerator_list(config)
    urls = [a + raw for a in accels] + [jsdelivr, raw]

    timeout = float(config["request"]["timeout"])
    errors: list[str] = []
    for url in urls:
        try:
            data = fetch_bytes(
                url, timeout=timeout, retries=1, headers={"User-Agent": UA}
            )
            if data:
                return decode_python(data), url
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}")
    raise RuntimeError("下载失败: " + ", ".join(errors))


def decode_dk8(source: str) -> str:
    """解码上游脚本里常见的 _dk8(base64 + XOR 35) 混淆字符串。"""
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        if count >= 1000:
            return match.group(0)
        try:
            raw = base64.b64decode(match.group(2))
            decoded = bytes(byte ^ 35 for byte in raw).decode("utf-8")
            if not decoded:
                return match.group(0)
            printable = sum(ch.isprintable() for ch in decoded)
            if printable < len(decoded) * 0.8:
                return match.group(0)
            count += 1
            return repr(decoded)
        except Exception:
            return match.group(0)

    return DK8_RE.sub(repl, source)


def iter_literals(node: ast.AST | None) -> Iterable[str]:
    if node is None:
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            yield node.value
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            yield from iter_literals(element)
    elif isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if key is not None:
                yield from iter_literals(key)
            yield from iter_literals(value)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        yield from iter_literals(node.left)
        yield from iter_literals(node.right)
    elif isinstance(node, ast.IfExp):
        yield from iter_literals(node.body)
        yield from iter_literals(node.orelse)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from iter_literals(value)
    elif isinstance(node, ast.JoinedStr):
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                yield value.value


def target_name(target: ast.AST) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def is_asset_url(url: str) -> bool:
    try:
        path = urllib.parse.urlsplit(url).path
    except ValueError:
        return True
    return bool(ASSET_EXT_RE.search(path))


def origin_of(url: str) -> str | None:
    """把 URL 归一化成 scheme://host[:port]，过滤明显无效/内网的地址。"""
    text = url.strip().strip("'\"")
    if not text or len(text) > 2048:
        return None
    if not re.match(r"^https?://", text, re.IGNORECASE):
        return None
    if any(ch in text for ch in "{}\\<>") or any(ch.isspace() for ch in text):
        return None
    # 允许 %E4 这类百分号编码，拒绝 %s / %d / %(name)s 这类格式化占位符。
    if re.search(r"%(?![0-9A-Fa-f]{2})", text):
        return None

    try:
        parsed = urllib.parse.urlsplit(text)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return None

    if not host or parsed.username or parsed.password:
        return None
    if host in {
        "localhost",
        "domain.com",
        "example.com",
        "xxx",
        "127.0.0.1",
        "0.0.0.0",
    }:
        return None
    if host.endswith((".local", ".internal", ".lan", ".home")):
        return None
    if "_" in host or ".." in host:
        return None
    if host.startswith("m.") and host.count(".") == 1:
        return None

    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            return None
    except ValueError:
        if "." not in host:
            return None
        if not re.match(r"^[a-z0-9.-]+$", host):
            return None
        if not re.search(r"\.[a-z]{2,}$", host):
            return None

    if port is not None and not (1 <= port <= 65535):
        return None

    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    return f"{parsed.scheme.lower()}://{netloc}"


def is_penalized_domain(origin: str) -> bool:
    host = urllib.parse.urlsplit(origin).hostname or ""
    return any(host == domain or host.endswith("." + domain) for domain in PENALIZED_DOMAINS)


def fallback_hosts(source: str, limit: int) -> list[str]:
    matches: list[tuple[str, str, int]] = []
    for match in URL_RE.finditer(source):
        url = match.group(0).rstrip(".,;")
        origin = origin_of(url)
        if not origin or is_asset_url(url):
            continue
        matches.append((url, origin, match.start()))
    if not matches:
        return []

    counts = Counter(origin for _, origin, _ in matches)
    scored: list[tuple[int, int, str]] = []
    for url, origin, position in matches:
        path = urllib.parse.urlsplit(url).path or "/"
        score = counts[origin] * 10
        if path in ("", "/"):
            score += 5
        if position < 5000:
            score += 2
        if is_penalized_domain(origin):
            score -= 100
        lowered = url.lower()
        if "kefu" in lowered or "7moor" in lowered:
            score -= 50
        scored.append((score, -position, origin))

    scored.sort(reverse=True)
    result: list[str] = []
    for _, _, origin in scored:
        if origin not in result:
            result.append(origin)
        if len(result) >= limit:
            break
    return result


def extract_hosts(
    source: str, max_hosts: int, max_fallback: int
) -> tuple[list[str], str]:
    decoded_source = decode_dk8(source)

    tree: ast.AST | None = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            tree = ast.parse(decoded_source)
        except Exception:
            tree = None

    tier_values: dict[int, list[tuple[int, str]]] = {0: [], 1: [], 2: []}
    if tree is not None:
        for node in ast.walk(tree):
            candidates: list[tuple[int, ast.AST | None, int]] = []
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = target_name(target)
                    if name and name.lower() in HOST_TIERS:
                        candidates.append(
                            (HOST_TIERS[name.lower()], node.value, node.lineno)
                        )
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                name = target_name(node.target)
                if name and name.lower() in HOST_TIERS:
                    candidates.append(
                        (HOST_TIERS[name.lower()], node.value, node.lineno)
                    )
            elif isinstance(node, ast.keyword) and node.arg:
                if node.arg.lower() in HOST_TIERS:
                    candidates.append(
                        (
                            HOST_TIERS[node.arg.lower()],
                            node.value,
                            getattr(node.value, "lineno", 0),
                        )
                    )

            for tier, value, line in candidates:
                for literal in iter_literals(value):
                    origin = origin_of(literal)
                    if origin and not is_asset_url(literal):
                        tier_values[tier].append((line, origin))

    for tier in (0, 1, 2):
        values = tier_values[tier]
        if not values:
            continue
        values.sort(key=lambda item: item[0])
        result: list[str] = []
        for _, origin in values:
            if origin not in result:
                result.append(origin)
        return result[:max_hosts], f"tier{tier}"

    return fallback_hosts(decoded_source, max_fallback), "fallback"


def is_error_page(source: str) -> bool:
    head = source[:3000].lower()
    if "devsidecar error" in head:
        return True
    # 上游偶尔会把代理报错页当成 .py 文件提交。
    if head.lstrip().startswith("<") and ("<style" in head or "<html" in head or "<p>" in head):
        return True
    return False


def has_spider_class(source: str) -> bool:
    """TVBox/影视仓 的 py 源必须定义 class Spider，否则加载即失败。"""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return bool(re.search(r"^\s*class\s+Spider\b", source, re.M))
    return any(
        isinstance(node, ast.ClassDef) and node.name == "Spider"
        for node in ast.walk(tree)
    )


def source_fingerprint(source: str) -> str:
    """代码指纹：忽略注释/空白/中文文案，保留 URL，用于识别改名副本。"""
    try:
        parts: list[str] = []
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in (
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENCODING,
            ):
                continue
            parts.append(token.string)
        normalized = "\x00".join(parts)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        normalized = re.sub(r"#[^\n]*", "", source)
        normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[\u4e00-\u9fff]+", "CN", normalized)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def sanitize_name(filename: str) -> str:
    name = Path(filename).stem
    name = AD_SUFFIX_RE.sub("", name)
    name = AD_SUFFIX_RE2.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" ._-")
    return name or "未命名"


def build_entry(config: dict[str, Any], filename: str, src: int = 0) -> dict[str, Any]:
    prefix = str(config.get("auto_key_prefix") or "")
    digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:12]
    local_dir = str(config.get("local_spider_dir") or "").strip().strip("/")
    if local_dir:
        # 同步到本地脚本目录，接口指向本地文件；不依赖 gh-proxy 存活。
        api = f"./{local_dir}/{filename}"
    else:
        api = upstream_api_url(config, filename, src)
    return {
        "key": f"{prefix}{digest}",
        "name": sanitize_name(filename),
        "type": 3,
        "api": api,
    }


def resolve_public(host: str, port: int) -> bool:
    key = (host, port)
    if key in _DNS_CACHE:
        return _DNS_CACHE[key]
    if host == "metadata.google.internal":
        _DNS_CACHE[key] = False
        return False
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception:
        _DNS_CACHE[key] = False
        return False

    seen_global = False
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not ip.is_global:
            _DNS_CACHE[key] = False
            return False
        seen_global = True
    _DNS_CACHE[key] = seen_global
    return seen_global


def build_probe_variants(origin: str) -> list[str]:
    parsed = urllib.parse.urlsplit(origin)
    variants = [origin]

    alternate_scheme = "http" if parsed.scheme == "https" else "https"
    variants.append(
        urllib.parse.urlunsplit((alternate_scheme, parsed.netloc, "", "", ""))
    )

    host = parsed.hostname or ""
    alternate_host: str | None = None
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip:
        alternate_host = None
    elif host.startswith("www."):
        alternate_host = host[4:]
    elif host.count(".") >= 1 and not host.startswith(
        ("api.", "m.", "cdn.", "img.", "static.", "live.", "app.", "v.")
    ):
        alternate_host = "www." + host
    if alternate_host:
        netloc = alternate_host
        if parsed.port:
            netloc += f":{parsed.port}"
        variants.append(
            urllib.parse.urlunsplit((parsed.scheme, netloc, "", "", ""))
        )

    result: list[str] = []
    for variant in variants:
        if variant not in result:
            result.append(variant)
    return result


def status_accepted(status: int | None, config: dict[str, Any]) -> bool:
    if status is None:
        return False
    if 200 <= status < 400:
        return True
    if config["request"].get("accept_4xx", True) and 400 <= status < 500:
        return True
    if config["request"].get("accept_5xx", False) and 500 <= status < 600:
        return True
    return False


def probe_host(origin: str, config: dict[str, Any]) -> ProbeResult:
    timeout = float(config["request"]["timeout"])
    retries = int(config["request"]["retries"])
    last_error = ""
    primary_error = ""

    for index, variant in enumerate(build_probe_variants(origin)):
        parsed = urllib.parse.urlsplit(variant)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host or not resolve_public(host, port):
            last_error = "DNS 解析失败或解析到内网地址"
            if index == 0 and not primary_error:
                primary_error = last_error
            continue

        for attempt in range(retries + 1):
            try:
                request = urllib.request.Request(variant, headers=PROBE_HEADERS)
                with PROBE_OPENER.open(request, timeout=timeout) as response:
                    status = getattr(response, "status", None) or response.getcode()
                    response.close()
                    if status_accepted(status, config):
                        return ProbeResult(True, status, variant)
                    last_error = f"HTTP {status}"
                    break
            except urllib.error.HTTPError as exc:
                status = exc.code
                try:
                    exc.close()
                except Exception:
                    pass
                if status_accepted(status, config):
                    return ProbeResult(True, status, variant)
                last_error = f"HTTP {status}"
                break
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    time.sleep(0.5 + attempt)

        if index == 0 and not primary_error:
            primary_error = last_error

    return ProbeResult(False, None, None, primary_error or last_error or "不可达")


def validate_hosts(
    hosts: Iterable[str], config: dict[str, Any]
) -> dict[str, ProbeResult]:
    unique_hosts = sorted(set(hosts))
    if not unique_hosts:
        return {}
    results: dict[str, ProbeResult] = {}
    workers = int(config["request"]["workers"])
    started = time.time()
    print(f"开始校验 {len(unique_hosts)} 个唯一 host（并发 {workers}）...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(probe_host, host, config): host for host in unique_hosts
        }
        for index, future in enumerate(as_completed(futures), 1):
            host = futures[future]
            try:
                results[host] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[host] = ProbeResult(False, None, None, repr(exc))
            if index % 25 == 0 or index == len(futures):
                print(
                    f"  已校验 {index}/{len(futures)}，"
                    f"耗时 {time.time() - started:.1f}s"
                )
    return results


def split_sites(
    sites: list[Any], config: dict[str, Any]
) -> tuple[list[Any], list[Any]]:
    prefixes = tuple(str(p) for p in config.get("preserve_api_prefixes", ["./"]))
    preserve_non_http = bool(config.get("preserve_non_http", True))
    preserved: list[Any] = []
    removed: list[Any] = []
    for site in sites:
        if not isinstance(site, dict):
            preserved.append(site)
            continue
        api = str(site.get("api") or "").strip()
        if not api:
            preserved.append(site)
        elif prefixes and api.startswith(prefixes):
            preserved.append(site)
        elif not api.lower().startswith(("http://", "https://")):
            if preserve_non_http:
                preserved.append(site)
            else:
                removed.append(site)
        else:
            removed.append(site)
    return preserved, removed


def load_existing(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {"sites": []}, "\n"
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 不是 JSON 对象")
    return data, newline


def load_functional_report(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    rows = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}
    quality: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("file"):
            quality[str(row["file"])] = row
    return quality


def sync_jsm_fields(
    config: dict[str, Any],
    output: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    """把 jsm.json（qist/tvbox）的顶层字段同步进输出数据。

    同步 `hosts`/`doh`/`rules`/`ads`/`wallpaper`/`lives` 等字段，让它们始终跟上游
    jsm.json 保持一致，而不是只靠 `existing`（上一次接口）原样保留。拉取失败、字段
    缺失或非法时回退到 `existing` 里的原值，不中断生成。

    返回更新后的 output（原地修改并返回）。
    """
    cfg = config.get("jsm_sync") or {}
    if not cfg.get("enabled"):
        return output
    url_tpl = str(cfg.get("url") or "").strip()
    if not url_tpl:
        return output
    fields = [str(f) for f in (cfg.get("fields") or []) if str(f).strip()]

    # jsm_sync.url 支持 {accelerator} 模板（多镜像降级）：每个加速镜像各试一次，
    # 成功即用；兼容旧完整 url（含 gh-proxy 前缀，无模板时直接用）。
    urls: list[str] = []
    if "{accelerator}" in url_tpl:
        urls = [url_tpl.format(accelerator=a) for a in accelerator_list(config)]
    else:
        urls = [url_tpl]
    data: dict[str, Any] | None = None
    for url in urls:
        try:
            raw = fetch_bytes(url, timeout=float(config.get("request", {}).get("timeout") or 15), retries=1)
            data = json.loads(raw.decode("utf-8-sig"))
            if isinstance(data, dict):
                break
            data = None
        except Exception as exc:  # noqa: BLE001 - 网络/解析失败换下一个镜像
            print(f"  jsm_sync: 拉取 {url} 失败: {type(exc).__name__}: {exc}")
    if data is None:
        print(f"  jsm_sync: 全部镜像拉取失败（回退 existing 保留）: {url_tpl}")
        return output

    got = 0
    for field in fields:
        if field in data:
            output[field] = data[field]
            got += 1
        elif field in existing:
            # jsm 这次没有这个字段，但上次接口里有——保留原值，别丢掉。
            output[field] = existing[field]
    if got:
        print(f"  jsm_sync: 同步 {got} 个字段（{', '.join(f for f in fields if f in data)}）")
    else:
        print("  jsm_sync: jsm.json 没有可同步的字段，保持 existing")
    return output


# 正常短剧题材中被成人词表误伤的分类名：命中这些就不再判成人。
CATEGORY_ALLOW_PHRASES = ("家庭伦理", "伦理现实")

# 分类名精确匹配：这些词单独出现就是成人分类。
ADULT_CATEGORY_EXACT = frozenset(
    {"伦理", "理论", "福利", "里番", "无码", "三级", "成人", "情色", "色情", "三级片", "成人片"}
)

# 分类名包含匹配：必须足够明确，避免「家庭伦理」「伦理现实」这类正常短剧分类被误杀。
ADULT_CATEGORY_KEYWORDS = (
    "伦理片",
    "理论片",
    "福利片",
    "成人",
    "三级",
    "无码",  # 成人分类前缀词（中字无码/步兵无码，花都影视实测）
    "写真集", "大尺度", "私拍", "白丝", "黑丝",  # 软色情写真分类（momo图鉴实测）
    "AV片",
    "麻豆",
    "蜜桃",
    "天美",
    "星空传媒",
    "果冻传媒",
    "精东",
    "91传媒",
    "女优",
    "素人",
    "自拍",
    "偷拍",
    "乱伦",
    "迷奸",
    "强奸",
    "反差婊",
    "禁忌",
    "车震",
    "换妻",
    "性爱",
    "换脸",
    "少妇",
    "人妻",
    "调教",
    "18禁",
    "R18",
)

# 标题只认工作室品牌和明确成人词；「调教」「人妻」这类词在正常短剧标题里也会出现。
# 明确成人短语：标题含这些几乎必是成人内容（新闻标题不会用）。用于标题子串匹配。
# 新逻辑：只用「女教师」关键词搜出的色情片名后缀模式。
# 旧逻辑（porn/探花/打桩机/无码片名猜词等）已移除——识别率低、误伤高。
# 分类名识别（无码/伦理/三级等）由 ADULT_CATEGORY_EXACT/KEYWORDS 负责，保留。
ADULT_TITLE_STRICT = (
    # 已AI确认的完整色情片名/稳定唯一片段（从 scripts/porn_titles.txt 加载）。
    # 用完整片名匹配而非宽泛子串——色情片名同质化、多源共享，精确匹配零误伤。
    # 见 detect_adult 里的 porn_titles 加载。
)
# 成人品牌词：新闻/评论标题常提及（如「麻豆传媒落网」），只用于分类名精确匹配，
# 不用于标题子串匹配，避免把新闻源误判成成人源。
ADULT_TITLE_KEYWORDS = (
    "麻豆传媒", "星空传媒", "果冻传媒", "精东传媒", "天美传媒", "蜜桃传媒",
    "91制片厂", "女优",
) + ADULT_TITLE_STRICT


def detect_adult(
    quality: dict[str, Any] | None,
    category_keywords: tuple[str, ...] | list[str],
    title_keywords: tuple[str, ...] | list[str],
    probe_phrases: tuple[str, ...] | list[str] = (),
    strict_keywords: tuple[str, ...] | list[str] = (),
) -> list[str]:
    """从首页分类名和探针搜索结果的分类/标题里识别成人内容。

    分类名用宽一点的词表；标题只用工作室品牌、明确成人词，以及探针关键词原文
    （站点能搜出「被家长调教的女教师」这种完整片名，说明它确实收录了成人片）。
    """
    if not quality:
        return []
    hits: list[str] = []
    # 功能校验阶段已按分类名判定的纯色情源（runner 提前跳过分析省的标记）。
    if quality.get("adult_by_category"):
        return ["纯色情源(分类名)"]

    # 完整色情片名清单（精确匹配，多源同质化片名）——运行时从文件加载。
    porn_titles: tuple[str, ...] = ()
    pt_path = Path(__file__).resolve().parent / "porn_titles.txt"
    if pt_path.exists():
        porn_titles = tuple(
            line.strip() for line in pt_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )

    def add(value: str) -> None:
        if value not in hits:
            hits.append(value)

    for label in quality.get("classes") or []:
        text = str(label).strip()
        # 短剧题材里的「家庭伦理/伦理现实」是正常分类，不是色情分类。
        if any( phrase in text for phrase in CATEGORY_ALLOW_PHRASES):
            continue
        if text in ADULT_CATEGORY_EXACT:
            add(text)
        for keyword in category_keywords:
            if keyword and keyword.lower() in text.lower():
                add(keyword)

    phrases = [str(p) for p in probe_phrases if str(p).strip()]
    strict = [str(k) for k in strict_keywords] or list(ADULT_TITLE_STRICT)
    # 片名检测：先用完整色情片名清单精确匹配（同质化片名，多源共享），
    # 再用严格短语。完整片名匹配最可靠，零误伤。
    all_title_fields = list(quality.get("probe_labels") or []) + list(quality.get("search_titles") or [])
    for label in all_title_fields:
        text = str(label)
        for title in porn_titles:
            if title.lower() in text.lower():
                add(title)
        for keyword in strict:
            if keyword and keyword.lower() in text.lower():
                add(keyword)

    return hits


def is_fixed_category_mixed(
    quality: dict[str, Any] | None,
    hits: list[str],
    block_names: list[str],
    adult_terms: tuple[str, ...],
) -> bool:
    """成人内容是否集中在某个固定分类（如「伦理片」）。

    判定条件：
    1) 首页分类里命中成人词的只占少数（还有大量正常分类）；
    2) 命中的成人分类全部属于可屏蔽的固定类型；
    3) 其它成人命中（探针/片名）也都落在这些固定类型里。
    满足才认为可以「只屏蔽分类、保留源」，否则按纯色情源整源剔除。
    """
    if not quality:
        return False
    classes = [str(c) for c in (quality.get("classes") or [])]
    if not classes:
        return False
    # 隐藏类型 id（首页没列出、但内容全是色情，如瓜子APP 的 75）：
    # 只要还有正常分类，就可以按 id 屏蔽该类型、保留源。
    if quality.get("adult_type_ids"):
        return True
    if not hits or not block_names:
        return False

    def is_adult_class(name: str) -> bool:
        text = name.strip()
        if not text:
            return False
        return text in ADULT_CATEGORY_EXACT or any(
            term and term in text for term in adult_terms
        )

    adult_classes = [c for c in classes if is_adult_class(c)]
    if not adult_classes or len(adult_classes) >= len(classes):
        return False
    def in_block(text: str) -> bool:
        return any(b in text or text in b for b in block_names)

    if not all(in_block(c) for c in adult_classes):
        return False
    # 搜索/探针命中的成人词必须也能归到可屏蔽分类（含「伦理」这类子词），
    # 否则说明色情内容不只在这一个分类里，不能只靠分类屏蔽。
    if any(not in_block(h) for h in hits):
        return False
    return True


def effective_grade(
    quality: dict[str, Any] | None, thresholds: dict[str, float] | None = None
) -> str:
    """把功能校验结果换算成 A/B/C/D，无法验证画质的返回 U。

    质量等级**只按画质（码率/分辨率/bpp）+ 速度**，不看链接类型（直链/解析/page）。
    用 stream_check.grade_of 对每个 stream 重算（不依赖旧 stream.grade 链接类型值）。
    thresholds 可覆盖分级阈值（方向4动态阈值，默认 GRADE_THRESHOLDS）。

    优先看所有采样线路（line_streams），取其中最好的等级：实测华谊影视的
    第一条线路经常连接失败，但 K蓝光线路正常，只看第一条会误判成 U。
    没有 line_streams 时退回单条 stream。
    """
    streams: list[dict[str, Any]] = []
    for entry in (quality or {}).get("line_streams") or []:
        stream = entry.get("stream") or {}
        if stream:
            streams.append(stream)
    if not streams:
        stream = (quality or {}).get("stream") or {}
        if stream:
            streams.append(stream)
    grades: list[str] = []
    for stream in streams:
        grade = stream_check.grade_of(stream, thresholds)
        kind = str(stream.get("kind") or "")
        if grade and kind and kind not in ("local", "unknown"):
            grades.append(grade)
    if not grades:
        return "U"
    rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    return min(grades, key=lambda grade: rank.get(grade, 9))


VIDEO_KINDS = ("hls", "mp4", "video")


def quality_sort_key(
    result: ScriptResult, thresholds: dict[str, float] | None = None
) -> tuple:
    """站点排序：等级（A>B>C>D>U）→ 最高 bpp（画质密度）→ 最快速度比 → 名称。

    用户标准：三方法（search/detail/player）是硬门槛（任一失败=源废，不进评分），
    homeContent/分类不重要。通过门槛后只按**画质**（最高，bpp 归一化）→ **加载速度**
    排名，功能 score 不参与（score 只作门槛判定的诊断，不是评分项）。

    bpp = 码率 ÷ (宽×高×fps)，把分辨率/帧率归一化，比绝对码率更能反映真实画质：
    720p@2500kbps 的 bpp 是 1080p@2500kbps 的两倍多，应排前面；绝对码率会高估
    高分辨率低码率源（如 1080p 但 2309kbps 的采集聚合）。
    """
    quality = result.quality or {}
    grade = effective_grade(quality, thresholds)
    grade_rank = {"A": 0, "B": 1, "C": 2, "D": 3, "U": 4, "": 4}.get(grade, 4)
    best_bpp = 0.0
    best_speed = 0.0
    for entry in quality.get("line_streams") or []:
        stream = entry.get("stream") or {}
        best_bpp = max(best_bpp, stream_bpp(stream))
        best_speed = max(best_speed, float(stream.get("speed_ratio") or 0))
    return (grade_rank, -best_bpp, -best_speed, result.name)


def dynamic_grade_thresholds(
    quality_map: dict[str, dict[str, Any]],
    base: dict[str, float] | None = None,
) -> dict[str, float]:
    """按源池实际分布算动态分级阈值（bpp/speed 分位数）。

    方向4：固定阈值（bpp 0.10/0.05）可能不适合源池变化。按高质量线路的
    bpp/speed 分布取分位数自适应：bpp_a=P75、bpp_b=P50、speed_a=P75、
    speed_b=P50。取 max(分位数, 默认) 只收紧不放宽（保证「只留高质量」），
    且限制在默认值的 2 倍内（避免某周源池异常导致阈值过激）。

    只统计视频线路（音频无分辨率、local/unknown 无法验证）。
    """
    base = {**stream_check.GRADE_THRESHOLDS, **(base or {})}
    bpps: list[float] = []
    speeds: list[float] = []
    for quality in quality_map.values():
        for entry in quality.get("line_streams") or []:
            stream = entry.get("stream") or {}
            kind = str(stream.get("kind") or "")
            if kind in ("audio", "local", "unknown"):
                continue
            if not stream.get("bitrate_kbps") or not stream.get("width") or not stream.get("height"):
                continue
            bpps.append(stream_bpp(stream))
            speeds.append(float(stream.get("speed_ratio") or 0))
    if not bpps:
        return dict(base)
    bpps.sort()
    speeds.sort()

    def pct(arr: list[float], p: float) -> float:
        return arr[min(int(len(arr) * p), len(arr) - 1)]

    def clamp(value: float, default: float) -> float:
        """只收紧不放宽，且不超过默认 2 倍。"""
        return min(max(value, default), default * 2)

    return {
        "bpp_a": clamp(pct(bpps, 0.75), base["bpp_a"]),
        "bpp_b": clamp(pct(bpps, 0.50), base["bpp_b"]),
        "speed_a": clamp(pct(speeds, 0.75), base["speed_a"]),
        "speed_b": clamp(pct(speeds, 0.50), base["speed_b"]),
        "bpp_c": base["bpp_c"],
        "res_a": base["res_a"], "res_b": base["res_b"], "res_c": base["res_c"],
        "ref_pixels": base["ref_pixels"],
        "audio_bitrate_a": base["audio_bitrate_a"],
        "audio_speed_a": base["audio_speed_a"],
        "audio_bitrate_b": base["audio_bitrate_b"],
    }


def line_grade_order(quality: dict[str, Any] | None) -> list[str]:
    """按画质速度重排线路名（最优在前）。

    线路级推荐：TVBox 默认播 vod_play_url 第一条，把画质速度最好的线路排第一。
    只排有画质数据的线路（grade_of 可判）；未知线路不在 order 里，注入时
    稳定保持原序后置。同一 grade 内按 bpp（画质密度）→ 速度排序。
    """
    if not quality:
        return []
    scored: list[tuple[float, float, float, str]] = []
    for entry in quality.get("line_streams") or []:
        flag = str(entry.get("flag") or "").strip()
        stream = entry.get("stream") or {}
        if not flag or not stream:
            continue
        grade = stream_check.grade_of(stream)
        rank = {"A": 0, "B": 1, "C": 2, "D": 3, "U": 4}.get(grade, 4)
        scored.append(
            (rank, -stream_bpp(stream), -float(stream.get("speed_ratio") or 0), flag)
        )
    scored.sort()
    return [flag for _, _, _, flag in scored]


def resolution_threshold(
    stream: dict[str, Any],
    default_kbps: float,
    thresholds: dict[str, Any] | None = None,
) -> float:
    """按分辨率返回最低达标码率。

    码率档按**长边**（max(宽,高)）判：码率需求随水平分辨率/像素数增长，
    2.35:1 电影 1280x544（69.6 万像素，接近 720p）按 1280 档要 2000kbps——
    1831kbps 不达标被剔（用户实测）。竖屏短剧 720x1280 长边 1280 → 720p 档。
    这与画质分级（grade_of 用**短边**判清晰度）是不同维度：清晰度看短边
    （1920x1080=1080p），码率门槛看长边/像素数（决定数据量），不矛盾。
    分辨率未知时退回 default_kbps。
    """
    table = thresholds or DEFAULT_BITRATE_THRESHOLDS
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    long_edge = max(width, height) if width and height else height
    if long_edge <= 0:
        return float(default_kbps)
    best: tuple[int, float] | None = None
    for key, value in table.items():
        try:
            level = int(key)
        except (TypeError, ValueError):
            continue
        if long_edge >= level and (best is None or level > best[0]):
            best = (level, float(value))
    if best is not None:
        return best[1]
    # 比最低档还小（240p 之类），用最低档的阈值。
    try:
        return float(min(float(value) for value in table.values()))
    except ValueError:
        return float(default_kbps)


def stream_fps(stream: dict[str, Any]) -> float:
    """取 ffprobe 读到的帧率；取不到或异常时按 25 算。

    实测绝大多数源是 25fps，少数 24/30 对阈值影响 <20%。
    """
    try:
        fps = float(stream.get("fps") or 0)
    except (TypeError, ValueError):
        fps = 0.0
    return fps if 0 < fps <= 120 else 25.0


def stream_bpp(stream: dict[str, Any], bitrate: int | None = None) -> float:
    """算实际 bpp（每像素每帧的比特数），用于和 min_bpp 比较。"""
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    kbps = int(bitrate if bitrate is not None else (stream.get("bitrate_kbps") or 0))
    if not (width and height and kbps):
        return 0.0
    return kbps * 1000.0 / (width * height * stream_fps(stream))


def bitrate_verdict(
    quality: dict[str, Any] | None,
    min_kbps: float,
    thresholds: dict[str, Any] | None = None,
    min_bpp: float = 0.0,
) -> dict[str, Any]:
    """判断一个源的所有采样线路是否都低于对应分辨率的最低码率。

    只有「每条视频线路都测到了码率，且都低于阈值」才算低码率源。
    有任何一条线路测不出来（解析线路、页面、超时）就保留——没测到不等于低。
    音频源（听书/音乐）不参与码率判定。

    min_bpp > 0 时，阈值取 max(分辨率档阈值, min_bpp × 宽 × 高 × fps / 1000)，
    用来挡住「1080p 但码率只有 1.6–1.8 Mbps」的低端转码源。
    """
    verdict: dict[str, Any] = {
        "lines": [],
        "measured": 0,
        "unknown": 0,
        "untested": 0,
        "all_low": False,
    }
    if not quality:
        return verdict
    entries = list(quality.get("line_streams") or [])
    if not entries:
        stream = quality.get("stream") or {}
        if stream:
            entries = [{"flag": "", "stream": stream}]
    measured = 0
    unknown = 0
    for entry in entries:
        stream = entry.get("stream") or {}
        kind = str(stream.get("kind") or "")
        if kind == "audio":
            continue
        bitrate = int(stream.get("bitrate_kbps") or 0)
        if kind in VIDEO_KINDS and bitrate > 0:
            measured += 1
            limit = resolution_threshold(stream, min_kbps, thresholds)
            actual_bpp = stream_bpp(stream, bitrate)
            if min_bpp > 0 and stream.get("width") and stream.get("height"):
                limit = max(
                    limit,
                    min_bpp
                    * int(stream["width"])
                    * int(stream["height"])
                    * stream_fps(stream)
                    / 1000.0,
                )
            low = bitrate < limit
        else:
            limit = 0.0
            actual_bpp = 0.0
            unknown += 1
            low = False
        verdict["lines"].append(
            {
                "flag": str(entry.get("flag") or ""),
                "kind": kind,
                "bitrate_kbps": bitrate,
                "min_kbps": round(limit),
                "bpp": round(actual_bpp, 4),
                "fps": float(stream.get("fps") or 0),
                "width": int(stream.get("width") or 0),
                "height": int(stream.get("height") or 0),
                "low": low,
            }
        )
    verdict["measured"] = measured
    # 没测到的线路（解析线路、超出 max_lines 的线路）一律按「未知」处理，源保留。
    raw_lines = list(quality.get("lines") or [])
    untested = max(0, len(raw_lines) - len(entries))
    declared = int(quality.get("play_from") or 0)
    if declared > len(raw_lines):
        untested += declared - len(raw_lines)
    verdict["untested"] = untested
    verdict["unknown"] = unknown + untested
    verdict["all_low"] = bool(measured) and verdict["unknown"] == 0 and all(
        item["low"] for item in verdict["lines"]
    )
    return verdict


def speed_verdict(
    quality: dict[str, Any] | None,
    min_ratio: float,
    max_startup_ms: int,
) -> dict[str, Any]:
    """判断一个源的所有采样线路是不是都加载慢。

    每条线路看两个指标，任一不达标就算慢：
    - `speed_ratio`（实测吞吐 / 码率）低于 min_ratio；
    - `playlist_ms + ttfb_ms` 超过 max_startup_ms（点开要等太久）。

    和码率过滤一样：只有「每条视频线路都测到了速度，且都慢」才剔除。
    有任何一条线路测不出来（解析线路、页面、超时）就保留——没测到不等于慢。
    音频源不参与判定。
    """
    verdict: dict[str, Any] = {
        "lines": [],
        "measured": 0,
        "unknown": 0,
        "untested": 0,
        "all_slow": False,
    }
    if not quality:
        return verdict
    entries = list(quality.get("line_streams") or [])
    if not entries:
        stream = quality.get("stream") or {}
        if stream:
            entries = [{"flag": "", "stream": stream}]
    measured = 0
    unknown = 0
    for entry in entries:
        stream = entry.get("stream") or {}
        kind = str(stream.get("kind") or "")
        if kind == "audio":
            continue
        ratio = float(stream.get("speed_ratio") or 0)
        if kind in VIDEO_KINDS and ratio > 0:
            measured += 1
            playlist_ms = int(stream.get("playlist_ms") or 0)
            ttfb_ms = int(stream.get("ttfb_ms") or 0)
            startup_ms = playlist_ms + ttfb_ms
            slow = ratio < min_ratio or startup_ms > max_startup_ms
        else:
            ratio = 0.0
            playlist_ms = 0
            ttfb_ms = 0
            startup_ms = 0
            unknown += 1
            slow = False
        verdict["lines"].append(
            {
                "flag": str(entry.get("flag") or ""),
                "kind": kind,
                "speed_kbps": int(stream.get("speed_kbps") or 0),
                "speed_ratio": round(ratio, 2),
                "playlist_ms": playlist_ms,
                "ttfb_ms": ttfb_ms,
                "startup_ms": startup_ms,
                "slow": slow,
            }
        )
    verdict["measured"] = measured
    raw_lines = list(quality.get("lines") or [])
    untested = max(0, len(raw_lines) - len(entries))
    declared = int(quality.get("play_from") or 0)
    if declared > len(raw_lines):
        untested += declared - len(raw_lines)
    verdict["untested"] = untested
    verdict["unknown"] = unknown + untested
    verdict["all_slow"] = bool(measured) and verdict["unknown"] == 0 and all(
        item["slow"] for item in verdict["lines"]
    )
    return verdict


# ---------------------------------------------------------------------------
# 线路级裁减：把脚本里「不通 / 明显低于质量线」的线路从播放列表里去掉。
# 采用运行时注入：在脚本末尾包一层 detailContent，按线路名过滤。
# ---------------------------------------------------------------------------

# 标记注入代码块，用于识别「本仓库生成过、可安全清理」的本地脚本。
LINE_FILTER_MARKER = "# ---- TVBox 本地线路过滤（自动生成，勿改） ----"

# 成人分类过滤：色情内容集中在单一分类（如「伦理片」）的混合源，
# 只屏蔽该分类，不整源剔除。注入后在三个入口生效：
# ① homeContent 去掉该分类；② categoryContent 拒绝该 tid；
# ③ homeVideoContent / searchContent 过滤该分类的资源。
CATEGORY_FILTER_MARKER = "# ---- TVBox 成人分类过滤（自动生成，勿改） ----"

# 两振出局：源要连续两轮被判「要剔除」才真剔除；第一轮保留（strike1）。
# 源级剔除状态：命中即剔除（立即生效，不走两振）。
# 资源站（resource_station）是结构性属性——线路的 CDN/名字固定，不像速度会抖动，
# 一轮就能确定，且项目定位是「剔除低质源」，严格过滤立即剔。
HISTORY_REMOVE_STATUSES = {"low_quality", "low_bitrate", "slow_stream", "resource_station", "parse_required"}
HISTORY_MAX_ROUNDS = 8


def load_history(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"rounds": [], "streaks": {}, "line_low": {}, "line_dead": {}}
    if not isinstance(data, dict):
        return {"rounds": [], "streaks": {}, "line_low": {}, "line_dead": {}}
    data.setdefault("rounds", [])
    data.setdefault("streaks", {})
    data.setdefault("line_low", {})
    data.setdefault("line_dead", {})
    return data


def save_history(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data, "\n")


def apply_two_strike(
    results: list[ScriptResult], history: dict[str, Any]
) -> tuple[dict[str, str], dict[str, str]]:
    """源级质量剔除：立即生效（不走两振）。

    min_grade/drop_unverified/码率/速度过滤判定的 low_quality/low_bitrate/slow_stream
    源直接剔除，不再首轮保留——项目定位是「只留高质量」，C/D/U 级源首轮就应筛掉。
    两振历史仅记录连续剔除轮数（供统计/将来恢复判断），不影响本轮结果。
    返回 (本轮最终 streaks, 本轮最终 statuses)。
    """
    streaks = {str(k): int(v) for k, v in (history.get("streaks") or {}).items()}
    new_streaks: dict[str, str] = {}
    statuses: dict[str, str] = {}
    for result in results:
        name = result.filename
        if result.status in HISTORY_REMOVE_STATUSES:
            # 立即剔除：保持剔除状态（status 不回退 valid），只累积 streak 历史。
            streak = streaks.get(name, 0) + 1
            result.strike = streak
            result.pending = result.status
            new_streaks[name] = str(streak)
        else:
            new_streaks[name] = "0"
        statuses[name] = result.status
    return new_streaks, statuses


def line_prune_drops(
    quality: dict[str, Any] | None,
    line_prune_cfg: dict[str, Any] | None,
    min_kbps: float,
    thresholds: dict[str, Any] | None,
    min_bpp: float,
    source: str = "",
    prev_low: set[str] | None = None,
    prev_dead: set[str] | None = None,
    skip_quality: bool = False,
    min_speed_ratio: float = 0.0,
    max_startup_ms: int = 0,
    skip_speed: bool = False,
) -> tuple[dict[str, str], set[str], set[str]]:
    """计算线路裁减，返回 (要剔除的 {线路名: 原因}, 本轮低质量集合, 本轮疑似不通集合)。

    剔除规则：
    - **不可用**：HTTP >= 400，且**上一轮同样是 4xx/5xx**（连续两轮）才剔除。
      单集 token 过期是 403/404 误报（华谊 K蓝光某集 403、换集就 200），一振不删。
    - **低码率**：码率低于阈值（且同源另有达标线路），**一振即剔**——码率是
      稳定属性（不像速度/HTTP 抖动），实测确认的低码率源不再等两振。
    - **慢速**：加载速度低于阈值（且同源另有快速线路），**连续两轮**慢速才剔。
    - 手动黑名单在调用方直接加入，不经过两振。
    """
    drops: dict[str, str] = {}
    current_low: set[str] = set()
    current_dead: set[str] = set()
    prev_low = prev_low or set()
    prev_dead = prev_dead or set()
    if not quality:
        return drops, current_low, current_dead

    dead_min = int((line_prune_cfg or {}).get("dead_status_min") or 0)
    entries = list(quality.get("line_streams") or [])

    def key(flag: str) -> str:
        return f"{source}::{flag}"

    # 1) 不可用线路：>=400 一振记录；连续两轮（上一轮也在 dead 集合）才剔除。
    playable: set[str] = set()
    for entry in entries:
        stream = entry.get("stream") or {}
        flag = str(entry.get("flag") or "").strip()
        if not flag:
            continue
        status = int(stream.get("status") or 0)
        if not (dead_min and status >= dead_min):
            playable.add(flag)
    for entry in entries:
        stream = entry.get("stream") or {}
        flag = str(entry.get("flag") or "").strip()
        if not flag:
            continue
        status = int(stream.get("status") or 0)
        if status >= 400:
            current_dead.add(flag)
            # 立即剔除：dead_status_min>0 且整源还有可玩线路；或连续两轮 4xx。
            immediate = bool(dead_min and status >= dead_min and playable)
            if (immediate or key(flag) in prev_dead) and flag not in drops:
                drops[flag] = f"HTTP {status}" + ("" if immediate else "（连续两轮）")

    # 2) 低码率线路：仅当同源存在至少一条达标线路时删（一振即剔，码率稳定）。
    if not skip_quality:
        passing: list[str] = []
        failing: list[tuple[str, int, float]] = []
        for entry in entries:
            stream = entry.get("stream") or {}
            kind = str(stream.get("kind") or "")
            if kind not in VIDEO_KINDS:
                continue
            bitrate = int(stream.get("bitrate_kbps") or 0)
            if bitrate <= 0:
                continue  # 没测到码率，未知，不动。
            flag = str(entry.get("flag") or "").strip()
            if not flag:
                continue
            limit = resolution_threshold(stream, min_kbps, thresholds)
            if min_bpp > 0 and stream.get("width") and stream.get("height"):
                limit = max(
                    limit,
                    min_bpp
                    * int(stream["width"])
                    * int(stream["height"])
                    * stream_fps(stream)
                    / 1000.0,
                )
            if bitrate >= limit:
                passing.append(flag)
            else:
                failing.append((flag, bitrate, limit))
        if passing and failing:
            for flag, bitrate, limit in failing:
                current_low.add(flag)
                # 码率是稳定属性（不像速度/HTTP 会抖动），且同源另有达标线路，
                # 一振即剔：实测确认的低码率源不应再等一轮（用户反馈优先）。
                if flag not in drops:
                    drops[flag] = f"{bitrate}kbps<{round(limit)}kbps"

        # 2b) 慢速线路：与码率同逻辑——同源另有快速线路才删；连续两轮慢速才删。
        # 只对测到速度的线路判定；没测到的按未知处理，不删也不会被当作「快速」。
        if not skip_speed and (min_speed_ratio > 0 or max_startup_ms > 0):
            fast: list[str] = []
            slow_lines: list[tuple[str, float, int]] = []
            for entry in entries:
                stream = entry.get("stream") or {}
                kind = str(stream.get("kind") or "")
                if kind not in VIDEO_KINDS:
                    continue
                flag = str(entry.get("flag") or "").strip()
                if not flag:
                    continue
                speed_ratio = float(stream.get("speed_ratio") or 0)
                startup = int(stream.get("playlist_ms") or 0) + int(
                    stream.get("ttfb_ms") or 0
                )
                if speed_ratio <= 0 and startup <= 0:
                    continue  # 没测到速度，未知，不动。
                is_slow = (
                    min_speed_ratio > 0 and speed_ratio > 0 and speed_ratio < min_speed_ratio
                ) or (max_startup_ms > 0 and startup > max_startup_ms)
                if is_slow:
                    slow_lines.append((flag, speed_ratio, startup))
                else:
                    fast.append(flag)
            if fast and slow_lines:
                for flag, speed_ratio, startup in slow_lines:
                    current_low.add(flag)
                    if key(flag) in prev_low and flag not in drops:
                        reason = f"speed {speed_ratio:g}x"
                        if startup > max_startup_ms:
                            reason += f"/{startup}ms"
                        drops[flag] = f"{reason}（连续两轮）"

    # 不剔空源：若全部线路都被剔，保留最优一条（最高码率、非不可用优先），
    # 避免源无可播线路。码率检查的「达标线」可能被速度检查剔、速度检查的
    # 「快速线」可能被码率检查剔——两套检查互不感知，需最后兜底。
    if drops and entries:
        flags = [
            str(e.get("flag") or "").strip()
            for e in entries
            if str(e.get("flag") or "").strip()
        ]
        if flags and all(f in drops for f in flags):
            alive = [
                e
                for e in entries
                if int((e.get("stream") or {}).get("status") or 0) < 400
                and str(e.get("flag") or "").strip() in drops
            ]
            pool = alive or [
                e for e in entries if str(e.get("flag") or "").strip() in drops
            ]
            if pool:
                best = max(
                    pool,
                    key=lambda e: int((e.get("stream") or {}).get("bitrate_kbps") or 0),
                )
                best_flag = str(best.get("flag") or "").strip()
                if best_flag in drops:
                    drops.pop(best_flag)
                    current_low.discard(best_flag)
    return drops, current_low, current_dead


def inject_line_filter(
    source: str,
    drop_flags: list[str],
    line_order: list[str] | None = None,
    zy_sigs: dict[str, Any] | None = None,
) -> str:
    """在脚本末尾注入线路过滤 + 重排代码。

    不带 drop 时只打标记（方便后续清理）；line_order 非空时按画质速度重排
    线路（最优在前，TVBox 默认播第一条），未知线路保持原序后置。
    zy_sigs 非空时，额外内联资源站 URL 签名，运行时按播放 URL 实时判定——
    动态 API 脚本（如猎手）的线路名每次请求都可能变，静态名字名单挡不住，
    但资源站 CDN host 是固定的，按 URL 判定可覆盖所有动态线路。
    """
    marker = LINE_FILTER_MARKER
    if marker in source:
        source = source.split(marker)[0].rstrip("\n")
    header = f"\n\n{marker}\n"
    order = [str(f) for f in (line_order or []) if str(f).strip()]
    if not drop_flags and not order and not zy_sigs:
        return source + header
    lines: list[str] = [
        header.rstrip("\n"),
        f"_TVBOX_DROP_LINES = {json.dumps(sorted(drop_flags), ensure_ascii=False)}",
        f"_TVBOX_LINE_ORDER = {json.dumps(order, ensure_ascii=False)}",
        "",
    ]
    if zy_sigs:
        # 内联资源站签名：CDN host 关键词 + 采集 API 正则 + lzv 数字规则。
        # 只按 URL 判定，不按名字（名字动态变化）；音频源走本地代理/音乐 CDN，
        # 不会命中资源站签名，天然豁免。
        lines.extend([
            "_TVBOX_ZY_ENABLED = True",
            "_TVBOX_ZY_CDN = " + json.dumps(zy_sigs.get("cdn") or [], ensure_ascii=False),
            "_TVBOX_ZY_API = " + json.dumps(zy_sigs.get("api") or "", ensure_ascii=False),
            "_TVBOX_ZY_CODES = " + json.dumps(zy_sigs.get("exact_codes") or [], ensure_ascii=False),
            "_TVBOX_ZY_KW = " + json.dumps(zy_sigs.get("keywords") or [], ensure_ascii=False),
            "_TVBOX_ZY_NEG = " + json.dumps(zy_sigs.get("negatives") or [], ensure_ascii=False),
            "",
            "def _tvbox_is_zy_url(url, flag=''):",
            "    import re, urllib.parse",
            "    u = str(url or '')",
            "    f = str(flag or '').strip()",
            "    if re.search(_TVBOX_ZY_API, u, re.I):",
            "        return True",
            "    # 播放地址可能是多集拼接串：'第01集$https://a.com/x.m3u8#第02集$https://b.com/y.m3u8'",
            "    # 必须逐段提取 URL 再取 host，不能对整个串 urlparse（取不到 host）。",
            "    hosts = set()",
            "    for seg in re.split(r'[#$]', u):",
            "        seg = seg.strip()",
            "        if seg.startswith('http://') or seg.startswith('https://'):",
            "            try:",
            "                parsed = urllib.parse.urlparse(seg)",
            "                h = (parsed.hostname or '').lower()",
            "            except Exception:",
            "                h = ''; parsed = None",
            "            # 本地代理型脚本（如 APP影院1）：真实地址藏在 url= 参数里，",
            "            # 需解码后再提取 host，否则只会拿到 127.0.0.1 而漏判。",
            "            if parsed and h in ('127.0.0.1', 'localhost', '::1'):",
            "                qs = urllib.parse.parse_qs(parsed.query)",
            "                real = (qs.get('url') or [''])[0]",
            "                if real.startswith('//'): real = 'https:' + real",
            "                if real.startswith('http://') or real.startswith('https://'):",
            "                    try:",
            "                        rh = (urllib.parse.urlparse(real).hostname or '').lower()",
            "                    except Exception:",
            "                        rh = ''",
            "                    if rh: hosts.add(rh)",
            "            if h:",
            "                hosts.add(h)",
            "            # 中转缓存型：真实 URL 拼在路径里（/cache/https://cdn/...），",
            "            # 取内层 host（如 47电影天堂 dl.gybkw.com/cache/https://c1.7bbffvip.com）。",
            "            im = re.search(r'/(https?://[^/?#]+)', seg)",
            "            if im:",
            "                ih = re.match(r'https?://([^/?]+)', im.group(1))",
            "                if ih:",
            "                    hosts.add(ih.group(1).split(':')[0].lower())",
            "    for h in hosts:",
            "        for p in _TVBOX_ZY_CDN:",
            "            if re.search(r'(^|[.\\-_])' + re.escape(p), h, re.I):",
            "                return True",
            "        if re.search(r'(^|[.\\-_])lzv\\d+', h, re.I):",
            "            return True",
            "    if hosts:",
            "        return False  # 有真实 host 但没命中 CDN → 自有线路，不靠名字",
            "    # 无 host（占位符型脚本，detail 给相对路径/id）：回退到线路名判定。",
            "    # 官方/自营字样优先豁免，避免误伤。",
            "    if any(neg in f for neg in _TVBOX_ZY_NEG):",
            "        return False",
            "    if f.upper() in _TVBOX_ZY_CODES:",
            "        return True",
            "    if any(kw in f for kw in _TVBOX_ZY_KW):",
            "        return True",
            "    if re.search(r'(?i)\\b(LZ|FF|BF|HF|HN|YZ|DY|MY|IK|WL|TK|IQY|XL|WJ|BD|DB|SB|SN|MZ|PL)(?:线路|线)', f):",
            "        return True",
            "    return False",
            "",
        ])
    else:
        lines.extend(["_TVBOX_ZY_ENABLED = False", ""])
    lines.extend([
        "def _tvbox_filter_lines(result, drop):",
        "    if not isinstance(result, dict):",
        "        return result",
        "    items = result.get('list')",
        "    if isinstance(items, list):",
        "        for item in items:",
        "            _tvbox_filter_item(item, drop)",
        "    else:",
        "        _tvbox_filter_item(result, drop)",
        "    return result",
        "",
        "def _tvbox_filter_item(item, drop):",
        "    froms = item.get('vod_play_from') or ''",
        "    urls = item.get('vod_play_url') or ''",
        "    if not isinstance(froms, str) or not isinstance(urls, str):",
        "        return",
        "    if '$$$' not in froms:",
        "        return",
        "    parts_from = [f.strip() for f in froms.split('$$$')]",
        "    parts_url = urls.split('$$$')",
        "    if len(parts_from) != len(parts_url):",
        "        return",
        "    if _TVBOX_ZY_ENABLED:",
        "        keep = [(f, u) for f, u in zip(parts_from, parts_url)",
        "                if f not in drop and not _tvbox_is_zy_url(u, f)]",
        "    else:",
        "        keep = [(f, u) for f, u in zip(parts_from, parts_url) if f not in drop]",
        "    if not keep or len(keep) == len(parts_from):",
        "        return",
        "    item['vod_play_from'] = '$$$'.join(f for f, _ in keep)",
        "    item['vod_play_url'] = '$$$'.join(u for _, u in keep)",
        "",
        "def _tvbox_sort_lines(result, order):",
        "    if not order or not isinstance(result, dict):",
        "        return result",
        "    items = result.get('list')",
        "    if isinstance(items, list):",
        "        for item in items:",
        "            _tvbox_sort_item(item, order)",
        "    else:",
        "        _tvbox_sort_item(result, order)",
        "    return result",
        "",
        "def _tvbox_sort_item(item, order):",
        "    froms = item.get('vod_play_from') or ''",
        "    urls = item.get('vod_play_url') or ''",
        "    if not isinstance(froms, str) or not isinstance(urls, str):",
        "        return",
        "    if '$$$' not in froms:",
        "        return",
        "    parts_from = [f.strip() for f in froms.split('$$$')]",
        "    parts_url = urls.split('$$$')",
        "    if len(parts_from) != len(parts_url):",
        "        return",
        "    known = {f: i for i, f in enumerate(order)}",
        "    pairs = list(zip(parts_from, parts_url))",
        "    # 已知线路按 order（画质速度最优在前），未知线路稳定保持原序后置。",
        "    pairs.sort(key=lambda p: known.get(p[0], len(order)))",
        "    item['vod_play_from'] = '$$$'.join(f for f, _ in pairs)",
        "    item['vod_play_url'] = '$$$'.join(u for _, u in pairs)",
        "",
        "def _tvbox_apply(cls):",
        "    fn = getattr(cls, 'detailContent', None)",
        "    if fn is None:",
        "        return",
        "    def wrapper(self, *a, _fn=fn, **k):",
        "        res = _tvbox_filter_lines(_fn(self, *a, **k), _TVBOX_DROP_LINES)",
        "        return _tvbox_sort_lines(res, _TVBOX_LINE_ORDER)",
        "    setattr(cls, 'detailContent', wrapper)",
        "",
        "_tvbox_apply(Spider)",
        "",
    ])
    return source + "\n" + "\n".join(lines)


def inject_category_filter(
    source: str, categories: list[str], type_ids: list[str] | None = None
) -> str:
    """给混合源注入三点成人分类过滤。

    只用于色情内容集中在单一分类的源：
    ① homeContent 去掉该分类；② categoryContent 拒绝该 tid；
    ③ homeVideoContent / searchContent 过滤该分类的资源。
    支持按分类名（如「伦理片」）或隐藏类型 id（如瓜子APP 的 75）。
    """
    marker = CATEGORY_FILTER_MARKER
    if marker in source:
        source = source.split(marker)[0].rstrip("\n")
    block_json = json.dumps(
        [str(c) for c in categories if str(c).strip()], ensure_ascii=False
    )
    id_json = json.dumps(
        [str(x) for x in (type_ids or []) if str(x).strip()], ensure_ascii=False
    )
    code = """

""" + marker + """
_TVBOX_CAT_BLOCK = """ + block_json + """
_TVBOX_CAT_IDS = """ + id_json + """

def _tvbox_cat_hit(value):
    text = str(value or "")
    for name in _TVBOX_CAT_BLOCK:
        if name and name in text:
            return True
    return False

def _tvbox_cat_text(item):
    if not isinstance(item, dict):
        return ""
    return " ".join(str(item.get(k) or "") for k in ("type_name", "vod_class", "class", "category"))

def _tvbox_cat_item_hit(item):
    if not isinstance(item, dict):
        return False
    if _tvbox_cat_hit(_tvbox_cat_text(item)):
        return True
    for key in ("t_id", "d_type", "type_id", "tid"):
        if str(item.get(key) or "") in _TVBOX_CAT_IDS:
            return True
    return False

def _tvbox_cat_filter_raw(result):
    if isinstance(result, dict):
        for key in ("list", "vod"):
            arr = result.get(key)
            if isinstance(arr, list):
                result[key] = [it for it in arr if not _tvbox_cat_item_hit(it)]
    return result

def _tvbox_cat_filter_payload(payload):
    if isinstance(payload, dict) and isinstance(payload.get("list"), list):
        payload["list"] = [it for it in payload["list"] if not _tvbox_cat_item_hit(it)]
    return payload

def _tvbox_install_cat_filter(cls):
    originals = {}
    for name in ("homeContent", "categoryContent", "homeVideoContent", "searchContent"):
        fn = cls.__dict__.get(name)
        if callable(fn):
            originals[name] = fn

    def blocked_ids(spider):
        ids = getattr(spider, "_tvbox_blocked_ids", None)
        if ids is not None:
            return ids
        ids = set(_TVBOX_CAT_IDS)
        fn = originals.get("homeContent")
        if fn:
            try:
                payload = fn(spider, False)
                for c in (payload or {}).get("class") or []:
                    if _tvbox_cat_item_hit(c):
                        ids.add(str((c or {}).get("type_id")))
            except Exception:
                pass
        spider._tvbox_blocked_ids = ids
        return ids

    if "homeContent" in originals:
        def home(self, *a, **kw):
            payload = _tvbox_cat_filter_payload(originals["homeContent"](self, *a, **kw))
            if isinstance(payload, dict):
                classes = payload.get("class")
                if isinstance(classes, list):
                    removed = {str((c or {}).get("type_id")) for c in classes if _tvbox_cat_item_hit(c)}
                    payload["class"] = [c for c in classes if not _tvbox_cat_item_hit(c)]
                    filters = payload.get("filters")
                    if isinstance(filters, dict):
                        for tid in removed:
                            filters.pop(tid, None)
            return payload
        setattr(cls, "homeContent", home)

    if "categoryContent" in originals:
        def category(self, tid, *a, **kw):
            if str(tid) in blocked_ids(self):
                pg = kw.get("pg") or (a[0] if a else 1)
                try:
                    pg = int(pg)
                except Exception:
                    pg = 1
                return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}
            return _tvbox_cat_filter_payload(originals["categoryContent"](self, tid, *a, **kw))
        setattr(cls, "categoryContent", category)

    for name in ("homeVideoContent", "searchContent"):
        if name in originals:
            def make(fn):
                def wrapped(self, *a, **kw):
                    return _tvbox_cat_filter_payload(fn(self, *a, **kw))
                return wrapped
            setattr(cls, name, make(originals[name]))

    # MacCMS _api / fetch 返回的原始 list 带分类字段，先过滤再归一化。
    for name in tuple(dir(cls)):
        if not (
            name.endswith("_api")
            or name in ("fetch", "get_data", "request", "api")
        ):
            continue
        fn = cls.__dict__.get(name)
        if not callable(fn):
            continue
        def make_api(fn):
            def wrapped(self, *a, **kw):
                return _tvbox_cat_filter_raw(fn(self, *a, **kw))
            return wrapped
        setattr(cls, name, make_api(fn))

_tvbox_install_cat_filter(Spider)
"""
    return source.rstrip("\n") + code


def write_local_spiders(
    kept: list[ScriptResult],
    config: dict[str, Any],
    quality_map: dict[str, dict[str, Any]],
    script_out: Path,
    write: bool = True,
    prev_low: set[str] | None = None,
    prev_dead: set[str] | None = None,
    managed_scripts: set[str] | None = None,
    protect_scripts: set[str] | None = None,
) -> tuple[dict[str, dict[str, str]], set[str], set[str]]:
    """把保留的源脚本写入本地目录并注入线路过滤。

    返回 (每个源的 {flag: reason}, 本轮低质量 `source::flag` 集合, 本轮疑似不通集合)。
    write=False 时只计算不落盘（dry-run），也不清理旧文件。
    """
    script_out.mkdir(parents=True, exist_ok=True)
    quality_cfg = config.get("quality") or {}
    quality_enabled = bool(quality_cfg.get("enabled", True))
    line_prune_cfg = quality_cfg.get("line_prune") or {}
    enabled = bool(line_prune_cfg.get("enabled"))
    blacklist = {
        str(k): {str(v).strip() for v in (val or [])}
        for k, val in (line_prune_cfg.get("blacklist") or {}).items()
    }
    min_kbps = float(quality_cfg.get("min_bitrate_kbps") or 0)
    min_bpp = float(quality_cfg.get("min_bpp") or 0)
    min_speed_ratio = float(quality_cfg.get("min_speed_ratio") or 0)
    max_startup_ms = int(quality_cfg.get("max_startup_ms") or 0)
    thresholds = dict(DEFAULT_BITRATE_THRESHOLDS)
    thresholds.update(quality_cfg.get("bitrate_thresholds") or {})
    bitrate_allow = {str(n) for n in (quality_cfg.get("bitrate_allow") or [])}
    speed_allow = {str(n) for n in (quality_cfg.get("speed_allow") or [])}
    zs_cfg = quality_cfg.get("resource_station") or {}
    zs_drop_lines = bool(zs_cfg.get("enabled")) and bool(zs_cfg.get("drop_lines"))
    zs_allow = {str(name) for name in (zs_cfg.get("allow") or [])}
    prev_low = prev_low or set()
    prev_dead = prev_dead or set()

    kept_files: set[str] = set()
    pruned: dict[str, dict[str, str]] = {}
    new_low: set[str] = set()
    new_dead: set[str] = set()
    for result in kept:
        if not result.source:
            continue
        filename = result.filename
        kept_files.add(filename)
        drops: dict[str, str] = {}
        if enabled:
            # quality.enabled=false 时关掉码率/速度线路裁剪，只留黑名单+资源站。
            skip_quality = not quality_enabled or filename in bitrate_allow
            skip_speed = not quality_enabled or filename in speed_allow
            auto, low_flags, dead_flags = line_prune_drops(
                quality_map.get(filename),
                line_prune_cfg,
                min_kbps,
                thresholds,
                min_bpp,
                source=filename,
                prev_low=prev_low,
                prev_dead=prev_dead,
                skip_quality=skip_quality,
                min_speed_ratio=min_speed_ratio,
                max_startup_ms=max_startup_ms,
                skip_speed=skip_speed,
            )
            new_low |= {f"{filename}::{f}" for f in low_flags}
            new_dead |= {f"{filename}::{f}" for f in dead_flags}
            for flag, reason in auto.items():
                drops.setdefault(flag, reason)
            # 资源站（采集站）线路剔除：混合源剔掉资源站线路、留自有线路。
            # 纯资源站源已在源级被剔（status=resource_station），不会走到这里；
            # 这里再加一道护栏：剔完不能把所有视频线路都删空（保留最优一条）。
            if zs_drop_lines and filename not in zs_allow:
                _q = quality_map.get(filename) or {}
                zs_cls = resource_station.classify_source(
                    _q.get("line_streams") or [],
                    declared_flags=_q.get("declared_flags"),
                    declared_total=int(_q.get("play_from") or 0),
                )
                declared = [
                    str(f).strip()
                    for f in (_q.get("declared_flags") or [])
                    if str(f).strip()
                ]
                # 资源站线路 = 采样识别（CDN/URL 证据）+ 声明线路名识别。
                # 猎手.py 采样 4 条全是资源站，但完整 17 条声明里还有官方线——
                # 只按采样算「剩余」会以为剔完没线路可留，从而放过天堂线路。
                zs_flags = {f for f in zs_cls["z_flags"] if f}
                # 声明名单里按名字识别出的资源站线路（如「站外-量子」「1080资源」）
                # 也要剔除——不管采样有没有采到它们。占位符型脚本（如 dd）采样时
                # 拿不到真实 CDN，但线路名已明确是资源站。名字信号本身即证据，
                # 音频线路名（无损/音质）不会匹配，天然安全。
                zs_flags |= {
                    f for f in declared
                    if resource_station.match_resource_station("", f)
                }
                video_flags = set(declared) or {f for f in zs_cls["video_flags"] if f}
                remaining = video_flags - zs_flags
                if zs_flags and remaining:
                    for flag in sorted(zs_flags):
                        drops.setdefault(flag, "资源站线路")
            # 黑名单剔除：放在资源站之后执行（用户要求的过滤顺序）。
            for flag in blacklist.get(filename, ()):
                drops.setdefault(flag, "手动配置")
            # 不剔空源（通用护栏）：上面三套检查（码率/速度/资源站）各自为政，
            # 可能把同源线路全删空（如猎手.py：暴风/魔都/索尼被码率剔、天堂线路被
            # 资源站剔，4 条全没了）。删空源等于给 TVBox 一个打不开的空源，比留一条
            # 低质线路更差。故全部命中时优先保留最优**自有线路**（严格过滤：资源站
            # 线路是低质源，不该被优先留）；确实只剩资源站线路时兜底保留最优一条。
            # 「所有线路都是资源站」的纯聚合源已在源级被剔（status=resource_station），
            # 不会走到这里。
            entries_all = (quality_map.get(filename) or {}).get("line_streams") or []
            declared_all = [
                str(f).strip()
                for f in ((quality_map.get(filename) or {}).get("declared_flags") or [])
                if str(f).strip()
            ]
            # 用完整声明线路名判断「是否全被剔」：猎手采样 4 条全被剔，但完整
            # 17 条里还有官方线，不该触发兜底保留资源站线路。
            all_flags = set(declared_all) or {
                str(e.get("flag") or "").strip()
                for e in entries_all
                if str(e.get("flag") or "").strip()
            }
            if all_flags and all(f in drops for f in all_flags):
                zs_flags_now = {
                    str(e.get("flag") or "").strip()
                    for e in entries_all
                    if str(e.get("flag") or "").strip()
                    and resource_station.match_resource_station(
                        str(e.get("url") or ""), str(e.get("flag") or "")
                    )
                }

                def _best(pool: list[dict[str, Any]]) -> str:
                    if not pool:
                        return ""
                    return str(
                        max(
                            pool,
                            key=lambda e: (
                                int(
                                    (e.get("stream") or {}).get("status") or 0
                                ) < 400,
                                int(
                                    (e.get("stream") or {}).get("bitrate_kbps") or 0
                                ),
                            ),
                        ).get("flag")
                        or ""
                    ).strip()

                own_pool = [
                    e for e in entries_all
                    if str(e.get("flag") or "").strip() not in zs_flags_now
                ]
                zs_pool = [
                    e for e in entries_all if str(e.get("flag") or "").strip() in zs_flags_now
                ]
                best_flag = _best(own_pool) or _best(zs_pool)
                if best_flag in drops:
                    reason = drops.pop(best_flag)
                    new_low.discard(f"{filename}::{best_flag}")
                    origin = "自有线路" if own_pool else "资源站线路（兜底）"
                    print(
                        f"    {filename}: 线路全被剔（{reason}），"
                        f"保留最优{origin} {best_flag}（不剔空源）"
                    )
        pruned[filename] = drops
        # 检测到 4xx/5xx 但未自动剔除的线路（单集 token 可能过期，不代表整条线路死），
        # 列出来提示用户确认；确认死了再加进 line_prune.blacklist。
        dead_candidates: list[str] = []
        for entry in (quality_map.get(filename) or {}).get("line_streams") or []:
            stream = entry.get("stream") or {}
            flag = str(entry.get("flag") or "").strip()
            status = int(stream.get("status") or 0)
            if flag and status >= 400 and flag not in drops:
                dead_candidates.append(f"{flag}(HTTP {status})")
        if dead_candidates:
            print(
                f"    {filename}: 疑似不通线路（未自动剔除）: "
                + "、".join(dead_candidates)
            )
        if write:
            # 仅对已识别出资源站线路的源内联运行时 URL 判定：这类源的线路是
            # 上游 API 动态返回的（如猎手换集就变线路名），静态名单挡不住，
            # 但资源站 CDN host 固定，按播放 URL 判定可覆盖所有动态线路。
            # 音频源/纯自有源不注入，完全不受影响。
            has_zy = any(
                "资源站" in str(reason) for reason in drops.values()
            )
            # 声明线路比采样多 → 可能有未采样到的资源站线路（如分享者华谊采样4条
            # 没采到 B超高清=rrcdnbf6），也启用运行时 URL 签名按 CDN 兜底。
            _qz = quality_map.get(result.filename) or {}
            _declared_n = len(_qz.get("declared_flags") or [])
            _sampled_n = len(_qz.get("line_streams") or [])
            if not has_zy and _declared_n > _sampled_n:
                has_zy = True
            text = inject_line_filter(
                result.source,
                sorted(drops),
                line_grade_order(quality_map.get(result.filename)),
                zy_sigs=resource_station.runtime_url_signatures() if has_zy else None,
            )
            # 成人分类过滤：只给上一步判定为「固定分类混合源」且保留下来的源注入。
            q = quality_map.get(result.filename) or {}
            if q.get("category_filter"):
                cat_blocks = [
                    str(x) for x in (q.get("category_filter_names") or []) if str(x).strip()
                ]
                if cat_blocks:
                    type_ids = [str(x) for x in (q.get("category_filter_ids") or [])]
                    text = inject_category_filter(text, cat_blocks, type_ids)
                    label = "、".join(type_ids or cat_blocks)
                    print(f"    {filename}: 注入成人分类过滤（{label}）")
            # 冒烟检查：注入后必须是合法 Python（两种注入都是运行时包装，不应破坏语法）。
            try:
                compile(text, filename, "exec")
            except SyntaxError as exc:  # noqa: PERF203
                print(
                    f"    !! {filename}: 注入线路过滤后语法错误（脚本已写入，请人工检查）: {exc}",
                    file=sys.stderr,
                )
            (script_out / filename).parent.mkdir(parents=True, exist_ok=True)
            (script_out / filename).write_text(text, encoding="utf-8", newline="")

    if not write:
        return pruned, new_low, new_dead

    # 清理上一轮生成、这轮已不再保留的本地脚本。删两类：
    # ① 上游脚本（managed_scripts，无论是否带标记——被质量剔的源要清掉）
    # ② 带托管标记的旧文件（上游已下线但本地遗留、带标记的）
    for old in script_out.rglob("*.py"):
        rel = old.relative_to(script_out).as_posix()
        # 手动保留的自定义站点（豆瓣/哔哩等）即使本轮没被验证也不能删。
        if rel in kept_files or rel in (protect_scripts or set()):
            continue
        try:
            content = old.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rel in (managed_scripts or set()) or LINE_FILTER_MARKER in content:
            try:
                old.unlink()
            except OSError:
                pass
    return pruned, new_low, new_dead


def write_json(path: Path, data: Any, newline: str = "\n") -> None:
    text = json.dumps(data, ensure_ascii=False, indent=4) + "\n"
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    os.replace(temporary, path)


def dedupe_entries(
    results: list[ScriptResult],
    preserved_names: set[str],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[ScriptResult]]:
    excluded_scripts = set(config.get("exclude_scripts") or [])
    excluded_names = set(config.get("exclude_names") or [])
    candidates = [
        result
        for result in results
        if result.status == "valid" and result.entry is not None
    ]
    # 同名脚本优先保留不带广告后缀、文件名更短的那个。
    candidates.sort(
        key=lambda result: (
            "🍀" in result.filename,
            len(result.filename),
            result.filename,
        )
    )

    seen_names = set(preserved_names)
    seen_fingerprints: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    skipped: list[ScriptResult] = []
    for result in candidates:
        assert result.entry is not None
        name = result.entry["name"]
        if result.filename in excluded_scripts or name in excluded_names:
            result.status = "excluded"
            result.error = "配置排除"
            skipped.append(result)
            continue
        if name in seen_names:
            result.status = "duplicate"
            result.error = "同名站点已存在"
            skipped.append(result)
            continue
        if result.fingerprint:
            twin = seen_fingerprints.get(result.fingerprint)
            if twin:
                result.status = "duplicate"
                result.error = f"与 {twin} 代码内容相同"
                skipped.append(result)
                continue
            seen_fingerprints[result.fingerprint] = result.filename
        seen_names.add(name)
        entries.append(result.entry)

    entries.sort(key=lambda entry: entry["name"])
    return entries, skipped


def build_report(
    config: dict[str, Any],
    filenames: list[str],
    results: list[ScriptResult],
    checks: dict[str, ProbeResult],
    preserved: list[Any],
    removed: list[Any],
    entries: list[dict[str, Any]],
    output: Path,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    counts = Counter(result.status for result in results)
    grades = Counter(
        effective_grade(result.quality, thresholds)
        for result in results
        if result.quality and result.status == "valid"
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upstream": upstream_list(config),
        "output": str(output),
        "summary": {
            "upstream_scripts": len(filenames),
            "preserved_sites": len(preserved),
            "removed_http_sites": len(removed),
            "generated_sites": len(entries),
            "valid": counts.get("valid", 0),
            "invalid": counts.get("invalid", 0),
            "no_host": counts.get("no_host", 0),
            "download_failed": counts.get("download_failed", 0),
            "skipped": counts.get("skipped", 0),
            "duplicate": counts.get("duplicate", 0),
            "excluded": counts.get("excluded", 0),
            "excluded_adult": counts.get("excluded_adult", 0),
            "functional_fail": counts.get("functional_fail", 0),
            "low_quality": counts.get("low_quality", 0),
            "low_bitrate": counts.get("low_bitrate", 0),
            "slow_stream": counts.get("slow_stream", 0),
            "resource_station": counts.get("resource_station", 0),
            "parse_required": counts.get("parse_required", 0),
            "with_quality": sum(1 for result in results if result.quality),
            "grade_a": grades.get("A", 0),
            "grade_b": grades.get("B", 0),
            "grade_c": grades.get("C", 0),
            "grade_d": grades.get("D", 0),
            "grade_unverified": grades.get("U", 0),
        },
        "host_checks": {
            origin: {
                "ok": check.ok,
                "status": check.status,
                "url": check.url,
                "error": check.error,
            }
            for origin, check in sorted(checks.items())
        },
        "scripts": [
            {
                "file": result.filename,
                "name": result.name,
                "status": result.status,
                "tier": result.tier,
                "hosts": result.hosts,
                "checked_host": result.checked_host,
                "http_status": result.http_status,
                "error": result.error,
                "api": result.entry["api"] if result.entry else None,
                "quality": result.quality,
            }
            for result in sorted(results, key=lambda item: item.filename)
        ],
    }


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步上游 py 脚本并生成 接口.json")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件")
    parser.add_argument(
        "--source-dir", help="使用本地 py 目录（不下载），便于调试"
    )
    parser.add_argument("--output", help="输出 JSON 路径")
    parser.add_argument("--report", help="校验报告路径")
    parser.add_argument("--history", help="两振出局历史文件路径（默认 reports/history.json）")
    parser.add_argument("--dry-run", action="store_true", help="只校验，不写 接口.json")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个脚本")
    parser.add_argument("--no-report", action="store_true", help="不写校验报告")
    parser.add_argument("--force", action="store_true", help="跳过可用站点骤降保护")
    parser.add_argument(
        "--functional-report",
        help="functional_check.py 生成的报告，用于给站点打功能评分",
    )
    parser.add_argument("--verbose", action="store_true", help="输出更多日志")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    config = load_config(Path(args.config))
    source_dir = Path(args.source_dir).resolve() if args.source_dir else None
    output = (
        Path(args.output).resolve()
        if args.output
        else (ROOT / str(config["output"])).resolve()
    )
    report_path = (
        Path(args.report).resolve()
        if args.report
        else (ROOT / "reports" / "validation-report.json").resolve()
    )
    history_path = (
        Path(args.history).resolve()
        if args.history
        else (ROOT / "reports" / "history.json").resolve()
    )
    history = load_history(history_path)
    history_streaks: dict[str, str] = {}
    history_statuses: dict[str, str] = {}
    prev_line_low = set(str(k) for k, v in (history.get("line_low") or {}).items() if v)
    prev_line_dead = set(str(k) for k, v in (history.get("line_dead") or {}).items() if v)

    existing, newline = load_existing(output)
    sites = existing.get("sites")
    if not isinstance(sites, list):
        sites = []
    preserved, removed = split_sites(sites, config)
    preserved_names = {
        str(site.get("name"))
        for site in preserved
        if isinstance(site, dict) and site.get("name")
    }

    print("=" * 60)
    print(f"输出文件: {output}")
    print(f"保留站点: {len(preserved)}，待替换 http 站点: {len(removed)}")

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        filenames = get_upstream_filenames(config, source_dir, token)
    except Exception as exc:  # noqa: BLE001
        print(f"获取上游文件列表失败: {exc}", file=sys.stderr)
        return 1
    if args.limit > 0:
        filenames = dict(list(filenames.items())[: args.limit])
    if not filenames:
        print("上游没有找到 .py 文件，保留原 接口.json", file=sys.stderr)
        return 1
    print(f"上游脚本: {len(filenames)}")

    results: list[ScriptResult] = []
    download_workers = int(config["request"]["download_workers"])
    max_hosts = int(config["request"]["max_hosts_per_script"])
    max_fallback = int(config["request"]["max_fallback_hosts"])
    filters = config.get("filters") or {}
    require_spider = bool(filters.get("require_spider_class", True))
    dedupe_by_content = bool(filters.get("dedupe_identical_scripts", True))

    def process(filename: str) -> ScriptResult:
        name = sanitize_name(filename)
        src = filenames.get(filename, 0)
        try:
            source, source_url = download_script(config, filename, source_dir, src)
        except Exception as exc:  # noqa: BLE001
            return ScriptResult(
                filename, name, "download_failed", error=f"{type(exc).__name__}: {exc}"
            )
        if is_error_page(source):
            return ScriptResult(
                filename, name, "skipped", error=f"错误页/HTML: {source_url}"
            )
        if require_spider and not has_spider_class(source):
            return ScriptResult(
                filename, name, "skipped", error="缺少 class Spider，不是 TVBox py 源"
            )
        fingerprint = source_fingerprint(source) if dedupe_by_content else ""
        hosts, tier = extract_hosts(source, max_hosts, max_fallback)
        if not hosts:
            return ScriptResult(
                filename, name, "no_host", tier=tier, fingerprint=fingerprint
            )
        return ScriptResult(
            filename,
            name,
            "pending",
            hosts=hosts,
            tier=tier,
            fingerprint=fingerprint,
            source=source,
        )

    action = "读取" if args.source_dir else "下载"
    print(f"开始{action}并解析脚本（并发 {download_workers}）...")
    with ThreadPoolExecutor(max_workers=download_workers) as executor:
        futures = {executor.submit(process, filename): filename for filename in filenames}
        for index, future in enumerate(as_completed(futures), 1):
            filename = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                results.append(
                    ScriptResult(
                        filename,
                        sanitize_name(filename),
                        "download_failed",
                        error=repr(exc),
                    )
                )
            if index % 25 == 0 or index == len(futures):
                print(f"  已处理 {index}/{len(futures)}")

    # 功能报告：现在既用于质量门槛，也用于替代 host 校验——功能三方法全通
    # 必然 host 可达，无需再探测一遍（用户要求：只留功能门槛+资源站+成人）。
    quality_map: dict[str, dict[str, Any]] = {}
    functional_cfg = config.get("functional") or {}
    quality_path: Path | None = None
    if args.functional_report:
        quality_path = Path(args.functional_report).resolve()
    elif functional_cfg.get("enabled"):
        quality_path = (
            ROOT / str(functional_cfg.get("report") or "reports/functional-report.json")
        ).resolve()
    if quality_path is not None and quality_path.exists():
        quality_map = load_functional_report(quality_path)
        print(f"功能校验报告: {quality_path}（{len(quality_map)} 条）")

    def _quality_for(name: str) -> dict[str, Any] | None:
        return quality_map.get(name) or quality_map.get(Path(name).name)

    # 跳过 host 探测：功能报告存在时，functional_ok=True 的源直接判 valid；
    # 报告里没有的源（未测功能）才退回 host 校验兜底，避免误剔。
    skip_host = bool(quality_map) and bool(
        (config.get("verification") or {}).get("skip_host_when_functional", True)
    )
    checks: dict[str, ProbeResult] = {}
    if not skip_host:
        all_hosts = [host for result in results for host in result.hosts]
        checks = validate_hosts(all_hosts, config)

    for result in results:
        if result.status != "pending":
            continue
        q = _quality_for(result.filename)
        if skip_host and q is not None and q.get("functional_ok") is True:
            # 功能三方法全通 = host 可达，无需重复探测。
            result.status = "valid"
            result.checked_host = (q.get("lines") or [{}])[0].get("url", "")[:200]
            result.http_status = 200
            result.entry = build_entry(config, result.filename, filenames.get(result.filename, 0))
            continue
        hits = [
            (host, checks[host])
            for host in result.hosts
            if host in checks and checks[host].ok
        ]
        if hits:
            result.status = "valid"
            result.checked_host, result.http_status = hits[0][0], hits[0][1].status
            result.entry = build_entry(config, result.filename, filenames.get(result.filename, 0))
        else:
            result.status = "invalid"
            reasons = []
            for host in result.hosts:
                check = checks.get(host)
                if check is None:
                    reasons.append(f"{host} -> 未校验")
                elif check.status is not None:
                    reasons.append(f"{host} -> HTTP {check.status}")
                else:
                    reasons.append(f"{host} -> {check.error}")
            result.error = "; ".join(reasons)
    # 动态分级阈值（方向4）：quality_map 块内计算，块外（build_report/排序）也要用。
    dyn_thresholds: dict[str, float] | None = None
    if quality_map:
        quality_enabled = bool((config.get("quality") or {}).get("enabled", True))
        min_score = int(functional_cfg.get("min_score") or 0)
        quality_cfg = config.get("quality") or {}
        filter_cfg = config.get("filters") or {}
        exclude_adult = bool(filter_cfg.get("exclude_adult", True))
        # 色情分类词表：优先用 AI 从全量脚本分类名提取的外部词表文件，
        # config.filters.adult_keywords 可覆盖（为空则用词表）。
        adult_terms_path = ROOT / "scripts" / "adult_categories.txt"
        ai_adult_terms: tuple[str, ...] = ()
        if adult_terms_path.exists():
            ai_adult_terms = tuple(
                line.strip()
                for line in adult_terms_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            )
        adult_keywords = tuple(filter_cfg.get("adult_keywords") or ai_adult_terms)
        adult_title_keywords = tuple(
            filter_cfg.get("adult_title_keywords") or ADULT_TITLE_KEYWORDS
        )
        adult_probes = tuple(
            str(k) for k in (functional_cfg.get("adult_probe_keywords") or []) if str(k).strip()
        )
        adult_allow = {str(name) for name in (filter_cfg.get("adult_allow") or [])}
        adult_sources = {
            str(name).lower() for name in (filter_cfg.get("adult_sources") or [])
        }
        min_grade = str(quality_cfg.get("min_grade") or "").strip().upper()
        drop_unverified = bool(quality_cfg.get("drop_unverified"))
        # 方向4：动态分级阈值（按源池分布分位数，默认关=固定阈值）
        dyn_thresholds: dict[str, float] | None = None
        if bool(quality_cfg.get("dynamic_grade_thresholds")):
            dyn_thresholds = dynamic_grade_thresholds(quality_map)
            print(f"动态分级阈值（P75/P50）: bpp_a={dyn_thresholds['bpp_a']:.3f} "
                  f"bpp_b={dyn_thresholds['bpp_b']:.3f} "
                  f"speed_a={dyn_thresholds['speed_a']:.2f} "
                  f"speed_b={dyn_thresholds['speed_b']:.2f}")
        min_bitrate = float(quality_cfg.get("min_bitrate_kbps") or 0)
        min_bpp = float(quality_cfg.get("min_bpp") or 0)
        bitrate_thresholds = dict(DEFAULT_BITRATE_THRESHOLDS)
        bitrate_thresholds.update(quality_cfg.get("bitrate_thresholds") or {})
        bitrate_allow = {
            str(name) for name in (quality_cfg.get("bitrate_allow") or [])
        }
        min_speed_ratio = float(quality_cfg.get("min_speed_ratio") or 0)
        max_startup_ms = int(quality_cfg.get("max_startup_ms") or 0)
        speed_allow = {
            str(name) for name in (quality_cfg.get("speed_allow") or [])
        }
        # 资源站（采集站）线路过滤：资源站线路基本是低质源，严格过滤剔除。
        zs_cfg = quality_cfg.get("resource_station") or {}
        zs_enabled = bool(zs_cfg.get("enabled"))
        zs_drop_pure = bool(zs_cfg.get("drop_pure_source"))
        zs_drop_lines = bool(zs_cfg.get("drop_lines"))
        zs_allow = {str(name) for name in (zs_cfg.get("allow") or [])}
        grade_rank = {"A": 0, "B": 1, "C": 2, "D": 3}
        adult_hits: list[tuple[str, list[str]]] = []
        for result in results:
            quality = quality_map.get(result.filename)
            if quality is None:
                # functional_report 的 file 是 basename（script.name），子目录源
                # （如 app/xxx.py）用完整路径匹配不到，按 basename 兜底。
                quality = quality_map.get(Path(result.filename).name)
            if quality is None:
                continue
            result.quality = quality
            hits = detect_adult(
                quality, adult_keywords, adult_title_keywords, adult_probes
            )
            if hits:
                quality["adult_hits"] = hits
                adult_hits.append((result.filename, hits))
            if result.status != "valid":
                continue
            # 三方法硬门槛：searchContent+detailContent+playerContent 任一失败 = 源废。
            # functional_ok 由 _spider_runner 写入（True=三方法全通）。旧报告无该字段
            # 视为通过（None 不误剔）；新报告有则必须为 True，否则剔除。
            if quality.get("functional_ok") is False:
                result.status = "functional_fail"
                result.error = (
                    f"功能门槛未过: search={quality.get('search_ok')} "
                    f"detail={quality.get('detail_ok')} play={quality.get('play_ok')}"
                )
                continue
            # 内置解析线路剔除：parse=1 的线路依赖 TVBox 内置解析器（腾讯/芒果/
            # 优酷等官方平台给的是网页 URL）。用户的 TVBox 未配置内置解析，这类
            # 线路完全无法播放。若一个源所有线路都是 parse=1 → 整源剔除。
            parsed_lines = quality.get("lines") or []
            if parsed_lines and all(
                int(l.get("parse") or 0) == 1 for l in parsed_lines
            ):
                result.status = "parse_required"
                result.error = (
                    f"所有线路需内置解析({len(parsed_lines)}条)，环境无内置解析器无法播放"
                )
                continue
            if quality_enabled and min_score > 0 and int(quality.get("score") or 0) < min_score:
                result.status = "low_quality"
                result.error = f"功能校验 {quality.get('score')}/3 < {min_score}"
                continue
            if quality_enabled and min_grade in grade_rank:
                grade = effective_grade(quality, dyn_thresholds)
                if stream_check.is_audio_source(quality, result.filename):
                    # 音频源（听书/音乐）：本质不同（无分辨率，画质按码率评），
                    # 用户实测「正常保留」——不论 A/B/C/D/U 都保留，只按码率排序。
                    pass
                elif grade == "U":
                    # 非音频画质未知：page/local/无线路/unknown 用户实测有问题 → 剔。
                    if drop_unverified:
                        result.status = "low_quality"
                        result.error = "U级画质未知且非音频（page/local/无线路/unknown）"
                elif grade_rank.get(grade, 3) > grade_rank[min_grade]:
                    result.status = "low_quality"
                    result.error = f"源质量 {grade} 低于 {min_grade}"
            if (
                quality_enabled and min_bitrate > 0
                and result.status == "valid"
                and result.filename not in bitrate_allow
            ):
                verdict = bitrate_verdict(
                    quality, min_bitrate, bitrate_thresholds, min_bpp
                )
                quality["bitrate"] = verdict
                if verdict["all_low"]:
                    result.status = "low_bitrate"
                    detail = "、".join(
                        f"{item['bitrate_kbps']}kbps@"
                        f"{min(item['width'], item['height']) if item['width'] and item['height'] else item['height']}p"
                        f"<{item['min_kbps']}"
                        + (f" bpp={item['bpp']:.3f}" if min_bpp > 0 else "")
                        for item in verdict["lines"]
                    )
                    result.error = f"所有线路码率低于阈值（{detail}）"
            if (
                quality_enabled and min_speed_ratio > 0
                and result.status == "valid"
                and result.filename not in speed_allow
            ):
                verdict = speed_verdict(quality, min_speed_ratio, max_startup_ms)
                quality["speed"] = verdict
                if verdict["all_slow"]:
                    result.status = "slow_stream"
                    detail = "、".join(
                        f"{item['flag'] or '线路'} {item['speed_kbps']}kbps"
                        f"={item['speed_ratio']:.2f}x"
                        + (
                            f"/{item['startup_ms'] / 1000:.1f}s"
                            if item["startup_ms"]
                            else ""
                        )
                        for item in verdict["lines"]
                    )
                    result.error = f"所有线路加载慢（{detail}）"
            # 资源站（采集站）线路过滤：项目定位是「剔除低质源」，资源站线路
            # 内容来自第三方采集站聚合，质量不可控（转码/压缩/失效），基本是低质源。
            # 纯资源站源（所有视频线路都是资源站）→ 整源剔除；混合源 → 只剔资源站线路。
            if zs_enabled and result.status == "valid" and result.filename not in zs_allow:
                zs_cls = resource_station.classify_source(
                    quality.get("line_streams") or [],
                    declared_flags=quality.get("declared_flags"),
                    declared_total=int(quality.get("play_from") or 0),
                )
                quality["resource_station"] = zs_cls
                if zs_drop_pure and zs_cls["pure"]:
                    result.status = "resource_station"
                    if zs_cls["n_declared"]:
                        # 有声明线路名单时按「全部声明线路」口径说明原因。
                        shown = (
                            f"{zs_cls['n_declared_z']}/{zs_cls['n_declared']} 条声明线路"
                        )
                    else:
                        shown = (
                            f"{zs_cls['n_z']}/{zs_cls['n_video']} 条采样线路"
                        )
                    result.error = (
                        f"资源站聚合源（{shown}全是资源站："
                        f"{'、'.join(zs_cls['z_flags'][:6])}）"
                    )
            # 成人过滤：放在功能→资源站之后执行（用户要求的过滤顺序）。
            # 先剔除纯色情源；剩下命中成人词的，再分析色情内容是否来自某个
            # 固定分类类型（如「伦理片」）。是 → 保留源并注入三点分类过滤；
            # 否 → 仍按整源剔除。
            cat_cfg = filters.get("category_filter") or {}
            cat_blocks = [
                str(x) for x in (cat_cfg.get("categories") or []) if str(x).strip()
            ]
            fixed_mixed = bool(
                cat_cfg.get("enabled", True)
                and is_fixed_category_mixed(quality, hits, cat_blocks, adult_keywords)
            )
            if (
                (hits or Path(result.filename).name.lower() in adult_sources)
                and exclude_adult and result.status == "valid"
                and result.filename not in adult_allow
                and not fixed_mixed
            ):
                result.status = "excluded_adult"
                reason = "、".join(hits[:5]) if hits else "成人源黑名单"
                result.error = "成人内容: " + reason
            elif fixed_mixed and result.status == "valid":
                quality["category_filter"] = True
                type_ids = [str(x) for x in (quality.get("adult_type_ids") or [])]
                quality["category_filter_names"] = type_ids or cat_blocks
                quality["category_filter_ids"] = type_ids
        scores = Counter(
            int(result.quality.get("score") or 0)
            for result in results
            if result.quality and result.status == "valid"
        )
        print(
            "功能评分（有效站点）: "
            f"3分 {scores.get(3, 0)}，2分 {scores.get(2, 0)}，"
            f"1分 {scores.get(1, 0)}，0分 {scores.get(0, 0)}"
        )
        grades = Counter(
            effective_grade(result.quality, dyn_thresholds)
            for result in results
            if result.quality and result.status == "valid"
        )
        print(
            "源质量（有效站点）: "
            f"A 高画质 {grades.get('A', 0)}，B 画质达标 {grades.get('B', 0)}，"
            f"C 偏低 {grades.get('C', 0)}，D 差 {grades.get('D', 0)}，"
            f"U 画质未知 {grades.get('U', 0)}"
        )
        if adult_hits:
            print(
                f"成人内容: 命中 {len(adult_hits)} 个"
                + ("（已剔除）" if exclude_adult else "（仅标记，未剔除）")
            )
            for filename, hits in adult_hits[:10]:
                print(f"  - {filename}: {'、'.join(hits[:5])}")
        if min_bitrate > 0:
            low_bitrate = [
                result for result in results if result.status == "low_bitrate"
            ]
            print(
                f"码率过滤: 剔除 {len(low_bitrate)} 个"
                "（所有采样线路均低于对应分辨率阈值）"
            )
            for result in low_bitrate[:10]:
                print(f"  - {result.filename}: {result.error}")
        if min_speed_ratio > 0:
            slow_stream = [
                result for result in results if result.status == "slow_stream"
            ]
            print(
                f"加载速度过滤: 剔除 {len(slow_stream)} 个"
                f"（所有采样线路都低于 {min_speed_ratio:g}x 码率或启动超过 "
                f"{max_startup_ms / 1000:g}s）"
            )
            for result in slow_stream[:10]:
                print(f"  - {result.filename}: {result.error}")
        if zs_enabled:
            zs_dropped = [
                result for result in results if result.status == "resource_station"
            ]
            if zs_dropped:
                print(
                    f"资源站过滤: 剔除 {len(zs_dropped)} 个"
                    "（所有视频线路都是资源站/采集站聚合线路，基本是低质源）"
                )
                for result in zs_dropped[:20]:
                    print(f"  - {result.filename}: {result.error}")

    # 质量剔除：min_grade/drop_unverified/码率/速度过滤立即生效，不留两振缓冲。
    if not args.dry_run:
        history_streaks, history_statuses = apply_two_strike(results, history)
        removed = [result for result in results if getattr(result, "strike", 0)]
        if removed:
            print(
                "质量剔除（立即生效）: "
                + "、".join(
                    f"{result.filename}({result.pending})" for result in removed
                )
            )

    # 本地托管脚本由本流程重新生成，不能当作「保留的本地站点」，否则会和生成结果同名冲突。
    # 判断依据：api 落在 local_spider_dir 下，且文件名是本轮生成的脚本，或文件带托管标记
    # （上一轮生成、这轮掉出名单的也要清掉）。
    local_spider_dir = str(config.get("local_spider_dir") or "").strip().strip("/")
    if local_spider_dir:
        managed_files = {result.filename for result in results if result.status == "valid"}
        managed_scripts = set(filenames)  # 所有上游脚本（含被剔的），都是本流程托管
        # 手动保留的自定义站点（豆瓣/哔哩等）永远不算托管，不能被重新生成或删除。
        preserve_sites = {
            str(x) for x in (config.get("preserve_sites") or [])
        }

        def _is_managed(site: Any) -> bool:
            if not isinstance(site, dict):
                return False
            api = str(site.get("api") or "")
            if not api.startswith("./"):
                return False
            parts = api[2:].strip("/").split("/")
            if len(parts) < 2 or parts[0] != local_spider_dir:
                return False
            rel = "/".join(parts[1:])  # 完整相对路径（含子目录，如 综/1905.py）
            if Path(rel).name in preserve_sites:
                return False
            if rel in managed_files or rel in managed_scripts:
                return True
            path = output.parent / local_spider_dir / rel
            try:
                return LINE_FILTER_MARKER in path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                return False

        preserved = [site for site in preserved if not _is_managed(site)]
        preserved_names = {
            str(site.get("name"))
            for site in preserved
            if isinstance(site, dict) and site.get("name")
        }

    entries, skipped = dedupe_entries(results, preserved_names, config)
    counts = Counter(result.status for result in results)

    # 质量优先排序：打开接口第一个就是最好的源（只排自动生成部分，保留站点仍在前）。
    result_by_entry = {
        id(result.entry): result
        for result in results
        if result.entry is not None and result.status == "valid"
    }

    # 排序已按用户要求去除：保持上游/去重后的原始顺序，不再按画质 bpp/速度重排。
    # def _entry_sort_key(entry: dict[str, Any]) -> tuple:
    #     result = result_by_entry.get(id(entry))
    #     if result is None:
    #         return (4, 0, 0.0, 0.0, str(entry.get("name") or ""))
    #     return quality_sort_key(result, dyn_thresholds)
    # entries.sort(key=_entry_sort_key)

    print("-" * 60)
    print(
        "校验结果: "
        f"可用 {counts.get('valid', 0)}，"
        f"不可用 {counts.get('invalid', 0)}，"
        f"无 host {counts.get('no_host', 0)}，"
        f"下载失败 {counts.get('download_failed', 0)}，"
        f"跳过 {counts.get('skipped', 0)}，"
        f"成人剔除 {counts.get('excluded_adult', 0)}，"
        f"功能门槛未过 {counts.get('functional_fail', 0)}，"
        f"码率剔除 {counts.get('low_bitrate', 0)}，"
        f"慢速剔除 {counts.get('slow_stream', 0)}，"
        f"资源站剔除 {counts.get('resource_station', 0)}"
    )
    print(
        f"生成站点: {len(entries)}（同名/排除跳过 {len(skipped)}），"
        f"保留本地站点: {len(preserved)}"
    )

    if args.verbose:
        for result in sorted(results, key=lambda item: item.filename):
            if result.status == "valid":
                print(f"  ✓ {result.filename} -> {result.checked_host} [{result.http_status}]")
            elif result.status == "invalid":
                print(f"  ✗ {result.filename} -> {result.error}")
            elif result.status == "no_host":
                print(f"  - {result.filename} -> 未找到 host")
            elif result.status in ("skipped", "download_failed"):
                print(f"  ! {result.filename} -> {result.error}")

    if not args.no_report:
        report = build_report(
            config,
            filenames,
            results,
            checks,
            preserved,
            removed,
            entries,
            output,
            dyn_thresholds,
        )
        write_json(report_path, report, "\n")
        print(f"校验报告: {report_path}")

    if not entries:
        print(
            "没有任何可用脚本，为避免清空 接口.json，本次不写入。",
            file=sys.stderr,
        )
        return 1

    # 安全护栏已按用户要求去除：不再因站点数骤降/下载失败率而拒绝写入。

    # 同步脚本到本地目录并注入线路过滤（接口指向本地文件）。
    local_spider_dir = str(config.get("local_spider_dir") or "").strip().strip("/")
    pruned: dict[str, dict[str, str]] = {}
    new_line_low: set[str] = set()
    new_line_dead: set[str] = set()
    if local_spider_dir:
        entry_ids = {id(entry) for entry in entries}
        kept = [
            result
            for result in results
            if result.status == "valid"
            and result.entry is not None
            and id(result.entry) in entry_ids
        ]
        script_out = output.parent / local_spider_dir
        # 保留站点指向的本地脚本不参与清理（--source-dir 本地调试时尤其重要）。
        local_prefix = f"./{local_spider_dir}/"
        protected_scripts = {
            str(site.get("api"))[len(local_prefix):]
            for site in preserved
            if isinstance(site, dict) and str(site.get("api") or "").startswith(local_prefix)
        }
        pruned, new_line_low, new_line_dead = write_local_spiders(
            kept,
            config,
            quality_map,
            script_out,
            write=not args.dry_run,
            prev_low=prev_line_low,
            prev_dead=prev_line_dead,
            managed_scripts=set(filenames),
            protect_scripts=protected_scripts,
        )
        pruned_flags = {f for drops in pruned.values() for f in drops}
        print(f"本地脚本: {len(kept)} 个 -> {script_out}，线路裁减 {len(pruned_flags)} 条")
        for filename, drops in sorted(pruned.items()):
            if drops:
                detail = "、".join(f"{flag}({reason})" for flag, reason in drops.items())
                print(f"  - {filename}: {detail}")

    new_data = dict(existing)
    new_data["sites"] = preserved + entries
    # 从 jsm.json 同步 hosts/doh/rules/ads/wallpaper/lives 等顶层字段。
    sync_jsm_fields(config, new_data, existing)

    if args.dry_run:
        print("dry-run: 未写入 接口.json")
    else:
        write_json(output, new_data, newline)
        print(f"已写入: {output}")

        # 同时输出远程直链版：生成站点用 gh-proxy 绝对链接，兼容只发布单文件、不带脚本目录的托管。
        if local_spider_dir:
            remote_entries: list[dict[str, Any]] = []
            for entry in entries:
                result = result_by_entry.get(id(entry))
                if result is not None:
                    remote_entries.append(
                        dict(
                            entry,
                            api=upstream_api_url(
                                config, result.filename, filenames.get(result.filename, 0)
                            ),
                        )
                    )
                else:
                    remote_entries.append(entry)
            # 手动保留站点（豆瓣/哔哩等自定义）也用仓库自身绝对直链，单文件 CDN 发布才不失效。
            remote_preserved = [
                dict(site, api=local_api_to_remote(config, str(site.get("api") or "")))
                if isinstance(site, dict)
                else site
                for site in preserved
            ]
            remote_data = dict(existing)
            remote_data["sites"] = remote_preserved + remote_entries
            sync_jsm_fields(config, remote_data, existing)
            remote_path = output.with_name(
                output.stem + "-remote" + output.suffix
            )
            write_json(remote_path, remote_data, newline)
            print(f"已写入: {remote_path}")

        # 两振出局历史：追加本轮状态，保留最近 N 轮；连击/线路集合只存最后一轮。
        history["rounds"].append(history_statuses)
        history["rounds"] = history["rounds"][-HISTORY_MAX_ROUNDS:]
        history["streaks"] = history_streaks
        history["line_low"] = {k: True for k in new_line_low}
        history["line_dead"] = {k: True for k in new_line_dead}
        save_history(history_path, history)
        print(f"已写入: {history_path}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
