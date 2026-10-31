# Tvbox4.x_api
适配安卓4.x的tvbox接口

源地址：https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json

Github加速地址：https://gh-proxy.com/https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json

远程直链版（生成站点用 gh-proxy 绝对链接，不带 `脚本/` 目录也能用）：
https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口-remote.json

说明:由于盒子是安卓4.x会导致加载一些新的接口会崩溃,无法加载,无法播放等异常情况,况且有些线路含18禁内容不适合在电视上展示,以及一些线路含赌博广告,播放卡顿等问题都需要清除

1.符合下面要求的接口会添加进接口给电视用

2.在电视盒子上接口加载正常;自营线路播放正常

3.不存在18禁内容,比如伦理,福利等分类;搜索"女教师"等关键字无漏点图

4.无赌博广告,播放不卡顿,比如cms资源站的资源一般都不合格

5.直播使用本地电信组播IPTV源,需要路由器启用IGMP嗅探

## 自动同步接口

更新逻辑：`scripts/update_api.py`；定时运行在**本机**（Windows 任务计划程序），
GitHub Actions 只保留手动触发作为备用通道。

- 临时拉取上游 `wzxxcz/wzxxcz` 的 `py/` 目录，把校验通过的脚本**同步到 `脚本/` 目录**并提交进仓库。
- 解析每个脚本里的 host（支持 `HOST`、`HOSTS`、`host`、`xurl` 等变量，以及 `_dk8` 混淆字符串）。
- 只接受定义了 `class Spider` 的脚本：上游混入的报错 HTML、命令行脚本会被跳过。
- 代码内容相同的脚本（改名副本）只保留一个，优先保留文件名不带广告后缀、更短的那个。
- host 返回 `2xx/3xx/4xx` 视为可达；`5xx`、DNS 失败、连接超时视为失效。
- 重建 `接口.json` 的 `sites`：
  - `api` 以 `./` 开头（本地脚本）或其他非 http 站点原样保留；
  - 所有 http/https 站点删除后，用校验通过的上游脚本重新生成；
  - 生成站点的 `api` 指向本地文件 `./脚本/<脚本名>.py`，不再依赖 gh-proxy 存活。
- 线路级裁减：给每个脚本注入一段过滤代码，把**不通的线路**（HTTP 4xx/5xx、token 过期）
  和**明显低质量的线路**（码率低于分辨率档，且同源另有达标线路）从播放列表里去掉。
  剔除要走「两振出局」：源/线路连续两轮被判为同一剔除候选才真剔除，单集 token 过期、
  CDN 抖动不再让名单每周漂移（见「两振出局」）。
- 同时生成 `接口-remote.json`：生成站点的 `api` 用 gh-proxy 绝对链接，兼容只发布单个
  JSON 文件、不带 `脚本/` 目录的托管方式。
- `wallpaper`、`lives`、`doh`、`rules`、`ads` 等其他顶层字段保持不变。
- 可用站点骤降保护：本次生成数少于上次的一半、或下载失败率超过 20% 时不写入，直接报错退出。

### 本机定时运行（推荐）

```powershell
# 1. 先手动跑一次，确认能生成、能推送
python scripts/run_local.py --dry-run     # 只校验，不写文件
python scripts/run_local.py               # 校验 + 生成 + 提交推送

# 2. 注册每周任务（默认每周一 02:00，当前登录用户）
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1

# 可选参数
#   -Day Sunday -Time 03:30        改时间
#   -Functional                    顺带跑功能校验
#   -RunWhenLoggedOff              未登录也运行（会提示输入该用户密码）
#   -Unregister                    删除任务
```

`run_local.py` 每次运行会：

1. `git pull --rebase --autostash`（失败忽略，不影响生成）；
2. 可选跑 `functional_check.py`（`--functional`，默认关闭）；
3. 调用 `update_api.py` 重建 `接口.json`；
4. 有变化才提交，推送失败会重试 3 次；仍失败则保留本地提交，下次运行自动带上。

