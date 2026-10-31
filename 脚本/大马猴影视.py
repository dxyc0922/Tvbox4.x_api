# coding=utf-8
"""
SkyKB 影视爬虫 (大马猴影视 skykb.com) - TVBox Python Spider

【网站结构】
1. 站点为 Vue3 SPA，首页 HTML 仅 <div id="app"></div>，不含任何影视数据；
   所有数据均通过 https://skykb.com/api.php/web/* 接口以 JSON 返回。
2. 接口清单（取自 /assets/index-DRlQFQTh.js 中的常量表）：
     GET /api.php/web/index/home                 首页（categories 内含分类与筛选值）
     GET /api.php/web/filter/vod                 分类列表
          ?type_id=22&page=1&sort=hits[&class=&area=&year=&type_name=]
          返回 {code,msg,data[],total,page,limit,pageCount}
     GET /api.php/web/search/index?wd=&page=&limit=
          返回 {code,msg,data[],total,page,limit,pageCount,hasMore}
     GET /api.php/web/vod/get_detail?vod_id=     详情（需签名，否则 vod_play_from 为空）
     GET /api.php/web/internal/search_aggregate?vod_id=  聚合备用线路（需签名）
3. 请求签名（前端 Ze():
     raw = "finger={finger}&id={appId}&nonce={32位hex}&sk={secretKey}&time={13位毫秒}&v=1"
     x-sign = SHA256(raw).hexdigest().upper()
   同时必须携带 x-aid / x-ave / x-time / x-nonc / x-platform: web / x-client。
   【实测】不带签名访问 get_detail，vod_play_from 返回 ""；带签名返回 "lzm3u8$$$Ace"。
4. 播放地址为第三方 CDN 的 m3u8 直链（实测 HTTP 200，可直接播放），无需二次解析。
5. 详情接口的 vod_play_from / vod_play_url 本身已是 TVBox 格式：
     from 之间用 "$$$" 分隔，同一线路的剧集 "第01集$url" 之间用 "#" 分隔。
6. 分页：page 从 1 开始；分类固定每页 24 条（limit=24），pageCount 由接口给出，越界页返回空数组。
7. 【decode/url 实测结论】
   - 网页端 ACE 播放流程（Playwright 抓包证实）：
     POST /api.php/web/decode/url -> 解出 S3 直链 -> 浏览器 GET Range 拉流(206)。
     注意播放页线路定位用 hash（#sid=Ace&nid=1），query 参数 from/source 不生效。
   - 解出的 S3 直链（cmecloud EOS）：GET 一律 200/206（任意 Range 形式、任意协议版本、
     任意 UA、无 Referer 均可）；HEAD 恒为 403（S3 签名仅允许 GET）。
   - 直链 X-Amz-Expires=900（15 分钟），过期后一切请求 403 —— 必须播放时现解。
   - 直链查询参数全被 AWS 签名保护（response-content-disposition=attachment 不可改 inline）。
   - /api.php/proxy/media 站内代理对无 after_parse 配置的线路返回
     403 "after-parse config not available"，ACE 不可走该代理（RR 才有 after-parse）。
   - 站点前端的 mediaProxy 拼接条件（Cn()）：afterParseStatus==1 且配置了
     UA/Headers 且 URL 命中 afterParseFeatures —— ACE 三者皆空，网页同样不走代理。
8. 解码容错：_decode_url 内置 3 次重试（每次全新签名），结果按 TTL 缓存
   （900s 有效期，剩余 <120s 即重解）；解码失败时按同下标回退其它直连线路同集数。
"""
import re
import sys
import json
import time
import html as _html
import hashlib
import secrets
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
                print("[skykb]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://skykb.com"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ---- 前端硬编码的签名参数（源: index-DRlQFQTh.js 中 const ae = {...}）----
APP_ID = "cde75dbd61ce274e07e8ce29"
APP_FINGER = "505a0e62069a061e07698eb4b6327d88"
APP_SECRET = "9b1fccddb6f8e1b385de7e6e736e050144a7f3a208130fff"
APP_VERSION = "1"
CLIENT_ID = "YOUR_PUBLIC_CLIENT_ID"

DEFAULT_PIC = ""

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 分类兜底值：真实值来自 index/home 的 categories，接口异常时才使用
_CLASS_FALLBACK = [
    {"type_id": "22", "type_name": "剧集"},
    {"type_id": "23", "type_name": "电影"},
    {"type_id": "24", "type_name": "动漫"},
    {"type_id": "25", "type_name": "综艺"},
]

# 排序：前端 filter/vod 默认 sort=hits，实测 time 可切换到最新
_SORTS = [{"n": "最热", "v": "hits"}, {"n": "最新", "v": "time"}]

# 线路别名兜底（真实显示名取自 get_detail 的 vodplayer[].show）
_LINE_ALIAS = {
    "lzm3u8": "量子M3U8", "Ace": "ACE", "jsm3u8": "极速", "bfzym3u8": "暴风",
    "ikm3u8": "爱坤", "RR": "RR", "BBA": "BB", "NBY": "NB", "rose": "Rose",
    "vwnet": "VW", "YYNB": "YYNB",
}

# 站点 decode_status 取值（前端 On()：status == "2" 抛「线路维护中」）：
#   0 -> 地址为解析后的真实播放地址（可直接播）
#   1 -> 地址为密文串，需前端用 WASM 作服务端解码，TVBox 无法直连
_STATUS_MAINTENANCE = "2"
_STATUS_DECODED = "0"


class Spider(Spider):

    def getName(self):
        return "大马猴影视"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
            "x-platform": "web",
            "x-client": CLIENT_ID,
        }
        self._home_cache = None
        self._tid2name = {}       # 分类type_id -> 中文分类名（filter/vod 用 type_name 过滤）
        self._last_vod_id = ""
        self._label_to_from = {}  # 线路显示名 -> 站点 from 代号（详情时填充）
        # 详情时缓存各线路原始剧集地址，用于解码失败时同集数回退（实测样本见下）
        self._line_eps = []       # [(from代号, [ep_url,...]), ...] 按站点顺序
        # 解码结果缓存：实测 ACE 解出的 S3 直链 X-Amz-Expires=900（15分钟），
        # 且过期后所有请求 403；因此缓存有效期按剩余 <120s 即重解处理
        self._decoded_cache = {}  # (vod_from, ep_url) -> (real_url, 解码时刻)
        self._DECODE_TTL = 900
        self._DECODE_MARGIN = 120
        self.log("init: site=%s" % self.site_url)

    # ================= 签名 =================
    def _sign_values(self):
        """复现前端签名：SHA256(finger=..&id=..&nonce=..&sk=..&time=..&v=..) 大写
        返回 (13位毫秒时间戳, 32位hex随机数, 签名)"""
        ts = str(int(time.time() * 1000))
        nonce = secrets.token_hex(16)  # 16 字节 -> 32 位 hex，同前端 getRandomValues(16)
        raw = "finger=%s&id=%s&nonce=%s&sk=%s&time=%s&v=%s" % (
            APP_FINGER, APP_ID, nonce, APP_SECRET, ts, APP_VERSION)
        sign = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
        return ts, nonce, sign

    def _sign_headers(self):
        ts, nonce, sign = self._sign_values()
        return {
            "x-aid": APP_ID,
            "x-ave": APP_VERSION,
            "x-time": ts,
            "x-nonc": nonce,
            "x-sign": sign,
        }

    # ================= 请求 =================
    def _get_json(self, path, params=None, signed=False, referer=None):
        url = path if path.startswith("http") else self.site_url + path
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

        h = dict(self.headers)
        if referer:
            h["Referer"] = referer
        if signed:
            h.update(self._sign_headers())

        try:
            rsp = self.fetch(url, headers=h, timeout=20)
            text = ""
            if hasattr(rsp, "text"):
                text = rsp.text or ""
            elif hasattr(rsp, "content"):
                text = rsp.content.decode("utf-8", "ignore")
            else:
                text = str(rsp)
            if not text:
                self.log("empty response: %s" % url)
                return {}
            return json.loads(text)
        except Exception as e:
            self.log("request FAIL %s -> %s" % (url, e))
            return {}

    # ================= 工具 =================
    def _clean(self, s):
        if s is None:
            return ""
        s = str(s)
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = _html.unescape(s)
        s = s.replace("\xa0", " ")
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _join_list(self, v):
        """vod_area / vod_class 在列表接口是数组，在搜索接口是字符串"""
        if isinstance(v, list):
            return ",".join([str(x).strip() for x in v if str(x).strip()])
        return self._clean(v)

    def _fix_pic(self, pic):
        if not pic:
            return DEFAULT_PIC
        pic = str(pic).strip()
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("http"):
            return pic
        if pic.startswith("/"):
            return self.site_url + pic
        return pic

    def _vod_item(self, v):
        """把接口条目转为 TVBox 标准 vod"""
        vod_id = str(v.get("vod_id", "") or "").strip()
        return {
            "vod_id": vod_id,
            "vod_name": self._clean(v.get("vod_name"))[:100],
            "vod_pic": self._fix_pic(v.get("vod_pic")),
            "vod_remarks": self._clean(v.get("vod_remarks")),
            "vod_year": str(v.get("vod_year") or ""),
        }

    def _items_to_list(self, items):
        out = []
        seen = set()
        for v in items or []:
            if not isinstance(v, dict):
                continue
            vod_id = str(v.get("vod_id", "") or "").strip()
            if not vod_id or vod_id == "0" or vod_id in seen:
                continue
            seen.add(vod_id)
            out.append(self._vod_item(v))
        return out

    # ================= 首页配置 =================
    def _load_home(self):
        if self._home_cache is not None:
            return self._home_cache
        d = self._get_json("/api.php/web/index/home")
        data = d.get("data") if isinstance(d, dict) and d.get("code") == 200 else None
        # 接口异常时 data 可能是 null，统一兜成空 dict，避免后续 .get 崩溃
        self._home_cache = data if isinstance(data, dict) else {}
        return self._home_cache

    def _build_classes_and_filters(self):
        """分类与筛选项完全按接口 categories[].filter_options 生成"""
        home = self._load_home()
        cats = home.get("categories") or []
        if not isinstance(cats, list) or not cats:
            return list(_CLASS_FALLBACK), {}

        classes = []
        filters = {}
        for c in cats:
            if not isinstance(c, dict):
                continue
            tid = str(c.get("type_id", "")).strip()
            tname = self._clean(c.get("type_name"))
            if not tid:
                continue
            classes.append({"type_id": tid, "type_name": tname})
            if tname:
                self._tid2name[tid] = tname

            fo = c.get("filter_options") or {}
            fl = []

            cls_vals = fo.get("class") or []
            if cls_vals:
                fl.append({
                    "key": "class", "name": "剧情",
                    "value": [{"n": "全部", "v": ""}] +
                             [{"n": str(x), "v": str(x)} for x in cls_vals],
                })

            area_vals = fo.get("area") or []
            if area_vals:
                fl.append({
                    "key": "area", "name": "地区",
                    "value": [{"n": "全部", "v": ""}] +
                             [{"n": str(x), "v": str(x)} for x in area_vals],
                })

            year_vals = fo.get("year") or []
            if year_vals:
                fl.append({
                    "key": "year", "name": "年份",
                    "value": [{"n": "全部", "v": ""}] +
                             [{"n": str(x), "v": str(x)} for x in year_vals],
                })

            fl.append({"key": "sort", "name": "排序", "value": _SORTS})
            filters[tid] = fl

        return classes, filters

    def homeContent(self, filter=False):
        classes, filters = self._build_classes_and_filters()
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        home = self._load_home()
        videos = []
        seen = set()

        # 首页推荐位：接口 recommend 数组（正片/剧集混排）
        for key in ("recommend", "appCarouselVideos", "webCarouselVideos"):
            for v in (home.get(key) or []):
                if not isinstance(v, dict):
                    continue
                vod_id = str(v.get("vod_id", "") or "")
                if not vod_id or vod_id in seen:
                    continue
                seen.add(vod_id)
                videos.append(self._vod_item(v))

        # 各分类前 6 条补齐
        for c in (home.get("categories") or []):
            for v in (c.get("videos") or []):
                if not isinstance(v, dict):
                    continue
                vod_id = str(v.get("vod_id", "") or "")
                if not vod_id or vod_id in seen:
                    continue
                seen.add(vod_id)
                videos.append(self._vod_item(v))

        return {"list": videos}

    # ================= 分类 =================
    def _type_name_of(self, tid):
        """type_id -> 中文分类名；映射未建立时先拉一次首页分类表（惰性初始化）。
        实测无论电视端是先调 homeContent 还是直接调 categoryContent，
        都必须保证此处拿到中文名，否则接口会忽略分类过滤返回全站混合列表。"""
        tid = str(tid).strip()
        if tid not in self._tid2name:
            self._build_classes_and_filters()
        return self._tid2name.get(tid) or tid

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        if page < 1:
            page = 1

        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        # 【实测】filter/vod 的分类过滤参数是 type_name（中文）而非 type_id：
        #   传 type_id=22/23/24/25 服务端一律忽略，返回同一份列表；
        #   传 type_name=剧集/电影/动漫/综艺 才返回对应分类。
        #   且 type_name 可与 class/area/year/sort 组合使用。
        tname = self._type_name_of(tid)
        params = {
            "type_name": tname,
            "page": page,
            "sort": extend.get("sort") or "hits",
        }
        # 参数名与前端 In() 完全一致：class / area / year / type_name
        for key in ("class", "area", "year"):
            val = extend.get(key)
            if val and val != "全部":
                params[key] = val

        d = self._get_json("/api.php/web/filter/vod", params)
        if not d or d.get("code") != 200:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": 24, "total": 0}

        videos = self._items_to_list(d.get("data"))
        pagecount = d.get("pageCount")
        try:
            pagecount = int(pagecount)
        except Exception:
            pagecount = 1
        if pagecount <= 0:
            pagecount = 1

        total = d.get("total")
        try:
            total = int(total)
        except Exception:
            total = len(videos)

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": int(d.get("limit") or 24),
            "total": total,
        }

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        if page < 1:
            page = 1

        d = self._get_json("/api.php/web/search/index", {
            "wd": key,
            "page": page,
            "limit": 15,
        })
        if not d or d.get("code") != 200:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": 15, "total": 0}

        videos = self._items_to_list(d.get("data"))
        pagecount = d.get("pageCount")
        try:
            pagecount = int(pagecount)
        except Exception:
            pagecount = 1
        if pagecount <= 0:
            pagecount = 1

        total = d.get("total")
        try:
            total = int(total)
        except Exception:
            total = len(videos)

        return {"list": videos, "page": page, "pagecount": pagecount,
                "limit": int(d.get("limit") or 15), "total": total}

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ================= 详情 =================
    def _split_from_url(self, play_from, play_url):
        """按站点格式拆线路：from 用 $$$ 分隔，同一线路的剧集 "第01集$url" 用 # 分隔"""
        froms = [x.strip() for x in str(play_from or "").split("$$$")]
        urls = [x.strip() for x in str(play_url or "").split("$$$")]

        result = []
        for i, f in enumerate(froms):
            if not f or i >= len(urls):
                continue
            eps = []
            for seg in urls[i].split("#"):
                seg = seg.strip()
                if not seg or "$" not in seg:
                    continue
                name, url = seg.split("$", 1)
                name = self._clean(name)
                url = url.strip()
                if not url:
                    continue
                eps.append((name or ("第%d集" % (len(eps) + 1)), url))
            if eps:
                result.append((f, eps))
        return result

    def _player_meta(self, vodplayer):
        """vodplayer[] 是线路定义表：
        from -> {show显示名, decode_status, decode_mode, sort, after_referer}
        after_referer 取自 after_parse_headers（如 RR 的 "referer:https://m.yichengwlkj.com/"，
        实测解码后的地址必须带该 Referer 才能访问）
        """
        meta = {}
        if not isinstance(vodplayer, list):
            return meta
        for p in vodplayer:
            if not isinstance(p, dict):
                continue
            key = str(p.get("from") or "").strip()
            if not key:
                continue
            after_ref = ""
            for line in str(p.get("after_parse_headers") or "").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    if k.strip().lower() == "referer":
                        after_ref = v.strip()
            meta[key] = {
                "show": self._clean(p.get("show")) or key,
                "status": str(p.get("decode_status", "0")).strip(),
                "mode": str(p.get("decode_mode") or "").strip(),
                "sort": str(p.get("sort", "") or "").strip(),
                "after_referer": after_ref,
            }
        return meta

    def _line_kind(self, from_code, meta, eps=None):
        """
        判定一条线路的地址真实形态（以实测样本为准，不臆测）：
          m3u8 -> 已是可直连的 m3u8/mp4 地址
                  （如 lzm3u8: https://v.lzcdn31.com/.../index.m3u8，实测 200）
          page -> 网页地址，需要播放器嗅探
                  （如 RR: https://mh.yichengwlkj.com/drama/57746?episodeNo=1，
                    307 跳转 /pc/... 的 Next.js 页面，页面内无 m3u8）
          code -> 站点密文串，需服务端 WASM 解码
                  （如 Ace: Ace_Net-xxxxxxxx，自身不含协议与 .m3u8）
        """
        sample = ""
        if eps:
            sample = (eps[0][1] if isinstance(eps[0], (list, tuple)) else str(eps[0])).strip()
        low = sample.lower()

        if low.startswith("//"):
            low = "https:" + low

        if low.startswith("http"):
            if ".m3u8" in low or ".mp4" in low:
                return "m3u8"
            return "page"

        if sample:
            return "code"

        # 无样本时退回线路定义表
        m = meta.get(from_code) or {}
        if str(m.get("status", "")) == _STATUS_MAINTENANCE:
            return "code"
        if str(m.get("status", "")) == _STATUS_DECODED and str(m.get("mode", "")) in ("", "client"):
            return "m3u8"
        return "code"

    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        vod_id = str(ids[0]).strip()
        m = re.search(r"(\d+)", vod_id)
        if m:
            vod_id = m.group(1)

        play_page = "%s/play/%s" % (self.site_url, vod_id)
        self._last_vod_id = vod_id

        # 详情必须带签名，否则接口会把 vod_play_from / vod_play_url 置空（已实测）
        d = self._get_json("/api.php/web/vod/get_detail",
                           {"vod_id": vod_id}, signed=True, referer=play_page)
        if not d or d.get("code") != 200 or not isinstance(d.get("data"), list) or not d["data"]:
            self.log("detail empty: %s" % vod_id)
            return {"list": []}

        v = d["data"][0]
        meta = self._player_meta(d.get("vodplayer"))

        name = self._clean(v.get("vod_name")) or vod_id
        pic = self._fix_pic(v.get("vod_pic"))

        # 简介：原文前加固定前缀
        body = self._clean(v.get("vod_content"))
        content = (INTRO_PREFIX + "\n" + body) if body else INTRO_PREFIX

        lines = self._split_from_url(v.get("vod_play_from"), v.get("vod_play_url"))

        # 聚合线路：必须以“追加”方式合并，不能只在主线路为空时兜底。
        # 实测 get_detail 只下发部分线路（如仅 lzm3u8$$$Ace），
        # 而同一播放页调用的 internal/search_aggregate 还带有极速/暴风/爱坤等，
        # 部分影片（如 169386 拜托了冰箱）详情线路甚至为空、聚合却有 52 集。
        agg = self._get_json("/api.php/web/internal/search_aggregate",
                             {"vod_id": vod_id}, signed=True, referer=play_page)
        if agg and agg.get("code") == 200 and isinstance(agg.get("data"), list):
            for a in agg["data"]:
                if not isinstance(a, dict):
                    continue
                if str(a.get("decode_status")) == _STATUS_MAINTENANCE:
                    continue
                one = self._split_from_url(a.get("vod_play_from"), a.get("vod_play_url"))
                if not one:
                    continue
                f, eps = one[0]
                # 同一 from 已由详情提供时，保留详情版本（剧集更全），不覆盖
                if any(f == exist[0] for exist in lines):
                    continue
                _after_ref = ""
                for _ln in str(a.get("after_parse_headers") or "").splitlines():
                    if ":" in _ln:
                        _k, _v = _ln.split(":", 1)
                        if _k.strip().lower() == "referer":
                            _after_ref = _v.strip()
                meta.setdefault(f, {
                    "show": self._clean(a.get("site_name")) or _LINE_ALIAS.get(f, f),
                    "status": str(a.get("decode_status", "0")),
                    "mode": str(a.get("decode_mode") or ""),
                    "sort": str(a.get("sort", "") or ""),
                    "after_referer": _after_ref,
                })
                lines.append((f, eps))

        if not lines:
            self.log("no play line: %s" % vod_id)
            return {"list": []}

        # 记录各线路原始剧集地址（解码失败时按同下标回退用）
        self._line_eps = [(f, [e[1] if isinstance(e, (list, tuple)) else e
                               for e in eps]) for f, eps in lines]

        # 排序：完全按站点网页的真实顺序 —— vodplayer[].sort
        # （实测 云播=0 / ACE=4 / RR=5 / 极速·暴风·爱坤=99，
        #   sort 相同时保持聚合接口的返回顺序，即网页上的展示顺序）
        order = {f: i for i, (f, _) in enumerate(lines)}

        def rank(item):
            f = item[0]
            m = meta.get(f) or {}
            try:
                sv = int(float(m.get("sort") or 9999))
            except Exception:
                sv = 9999
            return (sv, order.get(f, 0))

        lines.sort(key=rank)

        play_from = []
        play_url = []
        self._label_to_from = {}
        for f, eps in lines:
            label = meta[f]["show"] if f in meta else _LINE_ALIAS.get(f, f)
            if label in play_from:  # 同名线路去重，避免 TVBox 线路重复
                label = "%s-%s" % (label, f)
            self._label_to_from[label] = (f, (meta.get(f) or {}).get("after_referer") or "")
            play_from.append(label)
            play_url.append("#".join("%s$%s" % (n, u) for n, u in eps))

        remarks = self._clean(v.get("vod_remarks"))
        if not remarks:
            remarks = "%d条线路" % len(play_from)

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": self._clean(v.get("type_name")),
            "vod_year": str(v.get("vod_year") or ""),
            "vod_area": self._join_list(v.get("vod_area")),
            "vod_lang": self._clean(v.get("vod_lang")),
            "vod_remarks": remarks,
            "vod_actor": self._clean(v.get("vod_actor")),
            "vod_director": self._clean(v.get("vod_director")),
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ================= 播放 =================
    # ---- protobuf 编解码（用于 /api.php/web/decode/url，结构与前端 Vt()/Ot() 一致）----
    @staticmethod
    def _pb_varint(n):
        out = b""
        while n >= 0x80:
            out += bytes([(n & 0x7F) | 0x80])
            n >>= 7
        return out + bytes([n])

    @classmethod
    def _pb_str(cls, field, s):
        b = s.encode("utf-8")
        return cls._pb_varint(field << 3 | 2) + cls._pb_varint(len(b)) + b

    @classmethod
    def _pb_int(cls, field, n):
        return cls._pb_varint(field << 3) + cls._pb_varint(int(n))

    @staticmethod
    def _pb_parse(data):
        """极简 protobuf 解析，返回 [(field, wire, value)]（wire=0 为整数，2 为字节串）"""
        out = []
        i = 0
        n = len(data)
        while i < n:
            key = 0
            sh = 0
            while i < n:
                x = data[i]
                i += 1
                key |= (x & 0x7F) << sh
                sh += 7
                if x < 0x80:
                    break
            field, wire = key >> 3, key & 7
            if wire == 0:
                v = 0
                sh = 0
                while i < n:
                    x = data[i]
                    i += 1
                    v |= (x & 0x7F) << sh
                    sh += 7
                    if x < 0x80:
                        break
                out.append((field, wire, v))
            elif wire == 2:
                ln = 0
                sh = 0
                while i < n:
                    x = data[i]
                    i += 1
                    ln |= (x & 0x7F) << sh
                    sh += 7
                    if x < 0x80:
                        break
                out.append((field, wire, data[i:i + ln]))
                i += ln
            elif wire == 5:
                out.append((field, wire, data[i:i + 4]))
                i += 4
            elif wire == 1:
                out.append((field, wire, data[i:i + 8]))
                i += 8
            else:
                break
        return out

    def _decode_url(self, ep_url, vod_from, referer, use_cache=True):
        """
        调用站点的 /api.php/web/decode/url 解出密文线路的真实地址。
        请求 protobuf 字段（取自前端 Vt()，实测有效）：
          1=剧集密文串  2=vodFrom  3=时间戳(ms)  4=nonce  5=签名
          6=appId      7=版本号
        响应 protobuf 字段（实测）：1=code(1成功) 2=msg(解密成功) 3=真实地址
        【实测重要特性】
          - 解出的 S3 直链 X-Amz-Expires=900，过期后 GET/HEAD 一律 403
          - HEAD 请求恒为 403（S3 签名只允许 GET），GET(任意 Range 形式) 均 206
          - 查询参数（含 response-content-disposition）全部被签名保护，不可改写
        因此：结果做 TTL 缓存，剩余有效期不足时重新解码（每次用全新签名）。
        """
        ck = (vod_from, ep_url)
        if use_cache and ck in self._decoded_cache:
            real, t0 = self._decoded_cache[ck]
            if time.time() - t0 < self._DECODE_TTL - self._DECODE_MARGIN:
                return real
            # 已过期或临近过期，重新解码（实测过期 URL 全部 403）
            self.log("decode cache expired, re-decode")

        last_err = ""
        for attempt in range(3):  # 每次全新签名重试，规避瞬时签名/网络失败
            real = self._decode_once(ep_url, vod_from, referer)
            if real:
                self._decoded_cache[ck] = (real, time.time())
                return real
            last_err = "attempt%d" % (attempt + 1)
        self.log("decode FAIL after 3 %s" % last_err)
        return ""

    def _decode_once(self, ep_url, vod_from, referer):
        """
        调用站点的 /api.php/web/decode/url 解出密文线路的真实地址。
        请求 protobuf 字段（取自前端 Vt()，实测有效）：
          1=剧集密文串  2=vodFrom  3=时间戳(ms)  4=nonce  5=签名
          6=appId      7=版本号
        响应 protobuf 字段（实测）：1=code(1成功) 2=msg(解密成功) 3=真实地址
        实测返回形如 https://...cmecloud.cn/xxx?...filename...01.mp4 的 video/mp4 直链。
        """
        ts, nonce, sg = self._sign_values()
        body = (self._pb_str(1, ep_url) + self._pb_str(2, vod_from) +
                self._pb_int(3, int(ts)) + self._pb_str(4, nonce) +
                self._pb_str(5, sg) + self._pb_str(6, APP_ID) +
                self._pb_int(7, APP_VERSION))

        h = dict(self.headers)
        h.update({
            "Referer": referer,
            "Content-Type": "application/x-protobuf",
            "Accept": "application/x-protobuf",
        })
        h.update(self._sign_headers())

        try:
            rsp = self._post(self.site_url + "/api.php/web/decode/url",
                             body, h)
        except Exception as e:
            self.log("decode FAIL: %s" % e)
            return ""

        raw = b""
        if rsp is not None:
            if hasattr(rsp, "content"):
                raw = rsp.content or b""
            elif isinstance(rsp, (bytes, bytearray)):
                raw = bytes(rsp)

        if not raw:
            self.log("decode empty response")
            return ""

        code = None
        url = ""
        for field, wire, val in self._pb_parse(raw):
            if field == 1 and wire == 0:
                code = val
            elif field == 3 and wire == 2:
                try:
                    url = val.decode("utf-8")
                except Exception:
                    url = ""
        if code != 1 or not url:
            self.log("decode rejected: code=%s" % code)
            return ""
        return url

    def _fallback_same_episode(self, vod_from, ep_url):
        """
        解码失败时，在同一下标找到可直连线路（m3u8 形态）的同集数地址。
        实测各线路集数一般一致（233460 各线路均 47 集）。
        """
        try:
            idx = None
            for f, eps in self._line_eps:
                if f == vod_from:
                    for i, e in enumerate(eps):
                        if e == ep_url:
                            idx = i
                            break
                    break
            if idx is None:
                return ""
            for f, eps in self._line_eps:
                if f == vod_from or idx >= len(eps):
                    continue
                cand = eps[idx]
                k = self._line_kind("", {}, [(None, cand)])
                if k == "m3u8":
                    self.log("decode fail, fallback %s ep#%d" % (f, idx + 1))
                    return cand
        except Exception as e:
            self.log("fallback err %s" % e)
        return ""

    def _post(self, url, body, headers):
        """POST 原始字节；兼容 base.spider 与 requests 两种环境"""
        try:
            import requests as _rq
            r = _rq.post(url, data=body, headers=headers,
                         timeout=20, verify=False)
            return r
        except Exception:
            import urllib.request as _ur
            req = _ur.Request(url, data=body, headers=headers, method="POST")
            return _ur.urlopen(req, timeout=20)

    def _fix_url(self, url):
        """补全协议，并对含非 ASCII（如中文『第01集』目录）的地址做路径编码。
        实测 https://p.bvvvvvvv7f.com/video/baituoliaobingxiang/第01集/index.m3u8
        直接请求会因非 ASCII 报错，编码为 %E7%AC%AC01%E9%9B%86 后返回 200。
        """
        u = (url or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            u = "https:" + u
        if not u.lower().startswith("http"):
            u = urllib.parse.urljoin(self.site_url + "/", u)
        # 只处理已编码则跳过，避免二次编码
        try:
            u.encode("ascii")
        except UnicodeEncodeError:
            parts = urllib.parse.urlsplit(u)
            path = urllib.parse.quote(parts.path, safe="/%:@&=+$,~*'()")
            query = urllib.parse.quote(parts.query, safe="=&%:@+$,~*'()/?")
            u = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))
        return u

    def playerContent(self, flag, id, vipFlags):
        """
        按地址真实形态分三种（实测样本）：
          m3u8 -> https://.../index.m3u8 直出，parse=0
          page -> 网页(如 RR 的 mh.yichengwlkj.com/drama/xxx)，parse=1 交 TVBox 嗅探
          code -> 站点密文(如 Ace_Net-xxx)：实时调 /api.php/web/decode/url 解出
                  video/mp4 直链（网页端即如此播放），失败才退回站点播放页嗅探
        """
        url = (id or "").strip()
        header = {"User-Agent": UA, "Referer": self.site_url + "/"}

        if not url:
            return {"parse": 1, "playUrl": "", "url": "", "header": header}

        if url.lower().startswith("//"):
            url = "https:" + url

        kind = self._line_kind("", {}, [(None, url)])

        # 线路显示名 -> (from 代号, 线路专属 Referer)
        vod_from, line_ref = self._label_to_from.get(
            str(flag or "").strip(), (str(flag or "").strip(), ""))
        ref = "%s/play/%s" % (self.site_url, self._last_vod_id) if self._last_vod_id \
            else self.site_url + "/"

        if kind == "m3u8":
            return {"parse": 0, "playUrl": "", "url": self._fix_url(url), "header": header}

        # page（如 RR 网页）与 code（如 ACE 密文）统一走站点解码接口：
        # 网页端即如此播放，实测两种形态都能解出直链（mp4/m3u8）
        real = self._decode_url(url, vod_from, ref)
        if real:
            out_header = {"User-Agent": UA,
                          "Referer": line_ref or (self.site_url + "/")}
            return {"parse": 0, "playUrl": "", "url": self._fix_url(real),
                    "header": out_header}

        # 解码失败（盒子上常见：系统时间偏差导致签名被拒、瞬时网络失败）：
        # 按同一下标回退到其它可直连线路的同集数，保证仍能播放
        alt = self._fallback_same_episode(vod_from, url)
        if alt:
            return {"parse": 0, "playUrl": "", "url": self._fix_url(alt),
                    "header": header}

        if kind == "page":
            # 解码失败：网页线路交 TVBox 嗅探（RR 页面会 307 跳 /pc/...）
            return {"parse": 1, "playUrl": "", "url": self._fix_url(url), "header": header}

        # 密文解码失败：回退到本站播放页嗅探
        if self._last_vod_id:
            return {"parse": 1, "playUrl": "", "url": ref, "header": header}

        return {"parse": 1, "playUrl": "", "url": url, "header": header}

    def localProxy(self, param):
        """封面等图片代理"""
        try:
            url = ""
            if isinstance(param, dict):
                url = param.get("url", "")
            else:
                for pair in str(param).split("&"):
                    if "=" in pair:
                        k, val = pair.split("=", 1)
                        if k == "url":
                            url = val
            if not url:
                return [200, "image/jpeg", b"", ""]

            if "%" in url:
                url = urllib.parse.unquote(url)
            url = self._fix_pic(url)

            rsp = self.fetch(url, headers={
                "User-Agent": UA,
                "Referer": self.site_url + "/",
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            }, timeout=20)
            content = rsp.content
            ctype = rsp.headers.get("Content-Type", "image/jpeg")
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return [200, ctype, content, ""]
        except Exception:
            return [200, "image/jpeg", b"", ""]

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
