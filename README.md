# 🐠 Home Assistant WeekAqua Integration & Lovelace Card

Home Assistant(HA) 환경에서 **WeekAqua 수조 조명**을 제어할 수 있는 전용 **Custom Integration (HACS 지원)** 및 **WPF 스타일 Lovelace 커스텀 대시보드 카드**입니다.

조명 내장 MCU의 하드웨어 슬롯(5개/8개/12개) 한계에서 완전히 벗어나, **Home Assistant의 시간 기반 트리거 및 실시간 선형 보간(Linear Ramp Interpolation) 엔진**을 통해 **무제한 스케줄 단계(Unlimited Steps)**를 자유롭게 구성할 수 있습니다.

---

## ✨ 주요 기능 (Key Features)

1. **무제한 단계 동적 스케줄러 (Unlimited Steps Dynamic Scheduler - 슬롯 정시 전송 모드)**:
   - 5개, 8개, 12개 슬롯 제한 없이 사용자가 원하는 만큼(10개, 20개, 50개 등) 시간-스펙트럼 포인트를 자유롭게 추가/삭제 구성
   - 설정된 슬롯 시간이 도래했을 때만 해당 목표 밝기를 **정시 1회 Live 전송**하고 60초 후 즉시 연결을 해제하여 **블루투스 절전 및 99% 무간섭 운용**
   - HA 재부팅 시에도 스케줄 활성화 상태 및 시간대별 밝기를 100% 온전하게 복원
2. **스마트 60초 무활동 자동 연결 해제 (Inactivity Auto-Disconnect)**:
   - 패킷 전송 후 60초 동안 추가 조작이 없으면 BLE 세션을 자동으로 안전하게 해제
   - 스마트폰 공식 WeekAqua 앱을 켤 때 1:1 블루투스 점유 충돌 없이 언제든지 자유롭게 사용 가능
3. **단일 블루투스 연결 스위치 (`switch.ble_connection`)**:
   - 불필요한 다중 버튼을 제거하고, 단 1개의 토글 스위치로 실시간 연결 상태 모니터링 및 수동 연결/해제 제어
4. **무지연 실시간 RTC 동기화 (Zero-Latency Dynamic RTC Sync)**:
   - 매일 자정(00:00) 조명 내부 RTC 시계를 HA 초정밀 시각으로 자동 재동기화
   - 무선 연결 지연 시간(1~3초)을 상쇄하기 위해 실제 전송 직전 1밀리초 시점의 `datetime.now()`로 동적 인코딩하여 오차 0초 보정
5. **ESPHome Bluetooth Proxy 완벽 지원**:
   - HA 서버와 어항의 거리가 멀어도 방마다 설치된 ESP32 Bluetooth Proxy를 통해 원격으로 블루투스 패킷 송수신
6. **100% 전력 안전 2중 가드 (Max Power Limit Dual-Layer Guard)**:
   - 안드로이드 공식 APK 전력 공식 기반 채널 비율 보존 자동 정규화(Normalize) 내장
   - $99.8\%$ 안전 스케일 팩터 및 Safety While Loop로 부동소수점 반올림 누적 오차($100.1\%$)를 원천 차단
7. **WPF 룩앤필의 Lovelace 커스텀 카드 (`weekaqua-card.js`)**:
   - 다크 테마, 채널별 컬러 슬라이더(R, G, B, W, UV, Violet, Fan)
   - 실시간 총 전력 부하(%) 게이지 프로그레스 바
   - **24시간 인터랙티브 SVG 타임라인 그래프** 시각화
   - 원클릭 프리셋 버튼 (수초, 어항, 산호, 💡 Max 100%, 심야 달빛 등)
   - 실시간 연결 상태 스위치 및 모드 토글 배지

---

## 🔌 호환 및 테스트된 기기 (Tested Devices)

본 프로젝트는 다음과 같은 하드웨어 펌웨어 환경에서 직접 테스트 및 검증되었습니다.
- **B3.0-M800Pro-18** (4-Channel RGB/UV, Legacy 5745 Protocol Mode)

---

> [!NOTE]
> ### 💡 Live 모드 (Mode 1) 하드웨어 제어 규격
> * **타이머 잠금 연동**: WeekAqua 조명 MCU는 실시간 라이브 모드(`Mode 1 / FDF1`) 동작 시 하드웨어 내부 타이머(`FEF9` 또는 `FEEF`)와 결합되어 작동합니다.
> * **완전한 라이브 제어 시퀀스**: 본 통합구성요소는 실시간 색상 변경 시 `FDF1(모드전환)` ➡ `스펙트럼(색상출력)` ➡ `FEF9/FEEF(24시간타이머개방)` 3단계 시퀀스를 자동 전송하여 과거 스케줄 잔여값(야간 달빛 등)으로의 덮어쓰기 및 소등을 완벽히 방지합니다.
> * **다이나믹 스케줄러 연동**: 지정 슬롯 정시 1회 전송 모드(Step 모드)와 연동되어 매 슬롯 도래 시 가장 안전하고 끊김 없는 스펙트럼 전환을 보장합니다.

---

## 📁 프로젝트 구조