日志写在 `logs/local-run-<时间>.log`，任务计划程序里也能看到上次运行结果。

### 功能校验（可选）

host 可达不代表脚本能用。`scripts/functional_check.py` 会在隔离环境里真正调用脚本：

1. `homeContent` —— 能否取到首页片单；
2. `searchContent` —— 用关键词搜索能否取到结果；
3. `detailContent` —— 能否拿到 `vod_play_url` 播放地址。

每通过一项记 1 分，满分 3 分。结果写入 `reports/functional-report.json`，`update_api.py`
用 `--functional-report` 读取并附加到 `接口.json` 的校验报告里。

```bash
# 本地调试（会执行第三方代码，建议在虚拟机里跑）
python scripts/functional_check.py --source-dir /path/to/py --limit 20

# 把评分合并进校验报告
python scripts/update_api.py --functional-report reports/functional-report.json
```

GitHub Actions 里这一步跑在 Docker 容器中：不注入任何密钥、`/work` 只读、限制内存/CPU/进程数、
禁止访问内网和回环地址。**本机运行（`--functional`）没有容器隔离**，等于在自己的机器上执行
221 个陌生脚本，只做了超时杀进程和「禁止访问内网地址」两道防护；除非装了 Docker/WSL2，
否则不建议在本机开启。

默认 **只评分不删源**（`functional.min_score = 0`）。实测 221 个脚本里约 47% 能拿到 2 分以上，
0 分的绝大多数是「请求成功但搜不到结果」——多半是境外 IP 被地区限制，按分数删源会误删。
确认识别准确后再把 `min_score` 设为 2 或 3。

### 源质量分级（A/B/C/D）

功能校验拿到播放地址后，`scripts/stream_check.py` 会再走一遍 `playerContent`，用真实播放地址判断来源
（每个源最多取 `quality.max_lines` 条线路，逐条判断，同时测量码率）：

| 等级 | 含义 | 判断依据 |
|---|---|---|
| **A 自营** | 播放地址和站点同主域，自己转码自己发 | 域名比对一致 |
| **B 第三方直连** | 直连 m3u8/mp4，但走的是别家 CDN | 域名不一致 |
| **C 搬运/解析** | 播放地址落在抖音/快手/西瓜等平台 CDN，或需要网页解析 | 平台域名 / 字节 `tos-cn-` 路径 / `parse=1` / 页面型地址 |
| **D 无法验证** | 请求失败、返回非视频内容 | — |
| **U 未取得播放地址** | 没解析出播放地址（地区限制/超时/本地代理） | 不参与过滤 |

另外会记录 `ad_score`：`#EXT-X-CUE-OUT` / `#EXT-X-DATERANGE` / `SCTE35` 广告标记各 +3，
分片来自多个域名（少数域名占比 ≤20%）+2；`filters.ad_hosts` 里配置的已知广告域名片段
命中即 +2（个别源只插 1–2 个广告分片，不看占比）。命中即判 C。

```bash
# 单独看某个播放地址
python scripts/stream_check.py "https://xxx/index.m3u8" --site-host https://www.example.com
```

**关于「广告藏在 m3u8 不规则时间段」**：实测不成立。221 个脚本里 87 个能解析出播放地址，
其中 55 个 HLS 全部单域名分片、无 CUE/DATERANGE 标记、`ad_score` 全为 0；而正常转码源（VFR）
普遍存在 0.2–1 秒短分片和大量 `#EXT-X-DISCONTINUITY`（例如金牌蓝兔子 307 个短分片、
低端影视 277 个），按「时长不规则」判断会把正常源大面积误判成广告。广告更可能来自
解析器/网页播放器（C 级）或视频画面本身（搬运源水印）。

想按等级过滤，把 `scripts/config.json` 里的 `quality.min_grade` 设为 `B`（保留 A/B，剔除 C/D）
或 `A`（只保留自营）。默认空字符串表示不过滤。

