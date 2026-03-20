# NQ Backtester — 설계 문서

## 1. 디렉토리 트리

```
nq_backtester/
├── DESIGN.md
├── BUILD_STATUS.md
├── README.md
├── requirements.txt
├── nq_backtester.spec          # PyInstaller 빌드 스펙
├── src/
│   ├── main.py                 # 앱 진입점
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fetcher.py          # yfinance 데이터 수집
│   │   ├── cache.py            # SQLite 로컬 캐시
│   │   └── store.py            # fetcher + cache 조합 인터페이스
│   ├── indicators.py           # SMA, EMA, RSI, MACD, Bollinger 계산
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── base_strategy.py    # Strategy 추상 기본 클래스
│   │   ├── strategies.py       # GoldenCross, RSIMeanReversion, MACDMomentum
│   │   ├── backtest.py         # BacktestEngine (이벤트 드리븐)
│   │   └── performance.py      # BacktestResult, PerformanceAnalyzer
│   └── ui/
│       ├── __init__.py
│       ├── main_window.py      # MainWindow (QMainWindow)
│       ├── chart_widget.py     # CandlestickChart + 오버레이
│       ├── settings_panel.py   # 좌측 설정 패널 위젯
│       ├── performance_panel.py# 우측 성과 비교 테이블
│       ├── trades_table.py     # 하단 거래 내역 탭
│       └── worker.py           # BacktestWorker (QThread)
└── tests/
    ├── __init__.py
    ├── test_smoke.py
    ├── test_data.py
    └── test_engine.py
```

---

## 2. 모듈 책임 정의

| 모듈 | 책임 |
|------|------|
| `src/main.py` | QApplication 생성 및 MainWindow 실행. PyInstaller 진입점. |
| `src/data/fetcher.py` | yfinance로 NQ=F OHLCV 데이터 수집. 봉 단위별 최대 기간 제한 적용. |
| `src/data/cache.py` | SQLite 기반 로컬 캐시. 동일 요청 재다운로드 방지. TTL 기반 만료 관리. |
| `src/data/store.py` | DataFetcher + DataCache를 조합한 단일 인터페이스. 결측치 처리 포함. |
| `src/indicators.py` | pandas/numpy 기반 벡터라이즈드 기술 지표 계산 함수 모음. |
| `src/engine/base_strategy.py` | Strategy 추상 기본 클래스. generate_signals() 인터페이스 정의. |
| `src/engine/strategies.py` | GoldenCross, RSIMeanReversion, MACDMomentum 3개 전략 구현. |
| `src/engine/backtest.py` | 이벤트 드리븐 백테스트 실행 엔진. 포지션/수수료/슬리피지 관리. |
| `src/engine/performance.py` | BacktestResult 데이터클래스. 수익률/MDD/샤프 등 성과 지표 계산. |
| `src/ui/main_window.py` | 전체 레이아웃 조립. 패널 간 시그널/슬롯 연결. |
| `src/ui/chart_widget.py` | pyqtgraph 기반 캔들차트 + 거래량 + 전략 마커 오버레이. Replay 애니메이션. |
| `src/ui/settings_panel.py` | 심볼/기간/봉 단위/전략 선택/파라미터 입력 UI. 봉 단위 변경 시 기간 제한 적용. |
| `src/ui/performance_panel.py` | 전략별 성과 비교 테이블. 전략 색상 배지 포함. |
| `src/ui/trades_table.py` | 전략별 탭으로 분리된 거래 내역 QTableView. |
| `src/ui/worker.py` | 백테스트를 별도 QThread에서 실행. progress/finished/error 시그널 발행. |

---

## 3. 데이터 플로우

```
[사용자 입력]
    심볼(NQ=F), 봉 단위, 기간, 전략 선택, 파라미터
         │
         ▼
[SettingsPanel]
    봉 단위 변경 → 기간 DateEdit 범위 자동 제한
         │
         ▼ Run 클릭
[BacktestWorker : QThread]
    │
    ├─► [DataStore]
    │       ├─► [DataCache] ──캐시 히트──► pd.DataFrame 반환
    │       └─► [DataFetcher] ─캐시 미스─► yfinance.download()
    │               └─► 결측치 처리(ffill + dropna)
    │               └─► pd.DataFrame (OHLCV) 반환
    │
    ├─► [indicators.py]
    │       SMA, EMA, RSI, MACD 등 계산 → DataFrame에 컬럼 추가
    │
    └─► [BacktestEngine]
            ├─► 선택된 전략별 generate_signals(df) 호출
            ├─► 바 단위 이벤트 드리븐 시뮬레이션
            │       포지션 상태 추적, 수수료/슬리피지 적용
            └─► [PerformanceAnalyzer]
                    └─► BacktestResult 생성
                            ├─► equity_curve (pd.Series)
                            ├─► trades_df (pd.DataFrame)
                            └─► metrics (dict)
         │
         ▼ finished Signal (list[BacktestResult])
[MainWindow]
    ├─► [ChartWidget]
    │       캔들차트 업데이트
    │       전략별 마커 오버레이 (각기 다른 색상)
    │       지표선 오버레이
    │
    ├─► [PerformancePanel]
    │       전략별 성과 비교 테이블 행 추가
    │
    └─► [TradesTable]
            전략별 탭에 거래 내역 채우기
```

