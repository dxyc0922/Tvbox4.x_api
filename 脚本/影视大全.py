# coding=utf-8
"""
影视大全 iysdq1.com | TVBox Python 爬虫

网站结构：
  - 分类导航  ：/ → 推荐 ; /vodtype/{1..5}.html → 电影/电视剧/综艺/动漫/短剧
  - 筛选      ：/vodshow/{id}-{area}-{by}-{class}-{lang}-{letter}--{page}---{year}.html
                （12 段式，段位定义见文件中部 FILTERS 注释，全部来自真实 href 实测）
  - 搜索      ：/vodsearch/{urlencode(词)}-------------.html   （也支持 ?wd=词）
                分页：/vodsearch/{词}----------{页码}---.html
  - 列表卡片  ：div.public-list-box > a.public-list-exp[href=/voddetail/{id}.html][title=剧名]
                img[alt="剧名封面图"][src=占位图][data-src=真实封面]
                span.public-list-prb → 更新至第N集 / 已完结
                span.public-prt     → 类型角标
  - 详情页    ：div.this-desc-info  → 评分/年份/地区/状态
                div.this-info       → 导演 / 演员
                #height_limit       → 简介正文
                div.anthology-tab a → 线路名（AA线/A线/B线.../http下载）
                div.anthology-list-box ul.anthology-list-play li a[href=/vodplay/{id}-{sid}-{nid}.html]
  - 播放页    ：var player_aaaa={"flag":"play","encrypt":0,...,
                "url":"https://svip.xgplay17.com/.../index.m3u8","from":"xiguam3u8",...}
                真实 m3u8 明文在 player_aaaa.url（首选）
                部分页面为 JXplayer 壳：iframe src 的 v= 参数（兜底）
"""
import re
import sys
import json
import time
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
                print("[iysdq]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.iysdq1.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 站点真实占位图（源码实测：所有卡片 src 均指向它，真实封面在 data-src）
DEFAULT_PIC = HOST + "/template/shoutu45/assets/images/img-bj-k.png"

# 简介前缀（按要求固定添加）
INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 分类：源码实测 href="/vodtype/{tid}.html"
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "5", "type_name": "短剧"},
]

# =====================================================================
# 筛选（vodshow）—— 全部依据 5 个真实筛选页源码逐项抄录，非臆测
#
# 真实 URL（按 - 切分共 12 段，1-based）：
#   seg1 分类id | seg2 地区 | seg3 排序by | seg4 类型class
#   seg5 语言   | seg6 字母 | seg7 字母续(仅0-9) | seg8 保留
#   seg9 页码   | seg10/11 保留 | seg12 年份
#
# 证据（源码 href 原文）：
#   重置     /vodshow/2-----------.html
#   按最新   /vodshow/2-大陆-time-国产剧--------2026.html
#   按最热   /vodshow/2-大陆-hits-国产剧--------2026.html
#   按评分   /vodshow/2-大陆-score-国产剧--------2026.html
#   第3页    /vodshow/2-大陆--国产剧-----3---2026.html
#   "全部"   = 该段留空（清空即不筛）
#
# 注意：每个分类（电影/电视剧/综艺/动漫/短剧）的"类型""地区""语言""年份"
#       选项各不相同；短剧无地区与语言筛选。以下数据均按真实源码逐一列出。
# =====================================================================

