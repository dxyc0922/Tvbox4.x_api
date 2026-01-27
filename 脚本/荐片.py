# -*- coding: utf-8 -*-
"""
请勿用于商业用途，请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任
"""
import concurrent.futures
import json
import sys
import time
from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend=""):
        """
        初始化配置文件传过来的参数
        :param extend: 来源于配置文件中的ext
        """
        self.name = "荐片"
        self.host = "https://ev2089.zxbwv.com"
        self.user_agent = "Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/87.0.4280.141 Mobile Safari/537.36;webank/h5face;webank/1.0;netType:NETWORK_WIFI;appVersion:416;packageName:com.jp3.xg3"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "com.jp3.xg3",
            "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        # 初始化图片服务器地址
        self.ihost = self.imgsite()

    def getName(self):
        return self.name

    def imgsite(self):
        """获取图片服务器地址"""
        data = self.fetch(f"{self.host}/api/appAuthConfig", headers=self.headers).json()
        host = data["data"]["imgDomain"]
        return host if host.startswith("http") else f"https://{host}"

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
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ]
        }
        """
        result = {}

        # 获取分类数据
        cdata = self.fetch(
            f"{self.host}/api/term/home_fenlei", headers=self.headers
        ).json()
        # 获取首页推荐视频
        hdata = self.fetch(
            f"{self.host}/api/dyTag/hand_data",
            params={"category_id": cdata["data"][0]["id"]},
            headers=self.headers,
        ).json()

        classes = []
        filters = {}

        # 构建分类列表
        for k in cdata["data"]:
            if "abbr" in k:  # 只添加有缩写的分类
                classes.append({"type_name": k["name"], "type_id": k["id"]})

        # 并发获取各分类的筛选条件
        if filter:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(classes)
            ) as executor:
                future_to_aid = {
                    executor.submit(self.getfts, aid["type_id"]): aid["type_id"]
                    for aid in classes
                }
                for future in concurrent.futures.as_completed(future_to_aid):
                    aid = future_to_aid[future]
                    try:
                        aid_id, fts = future.result()
                        filters[aid_id] = fts
                    except Exception as e:
                        self.log(f"Error processing filter for aid {aid}: {e}")

        result["class"] = classes
        if filter:
            result["filters"] = filters

        # 构建首页推荐视频列表
        result["list"] = [
            item for i in hdata["data"].values() for item in self.build_cl(i)
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
        # 已在homeContent中实现，此方法可不实现
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
            "page": 当前页数,
            "limit": 每页显示数量,
            "pagecount": 总页数=总数/每页数量
            "total": 总数
        }
        """
        # 构建请求参数
        params = {**{"fcate_pid": tid, "page": pg}, **extend}
        # 根据tid判断使用哪个API路径
        path = "/api/crumb/shortList" if tid == "67" else "/api/crumb/list"

        url = f"{self.host}{path}"
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"分类视频列表请求失败")
            return {"list": []}

        try:
            res_json = rsp.json()
            result = {}
            # 构建视频列表
            result["list"] = self.build_cl(res_json["data"], tid)
            result["page"] = pg
            result["pagecount"] = 9999
            result["limit"] = 90
            result["total"] = 999999
            return result
        except Exception as e:
            self.log(f"分类视频列表解析失败: {e}")
            return {"list": []}

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
        ids_split = ids[0].split("@")
        vid = ids_split[0]
        tid = ids_split[-1] if len(ids_split) > 1 else ""

        # 根据视频类型选择不同的API路径和参数键名
        path, ikey = (
            ("/api/detail", "vid") if tid == "67" else ("/api/video/detailv2", "id")
        )

        url = f"{self.host}{path}"
        params = {ikey: vid}
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"视频详情请求失败")
            return {"list": []}

        try:
            res_json = rsp.json()
            v = res_json["data"]

            # 根据视频类型构建播放源和播放地址
            if tid == "67":  # 短剧
                pdata = v.get("playlist", [])
                names = [pdata[0].get("source_config_name")] if pdata else [""]
                play_urls = ["#".join([f"{i.get('title')}${i['url']}" for i in pdata])]
            else:  # 普通视频
                names, play_urls = [], []
                for source in v.get("source_list_source", []):
                    names.append(source.get("name", ""))
                    urls = "#".join(
                        [
                            f"{j.get('source_name') or j.get('weight')}${j['url']}"
                            for j in source.get("source_list", [])
                        ]
                    )
                    if urls:
                        play_urls.append(urls)

            # 构建视频详情
            video = {
                "vod_id": str(v.get("id", "")),
                "vod_name": v.get("title", ""),
                "vod_pic": f"{self.ihost}{v.get('path') or v.get('cover_image') or v.get('thumbnail', '')}",
                "vod_remarks": v.get("update_cycle", ""),
                "vod_year": v.get("year", ""),
                "vod_area": v.get("area", ""),
                "vod_actor": "/".join([i.get("name", "") for i in v.get("actors", [])]),
                "vod_director": "/".join(
                    [i.get("name", "") for i in v.get("director", [])]
                ),
                "vod_content": v.get("description", ""),
                "vod_score": str(v.get("score", "")),
                "type_name": "/".join([i.get("name", "") for i in v.get("types", [])]),
                "vod_play_from": "$$$".join(names),
                "vod_play_url": "$$$".join(play_urls),
            }

            return {"list": [video]}
        except Exception as e:
            self.log(f"视频详情解析失败: {e}")
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
            "page": 当前页数,
            "limit": 每页显示数量,
            "pagecount": 总页数=总数/每页数量
            "total": 总数
        """
        url = f"{self.host}/api/v2/search/videoV2"
        params = {"key": key, "page": pg, "pageSize": 20}
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"搜索结果请求失败")
            return {"list": []}

        try:
            res_json = rsp.json()
            result = {}
            result["list"] = self.build_cl(res_json["data"])
            result["page"] = pg
            result["pagecount"] = 9999
            result["limit"] = 20
            result["total"] = 999999
            return result
        except Exception as e:
            self.log(f"搜索结果解析失败: {e}")
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
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": {"User-Agent": self.user_agent},
        }

    def getfts(self, id):
        """
        获取筛选条件
        :param id: 分类ID
        :return: 筛选条件
        """
        data = self.fetch(
            f"{self.host}/api/crumb/filterOptions",
            params={"fcate_pid": id},
            headers=self.headers,
        ).json()
        fts = [
            {
                "key": i["key"],
                "name": i["key"],
                "value": [{"n": j["name"], "v": j["id"]} for j in i["data"]],
            }
            for i in data["data"]
        ]
        return id, fts

    def build_cl(self, data, tid=""):
        """
        将API返回的视频列表转为标准vod格式
        :param data: API返回的视频数据
        :param tid: 分类ID
        :return: 标准vod格式的视频列表
        """
        videos = []
        for i in data:
            # 判断是否为短剧
            text = json.dumps(i.get("res_categories", []))
            video_tid = "67" if json.dumps("短剧") in text and "67" in text else tid

            videos.append(
                {
                    "vod_id": f"{i.get('id')}@{video_tid}",
                    "vod_name": i.get("title", ""),
                    "vod_pic": f"{self.ihost}{i.get('path') or i.get('cover_image') or i.get('thumbnail', '')}",
                    "vod_remarks": i.get("mask", ""),
                    "vod_year": i.get("score", ""),
                }
            )
        return videos


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    # print("---------------------获取分类列表测试------------------------------")
    # rsp = spider.homeContent(True)
    # print(rsp)
    # time.sleep(1)
    # 'filters': {3: [{'key': 'type', 'name': 'type', 'value': [{'n': '全部', 'v': ''}, {'n': '剧情', 'v': '1'}, {'n': '爱情', 'v': '2'}, {'n': '动画', 'v': '3'}, {'n': '喜剧', 'v': '4'}, {'n': '战争', 'v': '5'}, {'n': '歌舞', 'v': '6'}, {'n': '古装', 'v': '7'}, {'n': '奇幻', 'v': '8'}, {'n': '冒险', 'v': '9'}, {'n': '动作', 'v': '10'}, {'n': '科幻', 'v': '11'}, {'n': '悬疑', 'v': '12'}, {'n': '犯罪', 'v': '13'}, {'n': '家庭', 'v': '14'}, {'n': '传记', 'v': '15'}, {'n': '运动', 'v': '16'}, {'n': '同性', 'v': '17'}, {'n': '惊悚', 'v': '18'}, {'n': '情色', 'v': '19'}, {'n': '短片', 'v': '20'}, {'n': '历史', 'v': '21'}, {'n': '音乐', 'v': '22'}, {'n': '西部', 'v': '23'}, {'n': '武侠', 'v': '24'}, {'n': '恐怖', 'v': '25'}]}, {'key': 'area', 'name': 'area', 'value': [{'n': '全部', 'v': ''}, {'n': '国产', 'v': '1'}, {'n': '中国香港', 'v': '3'}, {'n': '中国台湾', 'v': '6'}, {'n': '美国', 'v': '5'}, {'n': '韩国', 'v': '18'}, {'n': '日本', 'v': '2'}]}, {'key': 'year', 'name': 'year', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '162'}, {'n': '2025', 'v': '107'}, {'n': '2024', 'v': '119'}, {'n': '2023', 'v': '153'}, {'n': '2022', 'v': '101'}, {'n': '2021', 'v': '118'}, {'n': '2020', 'v': '16'}, {'n': '2019', 'v': '7'}, {'n': '2018', 'v': '2'}, {'n': '2017', 'v': '3'}, {'n': '2016', 'v': '22'}, {'n': '2015以前', 'v': '2015'}]}, {'key': 'sort', 'name': 'sort', 'value': [{'n': '全部', 'v': ''}, {'n': '最新', 'v': 'update'}, {'n': '最热', 'v': 'hot'}, {'n': '评分', 'v': 'rating'}]}], 67: [{'key': 'category_id', 'name': 'category_id', 'value': [{'n': '全部', 'v': ''}, {'n': '言情', 'v': '70'}, {'n': '爱情', 'v': '71'}, {'n': '战神', 'v': '72'}, {'n': '古代', 'v': '73'}, {'n': '萌娃', 'v': '74'}, {'n': '神医', 'v': '75'}, {'n': '玄幻', 'v': '76'}, {'n': '重生', 'v': '77'}, {'n': '激情', 'v': '79'}, {'n': '时尚', 'v': '82'}, {'n': '剧情演绎', 'v': '83'}, {'n': '影视', 'v': '84'}, {'n': '人文社科', 'v': '85'}, {'n': '二次元', 'v': '86'}, {'n': '明星八卦', 'v': '87'}, {'n': '随拍', 'v': '88'}, {'n': '个人管理', 'v': '89'}, {'n': '音乐', 'v': '90'}, {'n': '汽车', 'v': '91'}, {'n': '休闲', 'v': '92'}, {'n': '校园教育', 'v': '93'}, {'n': '游戏', 'v': '94'}, {'n': '科普', 'v': '95'}, {'n': '科技', 'v': '96'}, {'n': '时政社会', 'v': '97'}, {'n': '萌宠', 'v': '98'}, {'n': '体育', 'v': '99'}, {'n': '穿越', 'v': '80'}, {'n': '', 'v': '81'}, {'n': '闪婚', 'v': '112'}]}, {'key': 'sort', 'name': 'sort', 'value': [{'n': '全部', 'v': ''}, {'n': '最新', 'v': 'update'}, {'n': '最热', 'v': 'hot'}]}], 1: [{'key': 'type', 'name': 'type', 'value': [{'n': '全部', 'v': ''}, {'n': '剧情', 'v': '1'}, {'n': '爱情', 'v': '2'}, {'n': '动画', 'v': '3'}, {'n': '喜剧', 'v': '4'}, {'n': '战争', 'v': '5'}, {'n': '歌舞', 'v': '6'}, {'n': '古装', 'v': '7'}, {'n': '奇幻', 'v': '8'}, {'n': '冒险', 'v': '9'}, {'n': '动作', 'v': '10'}, {'n': '科幻', 'v': '11'}, {'n': '悬疑', 'v': '12'}, {'n': '犯罪', 'v': '13'}, {'n': '家庭', 'v': '14'}, {'n': '传记', 'v': '15'}, {'n': '运动', 'v': '16'}, {'n': '同性', 'v': '17'}, {'n': '惊悚', 'v': '18'}, {'n': '情色', 'v': '19'}, {'n': '短片', 'v': '20'}, {'n': '历史', 'v': '21'}, {'n': '音乐', 'v': '22'}, {'n': '西部', 'v': '23'}, {'n': '武侠', 'v': '24'}, {'n': '恐怖', 'v': '25'}]}, {'key': 'area', 'name': 'area', 'value': [{'n': '全部', 'v': ''}, {'n': '国产', 'v': '1'}, {'n': '中国香港', 'v': '3'}, {'n': '中国台湾', 'v': '6'}, {'n': '美国', 'v': '5'}, {'n': '韩国', 'v': '18'}, {'n': '日本', 'v': '2'}]}, {'key': 'year', 'name': 'year', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '162'}, {'n': '2025', 'v': '107'}, {'n': '2024', 'v': '119'}, {'n': '2023', 'v': '153'}, {'n': '2022', 'v': '101'}, {'n': '2021', 'v': '118'}, {'n': '2020', 'v': '16'}, {'n': '2019', 'v': '7'}, {'n': '2018', 'v': '2'}, {'n': '2017', 'v': '3'}, {'n': '2016', 'v': '22'}, {'n': '2015以前', 'v': '2015'}]}, {'key': 'sort', 'name': 'sort', 'value': [{'n': '全部', 'v': ''}, {'n': '最新', 'v': 'update'}, {'n': '最热', 'v': 'hot'}, {'n': '评分', 'v': 'rating'}]}], 2: [{'key': 'type', 'name': 'type', 'value': [{'n': '全部', 'v': ''}, {'n': '剧情', 'v': '1'}, {'n': '爱情', 'v': '2'}, {'n': '动画', 'v': '3'}, {'n': '喜剧', 'v': '4'}, {'n': '战争', 'v': '5'}, {'n': '歌舞', 'v': '6'}, {'n': '古装', 'v': '7'}, {'n': '奇幻', 'v': '8'}, {'n': '冒险', 'v': '9'}, {'n': '动作', 'v': '10'}, {'n': '科幻', 'v': '11'}, {'n': '悬疑', 'v': '12'}, {'n': '犯罪', 'v': '13'}, {'n': '家庭', 'v': '14'}, {'n': '传记', 'v': '15'}, {'n': '运动', 'v': '16'}, {'n': '同性', 'v': '17'}, {'n': '惊悚', 'v': '18'}, {'n': '情色', 'v': '19'}, {'n': '短片', 'v': '20'}, {'n': '历史', 'v': '21'}, {'n': '音乐', 'v': '22'}, {'n': '西部', 'v': '23'}, {'n': '武侠', 'v': '24'}, {'n': '恐怖', 'v': '25'}]}, {'key': 'area', 'name': 'area', 'value': [{'n': '全部', 'v': ''}, {'n': '国产', 'v': '1'}, {'n': '中国香港', 'v': '3'}, {'n': '中国台湾', 'v': '6'}, {'n': '美国', 'v': '5'}, {'n': '韩国', 'v': '18'}, {'n': '日本', 'v': '2'}]}, {'key': 'year', 'name': 'year', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '162'}, {'n': '2025', 'v': '107'}, {'n': '2024', 'v': '119'}, {'n': '2023', 'v': '153'}, {'n': '2022', 'v': '101'}, {'n': '2021', 'v': '118'}, {'n': '2020', 'v': '16'}, {'n': '2019', 'v': '7'}, {'n': '2018', 'v': '2'}, {'n': '2017', 'v': '3'}, {'n': '2016', 'v': '22'}, {'n': '2015以前', 'v': '2015'}]}, {'key': 'sort', 'name': 'sort', 'value': [{'n': '全部', 'v': ''}, {'n': '最新', 'v': 'update'}, {'n': '最热', 'v': 'hot'}, {'n': '评分', 'v': 'rating'}]}], 4: [{'key': 'type', 'name': 'type', 'value': [{'n': '全部', 'v': ''}, {'n': '剧情', 'v': '1'}, {'n': '爱情', 'v': '2'}, {'n': '动画', 'v': '3'}, {'n': '喜剧', 'v': '4'}, {'n': '战争', 'v': '5'}, {'n': '歌舞', 'v': '6'}, {'n': '古装', 'v': '7'}, {'n': '奇幻', 'v': '8'}, {'n': '冒险', 'v': '9'}, {'n': '动作', 'v': '10'}, {'n': '科幻', 'v': '11'}, {'n': '悬疑', 'v': '12'}, {'n': '犯罪', 'v': '13'}, {'n': '家庭', 'v': '14'}, {'n': '传记', 'v': '15'}, {'n': '运动', 'v': '16'}, {'n': '同性', 'v': '17'}, {'n': '惊悚', 'v': '18'}, {'n': '情色', 'v': '19'}, {'n': '短片', 'v': '20'}, {'n': '历史', 'v': '21'}, {'n': '音乐', 'v': '22'}, {'n': '西部', 'v': '23'}, {'n': '武侠', 'v': '24'}, {'n': '恐怖', 'v': '25'}]}, {'key': 'area', 'name': 'area', 'value': [{'n': '全部', 'v': ''}, {'n': '国产', 'v': '1'}, {'n': '中国香港', 'v': '3'}, {'n': '中国台湾', 'v': '6'}, {'n': '美国', 'v': '5'}, {'n': '韩国', 'v': '18'}, {'n': '日本', 'v': '2'}]}, {'key': 'year', 'name': 'year', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '162'}, {'n': '2025', 'v': '107'}, {'n': '2024', 'v': '119'}, {'n': '2023', 'v': '153'}, {'n': '2022', 'v': '101'}, {'n': '2021', 'v': '118'}, {'n': '2020', 'v': '16'}, {'n': '2019', 'v': '7'}, {'n': '2018', 'v': '2'}, {'n': '2017', 'v': '3'}, {'n': '2016', 'v': '22'}, {'n': '2015以前', 'v': '2015'}]}, {'key': 'sort', 'name': 'sort', 'value': [{'n': '全部', 'v': ''}, {'n': '最新', 'v': 'update'}, {'n': '最热', 'v': 'hot'}, {'n': '评分', 'v': 'rating'}]}]}
    # print("\n-------------------获取分类内容测试------------------------------")
    # rsp = {"class": [{"type_name": "电影", "type_id": 1}]}
    # if rsp.get("class"):
    #     rsp_cat = spider.categoryContent(rsp["class"][0]["type_id"], 1, True, {"sort": "","category_id": ""})
    #     print(rsp_cat)
    #     time.sleep(1)
    #     if rsp_cat.get("list"):
    #         print("\n-------------------获取视频详情测试------------------------------")
    #         rsp_det = spider.detailContent([rsp_cat["list"][0]["vod_id"]])
    #         print(rsp_det)
    #         time.sleep(1)
    #         print("\n-------------------解析视频地址测试------------------------------")
    #         if rsp_det.get("list") and rsp_det["list"][0].get("vod_play_url"):
    #             play_url = (
    #                 rsp_det["list"][0]["vod_play_url"].split("$$$")[0].split("#")[0]
    #             )
    #             if "$" in play_url:
    #                 play_url = play_url.split("$")[1]
    #             rsp_player = spider.playerContent("", play_url, [])
    #             print(rsp_player)
    # print("\n-------------------获取搜索内容测试------------------------------")
    # rsp_search = spider.searchContent("推荐", False, 1)
    # print(rsp_search)
