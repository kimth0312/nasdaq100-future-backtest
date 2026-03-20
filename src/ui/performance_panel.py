"""
PerformancePanel: 우측 성과 비교 패널
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy,
)


class PerformancePanel(QWidget):
    """전략별 성과 비교 테이블"""

    COLUMNS = [
        ("전략", 100),
        ("수익률", 65),
        ("MDD", 60),
        ("샤프", 50),
        ("승률", 50),
        ("거래수", 50),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(250)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        title = QLabel("성과 비교")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #F39C12;")
        layout.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #2A2A2A;
                color: #CCCCCC;
                gridline-color: #444;
                font-size: 11px;
            }
            QTableWidget::item:alternate {
                background-color: #333333;
            }
            QHeaderView::section {
                background-color: #333;
                color: #AAA;
                padding: 4px;
                border: none;
                font-size: 10px;
            }
        """)

        header = self.table.horizontalHeader()
        for i, (name, width) in enumerate(self.COLUMNS):
            self.table.setColumnWidth(i, width)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def update(self, results):
        """
        성과 테이블 갱신.

        Args:
            results: list[BacktestResult]
        """
        self.table.setRowCount(0)

        for result in results:
            if result is None:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)
            m = result.metrics

            # 전략명 (색상 배지)
            name_item = QTableWidgetItem(f"■ {result.strategy_name}")
            name_item.setForeground(QColor(result.color))
            name_item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            name_item.setToolTip(result.strategy_name)
            self.table.setItem(row, 0, name_item)

            # 수익률
            total_ret = m.get("total_return", 0)
            ret_item = QTableWidgetItem(f"{total_ret:+.1f}%")
            ret_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if total_ret >= 0:
                ret_item.setForeground(QColor("#2ECC71"))
            else:
                ret_item.setForeground(QColor("#E74C3C"))
            self.table.setItem(row, 1, ret_item)

            # MDD
            mdd = m.get("mdd", 0)
            mdd_item = QTableWidgetItem(f"{mdd:.1f}%")
            mdd_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            mdd_item.setForeground(QColor("#E74C3C"))
            self.table.setItem(row, 2, mdd_item)

            # 샤프
            sharpe = m.get("sharpe", 0)
            sharpe_item = QTableWidgetItem(f"{sharpe:.2f}")
            sharpe_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if sharpe >= 1.0:
                sharpe_item.setForeground(QColor("#2ECC71"))
            elif sharpe >= 0:
                sharpe_item.setForeground(QColor("#F39C12"))
            else:
                sharpe_item.setForeground(QColor("#E74C3C"))
            self.table.setItem(row, 3, sharpe_item)

            # 승률
            win_rate = m.get("win_rate", 0)
            wr_item = QTableWidgetItem(f"{win_rate:.0f}%")
            wr_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, wr_item)

            # 거래수
            trades = m.get("total_trades", 0)
            trades_item = QTableWidgetItem(str(trades))
            trades_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 5, trades_item)

        self.table.resizeRowsToContents()
