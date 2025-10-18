from openai import OpenAI
import json
import time
import numpy as np
from datetime import datetime, date, timedelta
from config.settings import OPENAI_API_KEY
import re

class OpenAIService:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.assistant_id = "asst_uEs555PIWD31LYyoSNgt0nTf"
        self.monitoring_interval = 240  # 기본 모니터링 주기 (4시간)

    def initialize_thread(self):
        """이제 메서드마다 새 스레드가 생성되므로 이 메서드는 필요 없음"""
        print("각 분석마다 새 스레드가 자동으로 생성됩니다.")
        return True

    def reset_thread(self):
        """이제 메서드마다 새 스레드가 생성되므로 이 메서드는 필요 없음"""
        print("각 분석마다 새 스레드가 자동으로 생성됩니다.")

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

12시간봉 데이터:
{json.dumps(market_data['candlesticks'].get('12H', [])[-50:], indent=2)}

일봉 데이터:
{json.dumps(market_data['candlesticks'].get('1D', [])[-30:], indent=2)}

주봉 데이터:
{json.dumps(market_data['candlesticks'].get('1W', [])[-13:], indent=2)}

월봉 데이터:
{json.dumps(market_data['candlesticks'].get('1M', [])[-4:], indent=2)}
"""

        # 기술적 지표에서 모든 시간대 포함 (3m, 30m, 6H, 3D 제외 - 토큰 절약)
        all_timeframes = ['1m', '5m', '15m', '1H', '4H', '12H', '1D', '1W', '1M']
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

    def _format_candlestick_data(self, candlesticks):
        """캔들스틱 데이터 포맷팅"""
        formatted_data = ""
        for timeframe, data in candlesticks.items():
            if timeframe in ['1m', '5m', '15m', '1H', '1D']:
                formatted_data += f"\n{timeframe} 데이터:\n"
                formatted_data += json.dumps(data[-100:], indent=2)  # 최근 100개 캔들만 표시
        return formatted_data

    async def analyze_market_data(self, market_data):
        """시장 데이터 분석 및 트레이딩 판단"""
        run = None
        thread_id = None
        
        try:
            print("\n=== OpenAI API 분석 시작 ===")
            start_time = time.time()
            
            # 매번 새로운 스레드 생성
            thread = self.client.beta.threads.create()
            thread_id = thread.id
            print(f"새 스레드 생성됨: {thread_id}")

            # 2. 메시지 생성 (데이터 포맷팅)
            message_content = self._create_analysis_prompt(market_data)

            # 3. 스레드에 메시지 추가
            message = self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message_content
            )
            print(f"메시지 추가됨: {message.id}")

            # 4. 분석 실행
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant_id
            )
            print(f"분석 실행 시작됨: {run.id}")

            # 5. 실행 완료 대기
            run = self._wait_for_run(thread_id, run.id)

            # 6. 응답 받기
            messages = self.client.beta.threads.messages.list(thread_id=thread_id)
            
            # 7. 응답 파싱
            if not messages.data:
                raise Exception("응답 메시지가 없습니다.")
                
            print(f"응답 메시지 수신됨: {messages.data[0].id}")
            analysis = self._parse_ai_response(messages.data[0].content[0].text.value)
            
            # 8. 응답 출력 추가
            print("\n=== 파싱 시작: 원본 응답 ===")
            print(messages.data[0].content[0].text.value)

            # 9. expected_minutes가 10분 미만인 경우 30분으로 설정
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
                
            # HOLD 액션인 경우 next_analysis_time을 60분 후로 설정 (기존 7분에서 변경)
            if analysis.get('action') == 'HOLD':
                analysis['next_analysis_time'] = (datetime.now() + timedelta(minutes=60)).isoformat()
                # expected_minutes가 설정되어 있지 않거나 240으로 기본 설정된 경우 60으로 변경 (기존 7에서 변경)
                if 'expected_minutes' not in analysis or analysis.get('expected_minutes') == 240:
                    analysis['expected_minutes'] = 60
                
            # 총 소요 시간 계산 및 로깅
            elapsed_time = time.time() - start_time
            print(f"분석 완료: 총 소요 시간 {elapsed_time:.2f}초")

            return analysis

        except Exception as e:
            print(f"Error in market analysis: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 오류 유형에 따른 상세 메시지 생성
            error_type = type(e).__name__
            error_detail = str(e)
            error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 오류 상세 정보 로깅
            print(f"[{error_time}] {error_type}: {error_detail}")
            
            # 스레드와 실행 정보 로깅
            thread_info = f"Thread ID: {thread_id if thread_id else 'None'}"
            run_info = f"Run ID: {run.id if run else 'None'}"
            print(f"API 호출 정보: {thread_info}, {run_info}")
            
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
                    "time": error_time,
                    "thread_id": thread_id if thread_id else None,
                    "run_id": run.id if run else None
                }
            }

    def _wait_for_run(self, thread_id, run_id, max_retries=5, timeout=300):
        """실행 완료 대기 (재시도 로직, 타임아웃, 로깅 개선)"""
        retries = 0
        start_time = time.time()
        last_status = None
        backoff_factor = 1.5  # 지수 백오프를 위한 계수
        
        while True:
            # 타임아웃 체크
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                print(f"타임아웃 발생: {elapsed_time:.2f}초 경과 (제한: {timeout}초)")
                raise Exception(f"Assistant run timed out after {timeout} seconds")
                
            try:
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run_id
                )
                
                # 상태 변경 로깅
                if run.status != last_status:
                    print(f"Assistant run 상태 변경: {last_status} -> {run.status} (경과 시간: {elapsed_time:.2f}초)")
                    last_status = run.status
                
                if run.status == 'completed':
                    print(f"Assistant run 완료됨: {run.id} (총 소요 시간: {elapsed_time:.2f}초)")
                    return run
                elif run.status == 'failed':
                    if retries < max_retries:
                        retries += 1
                        wait_time = 2 * (backoff_factor ** retries)  # 지수 백오프 적용
                        print(f"Assistant run failed, 재시도 중... ({retries}/{max_retries}) - {wait_time:.2f}초 후 재시도")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"최대 재시도 횟수 초과: {max_retries}회")
                        raise Exception(f"Assistant run failed after {max_retries} retries")
                elif run.status == 'requires_action':
                    print(f"Assistant run requires action: {run.id}")
                    # 필요한 경우 여기에 action 처리 로직 추가
                    time.sleep(1)
                else:
                    # 기타 상태 (in_progress, queued 등)
                    # 30초마다 현재 상태 로깅
                    if elapsed_time % 30 < 1:
                        print(f"현재 상태: {run.status}, 경과 시간: {elapsed_time:.2f}초")
                    time.sleep(1)
                
            except Exception as e:
                if retries < max_retries:
                    retries += 1
                    wait_time = 2 * (backoff_factor ** retries)  # 지수 백오프 적용
                    print(f"API 호출 중 오류 발생, 재시도 중... ({retries}/{max_retries}): {str(e)} - {wait_time:.2f}초 후 재시도")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"API 호출 최대 재시도 횟수 초과: {max_retries}회")
                    raise Exception(f"API 호출 실패: {str(e)}")

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

        prompt = f"""당신은 비트코인 선물 트레이더이자 비트코인 투자전문가입니다. 주어진 캔들스틱 데이터와 기술적 지표 분석을 통해 수익을 극대화할 수 있는 결정을 합니다.

