"""
TradesTable: 하단 거래 내역 탭 위젯
전략마다 탭 1개, 탭 헤더에 전략 색상 적용
"""
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel,
)


COLUMNS = [
    ("진입시각", 140),
    ("청산시각", 140),
    ("진입가", 80),
    ("청산가", 80),
    ("P&L", 80),
    ("누적손익", 90),
]


def _make_table() -> QTableWidget:
    """거래 내역 테이블 생성"""
    table = QTableWidget()
    table.setColumnCount(len(COLUMNS))
    table.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.setStyleSheet("""
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

    for i, (name, width) in enumerate(COLUMNS):
        table.setColumnWidth(i, width)

    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    return table


class TradesTable(QWidget):
    """전략별 거래 내역 탭 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(220)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background: #2A2A2A;
            }
            QTabBar::tab {
                background: #333;
                color: #AAA;
                padding: 4px 8px;
                border: 1px solid #444;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background: #2A2A2A;
                color: #FFF;
            }
        """)

        layout.addWidget(self.tab_widget)

    def update(self, results):
        """
        거래 내역 탭 갱신.

        Args:
            results: list[BacktestResult]
        """
        self.tab_widget.clear()

        for result in results:
            if result is None:
                continue

            table = _make_table()

            if result.trades_df is not None and len(result.trades_df) > 0:
                for _, trade in result.trades_df.iterrows():
                    row_idx = table.rowCount()
                    table.insertRow(row_idx)

                    # 진입시각
                    entry_time = trade.get("entry_time")
                    if pd.notna(entry_time):
                        entry_str = str(entry_time)[:16]
                    else:
                        entry_str = "-"
                    table.setItem(row_idx, 0, QTableWidgetItem(entry_str))

                    # 청산시각
                    exit_time = trade.get("exit_time")
                    if pd.notna(exit_time):
                        exit_str = str(exit_time)[:16]
                    else:
                        exit_str = "-"
                    table.setItem(row_idx, 1, QTableWidgetItem(exit_str))

                    # 진입가
                    entry_price = trade.get("entry_price", 0)
                    table.setItem(row_idx, 2, QTableWidgetItem(f"{entry_price:.2f}"))

                    # 청산가
                    exit_price = trade.get("exit_price", 0)
                    table.setItem(row_idx, 3, QTableWidgetItem(f"{exit_price:.2f}"))

                    # P&L
                    pnl = trade.get("pnl", 0)
                    pnl_item = QTableWidgetItem(f"${pnl:+.0f}")
                    pnl_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if pnl >= 0:
                        pnl_item.setForeground(QColor("#2ECC71"))
                    else:
                        pnl_item.setForeground(QColor("#E74C3C"))
                    table.setItem(row_idx, 4, pnl_item)

                    # 누적손익
                    cum_pnl = trade.get("cumulative_pnl", 0)
                    cum_item = QTableWidgetItem(f"${cum_pnl:+.0f}")
                    cum_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if cum_pnl >= 0:
                        cum_item.setForeground(QColor("#2ECC71"))
                    else:
                        cum_item.setForeground(QColor("#E74C3C"))
                    table.setItem(row_idx, 5, cum_item)

                table.resizeRowsToContents()

            # 탭 추가 (탭 헤더에 색상 적용)
            tab_idx = self.tab_widget.addTab(table, result.strategy_name)
            self.tab_widget.tabBar().setTabTextColor(tab_idx, QColor(result.color))
