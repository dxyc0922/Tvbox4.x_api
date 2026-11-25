# Tvbox4.x_api

面向安卓 4.x 电视盒子的 TVBox 接口：从多个上游同步 py 脚本，校验后生成精简、可用的 `接口.json`。

- 接口：https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json
- 加速：https://gh-proxy.com/https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json
- 远程直链版（`脚本/` 目录缺失时可用）：https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口-remote.json

## 使用

```powershell
python scripts/run_local.py --dry-run                                    # 只校验
python scripts/run_local.py                                              # 校验 + 生成 + 提交推送
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1       # 注册每周任务
```

`run_local.py` 每次：`git pull` → 可选功能校验（`--functional`）→ 重建 `接口.json` → 有变化才提交推送。
日志在 `logs/local-run-<时间>.log`。

生成站点的 `api` 指向仓库内 `./脚本/<脚本名>.py`；`接口-remote.json` 使用 gh-proxy 绝对链接。

## 筛选规则

详细说明见 [docs/技术说明.md](docs/技术说明.md)。

- 功能校验（`searchContent` / `detailContent` / `playerContent`）任一失败即剔除。搜索词默认固定 `仙逆`。
- 成人内容多道门槛：分类命中 ≥2 → 纯色情源剔除；只命中 1 → 按色情片来源类型决定
  「保留源并屏蔽该类型」或「剔除脚本」。不使用分类白名单。
- 纯资源站聚合源剔除，混合源只剔资源站线路；不通/低质线路走两振裁减。
- 质量分级、低码率、速度过滤默认关闭（`quality.enabled=false`），等级只展示不过滤。
- 站点不按质量重排，保持上游去重后的顺序。

## 配置

编辑 `scripts/config.json`，常用项：

| 配置 | 默认 | 说明 |
|---|---|---|
| `upstream` | 4 个仓库 | 上游 py 脚本仓库列表 |
| `exclude_scripts` / `exclude_names` | `[]` | 排除指定脚本 / 站点 |
| `filters.exclude_adult` | `true` | 成人内容过滤 |
| `filters.adult_allow` | `["豆瓣.py"]` | 整源豁免（不参与成人门槛） |
| `filters.category_filter.enabled` | `true` | 固定分类混合源的三点分类过滤 |
| `functional.fixed_keyword` | `"仙逆"` | 功能校验固定搜索词；`--keyword` 可覆盖 |
| `functional.adult_probe_keywords` | `["女教师", "自拍"]` | 成人内容探针关键词 |
| `quality.enabled` | `false` | 质量分级 / 低码率 / 速度过滤总开关 |
| `preserve_sites` | `["豆瓣.py", "哔哩.py"]` | 自定义站点，更新时不重新生成、不删除 |

完整配置见 [docs/技术说明.md](docs/技术说明.md)。

## 自定义

- `sites` 中 `api` 以 `./` 开头的站点会被保留，自动更新只替换 http/https 站点。
- `lives`（广东 IPTV 组播）和 `wallpaper` 是自定义字段，不会被 jsm 同步覆盖；
  `hosts` / `doh` / `rules` / `ads` 始终跟随上游 `jsm.json`。

## 开发

```bash
python scripts/update_api.py --dry-run         # 只校验不写
python scripts/functional_check.py --limit 20  # 功能校验（执行第三方脚本，建议在隔离环境）
python scripts/stream_check.py "<m3u8>"        # 单独检测播放地址
python scripts/search_new_sources.py           # 搜索候选新源
```