# 分类筛选数据 —— 严格依据 5 个真实筛选页面源码逐项抄录
_CAT_FILTERS = {
    # 电影：/vodshow/1-大陆--喜剧片-----2---2026.html
    "1": {
        "class": ["动作片", "喜剧片", "科幻片", "恐怖片", "爱情片", "剧情片", "战争片",
                  "记录片", "动画片", "惊悚", "犯罪", "悬疑", "冒险", "奇幻", "家庭",
                  "历史", "传记", "古装", "音乐", "同性", "运动", "武侠", "短片",
                  "歌舞", "西部", "儿童", "灾难", "戏曲", "真人秀", "青春"],
        "area": ["大陆", "香港", "台湾", "美国", "日本", "韩国", "英国", "法国", "德国",
                 "意大利", "西班牙", "俄罗斯", "加拿大", "印度", "泰国", "其它",
                 "新加坡", "菲律宾", "澳大利亚", "土耳其", "瑞典", "巴西", "荷兰",
                 "印度尼西亚", "挪威", "智利", "爱尔兰", "伊朗", "蒙古"],
        "lang": ["国语", "粤语", "闽南语", "英语", "韩语", "日语", "法语", "德语", "其它"],
        "year": (2026, 2000),
    },
    # 电视剧：/vodshow/2-大陆--国产剧-----2---2026.html
    "2": {
        "class": ["国产剧", "欧美剧", "香港剧", "韩国剧", "台湾剧", "日本剧", "海外剧",
                  "泰国剧", "剧情", "爱情", "喜剧", "悬疑", "犯罪", "古装", "动作",
                  "奇幻", "惊悚", "家庭", "历史", "科幻", "战争", "同性", "武侠",
                  "冒险", "恐怖", "纪录", "传记", "短片", "运动", "音乐", "儿童",
                  "歌舞", "西部", "灾难"],
        "area": ["大陆", "香港", "台湾", "美国", "日本", "韩国", "英国", "泰国", "其它",
                 "西班牙", "加拿大", "法国", "印度", "新加坡", "俄罗斯", "巴西",
                 "澳大利亚", "土耳其", "意大利", "德国", "菲律宾", "瑞典",
                 "印度尼西亚", "爱尔兰", "挪威", "智利"],
        "lang": ["国语", "粤语", "闽南语", "英语", "韩语", "日语", "法语", "德语", "其它"],
        "year": (2026, 2000),
    },
    # 综艺：/vodshow/3-大陆--大陆综艺-----2---2026.html
    "3": {
        "class": ["大陆综艺", "港台综艺", "日韩综艺", "欧美综艺", "真人秀", "纪录片",
                  "脱口秀", "音乐", "歌舞", "相声", "喜剧", "爱情", "历史", "运动",
                  "冒险", "剧情", "访谈", "旅游", "悬疑", "家庭", "短片", "同性",
                  "动作", "儿童", "惊悚", "美食"],
        "area": ["大陆", "香港", "台湾", "韩国", "日本", "美国", "英国", "其它", "法国",
                 "加拿大", "泰国", "新加坡", "俄罗斯", "西班牙", "巴西", "澳大利亚",
                 "德国", "菲律宾"],
        "lang": ["国语", "粤语", "英语", "韩语", "日语", "法语", "德语", "其它"],
        "year": (2026, 2000),
    },
    # 动漫：/vodshow/4-大陆--国产动漫-----2---2026.html
    "4": {
        "class": ["国产动漫", "日韩动漫", "欧美动漫", "港台动漫", "海外动漫", "动画",
                  "喜剧", "剧情", "奇幻", "冒险", "动作", "科幻", "爱情", "儿童",
                  "家庭", "短片", "悬疑", "运动", "古装", "武侠", "音乐", "犯罪",
                  "惊悚", "战争", "恐怖", "历史", "搞笑", "歌舞", "热血"],
        "area": ["大陆", "香港", "台湾", "日本", "韩国", "美国", "英国", "法国", "其它",
                 "加拿大", "俄罗斯", "西班牙", "意大利", "印度", "德国", "泰国", "智利"],
        "lang": ["国语", "粤语", "闽南语", "英语", "韩语", "日语", "法语", "其它"],
        "year": (2026, 2000),
    },
    # 短剧：/vodshow/5---反转爽剧-----2---2026.html  （无地区、无语言筛选）
    "5": {
        "class": ["女频恋爱", "反转爽剧", "古装仙侠", "年代穿越", "脑洞悬疑", "现代都市"],
        "area": [],          # 短剧无地区筛选
        "lang": [],          # 短剧无语言筛选
        "year": (2026, 2021),  # 短剧年份仅 2026-2021
    },
}

# 字母（seg6）—— 全部页面一致
_F_LETTER = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["0-9"]

# 排序（seg3）—— 源码 .site-tabs 三按钮，默认"按最新"
_F_SORT = [("time", "按最新"), ("hits", "按最热"), ("score", "按评分")]


