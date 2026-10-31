# Tvbox4.x_api

适配安卓4.x的tvbox接口

- 源地址：https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json
- Github加速地址：https://gh-proxy.com/https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json
- 远程直链版（生成站点用 gh-proxy 绝对链接，不带 `脚本/` 目录也能用）：
  https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口-remote.json

说明：由于盒子是安卓4.x会导致加载一些新的接口会崩溃、无法加载、无法播放等异常情况，
况且有些线路含18禁内容不适合在电视上展示，以及一些线路含赌博广告、播放卡顿等问题都需要清除。

1. 符合下面要求的接口会添加进接口给电视用。
2. 在电视盒子上接口加载正常；自营线路播放正常。
3. 不存在18禁内容，比如伦理、福利等分类；搜索「女教师」等关键字无漏点图。
4. 无赌博广告，播放不卡顿，比如 cms 资源站的资源一般都不合格。
5. 直播使用本地电信组播 IPTV 源，需要路由器启用 IGMP 嗅探。

## 自动更新

`scripts/update_api.py` 从**多个上游仓库**（`config.json` 的 `upstream` 列表，默认
`wzxxcz/wzxxcz` + `zzq1234567890/tvbox1` + `jak0099/dr`）拉取 py 脚本，按文件名去重，
校验后同步到 `脚本/` 目录、重建 `接口.json`，定时在**本机**运行（Windows 任务计划程序）。

```powershell
# 先手动跑一次，确认能生成、能推送
python scripts/run_local.py --dry-run     # 只校验，不写文件
python scripts/run_local.py               # 校验 + 生成 + 提交推送

# 注册每周任务（默认每周一 02:00）
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1
```

`run_local.py` 每次：`git pull` → 可选功能校验（`--functional`）→ 重建 `接口.json` →
有变化才提交推送。日志写在 `logs/local-run-<时间>.log`。

`接口.json` 的生成站点 `api` 指向本地 `./脚本/<脚本名>.py`（随仓库发布）；
`接口-remote.json` 用 gh-proxy 绝对链接，只发布单个 JSON 也能用。

## 筛选机制（概述）

`接口.json` 只保留**验证过的高质量源**，过滤走「两振出局」（连续两轮差才剔除）：

| 机制 | 说明 |
|---|---|
| 功能校验 | 真正调用 `homeContent`/`searchContent`/`detailContent`，每项 1 分（满分 3） |
| 源质量分级 | A 自营 / B 第三方直连 / C 搬运解析 / U 未验证；只留 A/B（`min_grade=B`、`drop_unverified=true`） |
| 低码率过滤 | 按分辨率分档 + bpp 下限（`min_bpp=0.05`），只留真正高码率源 |
| 加载速度过滤 | 实测吞吐/启动耗时，只留流畅源 |
| 线路级裁减 | 给脚本注入过滤，去掉不通/低质/慢速线路（同源另有达标线路才删） |
| 成人内容过滤 | 分类名 + 探针搜索，自动剔除 |

站点按**质量排序**：等级 → 功能评分 → 最高 bpp（画质密度）→ 速度比 → 名称，接口第一个就是最好的源。

详细规则、阈值、判定逻辑见 [docs/技术说明.md](docs/技术说明.md)。

## 配置

编辑 `scripts/config.json`，常用项：

| 配置 | 默认 | 说明 |
|---|---|---|
| `upstream` | 3 个仓库 | 上游 py 脚本仓库列表（`owner/repo/branch/path`），按文件名去重合并 |
| `quality.min_grade` | `"B"` | 最低源质量等级（A/B/C/D），设 `""` 不过滤 |
| `quality.drop_unverified` | `true` | 连「拿不到播放地址（U）」的源一起剔除 |
| `quality.min_bpp` | `0.05` | 每像素每帧最低比特数，设 `0` 关闭 |
| `quality.min_speed_ratio` | `0.7` | 实测吞吐 ÷ 码率下限，设 `0` 关闭 |
| `quality.max_startup_ms` | `12000` | 播放列表+首个分片首字节耗时上限（毫秒） |
| `quality.line_prune.dead_status_min` | `0` | 4xx 视为死线路的状态码下限；`0`=连续两轮 4xx 才删 |
| `quality.line_prune.blacklist` | `{}` | 手动剔线路名，默认空（交给规则自动走两振） |
| `exclude_scripts` / `exclude_names` | `[]` | 排除不想加入的脚本 / 站点 |
| `quality.bitrate_allow` / `speed_allow` | `[]` | 码率 / 速度误判豁免 |
| `filters.exclude_adult` | `true` | 成人内容过滤 |
| `filters.adult_allow` | `[]` | 成人误判豁免 |
| `jsm_sync` | 开启 | 从 `qist/tvbox` 的 `jsm.json` 同步 `hosts`/`doh`/`rules`/`ads` |

完整配置清单、阈值表见 [docs/技术说明.md](docs/技术说明.md)。

## 自定义

- **保留自己的首页**：`sites` 里加一个 `api` 以 `./` 开头的站点（如 `./脚本/首页.py`），
  自动更新只替换 http/https 开头的网络站点，它保留。
- **`lives`（广东IPTV组播）和 `wallpaper`（深色壁纸）**是自定义字段，不会被 jsm 同步覆盖；
  `hosts`/`doh`/`rules`/`ads` 始终跟随上游 `jsm.json`。

## 开发工具

```bash
python scripts/update_api.py --dry-run         # 只校验不写
python scripts/functional_check.py --limit 20  # 功能校验（跑第三方代码，建议虚拟机）
python scripts/stream_check.py "<m3u8>" --site-host https://x.com   # 单独看某个播放地址
python scripts/ban_line.py 某源.py --line 某线路  # 手动剔线路（默认不用，交给规则）
```
