import os
import sys
import json
import time
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from io import StringIO
import threading

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError
from app.services.bitget_service import BitgetService
from app.services.trading_assistant import TradingAssistant, websocket_manager
from app.database.db import get_db, init_db
from app.models.trading_history import TradingHistory
from .routers import trading

# FastAPI 앱 생성
app = FastAPI(
    title="Bitcoin Trading API",
    description="API for Bitcoin trading bot",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(trading.router, prefix="/api")

# 서비스 인스턴스 생성
bitget_service = BitgetService()
trading_assistant = TradingAssistant(websocket_manager=websocket_manager)

# DB 초기화
init_db()

# 다음 분석 시간 저장
next_analysis_time = None

@app.get("/")
async def root():
    return {"message": "Bitcoin Trading API"}

@app.get("/trading/data")
async def get_trading_data():
    # 여기에 실제 거래 데이터를 가져오는 로직 구현
    return {
        "data": [
            {"timestamp": "2024-02-22T10:00:00", "price": 50000},
            {"timestamp": "2024-02-22T10:01:00", "price": 50100},
            # ... 더 많은 데이터
        ]
    }

@app.get("/api/market/ticker")
async def get_ticker():
    """
    현재 시장 가격 조회 API
    - 현재가
    - 24시간 변동폭
    - 거래량
    - 고가/저가
    Returns:
        JSON: 시장 데이터 정보
    """
    try:
        result = bitget_service.get_ticker()
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to fetch ticker data")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/kline")
async def get_kline(granularity: str = "1m", limit: int = 100, startTime: str = None, endTime: str = None):
    """
    캔들스틱 차트 데이터 조회 API
    Args:
        granularity (str): 시간 단위 (1m, 5m, 15m, 30m, 1H, 4H, 1D)
        limit (int): 조회할 캔들 개수 (기본값: 100)
        startTime (str): 시작 시간 (밀리초)
        endTime (str): 종료 시간 (밀리초)
    Returns:
        JSON: 캔들스틱 데이터 목록
    """
    try:
        print(f"Received kline request - granularity: {granularity}, limit: {limit}, startTime: {startTime}, endTime: {endTime}")
        
        result = bitget_service.get_kline(
            granularity=granularity, 
            limit=limit,
            startTime=startTime if startTime else None,
            endTime=endTime if endTime else None
        )
        
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to fetch kline data")
            
        return result
        
    except Exception as e:
        print(f"Error in get_kline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/account/info")
async def get_account_info():
    """
    계정 정보 조회 API
    Returns:
        JSON: 계정 잔고, 마진, 레버리지 등 정보
    """
    try:
        result = bitget_service.get_account_info()
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to fetch account info")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/position/current")
async def get_positions():
    """
    현재 포지션 조회 API
    Returns:
        JSON: 보유 중인 모든 포지션 정보
        - 포지션 크기
        - 진입가격
        - 현재가격
        - 미실현 손익
    """
    try:
        result = bitget_service.get_positions()
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to fetch position data")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/orderbook")
async def get_orderbook(limit: int = 100):
    """
    호가창 데이터 조회 API
    Args:
        limit (int): 조회할 호가 개수 (기본값: 100)
    Returns:
        JSON: 매수/매도 주문 데이터
        - asks: 매도 호가 목록 [가격, 수량]
        - bids: 매수 호가 목록 [가격, 수량]
    """
    try:
        result = bitget_service.get_orderbook(limit)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to fetch orderbook data")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trade/execute")
