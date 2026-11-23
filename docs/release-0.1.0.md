# Wallkeep 0.1.0

Wallkeep 是一个**本地优先的壁纸库**：索引、浏览、搜索、分类、去重本地图片，并可选地把下载结果纳入管理。

> **下载不是 Wallkeep 实现的。** 可选的 X 媒体同步完全由 [gallery-dl](https://codeberg.org/mikf/gallery-dl) 完成；Wallkeep 只调用它，并管理下载后的文件。项目不包含 X 爬虫、GraphQL 客户端、Cookie 提取/解密或下载器实现。

## 功能

- 本地文件夹原地索引，不移动原始壁纸。
- 缩略图网格、详情预览、搜索、按来源过滤。
- SHA-256 精确去重 + 64 位 DCT pHash 近似去重（可调阈值）。
- 重复图片复核：按组列出，默认保留体积最大的一张，可逐张勾选删除。
- 右键删除，直接移到系统回收站。
- 通过 quickshell / swww / hyprpaper 设置壁纸。
- 可选 X 媒体时间线同步：由 `gallery-dl` 读取浏览器 Cookie 并下载；Wallkeep 只负责启动、日志和入库。
- 简体中文 / English 界面，跟随系统 Qt 主题。

## 安装

### Debian / Ubuntu

需要 trixie 或更新（PySide6 6.8+）：

```bash
sudo apt install ./wallkeep_0.1.0_all.deb
wallkeep
```

### Arch Linux

AUR 包 `wallkeep`，或使用仓库中的 `packaging/aur/PKGBUILD`：

```bash
makepkg -si
```

### 从源码

```bash
uv sync
uv run wallkeep
```

## 说明

- X 下载依赖浏览器登录态与 `gallery-dl`；Cookie 过期后重新登录浏览器即可。
- Wallkeep 不保存密码或 Cookie 值；同步在独立的 Qt-free helper 进程中运行。
- 请遵守 X 的服务条款，仅保存你有权保存的内容。

## License

MIT
