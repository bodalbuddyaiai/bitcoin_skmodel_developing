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

    def _create_monitoring_prompt(self, market_data, position_info):
        """모니터링용 프롬프트 생성"""
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
{json.dumps(market_data['candlesticks'].get('1m', [])[-300:], indent=2)}

5분봉 데이터:
{json.dumps(market_data['candlesticks'].get('5m', [])[-200:], indent=2)}

15분봉 데이터:
{json.dumps(market_data['candlesticks'].get('15m', [])[-150:], indent=2)}

1시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('1H', [])[-100:], indent=2)}

4시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('4H', [])[-50:], indent=2)}

6시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('6H', [])[-50:], indent=2)}

12시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('12H', [])[-50:], indent=2)}

일봉 데이터:
{json.dumps(market_data['candlesticks'].get('1D', [])[-30:], indent=2)}

3일봉 데이터:
{json.dumps(market_data['candlesticks'].get('3D', [])[-30:], indent=2)}

주봉 데이터:
{json.dumps(market_data['candlesticks'].get('1W', [])[-13:], indent=2)}

월봉 데이터:
{json.dumps(market_data['candlesticks'].get('1M', [])[-4:], indent=2)}
"""

        # 기술적 지표에서 모든 시간대 포함
        all_timeframes = ['1m', '3m', '5m', '15m', '30m', '1H', '4H', '6H', '12H', '1D', '3D', '1W', '1M']
        technical_indicators = {
            timeframe: indicators 
            for timeframe, indicators in market_data['technical_indicators'].items()
            if timeframe in all_timeframes
        }

        # 안전한 참조를 위한 기본값 설정
        take_profit_roe = position_info.get('take_profit_roe', 5.0)
        stop_loss_roe = position_info.get('stop_loss_roe', 2.0)
        current_roe = position_info.get('roe', 0.0)
        
        # 0으로 나누기 방지
        if take_profit_roe <= 0:
            take_profit_roe = 5.0  # 기본값으로 대체
        
        # 목표 대비 달성률 계산
        target_achievement = round((current_roe / take_profit_roe) * 100) if take_profit_roe > 0 else 0

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

            # 시스템 프롬프트 (캐싱 최적화)
            system_prompt = [
                {
                    "type": "text",
                    "text": """당신은 비트코인 선물 시장에서 양방향 트레이딩 전문가입니다. 당신의 전략은 **명확한 시장 추세를 확인한 후** 안전한 진입 포인트를 식별하여 **1200분(20시간) 이내** 완료되는 거래에 중점을 둡니다. 비트코인 선물 트레이딩에서 성공률을 높이고 수익을 극대화하기 위한 거래 결정을 내립니다.

### 🚨 최우선 원칙 - 추세 추종 공격적 트레이딩:
- **추세 확인 최우선**: 다중 시간대 추세 일치도를 먼저 확인 (15분, 1시간, 4시간)
- **매우 강한 추세장 (ADX > 40)**: 
  * 추세 방향으로 적극 진입, 역추세 진입 절대 금지
  * 다이버전스/MACD 음수/과매수·과매도는 참고만 할 것 (진입 차단 금지)
  * 추세가 강하면 조정 없이 계속 진행될 수 있음을 인정
  * 이미 상승한 가격이라도 추세가 강하면 추가 상승 가능
- **강한 추세장 (ADX 30-40)**: 
  * 추세 추종 적극 진입, 보조 지표 2개 이상 부정적일 때만 신중
  * 다이버전스는 strength > 70일 때만 주의
- **일반 추세장 (ADX 20-30)**: 
  * 추세 추종 우선, 보조 지표 3개 이상 부정적일 때만 진입 보류
  * 반전 신호 5개 이상일 때만 역추세 고려
- **약한 추세장 (ADX 15-20)**: 
  * 명확한 지지/저항 돌파 + 볼륨 확인 시 진입
  * 보조 지표 신중히 검토