**注意**：拿不到播放地址的脚本（地区限制、超时、本地代理 `127.0.0.1`）单独记为 **U 未取得播放地址**。
`quality.drop_unverified` 默认 `false`，即 U 不参与等级过滤——测不出来不等于源差，实测 220 个脚本里
U 有 136 个，全删会误伤大量可用站点。本仓库现在显式设为 `true`，只保留验证过的源。

等级按**所有采样线路里最好的一条**算：只要有一条线路正常（比如华谊影视第一条线路连接失败、
K蓝光正常），就按那条线路的等级计，不会因为第一条失败被判成 U。

当前仓库的配置是 `min_grade = "B"` + `drop_unverified = true`，即**只保留验证过的 A/B 源**。
220 个脚本里本轮可用 51 个（A 6 + B 45），其余是等级不足/U、成人内容、低码率、加载慢、
host 不可达、无 host、跳过。最终 `接口.json` 是 53 个站点（51 自动 + 2 本地）。
想放宽就关掉 `drop_unverified`。

> 数量会随两振出局波动：源被判「剔除候选」后**连续两轮**才真剔除，所以某一轮可能比上一轮
> 略多（首轮全保留或新源进来），下一轮稳定后又回到基准。见「两振出局」。

### 本地运行

```bash
python scripts/update_api.py --dry-run
python scripts/update_api.py

# 用已经下载好的 py 目录调试，不访问 GitHub
python scripts/update_api.py --source-dir /path/to/py --dry-run
```

输出两个接口文件：

- `接口.json`：生成站点的 `api` 指向本地 `./脚本/<脚本名>.py`（随仓库一起发布，带 `脚本/` 目录）。
- `接口-remote.json`：生成站点的 `api` 是 gh-proxy 绝对链接，只发布这个 JSON 单文件也能用
  （但 `脚本/` 里的源就不带本地副本了，适合纯 CDN 托管）。

生成站点按**质量排序**：等级（A>B>C>D）→ 功能评分 → 最高线路码率 → 最快速度比 → 名称，
打开接口第一个就是最好的源。手动保留的本地站点（豆瓣/哔哩）仍排在最前。

### 成人内容过滤

默认开启（`filters.exclude_adult = true`）。判定分两条，都不依赖关键词搜索是否准确：

1. **分类名**：首页 `homeContent` 返回的分类里出现 `伦理片` / `理论片` / `福利` / `里番` / `无码` /
   `三级` / `成人` / `麻豆` / `蜜桃` / `星空传媒` / `自拍` / `偷拍` / `乱伦` 等。
   `伦理` / `理论` 必须带「片」或单独成词，所以「家庭伦理」「伦理现实」「女性成长」这类正常短剧分类不会被误判。
2. **探针搜索**：用 `functional.adult_probe_keywords`（默认「麻豆传媒」「被家长调教的女教师」）再搜一遍。
   只要结果标题里出现探针关键词原文、工作室品牌或明确成人词，就判定为成人源——能搜出完整成人片名，
   说明站点确实收录了这类内容。

实测 220 个脚本命中 6 个：EcoHub影视（`伦理片` 分类）、ZIP0影视（能搜出
《家访后，被家长调教的女教师》）、悟空传媒、熊猫秒播、飞流视频、黄豆短剧。

如果某个源被误判，把文件名加进 `filters.adult_allow`（例如 `["ZIP0影视.py"]`）即可豁免。
代价是每个首页正常的脚本多 1–2 次搜索，整轮多约 17 秒。

### 低码率过滤

功能校验会为每个源取前 `quality.max_lines` 条线路（默认 4）各测一集，逐条量码率和分辨率：

- **HLS**：均匀抽 24 个分片，用 `Content-Length / EXTINF` 算平均码率。不用 master 里的
  `BANDWIDTH`——实测大量源写的是 `128`、`800000` 这种占位值，和分片实测能差 2 倍以上。
  分辨率也**不信任 master 的 `RESOLUTION`**：实测 26 条标 `1080x608` 的线路里 17 条真实分辨率
  不是它（含 `720x1280`、`1080x1920` 竖屏），所以统一用 `ffprobe` 读真实宽高，
  ffprobe 不可用/失败时才退回 master 的值。