def _mk_filters(tid):
    """生成指定分类的 TVBox filters。

    ★ TVBox 规范要求：filters 里每个分类的值必须是【列表】，
      列表元素为 {"key":..., "name":..., "value":[{n,v},...]}。
      之前返回字典会导致筛选菜单完全不渲染。
    """
    cfg = _CAT_FILTERS.get(str(tid), {})
    flist = []

    # 地区（短剧无此项）
    if cfg.get("area"):
        flist.append({
            "key": "area",
            "name": "地区",
            "value": [{"n": "全部", "v": ""}] +
                     [{"n": x, "v": x} for x in cfg["area"]],
        })

    # 类型
    if cfg.get("class"):
        flist.append({
            "key": "class",
            "name": "类型",
            "value": [{"n": "全部", "v": ""}] +
                     [{"n": x, "v": x} for x in cfg["class"]],
        })

    # 年份（按分类实际范围，倒序）
    y_max, y_min = cfg.get("year", (2026, 2000))
    flist.append({
        "key": "year",
        "name": "年份",
        "value": [{"n": "全部", "v": ""}] +
                 [{"n": str(y), "v": str(y)}
                  for y in range(y_max, y_min - 1, -1)],
    })

    # 语言（短剧无此项）
    if cfg.get("lang"):
        flist.append({
            "key": "lang",
            "name": "语言",
            "value": [{"n": "全部", "v": ""}] +
                     [{"n": x, "v": x} for x in cfg["lang"]],
        })

    # 字母（全部页面一致）
    flist.append({
        "key": "letter",
        "name": "字母",
        "value": [{"n": "不限", "v": ""}] +
                 [{"n": x, "v": x} for x in _F_LETTER],
    })

    # 排序（全部页面一致）
    flist.append({
        "key": "by",
        "name": "排序",
        "value": [{"n": n, "v": v} for v, n in _F_SORT],
    })

    return flist


# 每个分类一套独立的筛选列表（结构 {"tid": [ {key,name,value}, ... ]}）
FILTERS = {c["type_id"]: _mk_filters(c["type_id"]) for c in CLASSES}


# ===================== 正则（全部对应真实源码结构） =====================

# 列表卡片：a.public-list-exp ... <img ... alt="X封面图" ... data-src="真实URL">
_RE_CARD = re.compile(
    r'<a\s+[^>]*class="[^"]*public-list-exp[^"]*"[^>]*'
    r'href="(/voddetail/\d+\.html)"[^>]*'
    r'title="([^"]*)"[^>]*>\s*'
    r'<img[^>]*?alt="([^"]*?)"[^>]*?data-src="([^"]*)"',
    re.S | re.I)

# 卡片备注（更新至第N集 / 已完结 / 全集 …）
_RE_REMARKS = re.compile(
    r'<span\s+class="public-list-prb[^"]*"[^>]*>([^<]+)</span>',
    re.I)

# 详情页 · 简介：<div id="height_limit" class="text"><strong ...>描述:</strong>正文</div>
_RE_INTRO = re.compile(
    r'<div[^>]*id="height_limit"[^>]*>(.*?)</div>',
    re.S | re.I)
_RE_INTRO_DESC = re.compile(r'<strong[^>]*>\s*描述[:：]\s*</strong>', re.I)

# 详情页 · 元信息：<div class="this-desc-info">...<span>2025</span><span>大陆</span>...
_RE_DESC_INFO = re.compile(
    r'<div[^>]*class="this-desc-info"[^>]*>(.*?)</div>',
    re.S | re.I)
_RE_DESC_SCORE = re.compile(
    r'<span[^>]*class="this-desc-score[^"]*"[^>]*>(.*?)</span>',
    re.S | re.I)
_RE_SPAN = re.compile(r'<span[^>]*>(.*?)</span>', re.S | re.I)

# 详情页 · 导演 / 演员：<div class="this-info"><strong>导演:</strong><a>名</a><i>，</i>...
_RE_INFO_BLOCK = re.compile(
    r'<div[^>]*class="this-info"[^>]*>\s*<strong[^>]*>([^<]+)</strong>(.*?)</div>',
    re.S | re.I)

# 详情页 · 影片参数区（info-parameter，源码实测）：
# <li><em class="cor4">年份：</em>2026</li>
# <li><em class="cor4">类型：</em><a>剧情</a> <a>喜剧</a>...</li>
# <li><em class="cor4">上映：</em>2026-10-15(美国)</li>
_RE_PARAM_WRAP = re.compile(
    r'<div[^>]*class="info-parameter[^"]*"[^>]*>.*?<ul>(.*?)</ul>',
    re.S | re.I)
_RE_PARAM_LI = re.compile(
    r'<li[^>]*>\s*<em[^>]*>([^<]+)</em>(.*?)</li>',
    re.S | re.I)

