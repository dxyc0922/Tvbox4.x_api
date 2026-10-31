# -*- coding: utf-8 -*-
# ============ 饭搭子影视 源 (fdzys.com) 终极稳定版 ============
import sys, re, json
from urllib.parse import quote

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

HOST = 'https://fdzys.com'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'

CATEGORIES = [
    {'type_id': 'movie',   'type_name': '电影'},
    {'type_id': 'tv',      'type_name': '电视剧'},
    {'type_id': 'dongman', 'type_name': '动漫片'},
    {'type_id': 'zongyi',  'type_name': '综艺片'},
    {'type_id': 'tiyu',    'type_name': '体育'},
    {'type_id': 'duanju',  'type_name': '短剧'},
]

FILTER_OPTIONS = {
    'movie': {
        'class': [('all','全部'),('dongzuo','动作'),('xiju','喜剧'),('aiqing','爱情'),('kehuan','科幻'),('kongbupian','恐怖片'),('juqing','剧情'),('zhanzheng','战争'),('fanzui','犯罪'),('donghua','动画'),('xuanyi','悬疑'),('jilu','纪录'),('guzhuang','古装')],
        'area':  [('all','全部'),('dalu','大陆'),('xianggang','香港'),('taiwan','台湾'),('meiguo','美国'),('faguo','法国'),('yingguo','英国'),('riben','日本'),('hanguo','韩国'),('deguo','德国'),('taiguo','泰国'),('yindu','印度'),('yidali','意大利'),('xibanya','西班牙'),('jianada','加拿大'),('qita','其他')],
        'lang':  [('all','全部'),('guoyu','国语'),('yingyu','英语'),('yueyu','粤语'),('minnanyu','闽南语'),('hanyu','韩语'),('riyu','日语'),('fayu','法语'),('deyu','德语'),('qita','其它')],
        'year':  [('all','全部')] + [(str(y), str(y)) for y in range(2026, 2017, -1)],
    },
    'tv': {
        'class': [('all','全部'),('guochan','国产'),('oumei','欧美'),('riben','日本'),('hanguo','韩国'),('juqing','剧情'),('aiqing','爱情'),('xuanyi','悬疑'),('guzhuang','古装')],
        'area':  [('all','全部'),('dalu','大陆'),('xianggang','香港'),('taiwan','台湾'),('meiguo','美国'),('riben','日本'),('hanguo','韩国')],
        'lang':  [('all','全部'),('guoyu','国语'),('yingyu','英语'),('riyu','日语'),('hanyu','韩语'),('yueyu','粤语')],
        'year':  [('all','全部')] + [(str(y), str(y)) for y in range(2026, 2017, -1)],
    },
    'dongman': {
        'class': [('all','全部'),('guochan','国漫'),('rihan','日韩'),('oumei','欧美'),('donghua','动画'),('juqing','剧情'),('kehuan','科幻')],
        'area':  [('all','全部'),('dalu','大陆'),('riben','日本'),('meiguo','美国')],
        'lang':  [('all','全部'),('guoyu','国语'),('riyu','日语')],
        'year':  [('all','全部')] + [(str(y), str(y)) for y in range(2026, 2017, -1)],
    },
    'zongyi': {
        'class': [('all','全部'),('dalu','大陆'),('gangtai','港台'),('rihan','日韩'),('oumei','欧美'),('zongyi','综艺'),('yinyue','音乐')],
        'area':  [('all','全部'),('dalu','大陆'),('xianggang','香港'),('taiwan','台湾')],
        'lang':  [('all','全部'),('guoyu','国语'),('yueyu','粤语')],
        'year':  [('all','全部')] + [(str(y), str(y)) for y in range(2026, 2017, -1)],
    },
    'tiyu': {
        'class': [('all','全部'),('zuqiu','足球'),('lanqiu','篮球'),('wangqiu','网球'),('taiqiu','斯诺克')],
        'area': [('all','全部')], 'lang': [('all','全部')], 'year': [('all','全部')],
    },
    'duanju': {
        'class': [('all','全部'),('aiqing','爱情'),('juqing','剧情'),('xuanhuan','玄幻')],
        'area': [('all','全部')], 'lang': [('all','全部')], 'year': [('all','全部')],
    },
}

