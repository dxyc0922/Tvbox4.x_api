"""
脚本说明：脚本仅用于学习,对请求频率做了限制，如若侵犯你的权益请联系删除
请勿用于商业用途，请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任
"""
import sys
import time
import random
from datetime import datetime

sys.path.append("..")
from base.spider import Spider


class Spider(Spider):  # 继承基类Spider，实现具体的脚本逻辑
    def init(self, extend=""):  # 初始化函数，设置脚本的基本配置信息
        self.name = "首页"  # 脚本名称
        # 豆瓣API接口地址，用于获取搜索结果
        self.douban_api = "https://movie.douban.com/j/new_search_subjects"
        # 非凡API接口地址
        self.ffzy_api = "https://ffzy.tv/index.php/ajax/data"
        # 用户代理字符串，模拟浏览器访问
        self.user_agent = [
            # Chrome - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            # Chrome - macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            # Chrome - Linux
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Firefox - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
            # Firefox - macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
            # Firefox - Linux
            "Mozilla/5.0 (X11; Linux i686; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
            # Safari - iOS
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            # Safari - macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            # Edge - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            # Samsung Browser - Android
            "Mozilla/5.0 (Linux; Android 10; SAMSUNG SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.5790.166 Mobile Safari/537.36",
            # Chrome - Android
            "Mozilla/5.0 (Linux; Android 10; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
            # Opera - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/105.0.0.0",
        ]
        # 请求头信息，模拟正常浏览器访问豆瓣网站
        self.douban_header = {
            "Accept": "application/json",  # 接收的数据格式
            "Referer": "https://www.douban.com/",  # 引用页面
        }
        self.ffzy_header = {
            "Accept": "application/json",
            "Referer": "https://ffzy.tv/",
        }
        # 添加标志以追踪是否为首次请求
        self.first_request = True
        # 缓存时间配置（单位：秒）,首次请求后,对常用请求内容进行缓存,避免浪费网络资源
        self.cache_times = {
            # 天*时*分*秒
            "home_video": 1 * 24 * 60 * 60,  # 首页推荐视频，1天,首页推荐一般少变动,每天刷新可以看看有没有新的推荐
            "douban_category": 1 * 24 * 60 * 60,  # 分类内容，1天,豆瓣分类内容一般少变动,只有新出影视才会有变动
            "ffzy_category": 1 * 1 * 10 * 60,  # 分类内容，10分钟,非凡资源经常变动,适合追剧看看有没有最新集
        }

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
        # 如果不是第一次请求，则添加随机延迟 0.5-2 秒
        if not self.first_request:
            delay = random.uniform(0.5, 2.0)
            time.sleep(delay)
        else:
            # 第一次请求后将标志设为False
            self.first_request = False
        # 调用父类的 fetch 方法
        return super().fetch(
            url, params, cookies, headers, timeout, verify, stream, allow_redirects
        )

    def getRandomHeader(self, api_or_headers):
        """获取带有随机user-agent的请求头"""
        # 判断参数是字典还是字符串URL
        if isinstance(api_or_headers, dict):
            # 如果传入的是字典类型的headers，则更新该字典
            headers_copy = api_or_headers.copy()
            headers_copy["User-Agent"] = random.choice(self.user_agent)
            return headers_copy
        else:
            # 如果传入的是字符串类型的URL，则创建新的字典
            header = {"User-Agent": random.choice(self.user_agent)}
            return header

    def getName(self):  # 获取脚本名称的方法
        return self.name

    def homeContent(self, filter):  # 获取首页内容（分类信息）的方法
        # 定义视频内容的分类列表，包括非凡资源和豆瓣资源
        categories = [
            {"type_id": "4", "type_name": "最新动漫"},  # 非凡动漫分类
            {"type_id": "2", "type_name": "最新剧集"},  # 非凡电视剧分类
            {"type_id": "电视剧", "type_name": "热门剧集"},  # 豆瓣电视剧分类
            {"type_id": "1", "type_name": "最新电影"},  # 非凡电影分类
            {"type_id": "电影", "type_name": "热门电影"},  # 豆瓣电影分类
            {"type_id": "3", "type_name": "最新综艺"},  # 非凡综艺分类
            {"type_id": "综艺", "type_name": "热门综艺"},  # 豆瓣综艺分类
        ]

        # 定义各类别的筛选条件，根据不同的分类提供不同的筛选参数
        filters = {
            "4": [  # 非凡动漫分类的筛选条件
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"v": "29", "n": "国产动漫"},
                        {"v": "30", "n": "日韩动漫"},
                        {"v": "31", "n": "欧美动漫"},
                        {"v": "32", "n": "港台动漫"},
                        {"v": "33", "n": "海外动漫"},
                    ],
                }
            ],
            "2": [  # 非凡电视剧分类的筛选条件
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"v": "13", "n": "国产剧"},
                        {"v": "14", "n": "香港剧"},
                        {"v": "15", "n": "韩国剧"},
                        {"v": "16", "n": "欧美剧"},
                        {"v": "21", "n": "台湾剧"},
                        {"v": "22", "n": "日本剧"},
                        {"v": "23", "n": "海外剧"},
                        {"v": "24", "n": "泰国剧"},
                        {"v": "36", "n": "短剧"},
                    ],
                },
            ],
            "电视剧": [  # 豆瓣电视剧分类的筛选条件
                {
                    "key": "排序",
                    "name": "排序",
                    "value": [
                        {"n": "近期热度", "v": "U"},
                        {"n": "高分优先", "v": "S"},
                        {"n": "综合排序", "v": "T"},
                        {"n": "首播时间", "v": "R"},
                    ],
                },
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"n": "动画", "v": "动画"},
                        {"n": "喜剧", "v": "喜剧"},
                        {"n": "动作", "v": "动作"},
                        {"n": "科幻", "v": "科幻"},
                        {"n": "爱情", "v": "爱情"},
                        {"n": "悬疑", "v": "悬疑"},
                        {"n": "武侠", "v": "武侠"},
                        {"n": "古装", "v": "古装"},
                        {"n": "家庭", "v": "家庭"},
                        {"n": "犯罪", "v": "犯罪"},
                        {"n": "恐怖", "v": "恐怖"},
                        {"n": "历史", "v": "历史"},
                        {"n": "战争", "v": "战争"},
                        {"n": "冒险", "v": "冒险"},
                        {"n": "传记", "v": "传记"},
                        {"n": "剧情", "v": "剧情"},
                        {"n": "玄幻", "v": "玄幻"},
                        {"n": "惊悚", "v": "惊悚"},
                        {"n": "灾难", "v": "灾难"},
                        {"n": "歌舞", "v": "歌舞"},
                        {"n": "音乐", "v": "音乐"},
                    ],
                },
                {
                    "key": "地区",
                    "name": "地区",
                    "value": [
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "国外", "v": "国外"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                        {"n": "印度", "v": "印度"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                    ],
                },
            ],
            "1": [  # 非凡电影分类的筛选条件
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"v": "6", "n": "动作片"},
                        {"v": "7", "n": "喜剧片"},
                        {"v": "8", "n": "爱情片"},
                        {"v": "9", "n": "科幻片"},
                        {"v": "10", "n": "恐怖片"},
                        {"v": "11", "n": "剧情片"},
                        {"v": "12", "n": "战争片"},
                        {"v": "20", "n": "记录片"},
                    ],
                },
            ],
            "电影": [  # 豆瓣电影分类的筛选条件
                {
                    "key": "排序",  # 排序方式
                    "name": "排序",
                    "value": [  # 排序选项
                        {"n": "近期热度", "v": "U"},  # 近期热度
                        {"n": "高分优先", "v": "S"},  # 高分优先
                        {"n": "综合排序", "v": "T"},  # 综合排序
                        {"n": "首播时间", "v": "R"},  # 首播时间
                    ],
                },
                {
                    "key": "类型",  # 类型筛选
                    "name": "类型",
                    "value": [  # 电影类型选项
                        {"n": "动画", "v": "动画"},
                        {"n": "喜剧", "v": "喜剧"},
                        {"n": "动作", "v": "动作"},
                        {"n": "科幻", "v": "科幻"},
                        {"n": "爱情", "v": "爱情"},
                        {"n": "悬疑", "v": "悬疑"},
                        {"n": "犯罪", "v": "犯罪"},
                        {"n": "惊悚", "v": "惊悚"},
                        {"n": "冒险", "v": "冒险"},
                        {"n": "音乐", "v": "音乐"},
                        {"n": "历史", "v": "历史"},
                        {"n": "奇幻", "v": "奇幻"},
                        {"n": "恐怖", "v": "恐怖"},
                        {"n": "战争", "v": "战争"},
                        {"n": "传记", "v": "传记"},
                        {"n": "歌舞", "v": "歌舞"},
                        {"n": "武侠", "v": "武侠"},
                        {"n": "灾难", "v": "灾难"},
                        {"n": "西部", "v": "西部"},
                        {"n": "纪录片", "v": "纪录片"},
                        {"n": "短片", "v": "短片"},
                    ],
                },
                {
                    "key": "地区",  # 地区筛选
                    "name": "地区",
                    "value": [  # 电影地区选项
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "日本", "v": "日本"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "印度", "v": "印度"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                    ],
                },
            ],
            "3": [  # 非凡综艺分类的筛选条件
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"v": "25", "n": "大陆综艺"},
                        {"v": "26", "n": "港台综艺"},
                        {"v": "27", "n": "日韩综艺"},
                        {"v": "28", "n": "欧美综艺"},
                    ],
                },
            ],
            "综艺": [  # 豆瓣综艺分类的筛选条件
                {
                    "key": "排序",
                    "name": "排序",
                    "value": [
                        {"n": "近期热度", "v": "U"},
                        {"n": "高分优先", "v": "S"},
                        {"n": "综合排序", "v": "T"},
                        {"n": "首播时间", "v": "R"},
                    ],
                },
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"n": "真人秀", "v": "真人秀"},
                        {"n": "脱口秀", "v": "脱口秀"},
                        {"n": "音乐", "v": "音乐"},
                        {"n": "歌舞", "v": "歌舞"},
                    ],
                },
                {
                    "key": "地区",
                    "name": "地区",
                    "value": [
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "国外", "v": "国外"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                        {"n": "印度", "v": "印度"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                    ],
                },
            ],
        }
        # 返回分类和筛选条件数据
        return {"class": categories, "filters": filters}

    def homeVideoContent(self):  # 获取首页推荐视频内容的方法
        try:
            # 获取当前年份，用于限制视频年份范围
            current_year = datetime.now().year
            # 生成缓存键名
            cache_key = f"douban_home_video"
            # 尝试从缓存获取数据
            cached_data = self.getCache(cache_key)
            # 检查缓存是否有效：存在、包含list字段、list不为空、list中第一个元素有vod_id字段
            if (
                cached_data
                and "list" in cached_data
                and len(cached_data["list"]) > 0
                and "vod_id" in cached_data["list"][0]
            ):
                self.log(f"首页推荐使用缓存数据:{cache_key}")
                return cached_data
            # 构建请求参数
            params = {
                "sort": "U",  # 排序:近期热度
                "range": "0,10",  # 评分区间:0-10分
                "playable": "0",  # 是否可播放:0-不开启，1-开启
                "start": "0",  # 视频起始位置
                "limit": "100",  # 每页数量
                "tags": "",  # 根据分类筛选
                "year_range": f"{current_year-1},{current_year}",  # 年份范围：去年到今年
            }
            self.log(f"请求豆瓣首页推荐视频数据:params={params}")
            rsp = self.fetch(
                url=self.douban_api,
                params=params,
                headers=self.getRandomHeader(self.douban_header.copy()),
            ).json()
            self.log(f"豆瓣首页推荐视频数据:{rsp}")
            video_list = []
            for item in rsp["data"]:
                video_info = self._build_video_info(item, "豆瓣")
                video_list.append(video_info)
            # 设置带过期时间的缓存数据，7天后过期
            cache_with_expiry = {
                "list": video_list,
                "expiresAt": int(time.time()) + self.cache_times["home_video"],
            }
            # 存储到缓存
            self.setCache(cache_key, cache_with_expiry)
            # 返回视频列表
            return {"list": video_list}
        except Exception as e:  # 捕获异常
            self.log(f"获取首页视频内容时出错：: {e}")
            # 出现错误时返回空列表
            return {"list": []}

    def _build_video_info(self, item, source):
        """构建视频信息的公共方法，根据数据源不同处理不同格式的数据"""
        if source == "豆瓣":
            # 获取评分
            rate = item.get("rate", "")
            # 获取封面图片URL
            cover = item.get("cover", "")
            # 如果有封面图，则添加用户代理参数，防止防盗链
            if cover:
                # 添加User-Agent和Referer参数，防止防盗链
                cover = f"{cover}@User-Agent={random.choice(self.user_agent)}@Referer=https://www.douban.com/"
            # 构建视频信息对象
            return {
                "vod_id": item["id"],  # 视频ID
                "vod_name": item.get("title", ""),  # 视频标题
                "vod_pic": cover,  # 视频封面图
                "vod_remarks": f"{rate}分" if rate else "暂无评分",  # 视频评分备注
            }
        elif source == "非凡":
            # 非凡资源的视频信息构建
            return {
                "vod_id": item["vod_id"],
                "vod_name": item.get("vod_name"),
                "vod_pic": item.get("vod_pic"),
                "vod_remarks": item.get("vod_remarks"),
            }

    def douban_cate_content(self, tid, pg, filter, extend, cache_key):
        """获取豆瓣分类内容的方法，支持多种筛选条件"""
        limit = 100  # 设置每页数量
        start = (int(pg) - 1) * limit  # 计算每次分页起始索引
        # 构建请求参数
        params = {
            "sort": "U",  # 排序:近期热度
            "range": "0,10",  # 评分区间:0-10分
            "playable": "0",  # 是否只显示可播放的:0-否,1-是
            "start": str(start),  # 视频起始索引
            "limit": str(limit),  # 每页数量
            "tags": tid,  # 根据分类筛选,还可以拼日期之类的比如:电影,2025
        }
        # 如果扩展参数存在，将其加入请求参数中
        if extend and isinstance(extend, dict):
            if "类型" in extend:
                params["genres"] = extend["类型"]  # 按类型筛选
            if "排序" in extend:
                params["sort"] = extend["排序"]  # 按指定排序方式排序
            if "地区" in extend:
                params["countries"] = extend["地区"]  # 按地区筛选
        self.log(f"请求豆瓣分类内容数据:params={params}")
        rsp = self.fetch(
            url=self.douban_api,
            params=params,
            headers=self.getRandomHeader(self.douban_header.copy()),
        ).json()
        self.log(f"豆瓣分类内容数据:{rsp}")
        video_list = []
        for item in rsp["data"]:
            video_info = self._build_video_info(item, "豆瓣")
            video_list.append(video_info)
        # 设置带过期时间的缓存数据，7天后过期
        cache_with_expiry = {
            "list": video_list,
            "expiresAt": int(time.time()) + self.cache_times["douban_category"],
        }
        # 存储到缓存
        self.setCache(cache_key, cache_with_expiry)
        # 返回视频列表
        return {"list": video_list}

    def ffzy_cate_content(self, tid, pg, filter, extend, cache_key):
        """获取非凡资源分类内容的方法"""
        params = {
            "mid": "1",
            "tid": tid,
            "page": pg,
            "limit": "30",  # 每页数量,最大支持30
        }
        # 如果扩展参数存在，将其加入请求参数中
        if extend and isinstance(extend, dict):
            if "类型" in extend:
                params["tid"] = extend["类型"]  # 按类型筛选
        self.log(f"请求非凡资源分类内容数据:params={params}")
        # 发送请求获取数据
        rsp = self.fetch(
            url=self.ffzy_api,
            params=params,
            headers=self.getRandomHeader(self.ffzy_header.copy()), # 使用正确的请求头
        ).json()
        self.log(f"非凡资源分类内容数据:{rsp}")
        video_list = []
        if 'list' in rsp and rsp['list']:  # 检查响应中是否有list字段
            for item in rsp["list"]:
                if "伦理片" in item.get("type_name", ""):
                    continue
                video_info = self._build_video_info(item, "非凡")
                video_list.append(video_info)
        # 设置带过期时间的缓存数据，10分钟后过期
        cache_with_expiry = {
            "list": video_list,
            "expiresAt": int(time.time()) + self.cache_times["ffzy_category"],
        }
        # 存储到缓存
        self.setCache(cache_key, cache_with_expiry)
        # 返回视频列表
        return {"list": video_list}

    def categoryContent(self, tid, pg, filter, extend):
        """获取指定分类下的视频内容"""
        try:
            # 生成缓存键名，包含分类ID和页数
            cache_params = f"cat_{tid}_page_{pg}"
            # 如果扩展参数存在，将其加入缓存键名中
            if extend and isinstance(extend, dict):
                if "类型" in extend:
                    cache_params += f"_genre_{extend['类型']}"  # 添加类型参数到缓存键
                if "排序" in extend:
                    cache_params += f"_sort_{extend['排序']}"  # 添加排序参数到缓存键
                if "地区" in extend:
                    cache_params += f"_country_{extend['地区']}"  # 添加地区参数到缓存键
            cache_key = f"category_{cache_params}"
            # 尝试从缓存获取数据
            cached_data = self.getCache(cache_key)
            # 检查缓存是否有效
            if (
                cached_data
                and "list" in cached_data
                and len(cached_data["list"]) > 0
                and "vod_id" in cached_data["list"][0]
            ):
                # 返回缓存的数据
                return cached_data
            # 根据分类ID决定使用哪个API获取数据：豆瓣API或非凡API
            if (
                tid == "电视剧"
                or tid == "电影"
                or tid == "综艺"
            ):
                self.log(f"使用豆瓣API获取分类内容:{tid}")
                return self.douban_cate_content(
                    tid, pg, filter, extend, cache_key
                )
            else:
                self.log(f"使用非凡资源API获取分类内容:{tid}")
                return self.ffzy_cate_content(tid, pg, filter, extend, cache_key)
        except Exception as e:  # 捕获异常
            self.log(f"获取分类内容时出错：{e}")  # 显示完整的错误信息
            # 出现错误时返回空列表
            return {"list": []}


if __name__ == "__main__":
    spider = Spider()
    spider.init()
