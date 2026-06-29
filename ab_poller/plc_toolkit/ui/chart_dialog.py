"""Live trend chart dialogs for Browse inspector and Monitor tab."""

from __future__ import annotations

from collections import deque
from typing import Callable, Optional

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from plc_toolkit.ui.stamp_panel import StampReadingsPanel

_SERIES_COLORS = (
    "#4ECB73",
    "#1565C0",
    "#E6A817",
    "#E57373",
    "#BA68C8",
    "#4DD0E1",
    "#FF8A65",
    "#AED581",
)


class TrendChartWidget(QFrame):
    """Multi-series trend chart with vertical cursor and click-to-stamp."""

    MARGIN_LEFT = 52
    MARGIN_RIGHT = 16
    MARGIN_TOP = 28
    MARGIN_BOTTOM = 36

    stamp_added = Signal(list)  # list[tuple[name, time_label, value]]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)
        self._series: dict[str, deque[float]] = {}
        self._labels: dict[str, deque[str]] = {}
        self._colors: dict[str, QColor] = {}
        self._title = ""
        self._plot_rect = None
        self._cursor_x: Optional[int] = None
        self._hover_readout = QLabel("")
        self._hover_readout.setObjectName("hint")
        self._hover_readout.setWordWrap(True)
        self._hover_readout.setText(
            "Move across the chart for readings · click to stamp values below"
        )

    def hover_label(self) -> QLabel:
        return self._hover_readout

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    def set_series_names(self, names: list[str]) -> None:
        self._series = {n: deque(maxlen=240) for n in names}
        self._labels = {n: deque(maxlen=240) for n in names}
        self._colors = {
            n: QColor(_SERIES_COLORS[i % len(_SERIES_COLORS)])
            for i, n in enumerate(names)
        }
        self.update()

    def replace_series_data(
        self, name: str, points: list[tuple[str, float]],
    ) -> None:
        if name not in self._series:
            return
        trimmed = points[-240:]
        self._series[name] = deque((p[1] for p in trimmed), maxlen=240)
        self._labels[name] = deque((p[0] for p in trimmed), maxlen=240)
        self.update()

    def replace_series(self, name: str, values: list[float]) -> None:
        labels = [str(i + 1) for i in range(len(values))]
        self.replace_series_data(name, list(zip(labels, values)))

    def _plot_area(self):
        rect = self.rect()
        plot = rect.adjusted(
            self.MARGIN_LEFT, self.MARGIN_TOP,
            -self.MARGIN_RIGHT, -self.MARGIN_BOTTOM,
        )
        return rect, plot

    def _index_for_x(self, mouse_x: int, n: int, plot) -> int:
        if n <= 1:
            return 0
        frac = (mouse_x - plot.left()) / max(plot.width(), 1)
        frac = max(0.0, min(1.0, frac))
        return max(0, min(n - 1, round(frac * (n - 1))))

    def samples_at_x(self, mouse_x: int) -> list[tuple[str, str, float]]:
        """Nearest sample per series at the cursor's horizontal position."""
        _rect, plot = self._plot_area()
        if plot.width() < 1:
            return []
        out: list[tuple[str, str, float]] = []
        for name, samples in self._series.items():
            pts = list(samples)
            if not pts:
                continue
            labels = list(self._labels.get(name, []))
            idx = self._index_for_x(mouse_x, len(pts), plot)
            time_lbl = labels[idx] if idx < len(labels) else str(idx + 1)
            out.append((name, time_lbl, pts[idx]))
        return out

    def _update_hover(self, mouse_x: int) -> None:
        _rect, plot = self._plot_area()
        if not plot.contains(mouse_x, plot.center().y()):
            self._cursor_x = None
            self._hover_readout.setText(
                "Move across the chart for readings · click to stamp values below"
            )
            self.update()
            return
        self._cursor_x = mouse_x
        rows = self.samples_at_x(mouse_x)
        if not rows:
            self._hover_readout.setText("No samples yet")
        else:
            lines = [f"{name}  ·  {ts}  ·  {val:g}" for name, ts, val in rows]
            self._hover_readout.setText("\n".join(lines))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect, plot = self._plot_area()
        self._plot_rect = plot
        p.fillRect(rect, QColor("#141414"))

        if plot.width() < 20 or plot.height() < 20:
            p.end()
            return

        p.setPen(QPen(QColor("#333333"), 1))
        for i in range(5):
            y = plot.top() + int(i * plot.height() / 4)
            p.drawLine(plot.left(), y, plot.right(), y)

        all_vals: list[float] = []
        for samples in self._series.values():
            all_vals.extend(samples)
        if len(all_vals) < 1:
            p.setPen(QColor("#888888"))
            p.drawText(plot, Qt.AlignCenter, "Waiting for numeric samples…")
            p.end()
            return

        lo = min(all_vals)
        hi = max(all_vals)
        if lo == hi:
            lo -= 1.0
            hi += 1.0
        rng = hi - lo

        p.setPen(QColor("#AAAAAA"))
        font = QFont(p.font())
        font.setPointSize(8)
        p.setFont(font)
        for i in range(5):
            y = plot.top() + int(i * plot.height() / 4)
            val = hi - (i / 4) * rng
            p.drawText(4, y + 4, f"{val:.4g}")

        if self._title:
            title_font = QFont(font)
            title_font.setPointSize(10)
            title_font.setBold(True)
            p.setFont(title_font)
            p.setPen(QColor("#E8ECF1"))
            p.drawText(
                rect.adjusted(8, 4, -8, 0),
                Qt.AlignTop | Qt.AlignHCenter,
                self._title,
            )

        legend_x = plot.left()
        legend_y = rect.bottom() - 14
        p.setFont(font)
        for name in self._series:
            color = self._colors.get(name, QColor("#4ECB73"))
            p.setPen(color)
            p.drawText(legend_x, legend_y, name)
            legend_x += p.fontMetrics().horizontalAdvance(name) + 18

        cursor_hits: list[tuple[str, int, int]] = []
        for name, samples in self._series.items():
            if len(samples) < 1:
                continue
            pts = list(samples)
            n = len(pts)
            color = self._colors.get(name, QColor("#4ECB73"))
            pen = QPen(color, 2)
            p.setPen(pen)
            for i in range(n):
                x = (
                    plot.left() + int(i * plot.width() / max(n - 1, 1))
                    if n > 1
                    else plot.left() + plot.width() // 2
                )
                y = plot.bottom() - int((pts[i] - lo) / rng * plot.height())
                if i > 0:
                    x0 = plot.left() + int((i - 1) * plot.width() / (n - 1))
                    y0 = plot.bottom() - int(
                        (pts[i - 1] - lo) / rng * plot.height()
                    )
                    p.drawLine(x0, y0, x, y)
            p.setBrush(color)
            for i in range(n):
                x = (
                    plot.left() + int(i * plot.width() / max(n - 1, 1))
                    if n > 1
                    else plot.left() + plot.width() // 2
                )
                y = plot.bottom() - int((pts[i] - lo) / rng * plot.height())
                p.drawEllipse(QPoint(x, y), 3, 3)
            if self._cursor_x is not None and plot.left() <= self._cursor_x <= plot.right():
                cidx = self._index_for_x(self._cursor_x, n, plot)
                cx = (
                    plot.left() + int(cidx * plot.width() / max(n - 1, 1))
                    if n > 1
                    else plot.left() + plot.width() // 2
                )
                cy = plot.bottom() - int((pts[cidx] - lo) / rng * plot.height())
                cursor_hits.append((name, cx, cy))

        if self._cursor_x is not None and plot.left() <= self._cursor_x <= plot.right():
            p.setPen(QPen(QColor("#E8ECF1"), 1, Qt.DashLine))
            p.drawLine(self._cursor_x, plot.top(), self._cursor_x, plot.bottom())
            for _name, cx, cy in cursor_hits:
                p.setPen(QPen(QColor("#FFFFFF"), 2))
                p.setBrush(QColor("#FFFFFF"))
                p.drawEllipse(QPoint(cx, cy), 5, 5)

        p.end()

    def mouseMoveEvent(self, event) -> None:
        self._update_hover(int(event.position().x()))

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        mouse_x = int(event.position().x())
        _rect, plot = self._plot_area()
        if not plot.contains(mouse_x, int(event.position().y())):
            return
        rows = self.samples_at_x(mouse_x)
        if rows:
            self.stamp_added.emit(rows)

    def leaveEvent(self, _event) -> None:
        self._cursor_x = None
        self._hover_readout.setText(
            "Move across the chart for readings · click to stamp values below"
        )
        self.update()


