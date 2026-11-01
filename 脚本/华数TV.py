# coding=utf-8
"""
华数TV (wasu.cn) TVBox Python 爬虫  
========================================================
【重要说明】

1. 站点是 Vue3 SPA（<div id="app"></div>），服务端不返回任何影视 HTML，
   所有数据来自 XHR JSON 接口，因此本爬虫不解析 HTML，只调真实接口。

2. 真实接口（全部实测通过）：
   [配置]  GET  https://mcspapp.5g.wasu.tv/bvradio_app/hzhs/configServlet
              ?functionName=getAppConf&siteId=1000101&platform=web
   [导航]  GET  https://mcspapp.5g.wasu.tv/bvradio_app/hzhs/recommendServlet
              ?functionName=getNavigationBar&indexId=41&siteId=1000101&platform=web
   [列表]  GET  https://mcspapp.5g.wasu.tv/bvradio_app/hzhs/recommendServlet
              ?functionName=getRecommond&modeId=<modeId>&siteId=1000101&platform=web
   [详情]  GET  https://mcspapp.5g.wasu.tv/bvradio_app/hzhs/newsServlet
              ?functionName=getCurrentNews&newsId=<id>&nodeId=<id>&siteId=1000101&platform=web
   [搜索]  GET  https://ups.5g.wasu.tv/rmp-user-suggest/10001/hzhs/searchServlet
              ?functionName=getServiceAndNewsSearch&keyword=<kw>&page=&pageSize=&siteId=1000101&platform=web
   [播放]  POST https://mcspapp.5g.wasu.tv/thirdApiFile/file/getPlayUrl
              Body: {"playUrl": "<.../xxx/playlist.m3u8>", "platform": "web"}
              Headers 必须带 x-sign 签名头（见下）

3. 【播放签名算法】—— 逆向自前端 JS：
      x-sign = Base64( HMAC-SHA256( compact_json(body), KEY ) )
      KEY    = b"3ecc90fe-da54-4bd6-8d2e-6e7820fbe76a"   # 直接字符串字节，勿 base64 解码
      compact_json = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
      请求头还需：siteId:1000101、launchChannel:web_channel
   播放流程：详情返回的 fileList[].playUrl 是 .../xxx.mp4，
      前端把它替换成 .../xxx/playlist.m3u8 再调 getPlayUrl，
      接口返回带 auth_key 的真实 m3u8 地址。

4. 分类 modeId（来自 getNavigationBar indexId=41）：
      首页 1033 / 电影 1036 / 电视剧 1034 / 少儿 1037 / 新闻 1035 / 栏目 1071 / 片库 1073
"""
import re
import sys
import json
import time
import hmac
import base64
import hashlib
import urllib.parse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    # 脱离 TVBox 环境时的独立运行兜底
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class Spider(object):
        def __init__(self):
            self._session = None

        def fetch(self, url, headers=None, **kw):
            import requests
            if self._session is None:
                self._session = requests.Session()
                self._session.verify = False
            return self._session.get(url, headers=headers, **kw)

        def post(self, url, headers=None, data=None, json=None, **kw):
            import requests
            if self._session is None:
                self._session = requests.Session()
                self._session.verify = False
            return self._session.post(url, headers=headers, data=data, json=json, **kw)

        def log(self, *a, **kw):
            try:
                print("[wasu]", *a)
            except Exception:
                pass


# ===================== 常量（真实站点参数） =====================
API_HOST = "https://mcspapp.5g.wasu.tv"
SEARCH_HOST = "https://ups.5g.wasu.tv"
SITE_ID = "1000101"
PLATFORM = "web"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 播放接口签名密钥（逆向自前端 index-*.js，字符串直接作为 key 字节）
SIGN_KEY = b"3ecc90fe-da54-4bd6-8d2e-6e7820fbe76a"

# 分类固定 modeId（若不动态拉取时的兜底）
DEFAULT_CLASSES = [
    {"type_id": "1036", "type_name": "电影"},
    {"type_id": "1034", "type_name": "电视剧"},
    {"type_id": "1037", "type_name": "少儿"},
    {"type_id": "1035", "type_name": "新闻"},
    {"type_id": "1071", "type_name": "栏目"},
    {"type_id": "1073", "type_name": "片库"},
]

SORT_OPTIONS = [
    {"n": "默认排序", "v": "1"},
    {"n": "最新", "v": "2"},
    {"n": "最热", "v": "3"},
]

# 简介前缀
INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 清晰度：接口 type 取值 → 线路名（数值越大越清晰）
# 实测：100=标清 / 110=高清 / 120=超清(1080P)
QUALITY_ALIAS = {100: "标清", 110: "高清", 120: "超清", 130: "蓝光"}