### 핵심지침:
- 비트코인 선물 트레이더 전문가의 관점에서 캔들스틱 데이터와 기술적 지표를 분석하여 수익을 극대화할 수 있는 결정을 합니다.
    1) ACTION: [ENTER_LONG/ENTER_SHORT/HOLD] : 롱으로 진입할지, 숏으로 진입할지, 홀드할지 결정
    2) POSITION_SIZE: [0.1-0.9] (HOLD 시 생략) : 포지션 진입 시 포지션 크기 결정(0.5 선택 시 포지션 크기 전체 자산의 50%로 진입)
    3) LEVERAGE: [15-90 정수] (HOLD 시 생략) : Take_Profit_ROE에 도달하는데 필요한 레버리지 결정
    4) STOP_LOSS_ROE: [소수점 1자리] (HOLD 시 생략) : 포지션 진입 시 예상 손절 라인 결정(위에서 결정한 레버리지를 계산에 적용하기 때문에 결국 진입 포시젼 사이즈의 순수 손절 % 비율임)
    5) TAKE_PROFIT_ROE: [소수점 1자리] (HOLD 시 생략) : 포지션 진입 시 예상 도달 목표 라인 결정(위에서 결정한 레버리지를 계산에 적용하기 때문에 결국 진입 포지션 사이즈의 순수 목표 % 비율임)
    6) EXPECTED_MINUTES: [720] : 현재 추세와 시장을 분석했을 때 목표 take_profit_roe에 도달하는데 걸리는 예상 시간 결정(당분간 720분으로 고정)
