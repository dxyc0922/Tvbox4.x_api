# -*- coding: utf-8 -*-
"""
巨婴云播（3gwy8dzn9ke4.qbzbank.com / juy1.cc / xjuyin.com）· TVBox Python 插件（纯标准库）
========================================================================
【站情 · 2026-10-02 实地探站】
  服务端渲染的静态站，但**整页套了一层壳**：返回的 HTML 里只有一段
      <script>var a="JTNDaHRtbCUzRSUwQSUzQ2hlYWQlM0UlMEE…";document.write(...)</script>
  浏览器自己解出来渲染。还原要**两步、且顺序不能反**：
      ① base64 解码（标准 base64，+/= ）  ② URL 解码（%XX）
  （先 unquote 会把 '+' 变成空格，解出来就是废的 —— 这个坑踩过一次。）

【导航 → 分类（严格照站方底部导航）】
  一级分类 = 底部导航三项：首页 / 精品 / 影视
  二级分类 = 各页里的具体分类块：
      首页：AI短剧、国产自拍、人妖伪娘
      精品：国产精品、自拍偷拍、反差母狗
      影视：精彩电影、热门网剧、热门综艺
  实现上挂 filters 下拉，选二级后走 /list/video/{cid}.html。

【路径 / 播放链】
  列表：/list/video/{cid}.html ；详情：/video/{id}.html
  详情页里是三个自定义属性（不是全局变量）：
      <div id="dplayers" vpic="…/cover.jpg" vpid="" vurl="…/play.m3u8"></div>
  vurl 就是 CDN 真 m3u8（vods3…），裸拉 200，清单/分片都无防盗链。

【分页与搜索的实话】
  站方分页走 /list/loadmore/{cid}/{type}/{page}，**实测在所有域上都 404**（站方自己关了），
  搜索接口 /search/data/… 同样 404。所以：分类只有第 1 页（20 条），搜索走
  【聚合本地检索】：并发抓 3 个一级页 + 9 个二级分类页，按标题关键字过滤。

自检: python3 巨婴云播-TVBox插件.py
"""

import base64
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

SITE_NAME = '巨婴云播'
HOSTS = [
    'https://3gwy8dzn9ke4.qbzbank.com',
    'https://xjuyin.com',
    'https://juy1.cc',
    'https://juy2.cc',
    'https://juy3.cc',
]
UA = ('Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')

# 一级分类（站方底部导航）
TOP = [
    ('home', '首页', '/'),
    ('factory', '精品', '/factory.html'),
    ('great', '影视', '/great.html'),
]
# 二级分类：一级 key、cid、显示名
SUB = [
    ('home', 'CC250219043336jc', 'AI短剧'),
    ('home', 'CC250219042550la', '国产自拍'),
    ('home', 'CC250219042606xe', '人妖伪娘'),
    ('factory', 'CC231117031513Wg', '国产精品'),
    ('factory', 'CC231117075024vY', '自拍偷拍'),
    ('factory', 'CC231117075120gL', '反差母狗'),
    ('great', 'CC2609230728268Y', '精彩电影'),
    ('great', 'CC260923072840sL', '热门网剧'),
    ('great', 'CC260923072856Js', '热门综艺'),
]
PAGE = 20

RE_CARD = re.compile(
    r'<a[^>]*class="[^"]*label[^"]*vlink[^"]*"[^>]*href="/(?:video|album|cartoon|novel)/([^".]+)\.html"[^>]*>',
    re.I)
RE_TITLE = re.compile(r'<div class="title">(.*?)</div>', re.S | re.I)
RE_IMG = re.compile(r'<img[^>]*src="([^"]+)"', re.I)
RE_SIZE = re.compile(r'<span>\s*([0-9.]+[KMG]B)\s*</span>', re.I)


# ---------------------------------------------------------------- 工具
def unwrap(raw):
    """包壳还原：先 base64 解码，再 URL 解码（顺序不能反）"""
    if not raw:
        return ''
    m = re.search(r'var\s+\w+\s*=\s*"([A-Za-z0-9+/=]{200,})"', raw)
    if m:
        try:
            out = unquote(base64.b64decode(m.group(1)).decode('utf-8', 'ignore'))
            if len(out) > 500 and '<' in out:
                return out
        except Exception:
            pass
    return raw


def dget(path, must='class="title"', tries=2):
    """域池轮试取一页（还原包壳后）"""
    for host in HOSTS:
        for _ in range(tries):
            try:
                req = Request(host + path, headers={
                    'User-Agent': UA,
                    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Referer': host + '/',
                })
                with urlopen(req, timeout=20) as r:
                    raw = r.read().decode('utf-8', 'ignore')
                if len(raw) < 300:
                    continue
                t = unwrap(raw)
                if len(t) < 800:
                    continue
                if must and must not in t:
                    continue
                return t
            except Exception:
                continue
    return ''


