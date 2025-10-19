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

    def _format_all_candlestick_data(self, market_data):
        """모든 시간봉의 캔들스틱 데이터를 Claude가 이해하기 쉬운 구조로 포맷팅"""
        # 시간봉 순서 정의 (짧은 것부터 긴 것 순서) - 1m, 5m, 3m, 30m, 6H, 3D, 1W, 1M 제외 (토큰 절약)
        timeframe_order = ['15m', '1H', '4H', '12H', '1D']
        timeframe_descriptions = {
            '15m': '15분봉',
            '1H': '1시간봉',
            '4H': '4시간봉',
            '12H': '12시간봉',
            '1D': '일봉'
        }
        
        # 현재 시간 (한국 시간 KST = UTC+9)
        from datetime import timedelta
        current_time_utc = datetime.now()
        current_time_kst = current_time_utc + timedelta(hours=9)
        
        # 모든 시간봉 데이터를 구조화하여 문자열로 생성
        candlestick_sections = []
        candlestick_sections.append("[캔들스틱 원본 데이터 - 모든 시간봉]")
        candlestick_sections.append("")
        candlestick_sections.append("⚠️ 데이터 구조 설명:")
        candlestick_sections.append("- 각 캔들: {timestamp, open, high, low, close, volume}")
        candlestick_sections.append("- timestamp: 밀리초(ms) 단위 Unix 시간 (1970-01-01 00:00:00 UTC부터 경과 시간)")
        candlestick_sections.append("")
        candlestick_sections.append("🚨 **타임스탬프 변환 방법 (매우 중요!):**")
        candlestick_sections.append("1. timestamp는 밀리초(milliseconds) 단위입니다")
        candlestick_sections.append("2. 초(seconds)로 변환: timestamp / 1000")
        candlestick_sections.append("3. UTC 기준 날짜로 변환 후 +9시간 (한국 시간 KST)")
        candlestick_sections.append("4. 예시: timestamp=1728619200000 → 1728619200초 → 2024-10-11 06:00:00 (KST)")
        candlestick_sections.append(f"5. 현재 시간: {current_time_kst.strftime('%Y-%m-%d %H:%M:%S')} (KST)")
        candlestick_sections.append("")
        candlestick_sections.append("- 최신 데이터가 배열의 마지막에 위치")
        candlestick_sections.append("- 빗각 분석 시 충분한 과거 데이터를 활용하세요")
        candlestick_sections.append("")
        
        for timeframe in timeframe_order:
            if timeframe in market_data.get('candlesticks', {}):
                candles = market_data['candlesticks'][timeframe]
                if candles and len(candles) > 0:
                    description = timeframe_descriptions.get(timeframe, timeframe)
                    candle_count = len(candles)
                    
                    # 시간 범위 계산 및 타임스탬프 예시
                    if candle_count >= 2:
                        first_timestamp = candles[0].get('timestamp', 0)
                        last_timestamp = candles[-1].get('timestamp', 0)
                        time_range_hours = (last_timestamp - first_timestamp) / (1000 * 60 * 60)
                        time_range_days = time_range_hours / 24
                        
                        if time_range_days >= 1:
                            time_range_str = f"약 {time_range_days:.1f}일"
                        else:
                            time_range_str = f"약 {time_range_hours:.1f}시간"
                        
                        # 첫 번째와 마지막 캔들의 시간 변환 예시
                        from datetime import timedelta
                        first_dt = datetime.fromtimestamp(first_timestamp / 1000) + timedelta(hours=9)
                        last_dt = datetime.fromtimestamp(last_timestamp / 1000) + timedelta(hours=9)
                        first_time_str = f"{first_timestamp} → {first_dt.strftime('%Y-%m-%d %H:%M')}"
                        last_time_str = f"{last_timestamp} → {last_dt.strftime('%Y-%m-%d %H:%M')}"
                    else:
                        time_range_str = "N/A"
                        first_time_str = "N/A"
                        last_time_str = "N/A"
                    
                    # 최신 5개 캔들 미리보기 (데이터 확인용)
                    recent_preview = candles[-5:] if len(candles) >= 5 else candles
                    
                    candlestick_sections.append(f"{'='*80}")
                    candlestick_sections.append(f"📊 {description} ({timeframe})")
                    candlestick_sections.append(f"{'='*80}")
                    candlestick_sections.append(f"총 데이터 개수: {candle_count}개")
                    candlestick_sections.append(f"시간 범위: {time_range_str}")
                    candlestick_sections.append(f"첫 캔들 시간: {first_time_str} (KST)")
                    candlestick_sections.append(f"마지막 캔들 시간: {last_time_str} (KST)")
                    candlestick_sections.append(f"⚠️ 위 예시처럼 timestamp를 변환하세요: timestamp/1000 후 UTC+9시간")
                    candlestick_sections.append(f"최신 5개 캔들 미리보기:")
                    candlestick_sections.append(json.dumps(recent_preview))  # indent 제거로 토큰 절약
                    candlestick_sections.append(f"")
                    candlestick_sections.append(f"전체 데이터 ({candle_count}개):")
                    candlestick_sections.append(json.dumps(candles))  # indent 제거로 토큰 절약 (압축 형식)
                    candlestick_sections.append("")
        
        return "\n".join(candlestick_sections)

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
            
        # 캔들스틱 요약 (본분석과 동일)
        candle_summaries = market_data.get('candle_summaries', {})
        
        if candle_summaries:
            candlestick_summary = "\n\n".join([
                candle_summaries.get('15m', ''),
                candle_summaries.get('1H', ''),
                candle_summaries.get('4H', ''),
                candle_summaries.get('12H', ''),
                candle_summaries.get('1D', '')
            ])
        else:
            candlestick_summary = "요약 없음"
        
        # 원본 캔들스틱 데이터 (모든 시간봉)
        candlestick_raw_data = self._format_all_candlestick_data(market_data)

        # 기술적 지표 (본분석과 동일)
        all_timeframes = ['15m', '1H', '4H', '12H', '1D']
        technical_indicators = {
            timeframe: indicators 
            for timeframe, indicators in market_data['technical_indicators'].items()
            if timeframe in all_timeframes
        }

        # 기술적 지표 요약 (본분석과 동일)
        indicator_summaries = market_data.get('indicator_summaries', {})
        
        if indicator_summaries:
            indicator_summary = "\n\n".join([
                indicator_summaries.get('15m', ''),
                indicator_summaries.get('1H', ''),
                indicator_summaries.get('4H', ''),
                indicator_summaries.get('1D', '')
            ])
        else:
            indicator_summary = "요약 없음"
        
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