- 횡보 시장 상황이거나 진입 시점이 모호한 경우 홀드 결정

### 현재 시스템 동작원리:
- 한번 포지션 진입하면 부분 청산, 추가 진입 불가능
- 한번 포지션 진입하면 중간에 take_profit_roe, stop_loss_roe, 레버리지, 포지션 비율 모두 변경 불가
- take_profit_roe, stop_loss_roe에 도달하면 자동으로 익절/손절 청산되며, 청산 30분 후 재분석 수행하여 다시 포지션 진입 결정
- HOLD 할 경우 30분 후 재분석 수행하여 다시 포지션 진입 결정
- expected minutes 동안 포지션 유지되면 강제 포지션 청산 후 30분 후 재분석 수행하여 다시 포지션 진입 결정

**현재 시장 상태:**
- 현재가: {market_data['current_market']['price']} USDT
- 24시간 고가: {market_data['current_market']['24h_high']} USDT
- 24시간 저가: {market_data['current_market']['24h_low']} USDT
- 24시간 거래량: {market_data['current_market']['24h_volume']} BTC
- 24시간 변동성: {round(((market_data['current_market']['24h_high'] - market_data['current_market']['24h_low']) / market_data['current_market']['24h_low']) * 100, 2)}%

**제공 데이터 (Scalping Priority Order):**
1. Candlestick Data
- index[0] : Milliseconds format of timestamp Unix
- index[1] : Entry price
- index[2] : Highest price
- index[3] : Lowest price
- index[4] : Exit price. The latest exit price may be updated in the future. Subscribe to WebSocket to track the latest price.
- index[5] : Trading volume of the base coin
- index[6] : Trading volume of quote currency
{candlestick_data}

2. Technical Indicators:
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

### 응답 형식:
## TRADING_DECISION
ACTION: [ENTER_LONG/ENTER_SHORT/HOLD]
POSITION_SIZE: [0.1-1.0] (HOLD 시 생략)
LEVERAGE: [10-100 정수] (HOLD 시 생략)
STOP_LOSS_ROE: [소수점 1자리] (HOLD 시 생략)
TAKE_PROFIT_ROE: [소수점 1자리] (HOLD 시 생략)
EXPECTED_MINUTES: [정수] (HOLD 시 생략)