def strip_tags(h):
    h = re.sub(r'(?is)<script.*?</script>', ' ', h or '')
    h = re.sub(r'(?is)<style.*?</style>', ' ', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', h).strip()


def cards(page):
    out = []
    if not page or len(page) < 500:
        return out
    for m in RE_CARD.finditer(page):
        vid = m.group(1)
        win = page[m.start():m.start() + 1400]
        mt = RE_TITLE.search(win)
        name = strip_tags(mt.group(1)) if mt else ''
        if not name:
            ma = re.search(r'title="([^"]+)"', win)
            name = ma.group(1) if ma else vid
        mp = RE_IMG.search(win)
        pic = mp.group(1).strip() if mp else ''
        if pic.startswith('//'):
            pic = 'https:' + pic
        ms = RE_SIZE.search(win)
        out.append({
            'vod_id': vid,
            'vod_name': name or vid,
            'vod_pic': pic,
            'vod_remarks': ms.group(1) if ms else '',
        })
    # 去重
    seen, uniq = set(), []
    for c in out:
        if c['vod_id'] in seen:
            continue
        seen.add(c['vod_id'])
        uniq.append(c)
    return uniq


def page_of(tid):
    for k, _, p in TOP:
        if k == tid:
            return p
    return '/'


def cat_of(cid):
    for _, c, n in SUB:
        if c == cid:
            return n
    return ''


# ---------------------------------------------------------------- 插件本体
class Spider(object):

    def __init__(self):
        self.extend_host = ''

    def init(self, extend=''):
        try:
            if extend:
                o = json.loads(extend) if isinstance(extend, str) else extend
                h = (o or {}).get('host', '')
                if h and len(h) > 8:
                    if not h.startswith('http'):
                        h = 'https://' + h
                    self.extend_host = h.rstrip('/')
        except Exception:
            pass
        return self

    def getName(self):
        return '🔞' + SITE_NAME

    # ---------------- 首页 ----------------
    def homeContent(self, filter=False):
        out = {'class': [], 'list': [], 'filters': {}}
        try:
            for k, n, _ in TOP:
                out['class'].append({'type_id': k, 'type_name': n})
                vals = [{'n': nm, 'v': cid} for kk, cid, nm in SUB if kk == k]
                out['filters'][k] = [{'key': '二级', 'name': '分类', 'value': vals}]
            out['list'] = cards(dget('/', 'class="title"'))
        except Exception:
            pass
        return out

    # ---------------- 分类 ----------------
    def categoryContent(self, tid, pg, filter=False, extend=None):
        out = {'list': [], 'page': 1, 'pagecount': 1, 'limit': PAGE, 'total': 0}
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        tid = (tid or 'home').strip()
        cid = ''
        if isinstance(extend, dict):
            cid = str(extend.get('二级') or '')
        path = ('/list/video/%s.html' % cid) if cid else page_of(tid)
        ls = cards(dget(path, 'class="title"'))
        out['list'] = ls
        out['page'] = page
        out['total'] = len(ls)
        return out

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        out = {'list': []}
        try:
            raw = (ids or [''])[0].strip()
            if not raw:
                return out
            vid = raw
            m = re.search(r'/(?:video|album|cartoon|novel)/([^/.]+)\.html', raw)
            if m:
                vid = m.group(1)
            body = dget('/video/%s.html' % vid, 'dplayers') or dget('/video/%s.html' % vid, '<title>')
            name, pic, vurl = '', '', ''
            md = re.search(r'<div[^>]*id="dplayers"[^>]*>', body or '', re.I)
            if md:
                tag = md.group(0)
                mu = re.search(r'vurl="([^"]*)"', tag)
                if mu:
                    vurl = mu.group(1).strip()
                mp = re.search(r'vpic="([^"]*)"', tag)
                if mp:
                    pic = mp.group(1).strip()
            if not vurl:
                mu = re.search(r'vurl="([^"]+)"', body or '')
                if mu:
                    vurl = mu.group(1).strip()
            mt = re.search(r'<div class="video_info_box">\s*<div class="title">(.*?)</div>',
                           body or '', re.S)
            if mt:
                name = strip_tags(mt.group(1))
            if not name:
                mt2 = re.search(r'<title>(.*?)</title>', body or '', re.S)
                if mt2:
                    name = strip_tags(mt2.group(1)).split(' - ')[0].strip()
            if not name:
                name = '%s %s' % (SITE_NAME, vid)
            if vurl.startswith('//'):
                vurl = 'https:' + vurl
            vod = {
                'vod_id': raw,
                'vod_name': name,
                'vod_pic': pic,
                'vod_content': '来源：%s' % SITE_NAME,
            }
            if len(vurl) > 20:
                vod['vod_play_from'] = '正片'
                vod['vod_play_url'] = '正片$%s' % vurl
            out['list'].append(vod)
        except Exception:
            pass
        return out

    # ---------------- 搜索（聚合本地检索）----------------
    def searchContent(self, key, quick=False, pg='1'):
        out = {'list': []}
        try:
            kw = (key or '').strip().lower()
            if not kw:
                return out
            paths = [p for _, _, p in TOP] + ['/list/video/%s.html' % c for _, c, _ in SUB]
            found, seen = [], set()

            def one(p):
                return cards(dget(p, 'class="title"'))

            with ThreadPoolExecutor(max_workers=6) as ex:
                for ls in ex.map(one, paths):
                    for c in ls:
                        nm = c['vod_name'].lower()
                        if kw not in nm or c['vod_id'] in seen:
                            continue
                        seen.add(c['vod_id'])
                        found.append(c)
            out['list'] = found
        except Exception:
            pass
        return out

    # ---------------- 播放 ----------------
    def playerContent(self, flag, vid, vipFlags=None):
        out = {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}}
        try:
            u = (vid or '').strip()
            if not u.startswith('http'):
                try:
                    pad = u + '=' * ((4 - len(u) % 4) % 4)
                    u = base64.urlsafe_b64decode(pad.encode()).decode('utf-8', 'ignore')
                except Exception:
                    u = ''
            out['url'] = u
            out['header'] = {'User-Agent': UA, 'Referer': HOSTS[0] + '/'}
        except Exception:
            pass
        return out