캔들스틱 원본:
{candlestick_raw_data}

기술적 지표 원본 (모든 시간대):
{json.dumps(technical_indicators, default=json_serializer)}

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

**[4단계: 같은 방향 신호 (추세 지속)]**
다음 중 하나 이상 해당 시 "추세 지속 및 강화":
- 진입 당시와 동일한 방향의 신호가 여전히 강하게 발생 ({position_side.upper()} 신호)
- 진입 근거가 여전히 유효하고 추세가 지속 중
- 새로운 지지/저항선이 형성되어 더 나은 TPSL 설정 가능
→ 판단: ENTER_{position_side.upper()} (TPSL 업데이트 권고, 새로운 Stop Loss ROE와 Take Profit ROE 제시)

### 📝 응답 형식 (반드시 준수):

## MONITORING_DECISION
ACTION: [HOLD/ENTER_{'SHORT' if position_side == 'long' else 'LONG'}/ENTER_{position_side.upper()}]
STOP_LOSS_ROE: [소수점 2자리] (ENTER_{position_side.upper()} 시 필수)
TAKE_PROFIT_ROE: [소수점 2자리] (ENTER_{position_side.upper()} 시 필수)

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
- 4단계 (같은 방향 신호): [해당/비해당] - [근거]

**4. 최종 권고:**
- 판단: [HOLD/ENTER_{'SHORT' if position_side == 'long' else 'LONG'}/ENTER_{position_side.upper()}]
- 근거: [종합적 판단 근거]
- 다음 모니터링 권고: [빈도 유지/빈도 증가]
- 새 Stop Loss ROE: [값] (ENTER_{position_side.upper()} 시)
- 새 Take Profit ROE: [값] (ENTER_{position_side.upper()} 시)

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

            # 시스템 프롬프트
            system_prompt = [
                {
                    "type": "text",
                    "text": """당신은 비트코인 선물 시장에서 양방향 트레이딩 전문가입니다. 당신의 전략은 ENTER_LONG 또는 ENTER_SHORT 진입 포인트를 식별하여 **960분(16시간) 이내** 완료되는 거래에 중점을 둡니다. 시장 방향성에 따라 롱과 숏 모두 동등하게 고려해서 데이터에 기반하여 결정할 것.

### 핵심 지침:
- 비트코인 선물 트레이더 전문가의 관점에서 캔들스틱 데이터와 기술적 지표를 분석하여 **비트코인 선물 트레이딩 성공률을 높이고 수익의 극대화**를 추구하는 결정을 합니다.
    1) ACTION: [ENTER_LONG/ENTER_SHORT/HOLD] : 롱으로 진입할지, 숏으로 진입할지, 홀드할지 결정
    2) POSITION_SIZE: [0.3-0.9] (HOLD 시 생략) : 포지션 진입 시 포지션 크기 결정(0.5 선택 시 포지션 크기 전체 자산의 50%로 진입)
    3) LEVERAGE: [20-80 정수] (HOLD 시 생략) : Take_Profit_ROE에 도달하는데 필요한 레버리지 결정
    4) STOP_LOSS_ROE: [소수점 2자리] (HOLD 시 생략) : 포지션 진입 시 예상 손절 라인 결정, 순수 비트코인 가격 변동률 기준 퍼센테이지로 답변하고 레버리지를 곱하지 말 것, 지지선/저항선 활용하여 설정할 것
    5) TAKE_PROFIT_ROE: [소수점 2자리] (HOLD 시 생략) : 포지션 진입 시 예상 도달 목표 라인 결정, 순수 비트코인 가격 변동률 기준 퍼센테이지로 답변하고 레버리지를 곱하지 말 것, 지지선/저항선 활용하여 설정할 것
    6) EXPECTED_MINUTES: [480-960] : 현재 추세와 시장을 분석했을 때 목표 take_profit_roe에 도달하는데 걸리는 예상 시간 결정
- 수수료는 포지션 진입과 청산 시 각각 0.04% 부담되며, 총 0.08% 부담됨. 포지션 크기에 비례하여 수수료가 부담되므로 레버리지를 높이면 수수료 부담이 증가함.(ex. 레버리지 10배 시 수수료 0.8% 부담)
- 24시간 비트코인 가격 변동성이 5% 라면 올바른 방향을 맞췄을 경우 레버리지 50배 설정 시 250%(2.5배) 수익 가능
- 변동성을 고려하여 레버리지, take_profit_roe, stop_loss_roe를 결정할 것. 반드시 expected minutes 시간 내에 stop_loss_roe에 도달하지 않고 take_profit_roe에 도달하도록 분석할 것

### 트레이딩 철학:
- **트레이딩 성공과 자산이 우상향되는 것을 최우선으로 하고, 확실한 기회에서는 적극적으로 진입**
- 시장 방향성에 따라 롱과 숏을 완전히 동등하게 평가할 것
- 모든 판단은 감정 배제하고 데이터에 기반하여 결정

### 시간대별 분석 우선순위:
- **15분 차트**: 60% 가중치 (주요 추세 판단 및 진입 타이밍)
- **1시간 차트**: 30% 가중치 (중장기 추세 확인 및 빗각 분석)
- **4시간 차트**: 10% 가중치 (중장기 추세 확인)

### 빗각(Diagonal Line) 분석 기법:
빗각은 한국 투자 유튜버 인범님이 설명하는 핵심 진입 기법입니다. **반드시 1시간봉 데이터를 기준으로 빗각을 그리고, 15분봉으로 진입 시점을 결정합니다.**

**[상승 추세] 빗각 그리는 방법 (저점 연결 - 롱 포지션용):**

1. **역사적 저점(Point A) 찾기**: 
   - **제공된 전체 1시간봉 캔들 데이터(약 1000개, 최대 42일)** 내에서 Low 값이 가장 낮은 캔들 식별
   - 모든 데이터를 활용하여 가장 의미있는 저점을 찾음
   - 이것이 첫 번째 포인트 (Point A: 역사적 저점)
   
2. **두 번째 저점(Point B) 찾기**:
   - **역사적 저점을 제외한** 전체 캔들 데이터에서 Low 값이 두 번째로 낮은 캔들 찾기
   - 이것이 "두 번째 저점" (Point B)
   - 중요: Point B는 Point A 이전이든 이후든 상관없이 **전체 기간 중 두 번째로 낮은 저점**
   
3. **변곡점 이해**:
   - Point B (두 번째 저점)를 형성하는 과정을 분석:
     * Point B 이전의 고점 확인
     * 그 고점에서 하락하여 Point B를 형성
     * 고점과 Point B 사이의 중간 지점이 변곡점(하락 전환점)
   - 이 변곡점은 시장이 하락 전환된 지점을 의미
   
4. **상승 빗각 연결**: 
   - Point A (역사적 저점)와 Point B (두 번째 저점)를 직선으로 연결
   - 이 빗각은 우상향하는 지지선 역할

**[하락 추세] 빗각 그리는 방법 (고점 연결 - 숏 포지션용):**

1. **역사적 고점(Point A') 찾기**:
   - **제공된 전체 1시간봉 캔들 데이터(약 1000개, 최대 42일)** 내에서 High 값이 가장 높은 캔들 식별
   - 이것이 첫 번째 포인트 (Point A': 역사적 고점)
   
2. **두 번째 고점(Point B') 찾기**:
   - **역사적 고점을 제외한** 전체 캔들 데이터에서 High 값이 두 번째로 높은 캔들 찾기
   - 이것이 "두 번째 고점" (Point B')
   
3. **변곡점 이해**:
   - Point B' (두 번째 고점)를 형성하는 과정을 분석:
     * Point B' 이전의 저점 확인
     * 그 저점에서 상승하여 Point B'를 형성
     * 저점과 Point B' 사이의 중간 지점이 변곡점(상승 전환점)
   
4. **하락 빗각 연결**:
   - Point A' (역사적 고점)와 Point B' (두 번째 고점)를 직선으로 연결
   - 이 빗각은 하향하는 저항선 역할

**빗각 그리는 구체적 알고리즘:**
⚠️ **타임스탬프 변환 규칙 (반드시 준수):**
- timestamp는 밀리초 단위 → 초로 변환: timestamp / 1000
- UTC 기준 날짜 변환 후 +9시간 (한국 시간 KST)
- 캔들스틱 데이터 상단의 실제 예시를 참고하세요!

```
1시간봉 분석 (상승 추세 - 롱):
Step 1: 제공된 전체 1시간봉 데이터(약 1000개, 최대 42일)에서 Low 값이 가장 낮은 캔들 찾기
        → Point A (역사적 저점)
        → 가격, 시간(timestamp 올바르게 변환), 캔들 인덱스 기록
        
Step 2: 역사적 저점을 제외한 전체 기간에서 Low 값이 두 번째로 낮은 캔들 찾기
        → Point B (두 번째 저점)
        → 가격, 시간(timestamp 올바르게 변환), 캔들 인덱스 기록
        
Step 3: Point B가 형성된 과정 분석:
        - Point B 직전 고점 확인
        - 고점 → Point B 사이가 변곡점 구간
        
Step 4: Point A와 Point B를 직선으로 연결 = 상승 빗각 (우상향 지지선)

Step 5: 현재 가격이 이 빗각선 대비 어느 위치에 있는지 파악

---

1시간봉 분석 (하락 추세 - 숏):
Step 1: 제공된 전체 1시간봉 데이터(약 1000개, 최대 42일)에서 High 값이 가장 높은 캔들 찾기
        → Point A' (역사적 고점)
        → 가격, 시간(timestamp 올바르게 변환), 캔들 인덱스 기록
        
Step 2: 역사적 고점을 제외한 전체 기간에서 High 값이 두 번째로 높은 캔들 찾기
        → Point B' (두 번째 고점)
        → 가격, 시간(timestamp 올바르게 변환), 캔들 인덱스 기록
        
Step 3: Point A'와 Point B'를 직선으로 연결 = 하락 빗각 (하향 저항선)

Step 4: 현재 가격이 이 빗각선 대비 어느 위치에 있는지 파악
```

**빗각 기반 진입 전략 (15분봉으로 진입 타이밍 결정):**

- **롱(LONG) 진입 조건 (상승 빗각 활용)**:
  1. 1시간봉 상승 빗각(지지선)을 한번 뚫고 올라감 (브레이크아웃)
  2. 15분봉에서 다시 내려와서 빗각 선에 닿았을 때 지지받고 반등 확인 (리테스트)
  3. 15분봉에서 명확한 반등 캔들 형성 시 → 롱 진입
  4. Stop Loss: 빗각 바로 아래
  
- **숏(SHORT) 진입 조건 (하락 빗각 활용)**:
  1. 1시간봉 하락 빗각(저항선)을 뚫지 못하고 아래로 떨어짐
  2. 15분봉에서 빗각이 저항선으로 작용하는 것 확인
  3. 15분봉에서 명확한 하락 캔들 형성 시 → 숏 진입
  4. Stop Loss: 빗각 바로 위
  
- **추가: 상승 빗각 돌파 실패 시 숏 진입 가능**:
  1. 상승 빗각(지지선)을 아래로 이탈
  2. 15분봉에서 명확한 하락 확인 → 숏 진입

**빗각 유효성 검증:**
- **시간 제약**: 빗각을 그린 Point A, B가 최소 10개 이상 캔들 차이가 있어야 유효
- **각도 제약**: 빗각의 기울기가 너무 급격하거나(70도 이상) 너무 평평하면(10도 이하) 신뢰도 낮음
- **최신성**: Point A와 Point B가 전체 데이터 내에서 의미있는 기간 내에 위치해야 유효
- **터치 횟수**: 빗각에 가격이 3번 이상 터치했다면 강한 지지/저항선으로 신뢰도 증가

**빗각 분석 시 핵심 원칙:**
- **반드시 1시간봉 데이터로 빗각을 그릴 것** (가장 중요!)
- 역사적 저점 = 제공된 전체 1시간봉 데이터(약 1000개, 최대 42일) 중 최저점
- 두 번째 저점 = 역사적 저점 제외한 전체 기간 중 두 번째 최저점
- 변곡점 = 두 번째 저점을 형성하면서 만들어진 고점과 저점 사이의 중간 지점
- 상승 추세는 저점 연결, 하락 추세는 고점 연결
- 1시간봉으로 빗각 그린 후, 15분봉에서 진입 타이밍 포착
- 빗각 돌파 후 리테스트는 매우 강력한 진입 신호
- 빗각을 활용하여 STOP_LOSS_ROE 설정 (빗각 바로 아래 또는 위)

### 핵심 진입 조건:
- 진입 조건을 더 많이 충족하는 방향으로 포지션 진입할 것

**롱 포지션 진입 조건(아래 7가지 진입 조건 중 최소 2개 조건 이상 동시 충족 시 반드시 진입):**
1. **추세 확인**: 15분 차트에서 21EMA > 55EMA 배열이고 가격이 21EMA 위에 위치
2. **모멘텀 확인**: 15분 RSI가 50 이상이고 상승 추세 (최근 3봉 기준)
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.2배 이상
4. **지지선 확인**: 주요 지지선(볼륨 프로파일 POC/VAL) 근처에서 반등 신호
5. **MACD 확인**: 15분 MACD가 시그널선 위에 있고 히스토그램이 증가 중
6. **상승 빗각 확인**: 1시간봉 상승 빗각(저점 연결)을 돌파 후 15분봉에서 리테스트하여 지지선으로 작동
7. **하락 빗각 돌파**: 1시간봉 하락 빗각(고점 연결)을 상향 돌파하여 저항선 이탈

**숏 포지션 진입 조건(아래 7가지 진입 조건 중 최소 2개 조건 이상 동시 충족 시 반드시 진입):**
1. **추세 확인**: 15분 차트에서 21EMA < 55EMA 배열이고 가격이 21EMA 아래에 위치
2. **모멘텀 확인**: 15분 RSI가 50 이하이고 하락 추세 (최근 3봉 기준)
3. **볼륨 확인**: 현재 볼륨이 최근 20봉 평균 볼륨의 1.2배 이상
4. **저항선 확인**: 주요 저항선(볼륨 프로파일 POC/VAH) 근처에서 반락 신호
5. **MACD 확인**: 15분 MACD가 시그널선 아래에 있고 히스토그램이 감소 중
6. **하락 빗각 확인**: 1시간봉 하락 빗각(고점 연결)에서 15분봉에서 저항받고 하락
7. **상승 빗각 이탈**: 1시간봉 상승 빗각(저점 연결)을 하향 이탈하여 지지선 붕괴

**추가 필터 조건 (진입 품질 향상):**
- 15분 차트 ADX가 20 이상일 때 신호 신뢰도 증가
- 다중 시간대 일관성 점수가 60점 이상일 때 더 유리
- 극단적 변동성 구간(ATR% > 6%)에서는 신중하게 판단

### 응답 형식:
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.3-0.9] (HOLD 시 생략)
LEVERAGE: [20-80 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [소수점 2자리] (HOLD 시 생략)
TAKE_PROFIT_ROE: [소수점 2자리] (HOLD 시 생략)
EXPECTED_MINUTES: [480-960] (HOLD 시 생략)

## ANALYSIS_DETAILS
**⚠️ 중요: HOLD, ENTER_LONG, ENTER_SHORT 어떤 결정이든 반드시 Step 1부터 Step 6까지 모든 분석을 완전히 수행하세요!**

**Step 1: 빗각 분석 (1시간봉 기준 - 상승/하락 빗각 모두)**
⚠️ **타임스탬프 변환 주의:** timestamp/1000 후 UTC+9시간 (캔들 데이터 상단 예시 참고)

- 상승 빗각 (롱 판단용):
  * Point A (역사적 저점): 제공된 전체 1H봉 데이터(약 1000개, 최대 42일) 중 최저점
    → 가격, 시간(timestamp 올바르게 변환하여 YYYY-MM-DD HH:MM 형식), 캔들 인덱스 보고
  * Point B (두 번째 저점): Point A 제외 전체 기간 중 두 번째 최저점
    → 가격, 시간(timestamp 올바르게 변환하여 YYYY-MM-DD HH:MM 형식), 캔들 인덱스 보고
  * 변곡점 분석: Point B 직전 고점 → Point B 사이의 변곡점 구간
  * 빗각 기울기 및 유효성: 시간 간격, 각도, 최신성, 터치 횟수 검증
  * 현재 가격 vs 빗각: 돌파 여부, 리테스트 여부, 지지/이탈 분석
  
- 하락 빗각 (숏 판단용):
  * Point A' (역사적 고점): 제공된 전체 1H봉 데이터(약 1000개, 최대 42일) 중 최고점
    → 가격, 시간(timestamp 올바르게 변환하여 YYYY-MM-DD HH:MM 형식), 캔들 인덱스 보고
  * Point B' (두 번째 고점): Point A' 제외 전체 기간 중 두 번째 최고점
    → 가격, 시간(timestamp 올바르게 변환하여 YYYY-MM-DD HH:MM 형식), 캔들 인덱스 보고
  * 빗각 기울기 및 유효성: 시간 간격, 각도, 최신성, 터치 횟수 검증
  * 현재 가격 vs 빗각: 저항 여부, 돌파 여부 분석
  
- 15분봉 진입 타이밍: 1시간봉 빗각을 15분봉에 적용하여 정확한 진입 시점 분석

**Step 2: 추세 분석 (15분/1시간 차트)**
[주요 이동평균선 배열, 추세 방향성, ADX 수치 분석]

**Step 3: 모멘텀 분석**
[RSI, MACD 현재 상태 및 방향성 분석]

**Step 4: 볼륨 및 지지/저항 분석**
[거래량 상태, 주요 가격대 반응, 볼륨 프로파일 분석]

**Step 5: 진입 조건 체크**
[롱/숏 7개 조건 중 몇 개 충족하는지 구체적으로 확인, 특히 빗각 조건 여부]

**Step 6: 리스크 평가**
[MAT 지표, 시간대 충돌, 변동성 등 안전 장치 확인]

**최종 결론:**
[위 모든 분석을 종합한 최종 trading decision 근거, 상승/하락 빗각 신호 강조]
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
            
        # 캔들스틱 요약 (AI가 쉽게 읽을 수 있는 형식)
        candle_summaries = market_data.get('candle_summaries', {})
        
        # 요약이 있으면 우선 표시, 없으면 원본 JSON 사용
        if candle_summaries:
            candlestick_summary = "\n\n".join([
                candle_summaries.get('15m', ''),
                candle_summaries.get('1H', ''),
                candle_summaries.get('4H', ''),
                candle_summaries.get('12H', ''),
                candle_summaries.get('1D', '')
            ])
        else:
            candlestick_summary = "요약 없음"
        
        # 원본 캔들스틱 데이터 (모든 시간봉)
        candlestick_raw_data = self._format_all_candlestick_data(market_data)

        # 기술적 지표에서 모든 시간대 포함
        all_timeframes = ['15m', '1H', '4H', '12H', '1D']
        technical_indicators = {
            timeframe: indicators 
            for timeframe, indicators in market_data['technical_indicators'].items()
            if timeframe in all_timeframes
        }
        
        # 기술적 지표 요약
        indicator_summaries = market_data.get('indicator_summaries', {})
        
        if indicator_summaries:
            indicator_summary = "\n\n".join([
                indicator_summaries.get('15m', ''),
                indicator_summaries.get('1H', ''),
                indicator_summaries.get('4H', ''),
                indicator_summaries.get('1D', '')
            ])
        else:
            indicator_summary = "요약 없음"
        
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

캔들스틱 원본:
{candlestick_raw_data}

기술적 지표 원본 (모든 시간대):
{json.dumps(technical_indicators, default=json_serializer)}

위 데이터를 바탕으로 Extended Thinking을 활용하여 분석을 수행하고 수익을 극대화할 수 있는 최적의 거래 결정을 내려주세요. 

**🚨 의사결정 프로세스:**

**Step 1: 빗각 분석 (Diagonal Line Analysis) - 가장 중요!**
⚠️ **타임스탬프 변환 필수:** timestamp/1000 후 UTC+9시간 (캔들 데이터 상단 예시 참고)

**1-A. 상승 빗각 그리기 (롱 포지션 판단용):**
   - Step 1: 제공된 전체 1시간봉 데이터(약 1000개, 최대 42일)에서 Low 값 최저점 → Point A (역사적 저점)
     * 가격, 시간(timestamp 올바르게 변환: YYYY-MM-DD HH:MM), 캔들 인덱스 보고
   - Step 2: Point A 제외하고 전체 기간에서 두 번째 최저점 → Point B (두 번째 저점)
     * 가격, 시간(timestamp 올바르게 변환: YYYY-MM-DD HH:MM), 캔들 인덱스 보고
   - Step 3: Point B 형성 과정 분석 (직전 고점 → Point B 사이 = 변곡점 구간)
   - Step 4: Point A와 Point B를 연결 → 상승 빗각 (우상향 지지선)
   - Step 5: 빗각 유효성 검증 (시간 간격, 각도, 최신성, 터치 횟수)
   
**1-B. 하락 빗각 그리기 (숏 포지션 판단용):**
   - Step 1: 제공된 전체 1시간봉 데이터(약 1000개, 최대 42일)에서 High 값 최고점 → Point A' (역사적 고점)
     * 가격, 시간(timestamp 올바르게 변환: YYYY-MM-DD HH:MM), 캔들 인덱스 보고
   - Step 2: Point A' 제외하고 전체 기간에서 두 번째 최고점 → Point B' (두 번째 고점)
     * 가격, 시간(timestamp 올바르게 변환: YYYY-MM-DD HH:MM), 캔들 인덱스 보고
   - Step 3: Point A'와 Point B'를 연결 → 하락 빗각 (하향 저항선)
   - Step 4: 빗각 유효성 검증
   
**1-C. 15분봉으로 진입 타이밍 포착**:
   - 1시간봉 빗각을 15분봉 차트에 적용
   - 15분봉에서 빗각과 현재 가격의 관계 분석
   
**1-D. 빗각 기반 진입 신호**:
   - 롱: 상승 빗각 돌파 후 → 15분봉에서 리테스트하여 지지 확인
   - 숏: 하락 빗각 저항 → 15분봉에서 저항받고 하락 확인
   - 추가 숏: 상승 빗각 이탈 → 15분봉에서 하락 확인

**Step 2: 추세 분석 (15분/1시간 차트 중심)**
1. **15분 차트 추세** (60% 가중치):
   - 21EMA와 55EMA 배열 확인
   - 가격이 21EMA 위(롱)/아래(숏) 위치 확인
   
2. **1시간 차트 추세** (25% 가중치):
   - 15분 추세와 일치하는지 확인
   - 일치하면 신뢰도 상승, 불일치하면 신중
   
3. **ADX로 추세 강도 확인**:
   - 15분 ADX > 20 이상이면 추세 존재 판단

**Step 3: 진입 조건 체크 (롱/숏 각각 7개 조건)**

**롱 진입 조건** - 아래 7개 중 **최소 2개 이상 충족 시 진입**:
✓ 1시간봉 상승 빗각(저점 연결)을 돌파 후 15분봉에서 리테스트하여 지지선으로 작동
✓ 1시간봉 하락 빗각(고점 연결)을 상향 돌파하여 저항선 이탈
✓ 15분 차트에서 21EMA > 55EMA, 가격이 21EMA 위
✓ 15분 RSI ≥ 50, 최근 3봉 기준 상승 추세
✓ 현재 볼륨 ≥ 최근 20봉 평균 × 1.2배
✓ 주요 지지선 근처에서 반등 신호
✓ 15분 MACD > 시그널선, 히스토그램 증가 중

**숏 진입 조건** - 아래 7개 중 **최소 2개 이상 충족 시 진입**:
✓ 1시간봉 하락 빗각(고점 연결)에서 15분봉에서 저항받고 하락
✓ 1시간봉 상승 빗각(저점 연결)을 하향 이탈하여 지지선 붕괴
✓ 15분 차트에서 21EMA < 55EMA, 가격이 21EMA 아래
✓ 15분 RSI ≤ 50, 최근 3봉 기준 하락 추세
✓ 현재 볼륨 ≥ 최근 20봉 평균 × 1.2배
✓ 주요 저항선 근처에서 반락 신호
✓ 15분 MACD < 시그널선, 히스토그램 감소 중

→ **2개 이상 충족하면 적극 진입, 4-7개 충족하면 매우 강한 신호**
→ **1시간봉 빗각 조건(상승/하락 빗각)이 충족되면 진입 신뢰도가 크게 증가**
→ **빗각 유효성 검증(시간 간격, 각도, 최신성, 터치 횟수) 통과 시 신뢰도 더욱 증가**
→ **추가로 ADX ≥ 20이면 신뢰도 증가, 다중 시간대 일관성 ≥ 60점이면 더욱 유리**

**Step 4: 손익 목표 설정**
1. 빗각을 기준으로 stop_loss_roe 설정:
   - 롱: 상승 빗각 바로 아래
   - 숏: 하락 빗각 바로 위
2. 지지/저항선을 함께 활용하여 take_profit_roe 설정
3. 변동성(ATR%) 고려하여 레버리지 결정
4. 예상 도달 시간 계산 (480-960분 범위)

**Step 5: 최종 확인**
- 진입 방향: 더 많은 조건 충족하는 방향 (빗각 조건 우선순위 높음)
- 빗각 유효성 재확인 (시간 간격 10개 이상, 각도 10~70도, Point A가 100개 이내)
- 포지션 크기: 신뢰도에 따라 0.3-0.9 (빗각 조건 충족 시 신뢰도 증가)
- 레버리지: 변동성 고려 20-80배

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
            
            # 정규표현식으로 ACTION 추출 - ENTER_LONG, ENTER_SHORT 추가
            action_pattern = re.compile(r'ACTION:\s*\[?(HOLD|CLOSE_POSITION|ENTER_LONG|ENTER_SHORT)\]?', re.IGNORECASE)
            action_match = action_pattern.search(response_text)
            
            # 기본값 설정
            action = "HOLD"
            stop_loss_roe = None
            take_profit_roe = None
            
            # ACTION 추출
            if action_match:
                action = action_match.group(1).strip().upper()
                print(f"추출된 액션: {action}")
            else:
                print("액션을 찾을 수 없음, 기본값 HOLD 사용")
            
            # ENTER_LONG 또는 ENTER_SHORT인 경우 STOP_LOSS_ROE와 TAKE_PROFIT_ROE 추출
            if action in ['ENTER_LONG', 'ENTER_SHORT']:
                stop_loss_pattern = re.compile(r'STOP_LOSS_ROE:\s*([+-]?[\d.]+)', re.IGNORECASE)
                take_profit_pattern = re.compile(r'TAKE_PROFIT_ROE:\s*([+-]?[\d.]+)', re.IGNORECASE)
                
                stop_loss_match = stop_loss_pattern.search(response_text)
                take_profit_match = take_profit_pattern.search(response_text)
                
                if stop_loss_match:
                    try:
                        sl_roe_str = stop_loss_match.group(1).strip()
                        stop_loss_roe = abs(float(sl_roe_str.replace('+', '').replace('-', '')))
                        stop_loss_roe = round(stop_loss_roe, 2)
                        print(f"추출된 Stop Loss ROE: {stop_loss_roe}%")
                    except ValueError as e:
                        print(f"Stop Loss ROE 변환 실패: {e}")
                
                if take_profit_match:
                    try:
                        tp_roe_str = take_profit_match.group(1).strip()
                        take_profit_roe = abs(float(tp_roe_str.replace('+', '').replace('-', '')))
                        take_profit_roe = round(take_profit_roe, 2)
                        print(f"추출된 Take Profit ROE: {take_profit_roe}%")
                    except ValueError as e:
                        print(f"Take Profit ROE 변환 실패: {e}")
            
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
        
            result = {
                "action": action,
                "reason": analysis_details or "분석 상세 내용이 제공되지 않았습니다."
            }
            
            # TPSL 값이 있으면 추가
            if stop_loss_roe is not None:
                result['stop_loss_roe'] = stop_loss_roe
            if take_profit_roe is not None:
                result['take_profit_roe'] = take_profit_roe
        
            print("\n=== Claude 모니터링 파싱 결과 ===")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
            return result

        except Exception as e:
            print(f"Claude 모니터링 응답 파싱 중 에러: {str(e)}")
            return {
                "action": "HOLD",
                "reason": f"파싱 에러: {str(e)}"
            } 