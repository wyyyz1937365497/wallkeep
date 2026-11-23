# Wallkeep

本地优先的原生壁纸库：索引、浏览、搜索、分类、去重本地图片，并可选同步 X 用户的媒体时间线。

**下载能力来自 [gallery-dl](https://codeberg.org/mikf/gallery-dl)，不是 Wallkeep。** Wallkeep 不实现 X 抓取、GraphQL 客户端、Cookie 提取/解密或媒体下载；可选的 X 同步只是调用 gallery-dl，并把下载结果纳入本地壁纸库管理。项目本质是本地壁纸管理的延伸。

界面使用系统 Qt 平台主题（Darkly/Breeze、KDE 配色和字体），不带自定义样式表，所以在当前桌面里不会突兀；支持简体中文/英文自动切换。

## 定位

- **做**：本地目录索引、缩略图、搜索、来源分类、SHA-256 + pHash 去重、回收站删除、设置壁纸、可选的 X 同步入口与结果管理。
- **不做**：X 爬虫、GraphQL 客户端、Cookie 提取/解密、下载器；这些全部由 `gallery-dl` 负责。
- `gallery-dl` 以独立进程运行；Wallkeep 通过命令行和文件与它交互。

## 功能

- **本地壁纸索引**：导入已有文件夹，原地索引，不移动/复制原文件。
- **可选 X 同步（下载由 gallery-dl 完成）**：通过 `gallery-dl` 读取浏览器 Cookie，下载 `x.com/<user>/media` 的图片时间线；支持增量同步、代理。
- **精确去重**：SHA-256，同一文件无论来自本地还是 X 都只保留一份。
- **感知去重**：64 位 DCT pHash（Hamming 距离）+ 宽高比守卫，识别被反复转发、缩放、重压缩的同一张图；重复的 X 媒体只记录来源，不落第二份文件。
- **SQLite 图库**：媒体路径、来源、尺寸、哈希、同步游标和去重信息统一保存。
- **原生浏览**：缩略图网格、详情预览、搜索、按来源过滤、设为壁纸（quickshell / swww / hyprpaper）。
- **右键删除**：图片右键 → “删除…”，不弹确认框，直接移到系统回收站；数据库记录和缩略图同步清理，X 来源标记为 `deleted`。
- **中文界面**：按系统语言自动检测，也可在设置中固定语言（重启生效）。

## 安装与运行

```bash
cd wallkeep
uv sync          # pyproject 已把默认 PyPI 索引设为 USTC 镜像
uv run wallkeep
```

系统要求：Linux、Python 3.11+、`gallery-dl`（由 `uv sync` 安装）。

### 发行包

- **Debian/Ubuntu**（trixie 及更新）：下载 Release 中的 `wallkeep_0.1.0_all.deb`，然后
  `sudo apt install ./wallkeep_0.1.0_all.deb`。
- **Arch Linux**：AUR 包 `wallkeep`；PKGBUILD 在 `packaging/aur/`。

如果希望从桌面启动并让 XDG portal 识别应用 ID：

```bash
uv tool install .
install -Dm644 packaging/wallkeep.desktop ~/.local/share/applications/wallkeep.desktop
```

## 使用 X 下载

1. 在 Firefox/Chrome/Chromium/Brave/Edge 中登录 [x.com](https://x.com)。
2. 点击“添加 X 用户…”，输入用户名（不含 `@`），选择你登录的浏览器。
3. 如果直连 X 需要代理，在“设置”或添加用户对话框里填写（例如 `http://127.0.0.1:7890`）。
4. 同步时 `gallery-dl` 会从浏览器读取 Cookie；Wallkeep 不保存密码或 Cookie 值。

同步过程中，每张图片及其 JSON sidecar 写完后会立即导入 SQLite；界面约每 1.5 秒批量插入新图，不重建整个视图，侧栏计数在同步结束时汇总刷新。新图片出现在列表顶部。

同步运行在独立的 `wallkeep.sync_cli` 进程里，Qt 主进程只读取日志和 SQLite；即使下载/导入 helper 崩溃，主窗口也不会一起退出。

X 的 Web 接口和 GraphQL query id 会变化；下载层使用 `gallery-dl`，升级它即可跟上变化：

```bash
uv sync --upgrade-package gallery-dl
```

### Cookie 解密 / `AuthRequired`

Chromium 系浏览器会用系统钥匙串加密 Cookie。Wallkeep 默认对 Chrome/Chromium/Edge/Brave 使用 `+gnomekeyring`（依赖已安装的 `secretstorage`），Edge 实测可正确解出 `auth_token` / `ct0`。

如果仍提示 `AuthRequired` 或 `could not be decrypted`：

1. 设置 → **Cookie 钥匙串**，依次尝试 `GNOME keyring`、`KWallet`、`Auto`。
2. 确认浏览器里仍然登录着 x.com，然后重新同步。
3. 仍不行可以改用 Firefox（Cookie 不加密），或把 Cookie 导出为 `cookies.txt` 后用 `gallery-dl --cookies` 手动下载。

Wallkeep 不保存密码或 Cookie 值；同步时由 `gallery-dl` 读取。

请遵守 X 的服务条款，控制同步频率，只下载你有权保存的内容。

## 去重规则

- 精确重复：相同 SHA-256 → 不新增文件。
- 近似重复：pHash Hamming 距离 ≤ 阈值（默认 8），且宽高比差异 ≤ 8%：
  - 已有本地壁纸与 X 转发图会匹配，X 图不会重复落盘；
  - 同一 X 图被多个账号转发时，只保留第一份媒体文件；
  - 低方差（纯色/近纯色）图片不生成 pHash，避免感知哈希误判，仍靠 SHA-256 精确去重。
- 阈值在“设置 → Similarity threshold”调整；`0` 关闭近似去重，数值越小越严格。
- 每次匹配的 `match_asset_id / match_distance / match_kind` 会写入 `sources` 表，便于审计。

## 重复图片复核

点击工具栏或 `图库 → 查找重复图片…`：

1. 对没有 pHash 的图片补算指纹，已有指纹直接复用。
2. 按当前 `Similarity threshold` 对全部图片做两两 pHash 比对，列出重复组。
3. 每组默认保留体积最大的一张，其余打勾；也可以手动改勾选，逐张决定。
4. 点击“删除勾选…”后直接执行（不再二次确认），文件移到系统回收站（回收站不可用时才永久删除），并把被删图片的 X 来源重新指向保留的那张，随后清理数据库记录和缩略图。

## 数据位置

| 内容 | 路径 |
| --- | --- |
| SQLite 图库 | `~/.local/share/wallkeep/wallkeep.db` |
| gallery-dl archive | `~/.local/share/wallkeep/archives/` |
| 下载暂存 | `~/.local/share/wallkeep/staging/` |
| 缩略图缓存 | `~/.cache/wallkeep/thumbs/` |
| X 下载目录 | 默认 `~/Pictures/wallkeep`，可在设置里修改 |

本地文件夹只建立索引；X 媒体会移动到下载目录的 `x/<user>/` 下。

## 主题与语言

- 启动时把 `/usr/lib/qt6/plugins` 加入 `QT_PLUGIN_PATH`，让 PySide6 使用系统的 KDE 平台主题和 Darkly/Breeze 风格。
- 不设置全局 stylesheet；颜色、字体、图标全部来自系统 Qt 设置。
- 语言：跟随系统 / English / 简体中文（设置中修改后重启）。

## 已知限制

- 目前只入库图片（jpg/jpeg/png/webp）；视频和 GIF 不进入壁纸库。
- X 登录依赖浏览器 Cookie，Cookie 过期后需要重新登录再同步。
- 近似去重是保守策略：裁切比例较大的转发图可能不会被合并。
- 暂无重复项人工复核界面；匹配记录已写入数据库，后续可加。

## License

MIT，见 [LICENSE](LICENSE)。