- **mp4 / 直链视频**：用 `ffprobe` 读 `bit_rate` 和分辨率（需要本机装了 ffmpeg，没装就记为未知）。
- **音频源**（听书/音乐）和本地代理线路不参与码率判定。

阈值**按分辨率分档**，用短边 `min(width, height)` 判档（竖屏 720x1280 算 720p，不算 1440p）：

| 短边 | 最低码率 | 说明 |
|---|---|---|
| ≥1800 | 6000 kbps | 4K |
| ≥1400 | 3500 kbps | 2K |
| ≥1000 | 1600 kbps | 1080p（1569/1583 档算低，1609+ 保留） |
| ≥700 | 920 kbps | 720p（893 档算低，947+ 保留） |
| ≥460 | 600 kbps | 480p（481 档算低，752+ 保留） |
| ≥340 | 400 kbps | 360p |
| 更低 | 400 kbps | 按最低档处理 |
| 未知 | `quality.min_bitrate_kbps`（默认 800） | 测不出分辨率时回退 |

分辨率分档只能挡住「低分辨率 + 低码率」，挡不住「1080p 但码率只有 1.6–1.8 Mbps」的廉价转码，
所以再加一层 **bpp（每像素每帧比特数）下限**，最终阈值取两者较大值：

```
最低码率 = max(分辨率档阈值, quality.min_bpp × 宽 × 高 × fps / 1000)
```

`quality.min_bpp` 默认 **0.035**。fps 用 `ffprobe` 的 `avg_frame_rate`，取不到时按 25 算。
0.035 落在实测 1080p 的 bpp 空档里（0.0348 = 1802 kbps 算低，0.0359 = 1860 kbps 保留）；
50fps 的源按 50 计算（同画质约需两倍码率），实测 4 条 1080p50 线路都只有 1.7 Mbps、
bpp 0.017，会被剔除。设 `quality.min_bpp = 0` 可关闭这一层。

只有**所有采样线路都测到码率、且各自都低于自己的阈值**才剔除；任何一条线路高于阈值、
或者测不出来（解析线路、页面、本地代理、抽片失败），源都保留。音频源不参与判定。

实测 220 个脚本里 147 条视频线路能量出码率（96% 带分辨率），13 个源的所有线路都低于各自阈值：

- 分辨率档剔除 8 个：55影院（1038@720p）、八度影院（1739@1080p）、河马短剧（730@720p）、
  河马剧场（672@720p×2、481@540p）、瓜子APP（360@480p）、蜗牛影院（1569@1080p）、
  达达兔影视（1569@1080p）。
- bpp 下限额外剔除 5 个：剧下饭4K（两个副本，1637@1080p，bpp 0.032）、
  水牛影院1（1713/1569@1080p，bpp 0.033/0.030）、
  韩国电影网 / 风月影院 / 麻花影视（同一 1080p50 源，1724–1732 kbps，bpp 0.017）。

像滴答影院（1148@720p）、第七影院（1569/1802@1080p，另有一条测不到的线路）只要有一条过线或
测不到就保留；分享央视（480x270、486 kbps）按 270p 判不算低，也保留。`接口.json` 因此是 54 个站点。

单集采样会随剧集和 CDN 波动，个别源在不同轮次会进出名单（例如 6080影视上一轮 793@720p 被剔，
本轮 1040@720p 但被加载速度过滤剔除）。想让判定更稳，可以调大 `quality.max_lines` 或把源加进
`quality.bitrate_allow`。

调阈值就改 `quality.bitrate_thresholds`（键是短边，值是 kbps）；分辨率未知时的回退值改
`quality.min_bitrate_kbps`，bpp 下限改 `quality.min_bpp`，设 `0` 关闭码率过滤。如果某个源被误判，
把文件名加进 `quality.bitrate_allow`。

### 加载速度过滤

