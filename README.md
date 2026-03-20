# NQ Backtester

나스닥 선물(NQ=F) 백테스팅 데스크톱 GUI 앱

## 실행 방법

### macOS 보안 경고 해제 (최초 1회)
```bash
xattr -rd com.apple.quarantine ./dist/NQBacktester/
```

### 실행
```bash
./dist/NQBacktester/NQBacktester
```

### 소스에서 직접 실행
```bash
cd /path/to/nq_backtester
pip install -r requirements.txt
PYTHONPATH=src python src/main.py
```

## 봉 단위별 조회 가능 기간

| 봉 단위 | 최대 기간 |
|---------|---------|
| 1분봉 | 최근 7일 |
| 5분봉 | 최근 60일 |
| 15분봉 | 최근 60일 |
| 60분봉 | 최근 730일 |
| 일봉 | 제한 없음 |

## 내장 전략

- **Golden Cross**: 단기(20) SMA가 장기(60) SMA를 상향 돌파 시 매수
- **RSI Mean Reversion**: RSI 30 이하 과매도 구간 매수, 70 이상 과매수 구간 청산
- **MACD Momentum**: MACD 선이 시그널 선을 상향 돌파 시 매수

## 멀티 전략 비교

전략 선택 패널에서 여러 전략을 동시에 체크하면
하나의 차트에 전략별 진입/청산 마커가 색상별로 오버레이됩니다.

| 전략 | 색상 |
|------|------|
| Golden Cross | 초록 (#2ECC71) |
| RSI Mean Reversion | 파랑 (#3498DB) |
| MACD Momentum | 빨강 (#E74C3C) |

## Replay 모드

백테스트 완료 후 [Replay] 버튼을 클릭하면
바 단위로 차트가 점진적으로 업데이트됩니다.
속도 슬라이더로 재생 속도를 조절할 수 있습니다.

## 성과 지표 설명

- **수익률**: (최종자본 - 초기자본) / 초기자본 × 100
- **MDD**: 최고점 대비 최대 낙폭 (Maximum Drawdown)
- **샤프 비율**: (연환산수익률 - 2%) / 연환산변동성
- **승률**: 수익 거래 수 / 전체 거래 수 × 100
- **손익비**: 총이익 / 총손실 (Profit Factor)

## NQ 선물 계약 스펙

| 항목 | 값 |
|------|-----|
| 심볼 | NQ=F (E-mini NASDAQ-100) |
| 계약 승수 | $20 per index point |
| 최소 틱 | 0.25 포인트 |
| 왕복 수수료 | $4.00 (진입 $2 + 청산 $2) |
| 슬리피지 가정 | 0.25포인트 (최소 틱 1개) |
| 초기 자본 | $100,000 |

## 캐시

데이터는 `~/.nq_backtester/cache.db` (SQLite)에 로컬 캐시됩니다.
같은 조건으로 재실행 시 네트워크 호출 없이 즉시 결과를 반환합니다.

| 봉 단위 | 캐시 유효 시간 |
|---------|-------------|
| 1분봉 | 1시간 |
| 5분봉, 15분봉 | 4시간 |
| 60분봉 | 12시간 |
| 일봉 | 24시간 |

## 프로젝트 구조

```
nq_backtester/
├── src/
│   ├── main.py                 # 앱 진입점
│   ├── data/
│   │   ├── fetcher.py          # yfinance 데이터 수집
│   │   ├── cache.py            # SQLite 로컬 캐시
│   │   └── store.py            # fetcher + cache 조합 인터페이스
│   ├── indicators.py           # SMA, EMA, RSI, MACD, Bollinger
│   ├── engine/
│   │   ├── base_strategy.py    # Strategy 추상 기본 클래스
│   │   ├── strategies.py       # 내장 전략 구현
│   │   ├── backtest.py         # 이벤트 드리븐 백테스트 엔진
│   │   └── performance.py      # 성과 지표 계산
│   └── ui/
│       ├── main_window.py      # MainWindow
│       ├── chart_widget.py     # 캔들차트 + 오버레이
│       ├── settings_panel.py   # 설정 패널
│       ├── performance_panel.py# 성과 비교 테이블
│       ├── trades_table.py     # 거래 내역 탭
│       └── worker.py           # 백테스트 QThread
└── tests/
    ├── test_smoke.py
    ├── test_data.py
    ├── test_engine.py
    └── test_integration.py
```

## 테스트 실행

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src pytest tests/ -v
```
