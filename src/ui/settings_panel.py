"""
SettingsPanel: 좌측 설정 패널 위젯
"""
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDateEdit, QCheckBox, QPushButton, QProgressBar, QSlider,
    QSpinBox, QGroupBox, QScrollArea, QFrame, QSizePolicy,
    QMessageBox,
)


# 봉 단위별 최대 기간 (일)
INTERVAL_MAX_DAYS = {
    "1m": 7,
    "5m": 60,
    "15m": 60,
    "60m": 730,
    "1d": 36500,
}

INTERVAL_LABELS = {
    "1m": "1분봉",
    "5m": "5분봉",
    "15m": "15분봉",
    "60m": "60분봉",
    "1d": "일봉",
}


class SettingsPanel(QWidget):
    """좌측 설정 패널"""

    run_clicked = Signal(str, str, object, object, list)  # symbol, interval, start, end, strategies
    replay_clicked = Signal(float)  # speed
    live_start_clicked = Signal(str, str)   # symbol, interval
    live_stop_clicked = Signal()

    def __init__(self, strategies, parent=None):
        """
        Args:
            strategies: list of BaseStrategy 인스턴스
        """
        super().__init__(parent)
        self._strategies = strategies
        self._param_widgets = {}  # strategy_name -> {key: spinbox}
        self._setup_ui()
        self._connect_signals()
        self._on_interval_changed(self.interval_combo.currentText())

    def _setup_ui(self):
        self.setFixedWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 심볼 레이블
        symbol_label = QLabel("심볼: NQ=F (E-mini NASDAQ-100)")
        symbol_label.setStyleSheet("font-weight: bold; color: #F39C12;")
        symbol_label.setToolTip("나스닥 100 선물 (CME E-mini)")
        main_layout.addWidget(symbol_label)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #444;")
        main_layout.addWidget(sep1)

        # 봉 단위
        interval_layout = QHBoxLayout()
        interval_label = QLabel("봉 단위:")
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["1m", "5m", "15m", "60m", "1d"])
        self.interval_combo.setCurrentText("1d")
        self.interval_combo.setToolTip("데이터 봉 단위 선택 (조회 가능 기간 자동 제한)")
        interval_layout.addWidget(interval_label)
        interval_layout.addWidget(self.interval_combo)
        main_layout.addLayout(interval_layout)

        # 시작일
        start_layout = QHBoxLayout()
        start_label = QLabel("시작일:")
        self.start_date = QDateEdit()
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setCalendarPopup(True)
        self.start_date.setToolTip("백테스트 시작 날짜")
        start_layout.addWidget(start_label)
        start_layout.addWidget(self.start_date)
        main_layout.addLayout(start_layout)

        # 종료일
        end_layout = QHBoxLayout()
        end_label = QLabel("종료일:")
        self.end_date = QDateEdit()
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setToolTip("백테스트 종료 날짜")
        end_layout.addWidget(end_label)
        end_layout.addWidget(self.end_date)
        main_layout.addLayout(end_layout)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #444;")
        main_layout.addWidget(sep2)

        # 전략 선택 (스크롤 가능)
        strategy_label = QLabel("전략 선택:")
        strategy_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(strategy_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(400)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(4)

        self._strategy_checks = {}
        self._param_groups = {}

        for strategy in self._strategies:
            # 전략 체크박스
            cb = QCheckBox(strategy.display_name)
            cb.setStyleSheet(f"QCheckBox {{ color: {strategy.color}; font-weight: bold; }}")
            cb.setToolTip(f"전략 활성화: {strategy.display_name}")
            scroll_layout.addWidget(cb)
            self._strategy_checks[strategy.name] = cb

            # 파라미터 그룹
            param_schema = strategy.get_param_schema()
            if param_schema:
                group = QGroupBox()
                group.setStyleSheet(f"QGroupBox {{ border: 1px solid {strategy.color}44; border-radius: 4px; padding: 4px; }}")
                group_layout = QVBoxLayout(group)
                group_layout.setContentsMargins(4, 4, 4, 4)
                group_layout.setSpacing(2)

                self._param_widgets[strategy.name] = {}

                for param in param_schema:
                    row = QHBoxLayout()
                    label = QLabel(f"  {param['label']}:")
                    label.setFixedWidth(120)
                    spinbox = QSpinBox()
                    spinbox.setMinimum(param.get("min", 1))
                    spinbox.setMaximum(param.get("max", 9999))
                    spinbox.setValue(param.get("default", 10))
                    spinbox.setToolTip(f"{param['label']} (min={param.get('min',1)}, max={param.get('max',9999)})")
                    row.addWidget(label)
                    row.addWidget(spinbox)
                    group_layout.addLayout(row)
                    self._param_widgets[strategy.name][param["key"]] = spinbox

                group.setVisible(False)  # 기본 숨김
                scroll_layout.addWidget(group)
                self._param_groups[strategy.name] = group

                # 체크박스 토글 시 파라미터 그룹 표시/숨김
                cb.toggled.connect(lambda checked, g=group: g.setVisible(checked))

        # 기본값: GoldenCross 체크
        if "GoldenCross" in self._strategy_checks:
            self._strategy_checks["GoldenCross"].setChecked(True)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("color: #444;")
        main_layout.addWidget(sep3)

        sep_live = QFrame()
        sep_live.setFrameShape(QFrame.Shape.HLine)
        sep_live.setStyleSheet("color: #444;")
        main_layout.addWidget(sep_live)

        # ── 실시간 모드 섹션 ──
        live_label = QLabel("실시간 모드")
        live_label.setStyleSheet("font-weight: bold; color: #E74C3C;")
        main_layout.addWidget(live_label)

        # 현재가 표시
        self.price_label = QLabel("—")
        self.price_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #F0F0F0; qproperty-alignment: AlignCenter;"
        )
        self.price_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.price_label)

        self.price_change_label = QLabel("")
        self.price_change_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.price_change_label.setStyleSheet("font-size: 12px; color: #888;")
        main_layout.addWidget(self.price_change_label)

        self.live_status_label = QLabel("대기 중")
        self.live_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_status_label.setStyleSheet("font-size: 10px; color: #888;")
        main_layout.addWidget(self.live_status_label)

        # Live 시작/중단 버튼
        self.live_btn = QPushButton("● Live 시작")
        self.live_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: #FFF;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #C0392B; }
            QPushButton:disabled { background-color: #444; color: #888; }
            QPushButton[live="true"] {
                background-color: #555;
                color: #FFF;
            }
        """)
        self.live_btn.setToolTip("실시간 데이터 수신 시작/중단")
        self.live_btn.setCheckable(True)
        main_layout.addWidget(self.live_btn)

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.Shape.HLine)
        sep4.setStyleSheet("color: #444;")
        main_layout.addWidget(sep4)

        # ── 백테스트 섹션 ──
        # Run 버튼
        self.run_btn = QPushButton("▶  Run Backtest")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ECC71;
                color: #000;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #27AE60; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.run_btn.setToolTip("선택된 전략으로 백테스트 실행")
        main_layout.addWidget(self.run_btn)

        # Replay 버튼
        self.replay_btn = QPushButton("⏵  Replay")
        self.replay_btn.setEnabled(False)
        self.replay_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: #FFF;
                font-weight: bold;
                padding: 6px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2980B9; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.replay_btn.setToolTip("백테스트 결과를 바 단위로 재생")
        main_layout.addWidget(self.replay_btn)

        # 속도 슬라이더
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("속도:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(10)
        self.speed_slider.setValue(3)
        self.speed_slider.setToolTip("Replay 속도 (1x~10x)")
        self.speed_label = QLabel("3x")
        self.speed_label.setFixedWidth(24)
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        main_layout.addLayout(speed_layout)

        # 진행률 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setToolTip("백테스트 진행률")
        main_layout.addWidget(self.progress_bar)

        main_layout.addStretch()

    def _connect_signals(self):
        self.interval_combo.currentTextChanged.connect(self._on_interval_changed)
        self.run_btn.clicked.connect(self._on_run_clicked)
        self.replay_btn.clicked.connect(self._on_replay_clicked)
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_label.setText(f"{v}x")
        )
        self.live_btn.toggled.connect(self._on_live_toggled)

    def _on_interval_changed(self, interval: str):
        """봉 단위 변경 시 날짜 범위 자동 조정"""
        max_days = INTERVAL_MAX_DAYS.get(interval, 36500)
        today = QDate.currentDate()

        if max_days < 36500:
            earliest = today.addDays(-max_days)
            self.start_date.setMinimumDate(earliest)
            self.start_date.setMaximumDate(today)
            self.end_date.setMinimumDate(earliest)
            self.end_date.setMaximumDate(today)

            # 기본 start: max_days의 절반 전
            default_start = today.addDays(-min(max_days, 30))
            self.start_date.setDate(default_start)
        else:
            earliest = today.addYears(-10)
            self.start_date.setMinimumDate(earliest)
            self.start_date.setMaximumDate(today)
            self.end_date.setMinimumDate(earliest)
            self.end_date.setMaximumDate(today)
            self.start_date.setDate(today.addYears(-1))

        self.end_date.setDate(today)

    def _on_run_clicked(self):
        """Run 버튼 클릭"""
        # 전략 선택 확인
        selected_strategies = self._get_selected_strategies()
        if not selected_strategies:
            QMessageBox.warning(self, "전략 미선택", "전략을 하나 이상 선택해주세요.")
            return

        # 날짜 유효성 검사
        start_qdate = self.start_date.date()
        end_qdate = self.end_date.date()
        if start_qdate >= end_qdate:
            QMessageBox.warning(self, "날짜 오류", "시작일이 종료일보다 앞이어야 합니다.")
            return

        interval = self.interval_combo.currentText()
        start = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day(), 23, 59, 59)

        self.run_clicked.emit("NQ=F", interval, start, end, selected_strategies)

    def _on_replay_clicked(self):
        """Replay 버튼 클릭"""
        speed = float(self.speed_slider.value())
        self.replay_clicked.emit(speed)

    def _get_selected_strategies(self):
        """선택된 전략 인스턴스 반환 (파라미터 적용)"""
        selected = []
        for strategy in self._strategies:
            cb = self._strategy_checks.get(strategy.name)
            if cb and cb.isChecked():
                # 파라미터 읽기
                params = {}
                param_widgets = self._param_widgets.get(strategy.name, {})
                for key, spinbox in param_widgets.items():
                    params[key] = spinbox.value()

                # 파라미터 적용한 새 인스턴스 생성
                strategy_class = type(strategy)
                instance = strategy_class(params=params if params else None)
                selected.append(instance)
        return selected

    def _on_live_toggled(self, checked: bool):
        if checked:
            self.live_btn.setText("■ Live 중단")
            self.live_btn.setStyleSheet("""
                QPushButton {
                    background-color: #555;
                    color: #FF6B6B;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 4px;
                    border: 1px solid #E74C3C;
                }
                QPushButton:hover { background-color: #666; }
            """)
            # 백테스트 버튼 비활성화
            self.run_btn.setEnabled(False)
            self.live_start_clicked.emit("NQ=F", self.interval_combo.currentText())
        else:
            self.live_btn.setText("● Live 시작")
            self.live_btn.setStyleSheet("""
                QPushButton {
                    background-color: #E74C3C;
                    color: #FFF;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #C0392B; }
                QPushButton:disabled { background-color: #444; color: #888; }
            """)
            self.run_btn.setEnabled(True)
            self.live_status_label.setText("대기 중")
            self.live_stop_clicked.emit()

    def update_live_price(self, price: float, prev_close: float, change_pct: float):
        """실시간 현재가 업데이트"""
        self.price_label.setText(f"{price:,.2f}")
        sign = "+" if change_pct >= 0 else ""
        color = "#2ECC71" if change_pct >= 0 else "#E74C3C"
        change_pts = price - prev_close
        self.price_change_label.setText(
            f'<span style="color:{color}">{sign}{change_pts:,.2f} ({sign}{change_pct:.2f}%)</span>'
        )
        self.price_label.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {color}; qproperty-alignment: AlignCenter;"
        )

    def update_live_status(self, status: str):
        self.live_status_label.setText(status)

    def set_live_error(self):
        """Live 오류 시 버튼 상태 복원"""
        self.live_btn.setChecked(False)

    def set_running(self, running: bool):
        """실행 중 UI 상태 관리"""
        self.run_btn.setEnabled(not running)
        self.interval_combo.setEnabled(not running)
        self.start_date.setEnabled(not running)
        self.end_date.setEnabled(not running)
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.setValue(0)

    def set_progress(self, value: int):
        self.progress_bar.setValue(value)

    def set_replay_enabled(self, enabled: bool):
        self.replay_btn.setEnabled(enabled)
