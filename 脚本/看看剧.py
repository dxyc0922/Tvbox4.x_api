# coding=utf-8
"""
看看剧 www.kkju.app | TVBox Python 爬虫
网站结构:
  站点为 Vue 单页应用 + Go 后端, 数据全部走 JSON 接口 /api/app/...
  接口需请求签名(还原自前端 request-CopgPU0g.js):
    X-Device-ID : web-<uuid>
    X-Platform  : web
    X-App-Version: web
    X-Timestamp / X-Nonce
    X-Signature : HMAC_SHA256( deriveKey(deviceId), 签名载荷 ) 的 hex
      deriveKey   = HMAC_SHA256( 固定密钥, deviceId ) 的 hex
      签名载荷    = METHOD\\nPATH\\n排序query\\nTIMESTAMP\\nNONCE\\nweb[\\nBODY_SHA256]
    POST 额外带 X-Body-Hash = SHA256(请求体)
  接口:
    GET  /settings                站点信息
    GET  /categories              分类
    GET  /categories/{id}         含 filters(area/class/lang/year 合法值)
    GET  /categories/{id}/videos  分类列表(分页 page/page_size/year...)
    GET  /videos/recommend        首页推荐
    GET  /videos/recent           最近更新
    GET  /videos/search?keyword=  搜索(分页)
    GET  /videos/{id}             详情(含 playGroups 全部线路与剧集)
    POST /play/token              换取真实播放地址 {videoId,episode,groupCode}
  备注: 实测该站中文 area/class/lang 筛选后端返回恒为 0(仅 year 数字筛选生效),
        但为保持筛选项完整、界面观感统一, 仍从 /categories/{id}.filters 暴露
        area/class/lang 合法值并把选中条件透传给列表接口。
"""
import re
import sys
import json
import time
import uuid
import hmac
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
            return self._session

        def fetch(self, url, headers=None, **kw):
            return self._sess.get(url, headers=headers,
                                  timeout=kw.pop('timeout', 15), **kw)

        def log(self, *a, **kw):
            try:
                print("[kkju]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.kkju.app"
API_BASE = "/api/app"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/favicon.svg"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 签名固定密钥(来自前端 JS)
_SIGN_KEY = b"cms_device_salt_v1_2024cms_app_sign_key_v1_2024_secure"
_APP_VERSION = "web"
_PAGE_SIZE = 30


def _years_filter():
    return [{"n": "全部", "v": ""}] + \
           [{"n": str(y), "v": str(y)} for y in range(2027, 1999, -1)]


class Spider(Spider):

    def getName(self):
        return "看看剧"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}
        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        # 每个实例固定一个设备号, 避免每次请求重新派生密钥
        self.device_id = "web-" + str(uuid.uuid4())
        self._derive_key = hmac.new(
            _SIGN_KEY, self.device_id.encode(), hashlib.sha256).hexdigest()
        self._cat_cache = None
        self._filters_cache = {}
        self._play_cache = {}
        self.log("init: site=%s device=%s" % (self.site_url, self.device_id))

    # ---------------- 签名 + 请求 ----------------
    @staticmethod
    def _sorted_query(params):
        """前端 Sr(): 仅对 null 值剔除, 按 key 排序后 a=b&c=d (值不编码)。"""
        if not params:
            return ""
        items = [(k, v) for k, v in params.items() if v is not None]
        items.sort(key=lambda x: x[0])
        return "&".join("%s=%s" % (k, v) for k, v in items)

    def _sign_headers(self, method, path, query, body_text):
        ts = str(int(time.time()))
        nonce = str(uuid.uuid4())
        body_hash = ""
        if method != "GET" and body_text is not None:
            body_hash = hashlib.sha256(body_text.encode()).hexdigest()
        rows = [method, path, query, ts, nonce, _APP_VERSION]
        if body_hash:
            rows.append(body_hash)
        payload = "\n".join(rows)
        sig = hmac.new(self._derive_key.encode(), payload.encode(),
                       hashlib.sha256).hexdigest()
        h = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": self.site_url,
            "Referer": self.site_url + "/",
            "X-Device-ID": self.device_id,
            "X-Platform": _APP_VERSION,
            "X-App-Version": _APP_VERSION,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
            "X-Signature": sig,
        }
        if body_hash:
            h["X-Body-Hash"] = body_hash
        return h

    def _api(self, method, path, params=None, body=None):
        method = method.upper()
        query = self._sorted_query(params)
        body_text = None
        if method != "GET":
            # 与 axios 默认 JSON.stringify 保持一致(带空格), 否则 bodyHash 校验不过
            body_text = json.dumps(body, ensure_ascii=False) \
                if body is not None else ""
        headers = self._sign_headers(method, API_BASE + path, query, body_text)
        if method != "GET":
            headers["Content-Type"] = "application/json"
        url = self.site_url + API_BASE + path
        if query:
            # 真正发请求时由 requests 对中文做 percent-encode
            url += "?" + urllib.parse.urlencode(sorted(params.items()))
        try:
            import requests
            rsp = requests.request(method, url, headers=headers,
                                   data=body_text, timeout=20, verify=False)
            try:
                data = rsp.json()
            except Exception:
                self.log("非JSON响应 %s %s" % (rsp.status_code, path))
                return None
            if isinstance(data, dict) and data.get("code") == 200:
                return data.get("data")
            self.log("API错误 %s code=%s msg=%s"
                     % (path, data.get("code") if isinstance(data, dict) else "?",
                        data.get("message") if isinstance(data, dict) else ""))
            return None
        except Exception as e:
            self.log("请求失败 %s -> %s" % (path, e))
            return None

    # ---------------- 工具 ----------------
    @staticmethod
    def _clean(s):
        if s is None:
            return ""
        s = str(s)
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'")
              .replace("&lt;", "<").replace("&gt;", ">"))
        return re.sub(r"\s+", " ", s).strip()

    def _pic(self, p):
        p = self._clean(p)
        return p if p.startswith("http") else DEFAULT_PIC

    def _load_categories(self):
        if self._cat_cache is not None:
            return self._cat_cache
        data = self._api("GET", "/categories") or []
        cats = []
        for c in data:
            if not c.get("status"):
                continue
            cats.append({"type_id": str(c.get("id")),
                         "type_name": self._clean(c.get("name"))})
        self._cat_cache = cats
        return cats

    def _load_category_filters(self, tid):
        """从 /categories/{id} 取 filters(area/class/lang/year 合法值) 并转为 TVBox 格式。"""
        if self._filters_cache is None:
            self._filters_cache = {}
        if tid in self._filters_cache:
            return self._filters_cache[tid]

        d = self._api("GET", "/categories/%s" % tid) or {}
        filters = d.get("filters") or {}
        out = []
        # 年份仍用本地生成(接口 year 可能为空), 保证选项齐全
        out.append({"key": "year", "name": "年份", "value": _years_filter()})
        for key, label in (("area", "地区"), ("class", "剧情"),
                           ("lang", "语言")):
            vals = filters.get(key) or []
            if not vals:
                continue
            opts = [{"n": "全部", "v": ""}]
            for v in vals:
                if isinstance(v, dict):
                    n = v.get("name") or v.get("n") or v.get("value")
                    val = v.get("value", v.get("v"))
                else:
                    n = val = v
                if val is None or str(val) == "":
                    continue
                opts.append({"n": self._clean(n) or str(val), "v": str(val)})
            if len(opts) > 1:
                out.append({"key": key, "name": label, "value": opts})
        self._filters_cache[tid] = out
        return out

    def _video_card(self, v):
        # 备注优先用接口 remarks(如 更新至HD / 已完结)
        remarks = self._clean(v.get("remarks"))
        return {
            "vod_id": str(v.get("id")),
            "vod_name": self._clean(v.get("name")) or str(v.get("id")),
            "vod_pic": self._pic(v.get("pic")),
            "vod_remarks": remarks,
        }

    # ================= TVBox 接口 =================
    def homeContent(self, filter=False):
        cats = self._load_categories()
        filters = {c["type_id"]: self._load_category_filters(c["type_id"])
                   for c in cats}
        return {"class": cats, "filters": filters}

    def homeVideoContent(self):
        # 推荐数量有限, 叠加各主分类最新片凑一个更丰富的首页
        videos, seen = [], set()

        def push(items):
            for v in items or []:
                vid = v.get("id")
                if vid in seen:
                    continue
                seen.add(vid)
                videos.append(self._video_card(v))

        push(self._api("GET", "/videos/recommend", {"limit": 12}))
        # 分类 id 由站点后台配置(曾调整过), 动态取主分类, 不写死; VIP 专享置后
        cats = self._api("GET", "/categories") or []
        cids = [str(c.get("id")) for c in cats
                if c.get("status", 1) and "VIP" not in str(c.get("name", ""))]
        cids += [str(c.get("id")) for c in cats
                 if c.get("status", 1) and "VIP" in str(c.get("name", ""))]
        for cid in cids[:7]:
            d = self._api("GET", "/categories/%s/videos" % cid,
                          {"page": 1, "page_size": 12})
            if d:
                push(d.get("list"))
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        extend = extend or {}

        params = {"page": page, "page_size": _PAGE_SIZE}
        # 年份 + 中文筛选(area/class/lang) 都带上, 与前端请求保持一致
        for k in ("year", "area", "class", "lang"):
            v = extend.get(k)
            if v:
                params[k] = v

        data = self._api("GET", "/categories/%s/videos" % tid, params) or {}
        lst = data.get("list") or []
        total = int(data.get("total") or 0)
        page_size = int(data.get("pageSize") or _PAGE_SIZE)
        pagecount = (total + page_size - 1) // page_size if page_size else 1
        return {
            "list": [self._video_card(v) for v in lst],
            "page": page,
            "pagecount": max(pagecount, 1),
            "limit": page_size,
            "total": total,
        }

    def searchContent(self, key, quick, pg="1"):
        return self._search(key, pg)

    def searchContentPage(self, key, quick, pg="1"):
        return self._search(key, pg)

    def _search(self, key, pg="1"):
        page = int(pg) if pg else 1
        data = self._api("GET", "/videos/search",
                         {"keyword": key, "page": page,
                          "page_size": _PAGE_SIZE}) or {}
        lst = data.get("list") or []
        total = int(data.get("total") or 0)
        # 搜索接口服务端固定每页返回数量, 以实际返回条数为准
        page_size = int(data.get("pageSize") or len(lst) or _PAGE_SIZE)
        pagecount = (total + page_size - 1) // page_size if page_size else 1
        return {
            "list": [self._video_card(v) for v in lst],
            "page": page,
            "pagecount": max(pagecount, 1),
            "limit": _PAGE_SIZE,
            "total": total,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0])
        vid = vid.rsplit("/", 1)[-1].replace(".html", "")
        vid = re.sub(r"\D", "", vid) or vid
        d = self._api("GET", "/videos/%s" % vid)
        if not d:
            return {"list": []}

        name = self._clean(d.get("name")) or vid
        pic = self._pic(d.get("pic"))
        actor = self._clean(d.get("actor"))
        director = self._clean(d.get("director"))
        year = self._clean(d.get("year"))
        area = self._clean(d.get("area"))
        type_name = self._clean(d.get("classExtend"))
        remarks = self._clean(d.get("remarks"))
        lang = self._clean(d.get("lang"))
        score = self._clean(d.get("doubanScore"))

        # 简介
        content = self._clean(d.get("content"))
        if content:
            vod_content = INTRO_PREFIX + "\n" + content
        else:
            vod_content = INTRO_PREFIX

        # 播放线路: playGroups[*].playUrls
        # vod_play_url 每集名字段编码为  groupCode|集名|videoId|episode
        play_from, play_url = [], []
        groups = d.get("playGroups") or []
        # 按 sort 升序(与前端一致)
        groups = sorted(groups, key=lambda g: g.get("sort", 0))
        line_count = 0
        for g in groups:
            code = str(g.get("code") or "")
            gname = self._clean(g.get("name")) or code or "线路"
            eps = g.get("playUrls") or []
            if not eps:
                continue
            eps = sorted(eps, key=lambda e: e.get("sort", 0))
            parts = []
            for idx, ep in enumerate(eps):
                # episode 为 0 基集序号(实测 token 接口: 0=第1集)
                ep_name = self._clean(ep.get("name")) or "第%d集" % (idx + 1)
                flag = "%s|%s|%d" % (code, vid, idx)
                parts.append("%s$%s" % (ep_name, flag))
            play_from.append(gname)
            play_url.append("#".join(parts))
            line_count += 1

        if not remarks:
            total = d.get("total")
            if total:
                remarks = "共%s集" % total
            elif line_count:
                remarks = "%d条线路" % line_count

        # 附加信息拼进 remarks 便于展示
        extra = [x for x in (area, year, lang) if x]
        if extra and remarks:
            vod_remarks = "%s · %s" % (remarks, "/".join(extra))
        elif extra:
            vod_remarks = "/".join(extra)
        else:
            vod_remarks = remarks
        if score:
            vod_remarks = ("豆瓣%s " % score) + vod_remarks

        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": vod_content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area,
            "vod_type": type_name,
            "vod_remarks": vod_remarks,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    def playerContent(self, flag, id, vipFlags):
        # id 形如: groupCode|videoId|episode|idx
        key = str(id)
        now = int(time.time())
        if key in self._play_cache:
            ts, res = self._play_cache[key]
            if now - ts < 240:
                return res

        res = {"parse": 1, "playUrl": "", "url": "", "header": {"User-Agent": UA}}
        parts = key.split("|")
        if len(parts) >= 3:
            code, vid, episode = parts[0], parts[1], parts[2]
            # episode 为 0 基集序号
            ep_val = int(episode)
            data = self._api("POST", "/play/token",
                             body={"videoId": int(vid), "episode": ep_val,
                                   "groupCode": code})
            if data:
                url = data.get("playUrl") or ""
                parse_api = data.get("parseApi") or ""
                headers = data.get("headers") or {}
                hdr = {"User-Agent": UA}
                if isinstance(headers, dict):
                    hdr.update({str(k): str(v) for k, v in headers.items()})
                if url:
                    # 后端 token 接口已给出最终可播地址(needParse=false 直链为主)
                    res = {
                        "parse": 0,
                        "playUrl": "",
                        "url": url,
                        "header": hdr,
                    }
                    # 个别线路附带解析接口时, 交给 TVBox 嗅探
                    if parse_api and not re.search(r"\.m3u8(\?|$)", url):
                        res["parse"] = 1
                        res["playUrl"] = parse_api
        self._play_cache[key] = (now, res)
        return res


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
