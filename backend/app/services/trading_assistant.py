from datetime import datetime, timedelta
import pandas as pd
from .bitget_service import BitgetService
import time
import numpy as np
from .ai_service import AIService
from app.models.trading_history import TradingHistory
from app.database.db import get_db
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
import uuid
import asyncio
import threading
import json
import sys
import traceback
from io import StringIO
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 웹소켓 연결 관리자 클래스 추가
class WebSocketConnectionManager:
    def __init__(self):
        self.active_connections = set()
        print("WebSocketConnectionManager 초기화됨")
    
    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"새로운 WebSocket 연결 추가됨. 현재 연결 수: {len(self.active_connections)}")
    
    def disconnect(self, websocket):
        self.active_connections.remove(websocket)
        print(f"WebSocket 연결 해제됨. 현재 연결 수: {len(self.active_connections)}")
    
    async def broadcast(self, message):
        """메시지를 모든 활성 연결에 브로드캐스트"""
        if not self.active_connections:
            print("활성화된 WebSocket 연결이 없습니다.")
            return

        print(f"\n=== WebSocket 브로드캐스트 시작 ===")
        print(f"활성 연결 수: {len(self.active_connections)}")
        
        def convert_datetime_to_str(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj
        
        try:
            if isinstance(message, dict):
                message = json.dumps(message, default=convert_datetime_to_str)
                print(f"브로드캐스트할 메시지:\n{json.dumps(json.loads(message), indent=2)}")
            
            disconnected = set()
            successful = 0
            
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                    successful += 1
                except Exception as e:
                    print(f"연결에 대한 브로드캐스트 실패: {str(e)}")
                    disconnected.add(connection)
            
            # 끊어진 연결 제거
            for connection in disconnected:
                self.disconnect(connection)
            
            print(f"\n브로드캐스트 결과:")
            print(f"- 성공: {successful}")
            print(f"- 실패/연결 해제: {len(disconnected)}")
            print(f"- 남은 연결 수: {len(self.active_connections)}")
            
        except Exception as e:
            print(f"브로드캐스트 중 예외 발생: {str(e)}")
            import traceback
            traceback.print_exc()

# 전역 웹소켓 연결 관리자 인스턴스 생성
websocket_manager = WebSocketConnectionManager()

class JobType:
    """작업 유형 정의"""
    ANALYSIS = "ANALYSIS"  # AI 분석 작업
    FORCE_CLOSE = "FORCE_CLOSE"  # 강제 청산 작업

class TradingAssistant:
    # 싱글톤 인스턴스
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TradingAssistant, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, websocket_manager=None):
        # 이미 초기화된 인스턴스인지 확인
        if hasattr(self, 'initialized') and self.initialized:
            # 웹소켓 매니저만 업데이트
            if websocket_manager is not None:
                self.websocket_manager = websocket_manager
            return
            
        # 초기화 플래그 설정
        self.initialized = True
        
        # 포지션 락 초기화
        self._position_lock = threading.Lock()
        
        # WebSocket 매니저 설정
        self.websocket_manager = websocket_manager
        
        # Bitget 서비스 초기화
        self.bitget = BitgetService()
        
        # AI 서비스 초기화 (OpenAI 서비스 대신)
        self.ai_service = AIService()
        
        # 스케줄러 초기화 (AsyncIOScheduler 대신 BackgroundScheduler 사용)
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        
        # 활성 작업 목록
        self.active_jobs = {}
        
        # 모니터링 관련 변수
        self.monitoring_job = None
        self.is_monitoring = False
        self.monitoring_start_time = None
        self.monitoring_end_time = None
        self.monitoring_interval = 2300  # 31분에서 15분으로 변경
        
        # 포지션 관련 변수 초기화
        self._position_entry_time = None
        self._last_position_check_time = time.time()
        self._position_check_interval = 1  # 1초
        self._last_position_side = None  # 마지막 포지션 방향 (long/short)
        self._last_position_size = 0  # 마지막 포지션 크기
        self._last_position_entry_price = 0  # 마지막 진입 가격
        self._last_position_leverage = 0  # 마지막 레버리지
        self._last_position_roe = 0  # 마지막 수익률
        self._last_position_pnl = 0  # 마지막 손익
        self._position_entry_price = None  # 포지션 진입 가격
        self._stop_loss_price = None  # 스탑로스 가격
        self._take_profit_price = None  # 익절 가격
        
        # 시스템 상태 변수
        self._system_initialized = True
        
        # 마지막 분석 결과 초기화
        self.last_analysis_result = None
        
        # 포지션 로깅 관련 속성 초기화
        self._last_position_log_time = time.time()
        self._position_log_interval = 30  # 30초마다 로깅
        
        # 현재 포지션 정보 초기화
        self.current_positions = []
        
        print("TradingAssistant 초기화 완료")

    def set_ai_model(self, model_type):
        """AI 모델 설정"""
        self.ai_service.set_model(model_type)
    
    def get_current_ai_model(self):
        """현재 AI 모델 반환"""
        return self.ai_service.get_current_model()

    async def _force_close_position(self, job_id):
        """Expected Time에 도달했을 때 포지션 강제 청산"""
        try:
            print(f"\n=== 강제 청산 작업 시작 (Job ID: {job_id}) ===")
            
            # 현재 포지션 확인
            positions = self.bitget.get_positions()
            if not positions or 'data' not in positions:
                print("포지션 정보를 가져올 수 없음")
                return
                
            # 포지션이 있는 경우에만 청산 실행
            has_position = False
            position_size = 0
            position_side = None
            
            for pos in positions['data']:
                if float(pos.get('total', 0)) > 0:
                    has_position = True
                    position_size = float(pos.get('total', 0))
                    position_side = pos.get('holdSide')
                    print(f"\n=== 포지션 청산 상세 ===")
                    print(f"포지션 방향: {position_side}")
                    print(f"포지션 크기: {position_size} BTC")
                    break
            
            if not has_position:
                print("청산할 포지션이 없음")
            else:
                # Flash Close API를 사용하여 포지션 청산
                close_result = self.bitget.close_positions(hold_side=position_side)
                print(f"청산 결과: {close_result}")
                
                # 청산 성공 여부 확인
                is_success = close_result.get('success', False)
                
                # 청산 성공 확인을 위해 포지션 재확인
                verification_positions = self.bitget.get_positions()
                current_position_size = 0
                if verification_positions and 'data' in verification_positions:
                    for pos in verification_positions['data']:
                        current_position_size += float(pos.get('total', 0))
                
                if is_success and current_position_size < position_size:
                    print("강제 청산 완료")
                    
                    # 모니터링 중지
                    self._stop_monitoring()
                    
                    # 기존 예약 작업 모두 취소
                    print("예약된 분석 작업이 취소되었습니다.")
                    self._cancel_scheduled_analysis()
                    print("모든 스케줄링된 작업이 취소되었습니다.")
                    self.cancel_all_jobs()
                    
                    # 60분 후 새로운 분석 예약
                    next_analysis_time = datetime.now() + timedelta(minutes=60)
                    new_job_id = str(uuid.uuid4())
                    
                    print(f"\n=== 강제 청산 후 새로운 분석 예약 ===")
                    print(f"예약 시간: {next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"작업 ID: {new_job_id}")
                    
                    # 비동기 함수를 실행하기 위한 래퍼 함수
                    def analysis_wrapper(job_id, analysis_time):
                        """비동기 분석 함수를 실행하기 위한 래퍼"""
                        print(f"\n=== 분석 래퍼 실행 (ID: {job_id}) ===")
                        print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        # 새로운 이벤트 루프 생성 및 설정
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        try:
                            # 비동기 함수를 동기적으로 실행
                            loop.run_until_complete(self.analyze_and_execute(job_id, schedule_next=True))
                        except Exception as e:
                            print(f"분석 작업 실행 중 오류: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            
                            # 오류 발생 시 60분 후 재분석 예약
                            def schedule_retry():
                                retry_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(retry_loop)
                                try:
                                    retry_loop.run_until_complete(
                                        self._schedule_next_analysis_on_error(f"강제 청산 후 분석 작업 {job_id} 실행 중 오류: {str(e)}")
                                    )
                                except Exception as retry_error:
                                    print(f"재시도 예약 중 오류: {str(retry_error)}")
                                finally:
                                    retry_loop.close()
                            
                            # 별도 스레드에서 재시도 예약 실행
                            import threading
                            retry_thread = threading.Thread(target=schedule_retry)
                            retry_thread.daemon = True
                            retry_thread.start()
                        finally:
                            # 이벤트 루프 종료
                            loop.close()
                    
                    # 스케줄러에 작업 추가
                    self.scheduler.add_job(
                        analysis_wrapper,
                        'date',
                        run_date=next_analysis_time,
                        id=new_job_id,
                        args=[new_job_id, next_analysis_time],
                        misfire_grace_time=300  # 5분의 유예 시간
                    )
                    
                    # 활성 작업에 추가
                    self.active_jobs[new_job_id] = {
                        "type": JobType.ANALYSIS,
                        "scheduled_time": next_analysis_time.isoformat(),
                        "status": "scheduled",
                        "metadata": {
                            "reason": "Expected time 도달 후 청산 및 자동 재시작",
                            "misfire_grace_time": 300
                        }
                    }
                    
                    # 청산 메시지 웹소켓으로 전송
                    if self.websocket_manager:
                        await self.websocket_manager.broadcast({
                            "type": "force_close",
                            "event_type": "FORCE_CLOSE",
                            "data": {
                                "success": True,
                                "message": "Expected minutes에 도달하여 포지션이 청산되었습니다. 60분 후 새로운 분석이 실행됩니다.",
                                "next_analysis": {
                                    "job_id": new_job_id,
                                    "scheduled_time": next_analysis_time.isoformat(),
                                    "reason": "Expected minutes 도달 후 자동 재시작",
                                    "expected_minutes": 60
                                }
                            },
                            "timestamp": datetime.now().isoformat()
                        })
                    
                    # 포지션 관련 상태 초기화
                    self._position_entry_time = None
                    self._expected_close_time = None
                    self._position_entry_price = None
                    self._stop_loss_price = None
                    self._take_profit_price = None
                    self._liquidation_detected = True  # 청산 감지 플래그 설정
                    
                    print("포지션 관련 상태가 초기화되었습니다.")
                    print(f"60분 후({next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')})에 새로운 분석이 실행됩니다.")
                    
                else:
                    print("강제 청산 실패 또는 부분 청산됨")
                    
                    # 포지션이 아직 있는 경우 15분 후에 다시 청산 시도
                    next_close_time = datetime.now() + timedelta(minutes=15)
                    retry_job_id = f"force_close_retry_{int(time.time())}"
                    
                    print(f"\n=== 청산 실패, 재시도 예약 ===")
                    print(f"재시도 시간: {next_close_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"작업 ID: {retry_job_id}")
                    
                    # 재시도용 래퍼 함수
                    def retry_close_wrapper(job_id):
                        """재시도 강제 청산 함수를 실행하기 위한 래퍼"""
                        print(f"\n=== 재시도 강제 청산 래퍼 실행 (ID: {job_id}) ===")
                        print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        # 새로운 이벤트 루프 생성 및 설정
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        try:
                            # 비동기 함수를 동기적으로 실행
                            loop.run_until_complete(self._force_close_position(job_id))
                        except Exception as e:
                            print(f"재시도 강제 청산 실행 중 오류: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            
                            # 오류 발생 시 30분 후 재분석 예약
                            def schedule_retry():
                                retry_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(retry_loop)
                                try:
                                    retry_loop.run_until_complete(
                                        self._schedule_next_analysis_on_error(f"재시도 강제 청산 작업 {job_id} 실행 중 오류: {str(e)}")
                                    )
                                except Exception as retry_error:
                                    print(f"재시도 예약 중 오류: {str(retry_error)}")
                                finally:
                                    retry_loop.close()
                            
                            # 별도 스레드에서 재시도 예약 실행
                            import threading
                            retry_thread = threading.Thread(target=schedule_retry)
                            retry_thread.daemon = True
                            retry_thread.start()
                        finally:
                            # 이벤트 루프 종료
                            loop.close()
                    
                    # 스케줄러에 작업 추가
                    self.scheduler.add_job(
                        retry_close_wrapper,
                        'date',
                        run_date=next_close_time,
                        id=retry_job_id,
                        args=[retry_job_id],
                        misfire_grace_time=300  # 5분의 유예 시간
                    )
                    
                    # 활성 작업에 추가
                    self.active_jobs[retry_job_id] = {
                        "type": JobType.FORCE_CLOSE,
                        "scheduled_time": next_close_time.isoformat(),
                        "status": "scheduled_retry",
                        "metadata": {
                            "reason": "청산 실패 또는 부분 청산 후 재시도",
                            "original_job_id": job_id,
                            "misfire_grace_time": 300
                        }
                    }
        except Exception as e:
            print(f"강제 청산 작업 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()

    def _cancel_force_close_job(self):
        """현재 예약된 FORCE_CLOSE 작업을 취소"""
        try:
            jobs = self.scheduler.get_jobs()
            for job in jobs:
                job_info = self.active_jobs.get(job.id)
                if job_info and job_info.get('type') == JobType.FORCE_CLOSE:
                    print(f"\n=== FORCE_CLOSE 작업 취소 (Job ID: {job.id}) ===")
                    self.scheduler.remove_job(job.id)
                    del self.active_jobs[job.id]
                    print(f"FORCE_CLOSE 작업이 취소되었습니다.")
        except Exception as e:
            print(f"FORCE_CLOSE 작업 취소 중 오류 발생: {str(e)}")

    async def _collect_market_data(self):
        """시장 데이터 수집"""
        try:
            print("\n=== 시장 데이터 수집 시작 ===")
            
            # 중복 수집 방지
            with self._position_lock:
                if hasattr(self, '_collecting_market_data') and self._collecting_market_data:
                    print("이미 시장 데이터 수집 중입니다. 기다려주세요.")
                    raise Exception("이미 시장 데이터 수집 중입니다.")
                self._collecting_market_data = True
            
            try:
                # 1. 현재 시장 데이터
                ticker = self.bitget.get_ticker()
                if not ticker or 'data' not in ticker or not ticker['data']:
                    raise Exception("티커 데이터 가져오기 실패")
                
                # API 응답에서 실제 24시간 데이터 사용
                if isinstance(ticker['data'], list) and ticker['data']:
                    ticker_data = ticker['data'][0]  # 첫 번째 항목 사용
                    current_market = {
                        'price': float(ticker_data['lastPr']),
                        '24h_high': float(ticker_data['high24h']),
                        '24h_low': float(ticker_data['low24h']),
                        '24h_volume': float(ticker_data['baseVolume'])
                    }
                else:
                    raise Exception("잘못된 티커 데이터 형식")
                
                # 필요한 필드가 있는지 확인
                required_fields = ['lastPr', 'high24h', 'low24h', 'baseVolume']
                missing_fields = [field for field in required_fields if field not in ticker_data]
                if missing_fields:
                    raise Exception(f"필수 티커 필드 누락: {missing_fields}")
                
                current_price = float(ticker_data['lastPr'])
                
                # 초기 데이터 구조 생성
                formatted_data = {
                    "current_market": {
                        "price": current_price,
                        "timestamp": datetime.now().isoformat(),
                        "24h_high": float(ticker_data['high24h']),
                        "24h_low": float(ticker_data['low24h']),
                        "24h_volume": float(ticker_data['baseVolume']),
                    },
                    "candlesticks": {},
                    "technical_indicators": {},
                    "account": {},
                    "positions": [],
                    "orderbook": {}
                }
                
                # 2. 여러 시간대의 캔들스틱 데이터 수집
                current_time = int(time.time() * 1000)
                
                # API 문서에 따른 각 granularity별 최대 조회 기간 설정
                # 최대 쿼리 범위는 90일(90 * 24 * 60 * 60 * 1000)을 넘지 않아야 함
                max_query_range = 90 * 24 * 60 * 60 * 1000  # 90일 (밀리초)
                
                timeframes = {
                    "1m": {"start": current_time - min(30 * 24 * 60 * 60 * 1000, max_query_range), "limit": "1000"},  # 1개월 제한, 최대 1000개
                    "3m": {"start": current_time - min(30 * 24 * 60 * 60 * 1000, max_query_range), "limit": "800"},   # 1개월 제한, 800개
                    "5m": {"start": current_time - min(30 * 24 * 60 * 60 * 1000, max_query_range), "limit": "600"},   # 1개월 제한, 600개
                    "15m": {"start": current_time - min(52 * 24 * 60 * 60 * 1000, max_query_range), "limit": "500"},  # 52일 제한, 500개
                    "30m": {"start": current_time - min(62 * 24 * 60 * 60 * 1000, max_query_range), "limit": "400"},  # 62일 제한, 400개
                    "1H": {"start": current_time - min(83 * 24 * 60 * 60 * 1000, max_query_range), "limit": "300"},   # 83일 제한, 300개
                    "4H": {"start": current_time - min(240 * 24 * 60 * 60 * 1000, max_query_range), "limit": "200"},  # 240일 제한(최대 90일)
                    "6H": {"start": current_time - min(360 * 24 * 60 * 60 * 1000, max_query_range), "limit": "150"},  # 360일 제한(최대 90일)
                    "12H": {"start": current_time - min(90 * 24 * 60 * 60 * 1000, max_query_range), "limit": "150"},  # 90일 제한
                    "1D": {"start": current_time - min(90 * 24 * 60 * 60 * 1000, max_query_range), "limit": "90"},    # 90일 제한, 90개
                    "3D": {"start": current_time - min(90 * 24 * 60 * 60 * 1000, max_query_range), "limit": "60"},    # 90일 제한, 60개
                    "1W": {"start": current_time - min(90 * 24 * 60 * 60 * 1000, max_query_range), "limit": "25"},    # 90일 제한, 25개
                    "1M": {"start": current_time - min(90 * 24 * 60 * 60 * 1000, max_query_range), "limit": "12"},    # 90일 제한, 12개
                }
                
                print("\n캔들스틱 데이터 수집 중...")
                for timeframe, time_info in timeframes.items():
                    try:
                        # 각 시간대별 API 요청
                        kline_data = self.bitget.get_kline(
                            symbol="BTCUSDT",
                            productType="USDT-FUTURES",
                            granularity=timeframe,
                            startTime=str(time_info["start"]),
                            endTime=str(current_time),
                            limit=time_info["limit"]
                        )
                        
                        if kline_data and 'data' in kline_data and kline_data['data']:
                            candle_count = len(kline_data['data'])
                            print(f"{timeframe} 캔들 데이터 수집 성공: {candle_count}개")
                            formatted_data['candlesticks'][timeframe] = self._format_kline_data(kline_data)
                            
                            # 기술적 지표 계산 (모든 시간대에 대해 계산)
                            if formatted_data['candlesticks'][timeframe]:
                                formatted_data['technical_indicators'][timeframe] = self.calculate_technical_indicators(formatted_data['candlesticks'][timeframe])
                        else:
                            print(f"{timeframe} 캔들 데이터 수집 실패 또는 빈 데이터")
                            formatted_data['candlesticks'][timeframe] = []
                            formatted_data['technical_indicators'][timeframe] = {}
                    except Exception as e:
                        print(f"{timeframe} 캔들 데이터 수집 중 오류: {str(e)}")
                        formatted_data['candlesticks'][timeframe] = []
                        formatted_data['technical_indicators'][timeframe] = {}
                
                # 3. 나머지 데이터 수집 및 포맷팅
                print("\n계정 및 포지션 데이터 수집 중...")
                account_info = self.bitget.get_account_info()
                positions = self.bitget.get_positions()
                orderbook = self.bitget.get_orderbook()
                
                formatted_data.update({
                    "account": self._format_account_data(account_info),
                    "positions": self._format_position_data(positions),
                    "orderbook": self._format_orderbook_data(orderbook)
                })
                
                print("=== 시장 데이터 수집 완료 ===\n")
                return formatted_data
                
            finally:
                # 데이터 수집 상태 초기화
                with self._position_lock:
                    self._collecting_market_data = False
                    
        except Exception as e:
            print(f"시장 데이터 수집 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 데이터 수집 상태 초기화
            with self._position_lock:
                self._collecting_market_data = False
                
            raise Exception(f"시장 데이터 수집 실패: {str(e)}")

    def _format_kline_data(self, kline_data):
        """캔들스틱 데이터 포맷팅"""
        try:
            formatted_candles = []
            
            if isinstance(kline_data, dict) and 'data' in kline_data:
                candles_data = kline_data['data']
                
                if isinstance(candles_data, list):
                    for candle in candles_data:
                        formatted_candle = {
                            'timestamp': int(candle[0]) if len(candle) > 0 else 0,
                            'open': float(candle[1]) if len(candle) > 1 else 0,
                            'high': float(candle[2]) if len(candle) > 2 else 0,
                            'low': float(candle[3]) if len(candle) > 3 else 0,
                            'close': float(candle[4]) if len(candle) > 4 else 0,
                            'volume': float(candle[5]) if len(candle) > 5 else 0
                        }
                        formatted_candles.append(formatted_candle)
            
            return formatted_candles
        except Exception as e:
            print(f"Error in _format_kline_data: {str(e)}")
            return []

    def _format_account_data(self, account_info):
        try:
            if not account_info:
                return self._get_default_account_data()
            
            if not isinstance(account_info, dict) or 'data' not in account_info:
                return self._get_default_account_data()
            
            account_data = account_info['data']

            if isinstance(account_data, dict):
                return {
                    "equity": float(account_data.get('accountEquity', 0)),
                    "available_balance": float(account_data.get('available', 0)),
                    "used_margin": float(account_data.get('locked', 0)),
                    "unrealized_pnl": float(account_data.get('unrealizedPL', 0))
                }
            else:
                return self._get_default_account_data()
            
        except Exception as e:
            print(f"Error in _format_account_data: {str(e)}")
            return self._get_default_account_data()

    def _format_position_data(self, positions):
        """포지션 데이터 포맷팅"""
        try:
            print("\n=== Format Position Data ===")
            print(f"원본 포지션 데이터: {positions}")
            
            if not positions or not isinstance(positions, dict) or 'data' not in positions:
                print("포지션 데이터가 없거나 올바른 형식이 아닙니다.")
                self.current_positions = []
                return []
            
            position_data = positions['data']
            if not position_data:
                print("포지션이 없습니다.")
                self.current_positions = []
                return []
            
            formatted_positions = []
            for pos in position_data:
                # 각 포지션 정보를 _update_position_info 함수를 통해 업데이트
                position_info = self._update_position_info(pos)
                if position_info:
                    formatted_positions.append(position_info)
            
            print(f"포맷팅된 포지션 데이터: {formatted_positions}")
            
            # 포지션 변화 감지 (추가)
            if formatted_positions:
                self._detect_position_changes(formatted_positions[0])
            
            # 포맷팅된 포지션 데이터를 인스턴스 변수에 저장
            self.current_positions = formatted_positions
            
            return formatted_positions
            
        except Exception as e:
            print(f"포지션 데이터 포맷팅 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            self.current_positions = []
            return []

    def _format_orderbook_data(self, orderbook):
        """호가창 데이터 포맷팅"""
        try:
            if not orderbook or 'data' not in orderbook:
                return {}
            
            if isinstance(orderbook['data'], dict):
                return {
                    "asks": [[float(price), float(size)] 
                            for price, size in orderbook['data'].get('asks', [])[:5]],
                    "bids": [[float(price), float(size)] 
                            for price, size in orderbook['data'].get('bids', [])[:5]]
                }
            elif isinstance(orderbook['data'], list) and len(orderbook['data']) > 0:
                first_item = orderbook['data'][0]
                return {
                    "asks": [[float(price), float(size)] 
                            for price, size in first_item.get('asks', [])[:5]],
                    "bids": [[float(price), float(size)] 
                            for price, size in first_item.get('bids', [])[:5]]
                }
            else:
                return {}
        except Exception as e:
            print(f"Error in _format_orderbook_data: {str(e)}")
            return {}

    def calculate_technical_indicators(self, kline_data):
        """
    기술적 지표 계산 함수 - 구현된 지표 목록:

    1. 모멘텀/오실레이터 지표:
    - RSI (7, 14, 21기간 및 다이버전스)
    - MACD (12,26,9 및 8,17,9)
    - 스토캐스틱 (14,3,3 및 9,3,3)
    - CMF (Chaikin Money Flow)
    - MPO (Modified Price Oscillator)

    2. 변동성/추세 지표:
    - 볼린저 밴드 (10, 20, 50일)
    - ATR (Average True Range)
    - DMI/ADX (Directional Movement Index)
    - MAT (평균 이동 시간대)
    - 트렌드 강도 및 방향성 분석

    3. 추세 지표:
    - 이동평균선 (SMA: 5, 10, 20, 50, 100, 200일)
    - 지수이동평균 (EMA: 9, 21, 55, 200일)
    - VWMA (Volume Weighted Moving Average)
    - 이치모쿠 구름 (전환선, 기준선, 선행스팬, 후행스팬)
    - 이동평균선 배열 및 교차 분석

    4. 볼륨 분석:
    - OBV (On-Balance Volume)
    - 볼륨 프로파일 (POC, VAH, VAL, HVN, LVN)
    - 상대 볼륨 분석 및 볼륨 RSI
    - 가격-볼륨 관계 분석

    5. 가격 레벨/지점:
    - 피보나치 레벨 (되돌림 및 확장)
    - 피벗 포인트 (PP, S1-S3, R1-R3)
    - 스윙 고점/저점 분석

    6. 패턴 인식:
    - 차트 패턴 (쌍바닥, 쌍천장 등)
    - 하모닉 패턴 (가트 나비, AB=CD)
    - RSI 다이버전스 패턴

    7. 심리 지표:
    - 불공포지수 (Fear & Greed Index)
    - 시장 심리 상태 분석

    8. 종합 분석:
    - 다중 시간대 일관성 분석
    - 볼륨-가격 상관관계
    - 추세 지속성 및 신뢰도 평가
"""
        if not kline_data:
            return {}

        df = pd.DataFrame(kline_data)
        
        try:
            # 1. RSI 계산 (14기간, 추가로 7, 21 기간도 계산)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            # 0으로 나누기 방지를 위한 epsilon 추가
            epsilon = 1e-10
            rs = gain / (loss + epsilon)
            rs = rs.fillna(0)  # NaN 값 처리
            rsi14 = 100 - (100 / (1 + rs))
            rsi14 = rsi14.fillna(50)  # NaN 값을 중립값 50으로 대체
            
            # 7기간 RSI
            gain7 = (delta.where(delta > 0, 0)).rolling(window=7).mean()
            loss7 = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
            rs7 = gain7 / (loss7 + epsilon)
            rs7 = rs7.fillna(0)  # NaN 값 처리
            rsi7 = 100 - (100 / (1 + rs7))
            rsi7 = rsi7.fillna(50)  # NaN 값을 중립값 50으로 대체
            
            # 21기간 RSI
            gain21 = (delta.where(delta > 0, 0)).rolling(window=21).mean()
            loss21 = (-delta.where(delta < 0, 0)).rolling(window=21).mean()
            rs21 = gain21 / (loss21 + epsilon)
            rs21 = rs21.fillna(0)  # NaN 값 처리
            rsi21 = 100 - (100 / (1 + rs21))
            rsi21 = rsi21.fillna(50)  # NaN 값을 중립값 50으로 대체

            # RSI 다이버전스 탐지 개선
            rsi_divergence = {
                "regular": None,  # 정규 다이버전스
                "hidden": None,   # 히든 다이버전스
                "strength": 0     # 다이버전스 강도 (0-100)
            }
            
            if len(df) >= 20:
                # 지역 고점/저점 찾기 (더 정확한 RSI 다이버전스 탐지용)
                price_highs = []
                price_lows = []
                rsi_highs = []
                rsi_lows = []
                
                # 지역 고점/저점 식별 (최소 5개 봉 범위)
                for i in range(2, min(20, len(df) - 2)):
                    # 가격 지역 고점
                    if (df['high'].iloc[-i] > df['high'].iloc[-i-1] and 
                        df['high'].iloc[-i] > df['high'].iloc[-i-2] and
                        df['high'].iloc[-i] > df['high'].iloc[-i+1] and
                        df['high'].iloc[-i] > df['high'].iloc[-i+2]):
                        price_highs.append((len(df)-i, df['high'].iloc[-i]))
                    
                    # 가격 지역 저점
                    if (df['low'].iloc[-i] < df['low'].iloc[-i-1] and 
                        df['low'].iloc[-i] < df['low'].iloc[-i-2] and
                        df['low'].iloc[-i] < df['low'].iloc[-i+1] and
                        df['low'].iloc[-i] < df['low'].iloc[-i+2]):
                        price_lows.append((len(df)-i, df['low'].iloc[-i]))
                    
                    # RSI 지역 고점
                    if (rsi14.iloc[-i] > rsi14.iloc[-i-1] and 
                        rsi14.iloc[-i] > rsi14.iloc[-i-2] and
                        rsi14.iloc[-i] > rsi14.iloc[-i+1] and
                        rsi14.iloc[-i] > rsi14.iloc[-i+2]):
                        rsi_highs.append((len(df)-i, rsi14.iloc[-i]))
                    
                    # RSI 지역 저점
                    if (rsi14.iloc[-i] < rsi14.iloc[-i-1] and 
                        rsi14.iloc[-i] < rsi14.iloc[-i-2] and
                        rsi14.iloc[-i] < rsi14.iloc[-i+1] and
                        rsi14.iloc[-i] < rsi14.iloc[-i+2]):
                        rsi_lows.append((len(df)-i, rsi14.iloc[-i]))
                
                # 최소 2개의 고점/저점이 필요
                if len(price_highs) >= 2 and len(rsi_highs) >= 2:
                    # 정규 베어리시 다이버전스: 가격 고점은 상승, RSI 고점은 하락
                    ph1, ph2 = price_highs[0][1], price_highs[1][1]
                    rh1, rh2 = rsi_highs[0][1], rsi_highs[1][1]
                    
                    if ph1 > ph2 and rh1 < rh2:
                        div_strength = min(100, int(abs((rh2 - rh1) / rh2 * 100)))
                        rsi_divergence["regular"] = "bearish"
                        rsi_divergence["strength"] = div_strength
                    # 히든 베어리시 다이버전스: 가격 고점은 하락, RSI 고점은 상승
                    elif ph1 < ph2 and rh1 > rh2:
                        div_strength = min(100, int(abs((rh1 - rh2) / rh1 * 100)))
                        rsi_divergence["hidden"] = "bearish"
                        rsi_divergence["strength"] = div_strength
                
                if len(price_lows) >= 2 and len(rsi_lows) >= 2:
                    # 정규 불리시 다이버전스: 가격 저점은 하락, RSI 저점은 상승
                    pl1, pl2 = price_lows[0][1], price_lows[1][1]
                    rl1, rl2 = rsi_lows[0][1], rsi_lows[1][1]
                    
                    if pl1 < pl2 and rl1 > rl2:
                        div_strength = min(100, int(abs((rl1 - rl2) / rl1 * 100)))
                        rsi_divergence["regular"] = "bullish"
                        rsi_divergence["strength"] = div_strength
                    # 히든 불리시 다이버전스: 가격 저점은 상승, RSI 저점은 하락
                    elif pl1 > pl2 and rl1 < rl2:
                        div_strength = min(100, int(abs((rl2 - rl1) / rl2 * 100)))
                        rsi_divergence["hidden"] = "bullish"
                        rsi_divergence["strength"] = div_strength

            # 2. MACD 계산 (다양한 파라미터)
            # 기본 MACD (12, 26, 9)
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            histogram = macd - signal
            
            # NaN 값 처리
            macd = macd.fillna(0)
            signal = signal.fillna(0)
            histogram = histogram.fillna(0)
            
            # 빠른 MACD (8, 17, 9)
            exp1_fast = df['close'].ewm(span=8, adjust=False).mean()
            exp2_fast = df['close'].ewm(span=17, adjust=False).mean()
            macd_fast = exp1_fast - exp2_fast
            signal_fast = macd_fast.ewm(span=9, adjust=False).mean()
            histogram_fast = macd_fast - signal_fast
            
            # NaN 값 처리
            macd_fast = macd_fast.fillna(0)
            signal_fast = signal_fast.fillna(0)
            histogram_fast = histogram_fast.fillna(0)
            
            # 3. 볼린저 밴드 (20일, 2표준편차 + 추가 파라미터)
            # 표준 볼린저 밴드 (20일)
            middle_band_20 = df['close'].rolling(window=20).mean()
            std_dev_20 = df['close'].rolling(window=20).std()
            upper_band_20 = middle_band_20 + (std_dev_20 * 2)
            lower_band_20 = middle_band_20 - (std_dev_20 * 2)
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            middle_band_20 = middle_band_20.ffill()
            std_dev_20 = std_dev_20.fillna(0)  # 표준편차는 0으로 처리
            upper_band_20 = upper_band_20.ffill()
            lower_band_20 = lower_band_20.ffill()
            
            # 짧은 볼린저 밴드 (10일)
            middle_band_10 = df['close'].rolling(window=10).mean()
            std_dev_10 = df['close'].rolling(window=10).std()
            upper_band_10 = middle_band_10 + (std_dev_10 * 2)
            lower_band_10 = middle_band_10 - (std_dev_10 * 2)
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            middle_band_10 = middle_band_10.ffill()
            std_dev_10 = std_dev_10.fillna(0)  # 표준편차는 0으로 처리
            upper_band_10 = upper_band_10.ffill()
            lower_band_10 = lower_band_10.ffill()
            
            # 긴 볼린저 밴드 (50일)
            middle_band_50 = df['close'].rolling(window=50).mean()
            std_dev_50 = df['close'].rolling(window=50).std()
            upper_band_50 = middle_band_50 + (std_dev_50 * 2)
            lower_band_50 = middle_band_50 - (std_dev_50 * 2)
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            middle_band_50 = middle_band_50.ffill()
            std_dev_50 = std_dev_50.fillna(0)  # 표준편차는 0으로 처리
            upper_band_50 = upper_band_50.ffill()
            lower_band_50 = lower_band_50.ffill()
            
            # 4. 이동평균선 (추가 MA 계산)
            ma5 = df['close'].rolling(window=5).mean()
            ma10 = df['close'].rolling(window=10).mean()
            ma20 = df['close'].rolling(window=20).mean()
            ma50 = df['close'].rolling(window=50).mean()
            ma100 = df['close'].rolling(window=100).mean()
            ma200 = df['close'].rolling(window=200).mean()
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            ma5 = ma5.ffill()
            ma10 = ma10.ffill()
            ma20 = ma20.ffill()
            ma50 = ma50.ffill()
            ma100 = ma100.ffill()
            ma200 = ma200.ffill()
            
            # 지수이동평균 (EMA)
            ema9 = df['close'].ewm(span=9, adjust=False).mean()
            ema21 = df['close'].ewm(span=21, adjust=False).mean()
            ema55 = df['close'].ewm(span=55, adjust=False).mean()
            ema200 = df['close'].ewm(span=200, adjust=False).mean()
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            ema9 = ema9.ffill()
            ema21 = ema21.ffill()
            ema55 = ema55.ffill()
            ema200 = ema200.ffill()
            
            # 5. 스토캐스틱 (14,3,3)
            low_14 = df['low'].rolling(window=14).min()
            high_14 = df['high'].rolling(window=14).max()
            k_percent = 100 * ((df['close'] - low_14) / (high_14 - low_14))
            d_percent = k_percent.rolling(window=3).mean()
            slow_d = d_percent.rolling(window=3).mean()
            
            # NaN 값 처리
            k_percent = k_percent.fillna(50)  # 중립값으로 대체
            d_percent = d_percent.fillna(50)
            slow_d = slow_d.fillna(50)

            # 스토캐스틱 추가 버전 (9,3,3)
            low_9 = df['low'].rolling(window=9).min()
            high_9 = df['high'].rolling(window=9).max()
            k_percent_9 = 100 * ((df['close'] - low_9) / (high_9 - low_9))
            d_percent_9 = k_percent_9.rolling(window=3).mean()
            slow_d_9 = d_percent_9.rolling(window=3).mean()

            # NaN 값 처리
            k_percent_9 = k_percent_9.fillna(50)  # 중립값으로 대체
            d_percent_9 = d_percent_9.fillna(50)
            slow_d_9 = slow_d_9.fillna(50)

            # 6. ATR (14일)
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift())
            low_close = abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(window=14).mean()
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            atr = atr.ffill()
            
            # ATR % (ATR를 현재 가격의 백분율로 표시)
            atr_percent = (atr / df['close']) * 100
            atr_percent = atr_percent.fillna(0)  # NaN 값을 0으로 대체

            # 7. OBV - On-Balance Volume
            obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
            obv_ma20 = obv.rolling(window=20).mean()
            obv_ma20 = obv_ma20.ffill()

            # 8. DMI/ADX (14일)
            # DMI 계산을 위한 +DM과 -DM을 올바르게 계산
            high_diff = df['high'].diff()
            low_diff = df['low'].diff()
            
            # +DM: 상승폭이 하락폭보다 크고 양수일 때만 사용
            plus_dm = high_diff.copy()
            plus_dm = plus_dm.where((high_diff > low_diff.abs()) & (high_diff > 0), 0)
            
            # -DM: 하락폭이 상승폭보다 크고 음수일 때만 사용 (수정된 부분)
            minus_dm = low_diff.abs().copy()
            minus_dm = minus_dm.where((low_diff.abs() > high_diff) & (low_diff < 0), 0)
            
            # True Range 계산
            tr = true_range
            
            # 지수평균 사용으로 변경하여 더 부드러운 결과 얻기
            smoothing = 14
            plus_di = 100 * (plus_dm.ewm(alpha=1/smoothing, adjust=False).mean() / tr.ewm(alpha=1/smoothing, adjust=False).mean())
            minus_di = 100 * (minus_dm.ewm(alpha=1/smoothing, adjust=False).mean() / tr.ewm(alpha=1/smoothing, adjust=False).mean())
            
            # NaN 값 처리
            plus_di = plus_di.fillna(0)
            minus_di = minus_di.fillna(0)
            
            # ADX 계산 수정 - 0으로 나누기 방지 및 정규화
            epsilon = 1e-10  # 작은 값 추가하여 0으로 나누기 방지
            # DX 계산: +DI와 -DI의 차이를 합으로 나눈 절대값
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + epsilon)
            dx = dx.fillna(0)  # NaN 값을 0으로 대체
            
            # ADX 계산: DX의 지수평균
            adx = dx.ewm(alpha=1/smoothing, adjust=False).mean()
            adx = adx.fillna(0)  # NaN 값을 0으로 대체

            # ADX 값을 0-100 사이로 제한
            adx = adx.clip(0, 100)  # 0보다 작은 값은 0으로, 100보다 큰 값은 100으로 제한

            # 9. Ichimoku Cloud
            # 전환선 (Conversion Line, 9일)
            high_9 = df['high'].rolling(window=9).max()
            low_9 = df['low'].rolling(window=9).min()
            conversion_line = (high_9 + low_9) / 2
            
            # 기준선 (Base Line, 26일)
            high_26 = df['high'].rolling(window=26).max()
            low_26 = df['low'].rolling(window=26).min()
            base_line = (high_26 + low_26) / 2
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            conversion_line = conversion_line.ffill()
            base_line = base_line.ffill()
            
            # 선행스팬1 (Leading Span A)
            leading_span_a = ((conversion_line + base_line) / 2).shift(26)
            
            # 선행스팬2 (Leading Span B)
            high_52 = df['high'].rolling(window=52).max()
            low_52 = df['low'].rolling(window=52).min()
            leading_span_b = ((high_52 + low_52) / 2).shift(26)
            
            # NaN 값 처리 - fillna 대신 ffill() 사용
            leading_span_a = leading_span_a.ffill()
            leading_span_b = leading_span_b.ffill()
            
            # 후행스팬 (Lagging Span)
            lagging_span = df['close'].shift(-26)
            lagging_span = lagging_span.bfill()  # 뒤의 값으로 채우기
            
            # 추가: 일목구름도 신호 판단
            if len(df) > 26:
                # 구름대 위치 (현재 가격이 구름대 위인지 아래인지)
                current_price = df['close'].iloc[-1]
                current_leading_span_a = leading_span_a.iloc[-26] if not pd.isna(leading_span_a.iloc[-26]) else None
                current_leading_span_b = leading_span_b.iloc[-26] if not pd.isna(leading_span_b.iloc[-26]) else None
                
                if current_leading_span_a is not None and current_leading_span_b is not None:
                    cloud_top = max(current_leading_span_a, current_leading_span_b)
                    cloud_bottom = min(current_leading_span_a, current_leading_span_b)
                    
                    if current_price > cloud_top:
                        cloud_position = "above_cloud"  # 구름대 위 (강세)
                    elif current_price < cloud_bottom:
                        cloud_position = "below_cloud"  # 구름대 아래 (약세)
                    else:
                        cloud_position = "in_cloud"  # 구름대 내부 (중립)
                else:
                    cloud_position = None
                
                # 전환선과 기준선 크로스 판단
                if not pd.isna(conversion_line.iloc[-1]) and not pd.isna(base_line.iloc[-1]):
                    if conversion_line.iloc[-2] < base_line.iloc[-2] and conversion_line.iloc[-1] >= base_line.iloc[-1]:
                        tenkan_kijun_cross = "bullish"  # 골든 크로스
                    elif conversion_line.iloc[-2] > base_line.iloc[-2] and conversion_line.iloc[-1] <= base_line.iloc[-1]:
                        tenkan_kijun_cross = "bearish"  # 데드 크로스
                    else:
                        tenkan_kijun_cross = "none"
                else:
                    tenkan_kijun_cross = None
                
                # 구름대 두께 (강한 트렌드 확인)
                if current_leading_span_a is not None and current_leading_span_b is not None:
                    cloud_thickness = abs(current_leading_span_a - current_leading_span_b)
                else:
                    cloud_thickness = None
            else:
                cloud_position = tenkan_kijun_cross = cloud_thickness = None
            
            # 10. 피보나치 되돌림 레벨
            # 최근 고점과 저점 찾기 (최근 100개 캔들에서)
            recent_df = df.iloc[-100:] if len(df) > 100 else df
            
            # 상승장과 하락장 구분을 위한 최근 트렌드 확인
            if len(recent_df) > 20:
                uptrend = recent_df['close'].iloc[-1] > recent_df['close'].iloc[-20]
            else:
                uptrend = True  # 기본값
            
            # 상승장이면 고점에서 저점으로, 하락장이면 저점에서 고점으로 피보나치 레벨 계산
            if uptrend:
                # 상승 추세: 저점에서 고점으로
                recent_high = recent_df['high'].max()
                recent_high_idx = recent_df['high'].idxmax() if not recent_df.empty else None
                
                # 고점 이전의 저점 찾기
                if recent_high_idx is not None and recent_high_idx > recent_df.index.min():
                    temp_df = recent_df.loc[:recent_high_idx]
                    recent_low = temp_df['low'].min()
                else:
                    recent_low = recent_df['low'].min()
                
                # 피보나치 레벨 계산 (상승 트렌드)
                fib_diff = recent_high - recent_low
            else:
                # 하락 추세: 고점에서 저점으로
                recent_low = recent_df['low'].min()
                recent_low_idx = recent_df['low'].idxmin() if not recent_df.empty else None
                
                # 저점 이전의 고점 찾기
                if recent_low_idx is not None and recent_low_idx > recent_df.index.min():
                    temp_df = recent_df.loc[:recent_low_idx]
                    recent_high = temp_df['high'].max()
                else:
                    recent_high = recent_df['high'].max()
                
                # 피보나치 레벨 계산 (하락 트렌드)
                fib_diff = recent_high - recent_low
            
            # 피보나치 레벨 계산
            fib_levels = {
                "0.0": recent_low if uptrend else recent_high,
                "0.236": recent_low + 0.236 * fib_diff if uptrend else recent_high - 0.236 * fib_diff,
                "0.382": recent_low + 0.382 * fib_diff if uptrend else recent_high - 0.382 * fib_diff,
                "0.5": recent_low + 0.5 * fib_diff if uptrend else recent_high - 0.5 * fib_diff,
                "0.618": recent_low + 0.618 * fib_diff if uptrend else recent_high - 0.618 * fib_diff,
                "0.786": recent_low + 0.786 * fib_diff if uptrend else recent_high - 0.786 * fib_diff,
                "1.0": recent_high if uptrend else recent_low
            }
            
            # 피보나치 확장 레벨 (1.272, 1.618, 2.0)
            fib_ext_levels = {
                "1.272": recent_high + 0.272 * fib_diff if uptrend else recent_low - 0.272 * fib_diff,
                "1.618": recent_high + 0.618 * fib_diff if uptrend else recent_low - 0.618 * fib_diff,
                "2.0": recent_high + fib_diff if uptrend else recent_low - fib_diff
            }
            
            # 현재 가격과 가장 가까운 피보나치 되돌림 레벨 찾기
            current_price = df['close'].iloc[-1]
            closest_level = None
            min_distance = float('inf')
            
            for level, value in fib_levels.items():
                distance = abs(current_price - value)
                if distance < min_distance:
                    min_distance = distance
                    closest_level = level
            
            # 11. Pivot Points (전통적인 방식)
            # 최근 high, low, close 가져오기
            if len(df) > 1:
                prev_high = df['high'].iloc[-2]
                prev_low = df['low'].iloc[-2]
                prev_close = df['close'].iloc[-2]
                
                # Pivot Points 계산
                pivot_point = (prev_high + prev_low + prev_close) / 3
                support1 = (2 * pivot_point) - prev_high
                support2 = pivot_point - (prev_high - prev_low)
                support3 = pivot_point - 2 * (prev_high - prev_low)
                resistance1 = (2 * pivot_point) - prev_low
                resistance2 = pivot_point + (prev_high - prev_low)
                resistance3 = pivot_point + 2 * (prev_high - prev_low)
            else:
                pivot_point = support1 = support2 = support3 = resistance1 = resistance2 = resistance3 = None
                
            # 12. 추가 지표: Chaikin Money Flow (CMF)
            if len(df) >= 20:
                mfv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
                mfv = mfv * df['volume']
                cmf = mfv.rolling(window=20).sum() / df['volume'].rolling(window=20).sum()
                cmf_value = cmf.iloc[-1] if not pd.isna(cmf.iloc[-1]) else None
            else:
                cmf_value = None
                
            # 13. 추가 지표: 수정 가격 진동 지수 (Modified Price Oscillator, MPO)
            if len(df) >= 10:
                mpo = 100 * ((df['close'] - df['close'].rolling(window=10).mean()) / df['close'].rolling(window=10).mean())
                mpo_value = mpo.iloc[-1] if not pd.isna(mpo.iloc[-1]) else None
            else:
                mpo_value = None
                
            # 14. 추가 지표: 볼륨 가중 이동평균 (VWMA)
            if len(df) >= 20:
                vwma = (df['close'] * df['volume']).rolling(window=20).sum() / df['volume'].rolling(window=20).sum()
                vwma_value = vwma.iloc[-1] if not pd.isna(vwma.iloc[-1]) else None
            else:
                vwma_value = None
            
            # 볼륨 프로파일 (간단한 버전)
            if len(df) >= 20:
                # 최근 20개 캔들의 가격대별 거래량 계산
                price_buckets = pd.cut(df['close'].iloc[-20:], bins=5)
                volume_profile = df['volume'].iloc[-20:].groupby(price_buckets, observed=True).sum()
                # 가장 거래량이 많은 가격대
                max_volume_price = volume_profile.idxmax().mid if not volume_profile.empty else None
            else:
                max_volume_price = None
            
            # 패턴 인식 (간단한 형태)
            pattern_data = {}
            
            # 추세 판별 (단순 방식)
            if len(df) >= 20:
                # 20일 추세 판별: 현재 가격이 20일 이동평균보다 위에 있으면 상승, 아래면 하락
                trend_20d = "uptrend" if df['close'].iloc[-1] > ma20.iloc[-1] else "downtrend"
                # 10일 추세 판별
                trend_10d = "uptrend" if df['close'].iloc[-1] > ma10.iloc[-1] else "downtrend"
                # 50일 추세 판별
                trend_50d = "uptrend" if df['close'].iloc[-1] > ma50.iloc[-1] else "downtrend"
                
                pattern_data = {
                    "trend_10d": trend_10d,
                    "trend_20d": trend_20d,
                    "trend_50d": trend_50d
                }
                
                # 간단한 패턴 감지 (마지막 5개 캔들)
                if len(df) >= 5:
                    last5 = df.iloc[-5:]
                    
                    # 쌍바닥 패턴 간단 감지 (V자 형태)
                    if (last5['low'].iloc[0] > last5['low'].iloc[1] and
                        last5['low'].iloc[1] < last5['low'].iloc[2] and
                        last5['low'].iloc[2] > last5['low'].iloc[3] and
                        last5['low'].iloc[3] < last5['low'].iloc[4]):
                        pattern_data["double_bottom"] = True
                    else:
                        pattern_data["double_bottom"] = False
                    
                    # 쌍천장 패턴 간단 감지 (역V자 형태)
                    if (last5['high'].iloc[0] < last5['high'].iloc[1] and
                        last5['high'].iloc[1] > last5['high'].iloc[2] and
                        last5['high'].iloc[2] < last5['high'].iloc[3] and
                        last5['high'].iloc[3] > last5['high'].iloc[4]):
                        pattern_data["double_top"] = True
                    else:
                        pattern_data["double_top"] = False
            else:
                pattern_data = {"trend_10d": None, "trend_20d": None, "trend_50d": None}
            
            # 15. 고급 볼륨 분석
            if len(df) >= 20:
                # 볼륨 이동평균
                volume_ma5 = df['volume'].rolling(window=5).mean()
                volume_ma10 = df['volume'].rolling(window=10).mean()
                volume_ma20 = df['volume'].rolling(window=20).mean()
                
                # 볼륨 상대 강도 지표 (Volume RSI)
                volume_delta = df['volume'].diff()
                volume_gain = (volume_delta.where(volume_delta > 0, 0)).rolling(window=14).mean()
                volume_loss = (-volume_delta.where(volume_delta < 0, 0)).rolling(window=14).mean()
                # 0으로 나누기 방지를 위한 epsilon 추가
                epsilon = 1e-10
                volume_rs = volume_gain / (volume_loss + epsilon)
                volume_rsi = 100 - (100 / (1 + volume_rs))
                
                # 상대 볼륨 비율 (현재 볼륨 / 이동평균 볼륨)
                relative_volume = df['volume'].iloc[-1] / volume_ma20.iloc[-1] if not pd.isna(volume_ma20.iloc[-1]) and volume_ma20.iloc[-1] != 0 else None
                
                # 가격 상승 시 볼륨과 가격 하락 시 볼륨 비교
                price_diff = df['close'].diff()
                up_volume = np.where(price_diff > 0, df['volume'], 0)
                down_volume = np.where(price_diff < 0, df['volume'], 0)
                
                # 최근 10봉 기준
                recent_up_volume = np.sum(up_volume[-10:]) if len(up_volume) >= 10 else None
                recent_down_volume = np.sum(down_volume[-10:]) if len(down_volume) >= 10 else None
                # 0으로 나누기 방지
                up_down_ratio = recent_up_volume / (recent_down_volume + epsilon) if recent_down_volume is not None else None
                
                # 볼륨 트렌드 방향성
                volume_trend = None
                if not pd.isna(volume_ma5.iloc[-1]) and not pd.isna(volume_ma20.iloc[-1]):
                    if volume_ma5.iloc[-1] > volume_ma20.iloc[-1] * 1.2:
                        volume_trend = "strongly_increasing"
                    elif volume_ma5.iloc[-1] > volume_ma20.iloc[-1]:
                        volume_trend = "increasing"
                    elif volume_ma5.iloc[-1] < volume_ma20.iloc[-1] * 0.8:
                        volume_trend = "strongly_decreasing"
                    elif volume_ma5.iloc[-1] < volume_ma20.iloc[-1]:
                        volume_trend = "decreasing"
                    else:
                        volume_trend = "neutral"
                
                # 볼륨 프로파일 개선 (가격대별 거래량)
                price_range = df['high'].max() - df['low'].min()
                num_buckets = 10  # 더 많은 가격대로 분석
                bucket_size = price_range / num_buckets if price_range > 0 else 1
                
                # 가격대별 버킷 생성
                buckets = []
                for i in range(num_buckets):
                    low_price = df['low'].min() + i * bucket_size
                    high_price = low_price + bucket_size
                    bucket_volume = df[(df['low'] >= low_price) & (df['high'] <= high_price)]['volume'].sum()
                    buckets.append({
                        'price_range': [low_price, high_price],
                        'volume': bucket_volume
                    })
                
                # Point of Control (최대 거래량 가격대)
                # 빈 버킷이 아니고 모든 볼륨이 0이 아닌지 확인
                if buckets and any(bucket['volume'] > 0 for bucket in buckets):
                    max_volume_bucket = max(buckets, key=lambda x: x['volume'])
                    poc_price = sum(max_volume_bucket['price_range']) / 2 if max_volume_bucket['price_range'][1] - max_volume_bucket['price_range'][0] > 0 else None
                else:
                    max_volume_bucket = None
                    poc_price = None
                
                # 볼륨 프로파일 데이터 계산 (Value Area 추가)
                total_volume = sum(bucket['volume'] for bucket in buckets)
                value_area_threshold = total_volume * 0.7  # Value Area는 총 거래량의 70%
                
                # 거래량 순서로 버킷 정렬
                sorted_buckets = sorted(buckets, key=lambda x: x['volume'], reverse=True)
                
                # Value Area 계산
                cumulative_volume = 0
                value_area_buckets = []
                
                for bucket in sorted_buckets:
                    cumulative_volume += bucket['volume']
                    value_area_buckets.append(bucket)
                    if cumulative_volume >= value_area_threshold:
                        break
                
                # Value Area 가격 범위 결정
                if value_area_buckets:
                    value_area_prices = [price for bucket in value_area_buckets for price in bucket['price_range']]
                    value_area_high = max(value_area_prices)
                    value_area_low = min(value_area_prices)
                else:
                    value_area_high = None
                    value_area_low = None
                
                # 볼륨 프로파일 데이터 구성
                volume_profile_data = {
                    'poc': poc_price,  # Point of Control
                    'vah': value_area_high,  # Value Area High
                    'val': value_area_low,  # Value Area Low
                    'buckets': buckets,
                    'total_volume': total_volume
                }
            else:
                volume_trend = relative_volume = up_down_ratio = poc_price = None
                volume_rsi = volume_ma5 = volume_ma10 = volume_ma20 = None
                volume_profile_data = {
                    'poc': None,
                    'vah': None,
                    'val': None,
                    'buckets': [],
                    'total_volume': 0
                }
            
            # 16. MAT(평균 이동 시간대) 계산
            if len(df) >= 50:
                # 21EMA를 기준으로 MAT 계산
                ema21 = df['close'].ewm(span=21, adjust=False).mean()
                
                # 가격이 EMA 위아래에 있는 지속 시간 추적
                above_ema = df['close'] > ema21
                
                # 연속된 위/아래 상태 길이 계산
                above_stretches = []
                below_stretches = []
                
                current_stretch = 1
                current_state = above_ema.iloc[0]
                
                for i in range(1, len(above_ema)):
                    if above_ema.iloc[i] == current_state:
                        current_stretch += 1
                    else:
                        if current_state:
                            above_stretches.append(current_stretch)
                        else:
                            below_stretches.append(current_stretch)
                        current_stretch = 1
                        current_state = above_ema.iloc[i]
                
                # 마지막 스트레치 추가
                if current_state:
                    above_stretches.append(current_stretch)
                else:
                    below_stretches.append(current_stretch)
                
                # 평균 지속 시간 계산
                avg_above_duration = np.mean(above_stretches) if above_stretches else 0
                avg_below_duration = np.mean(below_stretches) if below_stretches else 0
                
                # 현재 상태 및 지속 기간
                current_above = above_ema.iloc[-1]
                current_duration = current_stretch
                
                # MAT 추세 방향 판단
                if len(above_stretches) >= 2 and len(below_stretches) >= 2:
                    recent_above_avg = np.mean(above_stretches[-3:]) if len(above_stretches) >= 3 else np.mean(above_stretches)
                    recent_below_avg = np.mean(below_stretches[-3:]) if len(below_stretches) >= 3 else np.mean(below_stretches)
                    
                    above_trend = recent_above_avg / avg_above_duration if avg_above_duration > 0 else 1
                    below_trend = recent_below_avg / avg_below_duration if avg_below_duration > 0 else 1
                    
                    if current_above:
                        if above_trend > 1.2:
                            mat_trend = "strongly_bullish"  # 상승 시간이 확장 중
                        elif above_trend > 1:
                            mat_trend = "bullish"  # 약한 상승 확장
                        elif above_trend < 0.8:
                            mat_trend = "weakening_bullish"  # 상승 시간이 축소 중
                        else:
                            mat_trend = "neutral_bullish"  # 상승 시간이 안정적
                    else:
                        if below_trend > 1.2:
                            mat_trend = "strongly_bearish"  # 하락 시간이 확장 중
                        elif below_trend > 1:
                            mat_trend = "bearish"  # 약한 하락 확장
                        elif below_trend < 0.8:
                            mat_trend = "weakening_bearish"  # 하락 시간이 축소 중
                        else:
                            mat_trend = "neutral_bearish"  # 하락 시간이 안정적
                else:
                    mat_trend = "insufficient_data"
                
                # MAT 데이터 구성
                mat_data = {
                    'average_above_duration': avg_above_duration,
                    'average_below_duration': avg_below_duration,
                    'current_state': 'above' if current_above else 'below',
                    'current_duration': current_duration,
                    'trend': mat_trend
                }
            else:
                mat_data = {
                    'average_above_duration': 0,
                    'average_below_duration': 0,
                    'current_state': None,
                    'current_duration': 0,
                    'trend': 'insufficient_data'
                }
            
            # 17. 다중 시간대 일관성 분석
            # 이 부분은 서로 다른 timeframe의 데이터가 필요하므로
            # 여기서는 플레이스홀더만 생성하고 실제 구현은 별도로 해야 함
            timeframe_consistency = {
                'direction_agreement': None,
                'trend_strength_consistency': None,
                'overall_alignment': None
            }
            
            # 16. VWAP (Volume Weighted Average Price) 계산
            # 세션별 VWAP - 기관 진입점 파악에 중요
            if 'volume' in df.columns and len(df) > 0:
                # 일일 VWAP (최근 24시간 또는 데이터 길이만큼)
                vwap_period = min(1440, len(df))  # 1440분 = 24시간
                recent_df = df.tail(vwap_period).copy()
                
                # Typical Price 계산
                typical_price = (recent_df['high'] + recent_df['low'] + recent_df['close']) / 3
                
                # VWAP 계산
                cumulative_tp_volume = (typical_price * recent_df['volume']).cumsum()
                cumulative_volume = recent_df['volume'].cumsum()
                
                # 0으로 나누기 방지
                cumulative_volume = cumulative_volume.replace(0, 1e-10)
                vwap = cumulative_tp_volume / cumulative_volume
                
                current_vwap = vwap.iloc[-1] if not vwap.empty else df['close'].iloc[-1]
                
                # VWAP 대비 현재 가격 위치
                vwap_deviation = ((df['close'].iloc[-1] - current_vwap) / current_vwap) * 100
                
                # VWAP 밴드 계산 (표준편차 기반)
                vwap_std = typical_price.std()
                vwap_upper = current_vwap + (2 * vwap_std)
                vwap_lower = current_vwap - (2 * vwap_std)
                
                vwap_data = {
                    'vwap': current_vwap,
                    'vwap_upper': vwap_upper,
                    'vwap_lower': vwap_lower,
                    'deviation_percent': vwap_deviation,
                    'price_position': 'above' if df['close'].iloc[-1] > current_vwap else 'below'
                }
            else:
                vwap_data = {
                    'vwap': df['close'].iloc[-1] if len(df) > 0 else 0,
                    'vwap_upper': 0,
                    'vwap_lower': 0,
                    'deviation_percent': 0,
                    'price_position': 'neutral'
                }
            
            # 17. CVD (Cumulative Volume Delta) - 매수/매도 압력 측정
            if len(df) >= 20:
                # 간소화된 CVD 계산 (가격 변화 기반)
                cvd_values = []
                for i in range(1, min(20, len(df))):
                    price_change = df['close'].iloc[-i] - df['close'].iloc[-i-1]
                    volume = df['volume'].iloc[-i] if 'volume' in df.columns else 1
                    
                    # 가격이 상승했으면 매수 압력, 하락했으면 매도 압력
                    if price_change > 0:
                        cvd_values.append(volume)
                    elif price_change < 0:
                        cvd_values.append(-volume)
                    else:
                        cvd_values.append(0)
                
                cumulative_cvd = sum(cvd_values)
                cvd_trend = 'bullish' if cumulative_cvd > 0 else 'bearish'
                
                # CVD 다이버전스 체크
                cvd_divergence = None
                if len(df) >= 30:
                    # 가격 추세와 CVD 추세 비교
                    price_trend = df['close'].iloc[-1] - df['close'].iloc[-30]
                    
                    if price_trend > 0 and cumulative_cvd < 0:
                        cvd_divergence = 'bearish'  # 가격 상승하나 매도 압력 우세
                    elif price_trend < 0 and cumulative_cvd > 0:
                        cvd_divergence = 'bullish'  # 가격 하락하나 매수 압력 우세
                
                cvd_data = {
                    'cumulative_delta': cumulative_cvd,
                    'trend': cvd_trend,
                    'divergence': cvd_divergence
                }
            else:
                cvd_data = {
                    'cumulative_delta': 0,
                    'trend': 'neutral',
                    'divergence': None
                }
            
            # 18. 시장 심리 지표
            # 기본 불공포 지수 계산 (간소화된 버전)
            if len(df) >= 30:
                # 변동성 요소
                volatility = (df['high'] / df['low'] - 1).rolling(window=30).mean().iloc[-1]
                volatility_norm = min(1, volatility * 100)  # 0-1 사이로 정규화
                
                # 추세 강도 요소
                if df['close'].iloc[-30] != 0:
                    trend_strength = abs(df['close'].iloc[-1] - df['close'].iloc[-30]) / df['close'].iloc[-30]
                else:
                    trend_strength = 0
                trend_strength_norm = min(1, trend_strength * 10)  # 0-1 사이로 정규화
                
                # 거래량 요소
                if df['volume'].iloc[-30:-5].mean() > 0:
                    volume_change = (df['volume'].iloc[-5:].mean() / df['volume'].iloc[-30:-5].mean()) - 1
                else:
                    volume_change = 0
                volume_change_norm = min(1, max(0, (volume_change + 0.2) * 2))  # -0.2 ~ 0.3 범위를 0-1로 정규화
                
                # RSI 요소 (극단값 확인)
                rsi_extreme = 0
                if not pd.isna(rsi14.iloc[-1]):
                    if rsi14.iloc[-1] <= 30:
                        rsi_extreme = (30 - rsi14.iloc[-1]) / 30  # 0-1 사이로 정규화
                    elif rsi14.iloc[-1] >= 70:
                        rsi_extreme = (rsi14.iloc[-1] - 70) / 30  # 0-1 사이로 정규화
                
                # 불공포 지수 (0: 극단적 공포, 1: 극단적 탐욕)
                fear_greed_index = (trend_strength_norm * 0.3 + 
                                    (1 - volatility_norm) * 0.3 + 
                                    volume_change_norm * 0.2 + 
                                    (1 - rsi_extreme) * 0.2)
                
                # 0-100 스케일로 변환
                fgi_value = int(fear_greed_index * 100)
                
                # 감정 레벨 분류
                if fgi_value <= 25:
                    fgi_level = "extreme_fear"
                elif fgi_value <= 40:
                    fgi_level = "fear"
                elif fgi_value <= 60:
                    fgi_level = "neutral"
                elif fgi_value <= 80:
                    fgi_level = "greed"
                else:
                    fgi_level = "extreme_greed"
            else:
                fgi_value = fgi_level = None
            
            # 17. 트렌드 지속성 및 강도 지표
            if len(df) >= 50:
                # 방향 이동 지수 (ADX) 활용
                adx_value = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else None
                
                # 추세 신뢰도 그룹
                trend_reliability = None
                if adx_value is not None:
                    if adx_value >= 30:
                        trend_reliability = "strong"
                    elif adx_value >= 20:
                        trend_reliability = "moderate"
                    else:
                        trend_reliability = "weak"
                
                # 추세 방향성 판별 (단순 방식)
                if ma50.iloc[-1] > ma200.iloc[-1] and ma20.iloc[-1] > ma50.iloc[-1]:
                    trend_direction = "strongly_bullish"
                elif ma50.iloc[-1] > ma200.iloc[-1]:
                    trend_direction = "bullish"
                elif ma50.iloc[-1] < ma200.iloc[-1] and ma20.iloc[-1] < ma50.iloc[-1]:
                    trend_direction = "strongly_bearish"
                elif ma50.iloc[-1] < ma200.iloc[-1]:
                    trend_direction = "bearish"
                else:
                    trend_direction = "neutral"
                
                # 추세 일관성 검사 (여러 이동평균선이 같은 방향으로 정렬)
                ma_list = [ma20.iloc[-1], ma50.iloc[-1], ma100.iloc[-1], ma200.iloc[-1]]
                ma_list = [ma for ma in ma_list if not pd.isna(ma)]
                
                if len(ma_list) >= 3:
                    is_ascending = all(ma_list[i] >= ma_list[i+1] for i in range(len(ma_list)-1))
                    is_descending = all(ma_list[i] <= ma_list[i+1] for i in range(len(ma_list)-1))
                    
                    if is_ascending:
                        ma_alignment = "bullish_aligned"
                    elif is_descending:
                        ma_alignment = "bearish_aligned"
                    else:
                        ma_alignment = "mixed"
                else:
                    ma_alignment = None
                
                # 스윙 고점/저점 분석
                swing_high_prices = []
                swing_low_prices = []
                
                for i in range(2, len(df)-2):
                    # 스윙 고점 조건: 현재 고가가 전후 2봉의 고가보다 높아야 함
                    if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                        df['high'].iloc[i] > df['high'].iloc[i-2] and
                        df['high'].iloc[i] > df['high'].iloc[i+1] and
                        df['high'].iloc[i] > df['high'].iloc[i+2]):
                        swing_high_prices.append(df['high'].iloc[i])
                    
                    # 스윙 저점 조건: 현재 저가가 전후 2봉의 저가보다 낮아야 함
                    if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                        df['low'].iloc[i] < df['low'].iloc[i-2] and
                        df['low'].iloc[i] < df['low'].iloc[i+1] and
                        df['low'].iloc[i] < df['low'].iloc[i+2]):
                        swing_low_prices.append(df['low'].iloc[i])
                
                # 최근 3개의 스윙 고점/저점만 유지
                recent_swing_highs = swing_high_prices[-3:] if len(swing_high_prices) >= 3 else swing_high_prices
                recent_swing_lows = swing_low_prices[-3:] if len(swing_low_prices) >= 3 else swing_low_prices
                
                # 스윙 고점/저점의 방향성 분석
                swings_analysis = None
                if len(recent_swing_highs) >= 2 and len(recent_swing_lows) >= 2:
                    highs_increasing = recent_swing_highs[-1] > recent_swing_highs[0]
                    lows_increasing = recent_swing_lows[-1] > recent_swing_lows[0]
                    
                    if highs_increasing and lows_increasing:
                        swings_analysis = "strong_uptrend"
                    elif not highs_increasing and not lows_increasing:
                        swings_analysis = "strong_downtrend"
                    elif highs_increasing and not lows_increasing:
                        swings_analysis = "expanding_range"
                    else:
                        swings_analysis = "contracting_range"
            else:
                trend_reliability = trend_direction = ma_alignment = swings_analysis = None
                recent_swing_highs = recent_swing_lows = None

            # 18. 하모닉 패턴 탐지 (기본 버전)
            harmonic_patterns = {}
            if len(df) >= 50:
                # 주요 스윙 포인트를 찾기 위한 간단한 알고리즘
                # (실제 구현에서는 더 정교한 피크 탐지 알고리즘을 사용할 수 있음)
                points = []
                for i in range(2, len(df)-2):
                    # 피크 (고점)
                    if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                        df['high'].iloc[i] > df['high'].iloc[i-2] and
                        df['high'].iloc[i] > df['high'].iloc[i+1] and
                        df['high'].iloc[i] > df['high'].iloc[i+2]):
                        points.append({"type": "peak", "price": df['high'].iloc[i], "index": i})
                    
                    # 저점
                    if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                        df['low'].iloc[i] < df['low'].iloc[i-2] and
                        df['low'].iloc[i] < df['low'].iloc[i+1] and
                        df['low'].iloc[i] < df['low'].iloc[i+2]):
                        points.append({"type": "trough", "price": df['low'].iloc[i], "index": i})
                
                # 최근 점들만 선택 (최대 5개)
                recent_points = sorted(points, key=lambda x: x["index"])[-5:]
                
                if len(recent_points) >= 4:
                    # 가트 나비 패턴 검사
                    # 가트 나비 패턴은 XABCD 패턴의 일종으로, 특정 피보나치 비율을 따름
                    # X->A: 일반적으로 큰 움직임
                    # A->B: X->A의 61.8% 되돌림
                    # B->C: A->B의 38.2-88.6% 확장
                    # C->D: B->C의 161.8-224.0% 확장
                    
                    # 간단한 구현을 위해 최근 4개 점만 사용 (ABCD)
                    if len(recent_points) >= 4:
                        a, b, c, d = recent_points[-4], recent_points[-3], recent_points[-2], recent_points[-1]
                        
                        # AB와 CD 레그가 같은 방향이고, BC가 반대 방향인지 확인
                        if ((a["type"] == c["type"]) and (b["type"] == d["type"]) and (a["type"] != b["type"])):
                            ab_move = abs(b["price"] - a["price"])
                            bc_move = abs(c["price"] - b["price"])
                            cd_move = abs(d["price"] - c["price"])
                            
                            # AB = CD 패턴 (AB 레그와 CD 레그가 거의 동일)
                            if 0.9 <= cd_move / ab_move <= 1.1:
                                harmonic_patterns["ab_cd"] = True
                            else:
                                harmonic_patterns["ab_cd"] = False
                            
                            # 가트 나비 패턴 (대략적인 검증, 실제로는 더 정확한 비율 확인 필요)
                            # BC가 AB의 38.2-88.6% 사이인지 확인
                            if 0.382 <= bc_move / ab_move <= 0.886:
                                # CD가 BC의 161.8-224.0% 사이인지 확인
                                if 1.618 <= cd_move / bc_move <= 2.24:
                                    harmonic_patterns["butterfly"] = True
                                else:
                                    harmonic_patterns["butterfly"] = False
                            else:
                                harmonic_patterns["butterfly"] = False
            
            # 결과 반환
            return {
                "rsi": {
                    "rsi7": rsi7.iloc[-1] if not pd.isna(rsi7.iloc[-1]) else None,
                    "rsi14": rsi14.iloc[-1] if not pd.isna(rsi14.iloc[-1]) else None,
                    "rsi21": rsi21.iloc[-1] if not pd.isna(rsi21.iloc[-1]) else None,
                    "divergence": rsi_divergence
                },
                "macd": {
                    "standard": {
                        "macd": macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else None,
                        "signal": signal.iloc[-1] if not pd.isna(signal.iloc[-1]) else None,
                        "histogram": histogram.iloc[-1] if not pd.isna(histogram.iloc[-1]) else None
                    },
                    "fast": {
                        "macd": macd_fast.iloc[-1] if not pd.isna(macd_fast.iloc[-1]) else None,
                        "signal": signal_fast.iloc[-1] if not pd.isna(signal_fast.iloc[-1]) else None,
                        "histogram": histogram_fast.iloc[-1] if not pd.isna(histogram_fast.iloc[-1]) else None
                    }
                },
                "bollinger_bands": {
                    "standard": {
                        "upper": upper_band_20.iloc[-1] if not pd.isna(upper_band_20.iloc[-1]) else None,
                        "middle": middle_band_20.iloc[-1] if not pd.isna(middle_band_20.iloc[-1]) else None,
                        "lower": lower_band_20.iloc[-1] if not pd.isna(lower_band_20.iloc[-1]) else None
                    },
                    "short": {
                        "upper": upper_band_10.iloc[-1] if not pd.isna(upper_band_10.iloc[-1]) else None,
                        "middle": middle_band_10.iloc[-1] if not pd.isna(middle_band_10.iloc[-1]) else None,
                        "lower": lower_band_10.iloc[-1] if not pd.isna(lower_band_10.iloc[-1]) else None
                    },
                    "long": {
                        "upper": upper_band_50.iloc[-1] if not pd.isna(upper_band_50.iloc[-1]) else None,
                        "middle": middle_band_50.iloc[-1] if not pd.isna(middle_band_50.iloc[-1]) else None,
                        "lower": lower_band_50.iloc[-1] if not pd.isna(lower_band_50.iloc[-1]) else None
                    }
                },
                "moving_averages": {
                    "simple": {
                        "ma5": ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else None,
                        "ma10": ma10.iloc[-1] if not pd.isna(ma10.iloc[-1]) else None,
                        "ma20": ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else None,
                        "ma50": ma50.iloc[-1] if not pd.isna(ma50.iloc[-1]) else None,
                        "ma100": ma100.iloc[-1] if not pd.isna(ma100.iloc[-1]) else None,
                        "ma200": ma200.iloc[-1] if not pd.isna(ma200.iloc[-1]) else None
                    },
                    "exponential": {
                        "ema9": ema9.iloc[-1] if not pd.isna(ema9.iloc[-1]) else None,
                        "ema21": ema21.iloc[-1] if not pd.isna(ema21.iloc[-1]) else None,
                        "ema55": ema55.iloc[-1] if not pd.isna(ema55.iloc[-1]) else None,
                        "ema200": ema200.iloc[-1] if not pd.isna(ema200.iloc[-1]) else None
                    }
                },
                "stochastic": {
                    "standard": {
                        "k": k_percent.iloc[-1] if not pd.isna(k_percent.iloc[-1]) else None,
                        "d": d_percent.iloc[-1] if not pd.isna(d_percent.iloc[-1]) else None,
                        "slow_d": slow_d.iloc[-1] if not pd.isna(slow_d.iloc[-1]) else None
                    },
                    "fast": {
                        "k": k_percent_9.iloc[-1] if not pd.isna(k_percent_9.iloc[-1]) else None,
                        "d": d_percent_9.iloc[-1] if not pd.isna(d_percent_9.iloc[-1]) else None,
                        "slow_d": slow_d_9.iloc[-1] if not pd.isna(slow_d_9.iloc[-1]) else None
                    }
                },
                "atr": {
                    "value": atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else None,
                    "percent": atr_percent.iloc[-1] if not pd.isna(atr_percent.iloc[-1]) else None
                },
                "obv": {
                    "value": obv.iloc[-1] if not pd.isna(obv.iloc[-1]) else None,
                    "ma20": obv_ma20.iloc[-1] if not pd.isna(obv_ma20.iloc[-1]) else None
                },
                "dmi": {
                    "plus_di": plus_di.iloc[-1] if not pd.isna(plus_di.iloc[-1]) else None,
                    "minus_di": minus_di.iloc[-1] if not pd.isna(minus_di.iloc[-1]) else None,
                    "adx": adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else None
                },
                "ichimoku": {
                    "conversion_line": conversion_line.iloc[-1] if not pd.isna(conversion_line.iloc[-1]) else None,
                    "base_line": base_line.iloc[-1] if not pd.isna(base_line.iloc[-1]) else None,
                    "leading_span_a": leading_span_a.iloc[-1] if not pd.isna(leading_span_a.iloc[-1]) else None,
                    "leading_span_b": leading_span_b.iloc[-1] if not pd.isna(leading_span_b.iloc[-1]) else None,
                    "cloud_position": cloud_position,
                    "tenkan_kijun_cross": tenkan_kijun_cross,
                    "cloud_thickness": cloud_thickness
                },
                "fibonacci": {
                    "levels": fib_levels,
                    "extensions": fib_ext_levels,
                    "closest_level": closest_level,
                    "is_uptrend": uptrend,
                    "recent_high": recent_high,
                    "recent_low": recent_low
                },
                "pivot_points": {
                    "pivot": pivot_point,
                    "s1": support1,
                    "s2": support2,
                    "s3": support3,
                    "r1": resistance1,
                    "r2": resistance2,
                    "r3": resistance3
                },
                "additional": {
                    "cmf": cmf_value,
                    "mpo": mpo_value,
                    "vwma": vwma_value,
                    "max_volume_price": max_volume_price
                },
                "patterns": pattern_data,
                "volume_analysis": {
                    "volume_trend": volume_trend,
                    "relative_volume": relative_volume,
                    "up_down_volume_ratio": up_down_ratio,
                    "volume_rsi": volume_rsi.iloc[-1] if volume_rsi is not None and not pd.isna(volume_rsi.iloc[-1]) else None,
                    "point_of_control": poc_price,
                    "volume_ma": {
                        "ma5": volume_ma5.iloc[-1] if volume_ma5 is not None and not pd.isna(volume_ma5.iloc[-1]) else None,
                        "ma10": volume_ma10.iloc[-1] if volume_ma10 is not None and not pd.isna(volume_ma10.iloc[-1]) else None,
                        "ma20": volume_ma20.iloc[-1] if volume_ma20 is not None and not pd.isna(volume_ma20.iloc[-1]) else None
                    }
                },
                "market_psychology": {
                    "fear_greed_index": fgi_value,
                    "sentiment": fgi_level
                },
                "trend_analysis": {
                    "reliability": trend_reliability,
                    "direction": trend_direction,
                    "ma_alignment": ma_alignment,
                    "swing_points": {
                        "recent_highs": recent_swing_highs,
                        "recent_lows": recent_swing_lows,
                        "pattern": swings_analysis
                    }
                },
                "harmonic_patterns": harmonic_patterns,
                "volume_profile": volume_profile_data,
                "mat": mat_data,
                "timeframe_consistency": timeframe_consistency,
                "vwap": vwap_data,
                "cvd": cvd_data
            }
        except Exception as e:
            print(f"Error calculating technical indicators: {str(e)}")
            traceback.print_exc()
            return {}

    async def analyze_and_execute(self, job_id=None, schedule_next=True):
        """기존 분석 및 실행 메서드 수정"""
        try:
            # 현재 시장 데이터 수집
            market_data = await self._collect_market_data()
            if not market_data:
                raise Exception("시장 데이터 수집 실패")

            # AI 분석 실행
            analysis_result = await self.ai_service.analyze_market_data(market_data)
            
            # 분석 결과 저장
            self.last_analysis_result = analysis_result
            print(f"\n=== 분석 결과 저장됨 ===\n{json.dumps(analysis_result, indent=2, default=str)}")
            
            # 분석 결과 브로드캐스트
            await self._broadcast_analysis_result(analysis_result)
            
            # AI 분석 결과 처리
            if analysis_result['action'] in ['ENTER_LONG', 'ENTER_SHORT']:
                # 포지션 진입 처리
                trade_result = await self._execute_trade(
                    analysis_result['action'],
                    analysis_result['position_size'],
                    analysis_result['leverage'],
                    analysis_result['stop_loss_roe'],
                    analysis_result['take_profit_roe']
                )
                
                if trade_result.get('success'):
                    # expected_minutes 그대로 적용 (기본값만 240으로 설정)
                    expected_minutes = analysis_result.get('expected_minutes', 240)
                    
                    # 모니터링 시작
                    await self._start_position_monitoring(
                        expected_minutes=expected_minutes,
                        monitoring_interval=self.monitoring_interval
                    )
            elif analysis_result['action'] == 'HOLD':
                # HOLD 결과 처리
                print("\n=== HOLD 포지션 결정됨 ===")
                if schedule_next:
                    # HOLD 액션인 경우 항상 60분 후에 재분석 (기존 30분에서 변경)
                    next_time = datetime.now() + timedelta(minutes=60)
                    print(f"HOLD 상태로 60분 후({next_time.strftime('%Y-%m-%d %H:%M:%S')})에 재분석을 수행합니다.")
                    await self._schedule_next_analysis(next_time)
            
            return analysis_result

        except Exception as e:
            print(f"분석 및 실행 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            # 오류 발생 시 30분 후 재분석 스케줄링
            await self._schedule_next_analysis_on_error(str(e))
            return {
                "action": "ERROR",
                "reason": str(e)
            }

    async def _schedule_next_analysis(self, next_time):
        """다음 분석 작업 스케줄링"""
        try:
            # 기존 분석 작업 취소
            self.scheduler.remove_all_jobs()
            
            # 새로운 분석 작업 스케줄링
            def async_job_wrapper(job_id):
                # 새로운 이벤트 루프 생성 및 설정
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # 비동기 함수를 동기적으로 실행
                    loop.run_until_complete(self.analyze_and_execute(job_id, schedule_next=True))
                except Exception as e:
                    print(f"분석 작업 실행 중 오류: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    
                    # 오류 발생 시 다른 스레드에서 30분 후 재분석 예약
                    def schedule_retry():
                        retry_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(retry_loop)
                        try:
                            retry_loop.run_until_complete(
                                self._schedule_next_analysis_on_error(f"작업 {job_id} 실행 중 오류: {str(e)}")
                            )
                        except Exception as retry_error:
                            print(f"재시도 예약 중 오류: {str(retry_error)}")
                        finally:
                            retry_loop.close()
                    
                    # 별도 스레드에서 재시도 예약 실행
                    import threading
                    retry_thread = threading.Thread(target=schedule_retry)
                    retry_thread.daemon = True
                    retry_thread.start()
                finally:
                    # 이벤트 루프 종료
                    loop.close()
            
            job_id = f'analysis_{int(time.time())}'
            self.scheduler.add_job(
                async_job_wrapper,
                'date',
                run_date=next_time,
                id=job_id,
                args=[job_id],
                misfire_grace_time=300  # 5분의 유예 시간 추가
            )
            
            print(f"\n=== 다음 분석 작업 예약됨 ===")
            print(f"예약 시간: {next_time}")
            print(f"Job ID: {job_id}")
            
        except Exception as e:
            print(f"다음 분석 작업 스케줄링 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()

    async def _schedule_next_analysis_on_error(self, error_message):
        """오류 발생 시 다음 분석 작업 스케줄링"""
        try:
            print(f"\n=== 오류 발생으로 인한 다음 분석 예약 ===")
            print(f"오류 내용: {error_message}")
            
            # 60분 후로 다음 분석 예약 (기존 1분에서 60분으로 변경)
            next_time = datetime.now() + timedelta(minutes=60)
            await self._schedule_next_analysis(next_time)
            
            # 에러 메시지 브로드캐스트
            if self.websocket_manager:
                error_data = {
                    "type": "ANALYSIS_ERROR",
                    "data": {
                        "message": str(error_message),
                        "timestamp": datetime.now().isoformat(),
                        "next_analysis_time": next_time.isoformat()
                    }
                }
                await self.websocket_manager.broadcast(error_data)
            
        except Exception as e:
            print(f"오류 복구를 위한 다음 분석 예약 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()

    async def _broadcast_analysis_result(self, result):
        """분석 결과를 웹소켓을 통해 브로드캐스트"""
        try:
            print("\n=== 분석 결과 브로드캐스트 시작 ===")
            print(f"전달받은 결과: {json.dumps(result, indent=2, default=str)}")
            
            # 웹소켓 매니저 확인
            if self.websocket_manager is None:
                print("웹소켓 매니저가 초기화되지 않았습니다.")
                return
            
            if not hasattr(self.websocket_manager, 'broadcast'):
                print("웹소켓 매니저에 broadcast 메서드가 없습니다.")
                return
            
            # 메시지 구성
            message = {
                "type": "ANALYSIS_RESULT",
                "event_type": "ANALYSIS_RESULT",
                "data": {
                    "action": result.get("action", "UNKNOWN"),
                    "position_size": result.get("position_size", 0.5),
                    "leverage": result.get("leverage", 5),
                    "stop_loss_roe": result.get("stop_loss_roe", 5.0),
                    "take_profit_roe": result.get("take_profit_roe", 10.0),
                    "expected_minutes": result.get("expected_minutes", 240),
                    "reason": result.get("reason", "No reason provided"),
                    "next_analysis_time": result.get("next_analysis_time", 
                        (datetime.now() + timedelta(minutes=30 if result.get("action") == "HOLD" else 240)).isoformat())
                },
                "timestamp": datetime.now().isoformat()
            }
            
            print(f"브로드캐스트할 메시지 구성됨:\n{json.dumps(message, indent=2, default=str)}")
            
            # 메시지 전송
            await self.websocket_manager.broadcast(message)
            print("분석 결과 브로드캐스트 완료")
            
        except Exception as e:
            print(f"분석 결과 브로드캐스트 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()

    async def _start_position_monitoring(self, expected_minutes, monitoring_interval):
        """포지션 모니터링 시작"""
        try:
            print(f"\n=== 포지션 모니터링 시작 ===")
            print(f"예상 유지 시간: {expected_minutes}분")
            print(f"모니터링 주기: {monitoring_interval}분")
            
            self.monitoring_start_time = datetime.now()
            self.monitoring_end_time = self.monitoring_start_time + timedelta(minutes=expected_minutes)
            
            print(f"모니터링 시작 시간: {self.monitoring_start_time}")
            print(f"모니터링 종료 예정 시간: {self.monitoring_end_time}")
            
            self.is_monitoring = True
            
            # 기존 모니터링 작업 취소
            if self.monitoring_job:
                self.monitoring_job.remove()
            
            # 새로운 모니터링 작업 스케줄링
            def async_job_wrapper(job_id):
                """비동기 함수를 실행하기 위한 래퍼 함수"""
                print(f"\n=== 주기적 모니터링 작업 실행 (Job ID: {job_id}) ===")
                
                try:
                    # 동기 메서드 직접 호출
                    self._monitor_position_periodically(job_id)
                except Exception as e:
                    print(f"모니터링 작업 실행 중 오류: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            self.monitoring_job = self.scheduler.add_job(
                async_job_wrapper,
                'interval',
                minutes=monitoring_interval,
                id=f'monitoring_{int(time.time())}',
                args=[f'monitoring_{int(time.time())}']
            )
            
            print(f"모니터링 작업이 스케줄링되었습니다. (Job ID: {self.monitoring_job.id})")
            
        except Exception as e:
            print(f"모니터링 시작 중 오류: {str(e)}")
            self.is_monitoring = False

    def _monitor_position_periodically(self, job_id):
        """주기적 포지션 모니터링 실행"""
        try:
            if not self.is_monitoring:
                print("모니터링이 중지되었습니다.")
                return
                
            print(f"\n=== 주기적 모니터링 실행 (Job ID: {job_id}) ===")
            
            # 현재 시간이 모니터링 종료 시간을 초과했는지 확인
            current_time = datetime.now()
            
            # expected_minutes 계산 (모니터링 시작 시간과 종료 시간의 차이)
            if self.monitoring_start_time and self.monitoring_end_time:
                expected_minutes = (self.monitoring_end_time - self.monitoring_start_time).total_seconds() / 60
                print(f"설정된 예상 유지 시간: {expected_minutes:.1f}분")
            
            print(f"현재 시간: {current_time}")
            print(f"모니터링 종료 시간: {self.monitoring_end_time}")
            print(f"남은 시간: {(self.monitoring_end_time - current_time).total_seconds() / 60:.2f}분")
            
            if current_time > self.monitoring_end_time:
                print("예상 유지 시간이 종료되었습니다. 포지션을 청산합니다.")
                # 비동기 함수를 동기적으로 실행하기 위한 이벤트 루프 생성
                close_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(close_loop)
                try:
                    close_loop.run_until_complete(
                        self._force_close_position(job_id)
                    )
                finally:
                    close_loop.close()
                return
            
            # 현재 시장 데이터 수집
            # 비동기 함수를 동기적으로 실행하기 위한 이벤트 루프 생성
            market_data_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(market_data_loop)
            try:
                market_data = market_data_loop.run_until_complete(
                    self._collect_market_data()
                )
            finally:
                market_data_loop.close()
            
            # 현재 포지션 정보 수집
            position_info = self._get_position_info()
            
            if not position_info:
                print("활성 포지션이 없습니다. 모니터링을 중단합니다.")
                self._stop_monitoring()
                return
            
            # AI 모니터링 분석 실행
            # 비동기 함수를 동기적으로 실행하기 위한 이벤트 루프 생성
            monitor_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(monitor_loop)
            try:
                monitoring_result = monitor_loop.run_until_complete(
                    self.ai_service.monitor_position(market_data, position_info)
                )
            finally:
                monitor_loop.close()
            
            # 분석 결과에 따른 처리
            if monitoring_result['action'] == 'CLOSE_POSITION':
                print("AI가 포지션 청산을 권장합니다.")
                # 비동기 함수를 동기적으로 실행하기 위한 이벤트 루프 생성
                close_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(close_loop)
                try:
                    close_loop.run_until_complete(
                        self._force_close_position(job_id)
                    )
                finally:
                    close_loop.close()
            else:
                print("AI가 포지션 유지를 권장합니다.")
                
            # 웹소켓으로 모니터링 결과 전송
            # 비동기 함수를 동기적으로 실행하기 위한 이벤트 루프 생성
            broadcast_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(broadcast_loop)
            try:
                broadcast_loop.run_until_complete(
                    self._broadcast_monitoring_result(monitoring_result)
                )
            finally:
                broadcast_loop.close()
            
        except Exception as e:
            print(f"모니터링 실행 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()

    def _stop_monitoring(self):
        """모니터링 중지"""
        try:
            if self.monitoring_job:
                self.monitoring_job.remove()
                self.monitoring_job = None
            
            self.is_monitoring = False
            self.monitoring_start_time = None
            self.monitoring_end_time = None
            
            print("모니터링이 중지되었습니다.")
            
        except Exception as e:
            print(f"모니터링 중지 중 오류: {str(e)}")

    def _get_position_info(self):
        """현재 포지션 정보 가져오기"""
        try:
            # 캐싱된 포지션 정보를 가져옴
            formatted_positions = self.current_positions
            
            if not formatted_positions:
                # 포지션이 없는 경우
                return {
                    'size': 0, 
                    'entry_price': 0, 
                    'unrealized_pnl': 0, 
                    'side': 'none',
                    'roe': 0,
                    'leverage': 1,
                    'take_profit_roe': 5.0,  # 기본값
                    'stop_loss_roe': 2.0,    # 기본값
                    'entry_time': ''
                }
            
            # 첫 번째 포지션 정보 반환
            return formatted_positions[0]
        
        except Exception as e:
            print(f"포지션 정보 가져오기 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 오류 발생 시 기본 포지션 정보 반환
            return {
                'size': 0, 
                'entry_price': 0, 
                'unrealized_pnl': 0, 
                'side': 'none',
                'roe': 0,
                'leverage': 1,
                'take_profit_roe': 5.0,  # 기본값
                'stop_loss_roe': 2.0,    # 기본값
                'entry_time': ''
            }

    async def _broadcast_monitoring_result(self, result):
        """모니터링 결과를 웹소켓으로 전송"""
        try:
            if self.websocket_manager:
                message = {
                    "type": "MONITORING_RESULT",
                    "data": {
                        "action": result['action'],
                        "reason": result['reason'],
                        "timestamp": datetime.now().isoformat()
                    }
                }
                await self.websocket_manager.broadcast(message)
                
        except Exception as e:
            print(f"모니터링 결과 전송 중 오류: {str(e)}")

    def cancel_all_jobs(self):
        """모든 작업 취소 (STOP AUTO TRADING 시 호출)"""
        try:
            # 기존 작업 취소
            self.scheduler.remove_all_jobs()
            
            # 모니터링 중지
            self._stop_monitoring()
            
            # AI 스레드 초기화
            self.ai_service.reset_thread()
            
            print("모든 작업이 취소되었습니다.")
            
        except Exception as e:
            print(f"작업 취소 중 오류: {str(e)}")

    async def _restart_trading_safe(self):
        """안전한 트레이딩 재시작 처리"""
        try:
            print("\n=== 트레이딩 재시작 시도 ===")
            
            # 새로운 분석 실행
            result = await self.analyze_and_execute()
            
            if result['success']:
                print("트레이딩 재시작 성공")
                return result
            else:
                print(f"트레이딩 재시작 실패: {result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            print(f"트레이딩 재시작 중 에러: {str(e)}")
            return None

    def _is_stop_loss_triggered(self, initial_position, current_position):
        """
        스탑로스/테이크프로핏으로 인한 청산 감지 - 사용하지 않음
        포지션 청산 감지는 포지션 모니터링 스레드에서만 처리
        """
        # 항상 False 반환 - 이 메서드를 통한 청산 감지 비활성화
        return False

    def _update_position_state(self, position_data):
        """포지션 상태 업데이트 - 포지션 정보만 업데이트하고 청산 감지는 하지 않음"""
        # time 모듈 임포트
        import time
        
        # 로그 출력 제한을 위한 시간 체크
        current_time = time.time()
        should_log = not hasattr(self, '_last_position_log_time') or (current_time - getattr(self, '_last_position_log_time', 0) >= 30)
        
        if should_log:
            print("\n=== 포지션 데이터 업데이트 ===")
            print(f"원본 포지션 데이터: {position_data}")
            # 로그 시간 업데이트
            self._last_position_log_time = current_time
        
        # API 오류 또는 잘못된 데이터 처리
        if not position_data or not isinstance(position_data, dict):
            if should_log:
                print(f"포지션 데이터가 없거나 올바르지 않은 형식입니다: {position_data}")
            return None
            
        if 'code' in position_data and position_data['code'] == 'ERROR':
            if should_log:
                print(f"포지션 데이터 가져오기 실패: {position_data.get('msg', '알 수 없는 오류')}")
            # 429 에러(Too Many Requests)인 경우 잠시 대기
            if 'msg' in position_data and '429' in position_data['msg']:
                if should_log:
                    print("API 요청 제한 초과. 1초 대기 후 재시도합니다.")
                time.sleep(1)  # 이미 임포트된 time 모듈 사용
                try:
                    # 재시도
                    position_data = self.bitget.get_positions()
                    if should_log:
                        print(f"재시도 결과: {position_data}")
                except Exception as e:
                    if should_log:
                        print(f"재시도 중 오류 발생: {str(e)}")
                    return None
            else:
                return None
        
        # 포지션 데이터 처리
        current_position = None
        
        with self._position_lock:
            if 'data' not in position_data:
                if should_log:
                    print("포지션 데이터에 'data' 필드가 없습니다.")
                return None
                
            # BTCUSDT 포지션 찾기
            btc_positions = []
            try:
                btc_positions = [pos for pos in position_data['data'] 
                               if isinstance(pos, dict) and 
                               pos.get('symbol') == 'BTCUSDT' and 
                               float(pos.get('total', 0)) != 0]
            except Exception as e:
                if should_log:
                    print(f"포지션 데이터 처리 중 오류: {str(e)}")
                    print(f"position_data['data']: {position_data['data']}")
                return None
            
            if btc_positions:
                pos = btc_positions[0]
                try:
                    size = float(pos.get('total', 0))
                    entry_price = float(pos.get('averageOpenPrice', 0))
                    unrealized_pnl = float(pos.get('unrealizedPL', 0))
                    side = pos.get('holdSide', '').lower()
                    
                    # 포지션 정보 저장
                    current_position = {
                        'size': size,
                        'entry_price': entry_price,
                        'unrealized_pnl': unrealized_pnl,
                        'side': side
                    }
                    
                    if should_log:
                        print(f"포지션 정보 업데이트 완료: {current_position}")
                    
                    # 포지션 진입 시간 기록 (없는 경우에만)
                    if not self._position_entry_time:
                        self._position_entry_time = datetime.now()
                        self._position_entry_price = entry_price
                        self._last_position_side = side
                        print(f"새로운 포지션 진입 감지: {side} 포지션, 진입가: {entry_price}, 진입 시간: {self._position_entry_time}")
                except Exception as e:
                    if should_log:
                        print(f"포지션 정보 변환 중 오류: {str(e)}")
                    return None
                
                return current_position
            
            # 포지션이 없는 경우
            if should_log:
                print("활성화된 BTCUSDT 포지션이 없습니다.")
            return None

    def _check_liquidation_reason(self, current_price):
        """포지션 청산 원인 확인"""
        if not hasattr(self, '_position_entry_price') or not self._position_entry_price or not hasattr(self, '_last_position_side') or not self._last_position_side:
            return "알 수 없음"
        
        # 수동 청산 여부 확인 플래그 추가
        if hasattr(self, '_manual_liquidation') and self._manual_liquidation:
            print("수동 청산 플래그가 설정되어 있습니다.")
            # 수동 청산 플래그 초기화
            self._manual_liquidation = False
            return "수동 청산"
        
        # 청산 원인 판단 로직
        if hasattr(self, '_stop_loss_price') and self._stop_loss_price and self._last_position_side == "long" and current_price <= self._stop_loss_price:
            print(f"손절가 도달 감지: 현재가({current_price}) <= 손절가({self._stop_loss_price})")
            return "손절가 도달"
        elif hasattr(self, '_stop_loss_price') and self._stop_loss_price and self._last_position_side == "short" and current_price >= self._stop_loss_price:
            print(f"손절가 도달 감지: 현재가({current_price}) >= 손절가({self._stop_loss_price})")
            return "손절가 도달"
        elif hasattr(self, '_take_profit_price') and self._take_profit_price and self._last_position_side == "long" and current_price >= self._take_profit_price:
            print(f"익절가 도달 감지: 현재가({current_price}) >= 익절가({self._take_profit_price})")
            return "익절가 도달"
        elif hasattr(self, '_take_profit_price') and self._take_profit_price and self._last_position_side == "short" and current_price <= self._take_profit_price:
            print(f"익절가 도달 감지: 현재가({current_price}) <= 익절가({self._take_profit_price})")
            return "익절가 도달"
        elif hasattr(self, '_expected_close_time') and self._expected_close_time and datetime.now() >= self._expected_close_time:
            print(f"예상 종료 시간 도달 감지: 현재 시간({datetime.now()}) >= 예상 종료 시간({self._expected_close_time})")
            return "예상 종료 시간 도달"
        else:
            # 청산 원인을 명확히 파악할 수 없는 경우
            print(f"청산 원인 분석: 현재가={current_price}, 진입가={self._position_entry_price}, 방향={self._last_position_side}")
            stop_loss_price = self._stop_loss_price if hasattr(self, '_stop_loss_price') else None
            take_profit_price = self._take_profit_price if hasattr(self, '_take_profit_price') else None
            print(f"손절가={stop_loss_price}, 익절가={take_profit_price}")
            
            # 가격 변동 폭 계산
            price_change = abs(current_price - self._position_entry_price) / self._position_entry_price * 100
            
            if price_change > 5:  # 5% 이상 가격 변동
                direction = "상승" if current_price > self._position_entry_price else "하락"
                return f"급격한 가격 {direction} (변동률: {price_change:.2f}%)"
            else:
                return "수동 청산 또는 거래소 청산"

    def _update_position_info(self, position_data):
        """포지션 정보 업데이트"""
        try:
            position_info = {
                'size': float(position_data.get('total', 0)),
                'entry_price': float(position_data.get('openPriceAvg', 0)),
                'unrealized_pnl': float(position_data.get('unrealizedPL', 0)),
                'side': position_data.get('holdSide', '').lower()
            }
            
            # takeProfit과 stopLoss 값 추가 (이미 ROE 값으로 존재)
            take_profit = position_data.get('takeProfit', '')
            stop_loss = position_data.get('stopLoss', '')
            
            # 빈 문자열이거나 '0'인 경우 기본값 설정
            if not take_profit or take_profit == '0' or take_profit == '':
                position_info['take_profit_roe'] = 5.0  # 기본값
            else:
                # 문자열을 float로 변환
                position_info['take_profit_roe'] = float(take_profit)
            
            if not stop_loss or stop_loss == '0' or stop_loss == '':
                position_info['stop_loss_roe'] = 2.0  # 기본값 
            else:
                # 문자열을 float로 변환
                position_info['stop_loss_roe'] = float(stop_loss)
            
            # 현재 ROE 계산 또는 추가
            leverage = float(position_data.get('leverage', 1))
            mark_price = float(position_data.get('markPrice', 0))
            entry_price = float(position_data.get('openPriceAvg', 0))
            
            if entry_price > 0 and mark_price > 0:
                if position_info['side'] == 'long':
                    roe = ((mark_price / entry_price) - 1) * 100 * leverage
                else:  # short
                    roe = ((entry_price / mark_price) - 1) * 100 * leverage
                position_info['roe'] = round(roe, 2)
            else:
                position_info['roe'] = 0.0
            
            # 기타 중요 정보 추가
            position_info['leverage'] = leverage
            position_info['entry_time'] = position_data.get('cTime', '')
            
            print(f"포지션 정보 업데이트 완료: {position_info}")
            return position_info
            
        except Exception as e:
            print(f"포지션 정보 업데이트 실패: {str(e)}")
            # 기본 포지션 정보 반환
            return {
                'size': 0,
                'entry_price': 0,
                'unrealized_pnl': 0,
                'side': 'none',
                'take_profit_roe': 5.0,  # 기본값
                'stop_loss_roe': 2.0,    # 기본값
                'roe': 0.0,
                'leverage': 1,
                'entry_time': ''
            }

    def _detect_position_changes(self, position_info):
        """포지션 변경 감지 (진입/청산)"""
        try:
            with self._position_lock:
                # 포지션 크기 확인
                current_size = position_info.get('size', 0)
                current_side = position_info.get('side')
                current_entry_price = position_info.get('entry_price', 0)
                
                # 새로운 포지션 진입 감지
                if current_size > 0 and current_side and not self._position_entry_time:
                    self._position_entry_time = datetime.now()
                    self._position_entry_price = current_entry_price
                    self._last_position_side = current_side
                    print(f"새로운 포지션 진입 감지: {current_side} 포지션, 진입가: {current_entry_price}, 진입 시간: {self._position_entry_time}")
                
                # 포지션 청산 감지
                elif self._position_entry_time and current_size == 0:
                    # 이미 청산이 감지되었는지 확인
                    if hasattr(self, '_liquidation_detected') and self._liquidation_detected:
                        # 30초마다 로그 출력
                        current_time = time.time()
                        if (current_time - self._last_position_log_time) < self._position_log_interval:
                            return
                        self._last_position_log_time = current_time
                        print("이미 청산이 감지되었습니다. 중복 처리를 방지합니다.")
                        
                        # 수동 청산 후 일정 시간(5분)이 지났는데도 플래그가 초기화되지 않았다면 강제 초기화
                        if hasattr(self, '_manual_liquidation') and self._manual_liquidation:
                            liquidation_time = getattr(self, '_liquidation_time', None)
                            if liquidation_time and (datetime.now() - liquidation_time).total_seconds() > 300:  # 5분
                                print("청산 감지 플래그가 5분 이상 유지되어 강제 초기화합니다.")
                                self.reset_liquidation_flag()
                        return
                    
                    # 현재 가격 조회
                    ticker = self.bitget.get_ticker()
                    current_price = 0
                    if ticker and 'data' in ticker:
                        if isinstance(ticker['data'], list) and ticker['data']:
                            current_price = float(ticker['data'][0].get('lastPr', 0))
                        elif isinstance(ticker['data'], dict):
                            current_price = float(ticker['data'].get('lastPr', 0))
                    
                    # 수동 청산 여부 확인
                    is_manual_liquidation = False
                    if hasattr(self, '_manual_liquidation') and self._manual_liquidation:
                        liquidation_reason = "수동 청산"
                        is_manual_liquidation = True
                        print("수동 청산이 감지되었습니다.")
                    else:
                        # 자동 청산 원인 확인
                        liquidation_reason = self._check_liquidation_reason(current_price)
                    
                    print(f"\n=== 포지션 청산 감지 ===")
                    print(f"청산 시간: {datetime.now().isoformat()}")
                    print(f"진입 시간: {self._position_entry_time.isoformat() if self._position_entry_time else 'None'}")
                    print(f"진입가: {self._position_entry_price}")
                    print(f"청산가: {current_price}")
                    print(f"포지션 방향: {self._last_position_side}")
                    print(f"청산 원인: {liquidation_reason}")
                    print(f"수동 청산 여부: {is_manual_liquidation}")
                    
                    # 청산 감지 플래그 설정
                    self._liquidation_detected = True
                    self._liquidation_time = datetime.now()
                    self._liquidation_reason = liquidation_reason
                    self._liquidation_price = current_price
                    print("청산 감지 플래그 설정됨 - 포지션 모니터링 스레드에서 처리됩니다.")
                    
                    # 청산 정보 저장
                    liquidation_info = {
                        "entry_time": self._position_entry_time.isoformat() if self._position_entry_time else None,
                        "close_time": datetime.now().isoformat(),
                        "entry_price": self._position_entry_price,
                        "exit_price": current_price,
                        "side": self._last_position_side,
                        "reason": liquidation_reason
                    }
                    
                    # 청산 후 상태 초기화
                    self._position_entry_time = None
                    self._expected_close_time = None
                    self._position_entry_price = None
                    self._stop_loss_price = None
                    self._take_profit_price = None
                    
                    # 기존 예약 작업 취소
                    self._cancel_scheduled_analysis()
                    
                    # 60분 후 새로운 분석 예약
                    next_analysis_time = datetime.now() + timedelta(minutes=60)
                    new_job_id = str(uuid.uuid4())
                    
                    
                    print(f"\n=== 포지션 청산 감지 후 새로운 분석 예약 ===")
                    print(f"예약 시간: {next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"작업 ID: {new_job_id}")
                    
                    # 비동기 함수를 실행하기 위한 래퍼 함수 정의
                    def async_job_wrapper(job_id):
                        """비동기 함수를 실행하기 위한 래퍼 함수"""
                        print(f"\n=== 포지션 청산 후 자동 재시작 작업 실행 (ID: {job_id}) ===")
                        print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            # 비동기 함수 실행을 create_task로 감싸서 실행
                            task = loop.create_task(self.analyze_and_execute(job_id, schedule_next=True))
                            loop.run_until_complete(task)
                        except Exception as e:
                            print(f"자동 재시작 작업 실행 중 오류: {str(e)}")
                            import traceback
                            traceback.print_exc()
                        finally:
                            loop.close()
                    
                    # 스케줄러에 작업 등록
                    self.scheduler.add_job(
                        async_job_wrapper,
                        'date',
                        run_date=next_analysis_time,
                        args=[new_job_id],
                        id=new_job_id,
                        replace_existing=True
                    )
                    
                    # 활성 작업 목록에 추가
                    self.active_jobs[new_job_id] = {
                        "type": JobType.ANALYSIS,  # "analysis" 대신 JobType.ANALYSIS 사용
                        "scheduled_time": next_analysis_time.isoformat(),
                        "reason": "포지션 청산 후 자동 재시작"
                    }
                    
                    # 청산 메시지 웹소켓으로 전송
                    try:
                        if self.websocket_manager is not None:
                            # 비동기 함수를 동기적으로 실행하기 위한 이벤트 루프 생성
                            broadcast_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(broadcast_loop)
                            try:
                                broadcast_loop.run_until_complete(self.websocket_manager.broadcast({
                                    "type": "liquidation",
                                    "event_type": "LIQUIDATION",
                                    "data": {
                                        "success": True,
                                        "message": "포지션이 청산되었습니다. 60분 후 새로운 분석이 실행됩니다.",
                                        "liquidation_info": liquidation_info,
                                        "next_analysis": {
                                            "job_id": new_job_id,
                                            "scheduled_time": next_analysis_time.isoformat(),
                                            "reason": "포지션 청산 후 자동 재시작",
                                            "expected_minutes": 60
                                        }
                                    },
                                    "timestamp": datetime.now().isoformat()
                                }))
                            except Exception as e:
                                print(f"청산 메시지 전송 중 오류: {str(e)}")
                            finally:
                                broadcast_loop.close()
                    except Exception as e:
                        print(f"웹소켓 메시지 전송 중 오류: {str(e)}")
                            
                    except Exception as e:
                        print(f"청산 후 새 분석 예약 중 오류: {str(e)}")
                        import traceback
                        traceback.print_exc()
                
        except Exception as e:
            print(f"포지션 변경 감지 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
        
        except Exception as e:
            print(f"포지션 변경 감지 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()

    async def _execute_trade(self, action, position_size=0.5, leverage=5, stop_loss_roe=None, take_profit_roe=None):
        """거래 실행"""
        try:
            # 계좌 정보 조회
            account_info = self.bitget.get_account_info()
            print(f"계좌 정보 응답: {account_info}")
            
            if not account_info or 'data' not in account_info:
                raise Exception("계좌 정보 조회 실패")
            
            # 사용 가능한 USDT 추출
            available_usdt = float(account_info['data'].get('available', 0))
            
            if available_usdt <= 0:
                raise Exception(f"사용 가능한 USDT가 없습니다: {available_usdt}")
            
            # 현재 가격 조회
            ticker = self.bitget.get_ticker()
            if not ticker or 'data' not in ticker:
                raise Exception("현재 가격 조회 실패")
            
            print(f"티커 응답: {ticker}")
            
            # 현재 가격 추출
            current_price = float(ticker['data'][0]['lastPr']) if isinstance(ticker['data'], list) else float(ticker['data'].get('lastPr', 0))
            
            if current_price <= 0:
                raise Exception("유효하지 않은 현재 가격")
            
            print("\n=== 계좌 정보 ===")
            print(f"사용 가능한 USDT: {available_usdt}")
            print(f"현재 BTC 가격: {current_price} USDT")
            
            # 수수료와 슬리피지를 고려한 사용 가능 금액 계산 (95%)
            usable_amount = available_usdt * 0.95
            
            # 실제 진입할 금액 계산 (position_size 비율만큼)
            entry_amount = usable_amount * position_size
            
            
            # 레버리지를 적용한 최종 포지션 크기 계산
            final_position_size = entry_amount * leverage
            
            print(f"\n=== 거래 상세 ===")
            print(f"Action: {action}")
            print(f"현재 BTC 가격: {current_price} USDT")
            print(f"계좌 잔고(USDT): {available_usdt}")
            print(f"수수료 제외 금액(95%): {usable_amount}")
            print(f"실제 진입 금액({position_size*100}%): {entry_amount}")
            print(f"레버리지: {leverage}")
            print(f"최종 포지션 크기(USDT): {final_position_size}")
            print(f"최종 포지션 크기(BTC): {final_position_size/current_price}")
            
            # ROE 값 조정
            original_stop_loss_roe = stop_loss_roe if stop_loss_roe is not None else 5.0
            original_take_profit_roe = take_profit_roe if take_profit_roe is not None else 10.0
            
            # 레버리지에 따른 동적 조정값 계산 (0.15 * 레버리지)
            leverage_adjustment = 0.1 * leverage
            
            # Stop Loss는 AI 답변보다 leverage_adjustment 더 크게, Take Profit은 leverage_adjustment 작게 조정
            adjusted_stop_loss_roe = original_stop_loss_roe + leverage_adjustment
            adjusted_take_profit_roe = original_take_profit_roe - leverage_adjustment
            
            print("\n=== ROE 값 조정 ===")
            print(f"레버리지: {leverage}x")
            print(f"조정값 (0.1 * 레버리지): {leverage_adjustment}%")
            print(f"Stop Loss ROE: {original_stop_loss_roe}% -> {adjusted_stop_loss_roe}%")
            print(f"Take Profit ROE: {original_take_profit_roe}% -> {adjusted_take_profit_roe}%")
            
            # API 요청 간격 제한 (0.2초)
            await asyncio.sleep(0.2)
            print(f"API 요청 간격 제한: 0.20초 대기")
            
            # 예상 종료 시간 계산
            expected_minutes = 60  # 기본값
            if action in ['ENTER_LONG', 'ENTER_SHORT']:
                # 분석 결과에서 expected_minutes 가져오기
                if hasattr(self, 'last_analysis_result') and self.last_analysis_result is not None:
                    if isinstance(self.last_analysis_result, dict):
                        expected_minutes = self.last_analysis_result.get('expected_minutes', 60)
                    elif hasattr(self.last_analysis_result, 'analysis') and isinstance(self.last_analysis_result.analysis, dict):
                        expected_minutes = self.last_analysis_result.analysis.get('expected_minutes', 60)
                    else:
                        print(f"last_analysis_result 형식 오류: {type(self.last_analysis_result)}")
                else:
                    print("last_analysis_result가 없거나 None입니다. 기본값 60분 사용.")
            
            expected_close_time = datetime.now() + timedelta(minutes=expected_minutes)
            print(f"Expected close time: {expected_close_time}")
            
            # 거래 실행
            if action == 'ENTER_LONG':
                order_result = self.bitget.place_order(
                    size=str(final_position_size/current_price),
                    side="buy",
                    expected_minutes=expected_minutes,
                    leverage=leverage,
                    stop_loss_roe=adjusted_stop_loss_roe,
                    take_profit_roe=adjusted_take_profit_roe
                )
            elif action == 'ENTER_SHORT':
                order_result = self.bitget.place_order(
                    size=str(final_position_size/current_price),
                    side="sell",
                    expected_minutes=expected_minutes,
                    leverage=leverage,
                    stop_loss_roe=adjusted_stop_loss_roe,
                    take_profit_roe=adjusted_take_profit_roe
                )
            else:
                raise Exception(f"지원하지 않는 액션: {action}")
            
            print(f"주문 결과: {order_result}")
            
            # 주문 결과 확인
            if order_result and 'code' in order_result and order_result['code'] == '00000':
                print(f"거래 성공: {order_result}")
                
                # 포지션 정보 업데이트
                self._position_entry_time = datetime.now()
                self._expected_close_time = expected_close_time
                self._position_entry_price = current_price
                self._last_position_side = 'long' if action == 'ENTER_LONG' else 'short'
                
                # 스탑로스/익절가 설정
                if stop_loss_roe and stop_loss_roe > 0:
                    if action == 'ENTER_LONG':
                        self._stop_loss_price = current_price * (1 - stop_loss_roe / 100 / leverage)
                    else:
                        self._stop_loss_price = current_price * (1 + stop_loss_roe / 100 / leverage)
                    print(f"스탑로스 가격 설정: {self._stop_loss_price}")
                
                if take_profit_roe and take_profit_roe > 0:
                    if action == 'ENTER_LONG':
                        self._take_profit_price = current_price * (1 + take_profit_roe / 100 / leverage)
                    else:
                        self._take_profit_price = current_price * (1 - take_profit_roe / 100 / leverage)
                    print(f"익절 가격 설정: {self._take_profit_price}")
                
                # 스탑로스 모니터링 시작
                self._start_stop_loss_monitoring()
                
                # expected_minutes 시간에 자동 청산 작업 예약 (수정된 부분)
                force_close_job_id = f"force_close_{int(time.time())}"
                
                # 이전에 예약된 FORCE_CLOSE 작업이 있으면 취소
                self._cancel_force_close_job()
                
                print(f"\n=== 자동 청산 작업 예약 ===")
                print(f"예약 시간: {expected_close_time}")
                print(f"Job ID: {force_close_job_id}")
                
                # 비동기 함수를 실행하기 위한 래퍼 함수
                def force_close_wrapper(job_id):
                    """비동기 강제 청산 함수를 실행하기 위한 래퍼"""
                    print(f"\n=== 강제 청산 래퍼 실행 (ID: {job_id}) ===")
                    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # 새로운 이벤트 루프 생성 및 설정
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        # 비동기 함수를 동기적으로 실행
                        loop.run_until_complete(self._force_close_position(job_id))
                    except Exception as e:
                        print(f"강제 청산 실행 중 오류: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        
                        # 오류 발생 시 30분 후 재분석 예약
                        def schedule_retry():
                            retry_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(retry_loop)
                            try:
                                retry_loop.run_until_complete(
                                    self._schedule_next_analysis_on_error(f"강제 청산 작업 {job_id} 실행 중 오류: {str(e)}")
                                )
                            except Exception as retry_error:
                                print(f"재시도 예약 중 오류: {str(retry_error)}")
                            finally:
                                retry_loop.close()
                        
                        # 별도 스레드에서 재시도 예약 실행
                        import threading
                        retry_thread = threading.Thread(target=schedule_retry)
                        retry_thread.daemon = True
                        retry_thread.start()
                    finally:
                        # 이벤트 루프 종료
                        loop.close()
                
                # 스케줄러에 강제 청산 작업 추가
                self.scheduler.add_job(
                    force_close_wrapper,
                    'date',
                    run_date=expected_close_time,
                    id=force_close_job_id,
                    args=[force_close_job_id],
                    misfire_grace_time=300  # 5분의 유예 시간
                )
                
                # 활성 작업 목록에 추가
                self.active_jobs[force_close_job_id] = {
                    "type": JobType.FORCE_CLOSE,
                    "scheduled_time": expected_close_time.isoformat(),
                    "status": "scheduled",
                    "metadata": {
                        "reason": f"Expected minutes({expected_minutes}분) 도달 후 자동 청산",
                        "expected_minutes": expected_minutes,
                        "misfire_grace_time": 300
                    }
                }
                
                return {"success": True, "order_id": order_result.get('data', {}).get('orderId')}
            else:
                print(f"거래 실패: {order_result}")
                return {"success": False, "error": f"거래 실패: {order_result}"}
            
        except Exception as e:
            print(f"거래 실행 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def reset_liquidation_flag(self):
        """청산 감지 플래그 및 관련 상태 초기화"""
        with self._position_lock:
            # 청산 감지 플래그 초기화
            if hasattr(self, '_liquidation_detected'):
                self._liquidation_detected = False
                print("청산 감지 플래그가 초기화되었습니다.")
            else:
                print("청산 감지 플래그가 존재하지 않습니다.")
                
            # 청산 관련 상태 초기화
            if hasattr(self, '_liquidation_reason'):
                self._liquidation_reason = None
                print("청산 이유가 초기화되었습니다.")
                
            if hasattr(self, '_liquidation_price'):
                self._liquidation_price = None
                print("청산 가격이 초기화되었습니다.")
                
            # 마지막 로그 시간 초기화
            self._last_position_log_time = 0
            print("포지션 로그 시간이 초기화되었습니다.")
            
            # 수동 청산 플래그 초기화
            if hasattr(self, '_manual_liquidation'):
                self._manual_liquidation = False
                print("수동 청산 플래그가 초기화되었습니다.")
                
        print("모든 청산 관련 상태가 초기화되었습니다.")
        return True

    async def _schedule_liquidation(self, job_id):
        """예약된 청산 작업 실행"""
        print(f"\n=== 예약된 청산 작업 실행 (ID: {job_id}) ===")
        
        try:
            # 현재 포지션 확인
            positions = self.bitget.get_positions()
            has_position = False
            if positions and 'data' in positions:
                has_position = any(float(pos.get('total', 0)) > 0 for pos in positions['data'])
                print(f"현재 포지션 상태: {'있음' if has_position else '없음'}")
            
            # 포지션이 없으면 이미 청산된 것이므로 작업 종료
            if not has_position:
                print("포지션이 이미 청산되었습니다. 청산 작업을 건너뜁니다.")
                return
            
            # 포지션 청산 실행
            print("\n=== 예상 종료 시간 도달: 포지션 청산 실행 ===")
            print(f"현재 시간: {datetime.now()}")
            print(f"예상 종료 시간: {self._expected_close_time}")
            
            # 포지션 청산 실행
            close_result = self.bitget.close_position(position_size=1.0)
            print(f"청산 결과: {close_result}")
            
            if close_result and close_result.get('success'):
                # 현재 가격 확인
                ticker = self.bitget.get_ticker()
                current_price = 0
                if ticker and 'data' in ticker:
                    current_price = float(ticker['data'][0]['lastPr']) if isinstance(ticker['data'], list) else float(ticker['data'].get('lastPr', 0))
                
                # 청산 정보 저장
                liquidation_reason = "예상 종료 시간 도달"
                
                # 상태 초기화
                with self._position_lock:
                    print(f"이전 포지션 정보:")
                    print(f"- 진입 시간: {self._position_entry_time}")
                    print(f"- 예상 청산 시간: {self._expected_close_time}")
                    print(f"- 진입 가격: {self._position_entry_price}")
                    print(f"- Stop Loss 가격: {self._stop_loss_price}")
                    print(f"- Take Profit 가격: {self._take_profit_price}")
                    print(f"- 포지션 방향: {self._last_position_side}")
                    
                    # 상태 초기화 전에 필요한 정보 백업
                    liquidation_info = {
                        "entry_time": self._position_entry_time.isoformat() if self._position_entry_time else None,
                        "close_time": datetime.now().isoformat(),
                        "entry_price": self._position_entry_price,
                        "exit_price": current_price,
                        "side": self._last_position_side,
                        "reason": liquidation_reason
                    }
                    
                    # 포지션 관련 상태 초기화
                    self._position_entry_time = None
                    self._expected_close_time = None
                    self._position_entry_price = None
                    self._stop_loss_price = None
                    self._take_profit_price = None
                    self._liquidation_detected = True  # 청산 감지 플래그 설정
                
                # 기존 예약 작업 취소
                self.cancel_all_jobs()
                
                # 60분 후 새로운 분석 예약
                next_analysis_time = datetime.now() + timedelta(minutes=60)
                new_job_id = str(uuid.uuid4())
                
                print(f"\n=== 청산 후 새로운 분석 예약 ===")
                print(f"예약 시간: {next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"작업 ID: {new_job_id}")
                
                # 스케줄러에 작업 추가
                self.scheduler.add_job(
                    self._schedule_next_analysis,
                    'date',
                    run_date=next_analysis_time,
                    id=new_job_id,
                    args=[new_job_id],
                    misfire_grace_time=300  # 5분의 유예 시간 추가
                )
                
                self.active_jobs[new_job_id] = {
                    "type": JobType.FORCE_CLOSE,
                    "scheduled_time": next_analysis_time.isoformat(),
                    "expected_minutes": 60,
                    "analysis_result": liquidation_info
                }
                
                print(f"새로운 분석 작업 스케줄링됨: {new_job_id}")
                print(f"현재 활성 작업 목록: {self.active_jobs}")
                
                # 스케줄러 상태 확인
                print(f"스케줄러 작업 목록:")
                for job in self.scheduler.get_jobs():
                    print(f"- {job.id}: {job.next_run_time}")
            else:
                print(f"청산 실패: {close_result}")
                
        except Exception as e:
            print(f"예약된 청산 작업 실행 중 에러: {str(e)}")
            import traceback
            traceback.print_exc()
            # 에러 발생 시 청산 처리 플래그 초기화
            self._liquidation_detected = False

    def _start_stop_loss_monitoring(self):
        """Stop-loss 청산 모니터링 시작"""
        import threading
        import time
        
        def async_job_wrapper(job_id):
            """비동기 함수를 실행하기 위한 래퍼 함수"""
            print(f"\n=== Stop-loss 모니터링: 새로운 분석 작업 실행 (ID: {job_id}) ===")
            print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 새로운 이벤트 루프 생성 및 설정
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 비동기 함수를 동기적으로 실행 (create_task 대신 직접 run_until_complete 사용)
                loop.run_until_complete(self.analyze_and_execute(job_id, schedule_next=True))
            except Exception as e:
                print(f"분석 작업 실행 중 오류: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # 오류 발생 시 다른 스레드에서 30분 후 재분석 예약
                def schedule_retry():
                    retry_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(retry_loop)
                    try:
                        retry_loop.run_until_complete(
                            self._schedule_next_analysis_on_error(f"Stop-loss 모니터링 작업 {job_id} 실행 중 오류: {str(e)}")
                        )
                    except Exception as retry_error:
                        print(f"재시도 예약 중 오류: {str(retry_error)}")
                    finally:
                        retry_loop.close()
                
                # 별도 스레드에서 재시도 예약 실행
                import threading
                retry_thread = threading.Thread(target=schedule_retry)
                retry_thread.daemon = True
                retry_thread.start()
            finally:
                # 이벤트 루프 종료
                loop.close()
        
        def monitor_position():
            initial_position = self.bitget.get_positions()
            while True:
                try:
                    time.sleep(1)  # 1초마다 체크
                    current_position = self.bitget.get_positions()
                    
                    # Stop-loss 또는 Take-profit으로 인한 청산 감지
                    if self._is_position_closed_early(initial_position, current_position):
                        print("Stop-loss 또는 Take-profit에 의한 청산 감지됨")
                        
                        # 청산 플래그 설정
                        self._liquidation_detected = True
                        
                        # FORCE_CLOSE 작업 취소
                        self._cancel_force_close_job()
                        
                        # 새로운 분석 작업 예약 (60분 후)
                        next_analysis_time = datetime.now() + timedelta(minutes=60)
                        job_id = f"analysis_{next_analysis_time.strftime('%Y%m%d%H%M%S')}"
                        
                        try:
                            # 스케줄러에 래퍼 함수 등록 (misfire_grace_time 추가)
                            self.scheduler.add_job(
                                func=async_job_wrapper,
                                trigger='date',
                                run_date=next_analysis_time,
                                id=job_id,
                                args=[job_id],
                                replace_existing=True,
                                misfire_grace_time=300  # 5분(300초)의 유예 시간 추가
                            )
                            print(f"새로운 분석 작업이 예약됨: {job_id}, 실행 시간: {next_analysis_time}, 유예 시간: 5분")
                            
                            # active_jobs 업데이트
                            self.active_jobs[job_id] = {
                                'type': JobType.ANALYSIS,
                                'scheduled_time': next_analysis_time.isoformat(),
                                'status': 'scheduled',
                                'metadata': {
                                    'reason': 'Stop-loss 또는 Take-profit 청산 후 자동 재시작',
                                    'misfire_grace_time': 300
                                }
                            }
                            
                            # 청산 메시지 웹소켓으로 전송
                            try:
                                if self.websocket_manager is not None:
                                    # 비동기 함수를 동기적으로 실행하기 위한 이벤트 루프 생성
                                    broadcast_loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(broadcast_loop)
                                    try:
                                        broadcast_loop.run_until_complete(self.websocket_manager.broadcast({
                                            "type": "liquidation",
                                            "event_type": "LIQUIDATION",
                                            "data": {
                                                "success": True,
                                                "message": "포지션이 청산되었습니다. 60분 후 새로운 분석이 실행됩니다.",
                                                "liquidation_info": {},  # 필요한 정보 추가
                                                "next_analysis": {
                                                    "job_id": job_id,
                                                    "scheduled_time": next_analysis_time.isoformat(),
                                                    "reason": "포지션 청산 후 자동 재시작",
                                                    "expected_minutes": 60
                                                }
                                            },
                                            "timestamp": datetime.now().isoformat()
                                        }))
                                    except Exception as e:
                                        print(f"청산 메시지 전송 중 오류: {str(e)}")
                                    finally:
                                        broadcast_loop.close()
                            except Exception as e:
                                print(f"청산 메시지 전송 중 오류: {str(e)}")
                                traceback.print_exc()
                        except Exception as e:
                            print(f"새로운 분석 작업 예약 실패: {str(e)}")
                            traceback.print_exc()
                        
                        break
                except Exception as e:
                    print(f"포지션 모니터링 중 오류 발생: {str(e)}")
                    traceback.print_exc()
                    time.sleep(5)  # 오류 발생 시 5초 대기 후 재시도
        
        # 모니터링 스레드 시작
        try:
            monitor_thread = threading.Thread(target=monitor_position)
            monitor_thread.daemon = True
            monitor_thread.start()
            print("Stop-loss 모니터링 스레드가 시작되었습니다.")
        except Exception as e:
            print(f"Stop-loss 모니터링 스레드 시작 중 오류: {str(e)}")
            traceback.print_exc()

    def _is_position_closed_early(self, initial_position, current_position):
        """포지션이 예상 종료 시간 이전에 청산되었는지 확인"""
        try:
            # 초기 포지션 확인
            initial_has_position = False
            if initial_position and 'data' in initial_position:
                initial_has_position = any(float(pos.get('total', 0)) > 0 for pos in initial_position['data'])
            
            # 현재 포지션 확인
            current_has_position = False
            if current_position and 'data' in current_position:
                current_has_position = any(float(pos.get('total', 0)) > 0 for pos in current_position['data'])
            
            # 포지션이 있었다가 없어진 경우
            if initial_has_position and not current_has_position:
                # 예상 종료 시간 이전인지 확인
                with self._position_lock:
                    if self._expected_close_time and datetime.now() < self._expected_close_time:
                        print(f"조기 청산 감지: 현재 시간({datetime.now()}) < 예상 종료 시간({self._expected_close_time})")
                        return True
            
            return False
        
        except Exception as e:
            print(f"포지션 청산 확인 중 오류: {str(e)}")
            return False

    def get_active_jobs(self):
        """현재 활성화된 작업 목록 반환"""
        try:
            formatted_jobs = {}
            for job_id, job_info in self.active_jobs.items():
                scheduled_time = job_info.get("scheduled_time")
                # datetime 객체인 경우 isoformat으로 변환
                if isinstance(scheduled_time, datetime):
                    scheduled_time = scheduled_time.isoformat()
                # 이미 문자열인 경우 그대로 사용
                elif not isinstance(scheduled_time, str):
                    scheduled_time = None
                    
                formatted_jobs[job_id] = {
                    "type": job_info.get("type"),
                    "scheduled_time": scheduled_time,
                    "status": job_info.get("status", "unknown"),
                    "metadata": job_info.get("metadata", {})
                }
            return formatted_jobs
        except Exception as e:
            print(f"작업 목록 조회 중 오류: {str(e)}")
            return {}

    async def _schedule_next_analysis_on_error(self, error_message):
        """에러 발생 시 다음 분석 예약"""
        try:
            # 에러 메시지 브로드캐스트
            error_data = {
                "type": "ANALYSIS_ERROR",
                "data": {
                    "message": str(error_message),
                    "timestamp": datetime.now().isoformat()
                }
            }
            await self.websocket_manager.broadcast(error_data)
            
            # 60분 후 다음 분석 예약
            next_analysis_time = datetime.now() + timedelta(minutes=60)
            job_id = f"ANALYSIS_{int(time.time())}"
            
            # 새로운 분석 작업 예약
            self.active_jobs[job_id] = {
                "type": JobType.ANALYSIS,
                "scheduled_time": next_analysis_time,
                "status": "scheduled"
            }
            
            print(f"에러로 인한 다음 분석 예약됨: {next_analysis_time}")
            
        except Exception as e:
            print(f"다음 분석 예약 중 오류: {str(e)}")

    def get_trading_status(self):
        """현재 트레이딩 상태를 반환합니다."""
        try:
            # 포지션 데이터 가져오기
            positions_data = self.bitget.get_positions()
            
            # 현재 가격 가져오기
            ticker_data = self.bitget.get_ticker()
            current_price = 0
            
            if ticker_data and 'data' in ticker_data and ticker_data['data']:
                if isinstance(ticker_data['data'], list):
                    current_price = float(ticker_data['data'][0].get('lastPr', 0))
                else:
                    current_price = float(ticker_data['data'].get('lastPr', 0))
            
            # 포지션 정보 추출
            position_data = {
                "size": 0,
                "entry_price": 0,
                "unrealized_pnl": 0,
                "side": None
            }
            
            if positions_data and 'data' in positions_data and positions_data['data']:
                for pos in positions_data['data']:
                    if pos.get('symbol') == 'BTCUSDT' and float(pos.get('total', 0)) > 0:
                        position_data = {
                            "size": float(pos.get('total', 0)),
                            "entry_price": float(pos.get('averageOpenPrice', 0)),
                            "unrealized_pnl": float(pos.get('unrealizedPL', 0)),
                            "side": pos.get('holdSide', '').lower()
                        }
                        break
            
            # 스케줄러 작업 가져오기
            scheduler_jobs = self.scheduler.get_jobs()
            next_analysis = None
            
            if scheduler_jobs:
                # next_run_time이 있는 작업들을 시간순으로 정렬
                sorted_jobs = sorted(scheduler_jobs, key=lambda job: getattr(job, 'next_run_time', None) or datetime.max)
                next_job = sorted_jobs[0]
                next_analysis = next_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if getattr(next_job, 'next_run_time', None) else None
            
            # 응답 데이터 구성
            response = {
                "status": "running" if self.is_monitoring else "not_started",
                "next_analysis": next_analysis,
                "current_position": position_data,
                "current_price": current_price,
                "last_position_side": self._last_position_side,
                "last_analysis_result": self.last_analysis_result
            }
            
            return response
            
        except Exception as e:
            print(f"트레이딩 상태 조회 중 오류 발생: {str(e)}")
            traceback.print_exc()
            return {
                "status": "error",
                "message": str(e)
            }

    def _cancel_scheduled_analysis(self):
        """분석 작업만 취소"""
        try:
            # 스케줄러에서 작업 목록 가져오기
            jobs = self.scheduler.get_jobs()
            
            # 분석 작업만 취소
            for job in jobs:
                job_info = self.active_jobs.get(job.id)
                if job_info and job_info.get('type') == JobType.ANALYSIS:
                    job.remove()
                    print(f"분석 작업 취소됨: {job.id}")
                    # active_jobs에서도 제거
                    if job.id in self.active_jobs:
                        del self.active_jobs[job.id]
            
        except Exception as e:
            print(f"분석 작업 취소 중 오류: {str(e)}")
