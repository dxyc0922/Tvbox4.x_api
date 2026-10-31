# coding=utf-8
"""
金牌影院(蓝兔子) www.lwdys.com | TVBox Python 爬虫 
关键:
  - 全站走 /mw-movie/anonymous 接口, 服务端签名 sign = SHA1(MD5(排序参数 + key + t))
  - 分类 /anonymous/video/list (class/area/lang/year 与官网筛选一致)
  - 搜索 /anonymous/video/searchByWord
  - 详情 /anonymous/video/detail (含 episodeList)
  - 播放 /anonymous/v2/video/episode/url -> 每集 3 个清晰度
      1080 蓝光 / 720 高清  (登录专享, 未登录服务器拒绝)
      480  标清  (免登录)
    以 3 条线路形式呈现, 可在 extend 配置 {"token": "登录token"} 解锁高清
"""
import re
import sys
import json
import time
import hashlib
import urllib.parse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class _BaseSpider:
        def __init__(self):
            self._session = None

        @property
        def _sess(self):
            if self._session is None:
                self._session = _rq.Session()
                self._session.verify = False
                adapter = _rq.adapters.HTTPAdapter(
                    pool_connections=10, pool_maxsize=10, max_retries=0)
                self._session.mount('https://', adapter)
                self._session.mount('http://', adapter)
            return self._session

        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = self._sess.get(url, headers=headers, timeout=timeout, **kw)
            r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[lwdys]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.lwdys.com"
API = HOST + "/mw-movie/anonymous"

# 从前端 JS (chunk 2844) 逆向得到的固定 signKey
SIGN_KEY = "cb808529bae6b6be45ecfab29a4889bc"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "88", "type_name": "短剧"},
]

