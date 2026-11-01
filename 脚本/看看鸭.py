# coding=utf-8
"""
看看鸭 kankanya.me | TVBox Python 爬虫 
关键:
  - 破解服务端人机验证 (encrypt + robot.php 换取 Cookie)
  - 解析 player_aaaa -> POST /kkyplayer/api.php -> 自定义 Base64 解码真实直链
  - 支持 分类/筛选(地区·类型·语言·年份·排序)/搜索/多播放源
"""
import sys
sys.path.append('..')
import re
import json
import base64
import hashlib
import random
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urljoin
from base.spider import Spider

xurl = "https://www.kankanya.me"
headerx = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"


# ---- 门页 encrypt 复现：静态表移位 3 位，每字符前后各垫一个随机表内字符，再 base64 ----
_STATIC = "PXhw7UT1B0a9kQDKZsjIASmOezxYG4CHo5Jyfg2b8FLpEvRr3WtVnlqMidu6cN"


def _encrypt(s):
    out = []
    for ch in s:
        i = _STATIC.find(ch)
        code = _STATIC[(i + 3) % 62] if i != -1 else ch
        out.append(random.choice(_STATIC) + code + random.choice(_STATIC))
    return base64.b64encode(''.join(out).encode()).decode()


# ---- kkyplayer 直链解码（见文件头注释 5） ----
def _b64d(s):
    if isinstance(s, str):
        s = s.encode('latin1')
    return base64.b64decode(s + b'=' * (-len(s) % 4))


def _decode_kky2(data_url):
    # urlmode=2：base64 → 步长 3 取下标 1 起的字符 → 静态表后移 59 位
    blob = _b64d(data_url)
    out = []
    for b in blob[1::3]:
        ch = chr(b)
        if ch in _STATIC:
            out.append(_STATIC[(_STATIC.index(ch) + 59) % 62])
        else:
            out.append(ch)
    return ''.join(out)


def _decode_kky1(data_url):
    # urlmode=1：base64 → XOR md5("test") 循环 → base64 → 分段置换
    key = hashlib.md5(b'test').hexdigest().encode()
    s1 = _b64d(data_url)
    code = bytes(b ^ key[i % 32] for i, b in enumerate(s1))
    s2 = _b64d(code.decode('latin1')).decode('latin1')
    parts = s2.split('/')
    if len(parts) < 3:
        return ''
    a = json.loads(_b64d(parts[1]).decode('latin1'))
    b = json.loads(_b64d(parts[0]).decode('latin1'))
    payload = _b64d('/'.join(parts[2:])).decode('latin1')
    out = []
    for ch in payload:
        if ('a' <= ch <= 'z' or 'A' <= ch <= 'Z') and ch in b:
            out.append(b[a.index(ch)])
        else:
            out.append(ch)
    return ''.join(out)


# ---- 分类与筛选（站内 /show/ 筛选栏实测值，2026-10-26） ----
_CATS = [
    ('dianying', '电影'),
    ('juji', '剧集'),
    ('zongyi', '综艺'),
    ('dongman', '动漫'),
]
_CLASS = {
    'dianying': ['喜剧', '爱情', '恐怖', '动作', '科幻', '剧情', '战争', '警匪', '犯罪',
                 '动画', '奇幻', '武侠', '冒险', '枪战', '悬疑', '惊悚', '经典', '青春',
                 '文艺', '微电影', '古装', '历史', '运动', '农村', '儿童', '网络电影'],
    'juji': ['古装', '战争', '青春偶像', '喜剧', '家庭', '犯罪', '动作', '奇幻', '剧情',
             '历史', '经典', '乡村', '情景', '商战', '网剧', '其他'],
    'zongyi': ['选秀', '情感', '访谈', '播报', '旅游', '音乐', '美食', '纪实', '曲艺',
               '生活', '游戏互动', '财经', '求职'],
    'dongman': ['情感', '科幻', '热血', '推理', '搞笑', '冒险', '萝莉', '校园', '动作',
                '机战', '运动', '战争', '少年', '少女', '社会', '原创', '亲子', '益智',
                '励志', '其他'],
}
_AREA = {
    'dianying': ['大陆', '香港', '台湾', '美国', '法国', '英国', '日本', '韩国', '德国',
                 '泰国', '印度', '意大利', '西班牙', '加拿大', '其他'],
    'juji': ['内地', '韩国', '香港', '台湾', '日本', '美国', '泰国', '英国', '新加坡', '其他'],
    'zongyi': ['内地', '港台', '日韩', '欧美'],
    'dongman': ['国产', '日本', '欧美', '其他'],
}
_LANG = {
    'dianying': ['国语', '英语', '粤语', '闽南语', '韩语', '日语', '法语', '德语', '其它'],
    'juji': ['国语', '英语', '粤语', '闽南语', '韩语', '日语', '其它'],
    'zongyi': ['国语', '英语', '粤语', '闽南语', '韩语', '日语', '其它'],
    'dongman': ['国语', '英语', '粤语', '闽南语', '韩语', '日语', '其它'],
}
_YEAR = {
    'dianying': ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018',
                 '2017', '2016', '2015', '2014', '2013', '2012', '2011', '2010'],
    'juji': ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018',
             '2017', '2016', '2015', '2014', '2013', '2012', '2011', '2010', '2009',
             '2008', '2006', '2005', '2004'],
    'zongyi': ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018',
               '2017', '2016', '2015', '2014', '2013', '2012', '2011', '2010', '2009',
               '2008', '2007', '2006', '2005', '2004'],
    'dongman': ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018',
                '2017', '2016', '2015', '2014', '2013', '2012', '2011', '2010', '2009',
                '2008', '2007', '2006', '2005', '2004'],
}
_SORTS = [('time', '时间排序'), ('hits', '人气排序'), ('score', '评分排序')]


