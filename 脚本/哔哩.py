"""
请勿用于商业用途，请于24小时内删除，搜索结果均来自源站，本人不承担任何责任
"""

import re
import sys
import json
import time
from datetime import datetime
from urllib.parse import quote, unquote
from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend=""):
        """
        初始化配置文件传过来的参数
        :param extend: 来源于配置文件中的ext
        "ext": {"cookie": "file://storage/emulated/0/TV/bili_cookie.txt"}
        文件要完整路径才能正确读取cookie,可以通过浏览器F12获取cookie
        有cookie后画质提高到1080p
        """
        self.name = "哔哩哔哩"
        self.host = "https://www.bilibili.com"

        # 初始化请求头
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36",
            "Referer": "https://www.bilibili.com",
        }

        # 解析扩展配置
        try:
            self.extendDict = json.loads(extend) if extend else {}
        except:
            self.extendDict = {}

        self.cookie = self.getCookie_info()

    def getName(self):
        """
        获取插件名称
        :return: 插件名称
        """
        return self.name

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
        result = {}
        result["filters"] = {}
        result["class"] = []

        # 处理分类配置
        if "json" in self.extendDict:
            r = self.fetch(self.extendDict["json"])
            params = r.json()
            if "classes" in params:
                result["class"] = result["class"] + params["classes"]
            if filter and "filter" in params:
                result["filters"] = params["filter"]
        elif "categories" in self.extendDict or "type" in self.extendDict:
            cate_key = "categories" if "categories" in self.extendDict else "type"
            cateList = self.extendDict[cate_key].split("#")
            for cate in cateList:
                result["class"].append({"type_name": cate, "type_id": cate})

        # 设置默认分类
        if not result["class"]:
            result["class"] = [
                {"type_name": "演唱会", "type_id": "演唱会超清"},
                {"type_name": "流行音乐", "type_id": "音乐超清"},
                {"type_name": "风景", "type_id": "风景4K"},
            ]
        return result

    def getCookie_info(self):
        cookie = self._get_cookie_from_config()
        normalized_cookie = self._normalize_cookie(cookie)
        cookie_dict = self.getCookie(normalized_cookie)
        return cookie_dict

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
        result = {}

        try:
            url = "https://api.bilibili.com/x/web-interface/index/top/feed/rcmd?y_num=1&fresh_type=3&feed_version=SEO_VIDEO&fresh_idx_1h=1&fetch_row=1&fresh_idx=1&brush=0&homepage_ver=1&ps=20"

            r = self.fetch(url, headers=self.header, cookies=self.cookie)
            data = json.loads(self.cleanText(r.text))
            result["list"] = []
            vodList = data["data"]["item"]

            for vod in vodList:
                aid = str(vod["id"]).strip()
                title = self.removeHtmlTags(vod["title"]).strip()
                img = vod["pic"].strip()
                remark = time.strftime("%H:%M:%S", time.gmtime(vod["duration"]))

                if remark.startswith("00:"):
                    remark = remark[3:]
                if remark == "00:00":
                    continue

                result["list"].append(
                    {
                        "vod_id": aid,
                        "vod_name": title,
                        "vod_pic": img,
                        "vod_remarks": remark,
                    }
                )
        except Exception as e:
            self.log(f"获取首页视频失败: {e}")
            result["list"] = []

        return result

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
        page = int(pg)
        result = {"list": []}
        videos = []
        pagecount = page

        try:
            videos, pagecount = self._get_search_videos(tid, page, extend)
        except Exception as e:
            self.log(f"分类内容获取失败: {e}")
            videos = []
            pagecount = page

        # 构建返回结果
        lenvideos = len(videos)
        result.update(
            {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": lenvideos,
                "total": lenvideos,
            }
        )
        return result

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
        aid = ids[0]

        try:
            url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
            r = self.fetch(url, headers=self.header, cookies=self.cookie, timeout=10)
            data = json.loads(self.cleanText(r.text))

            # 处理导演信息
            if "staff" in data["data"]:
                director = ""
                for staff in data["data"]["staff"]:
                    director += (
                        '[a=cr:{{"id":"UP主&&&{}","name":"{}"}}/]{}[/a],'.format(
                            staff["mid"], staff["name"], staff["name"]
                        )
                    )
            else:
                director = '[a=cr:{{"id":"UP主&&&{}","name":"{}"}}/]{}[/a]'.format(
                    data["data"]["owner"]["mid"],
                    data["data"]["owner"]["name"],
                    data["data"]["owner"]["name"],
                )

            vod = {
                "vod_id": aid,
                "vod_name": self.removeHtmlTags(data["data"]["title"]),
                "vod_pic": data["data"]["pic"],
                "type_name": data["data"]["tname"],
                "vod_year": datetime.fromtimestamp(data["data"]["pubdate"]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "vod_content": data["data"]["desc"]
                .replace("\xa0", " ")
                .replace("\n\n", "\n")
                .strip(),
                "vod_director": director,
            }

            # 处理播放链接
            videoList = data["data"]["pages"]
            playUrl = ""
            for video in videoList:
                remark = time.strftime("%H:%M:%S", time.gmtime(video["duration"]))
                name = (
                    self.removeHtmlTags(video["part"])
                    .strip()
                    .replace("#", "-")
                    .replace("$", "*")
                )
                if remark.startswith("00:"):
                    remark = remark[3:]
                playUrl = playUrl + f"[{remark}]/{name}${aid}_{video['cid']}#"

            # 添加相关视频
            url = f"https://api.bilibili.com/x/web-interface/archive/related?aid={aid}"
            r = self.fetch(url, headers=self.header, cookies=self.cookie)
            data = json.loads(self.cleanText(r.text))
            videoList = data["data"]
            playUrl = playUrl.strip("#") + "$$$"

            for video in videoList:
                remark = time.strftime("%H:%M:%S", time.gmtime(video["duration"]))
                if remark.startswith("00:"):
                    remark = remark[3:]
                name = (
                    self.removeHtmlTags(video["title"])
                    .strip()
                    .replace("#", "-")
                    .replace("$", "*")
                )
                playUrl = playUrl + "[{}]/{}${}_{}#".format(
                    remark, name, video["aid"], video["cid"]
                )

            vod["vod_play_from"] = "B站视频$$$相关视频"
            vod["vod_play_url"] = playUrl.strip("#")
            return {"list": [vod]}

        except Exception as e:
            self.log(f"获取视频详情失败: {e}")
            return {"list": []}

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
        }
        """
        if quick:
            return {"list": []}

        try:
            url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={key}&page={pg}"
            r = self.fetch(url, headers=self.header, cookies=self.cookie, timeout=10)
            jo = json.loads(self.cleanText(r.text))

            if "result" not in jo["data"]:
                return {"list": []}

            videos = []
            vodList = jo["data"]["result"]

            for vod in vodList:
                aid = str(vod["aid"]).strip()
                title = self.removeHtmlTags(self.cleanText(vod["title"]))
                img = "https:" + vod["pic"].strip()

                try:
                    remarkinfo = vod["duration"].split(":")
                    minutes = int(remarkinfo[0])
                    seconds = remarkinfo[1]
                except:
                    continue

                if len(seconds) == 1:
                    seconds = "0" + seconds
                if minutes >= 60:
                    hour = str(minutes // 60)
                    minutes = str(minutes % 60)
                    if len(hour) == 1:
                        hour = "0" + hour
                    if len(minutes) == 1:
                        minutes = "0" + minutes
                    remark = f"{hour}:{minutes}:{seconds}"
                else:
                    minutes = str(minutes)
                    if len(minutes) == 1:
                        minutes = "0" + minutes
                    remark = f"{minutes}:{seconds}"

                videos.append(
                    {
                        "vod_id": aid,
                        "vod_name": title,
                        "vod_pic": img,
                        "vod_remarks": remark,
                    }
                )

            return {
                "list": videos,
                "page": pg,
                "limit": 20,
                "pagecount": 9999,
                "total": 999999,
            }
        except Exception as e:
            self.log(f"搜索内容失败: {e}")
            return {"list": []}

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
        result = {}

        try:
            if id.startswith("bvid&&&"):
                url = "https://api.bilibili.com/x/web-interface/view?bvid={}".format(
                    id[7:]
                )
                r = self.fetch(url, headers=self.header, cookies=self.cookie, timeout=10)
                data = r.json()["data"]
                aid = data["aid"]
                cid = data["cid"]
            else:
                idList = id.split("_")
                aid = idList[0]
                cid = idList[1]
            
            thread = str(self.extendDict.get("thread", "0"))

            result.update(
                {
                    "parse": 0,
                    "playUrl": "",
                    "url": f"http://127.0.0.1:9978/proxy?do=py&type=mpd&cookies={quote(self.cookie)}&url={quote(url)}&aid={aid}&cid={cid}&thread={thread}",
                    "header": self.header,
                    "danmaku": "https://api.bilibili.com/x/v1/dm/list.so?oid={}".format(
                        cid
                    ),
                    "format": "application/dash+xml",
                }
            )
            return result

        except Exception as e:
            self.log(f"播放内容处理失败: {e}")
            result = {}

        return result

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
        try:
            params = param
            if params["type"] == "mpd":
                return self.proxyMpd(params)
            elif params["type"] == "media":
                return self.proxyMedia(params)
        except Exception as e:
            self.log(f"本地代理处理失败: {e}")
        return None

    def destroy(self):
        """
        销毁实例
        """
        pass

    # 私有辅助方法
    def _get_cookie_from_config(self):
        """统一获取Cookie配置的方法"""
        cookie = ""
        if "cookie" in self.extendDict:
            cookie = self.extendDict["cookie"]
        elif "json" in self.extendDict:
            r = self.fetch(self.extendDict["json"])
            if "cookie" in r.json():
                cookie = r.json()["cookie"]

        if cookie == "":
            return "{}"
        elif isinstance(cookie, str) and cookie.startswith("http"):
            return self.fetch(cookie).text.strip()
        elif isinstance(cookie, str) and cookie.startswith("file://"):
            import os

            filepath = cookie[6:]  # 移除 "file://" 前缀
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read().strip()
            else:
                self.log(f"Cookie file not found: {filepath}")
                return "{}"
        return cookie

    def _normalize_cookie(self, cookie):
        """标准化Cookie格式"""
        try:
            if isinstance(cookie, dict):
                return json.dumps(cookie, ensure_ascii=False)
        except:
            pass
        return cookie

    def _get_search_videos(self, keyword, page, ext):
        """获取搜索视频"""
        url = "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={}&page={}"
        for key in ext:
            if key == "tid":
                keyword = ext[key]
                continue
            url += f"&{key}={ext[key]}"
        url = url.format(keyword, page)

        r = self.fetch(url, cookies=self.cookie, headers=self.header, timeout=10)
        data = json.loads(self.cleanText(r.text))

        pagecount = data["data"]["numPages"]
        videos = []
        vodList = data["data"]["result"]

        for vod in vodList:
            if vod["type"] != "video":
                continue

            vid = str(vod["aid"]).strip()
            title = self.removeHtmlTags(self.cleanText(vod["title"]))
            img = "https:" + vod["pic"].strip()

            # 处理时长格式
            remarkinfo = vod["duration"].split(":")
            minutes = int(remarkinfo[0])
            seconds = remarkinfo[1]

            if len(seconds) == 1:
                seconds = "0" + seconds
            if minutes >= 60:
                hour = str(minutes // 60)
                minutes = str(minutes % 60)
                if len(hour) == 1:
                    hour = "0" + hour
                if len(minutes) == 1:
                    minutes = "0" + minutes
                remark = f"{hour}:{minutes}:{seconds}"
            else:
                minutes = str(minutes)
                if len(minutes) == 1:
                    minutes = "0" + minutes
                remark = f"{minutes}:{seconds}"

            videos.append(
                {
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": img,
                    "vod_remarks": remark,
                }
            )
        return videos, pagecount

    def proxyMpd(self, params):
        content, durlinfos, mediaType = self.getDash(params)
        if mediaType == "mpd":
            return [200, "application/dash+xml", content]
        else:
            url = ""
            urlList = (
                [content] + durlinfos["durl"][0]["backup_url"]
                if "backup_url" in durlinfos["durl"][0]
                and durlinfos["durl"][0]["backup_url"]
                else [content]
            )
            for url in urlList:
                if "mcdn.bilivideo.cn" not in url:
                    break
            header = self.header.copy()
            if "range" in params:
                header["Range"] = params["range"]
            r = self.fetch(
                url, headers=self.header, stream=True
            )
            return [206, "application/octet-stream", r.content]

    def proxyMedia(self, params, forceRefresh=False):
        _, dashinfos, _ = self.getDash(params)
        if "videoid" in params:
            videoid = int(params["videoid"])
            dashinfo = dashinfos["video"][videoid]
        elif "audioid" in params:
            audioid = int(params["audioid"])
            dashinfo = dashinfos["audio"][audioid]
        else:
            return [404, "text/plain", ""]
        url = ""
        urlList = (
            [dashinfo["baseUrl"]] + dashinfo["backupUrl"]
            if "backupUrl" in dashinfo and dashinfo["backupUrl"]
            else [dashinfo["baseUrl"]]
        )
        for url in urlList:
            if "mcdn.bilivideo.cn" not in url:
                break
        if url == "":
            return [404, "text/plain", ""]
        header = self.header.copy()
        if "range" in params:
            header["Range"] = params["range"]
        r = self.fetch(
            url, headers=self.header, stream=True
        )
        return [206, "application/octet-stream", r.content]

    def getDash(self, params, forceRefresh=False):
        # 从参数中提取视频aid（av号）
        aid = params["aid"]
        # 从参数中提取视频cid（分P编号）
        cid = params["cid"]
        # 解码URL参数，获取原始播放地址
        url = unquote(params["url"])
        # 复制请求头信息
        header = self.header.copy()
        # 解析cookie字符串为字典格式
        cookieDict = json.loads(params["cookies"])
        # 复制cookie字典
        cookies = cookieDict.copy()
        # 发送HTTP请求获取视频播放信息
        r = self.fetch(url, cookies=cookies, headers=header)
        # 解析响应JSON数据并清理文本
        data = json.loads(self.cleanText(r.text))

        # 如果API返回错误码，直接返回空结果
        if data["code"] != 0:
            return "", {}, ""

        # 如果响应数据中不包含DASH格式信息（可能是普通MP4格式）
        if "dash" not in data["data"]:
            # 获取普通播放地址
            purl = data["data"]["durl"][0]["url"]
            # 返回普通MP4格式的播放信息
            return purl, data["data"], "mp4"

        # 提取DASH格式的视频信息
        dashinfos = data["data"]["dash"]
        # 获取视频总时长（秒）
        duration = dashinfos["duration"]
        # 获取最小缓冲时间
        minBufferTime = dashinfos["minBufferTime"]
        # 初始化视频信息XML字符串
        videoinfo = ""
        # 视频轨道ID计数器
        videoid = 0
        # 存储所有资源过期时间的列表
        deadlineList = []

        # 遍历处理每个视频轨道
        for video in dashinfos["video"]:
            # 提取视频资源的过期时间
            try:
                deadline = int(re.search(r"deadline=(\d+)", video["baseUrl"]).group(1))
            except:
                # 如果无法提取，则设置默认10分钟有效期
                deadline = int(time.time()) + 600
            # 将过期时间添加到列表中
            deadlineList.append(deadline)
            # 提取视频编码信息
            codecs = video["codecs"]
            # 提取带宽信息
            bandwidth = video["bandwidth"]
            # 提取帧率信息
            frameRate = video["frameRate"]
            # 提取视频高度
            height = video["height"]
            # 提取视频宽度
            width = video["width"]
            # 提取视频轨道ID
            void = video["id"]
            # 复制参数字典
            vidparams = params.copy()
            # 添加视频轨道ID参数
            vidparams["videoid"] = videoid
            # 构造代理服务器URL，用于视频流媒体传输
            baseUrl = f"http://127.0.0.1:9978/proxy?do=py&type=media&cookies={quote(json.dumps(cookies))}&url={quote(url)}&aid={aid}&cid={cid}&videoid={videoid}"
            # 构建视频轨道的MPD XML描述信息
            videoinfo = (
                videoinfo
                + f"""	      <Representation bandwidth="{bandwidth}" codecs="{codecs}" frameRate="{frameRate}" height="{height}" id="{void}" width="{width}">
	        <BaseURL>{baseUrl}</BaseURL>
	        <SegmentBase indexRange="{video['SegmentBase']['indexRange']}">
	        <Initialization range="{video['SegmentBase']['Initialization']}"/>
	        </SegmentBase>
	      </Representation>\n"""
            )
            # 视频轨道ID递增
            videoid += 1

        # 初始化音频信息XML字符串
        audioinfo = ""
        # 音频轨道ID计数器
        audioid = 0
        # 遍历处理每个音频轨道
        for audio in dashinfos["audio"]:
            # 提取音频资源的过期时间
            try:
                deadline = int(re.search(r"deadline=(\d+)", audio["baseUrl"]).group(1))
            except:
                # 如果无法提取，则设置默认10分钟有效期
                deadline = int(time.time()) + 600
            # 将过期时间添加到列表中
            deadlineList.append(deadline)
            # 提取音频带宽信息
            bandwidth = audio["bandwidth"]
            # 提取音频编码信息
            codecs = audio["codecs"]
            # 提取音频轨道ID
            aoid = audio["id"]
            # 复制参数字典
            aidparams = params.copy()
            # 添加音频轨道ID参数
            aidparams["audioid"] = audioid
            # 构造代理服务器URL，用于音频流媒体传输
            baseUrl = f"http://127.0.0.1:9978/proxy?do=py&type=media&cookies={quote(json.dumps(cookies))}&url={quote(url)}&aid={aid}&cid={cid}&audioid={audioid}"
            # 构建音频轨道的MPD XML描述信息
            audioinfo = (
                audioinfo
                + f"""	      <Representation audioSamplingRate="44100" bandwidth="{bandwidth}" codecs="{codecs}" id="{aoid}">
	        <BaseURL>{baseUrl}</BaseURL>
	        <SegmentBase indexRange="{audio['SegmentBase']['indexRange']}">
	        <Initialization range="{audio['SegmentBase']['Initialization']}"/>
	        </SegmentBase>
	      </Representation>\n"""
            )
            # 音频轨道ID递增
            audioid += 1

        # 构造完整的MPD（Media Presentation Description）XML文档
        mpd = f"""<?xml version="1.0" encoding="UTF-8"?>
	<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" type="static" mediaPresentationDuration="PT{duration}S" minBufferTime="PT{minBufferTime}S">
	  <Period>
	    <AdaptationSet mimeType="video/mp4" startWithSAP="1" scanType="progressive" segmentAlignment="true">
	      {videoinfo.strip()}
	    </AdaptationSet>
	    <AdaptationSet mimeType="audio/mp4" startWithSAP="1" segmentAlignment="true" lang="und">
	      {audioinfo.strip()}
	    </AdaptationSet>
	  </Period>
	</MPD>"""

        # 返回处理后的DASH播放信息
        return mpd.replace("&", "&amp;"), dashinfos, "mpd"

    def getCookie(self, cookie):
        if "{" in cookie and "}" in cookie:
            cookies = json.loads(cookie)
        else:
            cookies = dict(
                [co.strip().split("=", 1) for co in cookie.strip(";").split(";")]
            )
        # header = {
        #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36"
        # }
        # r = self.fetch(
        #     "http://api.bilibili.com/x/web-interface/nav",
        #     cookies=cookies,
        #     headers=header,
        # )
        # data = json.loads(r.text)
        # code = data["code"]
        # if code == 0:
        #     imgKey = data["data"]["wbi_img"]["img_url"].rsplit("/", 1)[1].split(".")[0]
        #     subKey = data["data"]["wbi_img"]["sub_url"].rsplit("/", 1)[1].split(".")[0]
        #     return cookies, imgKey, subKey
        # cookies = ""
        # imgKey = ""
        # subKey = ""
        return cookies

    def removeHtmlTags(self, src):
        from re import sub, compile

        clean = compile("<.*?>")
        return sub(clean, "", src)


if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("\n-------------------获取搜索内容测试------------------------------")
    rsp2 = spider.searchContent("剑来", False, "1")
    print(rsp2)
    time.sleep(1)
