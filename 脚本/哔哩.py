"""
哔哩哔哩TVBox爬虫
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
        
        # 获取Cookie并初始化
        cookie = self._get_cookie_from_config()
        normalized_cookie = self._normalize_cookie(cookie)
        _, _, _ = self.getCookie(normalized_cookie)
        bblogin = self.getCache("bblogin")
        
        result["class"] = [] if bblogin else []
        
        # 处理分类配置
        if "json" in self.extendDict:
            r = self.fetch(self.extendDict["json"], timeout=10)
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
        url = "https://api.bilibili.com/x/web-interface/index/top/feed/rcmd?y_num=1&fresh_type=3&feed_version=SEO_VIDEO&fresh_idx_1h=1&fetch_row=1&fresh_idx=1&brush=0&homepage_ver=1&ps=20"
        
        try:
            r = self._fetch_with_cookie(url, timeout=5)
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
                    
                result["list"].append({
                    "vod_id": aid,
                    "vod_name": title,
                    "vod_pic": img,
                    "vod_remarks": remark,
                })
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
        
        # 获取Cookie信息
        cookie = self._get_cookie_from_config()
        normalized_cookie = self._normalize_cookie(cookie)
        cookie_dict, imgKey, subKey = self.getCookie(normalized_cookie)
        
        try:
            if tid.startswith("UP主&&&"):
                videos, pagecount = self._get_up_videos(tid[6:], page, cookie_dict, imgKey, subKey)
            else:
                videos, pagecount = self._get_search_videos(tid, page, extend, cookie_dict)
        except Exception as e:
            self.log(f"分类内容获取失败: {e}")
            videos = []
            pagecount = page
            
        # 构建返回结果
        lenvideos = len(videos)
        result.update({
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": lenvideos,
            "total": lenvideos
        })
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
        
        if aid.startswith("UP主&&&"):
            return self._get_up_playlist(aid[6:])
            
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
            r = self.fetch(url, headers=self.header, timeout=10)
            data = json.loads(self.cleanText(r.text))
            
            # 处理导演信息
            if "staff" in data["data"]:
                director = ""
                for staff in data["data"]["staff"]:
                    director += '[a=cr:{{"id":"UP主&&&{}","name":"{}"}}/]{}[/a],'.format(
                        staff["mid"], staff["name"], staff["name"]
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
                "vod_year": datetime.fromtimestamp(data["data"]["pubdate"]).strftime("%Y-%m-%d %H:%M:%S"),
                "vod_content": data["data"]["desc"].replace("\xa0", " ").replace("\n\n", "\n").strip(),
                "vod_director": director,
            }
            
            # 处理播放链接
            videoList = data["data"]["pages"]
            playUrl = ""
            for video in videoList:
                remark = time.strftime("%H:%M:%S", time.gmtime(video["duration"]))
                name = self.removeHtmlTags(video["part"]).strip().replace("#", "-").replace("$", "*")
                if remark.startswith("00:"):
                    remark = remark[3:]
                playUrl = playUrl + f"[{remark}]/{name}${aid}_{video['cid']}#"
            
            # 添加相关视频
            url = f"https://api.bilibili.com/x/web-interface/archive/related?aid={aid}"
            r = self.fetch(url, headers=self.header, timeout=5)
            data = json.loads(self.cleanText(r.text))
            videoList = data["data"]
            playUrl = playUrl.strip("#") + "$$$"
            
            for video in videoList:
                remark = time.strftime("%H:%M:%S", time.gmtime(video["duration"]))
                if remark.startswith("00:"):
                    remark = remark[3:]
                name = self.removeHtmlTags(video["title"]).strip().replace("#", "-").replace("$", "*")
                playUrl = playUrl + "[{}]/{}${}_{}#".format(remark, name, video["aid"], video["cid"])
            
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
            cookie = self._get_cookie_from_config()
            normalized_cookie = self._normalize_cookie(cookie)
            cookie_dict, _, _ = self.getCookie(normalized_cookie)
            
            url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={key}&page={pg}"
            r = self.fetch(url, headers=self.header, cookies=cookie_dict, timeout=5)
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
                    
                videos.append({
                    "vod_id": aid,
                    "vod_name": title,
                    "vod_pic": img,
                    "vod_remarks": remark,
                })
                
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
                url = "https://api.bilibili.com/x/web-interface/view?bvid={}".format(id[7:])
                r = self.fetch(url, headers=self.header, timeout=10)
                data = r.json()["data"]
                aid = data["aid"]
                cid = data["cid"]
            else:
                idList = id.split("_")
                aid = idList[0]
                cid = idList[1]
                
            # 获取Cookie
            cookie = self._get_cookie_from_config()
            normalized_cookie = self._normalize_cookie(cookie)
            cookiesDict, _, _ = self.getCookie(normalized_cookie)
            
            # 直接获取视频真实地址，不使用本地代理
            video_url = self._get_direct_video_url(aid, cid, cookiesDict)
            
            if video_url:
                result.update({
                    "parse": 0,
                    "playUrl": "",
                    "url": video_url,
                    "header": {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": "https://www.bilibili.com"
                    },
                    "danmaku": "https://api.bilibili.com/x/v1/dm/list.so?oid={}".format(cid)
                })
                return result
            
            return {}
            
        except Exception as e:
            self.log(f"播放内容处理失败: {e}")
            result = {}
            
        return result
    
    def _get_direct_video_url(self, aid, cid, cookies_dict):
        """
        直接获取B站视频的真实播放地址，不使用本地代理
        :param aid: 视频aid
        :param cid: 视频cid
        :param cookies_dict: Cookie字典
        :return: 视频直链URL
        """
        try:
            # 请求获取视频播放信息
            url = f"https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}&qn=120&fnval=4048&fnver=0&fourk=1"
            r = self.fetch(url, cookies=cookies_dict, headers=self.header, timeout=10)
            data = json.loads(self.cleanText(r.text))
            
            if data["code"] == 0:
                # 优先使用dash格式
                if "dash" in data["data"]:
                    dash_data = data["data"]["dash"]
                    # 选择最高清晰度的视频轨道
                    if dash_data["video"]:
                        best_video = max(dash_data["video"], key=lambda x: x["bandwidth"])
                        # 选择最好的音频轨道
                        if dash_data["audio"]:
                            best_audio = max(dash_data["audio"], key=lambda x: x["bandwidth"])
                            # 返回组合的MPD URL（如果播放器支持）
                            return self._create_mpd_url(best_video, best_audio, aid, cid, cookies_dict)
                        else:
                            return best_video["baseUrl"]
                # fallback到durl格式
                elif "durl" in data["data"] and data["data"]["durl"]:
                    return data["data"]["durl"][0]["url"]
                    
        except Exception as e:
            self.log(f"获取直链失败: {e}")
        
        return None
    
    def _create_mpd_url(self, video_info, audio_info, aid, cid, cookies_dict):
        """
        创建MPD格式的播放URL
        :param video_info: 视频信息
        :param audio_info: 音频信息
        :param aid: 视频aid
        :param cid: 视频cid
        :param cookies_dict: Cookie字典
        :return: MPD URL
        """
        try:
            # 构造简单的MPD内容
            duration = "PT0H10M0S"  # 默认10分钟，实际应该从API获取
            video_url = video_info["baseUrl"]
            audio_url = audio_info["baseUrl"]
            
            mpd_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" type="static" mediaPresentationDuration="{duration}" minBufferTime="PT2S">
  <Period>
    <AdaptationSet mimeType="video/mp4" startWithSAP="1" segmentAlignment="true">
      <Representation bandwidth="{video_info['bandwidth']}" codecs="{video_info['codecs']}" height="{video_info['height']}" id="{video_info['id']}" width="{video_info['width']}">
        <BaseURL>{video_url}</BaseURL>
        <SegmentBase indexRange="{video_info['SegmentBase']['indexRange']}">
          <Initialization range="{video_info['SegmentBase']['Initialization']}"/>
        </SegmentBase>
      </Representation>
    </AdaptationSet>
    <AdaptationSet mimeType="audio/mp4" startWithSAP="1" segmentAlignment="true">
      <Representation audioSamplingRate="44100" bandwidth="{audio_info['bandwidth']}" codecs="{audio_info['codecs']}" id="{audio_info['id']}">
        <BaseURL>{audio_url}</BaseURL>
        <SegmentBase indexRange="{audio_info['SegmentBase']['indexRange']}">
          <Initialization range="{audio_info['SegmentBase']['Initialization']}"/>
        </SegmentBase>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""
            
            # 将MPD内容进行base64编码，通过data URI方式传递
            import base64
            mpd_b64 = base64.b64encode(mpd_content.encode('utf-8')).decode('utf-8')
            return f"data:application/dash+xml;base64,{mpd_b64}"
            
        except Exception as e:
            self.log(f"创建MPD失败: {e}")
            # fallback到直接返回视频URL
            return video_info["baseUrl"]

    def localProxy(self, param):
        """
        不使用本地代理，直接返回空
        """
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
            r = self.fetch(self.extendDict["json"], timeout=10)
            if "cookie" in r.json():
                cookie = r.json()["cookie"]
        
        if cookie == "":
            return "{}"
        elif isinstance(cookie, str) and cookie.startswith("http"):
            return self.fetch(cookie, timeout=10).text.strip()
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

    def _fetch_with_cookie(self, url, **kwargs):
        """带Cookie的网络请求封装"""
        cookie = self._get_cookie_from_config()
        normalized_cookie = self._normalize_cookie(cookie)
        cookies, _, _ = self.getCookie(normalized_cookie)
        
        headers = kwargs.pop('headers', self.header.copy())
        return self.fetch(url, cookies=cookies, headers=headers, **kwargs)

    def _get_up_videos(self, mid, page, cookie_dict, imgKey, subKey):
        """获取UP主视频"""
        params = {"mid": mid, "ps": 30, "pn": page}
        params = self.encWbi(params, imgKey, subKey)
        url = "https://api.bilibili.com/x/space/wbi/arc/search?"
        for key in params:
            url += f"&{key}={quote(params[key])}"
            
        r = self.fetch(url, cookies=cookie_dict, headers=self.header, timeout=5)
        data = json.loads(self.cleanText(r.text))
        
        pagecount = page + 1 if page < data["data"]["page"]["count"] else page
        videos = [{"vod_id": f"UP主&&&{mid}", "vod_name": "播放列表"}] if page == 1 else []
        
        vodList = data["data"]["list"]["vlist"]
        for vod in vodList:
            vid = str(vod["aid"]).strip()
            title = self.removeHtmlTags(vod["title"]).replace("&quot;", '"')
            img = vod["pic"].strip()
            
            # 处理时长格式
            remarkinfos = vod["length"].split(":")
            minutes = int(remarkinfos[0])
            if minutes >= 60:
                hours = str(minutes // 60)
                minutes = str(minutes % 60)
                if len(hours) == 1:
                    hours = "0" + hours
                if len(minutes) == 1:
                    minutes = "0" + minutes
                remark = hours + ":" + minutes + ":" + remarkinfos[1]
            else:
                remark = vod["length"]
                
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": remark,
            })
        return videos, pagecount

    def _get_search_videos(self, keyword, page, ext, cookie_dict):
        """获取搜索视频"""
        url = "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={}&page={}"
        for key in ext:
            if key == "tid":
                keyword = ext[key]
                continue
            url += f"&{key}={ext[key]}"
        url = url.format(keyword, page)
        
        r = self.fetch(url, cookies=cookie_dict, headers=self.header, timeout=5)
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
                
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": remark,
            })
        return videos, pagecount

    def _get_up_playlist(self, mid):
        """获取UP主播放列表"""
        try:
            url = f"https://api.bilibili.com/x/v2/medialist/resource/list?mobi_app=web&type=1&oid=&biz_id={mid}&otype=1&ps=100&direction=false&desc=true&sort_field=1&tid=0&with_current=false"
            r = self.fetch(url, headers=self.header, timeout=5)
            videoList = r.json()["data"]["media_list"]
            
            vod = {"vod_id": f"UP主&&&{mid}", "vod_name": "播放列表", "vod_play_from": "B站视频"}
            playUrl = ""
            
            for video in videoList:
                remark = time.strftime("%H:%M:%S", time.gmtime(video["duration"]))
                name = self.removeHtmlTags(video["title"]).strip().replace("#", "-").replace("$", "*")
                if remark.startswith("00:"):
                    remark = remark[3:]
                playUrl += f"[{remark}]/{name}$bvid&&&{video['bv_id']}#"
                
            vod["vod_play_url"] = playUrl.strip("#")
            return {"list": [vod]}
        except Exception as e:
            self.log(f"获取UP主播放列表失败: {e}")
            return {"list": []}

    def proxyMpd(self, params):
        """
        不使用MPD代理
        """
        return None

    def proxyMedia(self, params, forceRefresh=False):
        """
        不使用媒体代理
        """
        return None
    
    def getDash(self, params, forceRefresh=False):
        aid = params["aid"]
        cid = params["cid"]
        url = unquote(params["url"])
        thread = params.get("thread", 0)
        header = self.header.copy()
        cookieDict = json.loads(params["cookies"])
        key = f"bilivdmpdcache_{aid}_{cid}"
        
        if forceRefresh:
            self.delCache(key)
        else:
            data = self.getCache(key)
            if data:
                # 检查缓存是否过期
                if time.time() < data.get("expiresAt", 0):
                    return data["content"], data["dashinfos"], data["type"]
                else:
                    self.log(f"缓存已过期，重新获取: aid={aid}, cid={cid}")

        cookies = cookieDict.copy()
        # 增加超时时间，确保能获取到完整的dash信息
        r = self.fetch(url, cookies=cookies, headers=header, timeout=10)
        data = json.loads(self.cleanText(r.text))
        
        if data["code"] != 0:
            self.log(f"DASH获取失败: code={data['code']}, message={data.get('message', '')}")
            return "", {}, ""
            
        if "dash" not in data["data"]:
            purl = data["data"]["durl"][0]["url"]
            try:
                expiresAt = int(re.search(r"deadline=(\d+)", purl).group(1)) - 60
            except:
                expiresAt = int(time.time()) + 600
            if int(thread) > 0:
                try:
                    self.fetch("http://127.0.0.1:7777")
                except:
                    self.fetch("http://127.0.0.1:9978/go")
                purl = f"http://127.0.0.1:7777?url={quote(purl)}&thread={thread}"
            self.setCache(
                key,
                {
                    "content": purl,
                    "type": "mp4",
                    "dashinfos": data["data"],
                    "expiresAt": expiresAt,
                },
            )
            return purl, data["data"], "mp4"

        dashinfos = data["data"]["dash"]
        duration = dashinfos["duration"]
        minBufferTime = dashinfos["minBufferTime"]
        videoinfo = ""
        videoid = 0
        deadlineList = []
        
        # 先过滤掉AV1格式的视频流
        filtered_videos = self._filter_av1_videos(dashinfos["video"])
        
        # 再按分辨率过滤，保留最高的几个
        max_video_tracks = int(self.extendDict.get("max_video_tracks", "3"))
        selected_videos = self._filter_video_tracks_by_resolution(filtered_videos, max_video_tracks)
        
        # 为每个视频轨道添加更详细的日志
        self.log(f"处理视频轨道: 总共{len(dashinfos['video'])}个原始轨道 -> {len(selected_videos)}个保留轨道")
        
        for i, video in enumerate(selected_videos):
            try:
                deadline_match = re.search(r"deadline=(\d+)", video["baseUrl"])
                deadline = int(deadline_match.group(1)) if deadline_match else int(time.time()) + 600
            except:
                deadline = int(time.time()) + 600
            deadlineList.append(deadline)
            codecs = video["codecs"]
            bandwidth = video["bandwidth"]
            frameRate = video["frameRate"]
            height = video["height"]
            width = video["width"]
            void = video["id"]
            vidparams = params.copy()
            vidparams["videoid"] = videoid
            
            # 使用更稳定的URL生成方式
            baseUrl = f"http://127.0.0.1:9978/proxy?do=py&type=media&cookies={quote(json.dumps(cookies))}&url={quote(url)}&aid={aid}&cid={cid}&videoid={videoid}"
            videoinfo = (
                videoinfo
                + f"""	      <Representation bandwidth="{bandwidth}" codecs="{codecs}" frameRate="{frameRate}" height="{height}" id="{void}" width="{width}">
	        <BaseURL>{baseUrl}</BaseURL>
	        <SegmentBase indexRange="{video['SegmentBase']['indexRange']}">
	        <Initialization range="{video['SegmentBase']['Initialization']}"/>
	        </SegmentBase>
	      </Representation>\n"""
            )
            videoid += 1
            
        audioinfo = ""
        # 只保留一个音频轨道（选择带宽最高的）
        selected_audio = self._filter_audio_tracks(dashinfos["audio"])
        audioid = 0
        for audio in selected_audio:
            try:
                deadline_match = re.search(r"deadline=(\d+)", audio["baseUrl"])
                deadline = int(deadline_match.group(1)) if deadline_match else int(time.time()) + 600
            except:
                deadline = int(time.time()) + 600
            deadlineList.append(deadline)
            bandwidth = audio["bandwidth"]
            codecs = audio["codecs"]
            aoid = audio["id"]
            aidparams = params.copy()
            aidparams["audioid"] = audioid
            baseUrl = f"http://127.0.0.1:9978/proxy?do=py&type=media&cookies={quote(json.dumps(cookies))}&url={quote(url)}&aid={aid}&cid={cid}&audioid={audioid}"
            audioinfo = (
                audioinfo
                + f"""	      <Representation audioSamplingRate="44100" bandwidth="{bandwidth}" codecs="{codecs}" id="{aoid}">
	        <BaseURL>{baseUrl}</BaseURL>
	        <SegmentBase indexRange="{audio['SegmentBase']['indexRange']}">
	        <Initialization range="{audio['SegmentBase']['Initialization']}"/>
	        </SegmentBase>
	      </Representation>\n"""
            )
            audioid += 1
            
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
        
        # 更新缓存中的dashinfos为过滤后的版本
        filtered_dashinfos = dashinfos.copy()
        filtered_dashinfos["video"] = selected_videos
        filtered_dashinfos["audio"] = selected_audio
        
        expiresAt = min(deadlineList) - 60 if deadlineList else int(time.time()) + 600
        self.setCache(
            key,
            {
                "type": "mpd",
                "content": mpd.replace("&", "&amp;"),
                "dashinfos": filtered_dashinfos,
                "expiresAt": expiresAt,
            },
        )
        return mpd.replace("&", "&amp;"), filtered_dashinfos, "mpd"

    def _filter_av1_videos(self, video_tracks):
        """
        过滤掉AV1格式的视频流
        :param video_tracks: 原始视频轨道列表
        :return: 过滤后的视频轨道列表（移除了AV1格式）
        """
        filtered_tracks = []
        av1_removed_count = 0
        
        for track in video_tracks:
            codecs = track.get('codecs', '').lower()
            # 检查是否包含AV1编码格式
            if 'av01' in codecs or 'av1' in codecs:
                av1_removed_count += 1
                self.log(f"移除AV1视频轨道: ID={track['id']}, 分辨率={track['width']}x{track['height']}, 编码={codecs}")
                continue
            filtered_tracks.append(track)
        
        if av1_removed_count > 0:
            self.log(f"AV1过滤: 移除了{av1_removed_count}个AV1格式视频轨道")
        
        return filtered_tracks

    def _filter_video_tracks_by_resolution(self, video_tracks, max_tracks=3):
        """
        按分辨率过滤视频轨道，保留分辨率最高的几个
        :param video_tracks: 原始视频轨道列表
        :param max_tracks: 最大保留轨道数，默认3个
        :return: 过滤后的视频轨道列表
        """
        if len(video_tracks) <= max_tracks:
            # 按分辨率降序排列后返回
            return sorted(video_tracks, key=lambda x: x['height'] * x['width'], reverse=True)
            
        # 按分辨率排序（面积），保留最高的几个
        sorted_tracks = sorted(video_tracks, key=lambda x: x['height'] * x['width'], reverse=True)
        
        # 保留分辨率最高的max_tracks个轨道
        selected_tracks = sorted_tracks[:max_tracks]
        
        # 按高度重新排序（保持清晰度顺序）
        selected_tracks.sort(key=lambda x: x['height'], reverse=True)
        
        self.log(f"视频轨道过滤: 原始{len(video_tracks)}个轨道 -> 保留{len(selected_tracks)}个轨道")
        for track in selected_tracks:
            self.log(f"保留视频轨道: ID={track['id']}, 分辨率={track['width']}x{track['height']}, 带宽={track['bandwidth']}")
            
        return selected_tracks

    def _filter_audio_tracks(self, audio_tracks):
        """
        过滤音频轨道，只保留一个最佳的
        :param audio_tracks: 原始音频轨道列表
        :return: 过滤后的音频轨道列表（只包含1个）
        """
        if not audio_tracks:
            return []
            
        # 选择带宽最高的音频轨道（音质最好的）
        best_audio = max(audio_tracks, key=lambda x: x['bandwidth'])
        
        self.log(f"音频轨道过滤: 原始{len(audio_tracks)}个轨道 -> 保留1个轨道")
        self.log(f"保留音频轨道: ID={best_audio['id']}, 带宽={best_audio['bandwidth']}, 编码={best_audio['codecs']}")
        
        return [best_audio]

    def getCookie(self, cookie):
        if "{" in cookie and "}" in cookie:
            cookies = json.loads(cookie)
        else:
            cookies = dict(
                [co.strip().split("=", 1) for co in cookie.strip(";").split(";")]
            )
        bblogin = self.getCache("bblogin")
        if bblogin:
            imgKey = bblogin["imgKey"]
            subKey = bblogin["subKey"]
            return cookies, imgKey, subKey

        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36"
        }
        r = self.fetch(
            "http://api.bilibili.com/x/web-interface/nav",
            cookies=cookies,
            headers=header,
            timeout=10,
        )
        data = json.loads(r.text)
        code = data["code"]
        if code == 0:
            imgKey = data["data"]["wbi_img"]["img_url"].rsplit("/", 1)[1].split(".")[0]
            subKey = data["data"]["wbi_img"]["sub_url"].rsplit("/", 1)[1].split(".")[0]
            self.setCache(
                "bblogin",
                {
                    "imgKey": imgKey,
                    "subKey": subKey,
                    "expiresAt": int(time.time()) + 1200,
                },
            )
            return cookies, imgKey, subKey
        r = self.fetch("https://www.bilibili.com/", headers=header, timeout=5)
        cookies = r.cookies.get_dict()
        imgKey = ""
        subKey = ""
        return cookies, imgKey, subKey

    def removeHtmlTags(self, src):
        from re import sub, compile
        clean = compile("<.*?>")
        return sub(clean, "", src)

    def encWbi(self, params, imgKey, subKey):
        from hashlib import md5
        from functools import reduce
        from urllib.parse import urlencode

        mixinKeyEncTab = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
            26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
            20, 34, 44, 52,
        ]
        orig = imgKey + subKey
        mixinKey = reduce(lambda s, i: s + orig[i], mixinKeyEncTab, "")[:32]
        params["wts"] = round(time.time())  # 添加 wts 字段
        params = dict(sorted(params.items()))  # 按照 key 重排参数
        # 过滤 value 中的 "!'()*" 字符
        params = {
            k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
            for k, v in params.items()
        }
        query = urlencode(params)  # 序列化参数
        params["w_rid"] = md5((query + mixinKey).encode()).hexdigest()  # 计算 w_rid
        return params


if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("\n-------------------获取搜索内容测试------------------------------")
    rsp2 = spider.searchContent("剑来", False, "1")
    print(rsp2)
    time.sleep(1)