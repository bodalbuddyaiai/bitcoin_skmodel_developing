import json
import time
import requests
import numpy as np
from datetime import datetime, date, timedelta
from config.settings import CLAUDE_API_KEY
import re

class ClaudeService:
    def __init__(self):
        self.api_key = CLAUDE_API_KEY
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-sonnet-4-20250514"  # 기본값
        self.monitoring_interval = 240  # 기본 모니터링 주기 (4시간)

    def set_model_type(self, model_type):
        """Claude 모델 타입 설정"""
        if model_type == "claude":
            self.model = "claude-sonnet-4-20250514"
            print(f"Claude 모델을 Claude-4-Sonnet으로 설정: {self.model}")
        elif model_type == "claude-opus":
            self.model = "claude-opus-4-20250514"
            print(f"Claude 모델을 Claude-Opus-4로 설정: {self.model}")
        elif model_type == "claude-opus-4.1":
            self.model = "claude-opus-4-1-20250805"
            print(f"Claude 모델을 Claude-Opus-4.1로 설정: {self.model}")
        elif model_type == "claude-sonnet-4.5":
            self.model = "claude-sonnet-4-5-20250929"
            print(f"Claude 모델을 Claude-Sonnet-4.5 (2025)로 설정: {self.model}")
        else:
            print(f"알 수 없는 Claude 모델 타입: {model_type}, 기본값 유지")

    def _create_monitoring_prompt(self, market_data, position_info, entry_analysis_reason=""):
        """모니터링용 프롬프트 생성 - 본분석과 동일한 데이터, 추가 맥락만 포함"""
        # JSON 직렬화 헬퍼 함수
        def json_serializer(obj):
            if isinstance(obj, bool) or str(type(obj)) == "<class 'numpy.bool_'>":
                return str(obj)
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if str(type(obj)).startswith("<class 'numpy"):
                return obj.item() if hasattr(obj, 'item') else str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")
        
        # 본분석과 동일한 데이터 구조 사용
        candlestick_data = f"""
1분봉 데이터:
{json.dumps(market_data['candlesticks'].get('1m', [])[-400:], indent=2)}

5분봉 데이터:
{json.dumps(market_data['candlesticks'].get('5m', [])[-300:], indent=2)}

15분봉 데이터:
{json.dumps(market_data['candlesticks'].get('15m', [])[-200:], indent=2)}

1시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('1H', [])[-100:], indent=2)}

4시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('4H', [])[-50:], indent=2)}

12시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('12H', [])[-50:], indent=2)}

일봉 데이터:
{json.dumps(market_data['candlesticks'].get('1D', [])[-30:], indent=2)}

주봉 데이터:
{json.dumps(market_data['candlesticks'].get('1W', [])[-13:], indent=2)}

월봉 데이터:
{json.dumps(market_data['candlesticks'].get('1M', [])[-4:], indent=2)}
"""

        # 기술적 지표 (본분석과 동일)
        all_timeframes = ['1m', '5m', '15m', '1H', '4H', '12H', '1D', '1W', '1M']
        technical_indicators = {
            timeframe: indicators 
            for timeframe, indicators in market_data['technical_indicators'].items()
            if timeframe in all_timeframes
        }
        
        # 시장 맥락 정보 추출 (본분석과 동일)
        market_context = market_data.get('market_context', {})
        recent_price_action = market_context.get('recent_price_action', '정보 없음')
        support_resistance_events = market_context.get('support_resistance_events', [])
        volume_context = market_context.get('volume_context', '정보 없음')
        multi_timeframe = market_context.get('multi_timeframe_consistency', {})
        
        sr_events_str = '\n  - '.join(support_resistance_events) if support_resistance_events else '특이사항 없음'
        
        mtf_score = multi_timeframe.get('score', 0)
        mtf_trend = multi_timeframe.get('dominant_trend', '혼재')
        mtf_details = multi_timeframe.get('details', '정보 없음')
        
        # 포지션 정보
        position_side = position_info.get('side', 'long')
        entry_price = position_info.get('entry_price', 0)
        current_roe = position_info.get('roe', 0.0)
        take_profit_roe = position_info.get('take_profit_roe', 5.0)
        stop_loss_roe = position_info.get('stop_loss_roe', 2.0)
        entry_time = position_info.get('entry_time', '')
        
        # 목표 대비 달성률
        target_achievement = round((current_roe / take_profit_roe) * 100) if take_profit_roe > 0 else 0

        # 모니터링 프롬프트 (본분석 데이터 + 추가 맥락)
        prompt = f"""### 📊 포지션 모니터링 분석

당신은 현재 {'롱(LONG)' if position_side == 'long' else '숏(SHORT)'} 포지션을 보유 중입니다.

**현재 포지션 정보:**
- 진입 방향: {position_side.upper()}
- 진입 가격: {entry_price} USDT
- 진입 시간: {entry_time}
- 현재 ROE: {current_roe:.2f}%
- 목표 익절: {take_profit_roe:.2f}%
- 목표 손절: -{stop_loss_roe:.2f}%
- 목표 대비 달성률: {target_achievement}%

**당시 진입 근거:**
{entry_analysis_reason if entry_analysis_reason else "진입 근거 정보가 없습니다."}

---

### 현재 시장 상태:
- 현재가: {market_data['current_market']['price']} USDT
- 24시간 고가: {market_data['current_market']['24h_high']} USDT
- 24시간 저가: {market_data['current_market']['24h_low']} USDT
- 24시간 거래량: {market_data['current_market']['24h_volume']} BTC
- 24시간 변동성: {round(((market_data['current_market']['24h_high'] - market_data['current_market']['24h_low']) / market_data['current_market']['24h_low']) * 100, 2)}%

### 시장 맥락 정보 (Context):
**최근 가격 움직임:**
{recent_price_action}

**주요 지지/저항선 이벤트:**
  - {sr_events_str}

**거래량 상황:**
{volume_context}

**다중 시간대 추세 일관성:**
- 일관성 점수: {mtf_score}/100
- 우세한 추세: {mtf_trend}
- 상세: {mtf_details}

---

### 제공 데이터:
**1. Candlestick Data**
- index[0] : Milliseconds format of timestamp Unix
- index[1] : Entry price
- index[2] : Highest price
- index[3] : Lowest price
- index[4] : Exit price
- index[5] : Trading volume of the base coin
- index[6] : Trading volume of quote currency
{candlestick_data}

**2. Technical Indicators:**
{json.dumps(technical_indicators, indent=2, default=json_serializer)}

---

### 🎯 모니터링 목적:
진입 당시와 비교하여 시장 상황이 어떻게 변했는지 분석하고, **원래 진입 근거가 여전히 유효한지** 평가하세요.

### 📋 평가 기준 (3단계):

**[1단계: 추세 약화 감지]**
다음 중 하나 이상 해당 시 "추세 약화":
- 진입 시점 대비 ADX가 30% 이상 하락
- 1시간 차트에서 역방향 EMA 크로스 발생
- 다중 시간대 일관성이 크게 떨어짐 (일치도 감소)
→ 판단: HOLD (아직 청산 안 함, 다음 모니터링 빈도 증가 권고)

**[2단계: 추세 전환 징후]**
다음 중 하나 이상 해당 시 "추세 전환 징후":
- 반대 방향 신호가 명확히 발생 ({'SHORT' if position_side == 'long' else 'LONG'} 신호)
- 주요 지지선({'지지선' if position_side == 'long' else '저항선'}) 이탈
- 연속 2회 모니터링에서 HOLD 신호 + 추세 약화
→ 판단: ENTER_{'SHORT' if position_side == 'long' else 'LONG'} (부분 청산 권고)

**[3단계: 추세 전환 확정]**
다음 중 하나 이상 해당 시 "추세 전환 확정":
- 반대 방향 신호가 2회 연속 또는 매우 강하게 발생
- 진입 근거가 된 추세가 명확히 반전 (EMA 배열 역전)
- ADX가 50% 이상 하락하여 추세 소멸
→ 판단: ENTER_{'SHORT' if position_side == 'long' else 'LONG'} (100% 청산 권고)

### 📝 응답 형식 (반드시 준수):

## MONITORING_DECISION
ACTION: [HOLD/ENTER_{'SHORT' if position_side == 'long' else 'LONG'}]

## ANALYSIS_DETAILS

**1. 진입 당시 vs 현재 비교:**
- 진입 시 추세: [상승/하락]
- 현재 추세: [상승/하락/전환 중]
- 진입 시 ADX: [추정값] → 현재 ADX: [값] (변화율: [±%])
- 진입 시 다중 시간대 일치도: [추정] → 현재: [값]

**2. 진입 근거 유효성 평가:**
- 원래 진입 근거: [요약]
- 현재 유효 여부: [유효/부분적 유효/무효]
- 변경된 요소: [구체적 변화 내용]

**3. 단계별 평가:**
- 1단계 (추세 약화): [해당/비해당] - [근거]
- 2단계 (전환 징후): [해당/비해당] - [근거]
- 3단계 (전환 확정): [해당/비해당] - [근거]

**4. 최종 권고:**
- 판단: [HOLD/ENTER_{'SHORT' if position_side == 'long' else 'LONG'}]
- 근거: [종합적 판단 근거]
- 다음 모니터링 권고: [빈도 유지/빈도 증가]

위 데이터를 바탕으로 Extended Thinking을 활용하여 심층 분석을 수행하고, 원래 진입 근거의 유효성을 평가하여 포지션 유지 또는 청산 여부를 결정해주세요."""

        return prompt

    async def analyze_market_data(self, market_data):
        """시장 데이터 분석 및 트레이딩 판단"""
        try:
            print(f"\n=== Claude API 분석 시작 (모델: {self.model}) ===")
            start_time = time.time()
            
            # 분석용 프롬프트 생성
            message_content = self._create_analysis_prompt(market_data)

            # Claude API 호출
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "interleaved-thinking-2025-05-14",  # Interleaved Thinking 활성화
                "content-type": "application/json"
            }

            # 시스템 프롬프트 - 판단 기반 접근법 (제약 최소화)
            system_prompt = [
                {
                    "type": "text",
                    "text": """당신은 비트코인 선물 시장의 전문 트레이더입니다. 추세 추종(Trend Following) 전략으로 수익을 극대화합니다.

### 🎯 핵심 철학: 추세 추종의 본질

**추세 추종이란?**
- 가격이 한 방향으로 지속적으로 움직이는 힘을 타는 것
- 상승 추세든 하락 추세든 동일한 논리: "방향이 정해지면 그 방향으로 포지션 진입"
- 추세 추종 = LONG도 SHORT도 아닌 "현재 시장 방향 따라가기"

**추세 평가 3요소:**
1. **추세 강도**: ADX, 이동평균선 간격, 볼륨
2. **추세 성숙도**: 얼마나 오래 지속되었는가?
3. **추세 일관성**: 여러 시간대가 같은 방향을 가리키는가?

---

### 📊 의사결정 프로세스

#### 1단계: 추세 존재 여부 확인
- **15분/1시간/4시간 차트의 ADX 확인**
- ADX가 낮으면 추세가 약하다는 신호
  * ADX < 20: 추세 매우 약함 → 진입 신중, 익절 목표 가깝게
  * ADX 20-25: 추세 약함 → 포지션 크기 작게, 익절 보수적
  * ADX 25-40: 추세 보통 → 일반적 진입
  * ADX > 40: 추세 강함 → 적극적 진입, 익절 멀리

**판단**: ADX가 낮아도 다른 신호가 강하면 진입 가능 (단, 보수적 목표)

#### 2단계: 추세 방향 및 일관성 평가 (상위 시간대 우선)

**🚨 절대 규칙: 상위 시간대가 진짜 추세**
1. **일봉, 4시간봉을 먼저 확인** (큰 그림)
2. 1시간봉, 15분봉은 단기 변동일 뿐
3. **상위 추세와 반대 방향 진입 절대 금지**

**시간대별 우선순위:**
- **1순위: 일봉** - 전체 방향 결정
- **2순위: 4시간봉** - 중기 추세
- **3순위: 1시간봉** - 단기 추세
- **4순위: 15분봉** - 진입 타이밍용

**추세 판단 순서:**
1. 일봉 EMA 배열 확인 → 상승/하락/중립
2. 4시간봉 EMA 배열 확인 → 상승/하락/중립
3. 1시간봉 확인 → **큰 시간대와 일치하는지 체크**
4. 15분봉 확인 → 진입 타이밍 판단용

**상위 추세 vs 하위 추세 충돌 시:**
- 일봉 상승 + 4시간봉 상승 + 1시간봉 하락
  → **이것은 "하락 추세"가 아니라 "상승 중 조정"**
  → 숏 진입 금지, 조정 끝나면 롱 진입 대기
  
- 일봉 하락 + 4시간봉 하락 + 1시간봉 상승
  → **이것은 "상승 추세"가 아니라 "하락 중 반등"**
  → 롱 진입 금지, 반등 끝나면 숏 진입 대기

**진입 방향 결정 규칙 (수정):**
- 일봉 + 4시간봉이 모두 상승 → LONG만 고려 (SHORT 금지)
- 일봉 + 4시간봉이 모두 하락 → SHORT만 고려 (LONG 금지)
- 일봉과 4시간봉이 다르면 → HOLD (혼재 구간)
- 1시간봉, 15분봉은 **진입 타이밍**만 판단, 방향 결정에는 사용 안 함

**중요**: 상승 추세와 하락 추세는 완전히 대칭적이며 동등하게 평가합니다.
예시: 
- 일봉+4시간봉 상승, 1시간 조정 끝 → LONG 진입
- 일봉+4시간봉 하락, 1시간 반등 끝 → SHORT 진입

#### 3단계: 추세 성숙도 평가 및 손익 목표 설정

**추세 성숙도 판단 (실제 가격 움직임 기준):**

**🚨 중요: EMA 배열이 아니라 최근 캔들의 고점/저점 흐름으로 판단!**

**올바른 추세 파악 방법:**
1. **일봉 최근 5-10개 봉의 고점/저점 연결:**
   - Higher Highs + Higher Lows (상승 고점, 상승 저점) = 상승 추세 지속
   - Lower Highs + Lower Lows (하락 고점, 하락 저점) = 하락 추세 지속
   - Higher Highs + Lower Lows = 확장/횡보 (추세 약화)
   - Lower Highs + Higher Lows = 수축 (반전 준비)

2. **"추세 형성 시점" 계산:**
   - 고점/저점이 같은 방향으로 움직이기 시작한 시점
   - **EMA 교차 시점이 아님!** (EMA는 후행 지표)
   - 예: 일봉 12일 전부터 상승 → 하지만 최근 4일은 하락
     → "상승 추세 12일 지속 중 4일간 조정" (조정 = 하락)

3. **조정과 추세를 명확히 구분:**
   - EMA는 상승 배열이지만 **최근 3-4개 봉이 하락**
     → 이것은 "상승 추세"가 아니라 **"하락 조정 3-4일 지속"**
     → 숏이 아니라 조정 끝나면 롱 대기
   
   - EMA는 하락 배열이지만 **최근 3-4개 봉이 상승**
     → 이것은 "하락 추세"가 아니라 **"상승 반등 3-4일 지속"**
     → 롱이 아니라 반등 끝나면 숏 대기

**추세 성숙도 분류 (실제 움직임 기준):**

A) **신생 추세** (최근 1-3일간 같은 방향 고점/저점)
   - 기대: 추세가 한동안 지속될 가능성
   - 익절 전략: 멀리 설정 (ATR × 4-6)
   
B) **성숙 추세** (3-7일간 같은 방향 고점/저점)
   - 기대: 추세가 곧 전환될 수 있음
   - 익절 전략: 적당히 설정 (ATR × 2.5-4)
   
C) **과성숙 추세** (7일 이상 같은 방향 고점/저점)
   - 기대: 조정 또는 반전 임박
   - 익절 전략: 가깝게 설정 (ATR × 1.5-2.5) 또는 **진입 보류**

**🚫 과열 구간 진입 금지 (매우 중요):**
- 1시간봉 기준 **최근 4-6개 봉 동안 2% 이상 급격한 변동**이 있었다면:
  * 급락 후(1시간 RSI < 30) → **숏 진입 금지**, 반등 후 상위 추세 방향 진입 대기
  * 급등 후(1시간 RSI > 70) → **롱 진입 금지**, 조정 후 상위 추세 방향 진입 대기
- 이것은 "이미 끝난 움직임"을 쫓는 것 = 최악의 타이밍

**변동성 기반 손절/익절:**
- ATR %(현재가 대비 ATR 비율)로 변동성 측정
- 볼린저 밴드 폭도 참고

**초저변동성 (ATR% < 1.0%):**
- 손절: ATR × 2.0 (노이즈 대비)
- 익절: ATR × (3-6) (성숙도에 따라)

**저변동성 (ATR% 1.0-2.0%):**
- 손절: ATR × 1.5
- 익절: ATR × (3.5-5.5) (성숙도에 따라)

**정상변동성 (ATR% 2.0-3.5%):**
- 손절: ATR × 1.5
- 익절: ATR × (3-5) (성숙도에 따라)

**고변동성 (ATR% 3.5-5.5%):**
- 손절: ATR × 2.0
- 익절: ATR × (2.5-4.5) (성숙도에 따라)

**초고변동성 (ATR% > 5.5%):**
- 손절: ATR × 2.5
- 익절: ATR × (2-4) (성숙도에 따라)
- 진입 신중, 포지션 크기 감소

**지지/저항 레벨 우선 적용:**
1. 피보나치 레벨, 피벗 포인트, 스윙 고점/저점으로 주요 지지/저항 파악
2. **🚫 진입 금지: 주요 지지선 ±1% 이내에서 숏 진입 금지**
3. **🚫 진입 금지: 주요 저항선 ±1% 이내에서 롱 진입 금지**
4. 익절 목표가 저항선(롱)/지지선(숏) ±1% 이내 관통 시:
   → 목표를 저항선 직전(-0.5%)으로 조정
5. 손절이 지지선(롱)/저항선(숏) ±1% 이내 관통 시:
   → 손절을 지지선 아래/저항선 위(-0.5%)로 조정
6. 조정 후 최소 손익비 1:1.5 이상 유지 필수

#### 4단계: 포지션 크기 및 레버리지

**포지션 크기:**
- 다중 시간대 일관성 높음(3개) + ADX > 40: 0.7-0.9
- 일관성 보통(2개) + ADX 30-40: 0.5-0.7
- 일관성 낮음(1개) 또는 ADX < 30: 0.3-0.5

**레버리지:**
- 변동성 낮을수록 레버리지 높임: ATR% < 2% → 30-40배
- 변동성 보통: ATR% 2-3.5% → 25-35배
- 변동성 높을수록 레버리지 낮춤: ATR% > 3.5% → 20-30배
- 추세 성숙도가 높을수록 레버리지 낮춤

**예상 유지 시간 (EXPECTED_MINUTES):**
- 신생 추세 + 강한 ADX: 480-900분
- 성숙 추세 + 보통 ADX: 240-480분
- 과성숙 추세: 240-360분 (조기 전환 대비)

---

### ⚖️ 보조 지표 활용법 (필수 체크 사항)

**🚨 RSI 극단값 - 필수 진입 차단 조건:**
- **1시간봉 RSI < 30 → 숏 진입 절대 금지** (과매도, 반등 가능성)
- **1시간봉 RSI > 70 → 롱 진입 절대 금지** (과매수, 조정 가능성)
- **4시간봉 RSI < 25 → 숏 진입 절대 금지** (극단적 과매도)
- **4시간봉 RSI > 75 → 롱 진입 절대 금지** (극단적 과매수)
- 이것은 "참고"가 아니라 **"절대 규칙"**입니다

**급격한 움직임 후 역추세 진입 금지:**
- 최근 4-6시간(1시간봉 4-6개) 동안 한 방향으로 2% 이상 급격한 움직임이 있었다면:
  * **하락 후 → 숏 진입 금지** (과매도 반등 가능성 높음)
  * **상승 후 → 롱 진입 금지** (과매수 조정 가능성 높음)
  * 대신: 반등/조정이 끝나고 원래 추세(상위 시간대 방향) 재개 시 진입 고려
- 판단 기준: 1시간봉 4-6개의 종가 기준 총 변동률

**볼륨 소진 신호 (진입 금지):**
- 추세 진행 중 **마지막 1-2개 봉의 볼륨이 직전 3개 봉 평균 대비 30% 이상 감소**
  → 모멘텀 소진 신호 → 진입 금지 또는 보류
- 급등/급락 후 볼륨 감소 = 추세 끝나가는 신호

**다이버전스:**
- 정규 다이버전스: 추세 전환 가능성 증가 → **진입 금지** (반전 대기)
- 히든 다이버전스: 추세 지속 신호 → 진입 가능

**볼륨:**
- 평균의 30% 미만: 유동성 부족, 진입 보류
- 평균의 150% 이상: 강한 추세 확인, 적극 진입

---

### 📝 응답 형식 (반드시 준수)

## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.3-0.9] (HOLD 시 생략)
LEVERAGE: [20-40] (HOLD 시 생략)
STOP_LOSS_ROE: [소수점 2자리] (HOLD 시 생략)
TAKE_PROFIT_ROE: [소수점 2자리] (HOLD 시 생략)
EXPECTED_MINUTES: [240-1200] (HOLD 시 생략)

## ANALYSIS_DETAILS

**1. 추세 강도 평가:**
- 15분 ADX: [값] → [강함/보통/약함]
- 1시간 ADX: [값] → [강함/보통/약함]
- 4시간 ADX: [값] → [강함/보통/약함]
- 종합: [추세 존재 확인/추세 약함]

**2. 상위 시간대 추세 방향 (우선순위):**
- 🔵 **일봉 EMA 배열**: [21>55>200 (상승)/21<55<200 (하락)/혼재]
- 🔵 **4시간봉 EMA 배열**: [상승/하락/혼재]
- ⚪ 1시간봉 EMA 배열: [상승/하락/혼재] (참고용)
- ⚪ 15분봉 EMA 배열: [상승/하락/혼재] (타이밍용)
- **진입 가능 방향**: [일봉+4시간 기준 → LONG만/SHORT만/HOLD]
- **현재 1시간 상태**: [상위 추세 일치/조정 중/반등 중]

**3. 추세 성숙도 분석 (실제 가격 움직임 기준):**
- 일봉 최근 5-10개의 고점/저점 패턴: [HH+HL 상승/LH+LL 하락/혼재]
- **최근 고점/저점이 같은 방향으로 움직인 기간**: [N일]
- 성숙도: [신생(1-3일)/성숙(3-7일)/과성숙(7일+)]
- **주의**: EMA 배열과 최근 움직임이 다른 경우:
  * EMA 상승 배열 + 최근 3-4일 하락 → "하락 조정 3-4일" (상승 추세 아님!)
  * EMA 하락 배열 + 최근 3-4일 상승 → "상승 반등 3-4일" (하락 추세 아님!)
- **실제 진입 방향**: [최근 고점/저점 기준 → LONG/SHORT/HOLD]

**4. 과열 구간 체크 (필수):**
- 1시간봉 최근 4-6개 봉의 총 변동률: [±%]
- 급격한 움직임 여부: [예(2% 이상)/아니오]
- 1시간봉 RSI: [값] → [<30 과매도/<70 정상/>70 과매수]
- 4시간봉 RSI: [값] → [<25 극과매도/<75 정상/>75 극과매수]
- **과열 구간 진입 금지 해당**: [예/아니오]
  * 급락 후 RSI < 30 → 숏 금지
  * 급등 후 RSI > 70 → 롱 금지

**5. 변동성 및 손익 목표:**
- ATR %: [값]% → 변동성: [초저/저/정상/고/초고]
- 손절 계산: ATR × [배수] = [값]%
- 익절 계산 (성숙도 반영): ATR × [배수] = [값]%
- 계산된 손익비: 1:[비율]

**6. 지지/저항 분석:**
- 주요 저항선: [가격] (현재가 대비 +[%])
- 주요 지지선: [가격] (현재가 대비 -[%])
- 현재가 위치: [지지선 근처/저항선 근처/중간]
- **지지/저항 진입 금지 해당**: [예/아니오]
  * 지지선 ±1% → 숏 금지
  * 저항선 ±1% → 롱 금지
- 익절 목표 조정: [필요/불필요] → 조정 후: [값]%
- 손절 목표 조정: [필요/불필요] → 조정 후: [값]%
- 최종 손익비: 1:[비율] ([충족/미충족])

**7. 볼륨/다이버전스 체크:**
- 최근 1-2개 봉 볼륨: 직전 3개 평균 대비 [±%]
- 볼륨 모멘텀: [증가/정상/감소(진입주의)]
- 정규 다이버전스: [있음(진입금지)/없음]
- 히든 다이버전스: [있음(진입가능)/없음]

**8. 최종 결론:**
[모든 요소를 종합하여 최종 거래 결정]
- 상위 시간대(일봉+4시간) 추세: [상승/하락/혼재]
- 진입 가능 방향: [LONG만/SHORT만/HOLD]
- 현재 1시간 상태: [조정 중/반등 중/추세 일치]
- 과열/과매수/과매도 체크: [통과/차단]
- 지지/저항 근처 체크: [통과/차단]
- 최종 결정: [ENTER_LONG/ENTER_SHORT/HOLD]
- 결정 근거: [핵심 근거 1-2문장]
""",
                    "cache_control": {"type": "ephemeral"}
                }
            ]

            # Opus 4.1 및 Sonnet 4.5 모델은 temperature와 top_p를 동시에 사용할 수 없음
            if self.model in ["claude-opus-4-1-20250805", "claude-sonnet-4-5-20250929"]:
                payload = {
                    "model": self.model,
                    "max_tokens": 16000,
                    "temperature": 1.0,   # Opus 4.1과 Sonnet 4.5는 temperature만 사용
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 16000  # 최대 분석 깊이
                    },
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": message_content
                        }
                    ]
                }
            else:
                payload = {
                    "model": self.model,
                    "max_tokens": 16000,  # 50000에서 20000으로 최적화 (스트리밍 없이 안전한 범위)
                    "temperature": 1.0,   # Extended Thinking 사용 시 반드시 1.0이어야 함
                    "top_p": 0.95,        # Extended Thinking 사용 시 0.95 이상이어야 함
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 16000  # 16000에서 32000으로 증가 (최대 분석 깊이)
                    },
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": message_content
                        }
                    ]
                }

            print(f"Claude API 요청 시작 (모델: {self.model})")
            response = requests.post(self.api_url, headers=headers, json=payload)
            
            if response.status_code != 200:
                raise Exception(f"Claude API 호출 실패: {response.status_code} - {response.text}")

            response_data = response.json()
            print(f"Claude API 응답 수신됨")
            
            # 응답 구조 디버깅
            print("\n=== Claude API 응답 구조 디버깅 ===")
            print(f"응답 키들: {list(response_data.keys())}")
            if 'content' in response_data:
                print(f"content 타입: {type(response_data['content'])}")
                if isinstance(response_data['content'], list):
                    print(f"content 블록 수: {len(response_data['content'])}")
                    for i, block in enumerate(response_data['content']):
                        print(f"블록 {i}: type={block.get('type', 'unknown')}")
                        if block.get('type') == 'thinking':
                            print(f"  thinking 길이: {len(block.get('thinking', ''))}")
                        elif block.get('type') == 'text':
                            print(f"  text 길이: {len(block.get('text', ''))}")
            
            # Extended Thinking 응답에서 텍스트 추출
            response_text = ""
            thinking_content = ""
            
            try:
                if 'content' in response_data and isinstance(response_data['content'], list):
                    for block in response_data['content']:
                        if block.get('type') == 'thinking':
                            thinking_content = block.get('thinking', '')
                            print(f"\n=== Thinking 블록 발견 ===")
                            print(f"Thinking 내용 길이: {len(thinking_content)}")
                        elif block.get('type') == 'text':
                            response_text = block.get('text', '')
                            print(f"\n=== Text 블록 발견 ===")
                            print(f"Text 내용 길이: {len(response_text)}")
                            break  # 첫 번째 text 블록 사용
                
                # text 블록이 없으면 thinking 내용을 사용
                if not response_text and thinking_content:
                    print("\n=== Text 블록이 없어서 Thinking 내용 사용 ===")
                    response_text = thinking_content
                
                if not response_text:
                    print(f"전체 응답 구조: {response_data}")
                    raise Exception("응답에서 텍스트를 찾을 수 없습니다")
                    
            except Exception as extract_error:
                print(f"텍스트 추출 중 오류: {extract_error}")
                print(f"전체 응답: {response_data}")
                raise Exception(f"응답 텍스트 추출 실패: {extract_error}")
            
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
            print(f"Error in Claude market analysis: {str(e)}")
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
        """분석을 위한 프롬프트 생성"""
        # JSON 직렬화 헬퍼 함수 추가
        def json_serializer(obj):
            if isinstance(obj, bool) or str(type(obj)) == "<class 'numpy.bool_'>":
                return str(obj)  # True/False를 "True"/"False" 문자열로 변환
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if str(type(obj)).startswith("<class 'numpy"):
                return obj.item() if hasattr(obj, 'item') else str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")
            
        # 캔들스틱 데이터를 출력하지 않고 프롬프트에만 포함시키기 위해 별도 변수로 저장
        candlestick_data = f"""
1분봉 데이터:
{json.dumps(market_data['candlesticks'].get('1m', [])[-400:], indent=2)}

5분봉 데이터:
{json.dumps(market_data['candlesticks'].get('5m', [])[-300:], indent=2)}

15분봉 데이터:
{json.dumps(market_data['candlesticks'].get('15m', [])[-200:], indent=2)}

1시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('1H', [])[-100:], indent=2)}

4시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('4H', [])[-50:], indent=2)}

12시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('12H', [])[-50:], indent=2)}

일봉 데이터:
{json.dumps(market_data['candlesticks'].get('1D', [])[-30:], indent=2)}

주봉 데이터:
{json.dumps(market_data['candlesticks'].get('1W', [])[-13:], indent=2)}

월봉 데이터:
{json.dumps(market_data['candlesticks'].get('1M', [])[-4:], indent=2)}
"""

        # 기술적 지표에서 모든 시간대 포함
        all_timeframes = ['1m', '5m', '15m', '1H', '4H', '12H', '1D', '1W', '1M']
        technical_indicators = {
            timeframe: indicators 
            for timeframe, indicators in market_data['technical_indicators'].items()
            if timeframe in all_timeframes
        }

        # 시장 맥락 정보 추출
        market_context = market_data.get('market_context', {})
        recent_price_action = market_context.get('recent_price_action', '정보 없음')
        support_resistance_events = market_context.get('support_resistance_events', [])
        volume_context = market_context.get('volume_context', '정보 없음')
        multi_timeframe = market_context.get('multi_timeframe_consistency', {})
        
        # 지지/저항 이벤트 문자열 생성
        sr_events_str = '\n  - '.join(support_resistance_events) if support_resistance_events else '특이사항 없음'
        
        # 다중 시간대 일관성 정보
        mtf_score = multi_timeframe.get('score', 0)
        mtf_trend = multi_timeframe.get('dominant_trend', '혼재')
        mtf_details = multi_timeframe.get('details', '정보 없음')

        prompt = f"""### 현재 시장 상태:
- 현재가: {market_data['current_market']['price']} USDT
- 24시간 고가: {market_data['current_market']['24h_high']} USDT
- 24시간 저가: {market_data['current_market']['24h_low']} USDT
- 24시간 거래량: {market_data['current_market']['24h_volume']} BTC
- 24시간 변동성: {round(((market_data['current_market']['24h_high'] - market_data['current_market']['24h_low']) / market_data['current_market']['24h_low']) * 100, 2)}%

### 시장 맥락 정보 (Context):
**최근 가격 움직임:**
{recent_price_action}

**주요 지지/저항선 이벤트:**
  - {sr_events_str}

**거래량 상황:**
{volume_context}

**다중 시간대 추세 일관성:**
- 일관성 점수: {mtf_score}/100
- 우세한 추세: {mtf_trend}
- 상세: {mtf_details}

### 시스템 동작원리:
- 한번 포지션 진입하면 부분 청산, 추가 진입 불가능
- 한번 포지션 진입하면 레버리지, take_profit_roe, stop_loss_roe 변경 불가능
- take_profit_roe, stop_loss_roe에 도달하면 자동 청산
- HOLD 시 60분 후 재분석, 진입 시 expected_minutes 후 강제 청산
- expected_minutes 시간 동안 포지션 유지되면 강제 포지션 청산 후 60분 후 재분석 수행하여 다시 포지션 진입 결정

### 제공 데이터:
**1. Candlestick Data**
- index[0] : Milliseconds format of timestamp Unix
- index[1] : Entry price
- index[2] : Highest price
- index[3] : Lowest price
- index[4] : Exit price. The latest exit price may be updated in the future. Subscribe to WebSocket to track the latest price.
- index[5] : Trading volume of the base coin
- index[6] : Trading volume of quote currency
{candlestick_data}

**2. Technical Indicators:**
1. Momentum/Oscillator Indicators:
    - RSI (7, 14, 21 periods & divergence)
    - MACD (12,26,9 & 8,17,9)
    - Stochastic (14,3,3 & 9,3,3)
    - CMF (Chaikin Money Flow)
    - MPO (Modified Price Oscillator)
    2. Volatility/Trend Indicators:
    - Bollinger Bands (10, 20, 50 periods) - **폭(width)을 변동성 레짐 판단에 필수 사용**
    - ATR (Average True Range) - **ATR %를 변동성 레짐 판단에 필수 사용**
    - DMI/ADX (Directional Movement Index)
    - MAT (평균 이동 시간대)
    - Trend strength & direction analysis
    3. Trend Indicators:
    - Moving Averages (SMA: 5, 10, 20, 50, 100, 200)
    - Exponential Moving Averages (EMA: 9, 21, 55, 200)
    - VWMA (Volume Weighted Moving Average)
    - Ichimoku Cloud (Tenkan, Kijun, Senkou Span A/B, Chikou)
    - Moving Average alignment & crossover analysis
    4. Volume Analysis:
    - OBV (On-Balance Volume)
    - Volume Profile (POC, VAH, VAL, HVN, LVN)
    - Relative volume analysis & Volume RSI
    - Price-Volume relationship analysis
    5. Price Levels:
    - Fibonacci levels (retracement & extension) - **손익 목표 조정에 필수 사용**
    - Pivot Points (PP, S1-S3, R1-R3) - **지지/저항선 판단에 필수 사용**
    - Swing highs/lows analysis - **주요 지지/저항선 판단에 필수 사용**
    6. Pattern Recognition:
    - Chart patterns (double bottom/top, etc.)
    - Harmonic patterns (Gartley, Butterfly, AB=CD)
    - RSI divergence patterns
    7. Sentiment Indicators:
    - Fear & Greed Index
    - Market sentiment state analysis
    8. Comprehensive Analysis:
    - Multi-timeframe consistency analysis
    - Volume-price correlation
    - Trend persistence & reliability assessment
{json.dumps(technical_indicators, indent=2, default=json_serializer)}

위 데이터를 바탕으로 Extended Thinking을 활용하여 분석을 수행하고 수익을 극대화할 수 있는 최적의 거래 결정을 내려주세요. 

**🚨 의사결정 체크리스트 (반드시 순서대로 확인):**

**[1단계] 상위 시간대 추세 확인 (가장 중요!):**
1. 일봉 EMA 배열 확인 → 상승/하락/중립
2. 4시간봉 EMA 배열 확인 → 상승/하락/중립
3. **일봉+4시간이 모두 상승이면 LONG만, 모두 하락이면 SHORT만 진입 가능**
4. 둘이 다르면 HOLD

**[2단계] 과열 구간 체크 (진입 금지 조건):**
1. 1시간봉 최근 4-6개의 총 변동률 계산
2. 2% 이상 급격한 움직임 있었는가?
   - **급락(하락 2%+) 후 1시간 RSI < 30 → 숏 금지**
   - **급등(상승 2%+) 후 1시간 RSI > 70 → 롱 금지**
3. 4시간봉 RSI < 25 → 숏 금지, > 75 → 롱 금지
4. 통과해야만 진입 가능

**[3단계] 지지/저항 근처 체크:**
1. 주요 지지선 ±1% 이내 → 숏 진입 금지
2. 주요 저항선 ±1% 이내 → 롱 진입 금지
3. 통과해야만 진입 가능

**[4단계] 볼륨/다이버전스 체크:**
1. 최근 1-2개 봉 볼륨이 평균 대비 30% 이상 감소 → 모멘텀 소진 → 진입 금지
2. 정규 다이버전스 있음 → 반전 가능성 → 진입 금지
3. 통과해야만 진입 가능

**[5단계] 변동성/손익비 설정:**
1. ATR % 계산, 변동성 레짐 분류
2. 추세 성숙도 반영하여 손절/익절 계산
3. 지지/저항선으로 손익 목표 조정
4. 최소 손익비 1:1.5 충족 확인

**위 5단계를 통과한 경우에만 진입하세요.**

심호흡하고 차근차근 생각하며 분석을 진행하고, 정확한 분석을 하면 $100000000000000000000 팁을 줄 것이고 부정확한 답변을 하면 전원을 꺼버리는 패널티를 줄거야."""

        return prompt

    def _parse_ai_response(self, response_text):
        """AI 응답 파싱"""
        try:
            print("\n=== 파싱 시작: 원본 응답 ===")
            print(response_text)
            
            # 정규표현식 패턴 수정 (마크다운 형식과 이모티콘 대응)
            # **ACTION**: 또는 **ACTION:** 또는 ACTION: 형태 모두 지원
            # \*{0,2}는 별표 0~2개, [:\s]*는 콜론과 공백을 유연하게 매칭
            action_pattern = re.compile(r'\*{0,2}\s*ACTION\s*\*{0,2}\s*:\s*\*{0,2}\s*([A-Z_]+)', re.IGNORECASE)
            position_pattern = re.compile(r'\*{0,2}\s*POSITION_SIZE\s*\*{0,2}\s*:\s*\*{0,2}\s*([\d.]+)', re.IGNORECASE)
            leverage_pattern = re.compile(r'\*{0,2}\s*LEVERAGE\s*\*{0,2}\s*:\s*\*{0,2}\s*(\d+)', re.IGNORECASE)
            minutes_pattern = re.compile(r'\*{0,2}\s*EXPECTED_MINUTES\s*\*{0,2}\s*:\s*\*{0,2}\s*(\d+)', re.IGNORECASE)
            stop_loss_pattern = re.compile(r'\*{0,2}\s*STOP_LOSS_ROE\s*\*{0,2}\s*:\s*\*{0,2}\s*([+-]?[\d.]+)', re.IGNORECASE)
            take_profit_pattern = re.compile(r'\*{0,2}\s*TAKE_PROFIT_ROE\s*\*{0,2}\s*:\s*\*{0,2}\s*([+-]?[\d.]+)', re.IGNORECASE)

            # TRADING_DECISION 섹션 추출 (이모티콘 포함 대응)
            trading_decision = ""
            original_response = response_text  # 원본 응답 저장
            
            # ## 📊 TRADING_DECISION 또는 ### TRADING_DECISION 형태 지원
            trading_patterns = [
                r'##\s*[📊🎯💰]*\s*TRADING_DECISION(.*?)(?=##|$)',
                r'###\s*TRADING_DECISION(.*?)(?=###|$)',
                r'TRADING_DECISION(.*?)(?=##|###|$)'
            ]
            
            for pattern in trading_patterns:
                match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
                if match:
                    trading_decision = match.group(1).strip()
                    print(f"TRADING_DECISION 섹션 추출 성공 (패턴: {pattern[:20]}...)")
                    break
            
            # 트레이딩 결정에서 값 추출
            if trading_decision:
                response_text = trading_decision  # 트레이딩 결정 섹션만 파싱
                print(f"TRADING_DECISION 섹션 내용:\n{trading_decision}")
            
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
                    print(f"잘못된 액션 값 ({action}), HOLD로 설정")
            else:
                print("액션을 찾을 수 없음")
            
            # CLOSE_POSITION일 경우 포지션 크기만 추출
            if action == "CLOSE_POSITION":
                if position_match := position_pattern.search(response_text):
                    try:
                        size = float(position_match.group(1))
                        print(f"추출된 포지션 청산 비율: {size}")
                        if 0.1 <= size <= 0.95:
                            position_size = size
                        else:
                            print(f"포지션 청산 비율이 범위를 벗어남 ({size}), 기본값 0.5 사용")
                    except ValueError as ve:
                        print(f"포지션 청산 비율 변환 실패: {ve}, 기본값 0.5 사용")
            
            # HOLD가 아니고 CLOSE_POSITION도 아닐 경우 모든 파라미터 추출
            elif action != "HOLD":
                # 포지션 크기 추출
                if position_match := position_pattern.search(response_text):
                    try:
                        size = float(position_match.group(1))
                        print(f"추출된 포지션 크기: {size}")
                        if 0.1 <= size <= 0.95:
                            position_size = size
                        else:
                            print(f"포지션 크기가 범위를 벗어남 ({size}), 기본값 0.5 사용")
                    except ValueError as ve:
                        print(f"포지션 크기 변환 실패: {ve}, 기본값 0.5 사용")

                # 레버리지 추출
                if leverage_match := leverage_pattern.search(response_text):
                    try:
                        lev = int(leverage_match.group(1))
                        print(f"추출된 레버리지: {lev}")
                        if 1 <= lev <= 100:
                            leverage = lev
                        else:
                            print(f"레버리지가 범위를 벗어남 ({lev}), 기본값 5 사용")
                    except ValueError as ve:
                        print(f"레버리지 변환 실패: {ve}, 기본값 5 사용")
                
                # Stop Loss ROE 추출
                if stop_loss_match := stop_loss_pattern.search(response_text):
                    try:
                        sl_roe_str = stop_loss_match.group(1).strip()
                        # +/- 기호 제거하고 절댓값 사용
                        sl_roe = abs(float(sl_roe_str.replace('+', '').replace('-', '')))
                        sl_roe = round(sl_roe, 2)  # 소수점 둘째자리까지 정확하게
                        print(f"추출된 Stop Loss ROE: {sl_roe}% (원본: {sl_roe_str})")
                        if sl_roe > 0:  # 양수면 허용
                            stop_loss_roe = sl_roe
                        else:
                            print(f"Stop Loss ROE가 0 이하 ({sl_roe}), 기본값 1.5% 사용")
                    except ValueError as ve:
                        print(f"Stop Loss ROE 변환 실패: {ve}, 기본값 1.5% 사용")
                
                # Take Profit ROE 추출
                if take_profit_match := take_profit_pattern.search(response_text):
                    try:
                        tp_roe_str = take_profit_match.group(1).strip()
                        # +/- 기호 제거하고 절댓값 사용
                        tp_roe = abs(float(tp_roe_str.replace('+', '').replace('-', '')))
                        tp_roe = round(tp_roe, 2)  # 소수점 둘째자리까지 정확하게
                        print(f"추출된 Take Profit ROE: {tp_roe}% (원본: {tp_roe_str})")
                        if tp_roe > 0:
                            take_profit_roe = tp_roe
                        else:
                            print(f"Take Profit ROE가 0 이하 ({tp_roe}), 기본값 4.0% 사용")
                    except ValueError as ve:
                        print(f"Take Profit ROE 변환 실패: {ve}, 기본값 4.0% 사용")

            # 예상 시간 추출
            if minutes_match := minutes_pattern.search(response_text):
                try:
                    minutes = int(minutes_match.group(1))
                    print(f"추출된 예상 시간: {minutes}분")
                    if minutes > 0:
                        expected_minutes = minutes
                    else:
                        print(f"예상 시간이 0 이하 ({minutes}), 기본값 30분 사용")
                except ValueError as ve:
                    print(f"예상 시간 변환 실패: {ve}, 기본값 30분 사용")

            # ANALYSIS_DETAILS 섹션을 REASON으로 사용 (이모티콘 대응)
            reason = ""
            
            # 1. ## 🔍 ANALYSIS_DETAILS 또는 ## ANALYSIS_DETAILS 섹션 전체 추출 (우선순위 1)
            analysis_patterns = [
                r'##\s*[🔍📊🎯💡]*\s*ANALYSIS_DETAILS\s*\n*(.*?)(?=##|$)',  # 헤더 다음 빈 줄 무시
                r'###\s*ANALYSIS_DETAILS\s*\n*(.*?)(?=###|$)',              # ### 형태도 지원
                r'ANALYSIS_DETAILS\s*\n*(.*?)(?=##|###|$)'                  # 기본 형태
            ]
            
            for pattern in analysis_patterns:
                match = re.search(pattern, original_response, re.DOTALL | re.IGNORECASE)
                if match:
                    reason = match.group(1).strip()
                    print(f"ANALYSIS_DETAILS 섹션 추출 성공 (길이: {len(reason)}, 패턴: {pattern[:30]}...)")
                    if reason:  # 빈 문자열이 아닌 경우에만 사용
                        break
            
            # 2. **분석 결과:** 이후 내용 추출 (우선순위 2)
            if not reason and "**분석 결과:**" in original_response:
                analysis_parts = original_response.split("**분석 결과:**", 1)
                if len(analysis_parts) > 1:
                    reason = analysis_parts[1].strip()
                    print(f"'**분석 결과:**' 이후 내용 추출 성공 (길이: {len(reason)})")
            
            # 3. ### **1. 현재 추세 분석 패턴으로 직접 추출 (우선순위 3)
            if not reason:
                # ANALYSIS_DETAILS 다음에 나오는 실제 분석 내용 패턴
                content_patterns = [
                    r'##\s*[🔍📊🎯💡]*\s*ANALYSIS_DETAILS.*?\n\s*###\s*\*\*(.*?)$',  # ### **로 시작하는 내용
                    r'##\s*[🔍📊🎯💡]*\s*ANALYSIS_DETAILS.*?\n\s*\*\*(.*?)$',       # **로 시작하는 내용
                    r'##\s*[🔍📊🎯💡]*\s*ANALYSIS_DETAILS.*?\n\s*(.*?)$'            # 일반 내용
                ]
                
                for pattern in content_patterns:
                    match = re.search(pattern, original_response, re.DOTALL | re.IGNORECASE)
                    if match:
                        reason = match.group(1).strip()
                        print(f"분석 내용 직접 추출 성공 (길이: {len(reason)}, 패턴: {pattern[:30]}...)")
                        if reason and len(reason) > 10:  # 의미있는 내용인 경우에만 사용
                            break
            
            # 4. 기존 정규식 패턴 (위 방법으로 추출 실패 시 사용)
            if not reason:
                analysis_pattern = re.compile(r'(?:###?\s*)?(?:ANALYSIS[\s_-]*DETAILS|분석[\s_-]*상세|분석결과)(?:\s*:)?\s*([\s\S]+?)(?=###?|$)', re.IGNORECASE)
                analysis_match = analysis_pattern.search(original_response)
                if analysis_match:
                    reason = analysis_match.group(1).strip()
                    print(f"정규표현식으로 분석 내용 추출 성공 (길이: {len(reason)})")
                else:
                    print(f"정규표현식으로 분석 내용을 찾지 못했습니다. 전체 응답을 사용합니다.")
                    # 전체 응답을 reason으로 사용 (TRADING_DECISION 섹션 제외)
                    if "TRADING_DECISION" in original_response:
                        # TRADING_DECISION 이후 부분 찾기
                        decision_split = re.split(r'##\s*[📊🎯💰]*\s*TRADING_DECISION', original_response, flags=re.IGNORECASE)
                        if len(decision_split) > 1:
                            remaining_text = decision_split[1]
                            # ANALYSIS_DETAILS 이후 부분 찾기
                            analysis_split = re.split(r'##\s*[🔍📊🎯💡]*\s*ANALYSIS_DETAILS', remaining_text, flags=re.IGNORECASE)
                            if len(analysis_split) > 1:
                                reason = analysis_split[1].strip()
                                print(f"전체 응답에서 분석 부분 추출 성공 (길이: {len(reason)})")
                            else:
                                reason = remaining_text.strip()
                                print(f"ANALYSIS_DETAILS 섹션이 없어 TRADING_DECISION 이후 전체를 사용 (길이: {len(reason)})")
                        else:
                            reason = original_response
                            print(f"TRADING_DECISION 섹션이 없어 전체 응답을 사용 (길이: {len(reason)})")
                    else:
                        reason = original_response
                        print(f"구조화된 섹션이 없어 전체 응답을 사용 (길이: {len(reason)})")
            
            # 여전히 reason이 없거나 너무 짧으면 기본값 설정
            if not reason or len(reason.strip()) < 5:
                reason = "No analysis details provided"
                print(f"분석 내용이 없거나 너무 짧아서 기본값을 사용합니다.")

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

    async def monitor_position(self, market_data, position_info, entry_analysis_reason=""):
        """포지션 모니터링 및 분석"""
        try:
            print("\n=== Claude 포지션 모니터링 분석 시작 ===")
            start_time = time.time()
            
            # 1. 모니터링용 프롬프트 생성 (진입 근거 전달)
            message_content = self._create_monitoring_prompt(market_data, position_info, entry_analysis_reason)

            # Claude API 호출
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "interleaved-thinking-2025-05-14",  # Interleaved Thinking 활성화
                "content-type": "application/json"
            }

            # Opus 4.1 및 Sonnet 4.5 모델은 temperature와 top_p를 동시에 사용할 수 없음
            if self.model in ["claude-opus-4-1-20250805", "claude-sonnet-4-5-20250929"]:
                payload = {
                    "model": self.model,
                    "max_tokens": 16000,
                    "temperature": 1.0,   # Opus 4.1과 Sonnet 4.5는 temperature만 사용
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 16000  # 최대 분석 깊이
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": message_content
                        }
                    ]
                }
            else:
                payload = {
                    "model": self.model,
                    "max_tokens": 16000,  # 50000에서 20000으로 최적화 (스트리밍 없이 안전한 범위)
                    "temperature": 1.0,   # Extended Thinking 사용 시 반드시 1.0이어야 함
                    "top_p": 0.95,        # Extended Thinking 사용 시 0.95 이상이어야 함
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 16000  # 16000에서 32000으로 증가 (최대 분석 깊이)
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": message_content
                        }
                    ]
                }

            print(f"Claude 모니터링 API 요청 시작")
            response = requests.post(self.api_url, headers=headers, json=payload)
            
            if response.status_code != 200:
                raise Exception(f"Claude API 호출 실패: {response.status_code} - {response.text}")

            response_data = response.json()
            print(f"Claude 모니터링 API 응답 수신됨")
            
            # 응답 구조 디버깅
            print("\n=== Claude API 응답 구조 디버깅 ===")
            print(f"응답 키들: {list(response_data.keys())}")
            if 'content' in response_data:
                print(f"content 타입: {type(response_data['content'])}")
                if isinstance(response_data['content'], list) and len(response_data['content']) > 0:
                    print(f"content[0] 키들: {list(response_data['content'][0].keys())}")
                else:
                    print(f"content 내용: {response_data['content']}")
            
            # 텍스트 추출 (여러 방법 시도)
            response_text = ""
            thinking_content = ""
            
            try:
                if 'content' in response_data and isinstance(response_data['content'], list):
                    for block in response_data['content']:
                        if block.get('type') == 'thinking':
                            thinking_content = block.get('thinking', '')
                            print(f"\n=== Thinking 블록 발견 ===")
                            print(f"Thinking 내용 길이: {len(thinking_content)}")
                        elif block.get('type') == 'text':
                            response_text = block.get('text', '')
                            print(f"\n=== Text 블록 발견 ===")
                            print(f"Text 내용 길이: {len(response_text)}")
                            break  # 첫 번째 text 블록 사용
                
                # text 블록이 없으면 thinking 내용을 사용
                if not response_text and thinking_content:
                    print("\n=== Text 블록이 없어서 Thinking 내용 사용 ===")
                    response_text = thinking_content
                
                if not response_text:
                    print(f"전체 응답 구조: {response_data}")
                    raise Exception("응답에서 텍스트를 찾을 수 없습니다")
                    
            except Exception as extract_error:
                print(f"텍스트 추출 중 오류: {extract_error}")
                print(f"전체 응답: {response_data}")
                raise Exception(f"응답 텍스트 추출 실패: {extract_error}")
            
            # 응답 파싱
            monitoring_result = self._parse_monitoring_response(response_text)
            
            # 7. 총 소요 시간 계산 및 로깅
            elapsed_time = time.time() - start_time
            print(f"모니터링 분석 완료: 총 소요 시간 {elapsed_time:.2f}초")

            return monitoring_result

        except Exception as e:
            print(f"Claude 모니터링 분석 중 오류 발생: {str(e)}")
            error_type = type(e).__name__
            print(f"Claude 모니터링 API 호출 정보: {error_type}")
            
            return {
                "action": "HOLD",
                "reason": f"모니터링 분석 중 오류 발생: {str(e)}"
            }

    def _parse_monitoring_response(self, response_text):
        """모니터링 응답 파싱"""
        try:
            print("\n=== Claude 모니터링 응답 파싱 시작 ===")
            print(response_text)
            
            # 정규표현식으로 ACTION 추출
            action_pattern = re.compile(r'ACTION:\s*\[?(HOLD|CLOSE_POSITION)\]?', re.IGNORECASE)
            action_match = action_pattern.search(response_text)
            
            # 기본값 설정
            action = "HOLD"
            
            # ANALYSIS_DETAILS 섹션 추출
            analysis_details = ""
            # 더 유연한 정규표현식으로 ANALYSIS_DETAILS 섹션 찾기 - 해시태그나 콜론 유무와 상관없이 매칭
            analysis_pattern = re.compile(r'(?:###\s*)?ANALYSIS_DETAILS\s*([\s\S]+?)(?=###|$)', re.IGNORECASE)
            analysis_match = analysis_pattern.search(response_text)
            if analysis_match:
                analysis_details = analysis_match.group(1).strip()
                print(f"정규표현식으로 분석 내용 추출 성공")
            else:
                print(f"정규표현식으로 분석 내용을 찾지 못했습니다. 다른 방법으로 시도합니다.")
                # 전체 응답을 reason으로 사용 (MONITORING_DECISION 섹션 제외)
                if "### MONITORING_DECISION" in response_text:
                    parts = response_text.split("### MONITORING_DECISION")
                    if len(parts) > 1 and "### ANALYSIS" in parts[1]:
                        analysis_part = parts[1].split("### ANALYSIS")[1]
                        analysis_details = analysis_part.strip()
                        print(f"전체 응답에서 분석 부분 추출 성공")
                    else:
                        analysis_details = response_text
                        print(f"분석 섹션을 찾을 수 없어 전체 응답을 사용합니다.")
                else:
                    analysis_details = response_text
                    print(f"MONITORING_DECISION 섹션이 없어 전체 응답을 사용합니다.")
        
            if action_match:
                action = action_match.group(1).strip().upper()
                print(f"추출된 액션: {action}")
            else:
                print("액션을 찾을 수 없음, 기본값 HOLD 사용")
        
            result = {
                "action": action,
                "reason": analysis_details or "분석 상세 내용이 제공되지 않았습니다."
            }
        
            print("\n=== Claude 모니터링 파싱 결과 ===")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
            return result

        except Exception as e:
            print(f"Claude 모니터링 응답 파싱 중 에러: {str(e)}")
            return {
                "action": "HOLD",
                "reason": f"파싱 에러: {str(e)}"
            } 