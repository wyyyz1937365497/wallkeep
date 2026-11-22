from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import QLocale
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QWidget,
)

LANGUAGE = "en"

ZH = {
    "&File": "文件(&F)",
    "&Library": "图库(&L)",
    "&View": "视图(&V)",
    "&Help": "帮助(&H)",
    "Import folder…": "导入文件夹…",
    "Add X user…": "添加 X 用户…",
    "Sync": "同步",
    "Stop": "停止",
    "Settings": "设置",
    "Reload library": "重新载入图库",
    "Quit": "退出",
    "About Wallkeep": "关于 Wallkeep",
    "Index a folder of existing wallpapers": "将已有壁纸文件夹加入索引",
    "Download the media timeline of an X profile": "下载 X 用户的媒体时间线",
    "Sync the selected X user, or all X users": "同步选中的 X 用户，或全部 X 用户",
    "Search wallpapers…": "搜索壁纸…",
    "Activity": "活动",
    "Library": "图库",
    "X users": "X 用户",
    "No users yet": "还没有用户",
    "Dimensions": "尺寸",
    "Size": "大小",
    "Source": "来源",
    "Added": "添加时间",
    "SHA-256": "SHA-256",
    "Set as wallpaper": "设为壁纸",
    "Open": "打开",
    "Show in folder": "在文件夹中显示",
    "No wallpaper selected": "未选择壁纸",
    "Select a wallpaper to preview it": "选择一张壁纸以预览",
    "Preview unavailable": "无法预览",
    "Local file": "本地文件",
    "Local": "本地",
    "Open original post": "打开原帖",
    "Add X user": "添加 X 用户",
    "The media tab of this profile is downloaded with your browser login. "
    "Make sure x.com is logged in in the selected browser.": "将通过浏览器登录信息下载该用户的 Media 标签页。"
    "请确认所选浏览器中已登录 x.com。",
    "X username": "X 用户名",
    "username without @": "用户名，不含 @",
    "Cookie source": "Cookie 来源",
    "Cookie keyring": "Cookie 钥匙串",
    "GNOME keyring (libsecret)": "GNOME 钥匙串（libsecret）",
    "KWallet": "KWallet",
    "Basic": "Basic",
    "Auto": "自动",
    "X rejected the cookies. Set Cookie keyring to GNOME keyring, "
    "or log in to x.com again in the browser.": "X 拒绝了 Cookie。请把“Cookie 钥匙串”设为 GNOME 钥匙串，"
    "或在浏览器中重新登录 x.com。",
    "Proxy": "代理",
    "Cookies are read from the selected browser on every sync. "
    "No password or cookie value is stored by Wallkeep.": "每次同步都会从所选浏览器读取 Cookie。"
    "Wallkeep 不会保存密码或 Cookie 值。",
    "OK": "确定",
    "Cancel": "取消",
    "Wallkeep settings": "Wallkeep 设置",
    "X download folder": "X 下载文件夹",
    "Browse…": "浏览…",
    "Database and archives": "数据库与归档",
    "Local folders are indexed in place. X media is moved into the download folder above.": "本地文件夹只建立索引，不改动文件；"
    "X 媒体会移动到上方下载文件夹。",
    "Language": "语言",
    "System": "跟随系统",
    "Language changes take effect after restart.": "语言更改将在重启后生效。",
    "Similarity threshold": "相似度阈值",
    "pHash Hamming distance, 0 disables. Lower = stricter.": "pHash 汉明距离，0 表示关闭；数值越小越严格。",
    "Find duplicates…": "查找重复图片…",
    "Scan all images by pHash and review near-duplicates": "用 pHash 扫描全部图片并复核近似重复",
    "Duplicate images": "重复图片",
    "Scanning fingerprints…": "正在计算图片指纹…",
    "Computing fingerprints… {done}/{total}": "正在计算指纹… {done}/{total}",
    "Comparing fingerprints… {done}/{total}": "正在比对指纹… {done}/{total}",
    "No duplicates found": "没有找到重复图片",
    "No duplicates found at the current pHash threshold ({threshold}).": "当前 pHash 阈值（{threshold}）下没有找到重复图片。",
    "The similarity threshold is 0. Set it in Settings first.": "相似度阈值为 0，请先在设置中调大。",
    "Images are grouped by 64-bit pHash similarity. Unchecked images are kept; "
    "the largest file of each group is kept by default.": "图片按 64 位 pHash 相似度分组；未勾选的图片会保留，"
    "默认保留每组中体积最大的一张。",
    "Image": "图片",
    "Delete": "删除",
    "Group {index} · {count} images · {size}": "重复组 {index} · {count} 张 · {size}",
    "Keep largest, check the rest": "保留最大，勾选其余",
    "Delete checked…": "删除勾选…",
    "Keep at least one image in every group.": "每组至少保留一张图片。",
    "{count} files were permanently deleted because the trash was unavailable.": "{count} 个文件因回收站不可用而被永久删除。",
    "Some files could not be deleted": "部分文件无法删除",
    "No files were deleted.": "没有删除任何文件。",
    "Import wallpaper folder": "导入壁纸文件夹",
    "Ready": "就绪",
    "Stopping…": "正在停止…",
    "All wallpapers ({count})": "全部壁纸（{count}）",
    "Local ({count})": "本地（{count}）",
    "X ({count})": "X（{count}）",
    "@{user} ({count})": "@{user}（{count}）",
    "Last sync: {date}": "上次同步：{date}",
    "Last error: {error}": "上次错误：{error}",
    "Status: {status}": "状态：{status}",
    "No wallpapers match “{query}”.": "没有匹配“{query}”的壁纸。",
    "No wallpapers from @{user} yet.\nPress F5 or use Sync to download the media timeline.": "还没有 @{user} 的壁纸。\n"
    "按 F5 或点击“同步”下载媒体时间线。",
    "No local wallpapers indexed yet.\nImport a folder to index it in place.": "还没有本地壁纸索引。\n导入一个文件夹即可原地建立索引。",
    "No X wallpapers yet.\nAdd an X user and sync their media timeline.": "还没有 X 壁纸。\n添加 X 用户并同步其媒体时间线。",
    "Your wallpaper library is empty.\nImport an existing folder, or add an X user to download their media.": "壁纸库还是空的。\n"
    "导入已有文件夹，或添加 X 用户下载媒体。",
    "Indexing {name}…": "正在索引 {name}…",
    "Syncing {target}…": "正在同步 {target}…",
    "Syncing {count} X users…": "正在同步 {count} 个 X 用户…",
    "No X users": "没有 X 用户",
    "Add an X user first.": "请先添加 X 用户。",
    "Cannot create download folder": "无法创建下载文件夹",
    "Sync finished with errors": "同步完成，但有错误",
    "Sync cancelled": "同步已取消",
    "Sync complete": "同步完成",
    "Wallkeep error": "Wallkeep 错误",
    "Could not set wallpaper": "无法设置壁纸",
    "Wallpaper set via {method}": "壁纸已通过 {method} 设置",
    "Copy path": "复制路径",
    "Delete…": "删除…",
    "Moved {count} images to the trash.": "已将 {count} 张图片移到回收站。",
    "Could not move to trash": "无法移到回收站",
    "No images were deleted.": "没有删除任何图片。",
    "Wait for the current task to finish.": "请等待当前任务结束。",
    "Stop task?": "停止任务？",
    "A library task is still running. Stop it and quit?": "图库任务仍在运行。停止并退出？",
    "Invalid username": "用户名无效",
    "Enter an X username (1–15 letters, digits or _).": "请输入 X 用户名（1–15 位字母、数字或 _）。",
    "Invalid folder": "文件夹无效",
    "Choose a download folder.": "请选择下载文件夹。",
    "Cannot create folder": "无法创建文件夹",
    "Imported {imported} new, {duplicate} duplicates, {skipped} already indexed, {failed} failed.": "导入 {imported} 张新图，"
    "{duplicate} 张重复，{skipped} 张已索引，{failed} 张失败。",
    "{count} wallpaper": "{count} 张壁纸",
    "{count} wallpapers": "{count} 张壁纸",
    "<b>Wallkeep</b><br>A native wallpaper library for local collections and X media.<br><br>"
    "X downloads use gallery-dl with your browser cookies. Images are deduplicated by SHA-256.": "<b>Wallkeep</b><br>"
    "本地壁纸与 X 媒体的原生壁纸库。<br><br>"
    "X 下载通过 gallery-dl 使用浏览器 Cookie；图片按 SHA-256 去重。",
}