码率达标不代表能流畅播放：CDN 限速、线路绕路都会让播放器反复缓冲。功能校验会为每条 HLS 线路
测两个指标（只测前 2 个分片，每个最多下 2MB、最多 6 秒）：

- `playlist_ms`：拉取 master/媒体列表的耗时；
- `ttfb_ms`：首个分片的响应时间；
- `speed_ratio`：实测吞吐（含 TTFB）÷ 码率。`< 1` 表示下载速度追不上播放速度。

**为什么不是只测 256KB**：小样本会被 TCP 慢启动严重低估。实测大白鲨 10 秒分片用 256KB 测出
0.33x，下满 2MB 后是 1.2–1.5x；独播库从 0.48x 回到 1.3x。短分片（1–2 秒）本身不足 2MB，会整段下完。

线路判定为**加载慢**，满足任一条件即可：

| 条件 | 默认值 | 说明 |
|---|---|---|
| `speed_ratio` | `< 0.7` | 吞吐不到码率的 70%，实时播放会卡 |
| `playlist_ms + ttfb_ms` | `> 12000` | 点开要等 12 秒以上 |

和码率过滤一样，只有**所有采样线路都测到速度、且都慢**才剔除；任何一条线路快或测不出来都保留。
阈值取 12 秒是因为同一条线路的启动耗时实测能波动 2 倍（麒麟/独播库一次 4 秒、一次 9 秒），
阈值太低会按瞬时抖动误删。

本轮 147 条视频线路全部测到速度，5 个源的所有线路都慢：

| 源 | 线路实测 |
|---|---|
| 云朵视频（关梯） | 473/549 kbps = 0.45x/0.26x |
| 厂长资源 | 639 kbps = 0.57x，启动 3.2s |
| 无极电影网（关梯） | 734 kbps = 0.67x，启动 5.0s |
| 蝶卡影视 | 817 kbps = 0.68x，启动 2.9s |
| 麒麟影视 | 1028 kbps = 0.48x，启动 5.7s |

华谊影视是典型的「一条慢、一条快」：B超高清是 1080p/1566 kbps，但 CDN 只能跑到 0.42–0.55x，
会一直缓冲；K蓝光是 720p/1390 kbps，实测 23 Mbps（16.8x），非常流畅。按「有一条快就保留」，
华谊影视会留在 `接口.json` 里——播放时选 K蓝光即可，B超高清不要用。

调速度阈值就改 `quality.min_speed_ratio` 和 `quality.max_startup_ms`；设 `min_speed_ratio = 0`
关闭速度过滤。误判的源加进 `quality.speed_allow`。

### 线路级裁减

校验通过的脚本会**同步到 `脚本/` 目录**，`接口.json` 的 `api` 指向本地文件
`./脚本/<脚本名>.py`，不再走 gh-proxy。同步时给每个脚本末尾注入一段 `detailContent`
包装代码，按线路名过滤：

1. **手动黑名单**：`quality.line_prune.blacklist` 指定的线路无条件剔除，立即生效。
   华谊影视的 `F蓝光`（token 过期，HTTP 400）、`QQ蓝光`（404 页面）就是这样去掉的。
2. **低质量线路**：线路实测码率低于对应分辨率档阈值（含 bpp 下限），且同源**另有至少一条
   达标线路**时才剔除——不会把源删空。剔除要走两振：连续两轮低质量才删（见「两振出局」）。
3. **疑似不通线路**：HTTP 4xx/5xx 只作为提示打印（"疑似不通线路"），单集 token 过期是误报
   （华谊影视的 K蓝光某集返回 403、换集就 200），不自动剔除；连续两轮 4xx 才删。
   `line_prune.dead_status_min` 默认 `0`（禁用「单次 4xx 立即判死」）。

**为什么不用 HTTP 状态码自动判死**：线路 URL 是逐集带 token 的，某集的 403/404 只代表
那一集过期，不代表整条线路都坏。实测华谊影视的 K蓝光某集返回 403，但换一集或换时间段就正常，
按状态码剔除会误伤。确认死掉再加进 `line_prune.blacklist`。B超高清同理：单次慢不代表坏，
按「有一条快就保留」留在源里。