SORT_OPTIONS = [{'n': '最新', 'v': 'new'}, {'n': '热门', 'v': 'hot'}, {'n': '高分', 'v': 'score'}]
FILTER_TYPES = ('movie', 'tv', 'dongman', 'zongyi')


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOST.rstrip('/')
        self.ua = UA
        self.types = {c['type_id']: c['type_name'] for c in CATEGORIES}
        self._hd = {'User-Agent': self.ua, 'Referer': self.base + '/',
                    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9'}

    def _build_filters(self):
        fs = {}
        for c in CATEGORIES:
            tid = c['type_id']
            opts = FILTER_OPTIONS.get(tid, {})
            if not opts: continue
            filters = []
            for key, name in [('class','剧情'), ('area','地区'), ('lang','语言'), ('year','年份')]:
                if opts.get(key):
                    filters.append({'key': key, 'name': name, 'value': [{'n': n, 'v': v} for v, n in opts[key]]})
            filters.append({'key': 'sort', 'name': '排序', 'value': SORT_OPTIONS})
            fs[tid] = filters
        return fs

    def _get(self, url):
        try:
            r = self.fetch(url, headers=self._hd, timeout=12000)
            return r.text if hasattr(r, 'text') else str(r)
        except Exception:
            return ''

    def _abs(self, u):
        if not u: return ''
        if u.startswith('http'): return u
        if u.startswith('//'): return 'https:' + u
        return self.base + (u if u.startswith('/') else '/' + u)

    def _items(self, h):
        items, seen = [], set()
        if not h: return items
        
        for m in re.finditer(r'<a\s+[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', h):
            url = m.group(1)
            inner = m.group(2)
            full_tag = m.group(0)
            
            if not re.search(r'/(?:movie|tv|dongman|zongyi|tiyu|duanju)/', url):
                continue
                
            vid = self._abs(url)
            if vid in seen: continue
            seen.add(vid)
            
            pic = ''
            for attr in ['data-src', 'data-original', 'src']:
                m_pic = re.search(r'<img[^>]*?' + attr + r'=["\']([^"\']+)["\']', inner)
                if m_pic:
                    tmp_url = m_pic.group(1)
                    if 'base64' not in tmp_url and 'loading' not in tmp_url and '.gif' not in tmp_url:
                        pic = self._abs(tmp_url)
                        break
            
            name_m = re.search(r'<div class="title">([^<]+)</div>', inner)
            if not name_m: name_m = re.search(r'title="([^"]+)"', full_tag)
            name = name_m.group(1).strip() if name_m else ''
            if not name: continue
            
            remark_m = re.search(r'<div class="tag[^>]*>([^<]+)</div>', inner)
            remark = remark_m.group(1).strip() if remark_m else ''
            
            items.append({'vod_id': vid, 'vod_name': name[:60], 'vod_pic': pic, 'vod_remarks': remark[:30]})
        return items

    def _pagecount(self, h, cur):
        mx = cur
        for m in re.finditer(r'[?&]page=(\d+)', h):
            try: mx = max(mx, int(m.group(1)))
            except: pass
        return mx if mx > cur else cur + 1

    def homeContent(self, filter=False):
        r = {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()]}
        if filter: r['filters'] = self._build_filters()
        r['list'] = self.homeVideoContent().get('list', [])
        return r

    def homeVideoContent(self):
        return {'list': self._items(self._get(self.base))}

    # ========== ★ 终极修复：彻底解决“全部”过滤问题 ==========
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try: pn = max(int(str(pg)), 1)
        except: pn = 1
        ex = json.loads(extend) if isinstance(extend, str) and extend else (extend if isinstance(extend, dict) else {})
        
        main_cat = str(tid).split('/')[0]
        
        # 提取用户的选择，并进行彻底清洗
        raw_class = ex.get('class', 'all')
        raw_area = ex.get('area', 'all')
        raw_lang = ex.get('lang', 'all')
        raw_year = ex.get('year', 'all')
        
        # 过滤掉“全部”、空字符串、中文“全部”等所有非有效值
        c_val = raw_class if raw_class and raw_class not in ('全部', 'all', '') else 'all'
        a_val = raw_area if raw_area and raw_area not in ('全部', 'all', '') else 'all'
        l_val = raw_lang if raw_lang and raw_lang not in ('全部', 'all', '') else 'all'
        y_val = raw_year if raw_year and raw_year not in ('全部', 'all', '') else 'all'
        
        # 构造拼接数组：class 永远存在，其他有值才拼
        segments = [c_val]
        if a_val != 'all': segments.append(a_val)
        if l_val != 'all': segments.append(l_val)
        if y_val != 'all' and main_cat in FILTER_TYPES: segments.append(y_val)
        
        filter_path = '-'.join(segments)
        
        # 排序后缀：只在有排序值时添加
        sort_val = ex.get('sort', '')
        sort_suffix = '/' + sort_val if sort_val and sort_val not in ('默认', '') else ''
        
        url = '%s/%s/%s%s' % (self.base, main_cat, filter_path, sort_suffix)
        if pn > 1: url += '?page=%d' % pn
        
        self.log("Request URL: %s" % url)  # 关键调试日志，务必查看

        h = self._get(url)
        if not h: return {'page': pn, 'pagecount': pn, 'limit': 24, 'total': 0, 'list': []}
        items = self._items(h)
        return {'page': pn, 'pagecount': self._pagecount(h, pn), 'limit': 24, 'total': len(items), 'list': items}

    # ========== ★ 绝对精准的简介提取 ==========
    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        h = self._get(self._abs(vid))
        if not h: return {'list': []}
        
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_actor': '', 'vod_director': '', 'vod_content': '', 'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        
        m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', h)
        if m: d['vod_name'] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', h, re.I)
        if m: d['vod_pic'] = self._abs(m.group(1).strip())
        if not d['vod_pic']:
            m = re.search(r'<img[^>]*?data-src="([^"]+)"', h)
            if m: d['vod_pic'] = self._abs(m.group(1))
        
        content = ""
        m = re.search(r'<div[^>]*class="[^"]*wrapper_more_text[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>', h, re.S)
        if m:
            block = m.group(1)
            block = re.sub(r'<(input|label)[^>]*>[\s\S]*?</\1>', '', block, flags=re.I)
            block = re.sub(r'<(input|label)[^>]*>', '', block, flags=re.I)
            block = re.sub(r'<br\s*/?>', '\n', block, flags=re.I)
            block = re.sub(r'<[^>]+>', '', block)
            block = block.replace('简介:', '').replace('简介：', '').strip()
            block = block.replace('　　', '').replace('\u3000\u3000', '')
            block = re.sub(r'\n+', '\n', block)
            content = block.strip()
        else:
            m = re.search(r'<div[^>]*class="[^"]*intro[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>\s*</div>', h, re.S)
            if m:
                block = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                block = block.replace('简介:', '').replace('简介：', '').strip()
                block = block.replace('　　', '').replace('\u3000\u3000', '')
                content = block.strip()

        # ★★★ 唯一的修改：加上你指定的前缀 ★★★
        d['vod_content'] = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！\n" + content
        
        m = re.search(r'导演[:：]?\s*</div>\s*([^<]+)', h)
        if m: d['vod_director'] = m.group(1).strip()
        
        m = re.search(r'主演[:：]?\s*</div>\s*([^<]+)', h)
        if m: d['vod_actor'] = m.group(1).strip()
        
        m = re.search(r'<div class="tag[^>]*>([^<]+)</div>', h)
        if m: d['vod_remarks'] = m.group(1).strip()

        routes = {}
        for sid, seg in re.findall(r'<li class="swiper-slide player_name[^"]*" data-sid="(\d+)">([\s\S]*?)</li>', h):
            name_match = re.search(r'<a[^>]*>([^<]+)<span', seg)
            if name_match: routes[sid] = name_match.group(1).strip()
            
        body = h.split('class="tab-content"', 1)[-1]
        blocks = re.split(r'<div id="playlist\d+" class="tab-pane[^"]*" data-sid="(\d+)">', body)
        
        groups, seen_sid = [], set()
        for i in range(1, len(blocks), 2):
            sid = blocks[i]
            if sid in seen_sid: continue
            seen_sid.add(sid)
            seg = blocks[i + 1].split('<div id="playlist')[0]
            eps = re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', seg)
            
            # ★★★ 唯一的修改：过滤掉底部的“关于我们”、“登录”等无关链接 ★★★
            eps = [(u, ep) for u, ep in eps if not any(k in u.lower() or k in ep for k in ['javascript', 'about', 'login', '关于我们', '登录'])]
            
            if eps: groups.append((sid, eps))
            
        if groups:
            froms, urls = [], []
            for sid, eps in groups:
                froms.append(routes.get(sid, '线路' + sid))
                urls.append('#'.join('%s$%s' % (ep.strip().replace('#', '-'), self._abs(u)) for u, ep in eps))
            d['vod_play_from'] = '$$$'.join(froms)
            d['vod_play_url'] = '$$$'.join(urls)
            
        return {'list': [d]}

    def searchContent(self, key, quick=False, pg='1'):
        h = self._get('%s/yu-%s-xiangquan-de-yingpian-shippin-zhibo' % (self.base, quote(str(key))))
        return {'list': self._items(h) if h else []}

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id)
        if not url.startswith('http'): url = self._abs(url)
        if re.search(r'\.(?:%s)(?:\?|$)' % VIDEO_EXTS, url, re.I):
            return {'parse': 0, 'url': url, 'header': json.dumps(self._hd)}
        h = self._get(url)
        if not h: return {'parse': 0, 'url': ''}
        m = re.search(r'var player_aaaa=(\{.*?\})</script>', h)
        if not m: return {'parse': 0, 'url': ''}
        try: j = json.loads(m.group(1))
        except: return {'parse': 0, 'url': ''}
        share = (j.get('url') or '').strip()
        if not share: return {'parse': 0, 'url': ''}
        if re.search(r'\.(?:%s)(?:\?|$)' % VIDEO_EXTS, share, re.I):
            return {'parse': 0, 'url': share, 'header': json.dumps(self._hd)}
        if not share.startswith('http'): return {'parse': 1, 'url': share}
        h2 = self._get(share)
        m2 = re.search(r'const url\s*=\s*"([^"]+)"', h2 or '')
        if not m2: return {'parse': 0, 'url': share}
        path = m2.group(1)
        final = path if path.startswith('http') else ((re.match(r'https?://[^/]+', share).group(0) if re.match(r'https?://[^/]+', share) else self.base) + path if path.startswith('/') else share.rsplit('/', 1)[0] + '/' + path)
        return {'parse': 0, 'url': final, 'header': json.dumps(self._hd)}

    def isVideoFormat(self, url): return bool(url) and ('.m3u8' in url or bool(re.search(r'\.(?:%s)(?:\?|$)' % VIDEO_EXTS, url, re.I)))
    def manualVideoCheck(self): return False
    def destroy(self): pass


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