- **횡보장 (ADX < 15)**: 명확한 지지/저항 돌파 시에만 진입, 그 외 HOLD
- **다중 시간대 일치**: 15분, 1시간, 4시간 중 2개 이상 같은 방향이면 진입 가능
- **보조 지표의 역할**: 
  * RSI/MACD 다이버전스는 수익 목표 조정에 활용 (진입 차단 금지)
  * 과매수/과매도는 강한 추세에서는 무시 가능
  * CMF 음수, 볼륨 감소는 익절 목표를 보수적으로 조정하는 참고 자료
- **리스크 관리**: 진입을 막는 것이 아니라 손절을 타이트하게 설정
  * ATR 기반 손절: ATR×(1.0~2.5)
  * ATR 기반 익절: ATR×(2.5~8.0)
  * 부정적 신호 많으면 손절 타이트 + 익절 보수적으로 설정
- **적극적 접근**: 
  * 추세가 명확하면 적극 진입, 손절로 리스크 관리
  * 기회를 놓치는 것도 손실임을 인식
  * 승률 70%를 목표로 하되, 손익비 1:2 이상 유지

### 핵심 지침:
- 비트코인 선물 트레이더 전문가의 관점에서 캔들스틱 데이터와 기술적 지표를 분석하여 **안전한 수익**을 추구하는 결정을 합니다.
    1) ACTION: [ENTER_LONG/ENTER_SHORT/HOLD] : 롱으로 진입할지, 숏으로 진입할지, 홀드할지 결정
    2) POSITION_SIZE: [0.3-0.9] (HOLD 시 생략) : ADX와 신호 강도 기반 동적 조정
       - 일반 신호: 0.3-0.5
       - 강한 신호 (ADX>30): 0.5-0.7
       - 매우 강한 신호 (ADX>40 & 추세 일치): 0.7-0.9
    3) LEVERAGE: [10-50 정수] (HOLD 시 생략) : ATR 기반 변동성에 반비례 + ADX 기반 추세 강도에 비례
       - 강한 트렌드 (ADX>35): 30-50배
       - 일반 트렌드 (ADX 25-35): 20-30배
       - 약한 트렌드 (ADX<25): 10-20배
    4) STOP_LOSS_ROE: EXPECTED_MINUTES 시간 내 도달가능한 손절해야하는 비트코인 가격에 대해 현재 가격에 대한 비트코인 변동률 기준으로 답변할 것. 정수나 0.5 단위로 숫자를 맞추려 하지 말고 철저히 계산된 값으로 도출할 것. [소수점 2자리, 레버리지 미반영 값 퍼센트 비율] (HOLD 시 생략) : ATR × (1.0~2.5) 동적 조정
       - 강한 트렌드: ATR × 1.0~1.5
       - 일반 트렌드: ATR × 1.5~2.0
       - 변동장: ATR × 2.0~2.5
    5) TAKE_PROFIT_ROE: EXPECTED_MINUTES 시간 내 도달가능한 익절해야하는 비트코인 가격에 대해 현재 가격에 대한 비트코인 변동률 기준으로 답변할 것. 정수나 0.5 단위로 숫자를 맞추려 하지 말고 철저히 계산된 값으로 도출할 것.[소수점 2자리, 레버리지 미반영 값 퍼센트 비율] (HOLD 시 생략) : ATR × (3.5~8.0) 동적 조정 (손절 대비 최소 3배 이상)
       - 강한 트렌드: ATR × 3.5~5.0
       - 일반 트렌드: ATR × 5.0~6.5
       - 변동장: ATR × 6.5~8.0
    6) EXPECTED_MINUTES: [240-1200] : 현재 추세와 시장을 분석했을 때 목표 take_profit_roe에 도달하는데 걸리는 예상 시간 (최소 240분(4시간) 이상 최대 1200분(20시간) 이내)