---

## 4. GUI 레이아웃 와이어프레임 (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  NQ Backtester                                              [─][□][✕]           │
├──────────────┬──────────────────────────────────────┬──────────────────────────┤
│ [설정 패널]   │  [캔들스틱 차트 + 지표 + 마커]          │  [성과 비교 패널]          │
│  280px       │                                      │  250px                   │
│              │  ┌──────────────────────────────┐    │  ┌────────────────────┐  │
│ 심볼: NQ=F   │  │                              │    │  │전략  수익률 MDD 샤프│  │
│              │  │    캔들스틱 차트 영역           │    │  ├────────────────────┤  │
│ 봉 단위:      │  │    (pyqtgraph)               │    │  │■GC  +12.3% -8.1% 1.2│ │
│ [1m ▼]       │  │                              │    │  │■RSI  +9.1% -5.3% 0.9│ │
│              │  │  ▲ = 매수진입  ▼ = 청산        │    │  │■MAC  +7.8% -6.2% 0.8│ │
│ 시작일:       │  │                              │    │  └────────────────────┘  │
│ [2024-01-01] │  │  ── SMA20  ── SMA60           │    │                          │
│              │  │                              │    │  승률    거래수            │
│ 종료일:       │  └──────────────────────────────┘    │  ┌────────────────────┐  │
│ [2024-12-31] │                                      │  │■GC   62%    48      │  │
│              │  ┌──────────────────────────────┐    │  │■RSI  58%    73      │  │
│ ─────────── │  │  거래량 차트 (120px)            │    │  │■MAC  55%    61      │  │
│ 전략 선택:    │  │  (x축 캔들차트와 동기화)         │    │  └────────────────────┘  │
│ ☑ GoldenCross│  └──────────────────────────────┘    │                          │
│ ☑ RSIRevrsn  │                                      │                          │
│ ☑ MACDMomntm │                                      │                          │
│              │                                      │                          │
│ ─────────── │                                      │                          │
│ [GoldenCross]│                                      │                          │
│  Fast: [20 ] │                                      │                          │
│  Slow: [60 ] │                                      │                          │
│              │                                      │                          │
│ [RSIRevrsin] │                                      │                          │
│  Period:[14] │                                      │                          │
│  Oversold:[30│                                      │                          │
│  Overbought: │                                      │                          │
│  [70]        │                                      │                          │
│              │                                      │                          │
│ [MACDMomntm] │                                      │                          │
│  Fast:  [12] │                                      │                          │
│  Slow:  [26] │                                      │                          │
│  Signal:[9 ] │                                      │                          │
│              │                                      │                          │
│ ─────────── │                                      │                          │
│ [▶ Run     ] │                                      │                          │
│ [⏵ Replay  ] │                                      │                          │
│ 속도: [━━○─] │                                      │                          │
│ [████░░░] 60%│                                      │                          │
├──────────────┴──────────────────────────────────────┴──────────────────────────┤
│ 거래 내역                                                                        │
│ [GoldenCross] [RSIMeanReversion] [MACDMomentum]                                 │
│ ┌────────────┬────────────┬──────┬──────┬──────┬────────┐                      │
│ │ 진입시각   │ 청산시각   │ 진입가│ 청산가│  P&L │ 누적손익│                      │
│ ├────────────┼────────────┼──────┼──────┼──────┼────────┤                      │
│ │2024-01-05  │2024-01-12  │16820 │17050 │ +$460│ +$460  │                      │
│ │2024-01-18  │2024-01-25  │17100 │16950 │ -$300│ +$160  │                      │
│ └────────────┴────────────┴──────┴──────┴──────┴────────┘                      │
│                                                               높이: 200px       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Strategy 추상 인터페이스 명세

### BaseStrategy

**속성**
- `name: str` — 전략 식별 이름 (예: "GoldenCross")
- `display_name: str` — UI 표시용 이름 (예: "Golden Cross (SMA)")
- `color: str` — 차트 마커/테이블 색상 (예: "#2ECC71")
- `params: dict[str, Any]` — 파라미터 딕셔너리 (예: {"fast": 20, "slow": 60})

**메서드**

```
generate_signals(df: pd.DataFrame) -> pd.Series
  입력:  OHLCV DataFrame (인덱스=datetime)
  출력:  Signal Series
          인덱스 = df.index (datetime)
          값    = +1 (매수 진입)
                 -1 (매도/청산)
                  0 (홀드/포지션 없음)
  규칙:  해당 바의 데이터만 사용 (Lookahead 금지)
         종가(Close) 기준으로 시그널 생성
         다음 바 시가에 체결되는 것으로 가정

get_param_schema() -> list[dict]
  반환:  GUI 파라미터 입력 폼 자동 생성용 스키마
  예시:  [
           {"key": "fast", "label": "Fast Period", "type": "int",
            "min": 2, "max": 200, "default": 20},
           {"key": "slow", "label": "Slow Period", "type": "int",
            "min": 5, "max": 500, "default": 60}
         ]

get_indicator_lines(df: pd.DataFrame) -> dict[str, pd.Series]
  반환:  차트에 오버레이할 지표선
  예시:  {"SMA20": sma_series, "SMA60": sma_series}
```

---

## 6. BacktestEngine 이벤트 드리븐 설계

### 실행 방식: Bar-by-Bar 이벤트 드리븐

```
초기화:
  capital = initial_capital
  position = FLAT  (FLAT | LONG | SHORT)
  entry_price = None
  entry_time = None
  trades = []
  equity = []

바 단위 루프 (i = 0 to len(df)-1):
  현재 바: df.iloc[i]
  시그널:  signals.iloc[i]  (i번째 바 종가 기준으로 이미 계산됨)

  ─ 청산 처리 ─
  if position == LONG and signal == -1:
      exit_price = df.iloc[i+1]['Open']  # 다음 바 시가에 체결
      pnl = (exit_price - entry_price) * CONTRACT_SIZE - commission
      capital += pnl
      trades.append({진입/청산 정보, pnl})
      position = FLAT

  ─ 진입 처리 ─
  if position == FLAT and signal == +1:
      entry_price = df.iloc[i+1]['Open']  # 다음 바 시가에 체결
      entry_time = df.iloc[i+1].name
      position = LONG
      capital -= commission / 2  # 진입 수수료

  equity.append(capital)

완료:
  미청산 포지션 있으면 마지막 바 종가로 강제 청산
  BacktestResult 생성
```

### NQ 선물 계약 스펙 반영
- 계약 1개 기준으로 시뮬레이션
- P&L = (청산가 - 진입가) × 20 (달러)
- 슬리피지: 0.25포인트 (최소 틱) × 2 (진입+청산) = 0.5포인트 = $10

### run_multiple (멀티 전략 비교)
```
run_multiple(df, strategies: list[BaseStrategy], **kwargs) -> list[BacktestResult]
  - 동일한 df로 각 전략에 대해 run() 개별 호출
  - concurrent.futures.ThreadPoolExecutor로 병렬 실행
  - 결과 순서는 strategies 리스트 순서와 동일하게 반환
```

---

## 7. NQ 선물 계약 스펙

| 항목 | 값 |
|------|-----|
| 심볼 | NQ=F (E-mini NASDAQ-100) |
| 거래소 | CME |
| 계약 승수 | $20 per index point |
| 최소 틱 | 0.25 포인트 |
| 틱 가치 | $5 (= 0.25 × $20) |
| 일반 왕복 수수료 | $4.00 (진입 $2 + 청산 $2) |
| 슬리피지 가정 | 0.25포인트 (최소 틱 1개) |
| 증거금 (참고) | 약 $18,000 (CME 기준, 시뮬레이션에서는 미적용) |

---

## 8. 멀티 전략 비교 데이터 구조

### 전략별 색상 할당
```python
STRATEGY_COLORS = {
    "GoldenCross":      "#2ECC71",  # 초록
    "RSIMeanReversion": "#3498DB",  # 파랑
    "MACDMomentum":     "#E74C3C",  # 빨강
}
```

### BacktestResult 데이터클래스
```
BacktestResult:
  strategy_name: str
  color: str

  # 거래 내역
  trades_df: pd.DataFrame
    컬럼: entry_time, exit_time, entry_price, exit_price,
          pnl, cumulative_pnl, direction

  # 자본 곡선
  equity_curve: pd.Series
    인덱스: datetime (df의 인덱스와 동일)
    값:     누적 자본 (달러)

  # 성과 지표
  metrics: dict
    - total_return:   float  (%)
    - annual_return:  float  (%)
    - mdd:            float  (%) 최대 낙폭
    - sharpe:         float  샤프 비율 (무위험 수익률 2% 가정)
    - win_rate:       float  (%)
    - total_trades:   int
    - profit_factor:  float  총이익 / 총손실
```

### 멀티 전략 차트 오버레이 방식
- 각 전략의 진입 마커(▲)와 청산 마커(▼)를 해당 전략 색상으로 캔들차트 위에 오버레이
- 성과 비교 패널: 전략별 색상 배지 + 지표 행
- 거래 내역 탭: 전략별 분리된 탭 (탭 헤더에 전략 색상 적용)
- Equity Curve 비교: 별도 서브플롯 옵션 (구현 시 토글 가능하도록 설계)
