# -*- coding: utf-8 -*-
# TVBox 播放源：FoFo影院（fofo11.com）
# 站点特征（自研模板，Cloudflare CDN 直连可访问）：
#   - 分类：/{cat}，列表分页 /{cat}/0-0-0-0?page={n}（每页 24 条，page=1 与无参数等价）
#   - 搜索：/search?q={key}（单页结果，无分页）
#   - 详情：/{cat}/{id}；线路+选集内嵌于 JS 变量 urlList = decryptDict({...})，
#          混淆规则：key 与字符串值逐字符 charCode-1 后 JSON.parse（含 "#... #" 引号包裹形式）
#   - 播放：POST /source/ （form: id={sid}）直接返回 m3u8 直链明文，无防盗链
# 接口：homeContent / homeVideoContent / categoryContent / detailContent / searchContent / playerContent
# 依赖：优先 requests；环境无 requests 时自动降级 urllib 标准库，无第三方依赖
# 兼容：有 base.spider 基类的 TVBox（qiusunshine 系）自动继承；无基类环境独立运行
# 备注：源参数可用 host=xxx（或 {"host":"xxx"}）覆盖目标站域名

import re
import json
import sys

try:
    sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

try:
    import requests
except Exception:
    requests = None

from urllib.parse import quote, urlencode

HOST = "fofo11.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT = 12

# 固定分类树（导航实测：电影/电视剧/综艺/动漫）
CLASSES = [
    ("dianying", "电影"),
    ("dianshiju", "电视剧"),
    ("zongyi", "综艺"),
    ("dongman", "动漫"),
]


