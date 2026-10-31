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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "scripts" / "config.json"

# 按分辨率（短边）定最低码率，单位 kbps。阈值取在实测数据的空档里：
# 1080p 1600（1569/1583 档算低、1609+ 保留）、720p 920（893 档算低、947+ 保留）、
# 480p 600（481 档算低、752+ 保留）。分辨率未知时用 quality.min_bitrate_kbps。
DEFAULT_BITRATE_THRESHOLDS: dict[str, int] = {
    "2160": 6000,
    "1440": 3500,
    "1080": 1600,
    "720": 920,
    "480": 600,
    "360": 400,
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
    status: str  # pending / valid / invalid / no_host / skipped / download_failed / duplicate / excluded / excluded_adult / low_quality / low_bitrate / slow_stream
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


def upstream_raw_url(config: dict[str, Any], filename: str) -> str:
    up = config["upstream"]
    quoted = urllib.parse.quote(filename, safe="/")
    return (
        f"https://raw.githubusercontent.com/{up['owner']}/{up['repo']}/"
        f"{up['branch']}/{up['path']}/{quoted}"
    )


def upstream_api_url(config: dict[str, Any], filename: str) -> str:
    accelerator = str(config.get("accelerator") or "").strip()
    raw = upstream_raw_url(config, filename)
    if not accelerator:
        return raw
    return accelerator.rstrip("/") + "/" + raw


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
    accelerator = str(config.get("accelerator") or "").strip()
    if not accelerator:
        return raw
    return accelerator.rstrip("/") + "/" + raw


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": "Tvbox4.x_api-sync/1.0",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def upstream_files_from_github_tree(config: dict[str, Any], token: str | None) -> list[str]:
    up = config["upstream"]
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


def upstream_files_from_github_contents(config: dict[str, Any], token: str | None) -> list[str]:
    up = config["upstream"]
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


def upstream_files_from_jsdelivr(config: dict[str, Any]) -> list[str]:
    up = config["upstream"]
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
) -> list[str]:
    if source_dir is not None:
        if not source_dir.is_dir():
            raise RuntimeError(f"本地 py 目录不存在: {source_dir}")
        return sorted(
            path.relative_to(source_dir).as_posix()
            for path in source_dir.rglob("*.py")
        )

    errors: list[str] = []
    for label, loader in (
        ("GitHub tree", lambda: upstream_files_from_github_tree(config, token)),
        ("GitHub contents", lambda: upstream_files_from_github_contents(config, token)),
        ("jsDelivr", lambda: upstream_files_from_jsdelivr(config)),
    ):
        try:
            files = loader()
            if files:
                print(f"上游文件列表来源: {label} ({len(files)} 个 .py)")
                return files
            errors.append(f"{label}: 没有找到 .py")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    raise RuntimeError("无法获取上游 py 文件列表:\n  " + "\n  ".join(errors))


def download_script(
    config: dict[str, Any], filename: str, source_dir: Path | None
) -> tuple[str, str]:
    if source_dir is not None:
        path = source_dir / filename
        return decode_python(path.read_bytes()), str(path)

    up = config["upstream"]
    quoted = urllib.parse.quote(filename, safe="/")
    raw = (
        f"https://raw.githubusercontent.com/{up['owner']}/{up['repo']}/"
        f"{up['branch']}/{up['path']}/{quoted}"
    )
    jsdelivr = (
        f"https://cdn.jsdelivr.net/gh/{up['owner']}/{up['repo']}@"
        f"{up['branch']}/{up['path']}/{quoted}"
    )
    proxy = f"https://gh-proxy.com/{raw}"

    timeout = float(config["request"]["timeout"])
    errors: list[str] = []
    for url in (raw, jsdelivr, proxy):
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


def build_entry(config: dict[str, Any], filename: str) -> dict[str, Any]:
    prefix = str(config.get("auto_key_prefix") or "")
    digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:12]
    local_dir = str(config.get("local_spider_dir") or "").strip().strip("/")
    if local_dir:
        # 同步到本地脚本目录，接口指向本地文件；不依赖 gh-proxy 存活。
        api = f"./{local_dir}/{filename}"
    else:
        api = upstream_api_url(config, filename)
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
    url = str(cfg.get("url") or "").strip()
    if not url:
        return output
    fields = [str(f) for f in (cfg.get("fields") or []) if str(f).strip()]

    try:
        raw = fetch_bytes(url, timeout=float(config.get("request", {}).get("timeout") or 15), retries=1)
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - 网络/解析失败都回退
        print(f"  jsm_sync: 拉取 {url} 失败（回退 existing 保留）: {type(exc).__name__}: {exc}")
        return output
    if not isinstance(data, dict):
        print("  jsm_sync: jsm.json 不是 JSON 对象，跳过")
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
ADULT_TITLE_KEYWORDS = (
    "麻豆传媒",
    "星空传媒",
    "果冻传媒",
    "精东传媒",
    "天美传媒",
    "蜜桃传媒",
    "91制片厂",
    "无码",
    "里番",
    "三级片",
    "成人片",
    "18禁",
    "R18",
    "AV女优",
    "女优",
)


