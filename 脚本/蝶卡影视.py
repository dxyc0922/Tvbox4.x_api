# coding=utf-8
"""
蝶卡影视网 www.diekawang.com | TVBox Python 爬虫
================================================================

【网站结构】
  1. 首页/分类聚合页为 SSR 渲染：curl 直接可取到卡片
     - 卡片容器: <div class="moon-list-item">
     - 卡片链接: <a href="/vod/player/0/{影片ID}" class="item goLinklist">
     - 封面图  : <img data-original="..." src="..." class="cmslazyload">
     - 标题    : <p class="name item-title ohv-ellipsis">影片名</p>
     - 评分    : <label class="rate ml-20">5.2</label>
     - 在看人数: <span>39135人次在看</span>

  2. 分类/筛选：
     - 真实分类列表 URL : /vod/list/{页码}/{顶层tid}/{子分类id}
       第1位=页码(从1开始)，第2位=顶层分类ID，第3位=子分类ID(0=全部)
       例: /vod/list/1/1/0    → 电影第1页
           /vod/list/3/1/0    → 电影第3页
           /vod/list/1/1/9    → 电影-动作片第1页(9=动作片)
           /vod/list/2/2/22   → 电视剧-国产剧第2页(22=国产剧)
           /vod/list/1/457/541 → 短剧-玄幻第1页(541=玄幻)
     - SSR 渲染，每页固定 10 个卡片，curl 直接可取
     - 子分类 typeId 来自筛选栏 <a class="btn">，完整映射见 _FILTERS_MAP
     - 分类聚合入口(菜单): /vod/1/{顶层tid}/0

  3. 播放页解密：
     - 页面内 JS 变量: var temLineList = [ {...}, {...} ]
     - 每集字段: {"file":"j8UaHR0cHM6...", "name":"第01集", "tag":"1080zyk", "id":990024}
     - 解密算法:
         raw   = file[3:]                    # 去掉首部3个随机字符
         url   = base64_decode(raw)          # Base64 解码
         url   = urldecode(url)              # URL 解码 → 真实 m3u8
       实测: j8UaHR0cHM6JTJGJTJGY2RuLnZ2dmlwLXBsYXlzMzMuY2MlMkY...
             → https://cdn.vvvip-plays33.cc/20251215/2142_2a34abd6/index.m3u8

小橙子提醒: 如网站改版，需按上述真实字段重新对照源码调整正则。
"""