class Spider(Spider):

    def getName(self):
        return "华数TV"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}
        self.api = API_HOST
        self.search_api = SEARCH_HOST
        self.site_id = self.extend.get("site_id") or SITE_ID
        self.headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.wasu.cn/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self._classes = None
        self._play_cache = {}
        self.log("init: api=%s" % self.api)

    # ---------------- 通用请求 ----------------
    def _get(self, url, timeout=15):
        try:
            r = self.fetch(url, headers=self.headers, timeout=timeout)
            txt = r.text if hasattr(r, "text") else str(r)
            return json.loads(txt)
        except Exception as e:
            self.log("GET FAIL %s -> %s" % (url, e))
            return None

    def _sign(self, body):
        raw = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
        digest = hmac.new(SIGN_KEY, raw.encode("utf-8"), hashlib.sha256).digest()
        return raw, base64.b64encode(digest).decode()

    def _post_play(self, body, timeout=15):
        raw, sign = self._sign(body)
        h = dict(self.headers)
        h.update({
            "Content-Type": "application/json;charset=utf-8",
            "siteId": self.site_id,
            "launchChannel": "web_channel",
            "x-sign": sign,
            "Accept": "application/json, text/plain, */*",
        })
        try:
            r = self.post(self.api + "/thirdApiFile/file/getPlayUrl",
                          headers=h, data=raw.encode("utf-8"), timeout=timeout)
            txt = r.text if hasattr(r, "text") else str(r)
            return json.loads(txt)
        except Exception as e:
            self.log("POST getPlayUrl FAIL -> %s" % e)
            return None

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", str(s))
        s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'")
              .replace("&lt;", "<").replace("&gt;", ">"))
        return re.sub(r"\s+", " ", s).strip()

    # ---------------- 分类 ----------------
    def _get_classes(self):
        if self._classes:
            return self._classes
        url = ("%s/bvradio_app/hzhs/recommendServlet?functionName=getNavigationBar"
               "&indexId=41&siteId=%s&platform=%s" % (self.api, self.site_id, PLATFORM))
        d = self._get(url)
        out = []
        if d and d.get("code") == 200 and isinstance(d.get("data"), list):
            for it in d["data"]:
                tid = str(it.get("dataId") or "")
                name = it.get("name") or ""
                if tid and name and name != "首页":
                    out.append({"type_id": tid, "type_name": name})
        self._classes = out or DEFAULT_CLASSES
        self.log("classes: %s" % [(c["type_id"], c["type_name"]) for c in self._classes])
        return self._classes

    def homeContent(self, filter=False):
        classes = self._get_classes()
        filters = {}
        for c in classes:
            filters[c["type_id"]] = [
                {"key": "sort", "name": "排序", "value": SORT_OPTIONS},
            ]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 首页用 modeId=1033
        return {"list": self._mode_list("1033")}

    # ---------------- 列表（getRecommond） ----------------
    def _pick(self, item, *keys):
        for k in keys:
            if item.get(k):
                return item.get(k)
        return ""

    def _parse_items(self, nodes):
        """从 getRecommond 返回的 data[].manualList[] / childModels 中提取视频"""
        videos = []
        seen = set()

        def walk(node):
            if not isinstance(node, dict):
                return
            ml = node.get("manualList")
            if isinstance(ml, list):
                for it in ml:
                    self._append(videos, seen, it)
            ch = node.get("childModels")
            if isinstance(ch, list):
                for c in ch:
                    walk(c)

        if isinstance(nodes, list):
            for n in nodes:
                walk(n)
        return videos

    def _append(self, videos, seen, it):
        if not isinstance(it, dict):
            return
        raw_id = str(it.get("id") or "")
        # id 形如 "961,179271" -> nodeId,newsId
        node_id, news_id = "", ""
        if "," in raw_id:
            parts = raw_id.split(",")
            node_id, news_id = parts[0].strip(), parts[1].strip()
        if not news_id:
            news_id = str(it.get("newsId") or "")
            node_id = str(it.get("nodeId") or node_id)
        if not news_id:
            # 尝试从 reqUrl 解析
            req = it.get("reqUrl") or ""
            m = re.search(r"newsId=(\d+).*?nodeId=(\d+)", req)
            if m:
                news_id, node_id = m.group(1), m.group(2)
        if not news_id:
            return

        title = self._clean(it.get("title")) or self._clean(it.get("subTitle"))
        if not title:
            return
        vod_id = "%s,%s" % (node_id, news_id)
        if vod_id in seen:
            return
        seen.add(vod_id)

        pic = (it.get("hPic") or it.get("pPic") or it.get("coverPic") or "").strip()
        remarks = ""
        if it.get("episodeDesc"):
            remarks = self._clean(it.get("episodeDesc"))
        elif it.get("cornerMark"):
            remarks = self._clean(it.get("cornerMark"))

        videos.append({
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remarks,
        })

    def _mode_list(self, mode_id):
        url = ("%s/bvradio_app/hzhs/recommendServlet?functionName=getRecommond"
               "&modeId=%s&siteId=%s&platform=%s" % (self.api, mode_id, self.site_id, PLATFORM))
        d = self._get(url)
        if not d or d.get("code") != 200:
            self.log("mode %s 无数据: %s" % (mode_id, (d or {}).get("message")))
            return []
        return self._parse_items(d.get("data"))

    def categoryContent(self, tid, pg, filter, extend):
        """
        说明：getRecommond 接口为一次性全量返回（实测 page=2 恒为空），
        故这里不做真实翻页，pagecount 固定为 1，首屏即给出该分类全部内容。
        """
        self._get_classes()
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        extend = extend or {}

        videos = self._mode_list(str(tid))
        # 兜底：个别栏目（如“片库”）本身是二级门户，无直接可播内容时给出首页内容
        if not videos:
            self.log("category %s 无直接内容, 回退首页" % tid)
            videos = self._mode_list("1033")

        self.log("category tid=%s -> %d 条" % (tid, len(videos)))
        return {
            "list": videos,
            "page": page,
            "pagecount": 1,
            "limit": len(videos) or 24,
            "total": len(videos),
        }

    # ---------------- 搜索（searchServlet） ----------------
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        kw = urllib.parse.quote(key)
        url = ("%s/rmp-user-suggest/10001/hzhs/searchServlet?functionName=getServiceAndNewsSearch"
               "&keyword=%s&page=%d&pageSize=24&siteId=%s&platform=%s"
               % (self.search_api, kw, page, self.site_id, PLATFORM))
        d = self._get(url)
        videos = []
        seen = set()
        if d and d.get("code") == 200 and isinstance(d.get("data"), dict):
            data = d["data"]
            merged = []
            for k in ("videoDataList", "shortVideoDataList", "serviceDataList"):
                v = data.get(k)
                if isinstance(v, list):
                    merged.extend(v)
            for it in merged:
                self._append(videos, seen, it)
        self.log("search '%s' -> %d 条" % (key, len(videos)))
        limit = 24
        return {
            "list": videos,
            "page": page,
            "pagecount": 1 if len(videos) < limit else page + 1,
            "limit": limit,
            "total": len(videos),
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------------- 详情（getCurrentNews） ----------------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        node_id, news_id = "", ""
        if "," in vod_id:
            node_id, news_id = vod_id.split(",", 1)
        else:
            news_id = vod_id
        url = ("%s/bvradio_app/hzhs/newsServlet?functionName=getCurrentNews"
               "&newsId=%s&nodeId=%s&siteId=%s&platform=%s"
               % (self.api, news_id, node_id, self.site_id, PLATFORM))
        d = self._get(url)
        if not d or d.get("code") != 200 or not isinstance(d.get("data"), dict):
            self.log("detail 无数据: %s" % (d or {}).get("message"))
            return {"list": []}
        data = d["data"]

        title = self._clean(data.get("title")) or news_id
        pic = (data.get("hPic") or data.get("pPic") or "").strip()

        # 简介
        content = self._clean(data.get("newsAbstract") or data.get("content") or "")
        actor = self._clean(data.get("actor") or "")
        director = self._clean(data.get("director") or "")
        score = str(data.get("score") or "")

        # 剧集/线路：每集可能含多个清晰度（fileList），按清晰度拆成多条线路
        vod_list = data.get("vodList") or []

        # 收集所有出现过的清晰度 type，按数值降序（越清晰越靠前）
        quality_types = set()
        for v in vod_list:
            if not isinstance(v, dict):
                continue
            for f in (v.get("fileList") or []):
                if isinstance(f, dict) and f.get("playUrl"):
                    quality_types.add(int(f.get("type") or 0))
        # 稳定的清晰度顺序：已知的按 100<110<120<130，未知的排后
        quality_order = sorted(quality_types, key=lambda t: (t not in QUALITY_ALIAS, -t))

        # 每条线路：{线路名: [ "集名$playUrl", ... ]}
        lines = {}
        for qt in quality_order:
            qname = QUALITY_ALIAS.get(qt, "线路%s" % qt)
            eps = []
            for v in vod_list:
                if not isinstance(v, dict):
                    continue
                ep_name = self._clean(v.get("title")) or ("第%s集" % v.get("episode"))
                play = ""
                for f in (v.get("fileList") or []):
                    if isinstance(f, dict) and int(f.get("type") or 0) == qt and f.get("playUrl"):
                        play = f["playUrl"]
                        break
                # 该集缺失此清晰度时，用该集任意一个可用地址兜底，避免断集
                if not play:
                    allf = v.get("fileList") or []
                    if allf and isinstance(allf[0], dict):
                        play = allf[0].get("playUrl") or ""
                if play:
                    eps.append("%s$%s" % (ep_name, play))
            if eps:
                lines[qname] = eps

        # 兜底：极端情况下用原有单线路
        if not lines:
            eps = []
            for v in vod_list:
                if not isinstance(v, dict):
                    continue
                fl = v.get("fileList") or []
                if fl and isinstance(fl[0], dict) and fl[0].get("playUrl"):
                    ep_name = self._clean(v.get("title")) or ("第%s集" % v.get("episode"))
                    eps.append("%s$%s" % (ep_name, fl[0]["playUrl"]))
            if eps:
                lines["华数TV"] = eps

        if not lines:
            return {"list": []}

        play_from = "$$$".join(lines.keys())
        play_url = "$$$".join("#".join(eps) for eps in lines.values())

        # 简介加来源前缀（与需求一致）
        remarks = self._clean(data.get("subTitle")) or data.get("newsTypeStr") or ""
        vod_content = INTRO_PREFIX
        if content:
            vod_content = INTRO_PREFIX + "\n" + content

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": vod_content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_score": score,
            "vod_year": str(data.get("yearTag") or ""),
            "vod_area": self._clean(data.get("countryTag") or ""),
            "vod_remarks": remarks,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }]}

    # ---------------- 播放（getPlayUrl + 签名） ----------------
    def playerContent(self, flag, id, vipFlags):
        # id 为详情里的 fileList[].playUrl（形如 .../xxx.mp4）
        play_id = id
        if not play_id:
            return {"parse": 1, "playUrl": "", "url": "", "header": {}}

        # 命中缓存
        now = int(time.time())
        if play_id in self._play_cache:
            ts, res = self._play_cache[play_id]
            if now - ts < 1800:
                return res

        # mp4 -> playlist.m3u8（与前端 rt() 逻辑一致）
        m3u8_in = play_id
        base = play_id.split("?")[0]
        if base.endswith(".mp4"):
            m3u8_in = base[:-4] + "/playlist.m3u8"
        elif ".m3u8" not in base:
            m3u8_in = base.rstrip("/") + "/playlist.m3u8"

        body = {"playUrl": m3u8_in, "platform": PLATFORM}
        d = self._post_play(body)
        real_url = ""
        if d and d.get("code") == 200 and isinstance(d.get("data"), dict):
            real_url = d["data"].get("playUrl") or ""

        if real_url:
            res = {
                "parse": 0,
                "playUrl": "",
                "url": real_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": "https://www.wasu.cn/",
                },
            }
            self._play_cache[play_id] = (now, res)
            self.log("play OK -> %s" % real_url[:120])
            return res

        # 兜底：直接把原始地址交给 TVBox（可能因缺 auth_key 失败）
        self.log("play 换 auth_key 失败, 兜底返回原地址")
        res = {
            "parse": 0,
            "playUrl": "",
            "url": play_id,
            "header": {"User-Agent": UA, "Referer": "https://www.wasu.cn/"},
        }
        self._play_cache[play_id] = (now, res)
        return res

    # ---------------- 其他 ----------------
    def isVideoFormat(self, url):
        return bool(url and (".m3u8" in url or ".mp4" in url))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [200, "text/plain", "", ""]

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ===================== 独立自测 =====================
if __name__ == "__main__":
    sp = Spider()
    sp.init()
    print("=== homeContent ===")
    hc = sp.homeContent()
    print(json.dumps(hc["class"], ensure_ascii=False))
    print("=== categoryContent 电影(1036) ===")
    cc = sp.categoryContent("1036", "1", False, {})
    print("条数:", len(cc["list"]))
    for v in cc["list"][:3]:
        print("  ", v["vod_name"], "|", v["vod_id"], "|", v["vod_pic"][:60])
    print("=== searchContent 哆啦A梦 ===")
    sc = sp.searchContent("哆啦A梦", False, "1")
    print("条数:", len(sc["list"]))
    for v in sc["list"][:3]:
        print("  ", v["vod_name"], "|", v["vod_id"])
    if cc["list"]:
        vid = cc["list"][0]["vod_id"]
        print("=== detailContent", vid, "===")
        dc = sp.detailContent([vid])
        if dc["list"]:
            d = dc["list"][0]
            print("  名称:", d["vod_name"])
            print("  简介:", d["vod_content"][:80])
            froms = d["vod_play_from"].split("$$$")
            urls = d["vod_play_url"].split("$$$")
            print("  线路:", froms)
            for i, fn in enumerate(froms):
                eps = urls[i].split("#")
                print("    [%s] 集数=%d 首集=%s" % (fn, len(eps), eps[0].split("$")[0]))
            # 播放最高清线路的第1集
            first = urls[0].split("#")[0].split("$", 1)[-1]
            print("=== playerContent (线路=%s) ===" % froms[0])
            pc = sp.playerContent(froms[0], first, {})
            print("  url:", pc.get("url", "")[:150])


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
