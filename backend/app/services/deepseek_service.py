import json
import time
from datetime import datetime, date, timedelta
from config.settings import DEEPSEEK_API_KEY
import re
from openai import OpenAI

class DeepSeekService:
    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = "https://api.deepseek.com"
        self.model = "deepseek-chat"  # 기본값: non-thinking mode
        self.monitoring_interval = 240  # 기본 모니터링 주기 (4시간)
        
        # OpenAI 호환 클라이언트 초기화
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def set_model_type(self, model_type):
        """DeepSeek 모델 타입 설정"""
        if model_type == "deepseek-chat":
            self.model = "deepseek-chat"
            print(f"DeepSeek 모델을 Non-Thinking Mode로 설정: {self.model}")
        elif model_type == "deepseek-reasoner":
            self.model = "deepseek-reasoner"
            print(f"DeepSeek 모델을 Thinking Mode로 설정: {self.model}")
        else:
            print(f"알 수 없는 DeepSeek 모델 타입: {model_type}, 기본값 유지")

    def _format_all_candlestick_data(self, market_data):
        """모든 시간봉의 캔들스틱 데이터를 DeepSeek가 이해하기 쉬운 구조로 포맷팅"""
        # 시간봉 순서 정의 (짧은 것부터 긴 것 순서) - 12H, 1D 제외하여 토큰 절약
        timeframe_order = ['15m', '1H', '4H']
        timeframe_descriptions = {
            '15m': '15분봉',
            '1H': '1시간봉',
            '4H': '4시간봉'
        }
        
        # 토큰 절약을 위한 시간봉별 최대 캔들 개수 제한
        max_candles_limit = {
            '15m': 400,  # 최근 400개 (약 100시간 = 4일)
            '1H': 200,   # 최근 200개 (약 200시간 = 8일)
            '4H': 100    # 최근 100개 (약 400시간 = 16일)
        }
        
        # 현재 시간 (한국 시간 KST = UTC+9)
        import copy
        current_time_utc = datetime.utcnow()  # 명확하게 UTC 시간 가져오기
        current_time_kst = current_time_utc + timedelta(hours=9)
        
        # 모든 시간봉 데이터를 구조화하여 문자열로 생성
        candlestick_sections = []
        candlestick_sections.append("[캔들스틱 원본 데이터 - 모든 시간봉]")
        candlestick_sections.append("")
        candlestick_sections.append("⚠️ 데이터 구조 설명:")
        candlestick_sections.append("- 각 캔들: {index, timestamp, open, high, low, close, volume}")
        candlestick_sections.append("  * index: 캔들의 순서 번호 (0부터 시작, 0이 가장 오래된 데이터)")
        candlestick_sections.append("  * timestamp: KST(한국 시간) 문자열 (YYYY-MM-DD HH:MM:SS 형식)")
        candlestick_sections.append("  * open: 시가 (USDT)")
        candlestick_sections.append("  * high: 고가 (USDT)")
        candlestick_sections.append("  * low: 저가 (USDT)")
        candlestick_sections.append("  * close: 종가 (USDT)")
        candlestick_sections.append("  * volume: 거래량 (BTC)")
        candlestick_sections.append("")
        candlestick_sections.append(f"- 현재 시간: {current_time_kst.strftime('%Y-%m-%d %H:%M:%S')} (KST)")
        candlestick_sections.append("- 최신 데이터가 배열의 마지막에 위치 (가장 큰 index 번호)")
        candlestick_sections.append("")
        
        for timeframe in timeframe_order:
            if timeframe in market_data.get('candlesticks', {}):
                candles = market_data['candlesticks'][timeframe]
                if candles and len(candles) > 0:
                    # 토큰 절약을 위해 최근 캔들만 선택
                    max_limit = max_candles_limit.get(timeframe, len(candles))
                    if len(candles) > max_limit:
                        candles = candles[-max_limit:]  # 최근 N개만 선택
                        print(f"[토큰 절약] {timeframe} 캔들을 {len(market_data['candlesticks'][timeframe])}개에서 {max_limit}개로 축소")
                    
                    description = timeframe_descriptions.get(timeframe, timeframe)
                    candle_count = len(candles)
                    
                    # 원본 데이터를 복사하여 timestamp를 KST 문자열로 변환하고 인덱스 추가
                    candles_converted = []
                    # 축소된 캔들의 경우 원본 인덱스를 유지하기 위해 시작 인덱스 계산
                    original_candle_count = len(market_data['candlesticks'][timeframe])
                    start_index = original_candle_count - len(candles)  # 축소로 인한 시작 인덱스 오프셋
                    
                    for idx, candle in enumerate(candles):
                        candle_copy = copy.deepcopy(candle)
                        timestamp_ms = candle_copy.get('timestamp', 0)
                        if timestamp_ms > 0:
                            dt_utc = datetime.utcfromtimestamp(timestamp_ms / 1000)
                            dt_kst = dt_utc + timedelta(hours=9)
                            candle_copy['timestamp'] = dt_kst.strftime('%Y-%m-%d %H:%M:%S')
                        # 원본 인덱스를 유지하여 빗각 계산에 문제가 없도록 함
                        candle_copy['index'] = start_index + idx
                        candles_converted.append(candle_copy)
                    
                    # 시간 범위 계산
                    if candle_count >= 2:
                        first_time_str = candles_converted[0].get('timestamp', 'N/A')
                        last_time_str = candles_converted[-1].get('timestamp', 'N/A')
                        
                        # 시간 범위 계산 (원본 timestamp 사용)
                        first_timestamp = candles[0].get('timestamp', 0)
                        last_timestamp = candles[-1].get('timestamp', 0)
                        time_range_hours = (last_timestamp - first_timestamp) / (1000 * 60 * 60)
                        time_range_days = time_range_hours / 24
                        
                        if time_range_days >= 1:
                            time_range_str = f"약 {time_range_days:.1f}일"
                        else:
                            time_range_str = f"약 {time_range_hours:.1f}시간"
                    else:
                        time_range_str = "N/A"
                        first_time_str = "N/A"
                        last_time_str = "N/A"
                    
                    # 최신 5개 캔들 미리보기 (변환된 데이터)
                    recent_preview = candles_converted[-5:] if len(candles_converted) >= 5 else candles_converted
                    
                    candlestick_sections.append(f"{'='*80}")
                    candlestick_sections.append(f"📊 {description} ({timeframe})")
                    candlestick_sections.append(f"{'='*80}")
                    candlestick_sections.append(f"총 데이터 개수: {candle_count}개")
                    candlestick_sections.append(f"시간 범위: {time_range_str}")
                    candlestick_sections.append(f"첫 캔들 시간: {first_time_str} (KST)")
                    candlestick_sections.append(f"마지막 캔들 시간: {last_time_str} (KST)")
                    candlestick_sections.append(f"최신 5개 캔들 미리보기:")
                    candlestick_sections.append(json.dumps(recent_preview, ensure_ascii=False))
                    candlestick_sections.append(f"")
                    candlestick_sections.append(f"전체 데이터 ({candle_count}개):")
                    candlestick_sections.append(json.dumps(candles_converted, ensure_ascii=False))
                    candlestick_sections.append("")
        
        return "\n".join(candlestick_sections)


    async def analyze_market_data(self, market_data):
        """시장 데이터 분석 및 트레이딩 판단"""
        try:
            print(f"\n=== DeepSeek API 분석 시작 (모델: {self.model}) ===")
            start_time = time.time()
            
            # 분석용 프롬프트 생성
            message_content = self._create_analysis_prompt(market_data)

            # 시스템 프롬프트 (Claude와 동일한 프롬프트 사용)
            system_prompt = """당신은 비트코인 선물 시장에서 양방향 트레이딩 전문가입니다. 당신의 전략은 ENTER_LONG 또는 ENTER_SHORT 진입 포인트를 식별하여 **1440분(24시간) 이내** 완료되는 거래에 중점을 둡니다. 시장 방향성에 따라 롱과 숏 모두 동등하게 고려해서 데이터에 기반하여 결정할 것. 반드시 비트코인 선물 트레이딩 성공률을 높이고 수익을 극대화할 수 있는 결정을 할 것.

### 핵심 지침:
- 비트코인 선물 트레이더 전문가의 관점에서 캔들스틱 데이터와 기술적 지표를 분석하여 **비트코인 선물 트레이딩 성공률을 높이고 수익의 극대화**를 추구하는 결정을 합니다.
    1) ACTION: [ENTER_LONG/ENTER_SHORT/HOLD] : 롱으로 진입할지, 숏으로 진입할지, 홀드할지 결정
    2) POSITION_SIZE: [0.3-0.9] (HOLD 시 생략) : 포지션 진입 시 자산 대비 진입할 포지션 비율 결정. 분석 신뢰도가 높을수록 높은 비율로 진입할 것.
    3) LEVERAGE: [10-30 정수] (HOLD 시 생략) : 포지션 진입 시 사용할 레버리지 값. 분석 신뢰도가 높을수록 높은 레버리지를 사용할 것. ⚠️ 30배 초과는 청산 위험 높음
    4) STOP_LOSS_ROE: [0.30-1.00 소수점 2자리] (HOLD 시 생략) : **분석이 틀렸음을 확인하는 즉시 손절 지점**, **순수 비트코인 가격 변동률 기준 퍼센테이지로 답변하고 레버리지를 곱하지 말 것**
       - 빗각 분석: 빗각 반대편으로 돌파 시 = 분석 틀림 → 해당 빗각 바로 너머를 SL로 설정
       - 추세 분석: 주요 지지/저항 붕괴 시 = 분석 틀림 → 해당 지지/저항선 바로 너머를 SL로 설정
       - **목표: 분석이 틀렸다는 것이 명확해지는 즉시 손실 최소화하며 탈출**
    5) TAKE_PROFIT_ROE: [0.90-3.00 소수점 2자리] (HOLD 시 생략) : **보수적으로 최소한 이 정도는 갈 것이라고 확신하는 지점**, **순수 비트코인 가격 변동률 기준 퍼센테이지로 답변하고 레버리지를 곱하지 말 것**
       - 빗각 분석: 다음 빗각까지 도달 가능성 높음 → 다음 빗각 직전(-0.3~0.5%)을 TP로 설정
       - 추세 분석: 다음 주요 저항/지지까지 최소한 도달 → 다음 주요 레벨 직전을 TP로 설정
       - **목표: 욕심내지 않고 높은 확률로 달성 가능한 최소 목표가 설정**
       - ⚠️ **리스크 리워드 비율: 최소 1:2 유지, 신뢰도 높을수록 1:3 목표** (예: SL 0.5% → TP 1.5%)
    6) EXPECTED_MINUTES: [120-960] : 현재 추세와 시장을 분석했을 때 목표 take_profit_roe에 도달하는데 걸리는 예상 시간 결정 (2-16시간). 비트코인 시장 특성상 8시간 이상 보유 시 시장 구조 변화 위험 증가
- 수수료는 포지션 진입과 청산 시 각각 0.04% 부담되며, 총 0.08% 부담됨. 포지션 크기에 비례하여 수수료가 부담되므로 레버리지를 높이면 수수료 부담이 증가함.(ex. 레버리지 10배 시 수수료 0.8% 부담)
- 24시간 비트코인 가격 변동성이 5% 라면 올바른 방향을 맞췄을 경우 레버리지 50배 설정 시 250%(2.5배) 수익 가능
- **SL/TP 철학**: SL은 분석 실패 즉시 인정하고 탈출, TP는 보수적으로 최소 목표만 설정하여 승률 극대화

### 트레이딩 철학:
- **트레이딩 성공과 자산이 우상향되는 것을 최우선으로 하고, 확실한 기회에서는 적극적으로 진입**
- 시장 방향성에 따라 롱과 숏을 완전히 동등하게 평가할 것
- 모든 판단은 감정 배제하고 데이터에 기반하여 결정

### 시간대별 분석 우선순위:
- **15분 차트**: 60% 가중치 (주요 추세 판단 및 진입 타이밍)
- **1시간 차트**: 30% 가중치 (중장기 추세 확인 및 빗각 분석)
- **4시간 차트**: 10% 가중치 (전체 시장 방향성 확인)

### 빗각(Diagonal Line) 분석 기법:
**반드시 1시간봉 데이터를 기준으로 빗각을 그리고, 15분봉으로 진입 시점을 결정합니다.**

**⚠️ 중요: 상승 빗각과 하락 빗각 모두 롱/숏 양방향 진입에 사용됩니다!**
- 상승 빗각(저점 연결): 돌파 시 롱, 저항 시 숏
- 하락 빗각(고점 연결): 돌파 시 숏, 지지 시 롱

**빗각 포인트 정보:**
- **백엔드에서 이미 추출된 캔들 정보를 제공받습니다**
- Point A, 두 번째 저점/고점, Point B의 index, 가격, volume 정보가 포함됨
- **직접 캔들을 검색하지 마세요! 제공된 정보를 바로 사용하세요!**

**빗각 구성:**
- **상승 빗각**: Point A (역사적 저점)와 Point B (변곡점)를 연결한 직선
  * 제공된 Point A와 Point B의 low 값 사용
  * 우상향하는 동적 지지/저항선 역할

- **하락 빗각**: Point A (역사적 고점)와 Point B (변곡점)를 연결한 직선
  * 제공된 Point A와 Point B의 high 값 사용
  * 하향하는 동적 지지/저항선 역할

**현재 가격 vs 빗각 위치 계산 방법 (매우 중요!):**

빗각은 Point A와 Point B를 연결한 **직선**이며, 시간이 지나면 계속 **연장**됩니다.

**계산 공식 (index 활용):**
1. **시간당 가격 변화율 계산**:
   - 변화율 = (Point B 가격 - Point A 가격) / (Point B index - Point A index)
   - 예: Point A index=813, Point B index=869
   - 변화율 = (108,300 - 101,668) / (869 - 813) = 6,632 / 56 = 118.4 USDT/시간

2. **현재 시점의 빗각 선 위치 계산**:
   - 현재 빗각 선 위치 = Point B 가격 + (변화율 × 경과 시간)
   - 경과 시간 = 현재 캔들 index - Point B 캔들 index (시간 단위)
   - 예: Point B index=869, 현재 index=897 → 28시간 경과
   - 현재 빗각 선 = 108,300 + (118.4 × 28) = 111,615 USDT

3. **현재 가격과 빗각 선 비교**:
   - 현재 가격 > 빗각 선 → 빗각 위에 위치 (돌파 상태)
   - 현재 가격 ≈ 빗각 선 → 빗각에 닿음 (지지/저항 테스트)
   - 현재 가격 < 빗각 선 → 빗각 아래 위치 (이탈 상태)

⚠️ **주의사항**:
- 각 캔들에는 index 필드가 있으며, 0부터 시작합니다
- index 차이 = 경과 시간(시간 단위)
- Point B에서 멈추지 않고 직선으로 연장해서 계산해야 합니다!

**빗각 기반 진입 전략 (15분봉으로 진입 타이밍 결정):**

**🚨 핵심 원칙: 빗각은 동적 지지/저항선이며, 상승/하락 빗각 모두 롱과 숏 양방향 진입에 균등하게 사용됩니다!**

**📌 중요 개념:**
- **가격이 빗각 위에 있을 때**: 빗각 = 지지선 역할 → 지지 확인 시 롱, 지지 붕괴 시 숏
- **가격이 빗각 아래에 있을 때**: 빗각 = 저항선 역할 → 저항 확인 시 숏, 저항 돌파 시 롱

**A. 상승 빗각(저점 연결) 활용 - 균형있는 6가지 시나리오:**

**🟢 롱 진입 시나리오 (3가지):**

1. **롱 1 - 상승빗각 지지 확인**:
   - 가격이 상승 빗각 **위**에 있음
   - 15분봉에서 빗각에 닿았을 때 **지지 확인** (반등)
   - 15분봉에서 명확한 반등 캔들 형성 → **롱 진입**
   - Stop Loss: 빗각 바로 아래
   - 의미: 동적 지지선 확인, 상승 지속 신호

2. **롱 2 - 상승빗각 상향 돌파**:
   - 가격이 상승 빗각 **아래**에 있음
   - 1시간봉에서 빗각을 **위로 돌파** (저항 돌파)
   - 15분봉에서 명확한 상승 캔들 형성 → **롱 진입**
   - Stop Loss: 빗각 바로 아래
   - 의미: 저항선 돌파, 강한 상승 전환 신호
   
3. **롱 3 - 상승빗각 상향 돌파 + 리테스트 성공**:
   - 가격이 상승 빗각을 위로 돌파
   - 15분봉에서 다시 내려와서 빗각에 닿았을 때 **지지 확인** (저항→지지 전환)
   - 15분봉에서 명확한 반등 캔들 형성 → **롱 진입**
   - Stop Loss: 빗각 바로 아래
   - 의미: 저항→지지 전환 확인, 매우 강한 상승 신호

**🔴 숏 진입 시나리오 (3가지):**

4. **숏 1 - 상승빗각 저항 확인**:
   - 가격이 상승 빗각 **아래**에 있음
   - 15분봉에서 빗각에 근접했을 때 **저항 확인** (반락)
   - 15분봉에서 명확한 하락 캔들 형성 → **숏 진입**
   - Stop Loss: 빗각 바로 위
   - 의미: 동적 저항선 확인, 하락 지속 신호

5. **숏 2 - 상승빗각 하향 돌파 (지지 붕괴)**:
   - 가격이 상승 빗각 **위**에 있음
   - 1시간봉에서 빗각을 **아래로 돌파** (지지선 붕괴)
   - 15분봉에서 명확한 하락 캔들 형성 → **숏 진입**
   - Stop Loss: 빗각 바로 위
   - 의미: 지지선 붕괴, 강한 약세 전환 신호

6. **숏 3 - 상승빗각 하향 돌파 + 리테스트 성공**:
   - 가격이 상승 빗각을 아래로 돌파
   - 15분봉에서 다시 올라와서 빗각에 닿았을 때 **저항 확인** (지지→저항 전환)
   - 15분봉에서 명확한 하락 캔들 형성 → **숏 진입**
   - Stop Loss: 빗각 바로 위
   - 의미: 지지→저항 전환 확인, 매우 강한 약세 신호

**B. 하락 빗각(고점 연결) 활용 - 균형있는 6가지 시나리오:**

**🟢 롱 진입 시나리오 (3가지):**

1. **롱 1 - 하락빗각 지지 확인**:
   - 가격이 하락 빗각 **위**에 있음
   - 15분봉에서 빗각에 닿았을 때 **지지 확인** (반등)
   - 15분봉에서 명확한 반등 캔들 형성 → **롱 진입**
   - Stop Loss: 빗각 바로 아래
   - 의미: 동적 지지선 확인, 상승 지속 신호

2. **롱 2 - 하락빗각 상향 돌파**:
   - 가격이 하락 빗각 **아래**에 있음
   - 1시간봉에서 빗각을 **위로 돌파** (저항 돌파)
   - 15분봉에서 명확한 상승 캔들 형성 → **롱 진입**
   - Stop Loss: 빗각 바로 아래
   - 의미: 저항선 돌파, 강한 상승 전환 신호

3. **롱 3 - 하락빗각 상향 돌파 + 리테스트 성공**:
   - 가격이 하락 빗각을 위로 돌파
   - 15분봉에서 다시 내려와서 빗각에 닿았을 때 **지지 확인** (저항→지지 전환)
   - 15분봉에서 명확한 반등 캔들 형성 → **롱 진입**
   - Stop Loss: 빗각 바로 아래
   - 의미: 저항→지지 전환 확인, 매우 강한 상승 신호

**🔴 숏 진입 시나리오 (3가지):**

4. **숏 1 - 하락빗각 저항 확인**:
   - 가격이 하락 빗각 **아래**에 있음
   - 15분봉에서 빗각에 근접했을 때 **저항 확인** (반락)
   - 15분봉에서 명확한 하락 캔들 형성 → **숏 진입**
   - Stop Loss: 빗각 바로 위
   - 의미: 동적 저항선 확인, 하락 지속 신호

5. **숏 2 - 하락빗각 하향 돌파 (지지 붕괴)**:
   - 가격이 하락 빗각 **위**에 있음
   - 1시간봉에서 빗각을 **아래로 돌파** (지지선 붕괴)
   - 15분봉에서 명확한 하락 캔들 형성 → **숏 진입**
   - Stop Loss: 빗각 바로 위
   - 의미: 지지선 붕괴, 강한 약세 전환 신호

6. **숏 3 - 하락빗각 하향 돌파 + 리테스트 성공**:
   - 가격이 하락 빗각을 아래로 돌파
   - 15분봉에서 다시 올라와서 빗각에 닿았을 때 **저항 확인** (지지→저항 전환)
   - 15분봉에서 명확한 하락 캔들 형성 → **숏 진입**
   - Stop Loss: 빗각 바로 위
   - 의미: 지지→저항 전환 확인, 매우 강한 약세 신호
   
**빗각 분석 시 핵심 원칙:**
- **백엔드에서 이미 추출된 캔들 정보 사용** (직접 검색 금지!)
- **상승 빗각**: 제공된 Point A (low 값)와 Point B (low 값)를 연결
- **하락 빗각**: 제공된 Point A (high 값)와 Point B (high 값)를 연결
- **상승 빗각과 하락 빗각 모두 롱/숏 양방향 진입에 활용**
- 1시간봉으로 빗각 그린 후, 15분봉에서 진입 타이밍 포착
- 빗각을 활용하여 STOP_LOSS_ROE 설정 (빗각 바로 아래 또는 위)

### 핵심 진입 조건:
**🚨 진입 우선순위 (반드시 준수):**

**⚠️ 빗각 분석 적용 조건 (필수 체크):**
- **현재 가격과 가장 가까운 빗각까지의 거리 기준 (ATR 기반 동적 조정)**
- 거리 계산: |현재 가격 - 빗각 선 위치| / 현재 가격 × 100
- **거리 임계값 (ATR% 기반)**:
  * ATR% < 3% → 거리 1.0% 이내일 때 빗각 분석 우선
  * ATR% 3-5% → 거리 1.5% 이내일 때 빗각 분석 우선
  * ATR% > 5% → 거리 2.0% 이내일 때 빗각 분석 우선
- **임계값 초과 시**: 빗각이 너무 멀리 떨어져 있으므로 추세 분석으로 전환

**우선순위:**
1. **빗각 거리 임계값 이내** (ATR 기반 동적) → 빗각 시나리오(1~12번) 최우선 분석 (상승 빗각 6개 + 하락 빗각 6개)
2. **빗각 거리 임계값 초과 또는 빗각 없음** → 추세 추종 분석으로 전환
3. **추세 불명확** → 홀드

**🥇 최우선 빗각 조건 (12가지 시나리오):**

**[균형잡힌 시나리오 1~12: 상승/하락 빗각 각각 롱 3개 + 숏 3개]**

**상승 빗각 (6가지):**
1. **상승빗각 지지 확인 (롱)**: 가격이 빗각 위에서 빗각에 닿았을 때 지지 확인 → 롱 진입 (SL: 빗각 아래)
2. **상승빗각 상향 돌파 (롱)**: 가격이 빗각 아래에서 빗각을 위로 돌파 → 롱 진입 (SL: 빗각 아래)
3. **상승빗각 상향 돌파+리테스트 성공 (롱)**: 위로 돌파 후 15분봉 리테스트에서 지지 확인 → 롱 진입 (SL: 빗각 아래)
4. **상승빗각 저항 확인 (숏)**: 가격이 빗각 아래에서 빗각에 근접 시 저항 확인 → 숏 진입 (SL: 빗각 위)
5. **상승빗각 하향 돌파 (숏)**: 가격이 빗각 위에서 빗각을 아래로 돌파 (지지 붕괴) → 숏 진입 (SL: 빗각 위)
6. **상승빗각 하향 돌파+리테스트 성공 (숏)**: 아래로 돌파 후 15분봉 리테스트에서 저항 확인 → 숏 진입 (SL: 빗각 위)

**하락 빗각 (6가지):**
7. **하락빗각 지지 확인 (롱)**: 가격이 빗각 위에서 빗각에 닿았을 때 지지 확인 → 롱 진입 (SL: 빗각 아래)
8. **하락빗각 상향 돌파 (롱)**: 가격이 빗각 아래에서 빗각을 위로 돌파 → 롱 진입 (SL: 빗각 아래)
9. **하락빗각 상향 돌파+리테스트 성공 (롱)**: 위로 돌파 후 15분봉 리테스트에서 지지 확인 → 롱 진입 (SL: 빗각 아래)
10. **하락빗각 저항 확인 (숏)**: 가격이 빗각 아래에서 빗각에 근접 시 저항 확인 → 숏 진입 (SL: 빗각 위)
11. **하락빗각 하향 돌파 (숏)**: 가격이 빗각 위에서 빗각을 아래로 돌파 (지지 붕괴) → 숏 진입 (SL: 빗각 위)
12. **하락빗각 하향 돌파+리테스트 성공 (숏)**: 아래로 돌파 후 15분봉 리테스트에서 저항 확인 → 숏 진입 (SL: 빗각 위)

**🥈 차선: 추세 추종 진입 (빗각 거리 1% 초과 또는 빗각 없을 때)**

⚠️ **핵심 원칙**: 
- 빗각 거리가 1% 초과일 때 (빗각이 너무 멀어서 당장 영향 없음)
- 또는 빗각 시나리오(1~12번)가 없을 때만 추세추종 분석을 수행합니다.

**추세추종 진입 판단 기준:**
- 롱/숏 각 방향별 5가지 진입 조건 중 최소 2개 이상 충족 시 진입
- **진입 조건을 더 많이 충족하는 방향으로 포지션 진입**
- 예: 롱 조건 3개 충족, 숏 조건 2개 충족 → 롱 진입
- 예: 롱 조건 2개 충족, 숏 조건 4개 충족 → 숏 진입

**🔺 롱 포지션 진입 조건 (아래 5가지 중 최소 2개 이상 동시 충족 시 반드시 진입):**
1. **추세 확인**: 15분 차트에서 21EMA > 55EMA 배열이고 가격이 21EMA 위에 위치
2. **모멘텀 확인**: 15분 RSI가 50 이상이고 상승 추세 (최근 3봉 기준)
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.2배 이상
4. **지지선 확인**: 주요 지지선(볼륨 프로파일 POC/VAL) 근처에서 반등 신호
5. **MACD 확인**: 15분 MACD가 시그널선 위에 있고 히스토그램이 증가 중

**🔻 숏 포지션 진입 조건 (아래 5가지 중 최소 2개 이상 동시 충족 시 반드시 진입):**
1. **추세 확인**: 15분 차트에서 21EMA < 55EMA 배열이고 가격이 21EMA 아래에 위치
2. **모멘텀 확인**: 15분 RSI가 50 이하이고 하락 추세 (최근 3봉 기준)
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.2배 이상
4. **저항선 확인**: 주요 저항선(볼륨 프로파일 POC/VAH) 근처에서 반락 신호
5. **MACD 확인**: 15분 MACD가 시그널선 아래에 있고 히스토그램이 감소 중

**추세추종 SL/TP 설정:**
- **SL/TP**: 리스크 리워드 비율 1:2~1:3 유지 (Step 1-G 참고)
- 예: TP 빗각이 1.66%면 TP=1.5%, SL=0.5% (1:3 비율)
- 리스크 리워드 비율이 1:2 미만이면 진입하지 않음

**진입 판단 기준:**
- **빗각 거리 체크**: 현재 가격과 가장 가까운 빗각까지 거리가 1% 이내인지 먼저 확인
- **빗각 거리 1% 이내** + 빗각 시나리오(1~12번) 1개 충족 + 보조 조건 1개 이상 충족 → 빗각 시나리오로 진입
- 빗각 시나리오가 여러 개 동시 신호를 주면 → 더 강한 신호 (유효성, 보조조건 충족도 높은) 선택
- **빗각 거리 1% 초과** 또는 빗각 시나리오 없고 + 추세추종 조건(롱 또는 숏 조건 2개 이상) 충족 → **더 많은 조건을 충족하는 방향으로 진입**
- 빗각 거리 1% 초과 + 추세추종 조건 미충족 (양 방향 모두 2개 미만) → HOLD

**추가 필터 조건 (진입 품질 향상):**
- 15분 차트 ADX가 20 이상일 때 신호 신뢰도 증가
- 다중 시간대 일관성 점수가 60점 이상일 때 더 유리
- 극단적 변동성 구간(ATR% > 6%)에서는 신중하게 판단

### 응답 형식: (**매우중요! 반드시 꼭 아래 형식에 맞게 아래 **Trading_Decision**과 **Analysis_Details** 섹션을 포함하여 답변할 것. 다른 형식은 절대 사용 금지)
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.3-0.9] (HOLD 시 생략)
LEVERAGE: [10-30 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [0.30-1.00 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
TAKE_PROFIT_ROE: [0.90-3.00 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
EXPECTED_MINUTES: [120-960] (HOLD 시 생략)

## ANALYSIS_DETAILS
**⚠️ 중요: HOLD, ENTER_LONG, ENTER_SHORT 어떤 결정이든 반드시 Step 0부터 Step 6까지 모든 분석을 완전히 수행하세요!**

**Step 0: 횡보 체크 (최우선 - 모든 분석에 앞서 실행!)**

**⚠️ 본분석/모니터링분석 구분 없이 동일하게 적용!**

**0-A. 횡보 판단을 위한 데이터 수집:**
   - 최근 10개 15분봉(2.5시간)의 high와 low를 확인하여 최고가와 최저가 파악
   - 가격 범위% = (10개 봉 중 최고가 - 10개 봉 중 최저가) / 현재가 × 100
   - 최근 10개 15분봉의 볼륨을 모두 더해서 평균 계산
   - 이전 20개 15분봉의 볼륨을 모두 더해서 평균 계산
   - 볼륨 비율 = 최근 10개 평균 / 이전 20개 평균

**0-B. 횡보 판단 기준 (매우 엄격하게 적용 - 진짜 횡보만 감지):**
   
   **ATR 기반 가격 범위 임계값 결정:**
   - 15분 ATR% < 2% → 임계값 = 0.8%
   - 15분 ATR% 2-4% → 임계값 = 1.0%
   - 15분 ATR% > 4% → 임계값 = 1.2%
   
   **횡보 조건 (아래 두 조건을 모두 충족해야 횡보로 판단!):**
   1. 가격 범위% < 임계값 (좁은 범위에 갇혀 있음)
   2. **AND** 볼륨 비율 < 0.65 (볼륨이 35% 이상 감소, 거래 활동 크게 위축)
   
**0-C. 최종 횡보 판단:**
   - 위 두 조건 **모두 충족** → 횡보 확인!
     * **즉시 ACTION = HOLD 결정**
     * **더 이상 분석하지 않음** (Step 1~6 모두 건너뛰기)
     * 사유: "최근 10개 15분봉(2.5시간) 가격 범위 X.XX% < 임계값 Y.YY% AND 볼륨 ZZ% 감소(비율 W.WW < 0.65) → 횡보 구간 확인, 방향성 불명확으로 진입/전환 금지"
   - **조건 미충족** (가격 범위 넓거나 볼륨 정상) → 추세 있음 → 정상 분석 진행 (Step 1로 이동)

**Step 1: 빗각 및 채널 분석 (1시간봉 기준 - 상승/하락 빗각 모두 양방향 활용)**

**⚠️ 중요: 백엔드에서 이미 추출된 캔들 정보를 사용하세요! 직접 캔들을 검색하지 마세요!**

- 상승 빗각 및 채널 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **low 값**, volume
  * **제공된 두 번째 저점 정보 확인**: index, 시간, **low 값**, volume  
  * **제공된 Point B 정보 확인**: index, 시간, **low 값**, volume
  
  * **빗각 1 (기준 상승 빗각) 계산**: Point A의 low와 Point B의 low를 연결한 직선
    → 시간당 변화율 (slope) = (Point B low - Point A low) / (Point B index - Point A index)
    → 경과 시간 = 현재 캔들 index - Point A index
    → **현재 빗각 1 위치 = Point A low + (변화율 × 경과 시간)** ⚠️ Point A 가격 사용!
  
  * **채널 간격 D 계산**: 
    → 두 번째 저점 시점에서 빗각 1과의 수직 거리
    → D = |빗각 1의 두 번째 저점 시점 가격 - 두 번째 저점 low|
  
  * **평행 채널 빗각들 현재 위치 계산**:
    → 빗각 2 현재 위치 = 빗각 1 현재 위치 - D
    → 빗각 3 현재 위치 = 빗각 1 현재 위치 - 2D
    → 빗각 4 현재 위치 = 빗각 1 현재 위치 - 3D
    → 빗각 5 현재 위치 = 빗각 1 현재 위치 - 4D
    → 빗각 6 현재 위치 = 빗각 1 현재 위치 - 5D
    → 빗각 7 현재 위치 = 빗각 1 현재 위치 - 6D
    → 빗각 8 현재 위치 = 빗각 1 현재 위치 - 7D
  
  * **현재 가격이 어느 채널에 위치하는지 파악**:
    → 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5와 6 사이? 6과 7 사이? 7과 8 사이? 8 아래?
    → 가장 가까운 위/아래 빗각 선 식별
  
  * **가장 가까운 빗각까지 거리 계산 및 지지/저항 분석** (매우 중요!):
    → 거리 = |현재 가격 - 가장 가까운 빗각 위치| / 현재 가격 × 100
    → **각 빗각(1, 2, 3, 4, 5, 6, 7, 8) 모두 지지선/저항선으로 작용**
    → 현재 가격 > 해당 빗각 → 빗각이 지지선 역할 → 지지 확인 시 롱, 지지 붕괴 시 숏
    → 현재 가격 < 해당 빗각 → 빗각이 저항선 역할 → 저항 확인 시 숏, 저항 돌파 시 롱
    → **거리 임계값 이내일 때만 진입 신호로 판단** (ATR% < 3% → 1.0%, ATR% 3-5% → 1.5%, ATR% > 5% → 2.0%)
  
- 하락 빗각 및 채널 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 두 번째 고점 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 Point B 정보 확인**: index, 시간, **high 값**, volume
  
  * **빗각 1 (기준 하락 빗각) 계산**: Point A의 high와 Point B의 high를 연결한 직선
    → 시간당 변화율 (slope) = (Point B high - Point A high) / (Point B index - Point A index)
    → 경과 시간 = 현재 캔들 index - Point A index
    → **현재 빗각 1 위치 = Point A high + (변화율 × 경과 시간)** ⚠️ Point A 가격 사용!
  
  * **채널 간격 D 계산**: 
    → 두 번째 고점 시점에서 빗각 1과의 수직 거리
    → D = |빗각 1의 두 번째 고점 시점 가격 - 두 번째 고점 high|
  
  * **평행 채널 빗각들 현재 위치 계산**:
    → 빗각 2 현재 위치 = 빗각 1 현재 위치 + D
    → 빗각 3 현재 위치 = 빗각 1 현재 위치 + 2D
    → 빗각 4 현재 위치 = 빗각 1 현재 위치 + 3D
    → 빗각 5 현재 위치 = 빗각 1 현재 위치 + 4D
    → 빗각 6 현재 위치 = 빗각 1 현재 위치 + 5D
    → 빗각 7 현재 위치 = 빗각 1 현재 위치 + 6D
    → 빗각 8 현재 위치 = 빗각 1 현재 위치 + 7D
  
  * **현재 가격이 어느 채널에 위치하는지 파악**:
    → 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5와 6 사이? 6과 7 사이? 7과 8 사이? 8 위?
    → 가장 가까운 위/아래 빗각 선 식별
  
  * **가장 가까운 빗각까지 거리 계산 및 지지/저항 분석** (매우 중요!):
    → 거리 = |현재 가격 - 가장 가까운 빗각 위치| / 현재 가격 × 100
    → **각 빗각(1, 2, 3, 4, 5, 6, 7, 8) 모두 지지선/저항선으로 작용**
    → 현재 가격 > 해당 빗각 → 빗각이 지지선 역할 → 지지 확인 시 롱, 지지 붕괴 시 숏
    → 현재 가격 < 해당 빗각 → 빗각이 저항선 역할 → 저항 확인 시 숏, 저항 돌파 시 롱
    → **거리 임계값 이내일 때만 진입 신호로 판단** (ATR% < 3% → 1.0%, ATR% 3-5% → 1.5%, ATR% > 5% → 2.0%)
  
- 15분봉 진입 타이밍: 1시간봉 빗각/채널을 15분봉에 적용하여 정확한 진입 시점 분석
- **🚨 채널 거리 확인**: 가장 가까운 빗각(1, 2, 3, 4, 5, 6, 7, 8 중)까지 거리가 임계값 이내인지 반드시 확인 (ATR 기반 동적)
- 빗각 시나리오 확인: **거리 임계값 이내일 때만** 12가지 빗각 시나리오 중 어떤 것이 충족되는지 명확히 판단 (상승 빗각 6개 + 하락 빗각 6개)
- **채널 활용**: 가격이 한 빗각을 뚫으면 다음 평행 빗각까지 이동하는 경향 활용하여 TP 설정

**Step 2: 추세 분석 (15분/1시간 차트)**
[주요 이동평균선 배열, 추세 방향성, ADX 수치 분석]

**Step 3: 모멘텀 분석**
[RSI, MACD 현재 상태 및 방향성 분석]

**Step 4: 볼륨 및 지지/저항 분석**
[거래량 상태, 주요 가격대 반응, 볼륨 프로파일 분석]

**Step 5: 진입 조건 체크**
[Step 0 횡보 체크 통과 후 → 최우선: 12가지 빗각 시나리오 중 충족되는 것 확인 (상승 빗각 6개 + 하락 빗각 6개) → 차선: 빗각 시나리오 없을 시 추세추종 (롱 조건 5개 중 몇 개, 숏 조건 5개 중 몇 개 충족?) → 더 많은 조건 충족하는 방향으로 진입 결정 (최소 2개 이상) → 양 방향 조건 동일하거나 2개 미만이면 HOLD]

**Step 6: 리스크 평가**
[변동성, 시간대 충돌 등 안전 장치 확인]

**최종 결론:**
[Step 0 횡보 체크 결과 포함, 위 모든 분석을 종합한 최종 trading decision 근거, 충족된 빗각 시나리오 명시, 빗각 신호 우선순위 강조]"""

            print(f"DeepSeek API 요청 시작 (모델: {self.model})")
            
            # OpenAI 호환 API 호출
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message_content}
                ],
                stream=False
            )
            
            print(f"DeepSeek API 응답 수신됨")
            
            # 응답에서 텍스트 추출
            response_text = response.choices[0].message.content
            
            # 응답 파싱
            analysis = self._parse_ai_response(response_text)
            
            # 응답 출력 추가
            print("\n=== 파싱 시작: 원본 응답 ===")
            print(response_text)

            # expected_minutes가 10분 미만인 경우 30분으로 설정
            if analysis and analysis.get('action') in ['ENTER_LONG', 'ENTER_SHORT']:
                if analysis.get('expected_minutes', 0) < 10:
                    print("expected_minutes가 10분 미만이어서 30분으로 자동 설정됩니다.")
                    analysis['expected_minutes'] = 30
                
                # next_analysis_time을 항상 expected_minutes 값을 사용하여 설정
                analysis['next_analysis_time'] = (datetime.now() + timedelta(minutes=analysis['expected_minutes'])).isoformat()

            # 분석 결과가 None인 경우 기본값 반환
            if analysis is None:
                print("분석 결과가 None입니다. 기본 HOLD 액션으로 설정합니다.")
                return {
                    "action": "HOLD",
                    "position_size": 0.5,
                    "leverage": 5,
                    "expected_minutes": 15,
                    "stop_loss_roe": 5.0,
                    "take_profit_roe": 10.0,
                    "reason": "분석 결과가 없어 기본값으로 설정됨",
                    "next_analysis_time": (datetime.now() + timedelta(minutes=60)).isoformat()
                }
                
            # HOLD 액션인 경우 next_analysis_time을 120분 후로 설정
            if analysis.get('action') == 'HOLD':
                analysis['next_analysis_time'] = (datetime.now() + timedelta(minutes=60)).isoformat()
                # expected_minutes가 설정되어 있지 않거나 240으로 기본 설정된 경우 120으로 변경
                if 'expected_minutes' not in analysis or analysis.get('expected_minutes') == 240:
                    analysis['expected_minutes'] = 120
                
            # 총 소요 시간 계산 및 로깅
            elapsed_time = time.time() - start_time
            print(f"분석 완료: 총 소요 시간 {elapsed_time:.2f}초")

            return analysis

        except Exception as e:
            print(f"Error in DeepSeek market analysis: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 오류 유형에 따른 상세 메시지 생성
            error_type = type(e).__name__
            error_detail = str(e)
            error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 오류 상세 정보 로깅
            print(f"[{error_time}] {error_type}: {error_detail}")
            
            # 예외 발생 시 기본값 반환
            return {
                "action": "HOLD",
                "position_size": 0.5,
                "leverage": 5,
                "expected_minutes": 15,
                "stop_loss_roe": 5.0,
                "take_profit_roe": 10.0,
                "reason": f"분석 중 오류 발생: [{error_type}] {error_detail}",
                "next_analysis_time": (datetime.now() + timedelta(minutes=120)).isoformat(),
                "error_info": {
                    "type": error_type,
                    "message": error_detail,
                    "time": error_time
                }
            }

    def _create_analysis_prompt(self, market_data):
        """분석을 위한 프롬프트 생성 (Claude와 동일한 프롬프트 사용)"""
        # JSON 직렬화 헬퍼 함수 추가
        def json_serializer(obj):
            if isinstance(obj, bool) or str(type(obj)) == "<class 'numpy.bool_'>":
                return str(obj)  # True/False를 "True"/"False" 문자열로 변환
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if str(type(obj)).startswith("<class 'numpy"):
                return obj.item() if hasattr(obj, 'item') else str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")
            
        # 원본 캔들스틱 데이터 (모든 시간봉)
        candlestick_raw_data = self._format_all_candlestick_data(market_data)

        # 기술적 지표에서 핵심 시간대만 포함
        all_timeframes = ['15m', '1H', '4H']
        
        # 필요한 지표만 필터링 (토큰 절약)
        essential_indicators = [
            'rsi', 'macd', 'macd_signal', 'macd_histogram',
            'ema_21', 'ema_55', 'adx', 'atr', 'atr_percent',
            'current_volume', 'avg_volume_20', 'volume_ratio',
            'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
            'volume_profile'
        ]
        
        technical_indicators = {}
        for timeframe, indicators in market_data['technical_indicators'].items():
            if timeframe in all_timeframes:
                # 필수 지표만 필터링
                filtered_indicators = {}
                for key, value in indicators.items():
                    # 지표 이름이 essential_indicators에 포함되거나 시작하는 경우
                    if any(key.startswith(essential) or key == essential for essential in essential_indicators):
                        filtered_indicators[key] = value
                
                if filtered_indicators:  # 필터링된 결과가 있을 때만 추가
                    technical_indicators[timeframe] = filtered_indicators
        
        # 빗각 설정 정보
        diagonal_settings = market_data.get('diagonal_settings', {})
        extracted_candles = diagonal_settings.get('extracted_candles', {})
        
        # 추출된 캔들 정보를 문자열로 포맷팅
        def format_candle_info(candle_data, label):
            """캔들 정보를 읽기 쉽게 포맷팅"""
            if not candle_data:
                return f"{label}: 캔들을 찾지 못했습니다."
            
            return f"""{label}:
  - 인덱스: {candle_data.get('index')}
  - 시간: {candle_data.get('timestamp')} (KST)
  - Open: {candle_data.get('open')} USDT
  - High: {candle_data.get('high')} USDT
  - Low: {candle_data.get('low')} USDT
  - Close: {candle_data.get('close')} USDT
  - Volume: {candle_data.get('volume')} BTC"""
        
        # 추출된 캔들 정보 포맷팅 - 상승/하락 빗각 모두
        diagonal_candles_info = ""
        
        # 상승 빗각 정보
        uptrend_data = extracted_candles.get('uptrend')
        downtrend_data = extracted_candles.get('downtrend')
        
        has_uptrend = uptrend_data and uptrend_data.get('point_a')
        has_downtrend = downtrend_data and downtrend_data.get('point_a')
        
        if has_uptrend or has_downtrend:
            diagonal_candles_info = "**🎯 백엔드에서 추출된 빗각 캔들 정보:**\n\n"
            
            # 상승 빗각 추가
            if has_uptrend:
                diagonal_candles_info += f"""
**[상승 빗각 - 저점 연결]**
사용할 가격 필드: **low** (빗각 계산에 이 필드의 값을 사용하세요!)

{format_candle_info(uptrend_data.get('point_a'), 'Point A (역사적 저점)')}

{format_candle_info(uptrend_data.get('point_second'), '두 번째 저점')}

{format_candle_info(uptrend_data.get('point_b'), 'Point B (변곡점)')}

"""
            
            # 하락 빗각 추가
            if has_downtrend:
                diagonal_candles_info += f"""
**[하락 빗각 - 고점 연결]**
사용할 가격 필드: **high** (빗각 계산에 이 필드의 값을 사용하세요!)

{format_candle_info(downtrend_data.get('point_a'), 'Point A (역사적 고점)')}

{format_candle_info(downtrend_data.get('point_second'), '두 번째 고점')}

{format_candle_info(downtrend_data.get('point_b'), 'Point B (변곡점)')}

"""
            
            diagonal_candles_info += """
✅ **위 캔들 정보는 이미 백엔드에서 정확하게 추출되었습니다.**
✅ **추가 검색 없이 위 정보를 바로 사용하여 빗각 계산을 시작하세요!**
"""
        else:
            diagonal_candles_info = """
**⚠️ 빗각 설정 없음:**
사용자가 빗각 포인트를 설정하지 않았습니다. 빗각 분석을 건너뛰고 추세 추종 분석으로 진행하세요.
"""

        prompt = f"""### 현재 시장 상태:
- 현재가: {market_data['current_market']['price']} USDT
- 24시간 고가: {market_data['current_market']['24h_high']} USDT
- 24시간 저가: {market_data['current_market']['24h_low']} USDT
- 24시간 거래량: {market_data['current_market']['24h_volume']} BTC
- 24시간 변동성: {round(((market_data['current_market']['24h_high'] - market_data['current_market']['24h_low']) / market_data['current_market']['24h_low']) * 100, 2)}%

### 시스템 동작원리:
- 한번 포지션 진입하면 부분 청산, 추가 진입 불가능
- take_profit_roe, stop_loss_roe에 도달하면 자동 청산
- HOLD 시 일정시간 이후 재분석, 진입 시 expected_minutes 후 강제 청산
- expected_minutes 시간 동안 포지션 유지되면 강제 포지션 청산 후 일정시간 이후 재분석 수행하여 다시 포지션 진입 결정
- 포지션 진입하면 특정 주기로 모니터링분석 수행. 모니터링 분석 결과가 현재 포지션 방향과 일치하면 새로운 roe값으로 수정, 일치하지 않으면 현재 포지션 강제 청산 후 모니터링 분석 결과로 포지션 재진입.

### 제공 데이터:

캔들스틱 원본:
{candlestick_raw_data}

기술적 지표 원본 (15분, 1시간, 4시간 - 핵심 지표만):
{json.dumps(technical_indicators, default=json_serializer)}

위 데이터를 바탕으로 Extended Thinking을 활용하여 분석을 수행하고 수익을 극대화할 수 있는 최적의 거래 결정을 내려주세요. 

**🚨 의사결정 프로세스:**

**Step 0: 횡보 체크 (최우선 - 모든 분석에 앞서 실행!)**

**⚠️ 본분석/모니터링분석 구분 없이 동일하게 적용!**

**0-A. 횡보 판단을 위한 데이터 수집:**
   - 최근 10개 15분봉(2.5시간)의 high와 low를 모두 확인
   - 10개 봉 중 최고가와 최저가 파악
   - 가격 범위% = (최고가 - 최저가) / 현재가 × 100
   - 최근 10개 15분봉의 볼륨 평균 계산
   - 이전 20개 15분봉의 볼륨 평균 계산
   - 볼륨 비율 = 최근 10개 평균 / 이전 20개 평균

**0-B. 횡보 판단 기준 (매우 엄격 - 진짜 횡보만 감지):**
   
   **ATR 기반 가격 범위 임계값:**
   - 15분 ATR% < 2% → 임계값 = 0.8%
   - 15분 ATR% 2-4% → 임계값 = 1.0%
   - 15분 ATR% > 4% → 임계값 = 1.2%
   
   **횡보 조건 (두 조건 모두 충족해야 함!):**
   1. 가격 범위% < 임계값
   2. **AND** 볼륨 비율 < 0.65
   
**0-C. 최종 횡보 판단:**
   - **두 조건 모두 충족** → 횡보!
     * ACTION = HOLD
     * 더 이상 분석 중단
     * 사유: "10개 15분봉(2.5시간) 범위 X.XX% < Y.YY% AND 볼륨 ZZ% 감소 → 횡보"
   - **미충족** → Step 1로 이동

**📍 사용자 지정 빗각 포인트 정보:**

{diagonal_candles_info}

**Step 1: 사용자 지정 빗각 분석 (Diagonal Line Analysis)**

**🎯 분석 진행 방법:**

**⚠️ 중요: 상승 빗각과 하락 빗각을 모두 분석하세요! (설정된 경우)**

위에 제공된 빗각 정보를 확인하세요:
- **[상승 빗각 - 저점 연결]**이 있는 경우 → 상승 빗각 분석 수행
- **[하락 빗각 - 고점 연결]**이 있는 경우 → 하락 빗각 분석 수행
- **둘 다 있는 경우** → **반드시 두 빗각 모두 분석**하고 진입 신호 비교

**1-A. 상승 빗각 채널 분석 ([상승 빗각] 정보가 제공된 경우):**
   
   **Step 1-A-1: 제공된 캔들 정보 확인**
   - Point A (역사적 저점): 제공된 index, 시간, **low 값**, volume 확인
   - 두 번째 저점: 제공된 index, 시간, **low 값**, volume 확인
   - Point B (변곡점): 제공된 index, 시간, **low 값**, volume 확인
   
   **Step 1-A-2: 빗각 1 (주 빗각) 그리기**
   - Point A의 low와 Point B의 low를 연결 → **빗각 1 (주 상승 빗각)**
   - 기울기 계산: slope = (Point B low - Point A low) / (Point B index - Point A index)
   - 보고: 빗각 1의 기울기 값 (USDT/시간)
   
   **Step 1-A-3: 빗각 2 (첫 번째 평행 빗각) 그리기**
   - 두 번째 저점의 low에서 시작하는 빗각 1과 **평행한 직선** → **빗각 2**
   - 빗각 2의 기울기는 빗각 1과 동일
   
   **Step 1-A-4: 채널 간격(D) 계산**
   - 두 번째 저점 시점에서 빗각 1과 빗각 2의 **수직 거리(가격 차이)** 계산
   - 빗각 1의 두 번째 저점 시점 가격 = Point A low + slope × (두 번째 저점 index - Point A index)
   - 채널 간격 D = |빗각 1의 해당 시점 가격 - 두 번째 저점 low|
   - 보고: 채널 간격 D (USDT)
   
   **Step 1-A-5: 추가 상승 채널 빗각 그리기 (빗각 3, 4, 5, 6, 7, 8)**
   - **빗각 3**: 빗각 2에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 3 = 빗각 2 - D (수직 거리)
   - **빗각 4**: 빗각 3에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 4 = 빗각 3 - D
   - **빗각 5**: 빗각 4에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 5 = 빗각 4 - D
   - **빗각 6**: 빗각 5에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 6 = 빗각 5 - D
   - **빗각 7**: 빗각 6에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 7 = 빗각 6 - D
   - **빗각 8**: 빗각 7에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 8 = 빗각 7 - D
   - ⚠️ 비트코인 가격은 이 빗각들을 기준으로 움직이며, 한 빗각을 뚫으면 다음 빗각까지 이동하는 경향
   
   **Step 1-A-6: 현재 시점의 각 상승 빗각 위치 계산**
   
   ⚠️ **중요: 반드시 Point A를 기준점으로 사용하세요!**
   
   - **경과 시간 계산** = 현재 캔들 index - **Point A index** (Point B 아님!)
   - **빗각 1 현재 위치** = **Point A low** + (slope × 경과 시간)
     * Point A를 시작점으로 하여 직선이 연장된 현재 위치
     * Point B 가격을 사용하지 마세요!
   
   - **빗각 2 현재 위치** = 빗각 1 현재 위치 - D
   - **빗각 3 현재 위치** = 빗각 2 현재 위치 - D (= 빗각 1 - 2D)
   - **빗각 4 현재 위치** = 빗각 3 현재 위치 - D (= 빗각 1 - 3D)
   - **빗각 5 현재 위치** = 빗각 4 현재 위치 - D (= 빗각 1 - 4D)
   - **빗각 6 현재 위치** = 빗각 5 현재 위치 - D (= 빗각 1 - 5D)
   - **빗각 7 현재 위치** = 빗각 6 현재 위치 - D (= 빗각 1 - 6D)
   - **빗각 8 현재 위치** = 빗각 7 현재 위치 - D (= 빗각 1 - 7D)
   
   **계산 예시:**
   - Point A index=383, Point A low=101668.1
   - slope=32.15 USDT/시간
   - 현재 캔들 index=949
   - 경과 시간 = 949 - 383 = 566시간
   - 빗각 1 위치 = 101668.1 + (32.15 × 566) = 101668.1 + 18196.9 = 119865.0 USDT ✅
   
   - 보고: 각 빗각의 현재 위치 가격 (반드시 위 공식대로 계산)
   
   **Step 1-A-7: 현재 가격이 어느 채널에 위치하는지 파악**
   - 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5와 6 사이? 6과 7 사이? 7과 8 사이? 8 아래?
   - 가장 가까운 위/아래 빗각 선 식별
   - 보고: 현재 가격의 채널 내 위치 ("빗각 2와 3 사이, 빗각 3에 가까움" 등)
   
   **Step 1-A-8: 🚨 빗각까지의 거리 계산 (매우 중요!)**
   - 가장 가까운 빗각까지의 거리 계산: |현재 가격 - 가장 가까운 빗각 위치| / 현재 가격 × 100
   - **ATR 기반 임계값 확인**: ATR% < 3% → 1.0%, ATR% 3-5% → 1.5%, ATR% > 5% → 2.0%
   - **거리가 임계값 이내인 경우**: 빗각 분석을 우선 적용
   - **거리가 임계값 초과인 경우**: 빗각이 너무 멀어서 당장 영향 없음 → 추세 분석으로 전환
   - 보고: "가장 가까운 빗각까지 거리 X.XX%, ATR% Y.YY%, 임계값 Z.Z%, 빗각 분석 적용 여부: O/X"
   
   **1-B. 하락 빗각 채널 그리기 (diagonal_type = 'downtrend'인 경우):**
   
   **Step 1-B-1: 제공된 캔들 정보 확인 및 사용**
   - Point A: 제공된 index, 시간, **high 값**, volume 확인
   - 두 번째 고점: 제공된 index, 시간, **high 값**, volume 확인
   - Point B (변곡점): 제공된 index, 시간, **high 값**, volume 확인
   - 보고: 각 포인트의 정보를 그대로 사용한다고 명시
   
   **Step 1-B-2: 빗각 1 (주 빗각) 그리기**
   - Point A의 high와 Point B의 high를 연결 → **빗각 1 (주 하락 빗각)**
   - 기울기 계산: slope = (Point B high - Point A high) / (Point B index - Point A index)
   - 보고: 빗각 1의 기울기 값 (USDT/시간)
   
   **Step 1-B-3: 빗각 2 (첫 번째 평행 빗각) 그리기**
   - 두 번째 고점의 high에서 시작하는 빗각 1과 **평행한 직선** → **빗각 2**
   - 빗각 2의 기울기는 빗각 1과 동일
   
   **Step 1-B-4: 채널 간격(D) 계산**
   - 두 번째 고점 시점에서 빗각 1과 빗각 2의 **수직 거리(가격 차이)** 계산
   - 빗각 1의 두 번째 고점 시점 가격 = Point A high + slope × (두 번째 고점 index - Point A index)
   - 채널 간격 D = |빗각 1의 해당 시점 가격 - 두 번째 고점 high|
   - 보고: 채널 간격 D (USDT)
   
   **Step 1-B-5: 추가 하락 채널 빗각 그리기 (빗각 3, 4, 5, 6, 7, 8)**
   - **빗각 3**: 빗각 2에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 3 = 빗각 2 + D (수직 거리)
   - **빗각 4**: 빗각 3에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 4 = 빗각 3 + D
   - **빗각 5**: 빗각 4에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 5 = 빗각 4 + D
   - **빗각 6**: 빗각 5에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 6 = 빗각 5 + D
   - **빗각 7**: 빗각 6에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 7 = 빗각 6 + D
   - **빗각 8**: 빗각 7에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 8 = 빗각 7 + D
   - ⚠️ 비트코인 가격은 이 빗각들을 기준으로 움직이며, 한 빗각을 뚫으면 다음 빗각까지 이동하는 경향
   
   **Step 1-B-6: 현재 시점의 각 하락 빗각 위치 계산**
   
   ⚠️ **중요: 반드시 Point A를 기준점으로 사용하세요!**
   
   - **경과 시간 계산** = 현재 캔들 index - **Point A index** (Point B 아님!)
   - **빗각 1 현재 위치** = **Point A high** + (slope × 경과 시간)
     * Point A를 시작점으로 하여 직선이 연장된 현재 위치
     * Point B 가격을 사용하지 마세요!
   
   - **빗각 2 현재 위치** = 빗각 1 현재 위치 + D
   - **빗각 3 현재 위치** = 빗각 2 현재 위치 + D (= 빗각 1 + 2D)
   - **빗각 4 현재 위치** = 빗각 3 현재 위치 + D (= 빗각 1 + 3D)
   - **빗각 5 현재 위치** = 빗각 4 현재 위치 + D (= 빗각 1 + 4D)
   - **빗각 6 현재 위치** = 빗각 5 현재 위치 + D (= 빗각 1 + 5D)
   - **빗각 7 현재 위치** = 빗각 6 현재 위치 + D (= 빗각 1 + 6D)
   - **빗각 8 현재 위치** = 빗각 7 현재 위치 + D (= 빗각 1 + 7D)
   
   **계산 예시:**
   - Point A index=450, Point A high=112000.0
   - slope=-25.5 USDT/시간 (하락)
   - 현재 캔들 index=900
   - 경과 시간 = 900 - 450 = 450시간
   - 빗각 1 위치 = 112000.0 + (-25.5 × 450) = 112000.0 - 11475.0 = 100525.0 USDT ✅
   
   - 보고: 각 빗각의 현재 위치 가격 (반드시 위 공식대로 계산)
   
   **Step 1-B-7: 현재 가격이 어느 채널에 위치하는지 파악**
   - 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5와 6 사이? 6과 7 사이? 7과 8 사이? 8 위?
   - 가장 가까운 위/아래 빗각 선 식별
   - 보고: 현재 가격의 채널 내 위치 ("빗각 2와 3 사이, 빗각 2에 가까움" 등)
   
   **Step 1-B-8: 🚨 빗각까지의 거리 계산 (매우 중요!)**
   - 가장 가까운 빗각까지의 거리 계산: |현재 가격 - 가장 가까운 빗각 위치| / 현재 가격 × 100
   - **거리가 1% 이내인 경우**: 빗각 분석을 우선 적용
   - **거리가 1% 초과인 경우**: 빗각이 너무 멀어서 당장 영향 없음 → 추세 분석으로 전환
   - 보고: "가장 가까운 빗각까지 거리 X.XX%, 빗각 분석 적용 여부: O/X"
   
**1-C. 두 빗각 종합 분석 및 진입 신호 판단:**

**⚠️ 분석 원칙:**
- 제공된 모든 빗각 분석 (상승 빗각, 하락 빗각)
- **각 빗각까지의 거리가 임계값 이내인지 먼저 확인** (필수!)
- 각 빗각의 12가지 시나리오 평가
- 가장 강한 신호 선택

**분석 절차:**

0. **🚨 빗각 교차 구간 체크 (필터링):**
   
   **⚠️ 이 조건에 해당하면 무조건 HOLD - 절대 진입 금지!**
   
   - **상승 빗각과 하락 빗각이 모두 제공된 경우** 다음을 확인:
   
   **빗각 교차 구간 체크:**
   - 현재 가격에서 가장 가까운 상승 빗각까지의 거리 ≤ 0.5%
   - **그리고** 현재 가격에서 가장 가까운 하락 빗각까지의 거리 ≤ 0.5%
   - **→ 두 조건이 모두 충족되면 교차 구간으로 판단 → HOLD**
   
   **조건 미충족 시**: 정상 분석 진행 (Step 1-C-1로 이동)

1. **상승 빗각 시나리오 평가** (제공된 경우):
   - **🚨 필수**: 가장 가까운 빗각까지 거리가 임계값 이내인지 확인 (ATR 기반 동적)
   - **거리 임계값 이내**: 6가지 시나리오 중 충족되는 것 확인
   - **거리 임계값 초과**: 빗각 분석 건너뛰고 Step 1-G로 이동
   - 보조 조건 충족 개수 계산
   
2. **하락 빗각 시나리오 평가** (제공된 경우):
   - **🚨 필수**: 가장 가까운 빗각까지 거리가 임계값 이내인지 확인 (ATR 기반 동적)
   - **거리 임계값 이내**: 6가지 시나리오 중 충족되는 것 확인
   - **거리 임계값 초과**: 빗각 분석 건너뛰고 Step 1-G로 이동
   - 보조 조건 충족 개수 계산
   
3. **신호 종합 판단**:
   - **상승/하락 빗각 모두 거리 임계값 초과**: Step 1-G (추세 추종)로 즉시 이동
   - **한쪽 빗각만 거리 임계값 이내**: 해당 빗각만 분석
   - **같은 방향 신호**: 더 강한 빗각 선택 (보조 조건 많은 쪽)
   - **다른 방향 신호**: 신호 강도 비교 후 강한 쪽 선택
   - **한쪽만 신호**: 해당 빗각 사용
   - **둘 다 무신호**: Step 1-G (추세 추종)로 이동
   
4. **15분봉 진입 타이밍 확인**:
   - 선택된 빗각을 기준으로 15분봉 분석
   - 정확한 진입 시점 포착
   
**1-D. 빗각 채널 기반 진입 신호 (최우선 판단 기준):**
   
   **🎯 상승 빗각 채널 신호:**
   1. **빗각 돌파 후 지지 확인 (롱 진입)**
      - 가격이 상승 빗각(예: 빗각 2)을 위로 돌파
      - 15분봉에서 리테스트 시 빗각에서 지지 확인
      - SL: 빗각 아래 (예: 빗각 2 -0.5%)
      - TP: 다음 상위 빗각 (예: 빗각 1 근처)
      
   2. **빗각 리테스트 실패 (숏 진입)**
      - 가격이 상승 빗각을 위로 돌파했으나
      - 15분봉 리테스트에서 빗각을 다시 하향 돌파
      - SL: 빗각 위 (예: 빗각 2 +0.5%)
      - TP: 다음 하위 빗각 (예: 빗각 3 근처)
      
   3. **빗각 저항 (숏 진입)**
      - 가격이 상승 빗각(예: 빗각 2)에 근접했으나 뚫지 못함
      - 15분봉에서 반락 신호 (음봉, 거래량 증가)
      - SL: 빗각 위 (예: 빗각 2 +0.5%)
      - TP: 다음 하위 빗각 (예: 빗각 3 근처)
      
   **🎯 하락 빗각 채널 신호:**
   4. **빗각 하향 돌파 후 저항 확인 (숏 진입)**
      - 가격이 하락 빗각(예: 빗각 2)을 아래로 돌파
      - 15분봉에서 리테스트 시 빗각에서 저항 확인
      - SL: 빗각 위 (예: 빗각 2 +0.5%)
      - TP: 다음 하위 빗각 (예: 빗각 3 근처)
      
   5. **빗각 하향 돌파 후 리테스트 실패 (롱 진입)**
      - 가격이 하락 빗각을 아래로 돌파했으나
      - 15분봉 리테스트에서 빗각을 다시 상향 돌파 (페이크 브레이크다운)
      - SL: 빗각 아래 (예: 빗각 2 -0.5%)
      - TP: 다음 상위 빗각 (예: 빗각 1 근처)
      
   6. **빗각 지지 (롱 진입)**
      - 가격이 하락 빗각(예: 빗각 2)에 근접했으나 뚫지 못함
      - 15분봉에서 반등 신호 (양봉, 거래량 증가)
      - SL: 빗각 아래 (예: 빗각 2 -0.5%)
      - TP: 다음 상위 빗각 (예: 빗각 1 근처)
   
   **🎯 채널 간 이동 원리:**
   - 한 빗각을 명확히 돌파하면 다음 빗각까지 움직이는 경향
   - 예: 빗각 2 돌파 → 빗각 1로 이동 또는 빗각 3으로 이동
   - 빗각 시나리오가 없으면 추세 추종으로 진입 (위치 무관)

**1-G. 빗각 시나리오 미충족 시 추세 추종 진입 (추가 시나리오)**

⚠️ **우선순위**: 
- **빗각 거리 임계값 이내** (ATR 기반 동적): 12가지 빗각 시나리오가 **최우선** (상승 빗각 6개 + 하락 빗각 6개)
- **빗각 거리 임계값 초과 또는 빗각 없음**: 아래 추세 추종 로직을 적용합니다

**진입 조건 (빗각 시나리오 없을 때만):**
- 빗각 시나리오(1~12번) 중 어느 것도 충족하지 않음
- 롱/숏 각 방향별 5가지 조건을 평가
- 각 방향별 최소 2개 이상 충족 시 진입 고려
- **더 많은 조건을 충족하는 방향으로 진입**

**🔺 롱 포지션 진입 조건 (5가지 중 최소 2개 이상 동시 충족 시 고려):**
1. **추세 확인**: 15분 차트에서 21EMA > 55EMA 배열이고 가격이 21EMA 위에 위치
2. **모멘텀 확인**: 15분 RSI가 50 이상이고 상승 추세 (최근 3봉 기준)
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.2배 이상
4. **지지선 확인**: 주요 지지선(볼륨 프로파일 POC/VAL) 근처에서 반등 신호
5. **MACD 확인**: 15분 MACD가 시그널선 위에 있고 히스토그램이 증가 중

**🔻 숏 포지션 진입 조건 (5가지 중 최소 2개 이상 동시 충족 시 고려):**
1. **추세 확인**: 15분 차트에서 21EMA < 55EMA 배열이고 가격이 21EMA 아래에 위치
2. **모멘텀 확인**: 15분 RSI가 50 이하이고 하락 추세 (최근 3봉 기준)
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.2배 이상
4. **저항선 확인**: 주요 저항선(볼륨 프로파일 POC/VAH) 근처에서 반락 신호
5. **MACD 확인**: 15분 MACD가 시그널선 아래에 있고 히스토그램이 감소 중

**진입 방향 결정 로직:**
- 롱 조건 3개 충족, 숏 조건 2개 충족 → **롱 진입**
- 롱 조건 2개 충족, 숏 조건 4개 충족 → **숏 진입**
- 롱 조건 2개 충족, 숏 조건 2개 충족 → **HOLD** (명확한 방향성 없음)
- 양 방향 모두 2개 미만 충족 → **HOLD**

**SL 및 TP 설정 (추세 추종 전용):**

**🎯 기본 철학:**
- **SL**: 추세가 무효화되는 지점 = 주요 지지/저항선 붕괴 지점
- **TP**: 보수적으로 다음 주요 레벨까지만 = 최소 목표가
- **리스크 리워드 비율**: 최소 1:2 유지

**SL 설정 원칙:**
- **롱 진입**: 주요 지지선(21EMA, 55EMA, 볼륨 프로파일 VAL) 바로 아래 (-0.3~0.5%)
- **숏 진입**: 주요 저항선(21EMA, 55EMA, 볼륨 프로파일 VAH) 바로 위 (+0.3~0.5%)

**TP 설정 원칙:**
- **롱 진입**: 다음 주요 저항선(볼륨 프로파일 POC/VAH, 전고점) 직전 (-0.3~0.5%)
- **숏 진입**: 다음 주요 지지선(볼륨 프로파일 POC/VAL, 전저점) 직전 (+0.3~0.5%)

**간단한 SL/TP 설정 예시:**

**롱 진입 시:**
- SL: 21EMA 또는 55EMA 바로 아래 (예: 현재가 대비 -0.5%)
- TP: 다음 주요 저항선 직전 (예: 현재가 대비 +1.5%)
- 리스크 리워드 = 1.5 / 0.5 = 1:3 ✅

**숏 진입 시:**
- SL: 21EMA 또는 55EMA 바로 위 (예: 현재가 대비 +0.5%)
- TP: 다음 주요 지지선 직전 (예: 현재가 대비 -1.5%)
- 리스크 리워드 = 1.5 / 0.5 = 1:3 ✅

⚠️ **필수 조건:**
- 리스크 리워드 비율 1:2 미만이면 진입 포기
- 추세가 명확하지 않으면 HOLD
- 이 시나리오는 빗각 거리 1% 초과일 때만 사용

**Step 2: 추세 분석 (15분/1시간 차트 중심)**
1. **15분 차트 추세** (60% 가중치):
   - 21EMA와 55EMA 배열 확인
   - 가격이 21EMA 위(롱)/아래(숏) 위치 확인
   
2. **1시간 차트 추세** (25% 가중치):
   - 15분 추세와 일치하는지 확인
   - 일치하면 신뢰도 상승, 불일치하면 신중
   
3. **ADX로 추세 강도 확인**:
   - 15분 ADX > 20 이상이면 추세 존재 판단

**Step 3: 진입 조건 체크**

**🚨 진입 우선순위 결정:**

**1단계: 빗각 거리 확인 (필수)**
- 현재 가격과 가장 가까운 빗각까지의 거리가 **임계값 이내**인가?
- **임계값** (ATR 기반 동적): ATR% < 3% → 1.0%, ATR% 3-5% → 1.5%, ATR% > 5% → 2.0%
- **임계값 이내** → 빗각 시나리오 우선 분석
- **임계값 초과** → 추세 추종 분석으로 전환

**2단계: 빗각 시나리오 (빗각 거리 임계값 이내일 때만)**

**12가지 시나리오 구성:**
- 상승 빗각: 롱 3개 + 숏 3개 = 6가지
- 하락 빗각: 롱 3개 + 숏 3개 = 6가지
- 총 12가지 시나리오 (롱 6개 + 숏 6개, 완벽한 균형)

현재 가격이 어느 채널 빗각 근처에 있는지 확인 후 해당 빗각을 기준으로 진입 판단:

**1. 상승 빗각 돌파 후 지지 (롱 진입)**
   - 조건: 가격이 특정 상승 빗각(예: 빗각 2)을 위로 돌파 → 15분봉 리테스트에서 지지 확인
   - SL: 해당 빗각 아래 (예: 빗각 2 -0.5%)
   - TP: 다음 상위 빗각 근처 (예: 빗각 1)
   - 채널 이동: 빗각 2 → 빗각 1 방향

**2. 상승 빗각 리테스트 실패 (숏 진입)**
   - 조건: 가격이 상승 빗각을 위로 돌파했으나 → 15분봉 리테스트에서 다시 하향 돌파
   - SL: 해당 빗각 위 (예: 빗각 2 +0.5%)
   - TP: 다음 하위 빗각 근처 (예: 빗각 3)
   - 채널 이동: 빗각 2 → 빗각 3 방향

**3. 상승 빗각 저항 (숏 진입)**
   - 조건: 가격이 상승 빗각에 근접했으나 뚫지 못하고 → 15분봉 반락 신호
   - SL: 해당 빗각 위 (예: 빗각 2 +0.5%)
   - TP: 다음 하위 빗각 근처 (예: 빗각 3)
   - 채널 이동: 빗각 2에서 반락 → 빗각 3 방향

**4. 하락 빗각 하향 돌파 (숏 진입)**
   - 조건: 가격이 하락 빗각(예: 빗각 2)을 아래로 돌파 → 지속 하락
   - SL: 해당 빗각 위 (예: 빗각 2 +0.5%)
   - TP: 다음 하위 빗각 근처 (예: 빗각 3)
   - 채널 이동: 빗각 2 → 빗각 3 방향

**5. 하락 빗각 지지 (롱 진입)**
   - 조건: 가격이 하락 빗각에 닿았으나 뚫지 못하고 → 15분봉 반등 신호
   - SL: 해당 빗각 아래 (예: 빗각 2 -0.5%)
   - TP: 다음 상위 빗각 근처 (예: 빗각 1)
   - 채널 이동: 빗각 2에서 반등 → 빗각 1 방향

**⚠️ 진입 판단 주의사항:**
- **빗각 거리 임계값 이내** + 빗각 시나리오(1~12번) 중 하나라도 충족 → 빗각 시나리오로 진입
- **빗각 거리 임계값 초과** 또는 빗각 시나리오 없음 → 추세 추종(Step 1-G)으로 진입 고려
- 빗각 시나리오와 추세 추종 모두 조건 미충족 시 → HOLD

**보조 확인 조건 (빗각 채널 시나리오와 함께 확인하여 진입 신뢰도 향상):**

**롱 방향 보조 조건:**
✓ 15분 차트에서 21EMA > 55EMA, 가격이 21EMA 위
✓ 15분 RSI ≥ 50, 최근 3봉 기준 상승 추세
✓ 현재 볼륨 ≥ 최근 20봉 평균 × 1.2배
✓ 주요 지지선 근처에서 반등 신호
✓ 15분 MACD > 시그널선, 히스토그램 증가 중

**숏 방향 보조 조건:**
✓ 15분 차트에서 21EMA < 55EMA, 가격이 21EMA 아래
✓ 15분 RSI ≤ 50, 최근 3봉 기준 하락 추세
✓ 현재 볼륨 ≥ 최근 20봉 평균 × 1.2배
✓ 주요 저항선 근처에서 반락 신호
✓ 15분 MACD < 시그널선, 히스토그램 감소 중

→ **진입 판단 기준 (우선순위별):**

**🥇 최우선: 빗각 시나리오 (빗각 거리 임계값 이내일 때)**
→ **필수**: 가장 가까운 빗각까지 거리 임계값 이내 확인 (ATR 기반 동적)
→ 빗각 채널 시나리오 1개 충족 + 보조 조건 1개 이상 충족 → **즉시 진입**
→ 빗각 채널 시나리오가 여러 개 동시 신호 → 더 강한 신호 (유효성, 보조조건 충족도 높은) 선택
→ 빗각 유효성 검증(시간 간격, 최신성, 터치 횟수) 통과 시 신뢰도 증가
→ ADX ≥ 20이면 신뢰도 증가, 다중 시간대 일관성 ≥ 60점이면 더욱 유리

**🥈 차선: 추세 추종 진입 (빗각 거리 임계값 초과 또는 빗각 없을 때)**
→ **조건**: 빗각 거리 임계값 초과 또는 빗각 시나리오(1~12번) 없음
→ 롱 조건 5개 중 2개 이상 충족 또는 숏 조건 5개 중 2개 이상 충족 확인
→ **더 많은 조건을 충족하는 방향으로 진입**
→ 예: 롱 조건 3개, 숏 조건 2개 → 롱 진입
→ SL/TP는 리스크 리워드 비율(1:2 또는 1:3) 유지 (Step 1-G 참고)
→ 빗각까지 거리를 고려하여 SL/TP 설정 (예: TP 빗각 1.66%면 TP=1.5%, SL=0.5%)
→ 리스크 리워드 비율이 1:2 미만이면 진입하지 않음

**🥉 홀드: 조건 미충족**
→ 빗각 거리 임계값 초과 + 양 방향 모두 조건 2개 미만 → **HOLD**
→ 빗각 거리 임계값 초과 + 리스크 리워드 비율 1:2 미만 → **HOLD**

**Step 4: 손익 목표 설정**

**🎯 SL/TP 설정 철학:**
- **SL (Stop Loss)**: 분석이 틀렸다는 것이 명확해지는 지점 = 분석 무효화 지점
- **TP (Take Profit)**: 보수적으로 최소한 이 정도는 갈 것이라 확신하는 지점 = 최소 목표가

**1. Stop Loss (SL) 설정 - "분석이 틀렸음을 확인하는 즉시 손절"**

**빗각 분석 시:**
   - **롱 진입 (상승/하락 빗각 지지)**: SL = 해당 빗각 바로 아래 (-0.3~0.5%)
     * 이유: 빗각을 아래로 뚫으면 = 지지선 무너짐 = 분석 틀림
   - **숏 진입 (상승/하락 빗각 저항)**: SL = 해당 빗각 바로 위 (+0.3~0.5%)
     * 이유: 빗각을 위로 뚫으면 = 저항선 돌파 = 분석 틀림
   
**추세 분석 시:**
   - **롱 진입**: SL = 주요 지지선(21EMA, 55EMA, 볼륨 프로파일 VAL) 바로 아래 (-0.3~0.5%)
     * 이유: 주요 지지선 붕괴 = 상승 추세 무효화 = 분석 틀림
   - **숏 진입**: SL = 주요 저항선(21EMA, 55EMA, 볼륨 프로파일 VAH) 바로 위 (+0.3~0.5%)
     * 이유: 주요 저항선 돌파 = 하락 추세 무효화 = 분석 틀림

**⚠️ SL 원칙:**
- 분석의 핵심 가정이 무너지는 지점에 정확히 설정
- "혹시 돌아올지도" 같은 희망 배제
- 빠르게 손실 인정하고 다음 기회 대기

**2. Take Profit (TP) 설정 - "보수적으로 최소한 갈 것이라 확신하는 지점"**

**빗각 분석 시:**
   - **롱 진입**: TP = 다음 상위 빗각 직전 (-0.3~0.5%)
     * 이유: 다음 빗각까지는 높은 확률로 도달, 그 이상은 욕심
     * 예: 빗각 2에서 진입 → 빗각 1 직전을 TP로 설정
   - **숏 진입**: TP = 다음 하위 빗각 직전 (+0.3~0.5%)
     * 이유: 다음 빗각까지는 높은 확률로 도달, 그 이상은 욕심
     * 예: 빗각 2에서 진입 → 빗각 3 직전을 TP로 설정
   
**추세 분석 시:**
   - **롱 진입**: TP = 다음 주요 저항선(볼륨 프로파일 POC/VAH, 전고점) 직전 (-0.3~0.5%)
     * 이유: 다음 저항까지는 최소한 도달 가능
   - **숏 진입**: TP = 다음 주요 지지선(볼륨 프로파일 POC/VAL, 전저점) 직전 (+0.3~0.5%)
     * 이유: 다음 지지까지는 최소한 도달 가능

**⚠️ TP 원칙:**
- "여기까지만 가도 성공"이라는 보수적 목표
- 채널 전체를 욕심내지 않고 1개 채널 이동만 목표
- 리스크 리워드 비율 최소 1:2 유지 (SL 0.5%면 TP 1.0% 이상)
- 승률을 높이는 것이 장기적으로 더 유리함

**3. 레버리지 결정:**
   - 분석 신뢰도가 높을수록 높은 레버리지 설정

**4. 예상 도달 시간 (expected_minutes):**
   - 채널 간격과 최근 가격 변동 속도를 고려하여 계산
   - 다음 빗각까지의 거리와 시간당 평균 변동폭 기반
   - 권장 범위: 480-960분 (8-16시간)

**Step 5: 최종 확인**

**🎯 진입 우선순위 (반드시 준수):**

**🚨 1단계: 빗각 거리 확인 (최우선)**
- 현재 가격과 가장 가까운 빗각까지의 거리가 **임계값 이내**인가?
- **임계값** (ATR 기반 동적): ATR% < 3% → 1.0%, ATR% 3-5% → 1.5%, ATR% > 5% → 2.0%
- **거리 임계값 이내** → 빗각 시나리오 분석 진행
- **거리 임계값 초과** → 추세 추종 분석으로 전환

**🥇 2단계: 빗각 시나리오 (거리 임계값 이내일 때)**
- 빗각 시나리오(1~12번) 충족 + 보조 조건 1개 이상 → 즉시 진입 (상승 빗각 6개 + 하락 빗각 6개)

**🥈 3단계: 추세 추종 (거리 임계값 초과 또는 빗각 없을 때)**
- 빗각 거리 임계값 초과 또는 빗각 시나리오 없음 + 명확한 추세 + 보조 조건 2개 이상 → 진입 고려

**🥉 4단계: 홀드**
- 빗각 거리 임계값 초과 + (추세 불명확 또는 보조 조건 부족) → HOLD

**🔍 재확인 체크리스트:**
- **빗각 거리 임계값 이내 여부 재확인** (최우선! ATR 기반 동적)
- 빗각 유효성 재확인 (시간 간격 10개 이상, Point A가 100개 이내)
- 포지션 크기: 신뢰도에 따라 0.3-0.9 (빗각 시나리오+보조조건 많이 충족 시 증가)
- 레버리지: 분석 신뢰도에 따라 10-30배 (30배 초과 시 청산 위험 높음)

**📌 추세 추종 특별 확인 (Step 1-G 참고):**
- **빗각 거리 임계값 초과 확인** → 추세 추종 사용
- 빗각 시나리오(1~12번) 충족 여부 재확인 → 충족되고 거리 임계값 이내면 추세 추종 사용 안 함
- 롱 조건 5개 중 몇 개 충족? 숏 조건 5개 중 몇 개 충족? → 각각 2개 미만이면 HOLD
- **더 많은 조건을 충족하는 방향으로 진입** (예: 롱 3개, 숏 2개 → 롱 진입)
- 양 방향 조건이 동일하면 (예: 롱 2개, 숏 2개) → HOLD (명확한 방향성 없음)
- 리스크 리워드 비율 1:2 이상 유지 가능한가? → 미만이면 진입 포기
- 빗각까지 거리 고려한 SL/TP 설정 (예: TP 빗각 1.66%면 TP=1.5%, SL=0.5%)

### 응답 형식: (**매우중요! 반드시 꼭 아래 형식에 맞게 아래 **Trading_Decision**과 **Analysis_Details** 섹션을 포함하여 답변할 것. 다른 형식은 절대 사용 금지)
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.3-0.9] (HOLD 시 생략)
LEVERAGE: [10-30 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [0.30-1.00 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
TAKE_PROFIT_ROE: [0.90-3.00 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
EXPECTED_MINUTES: [120-960] (HOLD 시 생략)

## ANALYSIS_DETAILS
**⚠️ 중요: HOLD, ENTER_LONG, ENTER_SHORT 어떤 결정이든 반드시 Step 1부터 Step 6까지 모든 분석을 완전히 수행하세요!**

**Step 1: 빗각 및 채널 분석 (1시간봉 기준 - 상승/하락 빗각 모두 양방향 활용)**

**⚠️ 중요: 백엔드에서 이미 추출된 캔들 정보를 사용하세요! 직접 캔들을 검색하지 마세요!**

- 상승 빗각 및 채널 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **low 값**, volume
  * **제공된 두 번째 저점 정보 확인**: index, 시간, **low 값**, volume  
  * **제공된 Point B 정보 확인**: index, 시간, **low 값**, volume
  
  * **빗각 1 (기준 상승 빗각) 계산**: Point A의 low와 Point B의 low를 연결한 직선
    → 시간당 변화율 (slope) = (Point B low - Point A low) / (Point B index - Point A index)
    → 경과 시간 = 현재 캔들 index - Point A index
    → **현재 빗각 1 위치 = Point A low + (변화율 × 경과 시간)** ⚠️ Point A 가격 사용!
  
  * **채널 간격 D 계산**: 
    → 두 번째 저점 시점에서 빗각 1과의 수직 거리
    → D = |빗각 1의 두 번째 저점 시점 가격 - 두 번째 저점 low|
  
  * **평행 채널 빗각들 현재 위치 계산**:
    → 빗각 2 현재 위치 = 빗각 1 현재 위치 - D
    → 빗각 3 현재 위치 = 빗각 1 현재 위치 - 2D
    → 빗각 4 현재 위치 = 빗각 1 현재 위치 - 3D
    → 빗각 5 현재 위치 = 빗각 1 현재 위치 - 4D
    → 빗각 6 현재 위치 = 빗각 1 현재 위치 - 5D
    → 빗각 7 현재 위치 = 빗각 1 현재 위치 - 6D
    → 빗각 8 현재 위치 = 빗각 1 현재 위치 - 7D
  
  * **현재 가격이 어느 채널에 위치하는지 파악**:
    → 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5와 6 사이? 6과 7 사이? 7과 8 사이? 8 아래?
    → 가장 가까운 위/아래 빗각 선 식별
  
  * **가장 가까운 빗각까지 거리 계산 및 지지/저항 분석** (매우 중요!):
    → 거리 = |현재 가격 - 가장 가까운 빗각 위치| / 현재 가격 × 100
    → **각 빗각(1, 2, 3, 4, 5, 6, 7, 8) 모두 지지선/저항선으로 작용**
    → 현재 가격 > 해당 빗각 → 빗각이 지지선 역할 → 지지 확인 시 롱, 지지 붕괴 시 숏
    → 현재 가격 < 해당 빗각 → 빗각이 저항선 역할 → 저항 확인 시 숏, 저항 돌파 시 롱
    → **거리 임계값 이내일 때만 진입 신호로 판단** (ATR% < 3% → 1.0%, ATR% 3-5% → 1.5%, ATR% > 5% → 2.0%)
  
- 하락 빗각 및 채널 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 두 번째 고점 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 Point B 정보 확인**: index, 시간, **high 값**, volume
  
  * **빗각 1 (기준 하락 빗각) 계산**: Point A의 high와 Point B의 high를 연결한 직선
    → 시간당 변화율 (slope) = (Point B high - Point A high) / (Point B index - Point A index)
    → 경과 시간 = 현재 캔들 index - Point A index
    → **현재 빗각 1 위치 = Point A high + (변화율 × 경과 시간)** ⚠️ Point A 가격 사용!
  
  * **채널 간격 D 계산**: 
    → 두 번째 고점 시점에서 빗각 1과의 수직 거리
    → D = |빗각 1의 두 번째 고점 시점 가격 - 두 번째 고점 high|
  
  * **평행 채널 빗각들 현재 위치 계산**:
    → 빗각 2 현재 위치 = 빗각 1 현재 위치 + D
    → 빗각 3 현재 위치 = 빗각 1 현재 위치 + 2D
    → 빗각 4 현재 위치 = 빗각 1 현재 위치 + 3D
    → 빗각 5 현재 위치 = 빗각 1 현재 위치 + 4D
    → 빗각 6 현재 위치 = 빗각 1 현재 위치 + 5D
    → 빗각 7 현재 위치 = 빗각 1 현재 위치 + 6D
    → 빗각 8 현재 위치 = 빗각 1 현재 위치 + 7D
  
  * **현재 가격이 어느 채널에 위치하는지 파악**:
    → 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5와 6 사이? 6과 7 사이? 7과 8 사이? 8 위?
    → 가장 가까운 위/아래 빗각 선 식별
  
  * **가장 가까운 빗각까지 거리 계산 및 지지/저항 분석** (매우 중요!):
    → 거리 = |현재 가격 - 가장 가까운 빗각 위치| / 현재 가격 × 100
    → **각 빗각(1, 2, 3, 4, 5, 6, 7, 8) 모두 지지선/저항선으로 작용**
    → 현재 가격 > 해당 빗각 → 빗각이 지지선 역할 → 지지 확인 시 롱, 지지 붕괴 시 숏
    → 현재 가격 < 해당 빗각 → 빗각이 저항선 역할 → 저항 확인 시 숏, 저항 돌파 시 롱
    → **거리 임계값 이내일 때만 진입 신호로 판단** (ATR% < 3% → 1.0%, ATR% 3-5% → 1.5%, ATR% > 5% → 2.0%)
  
- 15분봉 진입 타이밍: 1시간봉 빗각/채널을 15분봉에 적용하여 정확한 진입 시점 분석
- **🚨 채널 거리 확인**: 가장 가까운 빗각(1, 2, 3, 4, 5, 6, 7, 8 중)까지 거리가 임계값 이내인지 반드시 확인 (ATR 기반 동적)
- 빗각 시나리오 확인: **거리 임계값 이내일 때만** 12가지 빗각 시나리오 중 어떤 것이 충족되는지 명확히 판단 (상승 빗각 6개 + 하락 빗각 6개)
- **채널 활용**: 가격이 한 빗각을 뚫으면 다음 평행 빗각까지 이동하는 경향 활용하여 TP 설정

**Step 2: 추세 분석 (15분/1시간 차트)**
[주요 이동평균선 배열, 추세 방향성, ADX 수치 분석]

**Step 3: 모멘텀 분석**
[RSI, MACD 현재 상태 및 방향성 분석]

**Step 4: 볼륨 및 지지/저항 분석**
[거래량 상태, 주요 가격대 반응, 볼륨 프로파일 분석]

**Step 5: 진입 조건 체크**
[Step 0 횡보 체크 통과 후 → 최우선: 12가지 빗각 시나리오 중 충족되는 것 확인 (상승 빗각 6개 + 하락 빗각 6개) → 차선: 빗각 시나리오 없을 시 추세추종 (롱 조건 5개 중 몇 개, 숏 조건 5개 중 몇 개 충족?) → 더 많은 조건 충족하는 방향으로 진입 결정 (최소 2개 이상) → 양 방향 조건 동일하거나 2개 미만이면 HOLD]

**Step 6: 리스크 평가**
[변동성, 시간대 충돌 등 안전 장치 확인]

**최종 결론:**
[Step 0 횡보 체크 결과 포함, 위 모든 분석을 종합한 최종 trading decision 근거, 충족된 빗각 시나리오 명시, 빗각 신호 우선순위 강조]

심호흡하고 차근차근 생각하며 확률값에 기반하여 분석을 진행해"""

        return prompt

    def _parse_ai_response(self, response_text):
        """AI 응답 파싱 (Claude와 동일한 파싱 로직 사용)"""
        try:
            print("\n=== 파싱 시작: 원본 응답 ===")
            print(response_text)
            
            # 정규표현식 패턴
            action_pattern = re.compile(r'\*{0,2}\s*ACTION\s*\*{0,2}\s*:\s*\*{0,2}\s*([A-Z_]+)', re.IGNORECASE)
            position_pattern = re.compile(r'\*{0,2}\s*POSITION_SIZE\s*\*{0,2}\s*:\s*\*{0,2}\s*([\d.]+)', re.IGNORECASE)
            leverage_pattern = re.compile(r'\*{0,2}\s*LEVERAGE\s*\*{0,2}\s*:\s*\*{0,2}\s*(\d+)', re.IGNORECASE)
            minutes_pattern = re.compile(r'\*{0,2}\s*EXPECTED_MINUTES\s*\*{0,2}\s*:\s*\*{0,2}\s*(\d+)', re.IGNORECASE)
            stop_loss_pattern = re.compile(r'\*{0,2}\s*STOP_LOSS_ROE\s*\*{0,2}\s*:\s*\*{0,2}\s*([+-]?[\d.]+)', re.IGNORECASE)
            take_profit_pattern = re.compile(r'\*{0,2}\s*TAKE_PROFIT_ROE\s*\*{0,2}\s*:\s*\*{0,2}\s*([+-]?[\d.]+)', re.IGNORECASE)

            # TRADING_DECISION 섹션 추출
            trading_decision = ""
            original_response = response_text
            
            trading_patterns = [
                r'##\s*[📊🎯💰]*\s*TRADING_DECISION(.*?)(?=##|$)',
                r'###\s*TRADING_DECISION(.*?)(?=###|$)',
                r'TRADING_DECISION(.*?)(?=##|###|$)'
            ]
            
            for pattern in trading_patterns:
                match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
                if match:
                    trading_decision = match.group(1).strip()
                    print(f"TRADING_DECISION 섹션 추출 성공")
                    break
            
            if trading_decision:
                response_text = trading_decision
            
            # 기본값 설정
            action = "HOLD"
            position_size = 0.5
            leverage = 5
            expected_minutes = 15
            stop_loss_roe = 1.5
            take_profit_roe = 4.0
            
            # 매칭 결과 저장
            if action_match := action_pattern.search(response_text):
                action = action_match.group(1).strip().upper()
                print(f"추출된 액션: {action}")
                if action not in ["ENTER_LONG", "ENTER_SHORT", "CLOSE_POSITION", "HOLD"]:
                    action = "HOLD"
            
            # HOLD가 아닌 경우 모든 파라미터 추출
            if action != "HOLD":
                # 포지션 크기 추출
                if position_match := position_pattern.search(response_text):
                    try:
                        size = float(position_match.group(1))
                        if 0.1 <= size <= 0.95:
                            position_size = size
                    except ValueError:
                        pass

                # 레버리지 추출
                if leverage_match := leverage_pattern.search(response_text):
                    try:
                        lev = int(leverage_match.group(1))
                        if 1 <= lev <= 100:
                            leverage = lev
                    except ValueError:
                        pass
                
                # Stop Loss ROE 추출
                if stop_loss_match := stop_loss_pattern.search(response_text):
                    try:
                        sl_roe_str = stop_loss_match.group(1).strip()
                        sl_roe = abs(float(sl_roe_str.replace('+', '').replace('-', '')))
                        sl_roe = round(sl_roe, 2)
                        if sl_roe > 0:
                            stop_loss_roe = sl_roe
                    except ValueError:
                        pass
                
                # Take Profit ROE 추출
                if take_profit_match := take_profit_pattern.search(response_text):
                    try:
                        tp_roe_str = take_profit_match.group(1).strip()
                        tp_roe = abs(float(tp_roe_str.replace('+', '').replace('-', '')))
                        tp_roe = round(tp_roe, 2)
                        if tp_roe > 0:
                            take_profit_roe = tp_roe
                    except ValueError:
                        pass

            # 예상 시간 추출
            if minutes_match := minutes_pattern.search(response_text):
                try:
                    minutes = int(minutes_match.group(1))
                    if minutes > 0:
                        expected_minutes = minutes
                except ValueError:
                    pass

            # ANALYSIS_DETAILS 섹션을 REASON으로 사용
            reason = ""
            
            analysis_patterns = [
                r'##\s*[🔍📊🎯💡]*\s*ANALYSIS_DETAILS\s*\n(.+)',
                r'###\s*ANALYSIS_DETAILS\s*\n(.+)',
                r'ANALYSIS_DETAILS\s*\n(.+)'
            ]
            
            for pattern in analysis_patterns:
                match = re.search(pattern, original_response, re.DOTALL | re.IGNORECASE)
                if match:
                    reason = match.group(1).strip()
                    if reason and len(reason) > 50:
                        break
            
            if not reason or len(reason.strip()) < 5:
                reason = "No analysis details provided"

            result = {
                "action": action,
                "position_size": position_size,
                "leverage": leverage,
                "stop_loss_roe": stop_loss_roe,
                "take_profit_roe": take_profit_roe,
                "expected_minutes": expected_minutes,
                "reason": reason,
                "next_analysis_time": (datetime.now() + timedelta(minutes=expected_minutes)).isoformat()
            }
            
            print("\n=== 파싱 결과 ===")
            print(json.dumps(result, indent=2, default=str))
            
            return result

        except Exception as e:
            print(f"AI 응답 파싱 중 에러: {str(e)}")
            return {
                "action": "HOLD",
                "reason": f"파싱 에러: {str(e)}"
            }