# 详情页 · 线路名：<div class="anthology-tab ..."><a class="swiper-slide">...名<span class="badge">N</span></a>
_RE_TAB_WRAP = re.compile(
    r'<div[^>]*class="anthology-tab[^"]*"[^>]*>(.*?)</div>\s*</div>',
    re.S | re.I)
_RE_TAB_A = re.compile(
    r'<a[^>]*class="[^"]*swiper-slide[^"]*"[^>]*>(.*?)</a>',
    re.S | re.I)

# 详情页 · 剧集列表容器组
_RE_LIST_WRAP = re.compile(
    r'<div[^>]*class="anthology-list[^"]*select-c"[^>]*>(.*)</div>\s*</div>\s*</div>',
    re.S | re.I)
_RE_LIST_BOX = re.compile(
    r'<div[^>]*class="anthology-list-box[^"]*"[^>]*>(.*?)</div>\s*</div>',
    re.S | re.I)
_RE_EP_A = re.compile(
    r'<a[^>]*href="(/vodplay/\d+-\d+-\d+\.html)"[^>]*>(.*?)</a>',
    re.S | re.I)
# http下载（mp4 直链）
_RE_DL_A = re.compile(
    r'<a[^>]*class="left"[^>]*href="(https?://[^"]+\.mp4)"[^>]*>(.*?)</a>',
    re.S | re.I)