# ===== 修复：严格按照官方网页源码 filerList 里的 itemValue（数字ID），补全所有筛选条件 =====
_FILTERS_MAP = {
    "1": {
        "type": [("喜剧", "22"), ("动作", "23"), ("科幻", "30"), ("爱情", "26"), 
                 ("悬疑", "27"), ("奇幻", "87"), ("剧情", "37"), ("恐怖", "36"), 
                 ("犯罪", "35"), ("动画", "33"), ("惊悚", "34"), ("战争", "25"), 
                 ("冒险", "31"), ("灾难", "81"), ("伦理", "83"), ("其他", "43")],
        "class": ["剧情", "喜剧", "动作", "爱情", "惊悚", "犯罪", "恐怖",
                  "悬疑", "冒险", "奇幻", "科幻", "动画", "战争", "灾难", "伦理", "其他"],
        "area": ["中国大陆", "中国香港", "中国台湾", "美国", "韩国", "日本",
                 "英国", "法国", "泰国", "印度", "其他"],
        "lang": ["国语", "粤语", "英语", "韩语", "日语", "其他"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020",
                 "2019", "2018", "2017", "2016", "2015", "2014", "2013",
                 "2012", "2011", "2010", "2009~2000"],
    },
    "2": {
        "type": [("国产剧", "14"), ("欧美剧", "15"), ("港台剧", "16"), 
                 ("日韩剧", "62"), ("其他剧", "68")],
        "class": ["剧情", "喜剧", "动作", "爱情", "悬疑", "犯罪", "家庭",
                  "奇幻", "历史", "古装", "战争", "短片", "其他"],
        "area": ["中国大陆", "中国香港", "中国台湾", "美国", "韩国", "日本",
                 "泰国", "其他"],
        "lang": ["国语", "粤语", "英语", "韩语", "日语", "泰语", "其他"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020",
                 "2019", "2018", "2017", "2016", "2015", "2014", "2013",
                 "2012", "2011", "2010"],
    },
    "3": {
        "type": [("国产综艺", "69"), ("港台综艺", "70"), ("日韩综艺", "72"), ("欧美综艺", "73")],
        "class": ["真人秀", "脱口秀", "音乐"],
        "area": ["中国大陆", "中国香港", "中国台湾", "美国", "韩国", "日本", "其他"],
        "lang": ["国语", "粤语", "英语", "韩语", "日语", "其他"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020"],
    },
    "4": {
        "type": [("国产动漫", "75"), ("日韩动漫", "76"), ("欧美动漫", "77")],
        "class": ["冒险", "动作", "动画", "喜剧", "战争", "热血", "科幻", "运动"],
        "area": ["中国大陆", "日本", "美国", "其他"],
        "lang": ["国语", "日语", "英语", "其他"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020",
                 "2019", "2018", "2017", "2016", "2015", "2014", "2013",
                 "2012", "2011", "2010"],
    },
    "88": {
        "type": [("喜剧", "100"), ("奇幻", "99"), ("惊悚", "98"), ("悬疑", "97"), 
                 ("古装", "96"), ("剧情", "94"), ("爱情", "95")],
        "class": ["爱情", "甜宠", "科幻", "穿越", "虐恋", "逆袭", "重生",
                  "冒险", "剧情", "动作", "战争", "武侠", "其他"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "更早"],
        "lang": [],
    },
}

_FILTER_KEYS = [("type", "分类"), ("class", "剧情"), ("area", "地区"),
                ("lang", "语言"), ("year", "年份")]

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    fmap = _FILTERS_MAP.get(tid, {})
    fl = []
    for key, name in _FILTER_KEYS:
        vals = fmap.get(key)
        if not vals:
            continue
        
        # 组装筛选列表，处理元组 (名称, 真实ID) 的情况
        v_list = [{"n": "全部", "v": ""}]
        for x in vals:
            if isinstance(x, tuple):
                v_list.append({"n": x[0], "v": x[1]})
            else:
                v_list.append({"n": x, "v": x})
                
        fl.append({"key": key, "name": name, "value": v_list})
    FILTERS[tid] = fl

# ===== 清晰度线路 (与官网播放器清晰度菜单一致) =====
# 接口按此顺序返回: 0=1080蓝光(登录专享) 1=720高清(登录专享) 2=480标清(免登录)
_RES_LINES = [
    {"name": "蓝光1080P(登录专享)", "resolution": 1080},
    {"name": "高清720P(登录专享)",  "resolution": 720},
    {"name": "标清480P",            "resolution": 480},
]


class Spider(Spider):

    def getName(self):
        return "金牌影院"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}
        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        # 可选: {"token": "登录后抓到的 authorization token"} 解锁1080/720
        self.token = self.extend.get("token") or ""
        self.headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
            "Origin": self.site_url,
        }
        self.default_pic = "https://obs.3688baihuo.com/upload/vod_default.webp"
        self._play_cache = {}
        self.log("init: site=%s token=%s" %
                 (self.site_url, "有" if self.token else "无"))

    # ===================== 签名 =====================
    def _sign(self, params):
        """sign = SHA1( MD5( 排序参数串 + '&key=..&t=..' ) )"""
        t = str(int(time.time() * 1000))
        ps = {k: str(v) for k, v in params.items()
              if v is not None and str(v) != ""}
        h = "&".join("%s=%s" % (k, ps[k]) for k in sorted(ps))
        h += "&key=%s&t=%s" % (SIGN_KEY, t)
        sign = hashlib.sha1(
            hashlib.md5(h.encode("utf-8")).hexdigest().encode("utf-8")
        ).hexdigest()
        return ps, t, sign

    def _api_get(self, path, params=None, timeout=15):
        try:
            ps, t, sign = self._sign(params or {})
            headers = dict(self.headers)
            headers.update({
                "sign": sign,
                "t": t,
                "authorization": self.token,
                "deviceId": "web-" + "0" * 16,
            })
            url = API + path
            if ps:
                url += "?" + urllib.parse.urlencode(ps)
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            text = rsp.text if hasattr(rsp, "text") else str(rsp)
            try:
                data = json.loads(text)
            except Exception:
                self.log("api %s 非 JSON: %s" % (path, text[:120]))
                return None
            if data.get("code") != 200:
                self.log("api %s code=%s msg=%s" %
                         (path, data.get("code"), data.get("msg")))
                return None
            return data.get("data")
        except Exception as e:
            self.log("api %s FAIL: %s" % (path, e))
            return None

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    # ===================== 列表通用 =====================
    def _video_to_item(self, it):
        pic = it.get("vodPic") or self.default_pic
        name = self._clean(it.get("vodName") or "")[:100]
        remark = it.get("vodRemarks") or ""
        if not remark and it.get("vodScore"):
            try:
                remark = "%.1f分" % float(it["vodScore"])
            except Exception:
                remark = str(it.get("vodScore"))
        return {
            "vod_id": str(it.get("vodId", "")),
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": str(remark)[:20],
        }

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        # 用电影分类第一页作为推荐位
        data = self._api_get("/video/list",
                             {"type1": 1, "pageNum": 1, "pageSize": 24})
        videos = []
        if data and data.get("list"):
            videos = [self._video_to_item(x) for x in data["list"]]
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}

        params = {
            "type1": tid,
            "pageNum": page,
            "pageSize": 24,
        }
        # 这里的 type 已经变成 14, 15 等真实 ID 了
        if extend.get("type"):
            params["type"] = extend["type"]
        if extend.get("class"):
            params["class"] = extend["class"]
        if extend.get("year"):
            params["year"] = extend["year"]
        if extend.get("area"):
            params["area"] = extend["area"]
        if extend.get("lang"):
            params["lang"] = extend["lang"]

        data = self._api_get("/video/list", params)
        videos = []
        pagecount = 1
        total = 0
        if data and data.get("list"):
            videos = [self._video_to_item(x) for x in data["list"]]
            try:
                pagecount = int(data.get("totalPage") or 1)
                total = int(data.get("totalCount") or 0)
            except Exception:
                pass
        self.log("category %s page=%d -> %d 条" % (tid, page, len(videos)))

        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 24, "total": total,
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        data = self._api_get("/video/searchByWord", {
            "keyword": key, "pageNum": page, "pageSize": 20,
        })
        videos = []
        pagecount = 1
        total = 0
        if data:
            res = data.get("result") or {}
            if res.get("list"):
                videos = [self._video_to_item(x) for x in res["list"]]
            try:
                pagecount = int(res.get("totalPage") or 1)
                total = int(res.get("totalCount") or 0)
            except Exception:
                pass
        self.log("search '%s' page=%d -> %d 条" % (key, page, len(videos)))

        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 20, "total": total,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ===================== 详情 =====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        data = self._api_get("/video/detail", {"id": vod_id})
        if not data:
            return {"list": []}

        name = self._clean(data.get("vodName") or "") or vod_id
        pic = data.get("vodPic") or self.default_pic

        # 1. 纯净的简介 (绝不拼接任何参数)
        content = self._clean(data.get("vodContent") or "") \
            or self._clean(data.get("vodBlurb") or "")
        if content:
            content = INTRO_PREFIX + "\n" + content
        else:
            content = INTRO_PREFIX

        # 2. 规范赋值，避免 UI 重复渲染前缀
        actor = self._clean(data.get("vodActor") or "")
        actor = re.sub(r",\s*", ", ", actor)
        director = self._clean(data.get("vodDirector") or "")

        score = ""
        try:
            if data.get("vodDoubanScore"):
                score = str(data["vodDoubanScore"])
            elif data.get("vodScore"):
                score = str(data["vodScore"])
        except Exception:
            pass

        remarks = self._clean(data.get("vodRemarks") or "")
        year = data.get("vodYear") or ""
        area = data.get("vodArea") or ""
        vclass = data.get("vodClass") or ""
        
        # ===== 剧集: 每个清晰度一条线路, id = "vodId-nid-清晰度下标" =====
        eps = data.get("episodeList") or []
        eps = sorted(eps, key=lambda e: e.get("sort") or 0)

        play_from = []
        play_url = []
        for li, line in enumerate(_RES_LINES):
            eps_txt = "#".join(
                "%s$%s-%s-%d" % (self._clean(e.get("name") or
                                             ("第%d集" % (i + 1))),
                                 vod_id, e.get("nid"), li)
                for i, e in enumerate(eps) if e.get("nid"))
            if eps_txt:
                play_from.append(line["name"])
                play_url.append(eps_txt)

        # 3. 返回数据：将元数据放入标准专属字段，让播放器自动上浮显示
        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,        # 纯简介
            "vod_actor": actor,            # 系统自动渲染
            "vod_director": director,      # 系统自动渲染，去掉重复的“导演：”
            "vod_score": score,
            "vod_remarks": remarks or ("共%d集" % len(eps) if eps else ""),
            "vod_year": str(year),         # 系统自动提取到海报旁边
            "vod_area": str(area),         # 系统自动提取到海报旁边
            "vod_class": str(vclass),      # 系统自动提取到海报旁边
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ===================== 播放 =====================
    def playerContent(self, flag, id, vipFlags):
        # id 格式: "vodId-nid-清晰度下标"
        parts = str(id).split("-")
        if len(parts) >= 3:
            vod_id, nid, res_idx = parts[0], parts[1], int(parts[2])
        elif len(parts) == 2:
            vod_id, nid, res_idx = parts[0], parts[1], 2
        else:
            vod_id, nid, res_idx = "0", str(id), 2
        self.log("player: vod=%s nid=%s res_idx=%d" % (vod_id, nid, res_idx))

        cache_key = "%s-%s-%d-%s" % (vod_id, nid, res_idx, bool(self.token))
        now = int(time.time())
        if cache_key in self._play_cache:
            ts, res = self._play_cache[cache_key]
            if now - ts < 600:
                return res

        # clientType=1 (Web)。返回按清晰度排列的直链列表
        data = self._api_get("/v2/video/episode/url", {
            "id": vod_id,
            "nid": nid,
            "clientType": 1,
        })

        url = ""
        picked = None
        if data and data.get("list"):
            items = [it for it in data["list"] if it.get("url")]
            if items:
                # 1) 优先取请求的下标对应清晰度
                want = _RES_LINES[res_idx]["resolution"] \
                    if 0 <= res_idx < len(_RES_LINES) else 480
                for it in items:
                    if (it.get("resolution") or 0) == want:
                        picked = it
                        break
                # 2) 取不到则从请求清晰度向下逐级回退 (1080->720->480)
                if picked is None:
                    order = [x["resolution"] for x in _RES_LINES]
                    try:
                        wi = order.index(want)
                    except Exception:
                        wi = len(order) - 1
                    for r in order[wi:]:
                        for it in items:
                            if (it.get("resolution") or 0) == r:
                                picked = it
                                break
                        if picked:
                            break
                # 3) 仍取不到则取第一个
                if picked is None:
                    picked = items[0]
                url = picked["url"]
                self.log("  => %sP: %s" %
                         (picked.get("resolution", "?"), url[:120]))

        if url:
            res = {
                "parse": 0,
                "playUrl": "",
                "url": url,
                "header": {
                    "User-Agent": UA,
                    "Referer": self.site_url + "/",
                },
            }
        else:
            # 兜底: 交给嗅探
            res = {
                "parse": 1,
                "playUrl": "",
                "url": "%s/vod/play/%s/sid/%s" % (self.site_url, vod_id, nid),
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
        self._play_cache[cache_key] = (now, res)
        return res

    def localProxy(self, param):
        return [200, "image/jpeg", b"", ""]

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url or url.startswith("http")

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