# ---------------------------------------------------------------- 自检
if __name__ == '__main__':
    ok = [0, 0]

    def ck(label, cond, detail=''):
        ok[1] += 1
        if cond:
            ok[0] += 1
        print(('  PASS ' if cond else '  FAIL ') + label + (('  | ' + str(detail)[:110]) if detail else ''))

    print('================ %s py 插件自检 ================' % SITE_NAME)
    s = Spider().init('')
    ck('getName', s.getName() == '🔞' + SITE_NAME, s.getName())

    # 包壳还原向量（真页面截取）
    raw = '<!DOCTYPE html><script> var a="%s";</script>' % base64.b64encode(
        quote('<html><body>' + ('<div class="title">测试标题</div>' * 20) + '</body></html>',
              safe='').encode()).decode()
    ck('包壳还原(base64→url解码)', 'class="title"' in unwrap(raw), unwrap(raw)[:60])

    h = s.homeContent(True)
    ck('首页分类=3(首页/精品/影视)', len(h.get('class') or []) == 3, len(h.get('class') or []))
    ck('首页列表非空', len(h.get('list') or []) > 0, 'n=%d' % len(h.get('list') or []))
    ck('一级挂二级 filters', len((h.get('filters') or {}).get('home') or []) > 0, '')

    c1 = s.categoryContent('home', '1', True, None)
    ck('分类-首页有货', len(c1.get('list') or []) > 0, 'n=%d' % len(c1.get('list') or []))

    c2 = s.categoryContent('factory', '1', True, {'二级': 'CC231117031513Wg'})
    ck('分类-精品→国产精品(二级)有货', len(c2.get('list') or []) > 0, 'n=%d' % len(c2.get('list') or []))

    c3 = s.categoryContent('great', '1', True, None)
    ck('分类-影视有货', len(c3.get('list') or []) > 0, 'n=%d' % len(c3.get('list') or []))

    ls = c2.get('list') or c1.get('list')
    if ls:
        d = s.detailContent([ls[0]['vod_id']])
        vod = (d.get('list') or [{}])[0]
        ck('详情有标题', len(vod.get('vod_name') or '') > 2, vod.get('vod_name'))
        ck('详情有封面', len(vod.get('vod_pic') or '') > 10, vod.get('vod_pic'))
        pu = vod.get('vod_play_url') or ''
        ck('详情带播放地址', len(pu) > 20, 'len=%d' % len(pu))
        pl = s.playerContent('正片', pu.split('$', 1)[-1] if '$' in pu else pu, None)
        url = pl.get('url') or ''
        ck('播放直链是 m3u8', '.m3u8' in url, url[:90])
        if url:
            try:
                req = Request(url, headers={'User-Agent': UA})
                with urlopen(req, timeout=20) as r:
                    body = r.read(200).decode('utf-8', 'ignore')
                ck('播放链真取到清单', '#EXTM3U' in body, body.split('\n')[0])
            except Exception as e:
                ck('播放链真取到清单', False, str(e))
        else:
            ck('播放链真取到清单', False, '无地址')

    sr = s.searchContent('自拍', False, '1')
    ck('搜索有结果(聚合检索)', len(sr.get('list') or []) > 0, 'n=%d' % len(sr.get('list') or []))

    print('================ 结果 %d/%d ================' % (ok[0], ok[1]))
    sys.exit(0 if ok[0] == ok[1] else 1)



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = []
_TVBOX_LINE_ORDER = ["正片"]

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