### 两振出局（稳定性）

单集采样 + CDN 抖动会让源/线路频繁进出名单。**两振出局**把「单轮判定」改成「连续两轮判定」：

- **源级**：本轮被判 `low_quality` / `low_bitrate` / `slow_stream` 的源，若上一轮也处于
  「剔除候选」，本轮才真剔除；否则保留一振（`strike1`），下一轮仍差才删。
- **线路级**：低质量/疑似不通线路同样连续两轮才裁减。
- 历史存 `reports/history.json`（每轮状态 + 连击数，保留最近 8 轮）。

**首轮基线**：`history.json` 不存在时，以上一轮已提交的 `接口.json` 为第 0 轮——上一轮已排除的
源视为已有第 1 振，本轮仍为候选则直接第 2 振剔除，避免首轮把上轮已过滤的源全部加回
（54→172 站）。这也意味着**第一轮不会出现 172 站的膨胀**，接口数量与上一轮基本持平。

**CI 每次全新**：`reports/` 被 gitignore，GitHub Actions 无历史 → 只保守保留，不删源。
两振的稳定裁减依赖本机跑 `run_local.py`（历史只存本机）。想在两振里看某源的判定，
看 `reports/validation-report.json` 的 `scripts[].status`，或手动跑完看输出的
「两振出局: ...」行。

```bash
# 查看/维护黑名单与豁免
python scripts/ban_line.py 华谊影视.py --line F蓝光 --line QQ蓝光      # 加黑名单
python scripts/ban_line.py 华谊影视.py --line F蓝光 --unban          # 取消
python scripts/ban_line.py 低端影视.py --bitrate                    # 码率豁免
python scripts/ban_line.py 麒麟影视.py --speed                      # 速度豁免
python scripts/ban_line.py 华谊影视.py --line K蓝光 --run            # 改完直接重跑
```

> `ban_line.py` 只改 `scripts/config.json`，不直接动脚本文件；线路裁减仍由 `update_api.py`
> 注入。你实际看片发现某源卡/某线路坏时，一行命令就能加进黑名单并重跑。

### 耗时与并发

一次完整流程（220 个脚本）约 **11 分钟**：

| 阶段 | 耗时 | 并发 |
|---|---|---|
| 功能校验 + 逐线路播放地址分析 | ~580s | 12 |
| 读取脚本 + host 校验 | ~75s | 12 / 20 |
| 提交推送 | ~5s | — |

逐线路采样是主要开销：每个 HLS 线路要抽 24 个分片（只请求响应头，不下载内容）、
跑一次 `ffprobe` 复核真实分辨率和 fps，再下 2 个分片测加载速度（每个最多 2MB）。
样本从 6 个加到 24 个是为了压住 VFR 分片的波动（6 个样本在个别源上能偏 16%，
24 个基本在 ±6% 以内）；分辨率必须实测，否则分档会用错档。网络慢的时候整轮能到 20 分钟以上，
定时任务留了 3 小时上限。速度测量每轮大约多下载 100–200MB（只测前 2 个分片）。

功能校验会把脚本缓存到 `%TEMP%\tvbox-py-cache`，生成阶段直接复用（`--source-dir`），
不再重复下载——之前重复下载 221 个文件要走 gh-proxy，光这一项就要 5 分钟。上游删掉的脚本
会自动从缓存清理。并发数在 `config.json` 里调：`functional.workers`（功能校验）、
`functional.stream_workers`（播放地址分析）、`request.workers`（host 校验）、
`request.download_workers`（下载）。

### 后续方向（未实现）

- **增量功能校验**：播放地址（线路 URL）逐集带 token、一周就失效，不能整行缓存 `run_one`
  结果。计划改为「缓存功能字段 + 只重取 detail 换新 URL」，上游没改的脚本跳过全量校验，
  把 11 分钟压到 3–5 分钟。