async def execute_trade():
    """
    거래 실행 API
    - 마진 모드 설정 (fixed)
    - 레버리지 설정 (2x)
    - 시장가 숏 포지션 주문
    """
    try:
        result = bitget_service.execute_trade()
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/close_trade")
async def close_trade(request: Request):
    """포지션 청산 API"""
    try:
        # 원래 stdout 저장
        original_stdout = sys.stdout
        
        print("\n=== 수동 청산 프로세스 시작 ===")
        
        # 기존 예약된 작업 취소
        trading_assistant.cancel_all_jobs()
        print("기존 예약된 모든 작업이 취소되었습니다.")
        
        # 청산 감지 플래그 및 관련 상태 초기화
        trading_assistant.reset_liquidation_flag()
        
        # 예상 종료 시간 초기화
        if hasattr(trading_assistant, '_expected_close_time'):
            trading_assistant._expected_close_time = None
            print("예상 종료 시간이 초기화되었습니다.")
        
        # 포지션 진입 시간 초기화
        if hasattr(trading_assistant, '_position_entry_time'):
            trading_assistant._position_entry_time = None
            print("포지션 진입 시간이 초기화되었습니다.")
        
        # 포지션 청산 실행
        result = await bitget_service.close_position()
        
        if result and result.get('success'):
            print(f"\n=== 포지션 청산 결과: 성공 ===")
            print(f"응답: {result}")
            
            # 청산 성공 시 60분 후 다음 분석 예약
            next_analysis_time = datetime.now() + timedelta(minutes=60)
            new_job_id = str(uuid.uuid4())
            
            print(f"\n=== 수동 청산 후 새로운 분석 예약 ===")
            print(f"예약 시간: {next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"작업 ID: {new_job_id}")
            
            # 수동 청산 플래그 설정 (필요한 경우)
            if hasattr(trading_assistant, '_manual_liquidation'):
                trading_assistant._manual_liquidation = True
                print("수동 청산 플래그가 설정되었습니다.")
            
            # 스케줄러에 작업 추가 - _schedule_next_analysis 메서드 호출
            trading_assistant.scheduler.add_job(
                trading_assistant._schedule_next_analysis,
                'date',
                run_date=next_analysis_time,
                id=new_job_id,
                args=[new_job_id],
                replace_existing=True
            )
            
            # 청산 정보 구성
            liquidation_info = {
                'reason': 'manual_liquidation',
                'close_time': datetime.now().isoformat()
            }
            
            # active_jobs에 추가
            trading_assistant.active_jobs[new_job_id] = {
                'type': 'analysis',
                'scheduled_time': next_analysis_time.isoformat(),
                'reason': '수동 청산 후 재분석',
                'liquidation_info': liquidation_info
            }
            
            print(f"다음 분석 예약됨: {next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"스케줄러에 있는 작업 ID 목록: {[job.id for job in trading_assistant.scheduler.get_jobs()]}")
            print(f"현재 active_jobs 목록: {list(trading_assistant.active_jobs.keys())}")
            
            # 청산 메시지 웹소켓으로 전송
            await websocket_manager.broadcast({
                "type": "liquidation",
                "event_type": "LIQUIDATION",
                "data": {
                    "success": True,
                    "message": "포지션이 성공적으로 청산되었습니다. 60분 후 새로운 분석이 실행됩니다.",
                    "liquidation_info": liquidation_info,
                    "next_analysis": {
                        "job_id": new_job_id,
                        "scheduled_time": next_analysis_time.isoformat(),
                        "reason": "수동 청산 후 재분석",
                        "expected_minutes": 60
                    }
                },
                "timestamp": datetime.now().isoformat()
            })
            
            # 분석 결과 미리 전송 (예약된 분석이 있음을 알림)
            await websocket_manager.broadcast({
                "type": "analysis_result",
                "event_type": "ANALYSIS_RESULT",
                "data": {
                    "success": True,
                    "message": "포지션이 청산되었습니다. 60분 후 새로운 분석이 실행됩니다.",
                    "next_analysis": {
                        "job_id": new_job_id,
                        "scheduled_time": next_analysis_time.isoformat(),
                        "reason": "수동 청산 후 재분석",
                        "expected_minutes": 60
                    }
                },
                "timestamp": datetime.now().isoformat()
            })
            
            print("\n=== 수동 청산 프로세스 완료 ===")
            return {"success": True, "message": "포지션이 성공적으로 청산되었습니다."}
        else:
            error_msg = result.get('error', '알 수 없는 오류로 청산에 실패했습니다.')
            print(f"청산 실패: {error_msg}")
            return {"success": False, "error": error_msg}
    
    except Exception as e:
        print(f"청산 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.post("/api/trade/execute-long")
async def execute_long_trade():
    """롱 포지션 진입 API"""
    try:
        result = bitget_service.execute_long_trade()
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trading/analyze-only")
async def analyze_only():
    """AI 분석만 수행 (거래 없음)"""
    try:
        import numpy as np
        import copy
        print("\n=== AI 분석만 수행 (거래 없음) ===")
        
        # 시장 데이터 수집 (비동기 메서드 호출)
        market_data = await trading_assistant._collect_market_data()
        if not market_data:
            raise HTTPException(status_code=500, detail="Failed to collect market data")
        
        # numpy 타입을 Python 기본 타입으로 변환하는 함수
        def convert_numpy_types(obj):
            # numpy bool 타입 처리
            if hasattr(np, 'bool_') and isinstance(obj, np.bool_):
                return bool(obj)
            elif hasattr(np, 'bool') and isinstance(obj, np.bool):
                return bool(obj)
            # numpy 정수 타입 처리
            elif isinstance(obj, (np.integer, np.int8, np.int16, np.int32, np.int64, 
                                np.uint8, np.uint16, np.uint32, np.uint64)):
                return int(obj)
            # numpy 부동소수점 타입 처리
            elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
                return float(obj)
            # numpy 배열 처리
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            # 딕셔너리 재귀 처리
            elif isinstance(obj, dict):
                return {key: convert_numpy_types(value) for key, value in obj.items()}
            # 리스트 재귀 처리
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            return obj
        
        # market_data를 변환
        market_data = convert_numpy_types(market_data)
        
        # 현재 포지션 정보 가져오기
        positions = trading_assistant.bitget.get_positions()
        current_position = None
        if positions and 'data' in positions:
            active_positions = [pos for pos in positions['data'] 
                              if pos['symbol'] == 'BTCUSDT' and float(pos.get('total', 0)) != 0]
            if active_positions:
                current_position = active_positions[0]
        
        # 분석용 market_data 깊은 복사본 생성 (포지션 정보 제거)
        analysis_market_data = copy.deepcopy(market_data) if isinstance(market_data, dict) else market_data
        
        # 포지션 정보를 완전히 제거 (포지션이 없는 것처럼)
        if isinstance(analysis_market_data, dict):
            # positions 필드를 빈 리스트로 설정
            analysis_market_data['positions'] = []
            
            # account 정보에서 포지션 관련 정보 제거
            # 분석만 실행 시 계정 정보 완전 제거 (포지션 정보뿐만 아니라 잔액 정보도 제거)
            if 'account' in analysis_market_data:
                # 계정 정보를 완전히 제거하여 AI가 잔액을 고려하지 않도록 함
                del analysis_market_data['account']
            
            # 최상위 레벨의 포지션 관련 필드도 제거
            if 'current_position' in analysis_market_data:
                analysis_market_data['current_position'] = None
            if 'position_info' in analysis_market_data:
                analysis_market_data['position_info'] = None
        
        print(f"\n=== 분석용 데이터 준비 완료 ===")
        print(f"포지션 정보 제거됨 - positions: {analysis_market_data.get('positions', [])}")
        print(f"계정 정보 제거됨 - account 필드 완전 삭제")
        print(f"AI는 잔액 정보 없이 순수한 시장 분석만 수행")
        
        # AI 분석 실행 (현재 선택된 모델 사용, 포지션 없는 데이터로)
        try:
            # AI 서비스를 통해 분석 실행 (포지션이 없는 데이터로)
            analysis_result = await trading_assistant.ai_service.analyze_market_data(analysis_market_data)
            
            print(f"\n=== AI 분석 결과 (분석만 - 포지션 없는 상태로 분석) ===")
            print(f"분석 모델: {trading_assistant.get_current_ai_model().upper()}")
            print(f"거래 방향: {analysis_result.get('action')}")
            print(f"포지션 크기: {analysis_result.get('position_size', 1.0)}")
            print(f"레버리지: {analysis_result.get('leverage', 2)}")
            print(f"예상 시간(분): {analysis_result.get('expected_minutes', 30)}")
            print(f"이유: {analysis_result.get('reason', 'No reason provided')[:200]}...")
            
            # 실제 포지션 정보 로깅 (비교용)
            if current_position:
                print(f"\n[참고] 실제 보유 중인 포지션: {current_position.get('holdSide')} {current_position.get('total')} BTC")
            else:
                print(f"\n[참고] 현재 보유 중인 포지션 없음")
            
            # WebSocket으로 분석 결과 전송
            await websocket_manager.broadcast({
                "type": "analysis_only_result",
                "event_type": "ANALYSIS_ONLY_RESULT",
                "data": {
                    "success": True,
                    "model": trading_assistant.get_current_ai_model(),
                    "analysis": analysis_result,
                    "current_position": current_position,
                    "market_data": {
                        "current_price": market_data.get('current_price') if isinstance(market_data, dict) else None,
                        "rsi": market_data.get('rsi') if isinstance(market_data, dict) else None,
                        "macd": market_data.get('macd') if isinstance(market_data, dict) else None,
                        "volume_24h": market_data.get('volume_24h') if isinstance(market_data, dict) else None
                    },
                    "timestamp": datetime.now().isoformat()
                },
                "timestamp": datetime.now().isoformat()
            })
            
            # 전체 response를 numpy 타입 변환
            response = {
                "success": True,
                "model": trading_assistant.get_current_ai_model(),
                "analysis": analysis_result,
                "current_position": current_position,
                "market_data": market_data,
                "message": "분석이 완료되었습니다. (거래는 실행되지 않았습니다)"
            }
            
            # 최종 response도 numpy 타입 변환
            return convert_numpy_types(response)
            
        except Exception as e:
            print(f"AI 분석 중 오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"AI 분석 실패: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"분석 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trading/start")
async def start_trading():
    """자동 트레이딩 시작"""
    try:
        # 이미 실행 중인지 확인
        global next_analysis_time
        if next_analysis_time:
            return {
                "success": False,
                "message": "Trading is already running"
            }

        # 시스템 초기화 플래그 설정
        if not hasattr(trading_assistant, '_system_initialized'):
            trading_assistant._system_initialized = True

        # 현재 포지션 확인
        positions = trading_assistant.bitget.get_positions()
        if positions and 'data' in positions:
            active_positions = [pos for pos in positions['data'] 
                              if pos['symbol'] == 'BTCUSDT' and float(pos.get('total', 0)) != 0]
            if active_positions:
                # 포지션이 있으면 자동 트레이딩 시작
                # AI 분석을 통해 expected_minutes 값을 얻음
                market_data = trading_assistant.collect_market_data()
                if not market_data['success']:
                    raise Exception("Failed to collect market data")
                
                try:
                    analysis_result = await trading_assistant.openai.analyze_market_data(market_data['data'])
                    
                    # AI 분석 결과 출력 추가
                    print("\n=== 기존 포지션에 대한 AI 분석 결과 ===")
                    print(f"전체 분석 결과: {analysis_result}")
                    print(f"거래 방향: {analysis_result.get('action')}")
                    print(f"예상 시간(분): {analysis_result.get('expected_minutes')}")
                    print(f"이유: {analysis_result.get('reason')}")
                    
                    # AI 분석 결과에 따라 거래 실행
                    trade_result = None
                    if analysis_result.get('action') == 'CLOSE_POSITION':
                        # 포지션 청산 로직
                        position_size = analysis_result.get("position_size", 1.0)
                        print(f"\n=== 포지션 청산 실행 ===")
                        print(f"청산 비율: {position_size * 100}%")
                        
                        # 포지션 청산 실행
                        trade_result = trading_assistant.bitget.close_position(position_size=position_size)
                        print(f"청산 결과: {trade_result}")
                    
                    # 다음 분석 시간 설정
                    expected_minutes = analysis_result.get('expected_minutes', 30)
                    next_analysis_time = datetime.now() + timedelta(minutes=expected_minutes)
                    
                    # 새로운 작업 ID 생성
                    new_job_id = str(uuid.uuid4())
                    
                    # 비동기 함수를 실행하기 위한 래퍼 함수 정의
                    def async_job_wrapper(job_id):
                        """비동기 함수를 실행하기 위한 래퍼 함수"""
                        print(f"\n=== 청산 후 자동 재시작 작업 실행 (ID: {job_id}) ===")
                        
                        # 원래 stdout 저장
                        original_stdout = sys.stdout
                        
                        # 분석 시작 메시지 출력
                        print("\n=== 시장 분석 시작 ===")
                        print("캔들스틱 데이터 로딩 중... (상세 출력은 생략됩니다)")
                        
                        # 임시 stdout으로 리디렉션 - 캔들스틱 데이터 수집 단계만 리디렉션
                        temp_stdout = StringIO()
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = None
                        
                        try:
                            # 시장 데이터 수집 단계에서만 stdout 리디렉션
                            trading_assistant._collecting_market_data = True
                            
                            # 모니터링 함수 정의
                            def monitor_collection_status():
                                """시장 데이터 수집 상태를 모니터링하는 함수"""
                                nonlocal original_stdout
                                
                                # 시장 데이터 수집 중에는 출력 리디렉션
                                while trading_assistant._collecting_market_data:
                                    sys.stdout = temp_stdout
                                    time.sleep(0.1)
                                
                                # 데이터 수집이 완료되면 원래 stdout으로 복원
                                sys.stdout = original_stdout
                                current_model = trading_assistant.get_current_ai_model().upper()
                                print(f"시장 데이터 수집 완료, {current_model} 분석 시작...")
                            
                            # 모니터링 스레드 시작
                            monitor_thread = threading.Thread(target=monitor_collection_status)
                            monitor_thread.daemon = True
                            monitor_thread.start()
                            
                            # 비동기 함수 실행 시작 - analyze_and_execute 직접 호출
                            result = loop.run_until_complete(trading_assistant.analyze_and_execute(job_id, schedule_next=False))
                            
                            # 원래 stdout으로 복원
                            sys.stdout = original_stdout
                            
                            # 모니터링 스레드 종료 대기
                            if monitor_thread.is_alive():
                                trading_assistant._collecting_market_data = False
                                monitor_thread.join(timeout=1.0)
                            
                            # 분석 결과 요약 출력
                            if isinstance(result, dict) and result.get('success'):
                                print("\n=== 시장 분석 완료 ===")
                                if 'analysis' in result:
                                    analysis = result['analysis']
                                    print(f"분석 결과: {analysis.get('action', 'UNKNOWN')}")
                                    print(f"이유: {analysis.get('reason', 'No reason provided')[:150]}...")  # 이유는 앞부분만 출력
                                    print(f"다음 분석 예정: {result.get('next_analysis', {}).get('scheduled_time', 'Unknown')}")
                                else:
                                    print("분석 결과가 없습니다.")
                            else:
                                print(f"자동 재시작 작업 결과: {result}")
                            
                            return result
                        except Exception as e:
                            # 원래 stdout으로 복원
                            sys.stdout = original_stdout
                            
                            print(f"자동 재시작 작업 실행 중 에러: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            return None
                        finally:
                            # 혹시 모를 경우를 대비해 stdout 복원 확인
                            sys.stdout = original_stdout
                            if hasattr(trading_assistant, '_collecting_market_data'):
                                trading_assistant._collecting_market_data = False
                            loop.close()
                    
                    # 1분 후 새로운 분석 스케줄링
                    try:
                        trading_assistant.scheduler.add_job(
                            async_job_wrapper,
                            trigger=DateTrigger(run_date=next_analysis_time),
                            id=new_job_id,
                            args=[new_job_id]
                        )
                        trading_assistant.active_jobs[new_job_id] = {
                            "scheduled_time": next_analysis_time.isoformat(),
                            "analysis_result": None
                        }
                        print(f"새로운 분석 작업 스케줄링됨: {new_job_id} - 실행 시간: {next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"새로운 분석 작업 스케줄링 중 에러: {str(e)}")
                    
                    # 실제 AI 분석 결과 반환 (analyze_and_execute 함수의 반환 형식과 일치)
                    return {
                        "success": True,
                        "analysis": analysis_result,
                        "execution": trade_result,
                        "market_data": market_data['data'],
                        "next_analysis": {
                            "job_id": new_job_id,
                            "scheduled_time": next_analysis_time.isoformat(),
                            "expected_minutes": expected_minutes
                        }
                    }
                except Exception as e:
                    print(f"Error during analysis: {str(e)}")
                    # 분석 실패 시에도 트레이딩은 시작
                    expected_minutes = 30
                    next_analysis_time = datetime.now() + timedelta(minutes=expected_minutes)
                    new_job_id = str(uuid.uuid4())
                    
                    return {
                        "success": True,
                        "message": "Trading started but analysis failed. Will retry analysis later.",
                        "market_data": market_data['data'],
                        "next_analysis": {
                            "job_id": new_job_id,
                            "scheduled_time": next_analysis_time.isoformat(),
                            "expected_minutes": expected_minutes
                        }
                    }

        # 새로운 분석 시작
        try:
            result = await trading_assistant.analyze_and_execute()
            
            if result['success'] and 'analysis' in result:
                next_analysis_time = result['analysis'].get('next_analysis_time')
            
            return result
        except Exception as e:
            print(f"Error during analyze_and_execute: {str(e)}")
            # 분석 실패 시에도 트레이딩은 시작
            expected_minutes = 30
            next_analysis_time = datetime.now() + timedelta(minutes=expected_minutes)
            new_job_id = str(uuid.uuid4())
            
            return {
                "success": True,
                "message": "Trading started but analysis failed. Will retry analysis later.",
                "next_analysis": {
                    "job_id": new_job_id,
                    "scheduled_time": next_analysis_time.isoformat(),
                    "expected_minutes": expected_minutes
                }
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/status")
async def get_trading_status():
    """트레이딩 상태 조회 및 포지션 청산 감지"""
    global next_analysis_time
    global trading_assistant
    
    if not trading_assistant:
        return {"status": "not_started", "message": "트레이딩이 시작되지 않았습니다."}
    
    # 현재 포지션 상태 확인
    try:
        position_data = trading_assistant.bitget.get_positions()
        current_position = trading_assistant._update_position_info(position_data)
    except Exception as e:
        print(f"포지션 데이터 가져오기 실패: {str(e)}")
        # API 오류 발생 시 이전 상태 유지
        return {
            "status": "running" if next_analysis_time else "not_started",
            "next_analysis": next_analysis_time if isinstance(next_analysis_time, str) else (next_analysis_time.isoformat() if next_analysis_time else None),
            "error": f"포지션 데이터 가져오기 실패: {str(e)}",
            "current_position": None,
            "last_position_side": trading_assistant._last_position_side,
        }
    
    # 현재 가격 정보 가져오기
    try:
        ticker = trading_assistant.bitget.get_ticker()
        current_price = 0
        if ticker and 'data' in ticker:
            current_price = float(ticker['data'][0]['lastPr']) if isinstance(ticker['data'], list) else float(ticker['data'].get('lastPr', 0))
    except Exception as e:
        print(f"가격 정보 가져오기 실패: {str(e)}")
        current_price = 0
    
    # 포지션 청산 감지 로직
    liquidation_detected = False
    liquidation_reason = None
    liquidation_price = 0
    
    # 포지션이 없고, 이전에 포지션 진입 시간이 있었다면 청산된 것
    # 단, 시스템 시작 직후 첫 실행인 경우는 제외
    if not current_position and trading_assistant._position_entry_time and hasattr(trading_assistant, '_system_initialized'):
        liquidation_detected = True
        
        # 수동 청산 플래그 확인
        if hasattr(trading_assistant, '_manual_liquidation') and trading_assistant._manual_liquidation:
            liquidation_reason = "수동 청산"
            print(f"\n=== 수동 청산 감지됨 (API 엔드포인트) ===")
            # 플래그 초기화
            trading_assistant._manual_liquidation = False
        else:
            # 청산 원인 파악
            liquidation_reason = trading_assistant._check_liquidation_reason(current_price)
        
        liquidation_price = current_price
        
        print(f"\n=== 포지션 청산 감지됨 (API 엔드포인트) ===")
        print(f"청산 원인: {liquidation_reason}")
        print(f"청산 시 가격: {current_price}")
        
        # 상태 초기화 (포지션 방향 정보는 유지)
        with trading_assistant._position_lock:
            # 상태 초기화 전에 필요한 정보 백업
            liquidation_info = {
                "entry_time": trading_assistant._position_entry_time.isoformat() if trading_assistant._position_entry_time else None,
                "close_time": datetime.now().isoformat(),
                "entry_price": trading_assistant._position_entry_price,
                "exit_price": current_price,
                "side": trading_assistant._last_position_side,
                "reason": liquidation_reason
            }
            
            # 포지션 관련 상태 초기화
            trading_assistant._position_entry_time = None
            trading_assistant._expected_close_time = None
            trading_assistant._position_entry_price = None
            trading_assistant._stop_loss_price = None
            trading_assistant._take_profit_price = None
            trading_assistant._liquidation_detected = False  # 플래그 초기화
        
        # 기존 예약 작업 취소
        trading_assistant._cancel_scheduled_analysis()
        
        # 60분 후 새로운 분석 예약
        next_analysis_time = datetime.now() + timedelta(minutes=60)
        print(f"포지션 청산 감지: 60분 후 ({next_analysis_time.strftime('%Y-%m-%d %H:%M:%S')})에 새로운 분석 예약됨")
        
        # 기존 스케줄링된 작업 취소 (중복 방지)
        for job_id in list(trading_assistant.active_jobs.keys()):
            try:
                trading_assistant.scheduler.remove_job(job_id)
                del trading_assistant.active_jobs[job_id]
                print(f"작업 취소됨: {job_id}")
            except Exception as e:
                print(f"작업 {job_id} 취소 중 에러: {str(e)}")
        
        # 새로운 작업 ID 생성
        new_job_id = str(uuid.uuid4())
        
        # 비동기 함수를 실행하기 위한 래퍼 함수 정의
        def async_job_wrapper(job_id):
            """비동기 함수를 실행하기 위한 래퍼 함수"""
            print(f"\n=== 포지션 청산 후 자동 재시작 작업 실행 (ID: {job_id}) ===")
            print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"포지션 청산 정보: {liquidation_info}")
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 비동기 함수 실행
                print("\n=== 시장 분석 및 거래 실행 시작 (포지션 청산 후 자동 재시작) ===")
                result = loop.run_until_complete(trading_assistant.analyze_and_execute(job_id, schedule_next=True))
                print(f"자동 재시작 작업 결과: {result['success'] if isinstance(result, dict) and 'success' in result else '알 수 없음'}")
            except Exception as e:
                print(f"자동 재시작 작업 실행 중 오류: {str(e)}")
            finally:
                loop.close()
        
        # 스케줄러에 작업 등록
        trading_assistant.scheduler.add_job(
            async_job_wrapper,
            'date',
            run_date=next_analysis_time,
            args=[new_job_id],
            id=new_job_id,
            replace_existing=True
        )
        
        # 활성 작업 목록에 추가
        trading_assistant.active_jobs[new_job_id] = {
            "type": "analysis",
            "scheduled_time": next_analysis_time.isoformat(),
            "reason": "포지션 청산 후 자동 재시작"
        }
        
        # 실제 응답 반환
        return {
            "success": True,
            "status": "running",  # 중요: 상태를 running으로 유지
            "liquidation_detected": True,
            "liquidation_reason": liquidation_reason,
            "liquidation_price": liquidation_price,
            "next_analysis": next_analysis_time if isinstance(next_analysis_time, str) else (next_analysis_time.isoformat() if next_analysis_time else None),
            "next_analysis_job_id": new_job_id
        }
    
    # 마지막 분석 결과 찾기
    last_analysis_result = None
    
    # 1. trading_assistant 객체에 직접 저장된 last_analysis_result 확인
    if hasattr(trading_assistant, 'last_analysis_result') and trading_assistant.last_analysis_result:
        last_analysis_result = trading_assistant.last_analysis_result
        print(f"trading_assistant 객체에서 last_analysis_result 찾음: {type(last_analysis_result)}")
        
        # 프론트엔드 호환성을 위해 필요한 필드 추가
        if isinstance(last_analysis_result, dict):
            # 분석 결과를 포함하는 결과 객체 생성
            last_analysis_result = {
                "success": True,
                "analysis": last_analysis_result,
                "action": last_analysis_result.get('action'),
                "position_size": last_analysis_result.get('position_size'),
                "leverage": last_analysis_result.get('leverage'),
                "expected_minutes": last_analysis_result.get('expected_minutes'),
                "reason": last_analysis_result.get('reason')
            }
    
    # 2. active_jobs에서 분석 결과 찾기 (기존 로직)
    if not last_analysis_result:
        for job_id, job_info in trading_assistant.active_jobs.items():
            if 'analysis_result' in job_info and job_info['analysis_result']:
                last_analysis_result = job_info['analysis_result']
                print(f"active_jobs에서 analysis_result 찾음: {job_id}")
                
                # 프론트엔드 호환성을 위해 필요한 필드 추가
                if isinstance(last_analysis_result, dict):
                    # 분석 결과를 포함하는 결과 객체 생성
                    last_analysis_result = {
                        "success": True,
                        "analysis": last_analysis_result,
                        "action": last_analysis_result.get('action'),
                        "position_size": last_analysis_result.get('position_size'),
                        "leverage": last_analysis_result.get('leverage'),
                        "expected_minutes": last_analysis_result.get('expected_minutes'),
                        "reason": last_analysis_result.get('reason')
                    }
                break
    
    # 스케줄러에서 가장 빠른 다음 분석 시간 찾기
    scheduler_next_time = None
    scheduler_jobs = trading_assistant.scheduler.get_jobs()
    if scheduler_jobs:
        # 실행 시간으로 정렬하여 가장 빠른 작업 찾기
        sorted_jobs = sorted(scheduler_jobs, key=lambda job: getattr(job, 'next_run_time', None) or datetime.max)
        if sorted_jobs and sorted_jobs[0].next_run_time:
            scheduler_next_time = sorted_jobs[0].next_run_time
            print(f"스케줄러에서 가장 빠른 다음 분석 시간 찾음: {scheduler_next_time}")
    
    # 다음 분석 시간 결정 (스케줄러 시간 우선)
    if scheduler_next_time:
        next_analysis_time = scheduler_next_time
    
    # 응답 데이터 구성
    response = {
        "status": "running" if next_analysis_time else "not_started",
        "next_analysis": next_analysis_time if isinstance(next_analysis_time, str) else (next_analysis_time.isoformat() if next_analysis_time else None),
        "current_position": current_position,
        "current_price": current_price,
        "last_position_side": trading_assistant._last_position_side,
        "last_analysis_result": last_analysis_result  # 마지막 분석 결과 추가
    }
    
    # 청산 감지된 경우 추가 정보 포함
    if liquidation_detected:
        response["liquidation_detected"] = True
        response["liquidation_reason"] = liquidation_reason
        response["liquidation_price"] = liquidation_price
        response["next_analysis_after_liquidation"] = next_analysis_time if isinstance(next_analysis_time, str) else (next_analysis_time.isoformat() if next_analysis_time else None)
    
    return response

@app.post("/api/trading/stop")
async def stop_trading():
    """자동 트레이딩 중지"""
    try:
        global next_analysis_time
        
        # 이미 중지된 상태인지 확인
        if not next_analysis_time:
            return {
                "success": True,
                "message": "Trading is already stopped"
            }

        # 다음 분석 시간을 None으로 설정하여 자동 트레이딩 중지
        next_analysis_time = None
        
        # 예약된 작업 취소
        trading_assistant.cancel_all_jobs()
        
        return {
            "success": True,
            "message": "Trading stopped successfully. Current positions are maintained."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/history")
async def get_trading_history(limit: int = 50):
    """거래 히스토리 조회 API"""
    try:
        db = next(get_db())
        
        # 최근 거래 히스토리 조회
        history = db.query(TradingHistory).order_by(TradingHistory.timestamp.desc()).limit(limit).all()
        
        # 결과를 딕셔너리 형태로 변환
        result = []
        for record in history:
            result.append({
                "id": record.id,
                "timestamp": record.timestamp.isoformat() if record.timestamp else None,
                "action": record.action,
                "position_size": record.position_size,
                "leverage": record.leverage,
                "entry_price": record.entry_price,
                "exit_price": record.exit_price,
                "pnl": record.pnl,
                "roe": record.roe,
                "reason": record.reason,
                "status": record.status
            })
        
        return {"success": True, "data": result}
        
    except Exception as e:
        print(f"거래 히스토리 조회 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/model")
async def set_ai_model(request: Request):
    """AI 모델 설정 API"""
    try:
        body = await request.json()
        model_type = body.get("model", "gpt")
        
        # 모델 타입 검증 - claude-opus, claude-opus-4.1 추가
        if model_type.lower() not in ["gpt", "openai", "claude", "anthropic", "claude-opus", "opus", "claude-opus-4.1", "opus-4.1"]:
            raise HTTPException(status_code=400, detail="지원하지 않는 모델 타입입니다. (gpt, claude, claude-opus, claude-opus-4.1만 지원)")
        
        # AI 모델 설정
        success = trading_assistant.ai_service.set_model(model_type)
        if not success:
            raise HTTPException(status_code=400, detail="AI 모델 설정에 실패했습니다.")
        
        return {
            "success": True,
            "message": f"AI 모델이 {model_type.upper()}로 설정되었습니다.",
            "current_model": trading_assistant.get_current_ai_model()
        }
        
    except Exception as e:
        print(f"AI 모델 설정 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/model")
async def get_ai_model():
    """현재 AI 모델 조회 API"""
    try:
        current_model = trading_assistant.get_current_ai_model()
        return {
            "success": True,
            "current_model": current_model,
            "available_models": ["gpt", "claude", "claude-opus", "claude-opus-4.1"]
        }
        
    except Exception as e:
        print(f"AI 모델 조회 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/scheduled-jobs")
async def get_scheduled_jobs():
    """현재 예약된 거래 작업 목록 조회"""
    try:
        jobs = trading_assistant.get_active_jobs()
        return {
            "success": True,
            "jobs": jobs
        }
    except Exception as e:
        print(f"Error in get_scheduled_jobs: {str(e)}")
        # 에러가 발생해도 빈 작업 목록 반환
        return {
            "success": True,
            "jobs": {},
            "error": "Error fetching scheduled jobs"
        }

@app.post("/api/trading/cancel-jobs")
async def cancel_scheduled_jobs():
    """예약된 모든 거래 작업 취소"""
    try:
        result = trading_assistant.cancel_all_jobs()
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        # 연결 시 현재 상태 전송
        welcome_message = {
            "type": "connection_established",
            "event_type": "CONNECTION_ESTABLISHED",  # 대문자로 통일
            "data": {
                "message": "WebSocket 연결이 성공적으로 설정되었습니다.",
                "connection_id": id(websocket),
                "active_connections": len(websocket_manager.active_connections)
            },
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_json(welcome_message)
        print(f"새 WebSocket 클라이언트에 환영 메시지 전송됨: {id(websocket)}")
        
        # 현재 트레이딩 상태 전송
        try:
            trading_status = await get_trading_status()
            status_message = {
                "type": "trading_status",
                "event_type": "TRADING_STATUS",  # 대문자로 통일
                "data": trading_status,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_json(status_message)
            print(f"새 WebSocket 클라이언트에 현재 트레이딩 상태 전송됨: {id(websocket)}")
            
            # 현재 예약된 작업 정보 전송
            try:
                scheduled_jobs = await get_scheduled_jobs()
                jobs_message = {
                    "type": "scheduled_jobs",
                    "event_type": "SCHEDULED_JOBS",  # 대문자로 통일
                    "data": scheduled_jobs,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send_json(jobs_message)
                print(f"새 WebSocket 클라이언트에 예약된 작업 정보 전송됨: {id(websocket)}")
            except Exception as e:
                print(f"예약된 작업 정보 전송 중 오류: {str(e)}")
        except Exception as e:
            print(f"트레이딩 상태 전송 중 오류: {str(e)}")
        
        while True:
            # 클라이언트로부터 메시지 수신 (필요한 경우 처리)
            data = await websocket.receive_text()
            print(f"클라이언트로부터 메시지 수신: {data[:100]}...")
            
            # 클라이언트로부터 받은 메시지에 대한 응답 (핑-퐁 메커니즘)
            try:
                message_data = json.loads(data)
                if message_data.get("type") == "ping":
                    pong_message = {
                        "type": "pong",
                        "event_type": "PONG",  # 대문자로 통일
                        "data": {
                            "message": "pong",
                            "timestamp": datetime.now().isoformat()
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send_json(pong_message)
                    print(f"클라이언트 {id(websocket)}에 pong 메시지 전송됨")
            except json.JSONDecodeError:
                print(f"잘못된 JSON 형식의 메시지 수신됨: {data[:50]}...")
            except Exception as e:
                print(f"메시지 처리 중 오류: {str(e)}")
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
        print(f"WebSocket 연결 종료됨: {id(websocket)}")
    except Exception as e:
        print(f"WebSocket 오류: {str(e)}")
        websocket_manager.disconnect(websocket)
        print(f"오류로 인한 WebSocket 연결 종료: {id(websocket)}") 