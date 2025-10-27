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
        # 시간봉 순서 정의 (짧은 것부터 긴 것 순서) - 12H, 1D 제외하여 토큰 절약
        timeframe_order = ['15m', '1H', '4H']
        timeframe_descriptions = {
            '15m': '15분봉',
            '1H': '1시간봉',
            '4H': '4시간봉'
        }
        
        # 현재 시간 (한국 시간 KST = UTC+9)
        from datetime import timedelta
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
        candlestick_sections.append("⚠️ 빗각 분석 시 필드 사용 규칙:")
        candlestick_sections.append("- 상승 빗각 (저점 연결):")
        candlestick_sections.append("  * 역사적 저점: 전체 데이터에서 'low' 값이 가장 낮은 지점")
        candlestick_sections.append("  * 두 번째 저점: 역사적 저점 이후 100개 캔들 후 'low' 값이 가장 낮은 지점")
        candlestick_sections.append("  * 변곡점 가격: 거래량 최대 캔들의 'low' 값 사용")
        candlestick_sections.append("- 하락 빗각 (고점 연결):")
        candlestick_sections.append("  * 역사적 고점: 전체 데이터에서 'high' 값이 가장 높은 지점")
        candlestick_sections.append("  * 두 번째 고점: 역사적 고점 이후 100개 캔들 후 'high' 값이 가장 높은 지점")
        candlestick_sections.append("  * 변곡점 가격: 거래량 최대 캔들의 'high' 값 사용")
        candlestick_sections.append("")
        candlestick_sections.append("- 1시간봉(1H) 데이터로 빗각 채널을 그릴 것 (약 950개 캔들, 최대 42일)")
        candlestick_sections.append("- 15분봉(15m) 데이터로 진입 타이밍을 포착할 것")
        candlestick_sections.append("- 시간 계산: 경과 시간(시간) = (index_현재 - index_이전) × 해당 timeframe")
        candlestick_sections.append("")
        
        for timeframe in timeframe_order:
            if timeframe in market_data.get('candlesticks', {}):
                candles = market_data['candlesticks'][timeframe]
                if candles and len(candles) > 0:
                    description = timeframe_descriptions.get(timeframe, timeframe)
                    candle_count = len(candles)
                    
                    # 원본 데이터를 복사하여 timestamp를 KST 문자열로 변환하고 인덱스 추가
                    candles_converted = []
                    for idx, candle in enumerate(candles):
                        candle_copy = copy.deepcopy(candle)
                        timestamp_ms = candle_copy.get('timestamp', 0)
                        if timestamp_ms > 0:
                            dt_utc = datetime.utcfromtimestamp(timestamp_ms / 1000)
                            dt_kst = dt_utc + timedelta(hours=9)
                            candle_copy['timestamp'] = dt_kst.strftime('%Y-%m-%d %H:%M:%S')
                        # 명시적인 인덱스 번호 추가 (0부터 시작)
                        candle_copy['index'] = idx
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
                    "text": """당신은 비트코인 선물 시장에서 양방향 트레이딩 전문가입니다. 당신의 전략은 ENTER_LONG 또는 ENTER_SHORT 진입 포인트를 식별하여 **960분(16시간) 이내** 완료되는 거래에 중점을 둡니다. 시장 방향성에 따라 롱과 숏 모두 동등하게 고려해서 데이터에 기반하여 결정할 것. 반드시 비트코인 선물 트레이딩 성공률을 높이고 수익을 극대화할 수 있는 결정을 할 것.

### 핵심 지침:
- 비트코인 선물 트레이더 전문가의 관점에서 캔들스틱 데이터와 기술적 지표를 분석하여 **비트코인 선물 트레이딩 성공률을 높이고 수익의 극대화**를 추구하는 결정을 합니다.
    1) ACTION: [ENTER_LONG/ENTER_SHORT/HOLD] : 롱으로 진입할지, 숏으로 진입할지, 홀드할지 결정
    2) POSITION_SIZE: [0.3-0.9] (HOLD 시 생략) : 포지션 진입 시 자산 대비 진입할 포지션 비율 결정. 분석 신뢰도가 높을수록 높은 비율로 진입할 것.
    3) LEVERAGE: [20-80 정수] (HOLD 시 생략) : 포지션 진입 시 사용할 레버리지 값. 분석 신뢰도가 높을수록 높은 레버리지를 사용할 것.
    4) STOP_LOSS_ROE: [0.20-1.20 소수점 2자리] (HOLD 시 생략) : 포지션 진입 시 예상 손절 라인 결정, **순수 비트코인 가격 변동률 기준 퍼센테이지로 답변하고 레버리지를 곱하지 말 것**, 빗각/빗각채널/지지선/저항선을 활용하여 설정할 것
    5) TAKE_PROFIT_ROE: [0.50-4.50 소수점 2자리] (HOLD 시 생략) : 포지션 진입 시 예상 도달 목표 라인 결정, **순수 비트코인 가격 변동률 기준 퍼센테이지로 답변하고 레버리지를 곱하지 말 것**, 빗각/빗각채널/지지선/저항선을 활용하여 설정할 것
    6) EXPECTED_MINUTES: [480-1440] : 현재 추세와 시장을 분석했을 때 목표 take_profit_roe에 도달하는데 걸리는 예상 시간 결정
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
1. **빗각 시나리오(1~12번) 최우선** - 시나리오 충족 시 (상승 빗각 6개 + 하락 빗각 6개)
2. **추세 추종 차선** - 빗각 시나리오 없고 명확한 추세 확인 시 (위치 무관)
3. **홀드** - 빗각 시나리오 없고 추세 불명확 시

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

**🥈 차선: 추세 추종 진입 (빗각 시나리오 없을 때만)**

⚠️ **핵심 원칙**: 빗각 시나리오(1~12번)가 없을 때만 추세추종 분석을 수행합니다.

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
- 빗각 시나리오(1~12번) 1개 충족 + 보조 조건 1개 이상 충족 → 빗각 시나리오로 진입
- 빗각 시나리오가 여러 개 동시 신호를 주면 → 더 강한 신호 (유효성, 보조조건 충족도 높은) 선택
- 빗각 시나리오 없고 + 추세추종 조건(롱 또는 숏 조건 2개 이상) 충족 → **더 많은 조건을 충족하는 방향으로 진입**
- 빗각 시나리오 없고 + 추세추종 조건 미충족 (양 방향 모두 2개 미만) → HOLD

**추가 필터 조건 (진입 품질 향상):**
- 15분 차트 ADX가 20 이상일 때 신호 신뢰도 증가
- 다중 시간대 일관성 점수가 60점 이상일 때 더 유리
- 극단적 변동성 구간(ATR% > 6%)에서는 신중하게 판단

### 응답 형식: (**매우중요! 반드시 꼭 아래 형식에 맞게 아래 **Trading_Decision**과 **Analysis_Details** 섹션을 포함하여 답변할 것. 다른 형식은 절대 사용 금지)
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.3-0.9] (HOLD 시 생략)
LEVERAGE: [20-80 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [0.20-1.20 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
TAKE_PROFIT_ROE: [0.50-4.50 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
EXPECTED_MINUTES: [480-1440] (HOLD 시 생략)

## ANALYSIS_DETAILS
**⚠️ 중요: HOLD, ENTER_LONG, ENTER_SHORT 어떤 결정이든 반드시 Step 1부터 Step 6까지 모든 분석을 완전히 수행하세요!**

**Step 1: 빗각 분석 (1시간봉 기준 - 상승/하락 빗각 모두 양방향 활용)**

**⚠️ 중요: 백엔드에서 이미 추출된 캔들 정보를 사용하세요! 직접 캔들을 검색하지 마세요!**

- 상승 빗각 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **low 값**, volume
  * **제공된 두 번째 저점 정보 확인**: index, 시간, **low 값**, volume  
  * **제공된 Point B 정보 확인**: index, 시간, **low 값**, volume
  * **상승 빗각 계산**: Point A의 low와 Point B의 low를 연결한 직선
  * **현재 시점의 빗각 선 위치 계산** (매우 중요!):
    → 시간당 변화율 = (Point B low - Point A low) / (Point B index - Point A index)
    → 현재 빗각 선 = Point B low + (변화율 × 경과 시간)
    → 경과 시간 = 현재 캔들 index - Point A index
  * **현재 가격 vs 빗각 선 비교** (양방향 해석):
    - 현재 가격 > 빗각 선 → 빗각 위에 위치 → 지지 확인 시 롱, 지지 붕괴 시 숏
    - 현재 가격 < 빗각 선 → 빗각 아래 위치 → 저항 확인 시 숏, 저항 돌파 시 롱
  
- 하락 빗각 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 두 번째 고점 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 Point B 정보 확인**: index, 시간, **high 값**, volume
  * **하락 빗각 계산**: Point A의 high와 Point B의 high를 연결한 직선
  * **현재 시점의 빗각 선 위치 계산** (매우 중요!):
    → 시간당 변화율 = (Point B high - Point A high) / (Point B index - Point A index)
    → 현재 빗각 선 = Point B high + (변화율 × 경과 시간)
    → 경과 시간 = 현재 캔들 index - Point A index
  * **현재 가격 vs 빗각 선 비교** (양방향 해석):
    - 현재 가격 > 빗각 선 → 빗각 위에 위치 → 지지 확인 시 롱, 지지 붕괴 시 숏
    - 현재 가격 < 빗각 선 → 빗각 아래 위치 → 저항 확인 시 숏, 저항 돌파 시 롱
  
- 15분봉 진입 타이밍: 1시간봉 빗각을 15분봉에 적용하여 정확한 진입 시점 분석
- 빗각 시나리오 확인: 12가지 빗각 시나리오 중 어떤 것이 충족되는지 명확히 판단 (상승 빗각 6개 + 하락 빗각 6개)

**Step 2: 추세 분석 (15분/1시간 차트)**
[주요 이동평균선 배열, 추세 방향성, ADX 수치 분석]

**Step 3: 모멘텀 분석**
[RSI, MACD 현재 상태 및 방향성 분석]

**Step 4: 볼륨 및 지지/저항 분석**
[거래량 상태, 주요 가격대 반응, 볼륨 프로파일 분석]

**Step 5: 진입 조건 체크**
[최우선: 12가지 빗각 시나리오 중 충족되는 것 확인 (상승 빗각 6개 + 하락 빗각 6개) → 차선: 빗각 시나리오 없을 시 추세추종 (롱 조건 5개 중 몇 개, 숏 조건 5개 중 몇 개 충족?) → 더 많은 조건 충족하는 방향으로 진입 결정 (최소 2개 이상) → 양 방향 조건 동일하거나 2개 미만이면 HOLD]

**Step 6: 리스크 평가**
[MAT 지표, 시간대 충돌, 변동성 등 안전 장치 확인]

**최종 결론:**
[위 모든 분석을 종합한 최종 trading decision 근거, 충족된 빗각 시나리오 명시, 빗각 신호 우선순위 강조]
""",
                    "cache_control": {"type": "ephemeral"}
                }
            ]

            # Opus 4.1 및 Sonnet 4.5 모델은 temperature와 top_p를 동시에 사용할 수 없음
            if self.model in ["claude-opus-4-1-20250805", "claude-sonnet-4-5-20250929"]:
                payload = {
                    "model": self.model,
                    "max_tokens": 64000,
                    "temperature": 1.0,   # Opus 4.1과 Sonnet 4.5는 temperature만 사용
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 2000  # thinking 토큰을 줄여서 text 응답에 더 많이 할당
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
                    "max_tokens": 64000,  # 전체 응답 토큰 한도
                    "temperature": 1.0,   # Extended Thinking 사용 시 반드시 1.0이어야 함
                    "top_p": 0.95,        # Extended Thinking 사용 시 0.95 이상이어야 함
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 2000  # thinking 토큰을 줄여서 text 응답에 더 많이 할당
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
            
        # 캔들스틱 요약 (AI가 쉽게 읽을 수 있는 형식) - 핵심 시간대만
        candle_summaries = market_data.get('candle_summaries', {})
        
        # 요약이 있으면 우선 표시, 없으면 원본 JSON 사용
        if candle_summaries:
            candlestick_summary = "\n\n".join([
                candle_summaries.get('15m', ''),
                candle_summaries.get('1H', ''),
                candle_summaries.get('4H', '')
            ])
        else:
            candlestick_summary = "요약 없음"
        
        # 원본 캔들스틱 데이터 (모든 시간봉)
        candlestick_raw_data = self._format_all_candlestick_data(market_data)

        # 기술적 지표에서 핵심 시간대만 포함 (12H, 1D 제외하여 토큰 절약)
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
        
        # 기술적 지표 요약 (핵심 시간대만)
        indicator_summaries = market_data.get('indicator_summaries', {})
        
        if indicator_summaries:
            indicator_summary = "\n\n".join([
                indicator_summaries.get('15m', ''),
                indicator_summaries.get('1H', ''),
                indicator_summaries.get('4H', '')
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
- 한번 포지션 진입하면 레버리지, take_profit_roe, stop_loss_roe 변경 불가능
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

**📍 사용자 지정 빗각 포인트 정보:**

{diagonal_candles_info}

**Step 1: 사용자 지정 빗각 분석 (Diagonal Line Analysis) - 가장 중요!**

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
   
   **Step 1-A-5: 추가 상승 채널 빗각 그리기 (빗각 3, 4, 5)**
   - **빗각 3**: 빗각 2에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 3 = 빗각 2 - D (수직 거리)
   - **빗각 4**: 빗각 3에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 4 = 빗각 3 - D
   - **빗각 5**: 빗각 4에서 **아래 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 5 = 빗각 4 - D
   - ⚠️ 비트코인 가격은 이 빗각들을 기준으로 움직이며, 한 빗각을 뚫으면 다음 빗각까지 이동하는 경향
   
   **Step 1-A-6: 현재 시점의 각 상승 빗각 위치 계산**
   - 경과 시간 = 현재 캔들 index - Point A index
   - **빗각 1 현재 위치** = Point A low + (slope × 경과 시간)
   - **빗각 2 현재 위치** = 빗각 1 현재 위치 - D
   - **빗각 3 현재 위치** = 빗각 2 현재 위치 - D (= 빗각 1 - 2D)
   - **빗각 4 현재 위치** = 빗각 3 현재 위치 - D (= 빗각 1 - 3D)
   - **빗각 5 현재 위치** = 빗각 4 현재 위치 - D (= 빗각 1 - 4D)
   - 보고: 각 빗각의 현재 위치 가격
   
   **Step 1-A-7: 현재 가격이 어느 채널에 위치하는지 파악**
   - 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5 아래?
   - 가장 가까운 위/아래 빗각 선 식별
   - 보고: 현재 가격의 채널 내 위치 ("빗각 2와 3 사이, 빗각 3에 가까움" 등)
   
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
   
   **Step 1-B-5: 추가 하락 채널 빗각 그리기 (빗각 3, 4, 5)**
   - **빗각 3**: 빗각 2에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 3 = 빗각 2 + D (수직 거리)
   - **빗각 4**: 빗각 3에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 4 = 빗각 3 + D
   - **빗각 5**: 빗각 4에서 **위 방향**으로 간격 D만큼 떨어진 평행선
     * 빗각 5 = 빗각 4 + D
   - ⚠️ 비트코인 가격은 이 빗각들을 기준으로 움직이며, 한 빗각을 뚫으면 다음 빗각까지 이동하는 경향
   
   **Step 1-B-6: 현재 시점의 각 하락 빗각 위치 계산**
   - 경과 시간 = 현재 캔들 index - Point A index
   - **빗각 1 현재 위치** = Point A high + (slope × 경과 시간)
   - **빗각 2 현재 위치** = 빗각 1 현재 위치 + D
   - **빗각 3 현재 위치** = 빗각 2 현재 위치 + D (= 빗각 1 + 2D)
   - **빗각 4 현재 위치** = 빗각 3 현재 위치 + D (= 빗각 1 + 3D)
   - **빗각 5 현재 위치** = 빗각 4 현재 위치 + D (= 빗각 1 + 4D)
   - 보고: 각 빗각의 현재 위치 가격
   
   **Step 1-B-7: 현재 가격이 어느 채널에 위치하는지 파악**
   - 현재 가격이 빗각 1과 2 사이? 2와 3 사이? 3과 4 사이? 4와 5 사이? 5 위?
   - 가장 가까운 위/아래 빗각 선 식별
   - 보고: 현재 가격의 채널 내 위치 ("빗각 2와 3 사이, 빗각 2에 가까움" 등)
   
**1-C. 두 빗각 종합 분석 및 진입 신호 판단:**

**⚠️ 분석 원칙:**
- 제공된 모든 빗각 분석 (상승 빗각, 하락 빗각)
- 각 빗각의 12가지 시나리오 평가
- 가장 강한 신호 선택

**분석 절차:**

1. **상승 빗각 시나리오 평가** (제공된 경우):
   - 6가지 시나리오 중 충족되는 것 확인
   - 보조 조건 충족 개수 계산
   - 현재 가격과 빗각까지 거리 확인
   
2. **하락 빗각 시나리오 평가** (제공된 경우):
   - 6가지 시나리오 중 충족되는 것 확인
   - 보조 조건 충족 개수 계산
   - 현재 가격과 빗각까지 거리 확인
   
3. **신호 종합 판단**:
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

⚠️ **우선순위**: 위 12가지 빗각 시나리오가 **최우선**입니다 (상승 빗각 6개 + 하락 빗각 6개). 12가지 시나리오에 해당하지 않으면 (현재가가 빗각 근처든 중간이든 관계없이) 아래 추세 추종 로직을 적용합니다.

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

**SL 및 TP 설정 (중요! - 리스크 리워드 비율 유지):**

**기본 원칙:**
- **리스크 리워드 비율**: 최소 1:2 (SL 1%면 TP 2%), 이상적으로는 1:3 (SL 0.5%면 TP 1.5%)
- SL 참고 빗각: 진입 방향 반대편 빗각 (롱이면 하단, 숏이면 상단)
- TP 참고 빗각: 진입 방향 쪽 빗각 (롱이면 상단, 숏이면 하단)

**SL/TP 계산 로직 (개선된 방식):**

**롱 진입 시:**
1. **TP 참고 빗각(상단)까지 거리 계산**: 
   - TP_distance_pct = (TP 빗각 가격 - 현재가) / 현재가 × 100
   
2. **SL 참고 빗각(하단)까지 거리 계산**:
   - SL_distance_pct = (현재가 - SL 빗각 가격) / 현재가 × 100
   
3. **SL/TP 설정 규칙**:
   - **케이스 A**: TP 거리가 SL 거리보다 2배 이상 (정상적인 리스크 리워드)
     - SL = SL 빗각 가격 (또는 -0.5% 추가 버퍼)
     - TP = TP 빗각 가격 (또는 -0.3% 버퍼)
     
   - **케이스 B**: TP 거리가 SL 거리보다 작음 (현재가가 상단 빗각에 매우 가까움)
     - **리스크 리워드 1:3 비율 적용**
     - TP = min(TP 빗각 거리, SL 거리 × 3)
     - SL = TP / 3
     - 예: TP 빗각이 1.66% 위에 있고 SL 빗각이 3% 아래 → TP = 1.5%, SL = 0.5%
     
   - **케이스 C**: 두 빗각 모두 너무 멀거나 가까움
     - **보수적 비율 사용**: TP = 1.5%, SL = 0.5% (1:3 비율)
     - 또는 TP = 2.0%, SL = 0.67% (1:3 비율)

**숏 진입 시:**
1. **TP 참고 빗각(하단)까지 거리 계산**:
   - TP_distance_pct = (현재가 - TP 빗각 가격) / 현재가 × 100
   
2. **SL 참고 빗각(상단)까지 거리 계산**:
   - SL_distance_pct = (SL 빗각 가격 - 현재가) / 현재가 × 100
   
3. **SL/TP 설정 규칙**:
   - **케이스 A**: TP 거리가 SL 거리보다 2배 이상 (정상적인 리스크 리워드)
     - SL = SL 빗각 가격 (또는 +0.5% 추가 버퍼)
     - TP = TP 빗각 가격 (또는 +0.3% 버퍼)
     
   - **케이스 B**: TP 거리가 SL 거리보다 작음 (현재가가 하단 빗각에 매우 가까움)
     - **리스크 리워드 1:3 비율 적용**
     - TP = min(TP 빗각 거리, SL 거리 × 3)
     - SL = TP / 3
     - 예: TP 빗각이 1.66% 아래에 있고 SL 빗각이 3% 위 → TP = 1.5%, SL = 0.5%
     
   - **케이스 C**: 두 빗각 모두 너무 멀거나 가까움
     - **보수적 비율 사용**: TP = 1.5%, SL = 0.5% (1:3 비율)
     - 또는 TP = 2.0%, SL = 0.67% (1:3 비율)

**예시 1 (롱, 빗각 근처 - 상단 빗각에 가까움):**
- 현재가: $110,000
- 빗각 2 (상단): $111,826 (TP 참고용, 거리 +1.66%)
- 빗각 3 (하단): $107,000 (SL 참고용, 거리 -2.73%)
- TP 거리(1.66%) < SL 거리(2.73%)의 2배 → **케이스 B 적용**
- **리스크 리워드 1:3 비율 적용**:
  - TP = 1.5% (목표: $111,650)
  - SL = 0.5% (손절: $109,450)

**예시 2 (롱, 채널 중간 - 정상적인 위치):**
- 현재가: $110,000 (빗각 2와 3 사이 중간)
- 빗각 2 (상단): $113,000 (TP 참고용, 거리 +2.73%)
- 빗각 3 (하단): $108,500 (SL 참고용, 거리 -1.36%)
- TP 거리(2.73%) > SL 거리(1.36%)의 2배 → **케이스 A 적용**
- SL = $108,500 (-1.36%)
- TP = $113,000 (+2.73%)

**예시 3 (숏, 빗각 근처 - 하단 빗각에 가까움):**
- 현재가: $110,000
- 빗각 2 (하단): $108,174 (TP 참고용, 거리 -1.66%)
- 빗각 3 (상단): $113,000 (SL 참고용, 거리 +2.73%)
- TP 거리(1.66%) < SL 거리(2.73%)의 2배 → **케이스 B 적용**
- **리스크 리워드 1:3 비율 적용**:
  - TP = 1.5% (목표: $108,350)
  - SL = 0.5% (손절: $110,550)

⚠️ **주의사항:**
- 이 시나리오는 빗각 시나리오(1~10번)가 없을 때만 사용
- 추세가 명확하지 않으면 HOLD
- 리스크 리워드 비율이 1:2 미만이면 진입하지 않음

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

**🚨 최우선 조건: 빗각 채널 시나리오 (12가지 빗각 시나리오 중 1개 이상 충족 시 진입 고려)**

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
- 빗각 시나리오(1~10번) 중 하나라도 충족되면 → 빗각 시나리오로 진입
- 빗각 시나리오가 없으면 → 추세 추종(Step 1-G)으로 진입 고려
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

**🥇 최우선: 빗각 시나리오 (1~10번)**
→ 빗각 채널 시나리오 1개 충족 + 보조 조건 1개 이상 충족 → **즉시 진입**
→ 빗각 채널 시나리오가 여러 개 동시 신호 → 더 강한 신호 (유효성, 보조조건 충족도 높은) 선택
→ 빗각 유효성 검증(시간 간격, 최신성, 터치 횟수) 통과 시 신뢰도 증가
→ ADX ≥ 20이면 신뢰도 증가, 다중 시간대 일관성 ≥ 60점이면 더욱 유리

**🥈 차선: 추세 추종 진입 (빗각 시나리오 미충족 시)**
→ 빗각 시나리오(1~10번) **없을 때만** 적용
→ 롱 조건 5개 중 2개 이상 충족 또는 숏 조건 5개 중 2개 이상 충족 확인
→ **더 많은 조건을 충족하는 방향으로 진입**
→ 예: 롱 조건 3개, 숏 조건 2개 → 롱 진입
→ SL/TP는 리스크 리워드 비율(1:2 또는 1:3) 유지 (Step 1-G 참고)
→ 빗각까지 거리를 고려하여 SL/TP 설정 (예: TP 빗각 1.66%면 TP=1.5%, SL=0.5%)
→ 리스크 리워드 비율이 1:2 미만이면 진입하지 않음

**🥉 홀드: 조건 미충족**
→ 빗각 시나리오 없고 + 양 방향 모두 조건 2개 미만 → **HOLD**
→ 빗각 시나리오 없고 + 리스크 리워드 비율 1:2 미만 → **HOLD**

**Step 4: 손익 목표 설정 (채널 빗각 기반)**

**1. Stop Loss (SL) 설정 - 현재 진입 기준 빗각 활용:**
   - **상승 빗각 돌파 후 지지 (롱)**: SL = 진입 기준 빗각(예: 빗각 2) -0.5%
   - **상승 빗각 리테스트 실패 (숏)**: SL = 진입 기준 빗각(예: 빗각 2) +0.5%
   - **상승 빗각 저항 (숏)**: SL = 진입 기준 빗각(예: 빗각 2) +0.5%
   - **하락 빗각 하향 돌파 후 저항 확인 (숏)**: SL = 진입 기준 빗각(예: 빗각 2) +0.5%
   - **하락 빗각 하향 돌파 후 리테스트 실패 (롱)**: SL = 진입 기준 빗각(예: 빗각 2) -0.5%
   - **하락 빗각 지지 (롱)**: SL = 진입 기준 빗각(예: 빗각 2) -0.5%
   - **추세 추종 (롱)**: Step 1-G 참고 - 리스크 리워드 비율 1:3 유지 (예: SL 0.5%, TP 1.5%)
   - **추세 추종 (숏)**: Step 1-G 참고 - 리스크 리워드 비율 1:3 유지 (예: SL 0.5%, TP 1.5%)
   - **⚠️ 추세 추종 설정**: 빗각까지 거리 고려, TP 빗각 1.66%면 TP=1.5% SL=0.5% (1:3 비율)
   - **SL-ROE 계산**: ((진입가 - SL가격) / 진입가) × 레버리지 × 100

**2. Take Profit (TP) 설정 - 다음 채널 빗각 활용:**
   - **롱 진입 시 (기본)**: TP = 다음 상위 빗각(예: 빗각 1) 근처 -0.3% (빗각 직전에서 이익 실현)
   - **숏 진입 시 (기본)**: TP = 다음 하위 빗각(예: 빗각 3) 근처 +0.3% (빗각 직전에서 이익 실현)
   - **추세 추종 (롱)**: Step 1-G 참고 - 리스크 리워드 비율 1:3 유지 (예: TP 1.5%, SL 0.5%)
   - **추세 추종 (숏)**: Step 1-G 참고 - 리스크 리워드 비율 1:3 유지 (예: TP 1.5%, SL 0.5%)
   - **⚠️ 추세 추종 TP/SL**: 빗각 거리 고려하여 1:2~1:3 비율 유지, 비율 미달 시 진입 포기
   - **TP-ROE 계산**: ((TP가격 - 진입가) / 진입가) × 레버리지 × 100
   - **채널 간격 고려**: 채널 간격(D)이 크면 TP-ROE도 크게 설정

**3. 레버리지 결정:**
   - 분석 신뢰도가 높을수록 높은 레버리지 설정

**4. 예상 도달 시간 (expected_minutes):**
   - 채널 간격과 최근 가격 변동 속도를 고려하여 계산
   - 다음 빗각까지의 거리와 시간당 평균 변동폭 기반
   - 권장 범위: 480-960분 (8-16시간)

**Step 5: 최종 확인**

**🎯 진입 우선순위 (반드시 준수):**
1. **빗각 시나리오(1~12번) 최우선**: 시나리오 충족 + 보조 조건 1개 이상 → 즉시 진입 (상승 빗각 6개 + 하락 빗각 6개)
2. **추세 추종 차선**: 빗각 시나리오 없고 + 명확한 추세 + 보조 조건 2개 이상 → 진입 고려
3. **홀드**: 빗각 시나리오 없고 + (추세 불명확 또는 보조 조건 부족) → HOLD

**🔍 재확인 체크리스트:**
- 빗각 유효성 재확인 (시간 간격 10개 이상, Point A가 100개 이내)
- 포지션 크기: 신뢰도에 따라 0.3-0.9 (빗각 시나리오+보조조건 많이 충족 시 증가)
- 레버리지: 분석 신뢰도에 따라 20-80배

**📌 추세 추종 특별 확인 (Step 1-G 참고):**
- 빗각 시나리오(1~12번) 충족 여부 재확인 → 충족되면 추세 추종 사용 안 함
- 롱 조건 5개 중 몇 개 충족? 숏 조건 5개 중 몇 개 충족? → 각각 2개 미만이면 HOLD
- **더 많은 조건을 충족하는 방향으로 진입** (예: 롱 3개, 숏 2개 → 롱 진입)
- 양 방향 조건이 동일하면 (예: 롱 2개, 숏 2개) → HOLD (명확한 방향성 없음)
- 리스크 리워드 비율 1:2 이상 유지 가능한가? → 미만이면 진입 포기
- 빗각까지 거리 고려한 SL/TP 설정 (예: TP 빗각 1.66%면 TP=1.5%, SL=0.5%)

### 응답 형식: (**매우중요! 반드시 꼭 아래 형식에 맞게 아래 **Trading_Decision**과 **Analysis_Details** 섹션을 포함하여 답변할 것. 다른 형식은 절대 사용 금지)
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.3-0.9] (HOLD 시 생략)
LEVERAGE: [20-80 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [0.20-1.20 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
TAKE_PROFIT_ROE: [0.50-4.50 소수점 2자리, 레버리지를 곱하지 말 것] (HOLD 시 생략)
EXPECTED_MINUTES: [480-1440] (HOLD 시 생략)

## ANALYSIS_DETAILS
**⚠️ 중요: HOLD, ENTER_LONG, ENTER_SHORT 어떤 결정이든 반드시 Step 1부터 Step 6까지 모든 분석을 완전히 수행하세요!**

**Step 1: 빗각 분석 (1시간봉 기준 - 상승/하락 빗각 모두 양방향 활용)**

**⚠️ 중요: 백엔드에서 이미 추출된 캔들 정보를 사용하세요! 직접 캔들을 검색하지 마세요!**

- 상승 빗각 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **low 값**, volume
  * **제공된 두 번째 저점 정보 확인**: index, 시간, **low 값**, volume  
  * **제공된 Point B 정보 확인**: index, 시간, **low 값**, volume
  * **상승 빗각 계산**: Point A의 low와 Point B의 low를 연결한 직선
  * **현재 시점의 빗각 선 위치 계산** (매우 중요!):
    → 시간당 변화율 = (Point B low - Point A low) / (Point B index - Point A index)
    → 현재 빗각 선 = Point B low + (변화율 × 경과 시간)
    → 경과 시간 = 현재 캔들 index - Point A index
  * **현재 가격 vs 빗각 선 비교** (양방향 해석):
    - 현재 가격 > 빗각 선 → 빗각 위에 위치 → 지지 확인 시 롱, 지지 붕괴 시 숏
    - 현재 가격 < 빗각 선 → 빗각 아래 위치 → 저항 확인 시 숏, 저항 돌파 시 롱
  
- 하락 빗각 분석 (사용자가 설정한 경우):
  * **제공된 Point A 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 두 번째 고점 정보 확인**: index, 시간, **high 값**, volume
  * **제공된 Point B 정보 확인**: index, 시간, **high 값**, volume
  * **하락 빗각 계산**: Point A의 high와 Point B의 high를 연결한 직선
  * **현재 시점의 빗각 선 위치 계산** (매우 중요!):
    → 시간당 변화율 = (Point B high - Point A high) / (Point B index - Point A index)
    → 현재 빗각 선 = Point B high + (변화율 × 경과 시간)
    → 경과 시간 = 현재 캔들 index - Point A index
  * **현재 가격 vs 빗각 선 비교** (양방향 해석):
    - 현재 가격 > 빗각 선 → 빗각 위에 위치 → 지지 확인 시 롱, 지지 붕괴 시 숏
    - 현재 가격 < 빗각 선 → 빗각 아래 위치 → 저항 확인 시 숏, 저항 돌파 시 롱
  
- 15분봉 진입 타이밍: 1시간봉 빗각을 15분봉에 적용하여 정확한 진입 시점 분석
- 빗각 시나리오 확인: 12가지 빗각 시나리오 중 어떤 것이 충족되는지 명확히 판단 (상승 빗각 6개 + 하락 빗각 6개)

**Step 2: 추세 분석 (15분/1시간 차트)**
[주요 이동평균선 배열, 추세 방향성, ADX 수치 분석]

**Step 3: 모멘텀 분석**
[RSI, MACD 현재 상태 및 방향성 분석]

**Step 4: 볼륨 및 지지/저항 분석**
[거래량 상태, 주요 가격대 반응, 볼륨 프로파일 분석]

**Step 5: 진입 조건 체크**
[최우선: 12가지 빗각 시나리오 중 충족되는 것 확인 (상승 빗각 6개 + 하락 빗각 6개) → 차선: 빗각 시나리오 없을 시 추세추종 (롱 조건 5개 중 몇 개, 숏 조건 5개 중 몇 개 충족?) → 더 많은 조건 충족하는 방향으로 진입 결정 (최소 2개 이상) → 양 방향 조건 동일하거나 2개 미만이면 HOLD]

**Step 6: 리스크 평가**
[MAT 지표, 시간대 충돌, 변동성 등 안전 장치 확인]

**최종 결론:**
[위 모든 분석을 종합한 최종 trading decision 근거, 충족된 빗각 시나리오 명시, 빗각 신호 우선순위 강조]

심호흡하고 차근차근 생각하며 확률값에 기반하여 분석을 진행해"""

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
            # ⚠️ 중요: ANALYSIS_DETAILS 이후 모든 내용을 가져옴 (다른 섹션에서 멈추지 않음)
            analysis_patterns = [
                r'##\s*[🔍📊🎯💡]*\s*ANALYSIS_DETAILS\s*\n(.+)',  # ## ANALYSIS_DETAILS 이후 끝까지
                r'###\s*ANALYSIS_DETAILS\s*\n(.+)',                # ### 형태도 지원
                r'ANALYSIS_DETAILS\s*\n(.+)'                       # 기본 형태 (이후 끝까지)
            ]
            
            for pattern in analysis_patterns:
                match = re.search(pattern, original_response, re.DOTALL | re.IGNORECASE)
                if match:
                    reason = match.group(1).strip()
                    print(f"ANALYSIS_DETAILS 섹션 추출 성공 (길이: {len(reason)}, 패턴: {pattern[:40]})")
                    if reason and len(reason) > 50:  # 의미있는 내용인 경우에만 사용 (최소 50자)
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
