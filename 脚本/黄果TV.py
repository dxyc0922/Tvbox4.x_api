# -*- coding: utf-8 -*-
"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '黄果TV',
  lang: 'hipy',
})
"""
"""
黄果TV (huangguotv.ai) TVBox Python 插件
API 基址: https://huangguotv.ai
媒体域名: https://img.mfantasy.net
"""
import json
import sys
import requests

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def __init__(self):
        self.siteUrl = "https://huangguotv.ai"
        self.apiUrl = "https://huangguotv.ai/api"
        self.mediaUrl = "https://img.mfantasy.net"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Referer": self.siteUrl + "/",
            "Accept": "application/json, text/plain, */*",
        }
        self.classes = []
        self.filterData = {}
        self._all_dramas = None       # 全量剧集缓存
        self._page_size = 20

    # ------------------------------------------------------------------
    # 基础信息
    # ------------------------------------------------------------------
    def getName(self):
        return "黄果TV"

    def init(self, extend=""):
        """初始化：拉取分类列表"""
        try:
            r = requests.get(f"{self.apiUrl}/dramas/categories",
                             headers=self.header, timeout=15)
            data = r.json()
            if data.get("code") == 0:
                for cat in data.get("data", []):
                    self.classes.append({
                        "type_id": str(cat["id"]),
                        "type_name": cat["name"],
                    })
        except Exception:
            pass
        if not self.classes:
            self.classes = [
                {"type_id": "2", "type_name": "都市爱情"},
                {"type_id": "10", "type_name": "家庭伦理"},
                {"type_id": "3", "type_name": "经典魔改"},
                {"type_id": "17", "type_name": "特殊趣味"},
                {"type_id": "13", "type_name": "域外传奇"},
                {"type_id": "9", "type_name": "异能穿越"},
                {"type_id": "6", "type_name": "现代惊悚"},
                {"type_id": "11", "type_name": "校园记忆"},
            ]
        return

    # ------------------------------------------------------------------
    # 工具：拉全量列表（API 不分页，一次返回全部）
    # ------------------------------------------------------------------
    def _fetch_all(self):
        if self._all_dramas is not None:
            return self._all_dramas
        try:
            r = requests.get(f"{self.apiUrl}/dramas?page=1&pageSize=500",
                             headers=self.header, timeout=20)
            data = r.json()
            if data.get("code") == 0:
                self._all_dramas = data.get("data", [])
            else:
                self._all_dramas = []
        except Exception:
            self._all_dramas = []
        return self._all_dramas

    def _cover(self, path):
        """相对封面路径 → 完整 URL"""
        if not path:
            return ""
        if path.startswith("http"):
            return path
        return self.mediaUrl + path

    def _vid(self, item):
        """把列表项转成 TVBox 视频卡片"""
        return {
            "vod_id": str(item.get("id", "")),
            "vod_name": item.get("title", ""),
            "vod_pic": self._cover(item.get("coverUrl", "")),
            "vod_remarks": item.get("categoryName", "") or "",
            "vod_year": "",
            "vod_area": "",
        }

    # ------------------------------------------------------------------
    # 首页
    # ------------------------------------------------------------------
    def homeContent(self, filter):
        result = self.categoryContent("", 1, filter, {})
        result["class"] = self.classes
        return result

    def homeVideoContent(self):
        return self.categoryContent("", 1, False, {})

    # ------------------------------------------------------------------
    # 分类 / 分页（本地分页）
    # ------------------------------------------------------------------
    def categoryContent(self, tid, pg, filter, extend):
        all_list = self._fetch_all()
        # 按分类过滤
        if tid:
            filtered = [v for v in all_list
                        if str(v.get("categoryId", "")) == str(tid)]
        else:
            filtered = list(all_list)
        # 本地分页
        pg = int(pg) if pg else 1
        start = (pg - 1) * self._page_size
        end = start + self._page_size
        page_items = filtered[start:end]
        total = len(filtered)
        pagecount = (total + self._page_size - 1) // self._page_size if total else 0

        videos = [self._vid(v) for v in page_items]
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": self._page_size,
            "total": total,
        }

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def detailContent(self, ids):
        if isinstance(ids, list):
            ids = ids[0]
        try:
            r = requests.get(f"{self.apiUrl}/dramas/{ids}",
                             headers=self.header, timeout=15)
            data = r.json()
        except Exception:
            return {"list": []}
        if data.get("code") != 0:
            return {"list": []}

        item = data.get("data", {})
        vod = {
            "vod_id": str(item.get("id", "")),
            "vod_name": item.get("title", ""),
            "vod_pic": self._cover(item.get("coverUrl", "")),
            "type_name": item.get("categoryName", ""),
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": f"共{item.get('totalEpisodes', 0)}集 · "
                           f"{item.get('viewCount', 0)}次观看",
            "vod_actor": "",
            "vod_director": "",
            "vod_content": (item.get("intro", "") or "").strip(),
        }

        # 播放列表：只放已解锁（有 videoUrl）的集
        episodes = item.get("episodes", [])
        play_list = []
        for ep in episodes:
            video_url = ep.get("videoUrl", "")
            if not video_url:
                continue
            if not video_url.startswith("http"):
                video_url = self.mediaUrl + video_url
            ep_no = ep.get("episodeNo", 0)
            play_list.append(f"第{ep_no}集${video_url}")

        if play_list:
            vod["vod_play_from"] = "黄果TV"
            vod["vod_play_url"] = "#".join(play_list)
        else:
            vod["vod_play_from"] = ""
            vod["vod_play_url"] = ""

        return {"list": [vod]}

    # ------------------------------------------------------------------
    # 搜索（全量本地过滤）
    # ------------------------------------------------------------------
    def searchContent(self, key, quick, pg="1"):
        all_list = self._fetch_all()
        key_lower = (key or "").lower()
        matched = [v for v in all_list
                   if key_lower in (v.get("title", "") or "").lower()]
        pg = int(pg) if pg else 1
        start = (pg - 1) * self._page_size
        end = start + self._page_size
        page_items = matched[start:end]
        total = len(matched)
        pagecount = (total + self._page_size - 1) // self._page_size if total else 0

        videos = [self._vid(v) for v in page_items]
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": self._page_size,
            "total": total,
        }

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ------------------------------------------------------------------
    # 播放
    # ------------------------------------------------------------------
    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": id,
            "header": {"Referer": self.siteUrl + "/",
                       "User-Agent": self.header["User-Agent"]},
            "playUrl": "",
            "jx": 0,
        }

    # ------------------------------------------------------------------
    # 杂项
    # ------------------------------------------------------------------
    def isVideoFormat(self, url):
        return any(ext in (url or "") for ext in [".m3u8", ".mp4", ".ts"])

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [404, "text/plain", ""]

    def getHeaders(self):
        return self.header

# ---- TVBox 本地线路过滤（自动生成，勿改） ----