class TagChartDialog(QDialog):
    """Live chart for a single tag (Browse inspector)."""

    def __init__(
        self,
        tag: str,
        history_getter: Callable[[], list],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Chart — {tag}")
        self.resize(760, 560)
        self._tag = tag
        self._history_getter = history_getter
        self._stamp_count = 0

        hint = QLabel(
            "Move across the chart to read values · click to stamp a snapshot below."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        self.chart = TrendChartWidget()
        self.chart.set_title(tag)
        self.chart.set_series_names([tag])
        self.chart.stamp_added.connect(self._on_stamp)

        self.stamp_panel = StampReadingsPanel(max_height=130)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)

        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(self.chart, 1)
        lay.addWidget(self.chart.hover_label())
        lay.addWidget(self.stamp_panel)
        lay.addWidget(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _on_stamp(self, rows: list[tuple[str, str, float]]) -> None:
        self._stamp_count += 1
        log = self.stamp_panel.stamps_log
        if self._stamp_count > 1:
            log.append("")
        lines = [f"--- Stamp {self._stamp_count} ---"]
        for name, ts, val in rows:
            lines.append(f"  {name}  ·  {ts}  ·  {val:g}")
        log.append("\n".join(lines))

    def _refresh(self) -> None:
        history = list(self._history_getter())
        points: list[tuple[str, float]] = []
        for entry in reversed(history):
            if len(entry) < 3:
                continue
            ts, qual, val, *_rest = entry
            if qual != "Good":
                continue
            try:
                points.append((str(ts), float(val)))
            except (TypeError, ValueError):
                continue
        if points:
            self.chart.replace_series_data(self._tag, points)


class MonitorChartDialog(QDialog):
    """Multi-tag chart from Monitor watch-list samples."""

    def __init__(
        self,
        tags: list[str],
        series_getter: Callable[[str], list[tuple[str, float]]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Monitor chart")
        self.resize(860, 620)
        self._tags = tags
        self._series_getter = series_getter
        self._stamp_count = 0

        hint = QLabel(
            f"Live chart for {len(tags)} tag(s). Move left/right for all values "
            f"at that time · click to stamp readings below. Each tag shows its "
            f"own nearest sample timestamp."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        self.chart = TrendChartWidget()
        title = " · ".join(tags[:3]) + ("…" if len(tags) > 3 else "")
        self.chart.set_title(title)
        self.chart.set_series_names(tags)
        self.chart.stamp_added.connect(self._on_stamp)
        for tag in tags:
            self.chart.replace_series_data(tag, series_getter(tag))

        self.stamp_panel = StampReadingsPanel(max_height=160)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)

        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(self.chart, 1)
        lay.addWidget(self.chart.hover_label())
        lay.addWidget(self.stamp_panel)
        lay.addWidget(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def _on_stamp(self, rows: list[tuple[str, str, float]]) -> None:
        self._stamp_count += 1
        log = self.stamp_panel.stamps_log
        if self._stamp_count > 1:
            log.append("")
        lines = [f"--- Stamp {self._stamp_count} ---"]
        for name, ts, val in rows:
            lines.append(f"  {name}  ·  {ts}  ·  {val:g}")
        log.append("\n".join(lines))

    def _refresh(self) -> None:
        for tag in self._tags:
            self.chart.replace_series_data(tag, self._series_getter(tag))