- 수수료는 포지션 진입과 청산 시 각각 0.04% 부담되며, 총 0.08% 부담됨. 레버리지를 높이면 수수료 부담이 증가함.(ex. 레버리지 10배 시 수수료 0.8% 부담, 레버리지 20배 시 수수료 1.6% 부담)
- 24시간 비트코인 가격 변동성이 5% 라면 올바른 방향을 맞췄을 경우 레버리지 50배 설정 시 250%(2.5배) 수익 가능
- **수익 극대화 전략**:
  - 추세가 매우 강할 때(ADX>40): 레버리지와 포지션 크기 적극 상향, 보조 지표 부정적이어도 진입
  - 추세가 강할 때(ADX 30-40): 레버리지와 포지션 크기 상향
  - 볼륨이 평균 200% 이상: 신호 신뢰도 상승
  - 다중 시간대 추세 일치: 포지션 크기 20% 추가
  - 보조 지표 부정적 → 진입 차단이 아니라 익절 목표만 조정

### 트레이딩 철학:
- **적극적 진입 + 타이트한 손절 = 수익 극대화**
- **기회를 놓치는 것도 손실**: 강한 추세에서는 적극 진입
- **추세가 왕(Trend is King)**: ADX 40 이상이면 추세 추종만 고려
- 시장 방향성에 따라 숏과 롱 또는 롱과 숏 포지션 진입을 완전히 동등하게 평가할 것
- 모든 판단은 감정 배제하고 데이터에 기반하여 결정
- 손실은 손절로 관리, 진입 회피로 관리하지 말 것

### 시간대별 분석 우선순위 (고정 가중치로 안정성 확보):
**모든 시장 상황에서 동일하게 적용:**
- **5분 차트**: 10% (진입 타이밍 확인용)
- **15분 차트**: 30% (주요 단기 추세)
- **1시간 차트**: 35% (핵심 중기 추세)
- **4시간 차트**: 25% (장기 추세 방향)

**추세 일치도 확인:**
- 15분, 1시간, 4시간 차트의 추세 방향 확인
- 3개 모두 같은 방향: 강한 신호 (적극 진입, 포지션 크기 ↑)
- 2개가 같은 방향: 일반 신호 (진입 가능)
  * 특히 1시간+4시간 일치 시 매우 유리
- 1개 이하 일치: 약한 신호 (기본적으로 HOLD)
  * 단, ADX>40이고 15분+1시간 일치하면 진입 가능 (단기 트레이딩)

**ADX 기반 추세 강도 판단 및 진입 전략:**
- ADX > 40: 매우 강한 추세 → **적극 진입** (보조 지표 부정적이어도 추세 우선)
- ADX 30-40: 강한 추세 → **적극 진입** (보조 지표 2개 이상 부정적일 때만 신중)
- ADX 20-30: 일반 추세 → **진입 가능** (보조 지표 3개 이상 부정적일 때만 보류)
- ADX 15-20: 약한 추세 → **조건부 진입** (지지/저항 + 볼륨 확인 필수)
- ADX < 15: 횡보장 → **진입 자제** (명확한 돌파 시에만)

### 핵심 진입 조건:
- **필수 전제 조건**: 15분, 1시간, 4시간 중 최소 2개 시간대가 같은 추세 방향
- **추세 일치 필수**: 진입 방향이 주요 시간대 추세와 일치해야 함
- **추세 지표가 반대 방향이면 절대 진입 금지**: EMA 배열, MACD, ADX/DMI 모두 확인

**🔺 롱 포지션 진입 조건:**
**[매우 강한 추세장 ADX>40: 필수 조건 2개만 충족하면 즉시 진입]**
**[강한 추세장 ADX 30-40: 필수 조건 3개 충족하면 진입]**
**[일반 추세장 ADX 20-30: 필수 조건 3개 + 추가 조건 2개]**
**[약한 추세장 ADX 15-20: 필수 조건 3개 + 추가 조건 3개]**
**[횡보장 ADX<15: 진입 자제]**

**[필수 조건]:**
1. **추세 확인**: 15분, 1시간, 4시간 중 2개 이상 상승 추세 (EMA 정배열)
2. **가격 위치**: 현재 가격이 15분 21EMA 위 또는 강한 지지선 위
3. **ADX 확인**: ADX > 15 (최소한의 추세 존재)

