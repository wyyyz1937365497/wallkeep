from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPixmapCache
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .. import i18n, library
from .model import AssetModel

CARD_RADIUS = 10
IMAGE_MARGIN = 8
CAPTION_HEIGHT = 24


class WallpaperDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        QPixmapCache.setCacheLimit(128 * 1024)
        fallback = QIcon.fromTheme("image-x-generic")
        self._placeholder = fallback.pixmap(96, 96)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(218, 198)

    def _thumbnail(self, row: dict, size: QSize) -> QPixmap:
        sha = row["sha256"]
        key = f"wallkeep:{sha}:{size.width()}x{size.height()}"
        pixmap = QPixmapCache.find(key)
        if pixmap is not None:
            return pixmap
        path = library.thumb_path(sha)
        source = QPixmap(str(path)) if path.exists() else self._placeholder
        if source.isNull():
            source = self._placeholder
        scaled = source.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        QPixmapCache.insert(key, scaled)
        return scaled

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        row = index.data(AssetModel.AssetRole)
        if not row:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        card = QRectF(option.rect.adjusted(4, 4, -4, -4))

        background = QColor(palette.alternateBase().color())
        if selected:
            background = QColor(palette.highlight().color())
            background.setAlpha(48)
        elif hovered:
            background = QColor(palette.alternateBase().color()).lighter(108)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(card, CARD_RADIUS, CARD_RADIUS)

        border = QColor(palette.highlight().color()) if selected else QColor(palette.mid().color())
        border.setAlpha(230 if selected else 90)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border, 2 if selected else 1))
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), CARD_RADIUS, CARD_RADIUS)

        image_area = card.adjusted(IMAGE_MARGIN, IMAGE_MARGIN, -IMAGE_MARGIN, -CAPTION_HEIGHT - IMAGE_MARGIN)
        target = QSize(max(1, int(image_area.width())), max(1, int(image_area.height())))
        pixmap = self._thumbnail(row, target)
        if not pixmap.isNull():
            x = image_area.x() + (image_area.width() - pixmap.width()) / 2
            y = image_area.y() + (image_area.height() - pixmap.height()) / 2
            painter.drawPixmap(int(x), int(y), pixmap)

        font = QFont(option.font)
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        painter.setFont(font)
        if selected:
            painter.setPen(palette.highlightedText().color())
        else:
            painter.setPen(palette.text().color())

        source = f"@{row['source_user']}" if row.get("source_user") else i18n.tr("Local")
        caption = f"{row['width']}×{row['height']}   {source}"
        caption_rect = QRectF(
            card.x() + 10,
            card.bottom() - CAPTION_HEIGHT,
            card.width() - 20,
            CAPTION_HEIGHT - 4,
        )
        elided = painter.fontMetrics().elidedText(
            caption, Qt.TextElideMode.ElideMiddle, int(caption_rect.width())
        )
        painter.drawText(
            caption_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )
        painter.restore()