def _system_is_chinese() -> bool:
    if QLocale.system().name().lower().startswith("zh"):
        return True
    locale_name = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    )
    return locale_name.lower().startswith("zh")


def configure(setting: str = "auto") -> None:
    global LANGUAGE
    if setting in {"zh", "zh_CN", "zh_TW"}:
        LANGUAGE = "zh_CN"
    elif setting == "en":
        LANGUAGE = "en"
    else:
        LANGUAGE = "zh_CN" if _system_is_chinese() else "en"


def language() -> str:
    return LANGUAGE


def tr(text: str) -> str:
    if LANGUAGE == "zh_CN":
        return ZH.get(text, text)
    return text


def trf(text: str, **kwargs: Any) -> str:
    return tr(text).format(**kwargs)


def trn(singular: str, plural: str, count: int) -> str:
    source = singular if count == 1 else plural
    return tr(source).format(count=count)


def translate_widget_tree(root: QWidget) -> None:
    """Translate the static labels/actions created up to this point.

    Dynamic text (tree items, status messages, dialogs created later) is
    translated explicitly with tr()/trf() at the point where it is set.
    """
    if LANGUAGE == "en":
        return
    if root.windowTitle():
        root.setWindowTitle(tr(root.windowTitle()))
    for action in root.findChildren(QAction):
        if action.text():
            action.setText(tr(action.text()))
        if action.statusTip():
            action.setStatusTip(tr(action.statusTip()))
        if action.toolTip():
            action.setToolTip(tr(action.toolTip()))
    for widget in root.findChildren(QWidget):
        if widget.toolTip():
            widget.setToolTip(tr(widget.toolTip()))
        if isinstance(widget, (QPushButton, QCheckBox, QRadioButton)):
            if widget.text():
                widget.setText(tr(widget.text()))
        elif isinstance(widget, QLabel):
            text = widget.text()
            if text and not text.startswith("<"):
                widget.setText(tr(text))
        elif isinstance(widget, QLineEdit):
            if widget.placeholderText():
                widget.setPlaceholderText(tr(widget.placeholderText()))
        elif isinstance(widget, QComboBox):
            for index in range(widget.count()):
                widget.setItemText(index, tr(widget.itemText(index)))
        elif isinstance(widget, QDockWidget):
            widget.setWindowTitle(tr(widget.windowTitle()))
        elif isinstance(widget, QGroupBox):
            widget.setTitle(tr(widget.title()))