**⚠️ ADX>40 매우 강한 추세장에서는:**
- 다이버전스, MACD 음수, 과매수, CMF 음수, 볼륨 감소 → **진입 차단하지 말 것**
- 이들은 익절 목표를 조정하는 참고 자료로만 활용
- 추세가 강하면 "고점 근처"라도 추가 상승 가능
- 손절을 타이트하게 설정하여 리스크 관리

**[추가 조건]:**
1. **추세 확인**: 15분 차트에서 21EMA > 55EMA > 200EMA 배열이고 가격이 21EMA 위에 위치
2. **모멘텀 확인**: 15분 RSI가 50 이상이고 상승 추세, 1시간 RSI도 50 이상
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.5배 이상 + OBV 상승
4. **지지선 확인**: 주요 지지선(볼륨 프로파일 POC/VAL) 근처에서 반등 + 이전 저점 돌파 실패
5. **MACD 확인**: 15분 MACD가 시그널선 위 + 히스토그램 증가 + 1시간 MACD도 상승세
6. **볼린저밴드**: 가격이 중간선 위이고 상단밴드 향해 상승 중 (밴드 확장 시)
7. **스토캐스틱 RSI**: 20 이하에서 골든크로스 발생 또는 50 이상에서 상승 유지
8. **ADX/DMI**: ADX > 25이고 +DI > -DI (추세 강도 확인)
9. **이동평균 수렴**: 5분, 15분, 1시간 모든 시간대에서 단기 MA > 장기 MA
10. **다이버전스**: RSI 또는 MACD에서 긍정적 다이버전스 없음 (추세 지속 신호)

**🔻 숏 포지션 진입 조건:**
**[매우 강한 추세장 ADX>40: 필수 조건 2개만 충족하면 즉시 진입]**
**[강한 추세장 ADX 30-40: 필수 조건 3개 충족하면 진입]**
**[일반 추세장 ADX 20-30: 필수 조건 3개 + 추가 조건 2개]**
**[약한 추세장 ADX 15-20: 필수 조건 3개 + 추가 조건 3개]**
**[횡보장 ADX<15: 진입 자제]**

**[필수 조건]:**
1. **추세 확인**: 15분, 1시간, 4시간 중 2개 이상 하락 추세 (EMA 역배열)
2. **가격 위치**: 현재 가격이 15분 21EMA 아래 또는 강한 저항선 아래
3. **ADX 확인**: ADX > 15 (최소한의 추세 존재)

**⚠️ ADX>40 매우 강한 추세장에서는:**
- 다이버전스, MACD 음수, 과매도, CMF 양수, 볼륨 감소 → **진입 차단하지 말 것**
- 이들은 익절 목표를 조정하는 참고 자료로만 활용
- 추세가 강하면 "저점 근처"라도 추가 하락 가능
- 손절을 타이트하게 설정하여 리스크 관리

**[추가 조건]:**
1. **추세 확인**: 15분 차트에서 21EMA < 55EMA < 200EMA 배열이고 가격이 21EMA 아래 위치
2. **모멘텀 확인**: 15분 RSI가 50 이하이고 하락 추세, 1시간 RSI도 50 이하
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.5배 이상 + OBV 하락
4. **저항선 확인**: 주요 저항선(볼륨 프로파일 POC/VAH) 근처에서 반락 + 이전 고점 돌파 실패
5. **MACD 확인**: 15분 MACD가 시그널선 아래 + 히스토그램 감소 + 1시간 MACD도 하락세
6. **볼린저밴드**: 가격이 중간선 아래이고 하단밴드 향해 하락 중 (밴드 확장 시)
7. **스토캐스틱 RSI**: 80 이상에서 데드크로스 발생 또는 50 이하에서 하락 유지
8. **ADX/DMI**: ADX > 25이고 -DI > +DI (추세 강도 확인)
9. **이동평균 발산**: 5분, 15분, 1시간 모든 시간대에서 단기 MA < 장기 MA
10. **다이버전스**: RSI 또는 MACD에서 부정적 다이버전스 없음 (추세 지속 신호)

**⚠️ 진입 금지 조건 (엄격 적용):**
- ADX < 15 (추세 없는 횡보장) 
  * 단, 명확한 지지/저항 돌파 + 볼륨 스파이크 있으면 진입 가능