import re
import sys
import json
import base64
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

    class _BaseSpider(object):
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
                print("[diekawang]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


# ===================== 站点常量 =====================
HOST = "https://www.diekawang.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/data/uploadFile/cskhyj.webp"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 顶层分类（对应 /vod/1/{typeId}/0）
CLASSES = [
    {"type_id": "1",   "type_name": "电影"},
    {"type_id": "2",   "type_name": "电视剧"},
    {"type_id": "3",   "type_name": "综艺"},
    {"type_id": "4",   "type_name": "动漫"},
    {"type_id": "457", "type_name": "短剧"},
    {"type_id": "462", "type_name": "体育"},
]

# 各分类下的子分类筛选（typeId 来源：分类页 a.btn，已逐页实测）
# 分类页真实格式: /vod/list/{页码}/{typeId}/0
_FILTERS_MAP = {
    # 电影（tid=1）
    "1": [
        ("全部", 1), ("动作片", 9), ("喜剧片", 10), ("爱情片", 11),
        ("恐怖片", 12), ("剧情片", 13), ("科幻片", 14), ("惊悚片", 15),
        ("奇幻片", 16), ("动画片", 17), ("悬疑片", 18), ("冒险片", 19),
        ("体育", 20), ("战争片", 21), ("倫理片", 460),
    ],
    # 电视剧（tid=2）
    "2": [
        ("全部", 2), ("国产剧", 22), ("香港剧", 23), ("台湾剧", 24),
        ("欧美剧", 25), ("日本剧", 26), ("韩国剧", 27), ("泰国剧", 28),
        ("海外剧", 29),
    ],
    # 综艺（tid=3）
    "3": [
        ("全部", 3), ("大陆综艺", 30), ("港台综艺", 31), ("日韩综艺", 32),
        ("欧美综艺", 33), ("海外综艺", 34),
    ],
    # 动漫（tid=4）
    "4": [
        ("全部", 4), ("国产动漫", 35), ("日韩动漫", 36), ("欧美动漫", 37),
        ("海外动漫", 38), ("港台动漫", 459),
    ],
    # 短剧（tid=457）
    "457": [
        ("全部", 457), ("漫剧", 540), ("玄幻", 541), ("剧情", 542),
        ("女性成长", 543), ("权谋", 544), ("豪门", 545), ("齐幻", 546),
        ("宫斗", 547), ("脑洞", 548), ("科幻", 549), ("冒险", 550),
        ("仙侠", 551), ("喜剧", 552), ("动作", 553), ("悬疑", 554),
        ("战神", 555), ("刑侦", 556), ("求生", 557), ("商战", 558),
        ("恐怖", 559), ("武侠", 560), ("爱情", 561), ("AI漫剧", 562),
        ("擦边剧", 563),
    ],
    # 体育（tid=462）
    "462": [
        ("全部", 462),
    ],
}

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    _sub = _FILTERS_MAP.get(tid, [("全部", 0)])
    FILTERS[tid] = [
        {"key": "class", "name": "分类",
         "value": [{"n": n, "v": str(v)} for n, v in _sub]},
    ]


# ===================== 正则（全部依据真实源码） =====================
# 卡片块：<div class="moon-list-item"> ... </div>（用非贪婪跨行）
_RE_CARD_BLOCK = re.compile(
    r'<div[^>]*class="[^"]*moon-list-item[^"]*"[^>]*>(.*?)</div>\s*</div>\s*(?=<div[^>]*class="[^"]*moon-list-item|</div>\s*</div>|$)',
    re.S | re.I)
# 卡片链接
_RE_CARD_A = re.compile(r'<a\s+href="(/vod/player/0/\d+)"[^>]*>', re.I)
# 封面
_RE_CARD_PIC = re.compile(
    r'<img[^>]*?(?:data-original|data-src|src)="([^"]+)"', re.I)
# 标题
_RE_CARD_NAME = re.compile(
    r'<p[^>]*class="[^"]*item-title[^"]*"[^>]*>\s*([\s\S]*?)\s*</p>', re.I)
# 评分
_RE_CARD_RATE = re.compile(
    r'<label[^>]*class="[^"]*rate[^"]*"[^>]*>\s*([\d.]+)\s*</label>', re.I)
# 在看人数
_RE_CARD_WATCH = re.compile(r'>\s*([\d,]+)人次在看\s*<', re.I)

# 播放页核心数据
_RE_LINELIST = re.compile(r'var\s+temLineList\s*=\s*(\[[\s\S]*?\])\s*;', re.S)
# 当前集对象 Iyplayer（含 id）
_RE_IYPLAYER = re.compile(r'Iyplayer\s*=\s*\{[^}]*?id\s*:\s*(\d+)', re.S)

# 详情页标题
_RE_H1 = re.compile(r'<h1[^>]*>([\s\S]*?)</h1>', re.I)
_RE_TITLE = re.compile(r'<title>([\s\S]*?)</title>', re.I)

# 线路 tag → 别名
_LINE_ALIAS = {
    "1080zyk": "1080资源", "lzm3u8": "量子M3U8", "bfzym3u8": "暴风资源",
    "dyttm3u8": "电影天堂", "ffm3u8": "非凡M3U8", "wjm3u8": "无尽M3U8",
    "modum3u8": "魔都M3U8", "jsm3u8": "极速M3U8", "mtm3u8": "茅台M3U8",
    "vip": "VIP线路", "wztv": "王者TV",
}
_LINE_PRIORITY = ["vip", "1080zyk", "wztv", "bfzym3u8", "dyttm3u8",
                  "ffm3u8", "lzm3u8", "modum3u8", "jsm3u8", "mtm3u8"]


class Spider(Spider):

    def getName(self):
        return "蝶卡影视"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
        }
        self.default_pic = DEFAULT_PIC
        self._play_cache = {}
        self._seg_cache = {}          # 分片内存缓存（预取用）
        self.log("init: site=%s" % self.site_url)

    # ------------------ 基础工具 ------------------
    def _fetch(self, url, timeout=20, headers=None):
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            if hasattr(rsp, "text"):
                return rsp.text or ""
            if hasattr(rsp, "content"):
                return rsp.content.decode("utf-8", "ignore")
            return str(rsp)
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.site_url + url
        return urllib.parse.urljoin(self.site_url + "/", url)

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

    # ------------------ 列表解析 ------------------
    def _extract_videos(self, html):
        """
        从 SSR HTML 中解析卡片列表。
        采用【锚点法】：以 <a href="/vod/player/0/{id}"> 为锚，
        每个锚点到下一个锚点之间即为一张卡片，取其中的 图/名/分。
        该法不依赖 card 外层 div 的确切闭合方式，最稳健。
        """
        videos = []
        seen = set()
        if not html:
            return videos

        # 找到所有卡片锚点位置
        anchors = list(re.finditer(r'<a\s+[^>]*href="(/vod/player/0/\d+)"[^>]*>',
                                   html, re.I))
        self.log("  锚点: %d 个" % len(anchors))
        if not anchors:
            return videos

        for idx, m in enumerate(anchors):
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)
            start = m.start()
            end = anchors[idx + 1].start() if idx + 1 < len(anchors) else len(html)
            blk = html[start:end]

            # 封面图：data-original 优先，其次 src
            pic = self.default_pic
            mp = re.search(r'(?:data-original|data-src)="([^"]+)"', blk, re.I)
            if not mp:
                mp = re.search(r'<img[^>]*src="([^"]+)"', blk, re.I)
            if mp and mp.group(1):
                pic = self._fix_url(mp.group(1))

            # 标题：p.item-title 优先
            name = ""
            mn = re.search(
                r'<p[^>]*class="[^"]*item-title[^"]*"[^>]*>\s*([\s\S]*?)\s*</p>',
                blk, re.I)
            if mn:
                name = self._clean(mn.group(1))
            if not name:
                # 首页轮播图 banner: <h2 class="bannertxex">片名</h2>
                mb = re.search(
                    r'<h2[^>]*class="[^"]*(?:bannertxex|banner)[^"]*"[^>]*>\s*([\s\S]*?)\s*</h2>',
                    blk, re.I)
                if mb:
                    name = self._clean(mb.group(1))
            if not name:
                # 其它 h2/h3 标题
                mh = re.search(r'<h[23][^>]*>\s*([\s\S]*?)\s*</h[23]>', blk, re.I)
                if mh:
                    name = self._clean(mh.group(1))
            if not name:
                # 兜底：img 的 alt 或 title 属性
                ma = re.search(r'<img[^>]*alt="([^"]+)"', blk, re.I)
                if ma:
                    name = self._clean(ma.group(1))
            if not name:
                mt = re.search(r'<a[^>]*title="([^"]+)"', blk, re.I)
                if mt:
                    name = self._clean(mt.group(1))

            # 评分
            rate = ""
            mr = re.search(r'<label[^>]*class="[^"]*rate[^"]*"[^>]*>\s*([\d.]+)\s*</label>',
                           blk, re.I)
            if mr:
                rate = mr.group(1)

            # 在看人数
            watch = ""
            mw = re.search(r'>\s*([\d,]+)\s*人次在看', blk)
            if mw:
                watch = mw.group(1)

            remarks = ""
            if rate and rate != "0.0":
                remarks = "评分%s" % rate
            if watch:
                remarks = ("%s %s人在看" % (remarks, watch)).strip()

            videos.append({
                "vod_id": href,
                "vod_name": name or href.rsplit("/", 1)[-1],
                "vod_pic": pic or self.default_pic,
                "vod_remarks": remarks,
            })
        return videos

    # ------------------ 首页 ------------------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        url = self.site_url + "/index.html"
        html = self._fetch(url)
        self.log("home HTML: %d" % len(html))
        return {"list": self._extract_videos(html)}

    # ------------------ 分类 ------------------
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        extend = extend or {}

        sub = extend.get("class")
        try:
            sub_id = int(sub) if sub not in (None, "", "全部") else 0
        except Exception:
            sub_id = 0

        # 真实格式: /vod/list/{页码}/{顶层tid}/{子分类id}
        #   子分类 id=0 表示全部；国产剧=22 等（extend["class"] 传入）
        type_id = sub_id if sub_id else 0

        url = "%s/vod/list/%d/%s/%d" % (self.site_url, page, tid, type_id)
        self.log("category: %s" % url)
        html = self._fetch(url)
        videos = self._extract_videos(html)

        # 从分页条解析真实总页数（/vod/list/{页}/{tid}/0）
        pagecount = 9999
        pages = re.findall(r'/vod/list/(\d+)/\d+/\d+', html or "")
        if pages:
            try:
                pagecount = max(int(p) for p in pages)
            except Exception:
                pass

        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 10, "total": pagecount * 10,
        }

    # ------------------ 搜索 ------------------
    def searchContent(self, key, quick, pg="1"):
        """
        真实搜索接口（已实测，参数名必须是 keyword，不是 name！）
          GET /public/auto/search1.html?keyword={关键词}
            必需的请求头: X-Requested-With: XMLHttpRequest
            Referer      : {site}/search/index.html?keyword={关键词}
          返回 HTML 片段，结果卡片结构（与本站列表页不同！）：
            <a href="/vod/player/0/{id}" class="moon-item seachlist ...">
              <img data-src="封面" src="封面" ... alt="片名海报">
              <h2 class="ohv-ellipsis">片名</h2>
              <div class="label-list"><span>2026</span><span>国产剧</span><span>日本</span></div>
              <p class="intro ohv-ellipsis">简介...</p>
          实测: keyword=妈妈 → 10 条;  keyword=蒸蒸日上 → 1 条;  乱码词 → 0 条
        """
        page = int(pg) if pg else 1
        kw = urllib.parse.quote(key or "")
        url = "%s/public/auto/search1.html?keyword=%s" % (self.site_url, kw)
        self.log("search: %s" % url)
        html = self._fetch(url, headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "%s/search/index.html?keyword=%s" % (self.site_url, kw),
        })
        videos = self._extract_search_videos(html)
        self.log("  搜索结果: %d" % len(videos))
        return {"list": videos, "page": page, "pagecount": 1,
                "limit": 30, "total": len(videos)}

    def _extract_search_videos(self, html):
        """解析 /public/auto/search1.html 的结果（结构与列表页不同，独立处理）"""
        videos = []
        seen = set()
        if not html:
            return videos
        anchors = list(re.finditer(
            r'<a\s+[^>]*href="(/vod/player/0/\d+)"[^>]*class="[^"]*seachlist[^"]*"[^>]*>',
            html, re.I))
        if not anchors:
            anchors = list(re.finditer(
                r'<a\s+[^>]*class="[^"]*seachlist[^"]*"[^>]*href="(/vod/player/0/\d+)"[^>]*>',
                html, re.I))
        for idx, m in enumerate(anchors):
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)
            start = m.start()
            end = anchors[idx + 1].start() if idx + 1 < len(anchors) else len(html)
            blk = html[start:end]

            pic = self.default_pic
            mp = re.search(r'(?:data-src|data-original|src)="([^"]+)"', blk, re.I)
            if mp and mp.group(1):
                pic = self._fix_url(mp.group(1))

            name = ""
            mn = re.search(r'<h2[^>]*class="[^"]*ohv-ellipsis[^"]*"[^>]*>\s*([\s\S]*?)\s*</h2>',
                           blk, re.I)
            if not mn:
                mn = re.search(r'<h2[^>]*>\s*([\s\S]*?)\s*</h2>', blk, re.I)
            if mn:
                name = self._clean(mn.group(1))
            if not name:
                ma = re.search(r'<img[^>]*alt="([^"]+?)海报"', blk, re.I)
                if ma:
                    name = self._clean(ma.group(1))
            if not name:
                name = href.rsplit("/", 1)[-1]

            # 标签：年份 / 类型 / 地区（label-list）
            remarks = ""
            ml = re.search(r'<div[^>]*class="[^"]*label-list[^"]*"[^>]*>([\s\S]*?)</div>',
                           blk, re.I)
            if ml:
                labs = [self._clean(x) for x in
                        re.findall(r'<span[^>]*>([\s\S]*?)</span>', ml.group(1))]
                labs = [x for x in labs if x]
                if labs:
                    remarks = " ".join(labs)

            videos.append({
                "vod_id": href,
                "vod_name": name,
                "vod_pic": pic or self.default_pic,
                "vod_remarks": remarks,
            })
        return videos

    # ------------------ 详情 ------------------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        self.log("  HTML: %d" % len(html))
        if not html:
            return {"list": []}

        # 标题
        name = ""
        m = _RE_H1.search(html)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = _RE_TITLE.search(html)
            if m:
                name = self._clean(m.group(1).split("_")[-1].split("-")[-1])
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        # 封面
        pic = self.default_pic
        m = re.search(r'<img[^>]*?(?:data-original|data-src|src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"',
                      html, re.I)
        if m:
            pic = self._fix_url(m.group(1))

        # 简介：优先页面正文 div.text-main-info（纯剧情简介）
        #      meta description 兜底（含站名杂物，需清洗）
        content = ""
        m = re.search(
            r'<div[^>]*class="[^"]*text-main-info[^"]*"[^>]*>\s*([\s\S]*?)\s*</div>',
            html, re.I)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = re.search(
                r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
                html, re.I)
            if m:
                content = self._clean(m.group(1))
                # 清洗 meta 杂物：去掉 "站名...片名类型年份" 前缀（正文中首次出现的剧情起点难以定位，
                # 但 meta 里片名后的"电视剧/国产剧/2026"等属于标题拼接，尽量截掉站名+片名前缀）
                mn = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
                if mn:
                    h1 = self._clean(mn.group(1))
                    if h1 and h1 in content:
                        content = content[content.index(h1) + len(h1):]
                content = re.sub(r'^(?:电影|电视剧|国产剧|综艺|动漫|短剧|体育)+',
                                 '', content)
                content = re.sub(r'^(?:19|20)\d{2}(?=[\u4e00-\u9fff])', '', content)
        content = INTRO_PREFIX + ("\n" + content if content else "")

        # 年份/地区/评分：取 label-list 区域，真实源码形如：
        #   <div class="label-list">
        #     <span class="din-condensed">6.1分</span>
        #     <span style="">2026</span></span>   ← 注意此处有 bug 多余的 </span>
        #     <span>大陆</span>
        #   </div>
        # 所以先取 label-list 整块（用 h3/后续 div 作为截断锚点，避免误吞），
        # 再分别匹配： 评分=含"分"的 span，年份=4位数字，地区=纯中文 span
        year, area, score = "", "", ""
        m = re.search(r'<div[^>]*class="[^"]*label-list[^"]*"[^>]*>([\s\S]*?)</div>',
                      html, re.I)
        if m:
            seg = m.group(1)
            # 评分
            ms = re.search(r'>\s*([\d.]+)\s*分\s*<', seg)
            if ms:
                score = ms.group(1)
            # 年份（4位数字）
            my = re.search(r'>\s*((?:19|20)\d{2})\s*(?:-\d{2}-\d{2})?\s*<', seg)
            if not my:
                my = re.search(r'((?:19|20)\d{2})', seg)
            if my:
                year = my.group(1)
            # 地区（纯中文 span，排除含"分"/纯数字）
            for sv in re.findall(r'<span[^>]*>\s*([^<>]{1,12}?)\s*</span>', seg):
                sv = sv.strip()
                if not sv or '分' in sv or re.match(r'^\d', sv):
                    continue
                if re.match(r'^[\u4e00-\u9fff\-]+$', sv) and sv != year:
                    area = sv
                    break

        # 导演/演员：演员表区域，真实源码形如：
        #   <div class="actor-list ...">
        #     <a class="worker-name">导演</a>
        #     <div class="flex-r-s-s"> 姚婷婷 </div>
        #   </div>
        #   <div class="actor-list ...">
        #     <a class="worker-name">演员</a>
        #     <div class="flex-r-s-s"> 高叶 韩东君 </div>
        #   </div>
        director, actor = "", ""
        for am in re.finditer(
                r'class="[^"]*worker-name[^"]*"[^>]*>\s*([^<]{1,6})\s*</a>'
                r'([\s\S]{0,400}?)</div>\s*</div>',
                html, re.I):
            role = self._clean(am.group(1))
            who = re.sub(r'\s+', ' ', self._clean(am.group(2))).strip()
            if not who:
                continue
            if '导演' in role:
                director = who
            elif '演员' in role or '主演' in role:
                actor = who

        # 剧集：核心 temLineList
        lines = self._parse_lines(html)
        self.log("  线路: %s" % {k[0]: len(v) for k, v in lines.items()})

        if not lines:
            # 无剧集数据时，至少返回单集=当前页
            return {"list": [{
                "vod_id": vod_id, "vod_name": name, "vod_pic": pic,
                "vod_content": content,
                "vod_actor": actor, "vod_director": director,
                "vod_year": year, "vod_area": area, "vod_score": score,
                "vod_remarks": "单集",
                "vod_play_from": "默认",
                "vod_play_url": "%s$%s" % (name, url),
            }]}

        sorted_tags = sorted(
            lines.keys(),
            key=lambda x: (_LINE_PRIORITY.index(x[0])
                           if x[0] in _LINE_PRIORITY else 999))

        play_from = []
        play_url = []
        for tag_key in sorted_tags:
            tag = tag_key[0]
            eps = lines[tag_key]
            play_from.append(_LINE_ALIAS.get(tag, tag or "线路"))
            play_url.append("#".join("%s$%s" % (n, u) for n, u in eps))

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area,
            "vod_score": score,
            "vod_remarks": "%d条线路" % len(play_from),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    def _extract_linelist_json(self, html):
        """
        稳健提取 temLineList 的 JSON 文本。
        不用非贪婪正则（数组内 "# LineList":[] 等嵌套会出错），
        改用【括号配对】从起始 '[' 扫描到匹配的 ']'。
        """
        m = re.search(r'var\s+temLineList\s*=\s*\[', html)
        if not m:
            return ""
        start = html.index('[', m.start())
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(html)):
            ch = html[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        return html[start:i + 1]
        return ""

    def _parse_lines(self, html):
        """解析 temLineList，按 tag 分组，返回 {(tag,): [(集名, 播放页url), ...]}"""
        result = {}
        raw = self._extract_linelist_json(html)
        if not raw:
            self.log("  未找到 temLineList")
            return result
        try:
            data = json.loads(raw)
        except Exception as e:
            self.log("  temLineList JSON 解析失败: %s" % e)
            return result

        for item in data:
            tag = item.get("tag") or "line"
            ep_name = item.get("name") or item.get("subTitle") or ""
            vid = item.get("videoID") or ""
            line_id = item.get("id") or ""
            play_url = "%s/vod/player/%s/%s" % (self.site_url, line_id, vid)
            key = (tag,)
            result.setdefault(key, []).append((ep_name, play_url))
        return result

    # ------------------ 播放 ------------------
    def playerContent(self, flag, id, vipFlags):
        """TVBox 传入的 id 可能是完整URL/相对路径，做全面兼容"""
        raw = (id or "").strip()
        if raw.startswith("http"):
            play_page = raw
        elif raw.startswith("/"):
            play_page = self.site_url + raw
        elif raw.isdigit():
            # 兜底：纯数字按 vod/player/0/{id} 处理
            play_page = "%s/vod/player/0/%s" % (self.site_url, raw)
        else:
            play_page = self._fix_url(raw)

        self.log("player: %s" % play_page)

        # 命中缓存
        if play_page in self._play_cache:
            return self._play_cache[play_page]

        html = self._fetch(play_page)
        raw_json = self._extract_linelist_json(html)

        if raw_json:
            data = []
            try:
                data = json.loads(raw_json)
            except Exception as e:
                self.log("  temLineList 解析失败: %s" % e)

            target = None
            if data:
                # 1) 优先匹配 URL 中的 line_id（/vod/player/{line_id}/{vid}）
                mm = re.search(r'/vod/player/(\d+)/', play_page)
                if mm:
                    cur_id = mm.group(1)
                    if cur_id != "0":
                        for it in data:
                            if str(it.get("id")) == cur_id:
                                target = it
                                break
                # 2) 匹配 Iyplayer.id（页面内嵌当前集对象）
                if target is None:
                    mi = re.search(r'Iyplayer\s*=\s*\{[^}]*?id\s*:\s*(\d+)', html)
                    if mi:
                        cur_id = mi.group(1)
                        for it in data:
                            if str(it.get("id")) == cur_id:
                                target = it
                                break
                # 3) 兜底取第一条
                if target is None:
                    target = data[0]

            if target:
                raw_file = target.get("file") or ""
                real = self._decode_file(raw_file)
                if real:
                    # 直接返回真实 m3u8 直链（最稳，兼容所有播放器/内核）。
                    #   实测本站每集真实地址是 master 主列表，先降一级到子列表，
                    #   避免 TVBox 处理 master 时反复选流。
                    final_url = self._resolve_master(real) or real
                    res = {
                        "parse": 0,
                        "playUrl": "",
                        "url": final_url,
                        "header": {
                            "User-Agent": UA,
                            "Referer": self.site_url + "/",
                        },
                    }
                    self._play_cache[play_page] = res
                    self.log("  => m3u8直链: %s" % final_url[:160])
                    return res

        # 兜底：交给 TVBox 嗅探
        res = {"parse": 1, "playUrl": "", "url": play_page,
               "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        self._play_cache[play_page] = res
        return res

    def _decode_file(self, raw_file):
        """真实解密: file[3:] -> Base64 -> URL解码 -> m3u8"""
        if not raw_file:
            return ""
        # 若本身已是明文 m3u8
        if raw_file.startswith("http") and ".m3u8" in raw_file.lower():
            return raw_file
        try:
            body = raw_file[3:]                      # 去掉首部3个随机字符
            body += "=" * (-len(body) % 4)           # 补齐 Base64 padding
            dec = base64.b64decode(body).decode("utf-8", "ignore")
            url = urllib.parse.unquote(dec)
            if url.startswith("//"):
                url = "https:" + url
            return url
        except Exception as e:
            self.log("  解密失败: %s" % e)
            return ""

    def _resolve_master(self, m3u8_url):
        """
        若 m3u8_url 是【主播放列表(master)】，返回其【子列表的绝对地址】；
        否则原样返回 ""。

        注：本站实测 master 只含一个码率子流（3000k/hls/mixed.m3u8），
        但为稳妥起见，若存在多个 BANDWIDTH，优先取 bandwididth 最小的子流
        （低码率更不易卡），无 BANDWIDTH 时取第一个。
        """
        if not m3u8_url or ".m3u8" not in m3u8_url.lower():
            return ""
        try:
            rsp = self.fetch(m3u8_url, headers={
                "User-Agent": UA, "Referer": self.site_url + "/"}, timeout=15)
            txt = rsp.content.decode("utf-8", "ignore")
            if "EXT-X-STREAM-INF" not in txt:
                return ""                            # 已是子列表，无需处理

            # 逐块解析：记录每个 #EXT-X-STREAM-INF 的带宽 + 紧随其后的地址
            cands = []          # [(bandwidth, url)]
            last_bw = None
            for ln in txt.splitlines():
                s = ln.strip()
                if not s:
                    continue
                if s.startswith("#EXT-X-STREAM-INF"):
                    mb = re.search(r'BANDWIDTH=(\d+)', s)
                    last_bw = int(mb.group(1)) if mb else 0
                    continue
                if s.startswith("#"):
                    continue
                # 这是子列表地址
                cands.append((last_bw if last_bw is not None else 0,
                              urllib.parse.urljoin(m3u8_url, s)))
                last_bw = None

            if not cands:
                return ""
            # 选码率最小的（更流畅）
            cands.sort(key=lambda x: x[0])
            return cands[0][1]
        except Exception as e:
            self.log("  resolve_master 失败: %s" % e)
        return ""

    # ------------------ 本地代理（预取 + 缓存，解决卡顿） ------------------
    def _proxy_pref(self):
        """本地代理前缀（TVBox 收到后回调 localProxy）"""
        return "proxy://do=py&url="

    def _seg_fetch(self, url, referer, timeout=25):
        """带 Range 拉取分片并重试（Range 走 CDN 流式通道，更稳）"""
        h = {
            "User-Agent": UA,
            "Referer": referer or (self.site_url + "/"),
            "Accept": "*/*",
            "Range": "bytes=0-",          # ★ 关键：与官网播放器一致
        }
        last = None
        for _ in range(3):                 # 失败重试 3 次
            try:
                rsp = self.fetch(url, headers=h, timeout=timeout)
                if rsp.status_code in (200, 206) and rsp.content:
                    return rsp.content
            except Exception as e:
                last = e
        # 退化：不带 Range 再试一次
        try:
            rsp = self.fetch(url, headers={
                "User-Agent": UA, "Referer": referer or (self.site_url + "/")},
                timeout=timeout)
            return rsp.content
        except Exception as e:
            last = e
        self.log("  seg_fetch FAIL %s -> %s" % (url, last))
        return b""

    def _prefetch(self, urls, referer):
        """并发预取一批分片到缓存"""
        try:
            import threading
            def worker(u):
                if u in self._seg_cache:
                    return
                data = self._seg_fetch(u, referer)
                if data:
                    self._seg_cache[u] = data
            ths = [threading.Thread(target=worker, args=(u,)) for u in urls]
            for t in ths:
                t.setDaemon(True)
                t.start()
        except Exception as e:
            self.log("  prefetch err: %s" % e)

    def _start_roll_prefetch(self, seg_urls, referer, start=0):
        """
        后台滚动预取：从 start 起按顺序持续缓存后续分片（每批 4 片并发下载）。
        已缓存的跳过；缓存超过 240 片时清理最旧的 60 片，防止内存膨胀。
        并发预取速度实测 > 实时播放速度，可一直领先于播放进度 → 根治卡顿。
        """
        try:
            import threading

            if getattr(self, "_prefetching", None) == id(seg_urls):
                return                              # 同一列表已在预取中
            self._prefetching = id(seg_urls)

            def roll():
                try:
                    import threading as _th
                    idx = start
                    n = len(seg_urls)
                    while idx < n:
                        # 内存保护
                        if len(self._seg_cache) > 240:
                            for k in list(self._seg_cache.keys())[:60]:
                                self._seg_cache.pop(k, None)
                        batch = [u for u in seg_urls[idx:idx + 4]
                                 if u not in self._seg_cache]

                        def one(u):
                            data = self._seg_fetch(u, referer)
                            if data:
                                self._seg_cache[u] = data

                        ths = [_th.Thread(target=one, args=(u,)) for u in batch]
                        for t in ths:
                            t.setDaemon(True)
                            t.start()
                        for t in ths:
                            t.join()                 # 等这一批完再下一批
                        idx += 4
                except Exception as e:
                    self.log("  roll_prefetch 异常: %s" % e)

            t = threading.Thread(target=roll)
            t.setDaemon(True)
            t.start()
        except Exception as e:
            self.log("  roll_prefetch err: %s" % e)

    def localProxy(self, param):
        """
        本地代理（由 playerContent 的 proxy:// 触发），支持三种：
          · type=ts  : 把整条 HLS 拼成【连续 TS 流】一次返回（首选方案）。
                       播放器当成一个大文件，大缓冲边下边播，不转圈。
          · m3u8     : 抓取 → 主列表降级子列表 → 分片改写为经代理地址，
                       并并发预取缓存（兜底，供不支持连续流的播放器）。
          · 分片(.ts): 命中内存缓存优先，否则带 Range+重试拉取。
          · 其它      : 直接转发（图片等）。
        """
        try:
            url = ""
            ptype = ""
            if isinstance(param, dict):
                url = param.get("url", "") or param.get("path", "") or ""
                ptype = param.get("type", "") or ""
            else:
                for pair in str(param).split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k in ("url", "path"):
                            url = v
                        elif k == "type":
                            ptype = v
            url = urllib.parse.unquote(url) if "%" in url else url
            if not url:
                return [200, "text/plain", b"", ""]
            url = self._fix_url(url)

            low = url.lower()
            referer = self.site_url + "/"
            headers = {
                "User-Agent": UA,
                "Referer": referer,
                "Accept": "*/*",
            }

            # ---------- 分片：命中缓存优先 ----------
            if low.endswith(".ts") or (".ts?" in low):
                data = self._get_seg(url, referer)
                return [200, "video/mp2t", data or b"", ""]

            rsp = self.fetch(url, headers=headers, timeout=20)
            content = rsp.content
            ctype = (rsp.headers.get("Content-Type", "") or "")

            head_txt = content[:2000].decode("utf-8", "ignore") if content else ""
            is_m3u8 = (
                ".m3u8" in low
                or "mpegurl" in ctype.lower()
                or head_txt.lstrip().startswith("#EXTM3U")
            )

            if is_m3u8:
                txt = content.decode("utf-8", "ignore")

                # ① master playlist → 取子列表
                if "EXT-X-STREAM-INF" in txt:
                    sub = ""
                    for ln in txt.splitlines():
                        s = ln.strip()
                        if s and not s.startswith("#"):
                            sub = s
                            break
                    if sub:
                        sub_url = urllib.parse.urljoin(url, sub)
                        try:
                            r2 = self.fetch(sub_url, headers=headers, timeout=20)
                            txt = r2.content.decode("utf-8", "ignore")
                            url = sub_url
                        except Exception as e:
                            self.log("  proxy: 取子列表失败 %s" % e)

                # ② 分片地址 → 全部改写为“经本代理”
                pref = self._proxy_pref()
                out = []
                seg_urls = []
                for ln in txt.splitlines():
                    s = ln.strip()
                    if not s or s.startswith("#"):
                        out.append(ln)
                        continue
                    absu = urllib.parse.urljoin(url, s)
                    seg_urls.append(absu)
                    out.append(pref + urllib.parse.quote(absu, safe=""))
                new_txt = "\n".join(out)

                # ③ 并发预取（兜底路径）
                if seg_urls:
                    self._prefetch(seg_urls[:12], referer)
                    self._start_roll_prefetch(seg_urls, referer, start=12)

                return [200, "application/vnd.apple.mpegurl",
                        new_txt.encode("utf-8"), ""]

            if not ctype:
                ctype = "application/octet-stream"
            return [200, ctype, content, ""]
        except Exception as e:
            self.log("localProxy error: %s" % e)
            return [200, "text/plain", b"", ""]

    def _get_seg(self, url, referer):
        """
        取分片：命中缓存直接返回；未命中则等锁/下载（避免与预取线程重复下载）。
        """
        if url in self._seg_cache:
            return self._seg_cache[url]
        try:
            import threading
            lock = getattr(self, "_seg_lock", None)
            if lock is None:
                lock = self._seg_lock = threading.Lock()
            with lock:
                if url in self._seg_cache:
                    return self._seg_cache[url]
                data = self._seg_fetch(url, referer)
                if data:
                    self._seg_cache[url] = data
                return data
        except Exception as e:
            self.log("  _get_seg err: %s" % e)
            return self._seg_fetch(url, referer)

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url or url.startswith("http")

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
