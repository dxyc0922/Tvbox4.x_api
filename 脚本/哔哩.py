import re
import sys
import json
import time
from datetime import datetime
from urllib.parse import quote, unquote
import requests
from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def getName(self):
        return "哔哩"

    def init(self, extend):
        """
        "ext": {"cookie": "file://storage/emulated/0/TV/bili_cookie.txt"}
        文件要完整路径才能正确读取cookie,可以通过浏览器F12获取cookie
        有cookie后画质提高到1080p
        """
        try:
            self.extendDict = json.loads(extend)
        except:
            self.extendDict = {}
        # 初始化请求头
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36",
            "Referer": "https://www.bilibili.com",
        }

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

    def homeContent(self, filter):
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
                {"type_name": "睡眠", "type_id": "窗白噪音"},
                {"type_name": "演唱会", "type_id": "演唱会超清"},
                {"type_name": "流行音乐", "type_id": "音乐超清"},
                {"type_name": "风景", "type_id": "风景4K"},
            ]
        return result

    def homeVideoContent(self):
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

    def categoryContent(self, cid, page, filter, ext):
        page = int(page)
        result = {"list": []}
        videos = []
        pagecount = page
        
        # 获取Cookie信息
        cookie = self._get_cookie_from_config()
        normalized_cookie = self._normalize_cookie(cookie)
        cookie_dict, imgKey, subKey = self.getCookie(normalized_cookie)
        
        try:
            if cid == "动态":
                videos, pagecount = self._get_dynamic_videos(page, cookie_dict)
            elif cid == "收藏夹":
                videos, pagecount = self._get_favorite_folders(cookie_dict)
            elif cid.startswith("fav&&&"):
                videos, pagecount = self._get_favorite_videos(cid[6:], page, cookie_dict)
            elif cid.startswith("UP主&&&"):
                videos, pagecount = self._get_up_videos(cid[6:], page, cookie_dict, imgKey, subKey)
            elif cid == "历史记录":
                videos, pagecount = self._get_history_videos(page, cookie_dict)
            else:
                videos, pagecount = self._get_search_videos(cid, page, ext, cookie_dict)
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

    def _get_dynamic_videos(self, page, cookie_dict):
        """获取动态视频"""
        if page > 1:
            offset = self.getCache("offset") or ""
            url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all?timezone_offset=-480&type=all&offset={offset}&page={page}"
        else:
            url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all?timezone_offset=-480&type=all&page={page}"
            
        r = self.fetch(url, cookies=cookie_dict, headers=self.header, timeout=5)
        data = json.loads(self.cleanText(r.text))
        self.setCache("offset", data["data"]["offset"])
        
        videos = []
        vodList = data["data"]["items"]
        pagecount = page + 1 if data["data"]["has_more"] else page
        
        for vod in vodList:
            if vod["type"] != "DYNAMIC_TYPE_AV":
                continue
            vid = str(vod["modules"]["module_dynamic"]["major"]["archive"]["aid"]).strip()
            remark = vod["modules"]["module_dynamic"]["major"]["archive"]["duration_text"].strip()
            title = self.removeHtmlTags(vod["modules"]["module_dynamic"]["major"]["archive"]["title"]).strip()
            img = vod["modules"]["module_dynamic"]["major"]["archive"]["cover"]
            
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": remark,
            })
        return videos, pagecount

    def _get_favorite_folders(self, cookie_dict):
        """获取收藏夹列表"""
        userid = self.getUserid(cookie_dict)
        if userid is None:
            return [], 0
            
        url = f"http://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={userid}&jsonp=jsonp"
        r = self.fetch(url, cookies=cookie_dict, headers=self.header, timeout=5)
        data = json.loads(self.cleanText(r.text))
        
        videos = []
        vodList = data["data"]["list"]
        
        for vod in vodList:
            videos.append({
                "vod_id": f"fav&&&{vod['id']}",
                "vod_name": vod["title"].strip(),
                "vod_pic": "https://api-lmteam.koyeb.app/files/shoucang.png",
                "vod_tag": "folder",
                "vod_remarks": vod["media_count"],
            })
        return videos, 1

    def _get_favorite_videos(self, fav_id, page, cookie_dict):
        """获取收藏夹视频"""
        url = f"http://api.bilibili.com/x/v3/fav/resource/list?media_id={fav_id}&pn={page}&ps=20&platform=web&type=0"
        r = self.fetch(url, cookies=cookie_dict, headers=self.header, timeout=5)
        data = json.loads(self.cleanText(r.text))
        
        videos = []
        pagecount = page + 1 if data["data"]["has_more"] else page
        vodList = data["data"]["medias"]
        
        for vod in vodList:
            vid = str(vod["id"]).strip()
            title = self.removeHtmlTags(vod["title"]).replace("&quot;", '"')
            img = vod["cover"].strip()
            remark = time.strftime("%H:%M:%S", time.gmtime(vod["duration"]))
            
            if remark.startswith("00:"):
                remark = remark[3:]
                
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": remark,
            })
        return videos, pagecount

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

    def _get_history_videos(self, page, cookie_dict):
        """获取历史记录"""
        url = f"http://api.bilibili.com/x/v2/history?pn={page}"
        r = self.fetch(url, cookies=cookie_dict, headers=self.header, timeout=5)
        data = json.loads(self.cleanText(r.text))
        
        pagecount = page + 1 if len(data["data"]) == 300 else page
        videos = []
        
        vodList = data["data"]
        for vod in vodList:
            if vod["duration"] <= 0:
                continue
                
            vid = str(vod["aid"]).strip()
            img = vod["pic"].strip()
            title = self.removeHtmlTags(vod["title"]).replace("&quot;", '"')
            
            if vod["progress"] != -1:
                process = time.strftime("%H:%M:%S", time.gmtime(vod["progress"]))
                totalTime = time.strftime("%H:%M:%S", time.gmtime(vod["duration"]))
                if process.startswith("00:"):
                    process = process[3:]
                if totalTime.startswith("00:"):
                    totalTime = totalTime[3:]
                remark = process + "|" + totalTime
                
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

    def detailContent(self, did):
        aid = did[0]
        
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

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg):
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

    def playerContent(self, flag, pid, vipFlags):
        result = {}
        
        try:
            if pid.startswith("bvid&&&"):
                url = "https://api.bilibili.com/x/web-interface/view?bvid={}".format(pid[7:])
                r = self.fetch(url, headers=self.header, timeout=10)
                data = r.json()["data"]
                aid = data["aid"]
                cid = data["cid"]
            else:
                idList = pid.split("_")
                aid = idList[0]
                cid = idList[1]
                
            url = "https://api.bilibili.com/x/player/playurl?avid={}&cid={}&qn=120&fnval=4048&fnver=0&fourk=1".format(aid, cid)
            
            # 获取Cookie
            cookie = self._get_cookie_from_config()
            normalized_cookie = self._normalize_cookie(cookie)
            cookiesDict, _, _ = self.getCookie(normalized_cookie)
            cookies = quote(json.dumps(cookiesDict))
            
            thread = str(self.extendDict.get("thread", "0"))
            
            result.update({
                "parse": 0,
                "playUrl": "",
                "url": f"http://127.0.0.1:9978/proxy?do=py&type=mpd&cookies={cookies}&url={quote(url)}&aid={aid}&cid={cid}&thread={thread}",
                "header": self.header,
                "danmaku": "https://api.bilibili.com/x/v1/dm/list.so?oid={}".format(cid),
                "format": "application/dash+xml"
            })
        except Exception as e:
            self.log(f"播放内容处理失败: {e}")
            result = {}
            
        return result

    def localProxy(self, params):
        try:
            if params["type"] == "mpd":
                return self.proxyMpd(params)
            elif params["type"] == "media":
                return self.proxyMedia(params)
        except Exception as e:
            self.log(f"本地代理处理失败: {e}")
        return None

    def destroy(self):
        pass

    # 以下方法保持原有实现不变
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
            if "127.0.0.1:7777" in url:
                header["Location"] = url
                return [302, "video/MP2T", None, header]
            r = requests.get(url, headers=header, stream=True)
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
        r = requests.get(url, headers=header, stream=True)
        return [206, "application/octet-stream", r.content]

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
                return data["content"], data["dashinfos"], data["type"]

        cookies = cookieDict.copy()
        r = self.fetch(url, cookies=cookies, headers=header, timeout=5)
        data = json.loads(self.cleanText(r.text))
        
        if data["code"] != 0:
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
        
        for video in dashinfos["video"]:
            try:
                deadline = int(re.search(r"deadline=(\d+)", video["baseUrl"]).group(1))
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
        audioid = 0
        for audio in dashinfos["audio"]:
            try:
                deadline = int(re.search(r"deadline=(\d+)", audio["baseUrl"]).group(1))
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
        
        expiresAt = min(deadlineList) - 60
        self.setCache(
            key,
            {
                "type": "mpd",
                "content": mpd.replace("&", "&amp;"),
                "dashinfos": dashinfos,
                "expiresAt": expiresAt,
            },
        )
        return mpd.replace("&", "&amp;"), dashinfos, "mpd"

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
        r = requests.get(
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

    def getUserid(self, cookie):
        # 获取自己的userid(cookies拥有者)
        url = "http://api.bilibili.com/x/space/myinfo"
        r = self.fetch(url, cookies=cookie, headers=self.header, timeout=5)
        data = json.loads(self.cleanText(r.text))
        if data["code"] == 0:
            return data["data"]["mid"]

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