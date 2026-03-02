import re
import os
import json
import time
import requests
from lxml import etree
from abc import abstractmethod, ABCMeta
from importlib.machinery import SourceFileLoader
from base.localProxy import Proxy


class Spider(metaclass=ABCMeta):
    _instance = None

    def __init__(self):
        self.extend = ""

    def __new__(cls, *args, **kwargs):
        if cls._instance:
            return cls._instance
        else:
            cls._instance = super().__new__(cls)
            return cls._instance

    @abstractmethod
    def init(self, extend=""):
        """
        初始化配置文件传过来的参数
        :param extend: 来源于配置文件中的ext
        """
        pass

    def homeContent(self, filter):
        """
        获取分类列表
        :param filter: 表示是否需要返回filters,True表示需要,False表示不需要,默认为True
        :return: 示例
        {
            "class": [
                {
                    "type_id": "1", "type_name": "电影"
                }
            ],
            filters: {
                "1": [
                    {
                        "key": "type",
                        "name": "类型",
                        "value": [
                            {"n": "动作", "v": "2"}
                        ]
                    }
                ]
            },
            api如果有完整的list数组可以直接使用,而不需要再调用homeVideoContent方法获取首页推荐
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ]
        }
        """
        pass

    def homeVideoContent(self):
        """
        获取首页推荐内容,如果homeContent方法返回了list数组,则该方法可以不用实现
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ]
        }
        """
        pass

    def categoryContent(self, tid, pg, filter, extend):
        """
        获取分类列表内容
        :param tid: 类型id,来源于homeContent的class数组中的type_id
        :param pg: 页数,来源于app翻页操作
        :param filter: 是否开启筛选,来源于app筛选操作
        :param extend: 扩展参数,来源于app筛选操作,选中的筛选项会传过来{"type":"2"}
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ],
            如果api有提供可以写入,不写入也没影响
            "page": 当前页数,
            "limit": 每页显示数量,
            "pagecount": 总页数=总数/每页数量
            "total": 总数
        }
        """
        pass

    def detailContent(self, ids):
        """
        获取视频详情
        :param ids: 视频id组,来源于app点击视频进入详情页,会带上vod_id参数,使用ids[0]获取
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "视频id(不显示)", # 示例:1
                    "vod_name": "视频名称(显示)", # 示例:申肖克的救赎
                    "vod_pic": "视频封面(显示)", # 示例:https://example.com/cover.jpg
                    "vod_remarks": "备注(显示)", # 示例:更新至第10集
                    "vod_year": "年份(显示)", # 示例:2023
                    "vod_area": "地区(显示)", # 示例:中国大陆
                    "vod_actor": "主演(显示)", # 示例:张三,李四,王五
                    "vod_director": "导演(显示)", # 示例:赵六
                    "vod_content": "视频简介(显示)", # 示例:这是一个精彩的视频...
                    "vod_score": "评分(显示)", # 示例:9.5
                    "type_name": "分类名称(显示)", # 示例:电影
                    "vod_play_from": "播放来源(显示)", # 示例:线路1$$$线路2
                    "vod_play_url": "播放地址(显示)" # 示例:第1集$http://example.com/video1.mp4#第2集$http://example.com/video2.mp4$$$第1集$http://backup.com/video1.mp4"
                }
            ]
        }
        """
        pass

    def searchContent(self, key, quick, pg="1"):
        """
        获取搜索内容
        :param key: 搜索关键字
        :param quick: 是否是快捷搜索,True表示是,False表示否,默认为True
        :param pg: 页数,来源于app翻页操作,默认1
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ],
            如果api有提供可以写入,不写入也没影响
            "page": 当前页数,
            "limit": 每页显示数量,
            "pagecount": 总页数=总数/每页数量
            "total": 总数
        """
        pass

    def playerContent(self, flag, id, vipFlags):
        """
        :param flag: 视频标识,来源于detailContent的vod_play_from
        :param id: 视频id来源于detailContent的vod_play_url
        :param vipFlags: 默认是空的,应该是猫影视vip会员的标识
        :return: {
            "parse": 表示是否调用配置中的parses解析,0表示不需要,1表示需要
            "playUrl": 表示是否需要在url前面添加播放器地址,示例:http://example.com/player.html?url=
            "url": 表示视频播放地址
            "jx": 表示播放器是否显示解析列表,0表示不需要,1表示需要
            "header": 表示是否需要添加请求头,触发防盗链时添加
        }
        """
        pass

    def liveContent(self, url):
        """
        获取直播内容
        :param url: 直播地址
        :return: 直播相关数据
        """
        pass

    def localProxy(self, param):
        """
        如果播放器返回的内容带上本地代理前缀,则自动调用该方法处理
        :param param: 接收的参数{"url": "http://example.com/live.m3u8"}
        :return: 示例
        [
            200, # 状态码
            "application/vnd.apple.mpegurl", # 返回的m3u8类型
            [xxx.m3u], # 处理后的内容,比如去广告后m3u8数据
            {"User-Agent":"xxx"}, # 响应头
            False, # 是否为base64编码,默认否
        ]
        """
        pass

    def isVideoFormat(self, url):
        """
        manualVideoCheck方法返回True时调用该方法判断是否是视频格式
        :param url: 链接地址
        :return: True表示是视频格式,False表示不是视频格式
        """
        pass

    def manualVideoCheck(self):
        """
        手动检测视频格式,项目自带了自动检测,如果视频格式十分特殊需要自定义判断,请实现该方法
        :return: True表示调用isVideoFormat手动检查,False表示自动检测
        """
        pass

    def action(self, action):
        """
        :param action: 执行动作,下面示例请求传过来
        http://127.0.0.1:9978/action(动作)
        {
            do: control(控制)
            type: stop(停止),prev(上一个),next(下一个),loop(循环),play(播放),pause(暂停),replay(重播)
        }
        {
            do: refresh(刷新)
            type: detail(详情),player(播放),live(直播),subtitle(推送字幕),danmaku(推送弹幕)
            path: http://example.com/xxx.m3u8
        }
        http://127.0.0.1:9978/cache(缓存):
        {
            do: set(新增)
            key: xxx
            value: xxx
        }
        {
            do: get(获取)
            key: xxx
        }
        {
            do: del(删除)
            key: xxx
        }
        """
        pass

    def destroy(self):
        """
        销毁实例
        """
        pass

    def getName(self):
        """
        获取插件名称
        :return: 插件名称
        """
        pass

    def getDependence(self):
        """
        获取依赖关系
        :return: 依赖列表
        """
        return []

    def loadSpider(self, name):
        """
        加载其他爬虫插件
        :param name: 插件名称
        :return: 爬虫实例
        """
        return self.loadModule(name).Spider()

    def loadModule(self, name):
        """
        动态加载模块
        :param name: 模块名称
        :return: 加载的模块
        """
        path = os.path.join(os.path.join("../plugin"), f"{name}.py")
        return SourceFileLoader(name, path).load_module()

    def regStr(self, reg, src, group=1):
        """
        正则表达式匹配
        :param reg: 正则表达式
        :param src: 源字符串
        :param group: 分组编号,默认为1
        :return: 匹配结果
        """
        m = re.search(reg, src)
        src = ""
        if m:
            src = m.group(group)
        return src

    def removeHtmlTags(self, src):
        """
        移除HTML标签
        :param src: 源字符串
        :return: 清理后的字符串
        """
        clean = re.compile("<.*?>")
        return re.sub(clean, "", src)

    def cleanText(self, src):
        """
        清理文本中的表情符号
        :param src: 源字符串
        :return: 清理后的字符串
        """
        clean = re.sub(
            "[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f1e0-\U0001f1ff]",
            "",
            src,
        )
        return clean

    def fetch(
        self,
        url,
        params=None,
        cookies=None,
        headers=None,
        timeout=5,
        verify=True,
        stream=False,
        allow_redirects=True,
    ):
        """
        发送GET请求
        :param url: 请求地址
        :param params: 请求参数
        :param cookies: cookies
        :param headers: 请求头
        :param timeout: 超时时间,默认5秒
        :param verify: 是否验证SSL证书
        :param stream: 是否流式传输
        :param allow_redirects: 是否允许重定向
        :return: 响应对象
        """
        rsp = requests.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=timeout,
            verify=verify,
            stream=stream,
            allow_redirects=allow_redirects,
        )
        rsp.encoding = "utf-8"
        return rsp

    def _clean_header_value(self, value):
        """
        清理请求头值
        :param value: 请求头值
        :return: 清理后的值
        """
        cleaned = value.strip()
        if cleaned.startswith("<!DOCTYPE html>"):
            cleaned = "DefaultValue"  # 根据需求替换为合适的默认值
        return cleaned

    def post(
        self,
        url,
        params=None,
        data=None,
        json=None,
        cookies=None,
        headers=None,
        timeout=5,
        verify=True,
        stream=False,
        allow_redirects=True,
    ):
        """
        发送POST请求
        :param url: 请求地址
        :param params: URL参数
        :param data: 表单数据
        :param json: JSON数据
        :param cookies: cookies
        :param headers: 请求头
        :param timeout: 超时时间,默认5秒
        :param verify: 是否验证SSL证书
        :param stream: 是否流式传输
        :param allow_redirects: 是否允许重定向
        :return: 响应对象
        """
        # 如果 headers 不为 None，则对其进行预处理
        if headers:
            headers = {k: self._clean_header_value(v) for k, v in headers.items()}

        rsp = requests.post(
            url,
            params=params,
            data=data,
            json=json,
            cookies=cookies,
            headers=headers,
            timeout=timeout,
            verify=verify,
            stream=stream,
            allow_redirects=allow_redirects,
        )
        rsp.encoding = "utf-8"
        return rsp

    def html(self, content):
        """
        解析HTML内容
        :param content: HTML内容
        :return: etree对象
        """
        return etree.HTML(content)

    def str2json(str):
        """
        字符串转JSON
        :param str: JSON字符串
        :return: JSON对象
        """
        return json.loads(str)

    def json2str(str):
        """
        JSON转字符串
        :param str: JSON对象
        :return: JSON字符串
        """
        return json.dumps(str, ensure_ascii=False)

    def getProxyUrl(self, local=True):
        """
        获取代理URL
        :param local: 是否使用本地代理
        :return: 代理URL
        """
        return f"{Proxy.getUrl(self,local)}?do=py"

    def log(self, msg):
        """
        日志输出
        :param msg: 日志消息
        """
        if isinstance(msg, dict) or isinstance(msg, list):
            print(json.dumps(msg, ensure_ascii=False))
        else:
            print(f"{msg}")

    def getCache(self, key):
        """
        获取缓存
        :param key: 缓存键
        :return: 缓存值
        """
        value = self.fetch(
            f"http://127.0.0.1:{Proxy.getPort(self)}/cache?do=get&key={key}", timeout=5
        ).text
        if len(value) > 0:
            if (
                value.startswith("{")
                and value.endswith("}")
                or value.startswith("[")
                and value.endswith("]")
            ):
                value = json.loads(value)
                if type(value) == dict:
                    if not "expiresAt" in value or value["expiresAt"] >= int(
                        time.time()
                    ):
                        return value
                    else:
                        self.delCache(key)
                        return None
            return value
        else:
            return None

    def setCache(self, key, value):
        """
        设置缓存
        :param key: 缓存键
        :param value: 缓存值
        :return: 操作结果
        """
        if type(value) in [int, float]:
            value = str(value)
        if len(value) > 0:
            if type(value) == dict or type(value) == list:
                value = json.dumps(value, ensure_ascii=False)
        r = self.post(
            f"http://127.0.0.1:{Proxy.getPort(self)}/cache?do=set&key={key}",
            data={"value": value},
            timeout=5,
        )
        return "succeed" if r.status_code == 200 else "failed"

    def delCache(self, key):
        """
        删除缓存
        :param key: 缓存键
        :return: 操作结果
        """
        r = self.fetch(
            f"http://127.0.0.1:{Proxy.getPort(self)}/cache?do=del&key={key}", timeout=5
        )
        return "succeed" if r.status_code == 200 else "failed"