class Spider(Spider):
    def getName(self):
        return '看看鸭'

    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update(headerx)

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        return '.m3u8' in u or '.mp4' in u

    # ---------- 网络：Session + 门页自动过盾 ----------
    def _get(self, url):
        last = None
        for _ in range(3):
            try:
                return self.session.get(url, timeout=20)
            except Exception as e:
                last = e
                time.sleep(2)
        raise last

    def _fetch(self, url):
        if not hasattr(self, 'session'):
            self.init('')
        for _ in range(3):
            r = self._get(url)
            txt = r.text
            # 门页唯一可靠特征：标题“人机验证”且含 robot.php
            if '人机验证' not in txt or 'robot.php' not in txt:
                return txt
            m = re.search(r'var token = encrypt\("([^"]+)"\)', txt)
            if not m:
                return txt
            # 关键：必须发原始字符串，dict 形式会被 URL 编码，服务器解不开
            body = 'value=' + _encrypt(url) + '&token=' + _encrypt(m.group(1))
            try:
                self.session.post(xurl + '/robot.php', data=body,
                                  headers={'Content-Type': 'application/x-www-form-urlencoded',
                                           'Referer': url}, timeout=20)
            except Exception:
                pass
            time.sleep(1)
        return self._get(url).text

    # ---------- 列表解析 ----------
    def _poster_cards(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        vods = []
        seen = set()
        for a in soup.select('a.module-poster-item.module-item'):
            href = a.get('href') or ''
            m = re.search(r'/detail/([A-Za-z0-9]+)\.html', href)
            if not m:
                continue
            code = m.group(1)
            if code in seen:
                continue
            seen.add(code)
            title = (a.get('title') or '').strip()
            if not title:
                t = a.select_one('.module-poster-item-title')
                title = t.get_text(strip=True) if t else ''
            pic = ''
            img = a.select_one('img[data-original]')
            if img:
                pic = img.get('data-original') or ''
            note = ''
            n = a.select_one('.module-item-note')
            if n:
                note = n.get_text(strip=True)
            vod = {'vod_id': code, 'vod_name': title, 'vod_pic': pic}
            if note:
                vod['vod_remarks'] = note
            vods.append(vod)
        return vods

    def homeContent(self, filter):
        filters = {}
        for tid, _name in _CATS:
            filters[tid] = [
                {'key': 'class_', 'name': '类型',
                 'value': [{'n': g, 'v': g} for g in _CLASS[tid]]},
                {'key': 'area', 'name': '地区',
                 'value': [{'n': c, 'v': c} for c in _AREA[tid]]},
                {'key': 'lang', 'name': '语言',
                 'value': [{'n': l, 'v': l} for l in _LANG[tid]]},
                {'key': 'year', 'name': '年份',
                 'value': [{'n': y, 'v': y} for y in _YEAR[tid]]},
                {'key': 'by', 'name': '排序',
                 'value': [{'n': n, 'v': v} for v, n in _SORTS]},
            ]
        return {'class': [{'type_id': tid, 'type_name': name} for tid, name in _CATS],
                'filters': filters}

    def homeVideoContent(self):
        try:
            html = self._fetch(xurl + '/')
            return {'list': self._poster_cards(html)}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)
        ext = extend or {}
        seg = [''] * 12
        seg[0] = tid
        if ext.get('area'):
            seg[1] = quote(ext['area'], safe='')
        if ext.get('by'):
            seg[2] = ext['by']
        if ext.get('class_'):
            seg[3] = quote(ext['class_'], safe='')
        if ext.get('lang'):
            seg[4] = quote(ext['lang'], safe='')
        if pg > 1:
            seg[8] = str(pg)
        if ext.get('year'):
            seg[11] = ext['year']
        url = xurl + '/show/' + '-'.join(seg) + '.html'
        try:
            html = self._fetch(url)
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 40, 'total': 0}
        vods = self._poster_cards(html)
        pagecount = 1
        # 尾页链接保留当前筛选，取其第 8 段（page 段）即总页数
        m = re.search(r'<a[^>]+href="(/show/[^"]+)"[^>]*>尾页</a>', html)
        if m:
            mm = re.match(r'/show/([^\.]+)\.html', m.group(1))
            if mm:
                sg = mm.group(1).split('-')
                if len(sg) == 12 and sg[8].isdigit():
                    pagecount = int(sg[8])
        return {'list': vods, 'page': pg, 'pagecount': pagecount,
                'limit': 40, 'total': pagecount * 40}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        code = ids[0]
        try:
            html = self._fetch(xurl + '/detail/' + code + '.html')
        except Exception:
            return {'list': []}
        soup = BeautifulSoup(html, 'html.parser')
        h1 = soup.select_one('h1')
        title = h1.get_text(strip=True) if h1 else code
        pic = ''
        for img in soup.select('img[data-original]'):
            src = img.get('data-original') or ''
            if not src:
                continue
            if (img.get('alt') or '').strip() == title:
                pic = src
                break
            if not pic:
                pic = src
        desc = ''
        md = soup.select_one('meta[name="description"]')
        if md:
            desc = (md.get('content') or '').strip()
            desc = re.sub(r'^' + re.escape(title) + r'剧情[:：]?', '', desc)
        director = actor = remarks = year = ''
        for m in re.finditer(
                r'<span class="module-info-item-title">([^<]+)</span>\s*'
                r'<div class="module-info-item-content">(.*?)</div>', html, re.S):
            k = m.group(1).strip()
            v = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if k.startswith('导演'):
                director = re.sub(r'/+', ',', v).strip(',')
            elif k.startswith('主演'):
                actor = re.sub(r'/+', ',', v).strip(',')
            elif k.startswith('集数'):
                remarks = v
            elif k.startswith('上映'):
                ym = re.search(r'(20\d\d)', v)
                if ym:
                    year = ym.group(1)
        # 线路 tab 按顺序对应 sid
        tab_names = []
        for tab in soup.select('div.module-tab-item.tab-item'):
            nm = tab.get('data-dropdown-value') or ''
            if not nm:
                sp = tab.select_one('span')
                nm = sp.get_text(strip=True) if sp else ''
            if nm:
                tab_names.append(nm)
        by_sid = {}
        for a in soup.select('a.module-play-list-link'):
            href = a.get('href') or ''
            m = re.search(r'/play/[A-Za-z0-9]+-(\d+)-(\d+)\.html', href)
            if not m:
                continue
            sid, nid = int(m.group(1)), int(m.group(2))
            sp = a.select_one('span')
            ep = sp.get_text(strip=True) if sp else ''
            if not ep:
                ep = re.sub(r'^播放' + re.escape(title), '', (a.get('title') or '').strip())
            if not ep:
                ep = '第%02d集' % nid
            by_sid.setdefault(sid, {})[href] = (nid, ep)
        lines = []
        for i, sid in enumerate(sorted(by_sid)):
            name = tab_names[i] if i < len(tab_names) else ('线路%d' % sid)
            play = '#'.join('%s$%s' % (ep, href) for href, (nid, ep) in
                            sorted(by_sid[sid].items(), key=lambda kv: kv[1][0]))
            lines.append((name, play))
        # 简介前加统一前缀
        if desc:
            desc = INTRO_PREFIX + '\n' + desc
        else:
            desc = INTRO_PREFIX
        vod = {'vod_id': code, 'vod_name': title, 'vod_pic': pic,
               'vod_remarks': remarks, 'vod_content': desc}
        if director:
            vod['vod_director'] = director
        if actor:
            vod['vod_actor'] = actor
        if year:
            vod['vod_year'] = year
        if lines:
            vod['vod_play_from'] = '$$$'.join(nm for nm, _p in lines)
            vod['vod_play_url'] = '$$$'.join(p for _nm, p in lines)
        return {'list': [vod]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vip_flags):
        play_url = id if id.startswith('http') else urljoin(xurl + '/', id.lstrip('/'))
        try:
            html = self._fetch(play_url)
        except Exception:
            return {'parse': 1, 'url': play_url}
        # var player_aaaa = {...}（嵌套对象，大括号深度匹配）
        i = html.find('var player_aaaa=')
        url = ''
        if i != -1:
            start = html.find('{', i)
            depth = 0
            instr = False
            esc = False
            end = -1
            for j in range(start, len(html)):
                ch = html[j]
                if instr:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == '"':
                        instr = False
                else:
                    if ch == '"':
                        instr = True
                    elif ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end = j + 1
                            break
            if end != -1:
                try:
                    d = json.loads(html[start:end])
                    url = d.get('url') or ''
                    enc = str(d.get('encrypt', '0'))
                    if enc == '1':
                        url = unquote(url)
                    elif enc == '2':
                        try:
                            url = unquote(base64.b64decode(
                                url + '=' * (-len(url) % 4)).decode('utf-8', 'ignore'))
                        except Exception:
                            pass
                except Exception:
                    url = ''
        if not url:
            return {'parse': 1, 'url': play_url}
        if '.m3u8' in url or '.mp4' in url:
            return {'parse': 0, 'url': url,
                    'header': {'Referer': play_url, 'User-Agent': headerx['User-Agent']}}
        # vid → api.php → 按 urlmode 解码 → 直链，失败才回退嗅探
        real = self._resolve_kky(url, play_url)
        if real:
            return {'parse': 0, 'url': real,
                    'header': {'Referer': play_url, 'User-Agent': headerx['User-Agent']}}
        return {'parse': 1, 'url': xurl + '/kkyplayer/index.php?vid=' + url,
                'header': {'Referer': play_url, 'User-Agent': headerx['User-Agent']}}

    def _resolve_kky(self, vid, play_url):
        if not hasattr(self, 'session'):
            self.init('')
        try:
            r = self.session.post(xurl + '/kkyplayer/api.php', data={'vid': vid},
                                  headers={'Referer': xurl + '/kkyplayer/index.php?vid=' + vid},
                                  timeout=20)
            d = (r.json().get('data') or {})
            du = d.get('url') or ''
            if not du:
                return ''
            if d.get('urlmode') == 1:
                real = _decode_kky1(du)
            elif d.get('urlmode') == 2:
                real = _decode_kky2(du)
            else:
                return ''
            return real if real.startswith('http') else ''
        except Exception:
            return ''

    # ---------- 搜索 ----------
    def searchContentPage(self, key, pg):
        pg = int(pg)
        url = xurl + '/search/-------------.html?wd=' + quote(key)
        if pg > 1:
            url += '&page=%d' % pg
        try:
            html = self._fetch(url)
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0}
        soup = BeautifulSoup(html, 'html.parser')
        vods = []
        seen = set()
        for item in soup.select('div.module-card-item.module-item'):
            a = item.select_one('a.module-card-item-poster')
            if not a:
                continue
            href = a.get('href') or ''
            m = re.search(r'/detail/([A-Za-z0-9]+)\.html', href)
            if not m:
                continue
            code = m.group(1)
            if code in seen:
                continue
            seen.add(code)
            title = ''
            t = item.select_one('.module-card-item-title')
            if t:
                title = t.get_text(strip=True)
            pic = ''
            img = item.select_one('img[data-original]')
            if img:
                pic = img.get('data-original') or ''
            note = ''
            n = item.select_one('.module-item-note')
            if n:
                note = n.get_text(strip=True)
            vod = {'vod_id': code, 'vod_name': title, 'vod_pic': pic}
            if note:
                vod['vod_remarks'] = note
            vods.append(vod)
        pagecount = 1
        m = re.search(r'/search/' + re.escape(quote(key)) + r'----------(\d+)---\.html[^>]*>尾页<', html)
        if m:
            pagecount = int(m.group(1))
        return {'list': vods, 'page': pg, 'pagecount': pagecount,
                'limit': 20, 'total': pagecount * 20}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, 1)

    def localProxy(self, param):
        return [200, 'video/mpeg', '', '']



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = []
_TVBOX_LINE_ORDER = ["地址3", "地址4", "地址8"]

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