def detect_adult(
    quality: dict[str, Any] | None,
    category_keywords: tuple[str, ...] | list[str],
    title_keywords: tuple[str, ...] | list[str],
    probe_phrases: tuple[str, ...] | list[str] = (),
) -> list[str]:
    """从首页分类名和探针搜索结果的分类/标题里识别成人内容。

    分类名用宽一点的词表；标题只用工作室品牌、明确成人词，以及探针关键词原文
    （站点能搜出「被家长调教的女教师」这种完整片名，说明它确实收录了成人片）。
    """
    if not quality:
        return []
    hits: list[str] = []

    def add(value: str) -> None:
        if value not in hits:
            hits.append(value)

    for label in quality.get("classes") or []:
        text = str(label).strip()
        if text in ADULT_CATEGORY_EXACT:
            add(text)
        for keyword in category_keywords:
            if keyword and keyword.lower() in text.lower():
                add(keyword)

    phrases = [str(p) for p in probe_phrases if str(p).strip()]
    for label in quality.get("probe_labels") or []:
        text = str(label)
        for keyword in title_keywords:
            if keyword and keyword.lower() in text.lower():
                add(keyword)
        for phrase in phrases:
            if phrase in text:
                add(f"探针:{phrase}")

    return hits


def effective_grade(quality: dict[str, Any] | None) -> str:
    """把功能校验结果换算成 A/B/C/D，无法验证的返回 U。

    U 包括：没拿到播放地址、请求失败、本地代理（127.0.0.1）。
    这些是「测不出来」，不代表源差，默认不参与等级过滤。

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
        grade = str(stream.get("grade") or "").upper()
        kind = str(stream.get("kind") or "")
        if grade and kind and kind not in ("local", "unknown"):
            grades.append(grade)
    if not grades:
        return "U"
    rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    return min(grades, key=lambda grade: rank.get(grade, 9))


VIDEO_KINDS = ("hls", "mp4", "video")


def quality_sort_key(result: ScriptResult) -> tuple:
    """站点排序：等级（A>B>C>D>U）→ 功能评分 → 最高线路码率 → 最快速度比 → 名称。"""
    quality = result.quality or {}
    grade = effective_grade(quality)
    grade_rank = {"A": 0, "B": 1, "C": 2, "D": 3, "U": 4, "": 4}.get(grade, 4)
    score = int(quality.get("score") or 0)
    best_bitrate = 0
    best_speed = 0.0
    for entry in quality.get("line_streams") or []:
        stream = entry.get("stream") or {}
        best_bitrate = max(best_bitrate, int(stream.get("bitrate_kbps") or 0))
        best_speed = max(best_speed, float(stream.get("speed_ratio") or 0))
    return (grade_rank, -score, -best_bitrate, -best_speed, result.name)


def resolution_threshold(
    stream: dict[str, Any],
    default_kbps: float,
    thresholds: dict[str, Any] | None = None,
) -> float:
    """按分辨率返回最低码率。

    竖屏短剧会出现 720x1280 这种分辨率，所以用短边（min(宽,高)）判档，
    否则 720x1280 会被当成 1440p。分辨率未知时退回 default_kbps。
    """
    table = thresholds or DEFAULT_BITRATE_THRESHOLDS
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    short = min(width, height) if width and height else height
    if short <= 0:
        return float(default_kbps)
    best: tuple[int, float] | None = None
    for key, value in table.items():
        try:
            level = int(key)
        except (TypeError, ValueError):
            continue
        if short >= level and (best is None or level > best[0]):
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

# 两振出局：源要连续两轮被判「要剔除」才真剔除；第一轮保留（strike1）。
HISTORY_REMOVE_STATUSES = {"low_quality", "low_bitrate", "slow_stream"}
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
    """源级两振出局。

    本轮判定为 low_quality/low_bitrate/slow_stream 的源：若上一轮（含更早）已连续
    在「要剔除」状态，则本轮真剔除；否则保留（strike1，status 回退为 valid）。
    返回 (本轮最终 streaks, 本轮最终 statuses)。
    """
    streaks = {str(k): int(v) for k, v in (history.get("streaks") or {}).items()}
    new_streaks: dict[str, str] = {}
    statuses: dict[str, str] = {}
    for result in results:
        name = result.filename
        if result.status in HISTORY_REMOVE_STATUSES:
            streak = streaks.get(name, 0) + 1
            if streak < 2:
                result.strike = 1
                result.pending = result.status
                result.status = "valid"
            new_streaks[name] = str(streak)
        else:
            new_streaks[name] = "0"
        statuses[name] = result.status
    return new_streaks, statuses


def seed_two_strike_history(
    history: dict[str, Any], existing: dict[str, Any], filenames: list[str]
) -> None:
    """两振首轮（无历史）基线：以上一轮已提交的接口为准。

    上一轮不在接口里的上游源 = 上一轮已被排除 → 视为已有第 1 振；本轮若仍是
    「剔除候选」，第 2 振直接剔除，避免首轮把上轮已过滤的源全部加回（54→172）。
    """
    if history.get("rounds"):
        return
    prev_basenames: set[str] = set()
    for site in existing.get("sites") or []:
        if not isinstance(site, dict):
            continue
        api = str(site.get("api") or "").strip()
        if not api:
            continue
        base = urllib.parse.unquote(api.rstrip("/").rsplit("/", 1)[-1])
        if base.endswith(".py"):
            prev_basenames.add(base)
    streaks = {str(k): int(v) for k, v in (history.get("streaks") or {}).items()}
    seeded = 0
    for filename in filenames:
        base = Path(filename).name
        if base not in prev_basenames and streaks.get(filename, 0) < 1:
            streaks[filename] = 1
            seeded += 1
    history["streaks"] = {k: str(v) for k, v in streaks.items()}
    if seeded:
        print(f"两振基线: 上轮已排除 {seeded} 个上游源视为第 1 振（本轮仍为候选则第 2 振剔除）")


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

    剔除规则（两振出局）：
    - **不可用**：HTTP >= 400，且**上一轮同样是 4xx/5xx**（连续两轮）才剔除。
      单集 token 过期是 403/404 误报（华谊 K蓝光某集 403、换集就 200），一振不删。
    - **低质量**：码率低于阈值、或加载速度低于阈值（且同源另有达标/快速线路），
      且**连续两轮**低质量才剔除。
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

    # 2) 低质量线路：仅当同源存在至少一条达标线路时删；连续两轮低质量才删。
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
                if key(flag) in prev_low and flag not in drops:
                    drops[flag] = f"{bitrate}kbps<{round(limit)}kbps（连续两轮）"

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
    return drops, current_low, current_dead


def inject_line_filter(source: str, drop_flags: list[str]) -> str:
    """在脚本末尾注入线路过滤代码；不带 drop 时只打标记，方便后续清理。"""
    marker = LINE_FILTER_MARKER
    if marker in source:
        source = source.split(marker)[0].rstrip("\n")
    header = f"\n\n{marker}\n"
    if not drop_flags:
        return source + header
    block = "\n".join(
        [
            header.rstrip("\n"),
            f"_TVBOX_DROP_LINES = {json.dumps(sorted(drop_flags), ensure_ascii=False)}",
            "",
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
            "    keep = [(f, u) for f, u in zip(parts_from, parts_url) if f not in drop]",
            "    if not keep or len(keep) == len(parts_from):",
            "        return",
            "    item['vod_play_from'] = '$$$'.join(f for f, _ in keep)",
            "    item['vod_play_url'] = '$$$'.join(u for _, u in keep)",
            "",
            "def _tvbox_apply(cls):",
            "    fn = getattr(cls, 'detailContent', None)",
            "    if fn is None:",
            "        return",
            "    def wrapper(self, *a, _fn=fn, **k):",
            "        return _tvbox_filter_lines(_fn(self, *a, **k), _TVBOX_DROP_LINES)",
            "    setattr(cls, 'detailContent', wrapper)",
            "",
            "_tvbox_apply(Spider)",
            "",
        ]
    )
    return source + "\n" + block


def write_local_spiders(
    kept: list[ScriptResult],
    config: dict[str, Any],
    quality_map: dict[str, dict[str, Any]],
    script_out: Path,
    write: bool = True,
    prev_low: set[str] | None = None,
    prev_dead: set[str] | None = None,
) -> tuple[dict[str, dict[str, str]], set[str], set[str]]:
    """把保留的源脚本写入本地目录并注入线路过滤。

    返回 (每个源的 {flag: reason}, 本轮低质量 `source::flag` 集合, 本轮疑似不通集合)。
    write=False 时只计算不落盘（dry-run），也不清理旧文件。
    """
    script_out.mkdir(parents=True, exist_ok=True)
    quality_cfg = config.get("quality") or {}
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
            # 手动黑名单优先（用户确认，不经过两振）；码率豁免的源不做质量自动剔除。
            for flag in blacklist.get(filename, ()):
                drops.setdefault(flag, "手动配置")
            skip_quality = filename in bitrate_allow
            skip_speed = filename in speed_allow
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
            text = inject_line_filter(result.source, sorted(drops))
            # 冒烟检查：注入后必须是合法 Python（线路过滤是运行时包装，不应破坏语法）。
            try:
                compile(text, filename, "exec")
            except SyntaxError as exc:  # noqa: PERF203
                print(
                    f"    !! {filename}: 注入线路过滤后语法错误（脚本已写入，请人工检查）: {exc}",
                    file=sys.stderr,
                )
            (script_out / filename).write_text(text, encoding="utf-8", newline="")

    if not write:
        return pruned, new_low, new_dead

    # 清理上一轮生成、这轮已不再保留的本地脚本（只动带标记的）。
    for old in script_out.glob("*.py"):
        if old.name in kept_files:
            continue
        try:
            content = old.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if LINE_FILTER_MARKER in content:
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
) -> dict[str, Any]:
    counts = Counter(result.status for result in results)
    grades = Counter(
        effective_grade(result.quality)
        for result in results
        if result.quality and result.status == "valid"
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upstream": dict(config["upstream"]),
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
            "low_quality": counts.get("low_quality", 0),
            "low_bitrate": counts.get("low_bitrate", 0),
            "slow_stream": counts.get("slow_stream", 0),
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
        filenames = filenames[: args.limit]
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
        try:
            source, source_url = download_script(config, filename, source_dir)
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

    all_hosts = [host for result in results for host in result.hosts]
    checks = validate_hosts(all_hosts, config)

    for result in results:
        if result.status != "pending":
            continue
        hits = [
            (host, checks[host])
            for host in result.hosts
            if host in checks and checks[host].ok
        ]
        if hits:
            result.status = "valid"
            result.checked_host, result.http_status = hits[0][0], hits[0][1].status
            result.entry = build_entry(config, result.filename)
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
    if quality_map:
        min_score = int(functional_cfg.get("min_score") or 0)
        quality_cfg = config.get("quality") or {}
        filter_cfg = config.get("filters") or {}
        exclude_adult = bool(filter_cfg.get("exclude_adult", True))
        adult_keywords = tuple(
            filter_cfg.get("adult_keywords") or ADULT_CATEGORY_KEYWORDS
        )
        adult_title_keywords = tuple(
            filter_cfg.get("adult_title_keywords") or ADULT_TITLE_KEYWORDS
        )
        adult_probes = tuple(
            str(k) for k in (functional_cfg.get("adult_probe_keywords") or []) if str(k).strip()
        )
        adult_allow = {str(name) for name in (filter_cfg.get("adult_allow") or [])}
        min_grade = str(quality_cfg.get("min_grade") or "").strip().upper()
        drop_unverified = bool(quality_cfg.get("drop_unverified"))
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
        grade_rank = {"A": 0, "B": 1, "C": 2, "D": 3}
        adult_hits: list[tuple[str, list[str]]] = []
        for result in results:
            quality = quality_map.get(result.filename)
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
            if hits and exclude_adult and result.filename not in adult_allow:
                result.status = "excluded_adult"
                result.error = "成人内容: " + "、".join(hits[:5])
                continue
            if min_score > 0 and int(quality.get("score") or 0) < min_score:
                result.status = "low_quality"
                result.error = f"功能校验 {quality.get('score')}/3 < {min_score}"
                continue
            if min_grade in grade_rank:
                grade = effective_grade(quality)
                if grade == "U":
                    # 没拿到播放地址（地区限制/超时/本地代理）不等于源差，默认保留。
                    if drop_unverified:
                        result.status = "low_quality"
                        result.error = "源质量无法验证"
                elif grade_rank.get(grade, 3) > grade_rank[min_grade]:
                    result.status = "low_quality"
                    result.error = f"源质量 {grade} 低于 {min_grade}"
            if (
                min_bitrate > 0
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
                min_speed_ratio > 0
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
            effective_grade(result.quality)
            for result in results
            if result.quality and result.status == "valid"
        )
        print(
            "源质量（有效站点）: "
            f"A 自营 {grades.get('A', 0)}，B 第三方 {grades.get('B', 0)}，"
            f"C 搬运/解析 {grades.get('C', 0)}，D 无法验证 {grades.get('D', 0)}，"
            f"U 未取得播放地址 {grades.get('U', 0)}"
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

    # 两振出局：本轮判「要剔除」的源，若上一轮也处于剔除候选，才真剔除；否则保留一振。
    if not args.dry_run:
        seed_two_strike_history(history, existing, filenames)
        history_streaks, history_statuses = apply_two_strike(results, history)
        pending = [result for result in results if getattr(result, "strike", 0)]
        if pending:
            print(
                "两振出局: "
                + "、".join(
                    f"{result.filename}({result.pending} 第1振)" for result in pending
                )
                + " —— 本轮保留，下一轮仍如此才剔除"
            )

    # 本地托管脚本由本流程重新生成，不能当作「保留的本地站点」，否则会和生成结果同名冲突。
    # 判断依据：api 落在 local_spider_dir 下，且文件名是本轮生成的脚本，或文件带托管标记
    # （上一轮生成、这轮掉出名单的也要清掉）。
    local_spider_dir = str(config.get("local_spider_dir") or "").strip().strip("/")
    if local_spider_dir:
        managed_files = {result.filename for result in results if result.status == "valid"}

        def _is_managed(site: Any) -> bool:
            if not isinstance(site, dict):
                return False
            api = str(site.get("api") or "")
            if not api.startswith("./"):
                return False
            parts = api[2:].strip("/").split("/")
            if len(parts) < 2 or parts[0] != local_spider_dir:
                return False
            basename = parts[-1]
            if basename in managed_files:
                return True
            path = output.parent / local_spider_dir / basename
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

    def _entry_sort_key(entry: dict[str, Any]) -> tuple:
        result = result_by_entry.get(id(entry))
        if result is None:
            return (4, 0, 0, 0.0, str(entry.get("name") or ""))
        return quality_sort_key(result)

    entries.sort(key=_entry_sort_key)

    print("-" * 60)
    print(
        "校验结果: "
        f"可用 {counts.get('valid', 0)}，"
        f"不可用 {counts.get('invalid', 0)}，"
        f"无 host {counts.get('no_host', 0)}，"
        f"下载失败 {counts.get('download_failed', 0)}，"
        f"跳过 {counts.get('skipped', 0)}，"
        f"成人剔除 {counts.get('excluded_adult', 0)}，"
        f"码率剔除 {counts.get('low_bitrate', 0)}，"
        f"慢速剔除 {counts.get('slow_stream', 0)}"
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
        )
        write_json(report_path, report, "\n")
        print(f"校验报告: {report_path}")

    if not entries:
        print(
            "没有任何可用脚本，为避免清空 接口.json，本次不写入。",
            file=sys.stderr,
        )
        return 1

    if not args.force and not args.dry_run and args.limit == 0:
        safety = config.get("safety", {})
        max_failure_ratio = float(safety.get("max_download_failure_ratio", 0.2))
        min_previous_ratio = float(safety.get("min_previous_ratio", 0.5))
        download_failed = counts.get("download_failed", 0)
        if filenames and download_failed / len(filenames) > max_failure_ratio:
            print(
                f"下载失败 {download_failed}/{len(filenames)}，超过安全阈值 "
                f"{max_failure_ratio:.0%}，本次不写入。",
                file=sys.stderr,
            )
            return 1
        # 质量过滤是我们主动删源，不算「上游异常」，回加后再比较。
        intentional = (
            counts.get("low_quality", 0)
            + counts.get("low_bitrate", 0)
            + counts.get("slow_stream", 0)
        )
        if (
            len(removed) >= 10
            and len(entries) + intentional < len(removed) * min_previous_ratio
        ):
            print(
                f"本次可用站点 {len(entries) + intentional} 个，比上次的 {len(removed)} 个少了一半以上，"
                "为避免误删，本次不写入。确认无误可加 --force。",
                file=sys.stderr,
            )
            return 1

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
        pruned, new_line_low, new_line_dead = write_local_spiders(
            kept,
            config,
            quality_map,
            script_out,
            write=not args.dry_run,
            prev_low=prev_line_low,
            prev_dead=prev_line_dead,
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
                        dict(entry, api=upstream_api_url(config, result.filename))
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
