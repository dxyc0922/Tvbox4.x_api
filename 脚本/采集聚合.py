# -*- coding: utf-8 -*-
# 专属全网聚合 Python版
# 适配常见 TVBox ok影视 鱼壳影视 羊壳PeekPro

import json
import time
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from base.spider import Spider

# 禁用 verify=False 的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Spider(Spider):
    sources = {
        's1': {'name': '电影天堂', 'api': 'http://caiji.dyttzyapi.com/api.php/provide/vod/from/dyttm3u8/at/json'},
        's2': {'name': '无水印', 'api': 'https://api.wsyzy.net/api.php/provide/vod'},
        's3': {'name': '量子', 'api': 'https://cj.lziapi.com/api.php/provide/vod'},
        's4': {'name': '1080资源', 'api': 'https://api.1080zyku.com/inc/api_mac10.php'},
        's5': {'name': '155资源', 'api': 'https://155api.com/api.php/provide/vod'},
        's6': {'name': '天涯', 'api': 'https://tyyszy.com/api.php/provide/vod/'},
        's7': {'name': '暴风', 'api': 'https://bfzyapi.com/api.php/provide/vod/'},
        's8': {'name': '索尼闪电', 'api': 'https://xsd.sdzyapi.com/api.php/provide/vod/'},
        's9': {'name': '索尼', 'api': 'https://suoniapi.com/api.php/provide/vod/'},
        's10': {'name': '红牛', 'api': 'https://www.hongniuzy2.com/api.php/provide/vod/'},
        's11': {'name': '茅台', 'api': 'https://caiji.maotaizy.cc/api.php/provide/vod/'},
        's12': {'name': '虎牙', 'api': 'https://www.huyaapi.com/api.php/provide/vod/'},
        's13': {'name': '豆瓣', 'api': 'https://caiji.dbzy.tv/api.php/provide/vod/'},
        's14': {'name': '豆瓣2', 'api': 'https://dbzy.tv/api.php/provide/vod/'},
        's15': {'name': '豪华', 'api': 'https://hhzyapi.com/api.php/provide/vod/'},
        's16': {'name': '如意影视', 'api': 'https://cj.rycjapi.com/api.php/provide/vod/'},
        's17': {'name': 'U酷', 'api': 'https://api.ukuapi.com/api.php/provide/vod'},
        's18': {'name': 'ikun', 'api': 'https://ikunzyapi.com/api.php/provide/vod'},
        's19': {'name': '无尽', 'api': 'https://api.wujinapi.cc/api.php/provide/vod'},
        's20': {'name': '光速', 'api': 'https://api.guangsuapi.com/api.php/provide/vod'},
        's21': {'name': '卧龙', 'api': 'https://collect.wolongzyw.com/api.php/provide/vod'},
        's22': {'name': '新浪', 'api': 'https://api.xinlangapi.com/xinlangapi.php/provide/vod'},
        's23': {'name': '旺旺', 'api': 'https://api.wwzy.tv/api.php/provide/vod'},
        's24': {'name': '最大', 'api': 'https://api.zuidapi.com/api.php/provide/vod'},
        's25': {'name': '樱花', 'api': 'https://m3u8.apiyhzy.com/api.php/provide/vod'},
        's26': {'name': '牛牛', 'api': 'https://api.niuniuzy.me/api.php/provide/vod'},
        's27': {'name': '百度云', 'api': 'https://api.apibdzy.com/api.php/provide/vod'},
        's28': {'name': '速播', 'api': 'https://subocaiji.com/api.php/provide/vod'},
        's29': {'name': '金鹰', 'api': 'https://jinyingzy.com/api.php/provide/vod'},
        's30': {'name': '闪电', 'api': 'https://sdzyapi.com/api.php/provide/vod'},
        's31': {'name': '非凡', 'api': 'https://cj.ffzyapi.com/api.php/provide/vod'},
        's32': {'name': '飘零', 'api': 'https://p2100.net/api.php/provide/vod'},
        's33': {'name': '魔爪', 'api': 'https://mozhuazy.com/api.php/provide/vod'},
        's34': {'name': '魔都', 'api': 'https://www.mdzyapi.com/api.php/provide/vod'},
        's35': {'name': '西瓜资源', 'api': 'https://caiji.xgzyapi.com/api.php/provide/vod/'},
        's36': {'name': '98资源', 'api': 'https://98zy.vip/api.php/provide/vod/'},
        's37': {'name': '火狐影视', 'api': 'https://hhzyapi.com/api.php/provide/vod/'},
        's38': {'name': '大众资源', 'api': 'https://cdn.dzzyapi.com/api.php/provide/vod/'},
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 分类缓存
    _class_cache = {}
    _class_cache_time = 0
    CACHE_TTL = 3600  # 1 小时

    def getName(self):
        return "影视+专属全网聚合"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def fetch(self, url, timeout=8):
        """通用请求，带 Referer 与超时"""
        try:
            headers = dict(self.headers)
            headers["Referer"] = url.split("?")[0]
            r = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                verify=False
            )
            return r.text
        except Exception:
            return ""

    def clean_item(self, item, source_key, source_name, is_detail=False):
        item = dict(item)

        if not is_detail:
            item["vod_id"] = f"{source_key}@@{item.get('vod_id', '')}"

        remarks = item.get("vod_remarks", "")
        item["vod_remarks"] = f"{source_name} | {remarks}"

        if item.get("vod_play_from"):
            froms = item["vod_play_from"].split("$$$")
            froms = [f"{source_name}-{x}" for x in froms]
            item["vod_play_from"] = "$$$".join(froms)

        item.pop("vod_down_from", None)
        item.pop("vod_down_url", None)

        return item

    # ------------------------------------------------------------------ #
    #  首页
    # ------------------------------------------------------------------ #
    def homeContent(self, filter):
        classes = []
        filters = {}
        now = time.time()

        def load_class(key, source):
            # 命中缓存
            if key in self._class_cache and (now - self._class_cache_time) < self.CACHE_TTL:
                return key, self._class_cache[key]

            url = f"{source['api']}?ac=list"
            html = self.fetch(url, 4)

            try:
                data = json.loads(html)
            except Exception:
                data = {}

            vals = [{"n": "全部(最新)", "v": ""}]
            for c in data.get("class", []):
                vals.append({
                    "n": c.get("type_name", ""),
                    "v": c.get("type_id", "")
                })

            self._class_cache[key] = vals
            return key, vals

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for key, source in self.sources.items():
                classes.append({
                    "type_id": key,
                    "type_name": source["name"]
                })
                futures.append(executor.submit(load_class, key, source))

            for future in as_completed(futures):
                try:
                    key, vals = future.result()
                    filters[key] = [{
                        "key": "cateId",
                        "name": "分类",
                        "value": vals
                    }]
                except Exception:
                    pass

        self._class_cache_time = now

        return {
            "class": classes,
            "filters": filters,
            "list": []
        }

    def homeVideoContent(self):
        """首页推荐：取电影天堂最新一页"""
        try:
            return self.categoryContent('s1', '1', None, {})
        except Exception:
            return {"list": []}

    # ------------------------------------------------------------------ #
    #  分类
    # ------------------------------------------------------------------ #
    def categoryContent(self, tid, pg, filter, extend):
        if tid not in self.sources:
            return {"list": []}

        source = self.sources[tid]

        cate_id = ""
        if isinstance(extend, dict):
            cate_id = extend.get("cateId", "")

        url = f"{source['api']}?ac=detail&pg={pg}"
        if cate_id:
            url += f"&t={cate_id}"

        html = self.fetch(url)

        try:
            data = json.loads(html)
        except Exception:
            data = {}

        result = []
        for item in data.get("list", []):
            result.append(
                self.clean_item(item, tid, source["name"], False)
            )

        return {
            "list": result,
            "page": data.get("page", pg),
            "pagecount": data.get("pagecount", 1),
            "limit": data.get("limit", 20),
            "total": data.get("total", len(result))
        }

    # ------------------------------------------------------------------ #
    #  详情
    # ------------------------------------------------------------------ #
    def detailContent(self, ids):
        if isinstance(ids, list):
            ids = ids[0]

        if "@@" not in ids:
            return {"list": []}

        source_key, real_id = ids.split("@@", 1)

        if source_key not in self.sources:
            return {"list": []}

        source = self.sources[source_key]
        url = f"{source['api']}?ac=detail&ids={real_id}"

        html = self.fetch(url)

        try:
            data = json.loads(html)
        except Exception:
            data = {}

        result = []
        for item in data.get("list", []):
            cleaned = self.clean_item(
                item, source_key, source["name"], True
            )
            cleaned["vod_id"] = ids
            result.append(cleaned)

        return {"list": result}

    # ------------------------------------------------------------------ #
    #  搜索
    # ------------------------------------------------------------------ #
    def search_one(self, source_key, source, keyword, pg):
        url = f"{source['api']}?ac=detail&wd={keyword}&pg={pg}"
        html = self.fetch(url, 6)

        try:
            data = json.loads(html)
        except Exception:
            data = {}

        result = []
        for item in data.get("list", []):
            result.append(
                self.clean_item(item, source_key, source["name"], False)
            )

        return {
            "list": result,
            "pagecount": data.get("pagecount", 1)
        }

    def searchContent(self, key, quick=False, pg=1):
        result = []
        max_page = 1

        # quick 模式：只搜前 10 个源，只取第 1 页
        if quick:
            pg = 1
            source_items = list(self.sources.items())[:10]
        else:
            source_items = list(self.sources.items())

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(self.search_one, k, s, key, pg)
                for k, s in source_items
            ]

            for future in as_completed(futures):
                try:
                    data = future.result()
                    result.extend(data["list"])
                    if data["pagecount"] > max_page:
                        max_page = data["pagecount"]
                except Exception:
                    pass

        # 按名称去重
        seen = set()
        unique = []
        for item in result:
            name = item.get("vod_name", "")
            if name and name in seen:
                continue
            seen.add(name)
            unique.append(item)

        return {
            "list": unique,
            "page": pg,
            "pagecount": max_page,
            "limit": 40,
            "total": len(unique)
        }

    # ------------------------------------------------------------------ #
    #  播放
    # ------------------------------------------------------------------ #
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {
                "parse": 0,
                "playUrl": "",
                "url": "",
                "header": self.headers
            }

        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": self.headers
        }

    def localProxy(self, param):
        return [200, "text/plain", "ok"]


if __name__ == "__main__":
    Spider().run()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