class Spider(_BaseSpider):

    def __init__(self):
        self.host = HOST
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://%s/" % HOST,
        }
        self.session = requests.Session() if requests is not None else None
        if self.session is not None:
            self.session.headers.update(self.headers)

    # ---------- 可选能力 ----------

    def getName(self):
        return "FoFo影院"

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return bool(url) and not url.startswith("http")

    def manualVideoCheck(self):
        pass

    # ---------- 内部工具 ----------

    def _url(self, path):
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return "https://%s%s" % (self.host, path)

    def _abs(self, s):
        s = (s or "").strip()
        if not s:
            return ""
        if s.startswith("//"):
            return "https:" + s
        if s.startswith("/"):
            return "https://%s%s" % (self.host, s)
        if s.startswith("http"):
            return s
        return "https://%s/%s" % (self.host, s)

    def _http_get(self, url, timeout=TIMEOUT):
        if self.session is not None:
            r = self.session.get(url, timeout=timeout)
            if not r.ok:
                raise RuntimeError("HTTP %s for %s" % (r.status_code, url))
            try:
                r.encoding = "utf-8"
            except Exception:
                pass
            return r.text
        import ssl
        import urllib.request
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as resp:
            data = resp.read()
            enc = resp.headers.get_content_charset() or "utf-8"
            try:
                return data.decode(enc)
            except Exception:
                return data.decode("utf-8", "ignore")

    def _http_post(self, url, data, timeout=TIMEOUT):
        """form 编码 POST，返回响应文本（仅用于 /source/ 播放接口）。"""
        if self.session is not None:
            r = self.session.post(url, data=data, timeout=timeout)
            if not r.ok:
                raise RuntimeError("HTTP %s for %s" % (r.status_code, url))
            try:
                r.encoding = "utf-8"
            except Exception:
                pass
            return r.text
        import ssl
        import urllib.request
        body = urlencode(data).encode("utf-8")
        hdrs = dict(self.headers)
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        hdrs["X-Requested-With"] = "XMLHttpRequest"
        req = urllib.request.Request(url, data=body, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as resp:
            data = resp.read()
            enc = resp.headers.get_content_charset() or "utf-8"
            try:
                return data.decode(enc)
            except Exception:
                return data.decode("utf-8", "ignore")

    def _get(self, path, timeout=TIMEOUT):
        return self._http_get(self._url(path), timeout)

    @staticmethod
    def _clean(s):
        return re.sub(r"\s+", " ", s or "").strip()

    # ---------- urlList 解密（复刻 decryptDict） ----------

    @staticmethod
    def _dec_str(s):
        """逐字符 charCode-1 后尝试 JSON.parse，失败返回平移后的字符串。"""
        c = "".join(chr(ord(ch) - 1) for ch in str(s))
        try:
            return json.loads(c)
        except Exception:
            return c

    @classmethod
    def _dec(cls, v):
        if isinstance(v, list):
            return [cls._dec(x) for x in v]
        if isinstance(v, dict):
            return {cls._dec_str(str(k)): cls._dec(x) for k, x in v.items()}
        return cls._dec_str(v)

    def _extract_url_list(self, html):
        """从详情页提取并解密 urlList，返回 {"source": [...], "url_list": [[{sid,title,...}...]...]} 或 None。"""
        m = re.search(r'var\s+urlList\s*=\s*decryptDict\((\{)', html)
        if not m:
            return None
        brace = m.start(1)
        depth = 0
        in_str = False
        esc = False
        for k in range(brace, len(html)):
            c = html[k]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == "'":
                    in_str = False
            else:
                if c == "'":
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        obj_src = html[brace:k + 1]
                        try:
                            raw = json.loads(obj_src.replace("'", '"'))
                        except Exception:
                            return None
                        return self._dec(raw)
        return None

    # ---------- 列表解析 ----------

    @staticmethod
    def _vid_of(href):
        """从详情 href 提取 (cat, id)；形如 /dianying/153021。"""
        m = re.search(r'/([a-z]+)/(\d+)', href or "")
        if m:
            return m.group(1), m.group(2)
        return None, None

    def _parse_list(self, html):
        """解析 li 卡片段：thumbnail 大图 + note 备注（+countrie 年份/地区可选）+ h2 标题。"""
        out = []
        seen = set()
        for seg in re.findall(r'<li[^>]*>(.*?)</li>', html, re.S):
            # 属性顺序不定，按 <a ... thumbnail ...> 整段再分别提取属性
            a = re.search(r'<a\b([^>]*class="thumbnail"[^>]*)>', seg)
            if not a:
                continue
            mh = re.search(r'href="([^"]+)"', a.group(1))
            if not mh:
                continue
            cat, vid = self._vid_of(mh.group(1))
            if not cat or not vid or vid in seen:
                continue
            seen.add(vid)
            h2 = re.search(r'<h2><a[^>]*>([^<]+)</a></h2>', seg, re.S)
            name = self._clean(h2.group(1)) if h2 else ""
            img = re.search(r'<img\b([^>]*)>', seg)
            pic = ""
            if img:
                ms = re.search(r'src="([^"]+)"', img.group(1))
                ma = re.search(r'alt="([^"]*)"', img.group(1))
                if ms:
                    pic = self._abs(ms.group(1))
                if not name and ma:
                    name = self._clean(ma.group(1))
            note = ""
            mn = re.search(r'<div class="note"><span>([^<]*)</span>', seg)
            if mn:
                note = self._clean(mn.group(1))
            if not note:
                mc = re.search(r'<div class="countrie">\s*<span[^>]*>([^<]*)</span>', seg)
                if mc:
                    note = self._clean(mc.group(1))
            out.append({
                "vod_id": "%s/%s" % (cat, vid),
                "vod_name": name or vid,
                "vod_pic": pic,
                "vod_remarks": note,
            })
        return out

    @staticmethod
    def _last_page(html):
        """从分页链接 page=N 取最大值（尾页）；无分页返回 1。"""
        pages = [int(x) for x in re.findall(r'page=(\d+)', html)]
        return max(pages) if pages else 1

    # ---------- 标准接口 ----------

    def init(self, extend=""):
        """extend 支持 host=xxx 或 JSON {"host":"xxx"} 覆盖默认域名。"""
        if not extend:
            return
        host = None
        s = extend.strip()
        if s.startswith("{"):
            try:
                host = (json.loads(s) or {}).get("host")
            except Exception:
                host = None
        if not host:
            m = re.search(r"(?:host|url)\s*[=:]\s*([^\s\"']+)", extend)
            if m:
                host = m.group(1).strip()
        if host:
            host = str(host).replace("https://", "").replace("http://", "").rstrip("/")
            if host:
                self.host = host
                self.headers["Referer"] = "https://%s/" % host
                if self.session is not None:
                    self.session.headers.update(self.headers)

    def homeContent(self, filter=False):
        return {
            "class": [{"type_id": tid, "type_name": name} for tid, name in CLASSES],
            "list": [],
            "filters": {},
        }

    def homeVideoContent(self):
        try:
            html = self._get("/")
        except Exception:
            return {"list": []}
        return {"list": self._parse_list(html)[:80]}

    def categoryContent(self, tid, pg, filter=False, extend=""):
        if not isinstance(pg, int):
            try:
                pg = int(pg or 1)
            except Exception:
                pg = 1
        if pg < 1:
            pg = 1
        path = "/%s/0-0-0-0?page=%s" % (tid, pg)
        try:
            html = self._get(path)
        except Exception:
            return {"page": pg, "pagecount": 1, "limit": 24, "total": 0, "list": []}
        lst = self._parse_list(html)
        total_page = self._last_page(html)
        total = len(lst) if total_page == 1 else total_page * 24
        return {"page": pg, "pagecount": total_page, "limit": 24, "total": total, "list": lst}

    def detailContent(self, ids):
        # ids 可能是 "cat/id"、纯数字、详情 URL 或列表
        if isinstance(ids, list):
            ids = ids[0] if ids else ""
        s = str(ids).strip()
        m = re.search(r'([a-z]+)/(\d+)', s)
        if m:
            cat, vid = m.group(1), m.group(2)
        else:
            m2 = re.search(r'(\d+)', s)
            if not m2:
                return {"list": []}
            vid = m2.group(1)
            cat = None
        html = ""
        # 纯数字 id 不带分类时，按分类顺序探测详情页
        if cat is None:
            for c, _ in CLASSES:
                try:
                    html = self._get("/%s/%s" % (c, vid))
                    cat = c
                    break
                except Exception:
                    continue
            if cat is None:
                return {"list": []}
        else:
            try:
                html = self._get("/%s/%s" % (cat, vid))
            except Exception:
                return {"list": []}

        # 标题 / 封面 / 简介
        name = ""
        mo = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        if mo:
            name = self._clean(mo.group(1))
        pic = ""
        mp = re.search(r'<meta property="og:image" content="([^"]*)"', html)
        if mp:
            pic = self._abs(mp.group(1))
        content = ""
        md = re.search(r'<meta property="og:description" content="([^"]*)"', html)
        if md:
            content = self._clean(md.group(1))
        if not content:
            md2 = re.search(r'<meta name="description" content="([^"]*)"', html)
            if md2:
                content = self._clean(md2.group(1))

        # 线路 + 选集（解密 urlList）
        u = self._extract_url_list(html)
        if not u:
            return {"list": []}
        source = u.get("source") or []
        url_list = u.get("url_list") or []
        play_from = []
        play_url = []
        for i, src in enumerate(source):
            eps = url_list[i] if i < len(url_list) else []
            if not eps:
                continue
            items = []
            for e in eps:
                sid = e.get("sid")
                if sid is None:
                    continue
                title = self._clean(e.get("title") or str(e.get("episode", "")))
                items.append("%s$%s" % (
                    title, self._url("/%s/%s?sid=%s" % (cat, vid, sid))))
            if items:
                play_from.append(self._clean(str(src)))
                play_url.append("#".join(items))
        if not play_url:
            return {"list": []}

        vod = {
            "vod_id": "%s/%s" % (cat, vid),
            "vod_name": name or vid,
            "vod_pic": pic,
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg=1):
        try:
            html = self._get("/search?q=%s" % quote(str(key)))
        except Exception:
            return {"list": []}
        return {"list": self._parse_list(html)}

    def playerContent(self, flag, ids, vipFlags=""):
        # ids 形如 https://fofo11.com/dianying/153021?sid=38152780
        m = re.search(r'[?&]sid=(\d+)', str(ids))
        if not m:
            return {}
        sid = m.group(1)
        try:
            text = self._http_post(self._url("/source/"), {"id": sid})
        except Exception:
            return {}
        play = (text or "").strip()
        if not play.startswith("http"):
            return {}
        return {"parse": 0, "playUrl": play,
                "header": "Referer: %s" % self._url("/")}

    def destroy(self):
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = ["光速(167)", "天堂(167)", "量子(167)", "非凡(167)"]
_TVBOX_LINE_ORDER = ["光速(167)", "无尽(167)", "量子(167)", "非凡(167)"]

_TVBOX_ZY_ENABLED = True
_TVBOX_ZY_CDN = ["ffzy", "feifei", "yzzy", "cdnlz", "lzzy", "bfzy", "rrcdnbf", "fengbao", "ffvip", "7bbffvip", "modujx", "modudm", "mujizybf", "jisuzy", "jisuzyv", "zuidazy", "wsyzym3u8", "xluuss", "bfvvs", "dytt", "phimgood", "ryiplay", "ryplay", "ruyijx", "gsuus", "guangsuzy", "maowushi", "ukuzi", "niuniuzy", "rstu6", "mzm3u8", "ppqrrs", "qqqrst", "hhuus"]
_TVBOX_ZY_API = "/api\\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod"
_TVBOX_ZY_CODES = ["BD", "BF", "FF", "HH", "HN", "JS", "JY", "KC", "LZ", "MT", "MY", "NN", "SD", "SN", "UK", "WJ", "XL", "YZ"]
_TVBOX_ZY_KW = ["量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库", "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛", "猫屋", "电影天堂", "天堂", "4K资源", "索尼"]
_TVBOX_ZY_NEG = ["官方", "自营", "自有", "正版"]

def _tvbox_is_zy_url(url, flag=''):
    import re, urllib.parse
    u = str(url or '')
    f = str(flag or '').strip()
    if re.search(_TVBOX_ZY_API, u, re.I):
        return True
    # 播放地址可能是多集拼接串：'第01集$https://a.com/x.m3u8#第02集$https://b.com/y.m3u8'
    # 必须逐段提取 URL 再取 host，不能对整个串 urlparse（取不到 host）。
    hosts = set()
    for seg in re.split(r'[#$]', u):
        seg = seg.strip()
        if seg.startswith('http://') or seg.startswith('https://'):
            try:
                parsed = urllib.parse.urlparse(seg)
                h = (parsed.hostname or '').lower()
            except Exception:
                h = ''; parsed = None
            # 本地代理型脚本（如 APP影院1）：真实地址藏在 url= 参数里，
            # 需解码后再提取 host，否则只会拿到 127.0.0.1 而漏判。
            if parsed and h in ('127.0.0.1', 'localhost', '::1'):
                qs = urllib.parse.parse_qs(parsed.query)
                real = (qs.get('url') or [''])[0]
                if real.startswith('//'): real = 'https:' + real
                if real.startswith('http://') or real.startswith('https://'):
                    try:
                        rh = (urllib.parse.urlparse(real).hostname or '').lower()
                    except Exception:
                        rh = ''
                    if rh: hosts.add(rh)
            if h:
                hosts.add(h)
            # 中转缓存型：真实 URL 拼在路径里（/cache/https://cdn/...），
            # 取内层 host（如 47电影天堂 dl.gybkw.com/cache/https://c1.7bbffvip.com）。
            im = re.search(r'/(https?://[^/?#]+)', seg)
            if im:
                ih = re.match(r'https?://([^/?]+)', im.group(1))
                if ih:
                    hosts.add(ih.group(1).split(':')[0].lower())
    for h in hosts:
        for p in _TVBOX_ZY_CDN:
            if re.search(r'(^|[.\-_])' + re.escape(p), h, re.I):
                return True
        if re.search(r'(^|[.\-_])lzv\d+', h, re.I):
            return True
    if hosts:
        return False  # 有真实 host 但没命中 CDN → 自有线路，不靠名字
    # 无 host（占位符型脚本，detail 给相对路径/id）：回退到线路名判定。
    # 官方/自营字样优先豁免，避免误伤。
    if any(neg in f for neg in _TVBOX_ZY_NEG):
        return False
    if f.upper() in _TVBOX_ZY_CODES:
        return True
    if any(kw in f for kw in _TVBOX_ZY_KW):
        return True
    if re.search(r'(?i)\b(LZ|FF|BF|HF|HN|YZ|DY|MY)(?:线路|线)', f):
        return True
    return False

def _tvbox_filter_lines(result, drop):
    if not isinstance(result, dict):
        return result
    items = result.get('list')
    if isinstance(items, list):
        for item in items:
            _tvbox_filter_item(item, drop)
    else:
        _tvbox_filter_item(result, drop)
    return result

def _tvbox_filter_item(item, drop):
    froms = item.get('vod_play_from') or ''
    urls = item.get('vod_play_url') or ''
    if not isinstance(froms, str) or not isinstance(urls, str):
        return
    if '$$$' not in froms:
        return
    parts_from = [f.strip() for f in froms.split('$$$')]
    parts_url = urls.split('$$$')
    if len(parts_from) != len(parts_url):
        return
    if _TVBOX_ZY_ENABLED:
        keep = [(f, u) for f, u in zip(parts_from, parts_url)
                if f not in drop and not _tvbox_is_zy_url(u, f)]
    else:
        keep = [(f, u) for f, u in zip(parts_from, parts_url) if f not in drop]
    if not keep or len(keep) == len(parts_from):
        return
    item['vod_play_from'] = '$$$'.join(f for f, _ in keep)
    item['vod_play_url'] = '$$$'.join(u for _, u in keep)

def _tvbox_sort_lines(result, order):
    if not order or not isinstance(result, dict):
        return result
    items = result.get('list')
    if isinstance(items, list):
        for item in items:
            _tvbox_sort_item(item, order)
    else:
        _tvbox_sort_item(result, order)
    return result

def _tvbox_sort_item(item, order):
    froms = item.get('vod_play_from') or ''
    urls = item.get('vod_play_url') or ''
    if not isinstance(froms, str) or not isinstance(urls, str):
        return
    if '$$$' not in froms:
        return
    parts_from = [f.strip() for f in froms.split('$$$')]
    parts_url = urls.split('$$$')
    if len(parts_from) != len(parts_url):
        return
    known = {f: i for i, f in enumerate(order)}
    pairs = list(zip(parts_from, parts_url))
    # 已知线路按 order（画质速度最优在前），未知线路稳定保持原序后置。
    pairs.sort(key=lambda p: known.get(p[0], len(order)))
    item['vod_play_from'] = '$$$'.join(f for f, _ in pairs)
    item['vod_play_url'] = '$$$'.join(u for _, u in pairs)

def _tvbox_apply(cls):
    fn = getattr(cls, 'detailContent', None)
    if fn is None:
        return
    def wrapper(self, *a, _fn=fn, **k):
        res = _tvbox_filter_lines(_fn(self, *a, **k), _TVBOX_DROP_LINES)
        return _tvbox_sort_lines(res, _TVBOX_LINE_ORDER)
    setattr(cls, 'detailContent', wrapper)

_tvbox_apply(Spider)
