# Wallkeep

原生 Qt/PySide6 壁纸库：索引本地壁纸，并把 X（Twitter）用户的 Media 时间线下载成可浏览、可去重的壁纸收藏。

界面使用系统 Qt 平台主题（Darkly/Breeze、KDE 配色和字体），不带自定义样式表，所以在当前桌面里不会突兀；支持简体中文/英文自动切换。

## 功能

- **本地壁纸索引**：导入已有文件夹，原地索引，不移动/复制原文件。
- **X 用户同步**：通过 `gallery-dl` 读取浏览器 Cookie，下载 `x.com/<user>/media` 的图片时间线；支持增量同步、代理。
- **精确去重**：SHA-256，同一文件无论来自本地还是 X 都只保留一份。
- **感知去重**：64 位 DCT pHash（Hamming 距离）+ 宽高比守卫，识别被反复转发、缩放、重压缩的同一张图；重复的 X 媒体只记录来源，不落第二份文件。
- **SQLite 图库**：媒体路径、来源、尺寸、哈希、同步游标和去重信息统一保存。
- **原生浏览**：缩略图网格、详情预览、搜索、按来源过滤、设为壁纸（quickshell / swww / hyprpaper）。
- **中文界面**：按系统语言自动检测，也可在设置中固定语言（重启生效）。

## 安装与运行

```bash
cd wallkeep
uv sync          # pyproject 已把默认 PyPI 索引设为 USTC 镜像
uv run wallkeep
```

系统要求：Linux、Python 3.11+、`gallery-dl`（由 `uv sync` 安装）。

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

X 的 Web 接口和 GraphQL query id 会变化；下载层使用 `gallery-dl`，升级它即可跟上变化：

```bash
uv sync --upgrade-package gallery-dl
```

请遵守 X 的服务条款，控制同步频率，只下载你有权保存的内容。

## 去重规则

- 精确重复：相同 SHA-256 → 不新增文件。
- 近似重复：pHash Hamming 距离 ≤ 阈值（默认 8），且宽高比差异 ≤ 8%：
  - 已有本地壁纸与 X 转发图会匹配，X 图不会重复落盘；
  - 同一 X 图被多个账号转发时，只保留第一份媒体文件；
  - 低方差（纯色/近纯色）图片不生成 pHash，避免感知哈希误判，仍靠 SHA-256 精确去重。
- 阈值在“设置 → Similarity threshold”调整；`0` 关闭近似去重，数值越小越严格。
- 每次匹配的 `match_asset_id / match_distance / match_kind` 会写入 `sources` 表，便于审计。

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
