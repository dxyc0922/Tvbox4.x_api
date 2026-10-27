# -*- coding: utf-8 -*-
"""TVBox `base.spider` 的最小替身，仅用于功能校验。

只实现脚本常用的宿主 API，不包含任何壳子逻辑：
- fetch / post：用 requests 发请求，返回带 .text/.json() 的响应对象；
- getProxyUrl / proxyM3u8 / proxyTs / proxyMedia：不启本地代理，原样返回 URL；
- getCache / setCache / delCache：进程内字典；
- regStr / cleanText / removeHtmlTags / log：常用小工具。
"""

from __future__ import annotations

import re
import warnings
from typing import Any

import requests

warnings.filterwarnings("ignore")

DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)


class Spider:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._cache: dict[str, Any] = {}
        self.extend = ""

    # ---------- 生命周期 ----------
    def init(self, extend: str = "") -> None:
        self.extend = extend

    def destroy(self) -> None:
        pass

    def getName(self) -> str:
        return "functional-check"

    def getDependence(self) -> list[str]:
        return []

    def isVideoFormat(self, url: str) -> bool:
        return bool(url)

    def manualVideoCheck(self) -> bool:
        return False

    def setVideoFlags(self, flags: Any) -> Any:
        return flags

    def progressVideo(self, url: str, json_str: str = "") -> str:
        return ""

    def homeVideoContent(self) -> dict[str, Any]:
        return {"list": []}

    def liveContent(self, url: str) -> dict[str, Any]:
        return {"class": [], "list": []}

    def localProxy(self, param: Any) -> Any:
        return None

    # ---------- 网络 ----------
    def fetch(self, url: str, headers: Any = None, timeout: float | None = None, **kwargs: Any):
        return self._request("GET", url, headers=headers, timeout=timeout, **kwargs)

    def post(
        self,
        url: str,
        headers: Any = None,
        data: Any = None,
        json: Any = None,
        timeout: float | None = None,
        **kwargs: Any,
    ):
        return self._request(
            "POST", url, headers=headers, data=data, json=json, timeout=timeout, **kwargs
        )

    def _request(self, method: str, url: str, headers: Any = None, timeout: float | None = None, **kwargs: Any):
        merged = {"User-Agent": DEFAULT_UA}
        if isinstance(headers, dict):
            merged.update({str(k): str(v) for k, v in headers.items() if v is not None})
        kwargs.pop("verify", None)
        kwargs.pop("allow_redirects", None)
        response = requests.request(
            method,
            url,
            headers=merged,
            timeout=timeout or 10,
            verify=False,
            allow_redirects=True,
            **kwargs,
        )
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response

    # ---------- 代理 ----------
    def getProxyUrl(self, url: str, *args: Any, **kwargs: Any) -> str:
        return url

    def proxyM3u8(self, url: str, *args: Any, **kwargs: Any) -> str:
        return url

    def proxyTs(self, url: str, *args: Any, **kwargs: Any) -> str:
        return url

    def proxyMedia(self, url: str, *args: Any, **kwargs: Any) -> str:
        return url

    # ---------- 缓存 ----------
    def getCache(self, key: str) -> Any:
        return self._cache.get(key)

    def setCache(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def delCache(self, key: str) -> None:
        self._cache.pop(key, None)

    # ---------- 工具 ----------
    def log(self, msg: Any) -> None:
        pass

    def regStr(self, pattern: str, text: str, group: int = 1) -> str:
        match = re.search(pattern, text or "")
        return match.group(group) if match else ""

    def cleanText(self, text: str) -> str:
        return re.sub(r"<[^>]+>", "", text or "").strip()

    def removeHtmlTags(self, text: str) -> str:
        return self.cleanText(text)