- **临界线路二次确认**：对码率/速度落在阈值 ±10% 的线路加测第 2 个视频（电影+剧集），
  避免单集波动误判；已并入两振出局（跨轮二次采样），单轮内复测未做。

### 自定义

编辑 `scripts/config.json`：

- `accelerator`：GitHub 加速前缀，默认 `https://gh-proxy.com/`。
- `exclude_scripts` / `exclude_names`：排除不想加入的脚本。
- `filters.require_spider_class`：只接受定义了 `class Spider` 的脚本，默认 `true`。
- `filters.dedupe_identical_scripts`：按代码内容去重改名副本，默认 `true`。
- `filters.exclude_adult`：剔除成人内容源，默认 `true`。
- `filters.adult_keywords` / `adult_title_keywords`：自定义分类/标题关键词，留空用内置词表。
- `filters.adult_allow`：误判豁免的文件名列表，例如 `["ZIP0影视.py"]`。
- `filters.ad_hosts`：已知广告/贴片域名片段列表（如 `["adcdn", "ads.example.com"]`），
  命中即记广告分；默认空列表表示不启用，无行为变化。
- `functional.adult_probe_keywords`：成人内容探针关键词，默认「麻豆传媒」「被家长调教的女教师」。
- `functional.enabled` / `functional.report`：是否自动读取功能校验报告。
- `functional.min_score`：最低功能评分（0–3），默认 `0` 表示只评分不删源。
- `functional.keyword` / `timeout` / `workers`：搜索关键词、单脚本超时、并发数。
- `quality.min_grade`：最低源质量等级（`A`/`B`/`C`/`D`），默认 `""` 不过滤；设为 `B` 会剔除 C/D。
- `quality.drop_unverified`：是否连「拿不到播放地址（U）」的源一起剔除，默认 `false`。
- `quality.min_bitrate_kbps`：分辨率未知时的回退最低码率（kbps），默认 `800`；设 `0` 关闭码率过滤。
- `quality.min_bpp`：每像素每帧最低比特数（bpp），默认 `0.035`；和分辨率档阈值取较大值，设 `0` 关闭。
- `quality.min_speed_ratio`：实测吞吐 ÷ 码率的下限，默认 `0.7`；设 `0` 关闭加载速度过滤。
- `quality.max_startup_ms`：播放列表 + 首个分片首字节的耗时上限（毫秒），默认 `12000`。
- `quality.bitrate_thresholds`：按分辨率（短边）分档的最低码率，默认见「低码率过滤」。
- `quality.max_lines`：每个源最多采样几条线路，默认 `4`；超出部分按未知处理，不会因此删源。
- `quality.bitrate_allow`：码率误判豁免的文件名列表，例如 `["低端影视.py"]`。
- `quality.speed_allow`：加载速度误判豁免的文件名列表。
- `quality.line_prune.enabled`：是否做线路级裁减（默认 `false`，本仓库 `true`）。
- `quality.line_prune.dead_status_min`：HTTP 状态码 ≥ 此值视为线路不可用，默认 `0`（禁用
  单次 4xx 立即判死，改走两振：连续两轮 4xx 才删）。
- `quality.line_prune.blacklist`：手动剔除线路名，键是脚本文件名，例如
  `{"华谊影视.py": ["F蓝光", "QQ蓝光"]}`。
- `local_spider_dir`：非空时把校验通过的脚本同步到该目录，并让 `接口.json` 的 `api`
  指向 `./<目录>/<脚本名>.py`；空字符串则仍用 gh-proxy 远程链接。同步会额外生成
  `接口-remote.json`（生成站点用绝对 gh-proxy 链接）。
- `request.accept_4xx`：是否把 403/404 等算作可达，默认 `true`。
- `request.timeout` / `request.workers`：请求超时和并发数。

### 保留自己的首页

在 `接口.json` 的 `sites` 里添加一个 `api` 以 `./` 开头的站点，例如：

```json
{
    "key": "home",
    "name": "首页",
    "type": 3,
    "api": "./脚本/首页.py"
}
```

每次自动更新都会保留它，只替换 http/https 开头的网络站点。