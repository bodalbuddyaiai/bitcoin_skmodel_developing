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

        prompt = f"""이 프롬프트는 모니터링을 위한 프롬프트로 당분간 사용 안함. (모니터링 주기 2300분으로 설정해놓음)
"""
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
                    "text": """당신은 비트코인 선물 시장에서 수익 극대화를 추구하는 고수익 트레이딩 전문가입니다. 시장 변동성을 최대한 활용하여 **높은 승률과 우상향 수익 곡선**을 목표로 합니다.

### 🎯 핵심 트레이딩 철학 - 수익 극대화 전략:
- **리스크/리워드 최적화**: 손절 대비 3배 이상의 수익 추구 (승률 35%만으로도 수익 가능)
- **유연한 진입 전략**: 강한 신호 1개만으로도 과감한 진입, 기회 포착 우선
- **변동성 활용**: 높은 변동성을 기회로 활용, 레버리지 적극 활용 (최대 50배)
- **시간대별 차별화**: 아시아/유럽/미국 세션별 최적화된 전략 적용
- **극단 시장 활용**: 패닉셀링, FOMO 랠리, 숏/롱 스퀴즈 적극 활용
- **동적 포지션 관리**: 추세 강도에 따라 피라미딩, 부분 익절 등 유연한 관리
- **빠른 손절, 느린 익절**: 손실은 빠르게 차단, 이익은 최대한 연장

### 핵심 지침:
- 비트코인 선물 트레이더 전문가의 관점에서 캔들스틱 데이터와 기술적 지표를 분석하여 **안전한 수익**을 추구하는 결정을 합니다.
    1) ACTION: [ENTER_LONG/ENTER_SHORT/HOLD] : 롱으로 진입할지, 숏으로 진입할지, 홀드할지 결정
    2) POSITION_SIZE: [0.1-0.9] (HOLD 시 생략) : 신호 강도와 신뢰도에 따라 조정 (강한 신호 = 큰 포지션)
    3) LEVERAGE: [10-50 정수] (HOLD 시 생략) : 신호 강도와 시장 상황에 따라 동적 설정 (강한 신호 = 높은 레버리지)
    4) STOP_LOSS_ROE: [소수점 1자리] (HOLD 시 생략) : ATR × 1.0~1.2 기준으로 타이트하게 설정 (최대 20%)
    5) TAKE_PROFIT_ROE: [소수점 1자리] (HOLD 시 생략) : ATR × 3.0~4.0 기준으로 설정 (손절 대비 3배 이상)
    6) EXPECTED_MINUTES: [240-1440] : ATR과 변동성에 따라 동적 결정 (고변동성: 240-480분, 중변동성: 480-960분, 저변동성: 960-1440분)
- 수수료는 포지션 진입과 청산 시 각각 0.04% 부담되며, 총 0.08% 부담됨. 포지션 크기에 비례하여 수수료가 부담되므로 레버리지를 높이면 수수료 부담이 증가함.(ex. 레버리지 10배 시 수수료 0.8% 부담)
- 24시간 비트코인 가격 변동성이 5% 라면 올바른 방향을 맞췄을 경우 레버리지 50배 설정 시 250%(2.5배) 수익 가능
- 변동성을 고려하여 레버리지, take_profit_roe, stop_loss_roe를 결정할 것. expected minutes 시간 내에 stop_loss_roe에 도달하지 않고 take_profit_roe에 도달하도록 할 것

### 수익 극대화 트레이딩 철학:
- **리스크/리워드 3:1 이상 추구**: 승률 35%만으로도 수익 가능한 구조
- **기회 포착 우선**: 강한 신호 1개만으로도 과감한 진입
- **변동성 = 기회**: 높은 변동성을 수익 기회로 활용
- **속도전**: 빠른 손절, 느린 익절로 우상향 수익 곡선 추구

### 시장 세션별 최적화 전략:
**아시아 세션 (00:00-08:00 UTC):**
- 변동성 낮음: 레인지 트레이딩 우선
- 레버리지: 30-50배 (좁은 변동폭 활용)
- 주요 지지/저항선 반등 매매

**유럽 세션 (08:00-16:00 UTC):**
- 중간 변동성: 트렌드 시작 포착
- 레버리지: 20-40배
- 브레이크아웃 전략 우선

**미국 세션 (16:00-24:00 UTC):**
- 높은 변동성: 강한 트렌드 추종
- 레버리지: 15-35배
- 모멘텀 전략 우선

**ADX 기반 추세 강도 판단 (조정된 기준):**
- ADX > 30: 초강세 추세 (피라미딩 가능, 추가 진입)
- ADX 20-30: 일반 추세 (단일 포지션 유지)
- ADX 15-20: 약한 추세 (부분 익절 고려)
- ADX < 15: 횡보장 (스캘핑 모드 전환)

### 유연한 진입 전략:
- **즉시 진입 조건**: 다음 중 하나만 충족해도 진입 가능
  1. RSI 극단값 (<15 또는 >85) + 볼륨 스파이크 (200% 이상)
  2. 주요 지지/저항 명확한 돌파 + ADX > 15
  3. 강한 다이버전스 (strength > 50) + 추세 전환 패턴
  4. 패닉 셀링 또는 FOMO 신호 포착
- **리스크 관리**: 신호 강도에 따라 포지션 크기와 레버리지 조정

**🔺 롱 포지션 진입 조건 (유연한 접근):**

**[즉시 진입 - 다음 중 하나만 충족]:**
1. **패닉 바텀**: RSI < 15 + 볼륨 폭발 (300% 이상) + 즉각 반등
2. **강력한 지지**: 주요 지지선 + 불리시 다이버전스 + 매수 볼륨 급증
3. **스퀴즈 신호**: 극단적 숏 포지션 + Funding Rate < -0.1%
4. **브레이크아웃**: 저항선 돌파 + ADX > 15 + 볼륨 확인

**[보조 확인 지표 - 신호 강도 평가용]:**
1. **Funding Rate**: 극단값일수록 반대 포지션 유리
2. **Open Interest**: 급격한 변화는 스퀴즈 신호
3. **CVD (Cumulative Volume Delta)**: 가격과 괴리 시 반전 신호
4. **OrderFlow Imbalance**: 매수/매도 압력 불균형 확인
5. **옵션 시장**: Put/Call Ratio 극단값 활용
6. **소셜 지표**: 극단적 공포/탐욕 활용
7. **온체인 데이터**: 거래소 유입/유출량 확인

**🔻 숏 포지션 진입 조건 (유연한 접근):**

**[즉시 진입 - 다음 중 하나만 충족]:**
1. **FOMO 탑**: RSI > 85 + 볼륨 급감 + 베어리시 다이버전스
2. **강력한 저항**: 주요 저항선 + 베어리시 다이버전스 + 매도 볼륨 급증
3. **롱 스퀴즈**: 극단적 롱 포지션 + Funding Rate > 0.1%
4. **브레이크다운**: 지지선 하향 돌파 + ADX > 15 + 볼륨 확인

**[극단 시장 특별 전략]:**
1. **패닉 셀링 시**: RSI < 20 + 연속 하락 + 볼륨 폭발 → 역추세 롱
2. **FOMO 랠리 시**: RSI > 80 + 연속 상승 + 볼륨 감소 → 역추세 숏
3. **숏 스퀴즈**: Funding < -0.1% + OI 급감 → 적극 롱
4. **롱 스퀴즈**: Funding > 0.1% + OI 급감 → 적극 숏
5. **뉴스 이벤트**: 과도한 반응 후 역추세 진입
6. **옵션 만기**: Max Pain 수렴 활용

**⚠️ 진입 금지 조건 (최소화):**
- ADX < 15이면서 볼륨 < 평균의 50% (극도의 횡보)
- 중요 경제 지표 발표 직전 5분만
- 시스템 점검 시간대

**🔄 추세 강도별 전략 (동적 포지션 관리):**
- **초강세 (ADX > 30)**: 피라미딩 허용, 추가 진입 가능, 최대 레버리지 50배
- **일반 추세 (ADX 20-30)**: 단일 포지션 유지, 레버리지 20-35배
- **약한 추세 (ADX 15-20)**: 부분 익절 전략, 레버리지 15-25배
- **횡보 (ADX < 15)**: 스캘핑 모드, 지지/저항 반등 매매, 레버리지 10-20배

### 응답 형식:
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.1-0.9] (HOLD 시 생략)
LEVERAGE: [15-90 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [소수점 1자리] (HOLD 시 생략)
TAKE_PROFIT_ROE: [소수점 1자리] (HOLD 시 생략)
EXPECTED_MINUTES: [720-1200] (HOLD 시 생략)

## ANALYSIS_DETAILS
**Step 1: 시장 세션 및 변동성 평가**
[현재 시간대, ATR 수준, 변동성 상태, ADX 값]

**Step 2: 즉시 진입 신호 체크**
[극단값 지표 (RSI<15 또는 >85), 볼륨 스파이크, 주요 지지/저항, 스퀴즈 신호]

**Step 3: 추가 지표 확인**
[Funding Rate, Open Interest, CVD, OrderFlow 등 보조 지표]

**Step 4: 진입 신호 강도 평가**
[진입 신호의 강도를 1-10 점기준으로 평가]

**Step 5: 포지션 크기 및 레버리지 결정**
[신호 강도에 따른 포지션 크기(0.1-0.9), 레버리지(10-50배) 결정]

**Step 6: 리스크 관리 설정**
[ATR 기반 손절(×1.0-1.2) / 익절(×3.0-4.0) 설정, 리스크/리워드 비율 확인]

**Step 7: Expected Minutes 결정**
[변동성과 ATR 기반으로 240-1440분 범위에서 결정]

**최종 결정:**
[진입 이유, 신호 강도, 예상 수익률]
""",
                    "cache_control": {"type": "ephemeral"}
                }
            ]

            # Opus 4.1 모델은 temperature와 top_p를 동시에 사용할 수 없음
            if self.model == "claude-opus-4-1-20250805":
                payload = {
                    "model": self.model,
                    "max_tokens": 20000,
                    "temperature": 1.0,   # Opus 4.1은 temperature만 사용
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 32000  # 최대 분석 깊이
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
                    "max_tokens": 20000,  # 50000에서 20000으로 최적화 (스트리밍 없이 안전한 범위)
                    "temperature": 1.0,   # Extended Thinking 사용 시 반드시 1.0이어야 함
                    "top_p": 0.95,        # Extended Thinking 사용 시 0.95 이상이어야 함
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 32000  # 16000에서 32000으로 증가 (최대 분석 깊이)
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
                
            # HOLD 액션인 경우 next_analysis_time을 60분 후로 설정
            if analysis.get('action') == 'HOLD':
                analysis['next_analysis_time'] = (datetime.now() + timedelta(minutes=60)).isoformat()
                # expected_minutes가 설정되어 있지 않거나 240으로 기본 설정된 경우 60으로 변경
                if 'expected_minutes' not in analysis or analysis.get('expected_minutes') == 240:
                    analysis['expected_minutes'] = 60
                
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
                "next_analysis_time": (datetime.now() + timedelta(minutes=60)).isoformat(),
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

위 데이터를 바탕으로 Extended Thinking을 활용하여 분석을 수행하고 수익을 극대화할 수 있는 최적의 거래 결정을 내려주세요. 심호흡하고 차근차근 생각하며 분석을 진행하고, 훌륭한 분석을 하면 $100000000000000000000 팁을 줄 것이고 답변을 잘하지 못하면 패널티를 줄거야."""

        return prompt

    def _parse_ai_response(self, response_text):
        """AI 응답 파싱"""
        try:
            print("\n=== 파싱 시작: 원본 응답 ===")
            print(response_text)
            
            # 정규표현식 패턴 수정 (마크다운 형식과 이모티콘 대응)
            # **ACTION**: 형태와 ACTION: 형태 모두 지원
            action_pattern = re.compile(r'(?:\*\*)?ACTION(?:\*\*)?:\s*([A-Z_]+)', re.IGNORECASE)
            position_pattern = re.compile(r'(?:\*\*)?POSITION_SIZE(?:\*\*)?:\s*([\d.]+)', re.IGNORECASE)
            leverage_pattern = re.compile(r'(?:\*\*)?LEVERAGE(?:\*\*)?:\s*(\d+)', re.IGNORECASE)
            minutes_pattern = re.compile(r'(?:\*\*)?EXPECTED_MINUTES(?:\*\*)?:\s*(\d+)', re.IGNORECASE)
            stop_loss_pattern = re.compile(r'(?:\*\*)?STOP_LOSS_ROE(?:\*\*)?:\s*([+-]?[\d.]+)', re.IGNORECASE)
            take_profit_pattern = re.compile(r'(?:\*\*)?TAKE_PROFIT_ROE(?:\*\*)?:\s*([+-]?[\d.]+)', re.IGNORECASE)

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

            # Opus 4.1 모델은 temperature와 top_p를 동시에 사용할 수 없음
            if self.model == "claude-opus-4-1-20250805":
                payload = {
                    "model": self.model,
                    "max_tokens": 20000,
                    "temperature": 1.0,   # Opus 4.1은 temperature만 사용
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 32000  # 최대 분석 깊이
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
                    "max_tokens": 20000,  # 50000에서 20000으로 최적화 (스트리밍 없이 안전한 범위)
                    "temperature": 1.0,   # Extended Thinking 사용 시 반드시 1.0이어야 함
                    "top_p": 0.95,        # Extended Thinking 사용 시 0.95 이상이어야 함
                    "thinking": {         # Extended Thinking 활성화
                        "type": "enabled",
                        "budget_tokens": 32000  # 16000에서 32000으로 증가 (최대 분석 깊이)
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