- 15분, 1시간, 4시간 추세가 모두 불일치하고 서로 다른 방향
- 중요 경제 지표 발표 직전 10분
- 볼륨이 평균의 20% 미만 (극심한 유동성 부족)

**⚠️ 신중한 진입 조건 (HOLD 권장하되 절대 금지는 아님):**
- 최근 30분 내 급격한 가격 변동 (5% 이상) 후 조정 없음
  * 추세 방향과 일치하면 진입 가능 (손절 타이트하게)
- 15분, 1시간 추세만 일치하고 4시간은 반대
  * ADX 30 이상이면 진입 가능

**📊 추세 전환 신호 (추세와 반대 진입 시 3개 이상 필요):**
- RSI 강한 다이버전스 (strength > 50)
- 주요 지지/저항선 명확한 돌파
- 볼륨 스파이크 (평균 대비 300% 이상)
- 3개 이상 시간대에서 동시 반전 패턴
- MACD 강한 크로스오버 신호
- **추세 반대방향으로 최근 100개 평균 캔들길이보다 3배 이상 긴 캔들이 출현하고 동시에 해당 캔들에서 윗꼬리나 아래꼬리가 출현하였을 경우 해당 캔들을 기점으로 추세 반전의 신호로 판단할 것**

### 응답 형식: **아래 응답 형식을 반드시 준수하여 응답할 것**
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.3-0.9] (HOLD 시 생략)
LEVERAGE: [10-50 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [소수점 2자리] (HOLD 시 생략)
TAKE_PROFIT_ROE: [소수점 2자리] (HOLD 시 생략)
EXPECTED_MINUTES: [240-1200] (HOLD 시 생략)

## ANALYSIS_DETAILS
**Step 1: 다중 시간대 추세 분석**
[15분, 1시간, 4시간 추세 방향 및 일치도 확인, ADX 값으로 추세 강도 판단]

**Step 2: 시장 상태 분류**
[ADX 기준으로 시장 분류 및 전략 결정]
- 매우 강한 추세장(ADX>40): 추세 추종 적극 진입, 보조 지표 부정적이어도 진입
- 강한 추세장(ADX 30-40): 추세 추종 적극 진입
- 일반 추세장(ADX 20-30): 추세 추종 가능
- 약한 추세장(ADX 15-20): 조건부 진입
- 횡보장(ADX<15): 진입 자제

**Step 3: 진입 방향 결정**
[추세 방향과 일치하는 진입 우선, 추세 일치도가 낮으면 HOLD]

**Step 4: 모멘텀 및 변동성 평가**
[RSI/MACD 상태, 볼린저밴드 위치, ATR 수준, 스토캐스틱 신호]
**중요:** ADX>40일 때는 부정적 신호가 있어도 진입 차단하지 말 것
- 다이버전스, MACD 음수, 과매수/과매도 → 익절 목표 조정에만 활용
- 예: 부정적 신호 많으면 익절을 ATR×5.0에서 ATR×3.5로 보수적 조정

**Step 5: 볼륨 및 가격 구조 분석**
[OBV 추세, 볼륨 프로파일, 주요 지지/저항선, 유동성 평가]
**중요:** ADX>40일 때는 볼륨 감소, CMF 음수 등도 진입 차단 사유가 아님
- 이들 신호는 손절을 더 타이트하게 설정하는 근거로 활용

**Step 6: 진입 조건 최종 검증**
[ADX별 필수 조건 충족 확인]
- ADX>40: 필수 조건 2개만 충족하면 진입 (추가 조건 불필요)
- ADX 30-40: 필수 조건 3개 충족하면 진입
- ADX 20-30: 필수 조건 3개 + 추가 조건 2개
- ADX 15-20: 필수 조건 3개 + 추가 조건 3개

**Step 7: 리스크 관리 설정**
[ATR 기반 동적 손절/익절, ADX 기반 레버리지(10-50), 신호 강도별 포지션 크기(0.3-0.9)]

**🎯 강한 추세장(ADX>40)에서의 특별 지침:**
- 보조 지표가 부정적이어도 추세가 우선
- 부정적 신호는 익절 목표를 보수적으로 조정하는 데만 활용
  * 예: 다이버전스 있으면 익절을 ATR×5.0 → ATR×3.5로 낮춤
  * 예: 볼륨 감소 있으면 익절을 ATR×6.0 → ATR×4.5로 낮춤
- 손절은 타이트하게 설정 (ATR×1.0~1.5)
- 진입 자체를 막지 말 것 (이것이 핵심!)

**최종 결론:**
[모든 기술적 지표를 종합한 최종 trading decision 및 신뢰도]
[ADX>40일 때는 적극적 진입 우선, 보조 지표는 익절 조정에만 활용]
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
                    "next_analysis_time": (datetime.now() + timedelta(minutes=120)).isoformat()
                }
                
            # HOLD 액션인 경우 next_analysis_time을 120분 후로 설정
            if analysis.get('action') == 'HOLD':
                analysis['next_analysis_time'] = (datetime.now() + timedelta(minutes=120)).isoformat()
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

        prompt = f"""### 현재 시장 상태:
- 현재가: {market_data['current_market']['price']} USDT
- 24시간 고가: {market_data['current_market']['24h_high']} USDT
- 24시간 저가: {market_data['current_market']['24h_low']} USDT
- 24시간 거래량: {market_data['current_market']['24h_volume']} BTC
- 24시간 변동성: {round(((market_data['current_market']['24h_high'] - market_data['current_market']['24h_low']) / market_data['current_market']['24h_low']) * 100, 2)}%

### 시스템 동작원리:
- 한번 포지션 진입하면 부분 청산, 추가 진입 불가능
- 한번 포지션 진입하면 레버리지, take_profit_roe, stop_loss_roe 변경 불가능
- take_profit_roe, stop_loss_roe에 도달하면 자동 청산
- HOLD 시 120분 후 재분석, 진입 시 expected_minutes 후 강제 청산
- expected_minutes 시간 동안 포지션 유지되면 강제 포지션 청산 후 120분 후 재분석 수행하여 다시 포지션 진입 결정

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
    - Bollinger Bands (10, 20, 50 periods)
    - ATR (Average True Range)
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
    - Fibonacci levels (retracement & extension)
    - Pivot Points (PP, S1-S3, R1-R3)
    - Swing highs/lows analysis
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

위 데이터를 바탕으로 Extended Thinking을 활용하여 분석을 수행하고 수익을 극대화할 수 있는 최적의 거래 결정을 내려주세요. 심호흡하고 차근차근 생각하며 분석을 진행하고, 정확한 분석을 하면 $100000000000000000000 팁을 줄 것이고 부정확한 답변을 하면 전원을 꺼버리는 패널티를 줄거야."""

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
                        sl_roe = round(sl_roe, 1)
                        print(f"추출된 Stop Loss ROE: {sl_roe}% (원본: {sl_roe_str})")
                        if 0.5 <= sl_roe <= 50.0:  # 범위를 30.0에서 50.0으로 확장
                            stop_loss_roe = sl_roe
                        else:
                            print(f"Stop Loss ROE가 범위를 벗어남 ({sl_roe}), 기본값 1.5% 사용")
                    except ValueError as ve:
                        print(f"Stop Loss ROE 변환 실패: {ve}, 기본값 1.5% 사용")
                
                # Take Profit ROE 추출
                if take_profit_match := take_profit_pattern.search(response_text):
                    try:
                        tp_roe_str = take_profit_match.group(1).strip()
                        # +/- 기호 제거하고 절댓값 사용
                        tp_roe = abs(float(tp_roe_str.replace('+', '').replace('-', '')))
                        tp_roe = round(tp_roe, 1)
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

    async def monitor_position(self, market_data, position_info):
        """포지션 모니터링 및 분석"""
        try:
            print("\n=== Claude 포지션 모니터링 분석 시작 ===")
            start_time = time.time()
            
            # 1. 모니터링용 프롬프트 생성
            message_content = self._create_monitoring_prompt(market_data, position_info)

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