# 播放页 · player_aaaa JSON（真实源码实测，url 字段即直链 m3u8）
_RE_PLAYER_AAAA = re.compile(
    r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', re.S | re.I)
# 播放页 · iframe 真实 m3u8（JXplayer 壳兜底）
_RE_IFRAME_SRC = re.compile(
    r'<iframe[^>]*?src="([^"]+)"', re.S | re.I)
_RE_V_PARAM = re.compile(r'[?&]v=([^&"\']+)', re.I)

_LINE_PRIORITY = ["AA线", "A线", "B线", "C线", "D线", "E线", "F线"]


class Spider(Spider):

    def getName(self):
        return "影视大全"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": self.site_url + "/",
            "Upgrade-Insecure-Requests": "1",
        }
        self.default_pic = DEFAULT_PIC
        self._play_cache = {}
        self.log("init: site=%s" % self.site_url)

    # ---------------- 基础工具 ----------------

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
        # 去掉字体图标实体（如 &#xe679;）
        s = re.sub(r"&#x?[0-9a-fA-F]+;", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    # ---------------- 列表解析（首页/分类/搜索 通用） ----------------

    def _extract_videos(self, html):
        videos = []
        seen = set()
        if not html:
            return videos

        for m in _RE_CARD.finditer(html):
            href, title, alt, pic = m.groups()
            href = href.replace("&amp;", "&")
            if href in seen:
                continue
            seen.add(href)

            # 备注：在卡片 a 标签闭合前就近截取
            tail = html[m.end():m.end() + 600]
            rm = _RE_REMARKS.search(tail)
            remarks = self._clean(rm.group(1)) if rm else ""

            name = self._clean(title) or self._clean(alt).replace("封面图", "")
            videos.append({
                "vod_id":      href,
                "vod_name":    name,
                "vod_pic":     self._fix_url(pic) or self.default_pic,
                "vod_remarks": remarks,
            })
        return videos

    def _build_show_url(self, tid, pg, extend):
        """按真实 12 段式拼 vodshow 筛选 URL（段位定义见文件头注释）。

        注意：中文值必须 urlencode（源码/浏览器会自动编码，但直连请求不会），
        而分隔符 '-' 与空段必须保留原样，故逐段编码后再拼接。
        """
        seg = [""] * 12
        seg[0] = str(tid)
        seg[1] = (extend.get("area") or "").strip()
        seg[2] = (extend.get("by") or "").strip()
        seg[3] = (extend.get("class") or "").strip()
        seg[4] = (extend.get("lang") or "").strip()
        seg[5] = (extend.get("letter") or "").strip()
        try:
            p = int(pg) if pg else 1
        except Exception:
            p = 1
        if p > 1:
            seg[8] = str(p)
        seg[11] = (extend.get("year") or "").strip()
        # 逐段编码：safe='' 确保 / 等也被编码；"-" 作为段间分隔符不参与编码
        enc = [urllib.parse.quote(s, safe="") for s in seg]
        return "%s/vodshow/%s.html" % (self.site_url, "-".join(enc))

    # 真实分页信息：<div class="rg10">2&nbsp;/&nbsp;16页</div>
    # 注意：中间是 &nbsp; 实体（可能被解析成空格/\xa0），故用宽松匹配
    _RE_PAGECNT = re.compile(
        r"(\d+)\s*(?:&nbsp;|\xa0|\s)*/?(?:&nbsp;|\xa0|\s)*(\d+)\s*页", re.I)
    # 真实总条数：<script>$('.hl-total').html('610');</script>
    _RE_TOTAL = re.compile(r"hl-total'\)\.html\('(\d+)'\)", re.I)

    def _page_info(self, html):
        """返回 (总页数, 总条数)。源码实测，缺失时回退 1 / 0。"""
        pc, total = 1, 0
        if not html:
            return pc, total
        m = self._RE_PAGECNT.search(html)
        if m:
            cur, tot = int(m.group(1)), int(m.group(2))
            if tot > 0:
                pc = tot
            elif cur > 0:
                pc = cur
        m = self._RE_TOTAL.search(html)
        if m:
            total = int(m.group(1))
        return pc, total

    # ---------------- TVBox 接口 ----------------

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        self.log("home HTML 长度: %d" % len(html))
        return {"list": self._extract_videos(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        extend = extend or {}

        # 判断是否带筛选条件（全部为空 = 无筛选）
        has_filter = any((extend.get(k) or "").strip() for k in
                         ("area", "by", "class", "lang", "letter", "year"))

        if has_filter or page > 1:
            # 真实筛选/翻页页：走 12 段式 vodshow
            url = self._build_show_url(tid, page, extend)
        else:
            # 无任何筛选且第1页：沿用更简洁真实的分类页 /vodtype/{tid}.html
            url = "%s/vodtype/%s.html" % (self.site_url, tid)
        self.log("category: %s" % url)

        html = self._fetch(url)
        videos = self._extract_videos(html)

        # 无筛选请求失败时，回退到分类页，保证基础可用
        if not videos and has_filter:
            fb = "%s/vodtype/%s.html" % (self.site_url, tid)
            self.log("  筛选无结果/失败，回退: %s" % fb)
            html = self._fetch(fb)
            videos = self._extract_videos(html)

        pagecount, total = self._page_info(html)
        if page > pagecount:
            pagecount = page
        self.log("  最终: %d 条 / 共%d页 / 总%d" % (len(videos), pagecount, total))
        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 24, "total": total or len(videos),
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        kw = urllib.parse.quote(key)
        # 真实搜索 URL（源码实测）：
        #   第1页 /vodsearch/{kw}-------------.html
        #   分页   /vodsearch/{kw}----------{pg}---.html（页码落第 11 段）
        if page > 1:
            url = "%s/vodsearch/%s----------%d---.html" % (
                self.site_url, kw, page)
        else:
            url = "%s/vodsearch/%s-------------.html" % (self.site_url, kw)
        self.log("search: %s" % url)
        html = self._fetch(url)
        videos = self._extract_videos(html)
        pagecount, total = self._page_info(html)
        if page > pagecount:
            pagecount = page
        self.log("  最终: %d 条 / 共%d页" % (len(videos), pagecount))
        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 24, "total": total or len(videos),
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        if not html:
            return {"list": []}

        # --- 标题：div.this-desc-title ---
        name = ""
        m = re.search(r'<div[^>]*class="this-desc-title"[^>]*>(.*?)</div>',
                      html, re.S | re.I)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
            if m:
                name = self._clean(m.group(1).split("_")[0].split("-")[0])
        name = re.sub(r"\s*《?([^》]*)》?.*", r"\1", name).strip() or vod_id

        # --- 封面：详情页顶部背景 div.this-pic-bj style:background-image ---
        pic = self.default_pic
        m = re.search(r'this-pic-bj[^>]*background-image:\s*url\([\'"]?([^\'")]+)',
                      html, re.I)
        if not m:
            m = re.search(r'<img[^>]*?data-src="([^"]+)"', html, re.I)
        if m:
            pic = self._fix_url(m.group(1))

        # --- 简介：#height_limit （去掉 "描述:"） ---
        content = ""
        m = _RE_INTRO.search(html)
        if m:
            raw = m.group(1)
            raw = _RE_INTRO_DESC.sub("", raw)
            content = self._clean(raw)
        if not content:
            # 兜底：meta description（源码实测同样含剧情介绍）
            m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"',
                          html, re.I)
            if m:
                content = self._clean(m.group(1))
                content = re.sub(r"^.*?剧情介绍[:：]\s*", "", content)
        content = (INTRO_PREFIX + "\n" + content) if content else INTRO_PREFIX

        # --- 评分 / 年份 / 地区 / 状态：div.this-desc-info ---
        score, year, area, remarks = "", "", "", ""
        m = _RE_DESC_INFO.search(html)
        if m:
            block = m.group(1)
            sm = _RE_DESC_SCORE.search(block)
            if sm:
                score = self._clean(sm.group(1))
                block = block.replace(sm.group(0), "")
            spans = [self._clean(x) for x in _RE_SPAN.findall(block)]
            spans = [x for x in spans if x]
            # 真实顺序：年份 地区 状态
            if len(spans) >= 1:
                year = spans[0]
            if len(spans) >= 2:
                area = spans[1]
            if len(spans) >= 3:
                remarks = spans[2]

        # --- 导演 / 演员：div.this-info ---
        director, actor = "", ""
        for m in _RE_INFO_BLOCK.finditer(html):
            label = self._clean(m.group(1))
            names = [self._clean(x) for x in
                     re.findall(r'<a[^>]*>(.*?)</a>', m.group(2), re.S | re.I)]
            names = [x for x in names if x]
            if "导演" in label:
                director = ", ".join(names)
            elif "演员" in label or "主演" in label:
                actor = ", ".join(names)

        # --- 影片参数区（info-parameter）：类型/上映/语言/更新 等 ---
        vod_class, publish, lang = "", "", ""
        pm = _RE_PARAM_WRAP.search(html)
        if pm:
            for li in _RE_PARAM_LI.finditer(pm.group(1)):
                label = self._clean(li.group(1)).rstrip("：:")
                val = self._clean(li.group(2))
                if not val:
                    continue
                if label == "类型":
                    tags = [self._clean(x) for x in
                            re.findall(r'<a[^>]*>(.*?)</a>', li.group(2),
                                       re.S | re.I)]
                    vod_class = ",".join([x for x in tags if x])
                elif label == "上映":
                    publish = val
                elif label == "语言":
                    lang = val

        # 年份/地区优先取参数区，缺失时回退 this-desc-info
        pm2 = self._param_simple(html, "年份")
        if pm2:
            year = pm2
        pm3 = self._param_simple(html, "地区")
        if pm3:
            area = pm3

        # --- 线路 + 剧集 ---
        lines = self._parse_play_lines(html)
        if not lines:
            return {"list": []}

        play_from = []
        play_url = []
        for line_name, eps in lines:
            play_from.append(line_name)
            play_url.append("#".join("%s$%s" % (n, h) for n, h in eps))

        return {"list": [{
            "vod_id":       vod_id,
            "vod_name":     name,
            "vod_pic":      pic,
            "vod_content":  content,
            "vod_actor":    actor,
            "vod_director": director,
            "vod_year":     year,
            "vod_area":     area,
            "vod_score":    score,
            "vod_class":    vod_class,
            "vod_remarks":  remarks or ("%d条线路" % len(lines)),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url":  "$$$".join(play_url),
        }]}

    def _param_simple(self, html, label):
        """从 info-parameter 区取纯文本字段（如 年份/地区）。"""
        pm = _RE_PARAM_WRAP.search(html)
        if not pm:
            return ""
        for li in _RE_PARAM_LI.finditer(pm.group(1)):
            lb = self._clean(li.group(1)).rstrip("：:")
            if lb == label:
                # 类型等含 <a> 的字段取全部文本
                val = self._clean(li.group(2))
                return val
        return ""

    def _parse_play_lines(self, html):
        """按源码真实结构解析线路名 + 剧集（顺序严格一一对应）。"""
        # 1) 线路名列表
        line_names = []
        m = re.search(r'<div[^>]*class="anthology-tab[^"]*"[^>]*>(.*?)</div>\s*</div>',
                      html, re.S | re.I)
        if m:
            for am in _RE_TAB_A.finditer(m.group(1)):
                inner = am.group(1)
                inner = re.sub(r'<span[^>]*>.*?</span>', '', inner,
                               flags=re.S | re.I)   # 去掉 badge 数量
                nm = self._clean(inner).replace("&nbsp;", "").strip()
                line_names.append(nm)

        # 2) 剧集容器组
        boxes = []
        mw = re.search(
            r'<div[^>]*class="anthology-list[^"]*select-c"[^>]*>(.*)'
            r'<script>\s*\$\(["\']\.anthology-tab a',
            html, re.S | re.I)
        scope = mw.group(1) if mw else html
        for bm in re.finditer(
                r"<div[^>]*class=[\"']anthology-list-box[^\"']*[\"'][^>]*>(.*?)</ul>",
                scope, re.S | re.I):
            body = bm.group(1)
            eps = []
            for em in _RE_EP_A.finditer(body):
                href = em.group(1).replace("&amp;", "&")
                ep_name = self._clean(em.group(2)) or ("第%s集" % (len(eps) + 1))
                eps.append((ep_name, href))
            # http下载线
            if not eps:
                for dm in _RE_DL_A.finditer(body):
                    href = dm.group(1).replace("&amp;", "&")
                    nm = self._clean(dm.group(2)) or ("下载%s" % (len(eps) + 1))
                    eps.append((nm, href))
            if eps:
                boxes.append(eps)

        # 3) 合并：线路名与容器一一对应
        lines = []
        for i, eps in enumerate(boxes):
            nm = line_names[i] if i < len(line_names) else ("线路%d" % (i + 1))
            lines.append((nm, eps))

        # 4) 排序：优先 AA线/A线/B线…，http下载置后
        def _key(item):
            n = item[0]
            return _LINE_PRIORITY.index(n) if n in _LINE_PRIORITY else 999
        lines.sort(key=_key)
        return lines

    # ---------------- 播放 ----------------

    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        # http下载返回的是 mp4 直链，直接用
        if play_page.lower().endswith(".mp4"):
            return {
                "parse": 0, "playUrl": "", "url": play_page,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page)

        real_url = ""
        if html:
            # 首选：var player_aaaa = {...} 的 url 字段（真实源码实测直出 m3u8）
            m = _RE_PLAYER_AAAA.search(html)
            if m:
                try:
                    raw = m.group(1)
                    # 源码中 \/ 转义，先还原再解析
                    raw = raw.replace('\\/', '/')
                    pa = json.loads(raw)
                    real_url = (pa.get("url") or "").strip()
                    enc = pa.get("encrypt", 0)
                    self.log("  player_aaaa from=%s encrypt=%s url=%s" %
                             (pa.get("from"), enc, real_url[:120]))
                    # encrypt 0 = 明文直链；如遇 1/2（base64等）走兜底嗅探
                    if enc and enc != 0:
                        real_url = ""
                except Exception as e:
                    self.log("  player_aaaa JSON 解析失败: %s" % e)
                    real_url = ""

            # 兜底1：JXplayer 壳，真实 m3u8 在 iframe src 的 v= 参数
            if not real_url:
                m = _RE_IFRAME_SRC.search(html)
                if m:
                    src = m.group(1).replace("&amp;", "&")
                    vm = _RE_V_PARAM.search(src)
                    if vm:
                        real_url = urllib.parse.unquote(vm.group(1))

            # 兜底2：整页直接找 m3u8
            if not real_url:
                m2 = re.search(r'(https?://[^\s"\'&]+\.m3u8[^\s"\']*)', html, re.I)
                if m2:
                    real_url = m2.group(1)

        if real_url:
            self.log("  => m3u8: %s" % real_url[:160])
            res = {
                "parse": 0, "playUrl": "", "url": real_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": self.site_url + "/",
                },
            }
        else:
            # 兜底交给 TVBox 嗅探
            res = {
                "parse": 1, "playUrl": "", "url": play_page,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
        self._play_cache[play_page] = (now, res)
        return res

    def localProxy(self, param):
        try:
            url = ""
            if isinstance(param, dict):
                url = param.get("url", "")
            else:
                for pair in str(param).split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k == "url":
                            url = v
            if not url:
                return [200, "image/jpeg", b"", ""]
            url = urllib.parse.unquote(url) if "%" in url else url
            url = self._fix_url(url)
            rsp = self.fetch(url, headers={
                "User-Agent": UA, "Referer": self.site_url + "/"}, timeout=15)
            content = rsp.content
            ctype = rsp.headers.get("Content-Type", "image/jpeg")
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return [200, ctype, content, ""]
        except Exception:
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