```
ha-weekaqua/
├── custom_components/
│   └── weekaqua/
│       ├── __init__.py                # HA 통합 진입점 및 서비스 등록
│       ├── manifest.json              # HACS / HA 메타데이터
│       ├── const.py                   # UUID, 모델 코드, 프리셋 상수
│       ├── protocol.py                # Python WeekAqua BLE 프로토콜 엔진
│       ├── coordinator.py             # BLE 통신 & 상태 영구 복원 & 무제한 스케줄 엔진
│       ├── config_flow.py             # BLE 기기 자동 검색(Discovery) 플로우
│       ├── light.py                   # Master Light Entity
│       ├── number.py                  # 채널별 백분율 슬라이더 (R/G/B/W/UV/V/Fan)
│       ├── switch.py                  # 다이나믹 스케줄러, 야간 달빛, BLE 연결 스위치
│       ├── sensor.py                  # 전력량(kWh), 소비전력 부하(%) 센서
│       ├── button.py                  # 스케줄 모드 / 라이브 모드 전환 버튼
│       ├── services.yaml              # 커스텀 서비스 명세
│       └── translations/              # 다국어 지원 (ko, en)
├── dist/
│   └── weekaqua-card.js               # WPF 스타일 Lovelace 커스텀 카드
├── preview.html                       # HA 설치 없이 브라우저에서 즉시 체험하는 데모
├── hacs.json                          # HACS 지원 메타데이터
├── test_protocol.py                   # 단위 검증 테스트 스크립트
└── README.md
```

---

## 🚀 설치 방법 (Installation)

### 방법 1. HACS 사용자 지정 저장소 등록 (권장)

1. HACS > Integrations > 우측 상단 메뉴 `...` > **Custom repositories (사용자 지정 저장소)** 클릭
2. **Repository URL**: `https://github.com/ad960009/ha-weekaqua`
3. **Category**: `Integration` 선택 후 **[Add]** 클릭
4. 목록에 추가된 **WeekAqua Aquarium Light**를 다운로드 후 HA 재시작
5. **설정 > 기기 및 서비스 > 통합구성요소 추가**에서 **"WeekAqua"** 검색 후 추가

### 방법 2. 수동 설치 (Manual Installation)

1. `custom_components/weekaqua` 폴더를 Home Assistant 설정 디렉토리(`config/custom_components/weekaqua/`)에 복사합니다.
2. Home Assistant를 재시작합니다.
3. **설정 > 기기 및 서비스 > 통합구성요소 추가**에서 **"WeekAqua"**를 검색하여 추가합니다.
4. *(통합구성요소가 `weekaqua-card.js` 대시보드 리소스를 자동으로 로드하므로 별도의 수동 리소스 등록이 필요 없습니다!)*

---

## 🌐 설치 없이 브라우저에서 UI 확인 (Preview)

`ha-weekaqua/preview.html` 파일을 크롬/엣지 등 웹 브라우저로 열면 Home Assistant 없이도 슬라이더 조작, 프리셋 변경, 24시간 스케줄 타임라인 차트를 즉시 인터랙티브하게 체험하실 수 있습니다.

---

## 🎨 Lovelace 대시보드 카드 사용법 (자동 등록 지원 ✨)

통합구성요소 활성화 시 대시보드 리소스가 자동으로 등록되므로, 대시보드 수정 모드에서 **수동 카드**를 추가하고 아래 YAML만 입력하시면 즉시 카드가 표시됩니다:

```yaml
type: custom:weekaqua-card
title: 거실 수초항 조명
entity: light.aquarium_light
```

---

## 🤖 HA 자동화 (Automation) 서비스 예시

### 1. 스펙트럼 프리셋 적용
```yaml
service: weekaqua.apply_preset
data:
  preset: Max  # GreenGrass, RedGrass, FishMixed, CoralAb, Max, Moonlight 등
```

### 2. 수동 스펙트럼 전송
```yaml
service: weekaqua.set_spectrum
data:
  red: 80
  green: 60
  blue: 40
  white: 70
  uv: 30
  violet: 20
```

### 3. 무제한 스케줄 업로드
```yaml
service: weekaqua.set_schedule
data:
  points:
    - time: "08:00"
      r: 0
      g: 0
      b: 0
      w: 0
      uv: 0
      v: 0
    - time: "10:00"
      r: 30
      g: 40
      b: 30
      w: 40
      uv: 10
      v: 10
    - time: "13:00"
      r: 70
      g: 100
      b: 70
      w: 90
      uv: 50
      v: 40
    - time: "18:00"
      r: 40
      g: 60
      b: 40
      w: 50
      uv: 20
      v: 10
    - time: "20:30"
      r: 0
      g: 0
      b: 4
      w: 0
      uv: 0
      v: 0
```

### 4. 하드웨어 타이머 스케줄 설정 (자정 24:00 자동 분할 무암전 연속 점등)
조명 점등 시간이 자정을 넘기는 경우(예: 18:00 ~ 02:00) Home Assistant가 자동으로 **2개의 연속 스케줄 슬롯**(`18:00 ~ 24:00` 및 `00:00 ~ 02:00`)으로 분할 전송하여 MCU의 1분 암전(블랙아웃) 없이 매끄럽게 연속 점등됩니다:
```yaml
service: weekaqua.set_timer
data:
  start_time: "18:00"
  end_time: "02:00"
  preset: "GreenGrass"   # 또는 red, green, blue, white, uv, violet 값 직접 지정
  ramp_index: 2          # 램프 시간 (0: 0분, 1: 30분, 2: 1시간, 3: 1.5시간, 4: 2시간, 5: 2.5시간)
```

### 5. 수동 BLE 연결 해제 (스마트폰 공식 앱 사용 시)
```yaml
service: weekaqua.disconnect
```