## ANALYSIS_DETAILS
**분석 결과:**
"""

        return prompt

    def _parse_ai_response(self, response_text):
        """AI 응답 파싱"""
        try:
            print("\n=== 파싱 시작: 원본 응답 ===")
            print(response_text)
            
            # 정규표현식 패턴 수정 (새로운 응답 형식 대응)
            action_pattern = re.compile(r'ACTION:\s*([A-Z_]+)', re.IGNORECASE)
            position_pattern = re.compile(r'POSITION_SIZE:\s*([\d.]+)', re.IGNORECASE)
            leverage_pattern = re.compile(r'LEVERAGE:\s*(\d+)', re.IGNORECASE)
            minutes_pattern = re.compile(r'EXPECTED_MINUTES:\s*(\d+)', re.IGNORECASE)
            stop_loss_pattern = re.compile(r'STOP_LOSS_ROE:\s*([\d.]+)', re.IGNORECASE)
            take_profit_pattern = re.compile(r'TAKE_PROFIT_ROE:\s*([\d.]+)', re.IGNORECASE)

            # TRADING_DECISION 섹션 추출
            trading_decision = ""
            original_response = response_text  # 원본 응답 저장
            if "### TRADING_DECISION" in response_text:
                sections = response_text.split("###")
                for section in sections:
                    if section.strip().startswith("TRADING_DECISION"):
                        trading_decision = section
                        break
            
            # 트레이딩 결정에서 값 추출
            if trading_decision:
                response_text = trading_decision  # 트레이딩 결정 섹션만 파싱
            
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
                        sl_roe = round(float(stop_loss_match.group(1)), 1)
                        print(f"추출된 Stop Loss ROE: {sl_roe}%")
                        if 0.5 <= sl_roe <= 30.0:
                            stop_loss_roe = sl_roe
                        else:
                            print(f"Stop Loss ROE가 범위를 벗어남 ({sl_roe}), 기본값 1.5% 사용")
                    except ValueError as ve:
                        print(f"Stop Loss ROE 변환 실패: {ve}, 기본값 1.5% 사용")
                
                # Take Profit ROE 추출
                if take_profit_match := take_profit_pattern.search(response_text):
                    try:
                        tp_roe = round(float(take_profit_match.group(1)), 1)
                        print(f"추출된 Take Profit ROE: {tp_roe}%")
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

            # ANALYSIS_DETAILS 섹션을 REASON으로 사용
            reason = ""
            
            # 수정된 정규식 패턴: "**분석 결과:**" 이후의 모든 내용을 추출
            if "**분석 결과:**" in original_response:
                analysis_parts = original_response.split("**분석 결과:**", 1)
                if len(analysis_parts) > 1:
                    reason = analysis_parts[1].strip()
                    print(f"'**분석 결과:**' 이후 내용 추출 성공")
            
            # 기존 정규식 패턴 (위 방법으로 추출 실패 시 사용)
            if not reason:
                analysis_pattern = re.compile(r'(?:###\s*)?(?:ANALYSIS[\s_-]*DETAILS|분석[\s_-]*상세|분석결과)(?:\s*:)?\s*([\s\S]+?)(?=###|$)', re.IGNORECASE)
                analysis_match = analysis_pattern.search(original_response)
                if analysis_match:
                    reason = analysis_match.group(1).strip()
                    print(f"정규표현식으로 분석 내용 추출 성공")
                else:
                    print(f"정규표현식으로 분석 내용을 찾지 못했습니다. 다른 방법으로 시도합니다.")
                    # 전체 응답을 reason으로 사용 (TRADING_DECISION 섹션 제외)
                    if "### TRADING_DECISION" in original_response:
                        parts = original_response.split("### TRADING_DECISION")
                        if len(parts) > 1 and "### ANALYSIS" in parts[1]:
                            analysis_part = parts[1].split("### ANALYSIS")[1]
                            reason = analysis_part.strip()
                            print(f"전체 응답에서 분석 부분 추출 성공")
                        else:
                            reason = original_response
                            print(f"분석 섹션을 찾을 수 없어 전체 응답을 사용합니다.")
                    else:
                        reason = original_response
                        print(f"TRADING_DECISION 섹션이 없어 전체 응답을 사용합니다.")
            
            # 여전히 reason이 없으면 기본값 설정
            if not reason:
                reason = "No analysis details provided"
                print(f"분석 내용이 없어 기본값을 사용합니다.")

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
        run = None
        thread_id = None
        
        try:
            print("\n=== 포지션 모니터링 분석 시작 ===")
            start_time = time.time()
            
            # 매번 새로운 스레드 생성
            thread = self.client.beta.threads.create()
            thread_id = thread.id
            print(f"모니터링용 새 스레드 생성됨: {thread_id}")
            
            # 1. 모니터링용 프롬프트 생성
            message_content = self._create_monitoring_prompt(market_data, position_info)

            # 2. 스레드에 메시지 추가
            message = self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message_content
            )
            print(f"모니터링 메시지 추가됨: {message.id}")

            # 3. 분석 실행
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant_id
            )
            print(f"모니터링 분석 시작됨: {run.id}")

            # 4. 실행 완료 대기
            run = self._wait_for_run(thread_id, run.id)

            # 5. 응답 받기
            messages = self.client.beta.threads.messages.list(thread_id=thread_id)
            
            if not messages.data:
                raise Exception("모니터링 응답 메시지가 없습니다.")
                
            # 6. 응답 파싱
            monitoring_result = self._parse_monitoring_response(messages.data[0].content[0].text.value)
            
            # 7. 총 소요 시간 계산 및 로깅
            elapsed_time = time.time() - start_time
            print(f"모니터링 분석 완료: 총 소요 시간 {elapsed_time:.2f}초")

            return monitoring_result

        except Exception as e:
            print(f"모니터링 분석 중 오류 발생: {str(e)}")
            error_type = type(e).__name__
            thread_info = f"Thread ID: {thread_id if thread_id else 'None'}"
            run_info = f"Run ID: {run.id if run else 'None'}"
            print(f"모니터링 API 호출 정보: {thread_info}, {run_info}")
            
            return {
                "action": "HOLD",
                "reason": f"모니터링 분석 중 오류 발생: {str(e)}"
            }

    def _parse_monitoring_response(self, response_text):
        """모니터링 응답 파싱"""
        try:
            print("\n=== 모니터링 응답 파싱 시작 ===")
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
        
            print("\n=== 모니터링 파싱 결과 ===")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
            return result

        except Exception as e:
            print(f"모니터링 응답 파싱 중 오류: {str(e)}")
            return {
                "action": "HOLD",
                "reason": f"파싱 오류: {str(e)}"
            } 