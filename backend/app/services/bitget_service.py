import base64
import hmac
import json
import time
import requests
from datetime import datetime, timedelta
from config.settings import BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_API_PASSPHRASE, BITGET_API_URL
import os
from typing import Dict, Any, Optional, List, Union

class BitgetService:
    """
    Bitget 거래소 API 연동을 위한 서비스 클래스
    - REST API를 통해 시장 데이터 조회 및 거래 기능 제공
    - API 문서: https://www.bitget.com/api-doc/contract/intro
    """
    
    def __init__(self):
        # API 인증 정보 초기화
        self.api_key = BITGET_API_KEY
        self.secret_key = BITGET_SECRET_KEY
        self.base_url = BITGET_API_URL
        self.passphrase = BITGET_API_PASSPHRASE
        self.symbol = "BTCUSDT"  # V2 API용 심볼
        self.expected_close_time = None  # expected_close_time 추가
        
        # API 요청 제한 관리를 위한 변수
        self.last_request_time = 0
        self.min_request_interval = 0.3  # 초 단위 (300ms) - Rate Limit 방지를 위해 증가
        self.retry_count = 3  # 재시도 횟수
        self.retry_delay = 2  # 재시도 간격 (초) - Rate Limit 에러 시 더 긴 대기
        
        # API 호출 시간 추적을 위한 변수
        self.last_api_call_time = 0
        self.api_call_interval = 0.2  # 초 단위 (200ms)
        
        # 로그 출력 제한을 위한 변수
        self.last_log_time = 0
        self.log_interval = 30  # 30초마다 로그 출력
        
        # 청산 로그 중복 방지 플래그
        self._position_closed_logged = False
        
        # 초기화 로그 출력
        print(f"\n=== BitgetService Initialization ===")
        print(f"API Key: {self.api_key}")
        print(f"Passphrase: {self.passphrase}")

    def _generate_signature(self, timestamp, method, request_path, body=''):
        """
        API 요청 서명 생성
        - Bitget API는 모든 요청에 서명이 필요함
        - 서명 = Base64(HMAC-SHA256(timestamp + method + requestPath + body))
        """
        path_with_query = request_path if '?' in request_path else request_path
        message = timestamp + method.upper() + path_with_query + (body or '')
        
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode('utf-8'),
                message.encode('utf-8'),
                digestmod='sha256'
            ).digest()
        ).decode()
        
        return signature

    def _make_request(self, method, endpoint, params=None, body=None):
        """
        API 요청 수행
        - HTTP 요청 헤더에 인증 정보 포함
        - 응답 결과 로깅 및 에러 처리
        - 타임아웃 설정 추가
        """
        try:
            url = f"{self.base_url}{endpoint}"
            timestamp = str(int(time.time() * 1000))
            
            if params:
                query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
                endpoint_with_query = f"{endpoint}?{query_string}"
            else:
                endpoint_with_query = endpoint
            
            body_str = json.dumps(body) if body else ''
            
            headers = {
                "ACCESS-KEY": self.api_key,
                "ACCESS-SIGN": self._generate_signature(timestamp, method, endpoint_with_query, body_str),
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": self.passphrase,
                "Content-Type": "application/json"
            }

            timeout = 15

            # 요청 간격 제한 적용
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            
            # 로그 출력 제한 (30초마다)
            should_log = (current_time - self.last_log_time) >= self.log_interval
            
            if elapsed < self.min_request_interval:
                sleep_time = self.min_request_interval - elapsed
                if should_log:
                    print(f"API 요청 간격 제한: {sleep_time:.2f}초 대기")
                time.sleep(sleep_time)
            
            # API 호출 시간 업데이트
            self.last_request_time = time.time()
            self.last_api_call_time = self.last_request_time
            
            # 로그 시간 업데이트 (필요한 경우)
            if should_log:
                self.last_log_time = current_time
            
            # 재시도 로직
            for attempt in range(self.retry_count):
                try:
                    if method == "GET":
                        response = requests.get(url, headers=headers, params=params, timeout=timeout)
                    elif method == "POST":
                        response = requests.post(url, headers=headers, json=body, timeout=timeout)
                    else:
                        raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")
                    
                    # 요청 시간 업데이트
                    self.last_request_time = time.time()
                    
                    # 응답 확인
                    if response.status_code == 429:
                        # Rate Limit 에러 시 exponential backoff 적용
                        wait_time = self.retry_delay * (2 ** attempt)  # 2초 -> 4초 -> 8초
                        print(f"API 요청 제한 초과 (429 에러). 재시도 {attempt+1}/{self.retry_count}")
                        print(f"Rate Limit으로 인해 {wait_time}초 대기 중...")
                        time.sleep(wait_time)
                        continue
                    
                    response.raise_for_status()
                    return response.json()
                    
                except requests.exceptions.Timeout:
                    print(f"Request timed out after {timeout} seconds")
                    return {"code": "TIMEOUT", "data": None, "msg": "Request timed out"}
                except requests.exceptions.RequestException as e:
                    # 에러 응답 본문 상세 출력
                    error_detail = str(e)
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_json = e.response.json()
                            error_detail = f"{str(e)}\n📋 Bitget 응답: {json.dumps(error_json, indent=2, ensure_ascii=False)}"
                        except:
                            error_detail = f"{str(e)}\n📋 응답 텍스트: {e.response.text[:500]}"
                    
                    print(f"API 요청 오류 ({attempt+1}/{self.retry_count}): {error_detail}")
                    
                    if attempt < self.retry_count - 1:
                        wait_time = self.retry_delay * (2 ** attempt)  # exponential backoff
                        print(f"요청 실패로 {wait_time}초 후 재시도...")
                        time.sleep(wait_time)
                    else:
                        print(f"최대 재시도 횟수 초과. 요청 실패: {error_detail}")
                        return {"code": "ERROR", "data": None, "msg": str(e)}
        
            return {"code": "ERROR", "data": None, "msg": "최대 재시도 횟수 초과"}
        except Exception as e:
            print(f"Error: {str(e)}")
            return {"code": "ERROR", "data": None, "msg": str(e)}

    def get_ticker(self):
        """현재 시장 데이터 조회"""
        try:
            endpoint = "/api/v2/mix/market/ticker"
            params = {
                "symbol": "BTCUSDT",
                "productType": "USDT-FUTURES"
            }
            
            response = self._make_request("GET", endpoint, params=params)
            
            if not response or not isinstance(response, dict) or 'data' not in response:
                print("Failed to get ticker data")
                return None
            
            # API 응답이 리스트 형태로 오는지 확인
            if not isinstance(response['data'], list) or not response['data']:
                print("Ticker data is not in expected format (list)")
                return None
            
            # 첫 번째 항목이 현재 시장 데이터
            ticker_data = response['data'][0]
            
            # 필수 필드 확인
            required_fields = ['lastPr', 'high24h', 'low24h', 'baseVolume']
            if not all(field in ticker_data for field in required_fields):
                print(f"Missing required fields in ticker data. Available fields: {ticker_data.keys()}")
                return None
            
            print("Successfully retrieved ticker data")
            return response
            
        except Exception as e:
            print(f"Error in get_ticker: {str(e)}")
            return None

    def get_kline(self, symbol: str = "BTCUSDT", productType: str = "USDT-FUTURES", 
                  granularity: str = "1m", limit: str = "100", 
                  startTime: str = None, endTime: str = None):
        """
        캔들스틱 데이터 조회
        Args:
            symbol: 거래 쌍 (예: BTCUSDT)
            productType: 상품 유형 (예: USDT-FUTURES)
            granularity: 시간 단위 (1m, 5m, 15m, 30m, 1H, 4H, 1D 등)
            limit: 조회할 캔들 개수 (최대 1000)
            startTime: 시작 시간 (밀리초)
            endTime: 종료 시간 (밀리초)
        """
        try:
            endpoint = "/api/v2/mix/market/candles"
            params = {
                "symbol": symbol,
                "productType": productType,
                "granularity": granularity,
                "limit": limit
            }
            if startTime:
                params["startTime"] = startTime
            if endTime:
                params["endTime"] = endTime

            response = self._make_request("GET", endpoint, params=params)
            
            if response and 'data' in response:
                print(f"Successfully retrieved {granularity} klines")
            else:
                print(f"Failed to retrieve {granularity} klines")
            
            return response

        except Exception as e:
            print(f"Error in get_kline: {str(e)}")
            return None

    def get_account_info(self):
        """
        계정 정보 조회
        - USDT 선물 계정의 상세 정보를 조회합니다.
        - API 문서: /api/v2/mix/account/account
        """
        try:
            endpoint = "/api/v2/mix/account/account"
            params = {
                "symbol": "BTCUSDT",
                "productType": "USDT-FUTURES",
                "marginCoin": "USDT"
            }
            response = self._make_request("GET", endpoint, params=params)
            
            if response and 'data' in response:
                print("Successfully retrieved account info")
            else:
                print("Failed to retrieve account info")
            
            return response
        except Exception as e:
            print(f"Error in get_account_info: {str(e)}")
            return {"code": "ERROR", "data": None, "msg": str(e)}

    def get_positions(self):
        """현재 포지션 조회"""
        try:
            endpoint = "/api/v2/mix/position/all-position"
            params = {
                "productType": "USDT-FUTURES",
                "marginCoin": "USDT"
            }
            result = self._make_request("GET", endpoint, params=params)
            return result
        except Exception as e:
            print(f"Error in get_positions: {str(e)}")
            return None

    def get_orderbook(self, limit=100):
        """
        호가창 데이터 조회
        - 매수/매도 주문 데이터 조회
        """
        endpoint = "/api/v2/mix/market/orderbook"
        params = {
            "symbol": "BTCUSDT",
            "productType": "USDT-FUTURES",
            "limit": limit
        }
        response = self._make_request("GET", endpoint, params=params)
        
        if response and 'data' in response:
            print("Successfully retrieved orderbook")
        else:
            print("Failed to retrieve orderbook")
        
        return response

    def get_leverage(self):
        """
        레버리지 설정 조회
        - 현재 설정된 레버리지 배율을 조회합니다.
        """
        endpoint = "/api/v2/mix/account/leverage-info"
        params = {
            "symbol": "BTCUSDT",
            "marginCoin": "USDT",
            "productType": "USDT-FUTURES"
        }
        return self._make_request("GET", endpoint, params=params)

    def get_margin_mode(self):
        """
        마진 모드 조회
        - 현재 설정된 마진 모드를 조회합니다.
        """
        endpoint = "/api/v2/mix/account/account-mode"
        params = {
            "productType": "USDT-FUTURES"
        }
        return self._make_request("GET", endpoint, params=params)

    def set_margin_mode(self):
        """마진 모드를 격리(isolated)로 설정"""
        endpoint = "/api/v2/mix/account/set-account-mode"
        body = {
            "productType": "USDT-FUTURES",
            "marginMode": "isolated"
        }
        return self._make_request("POST", endpoint, body=body)

    def set_leverage(self, leverage=5):
        """레버리지 설정
        Args:
            leverage (int): 설정할 레버리지 값 (기본값: 5)
        """
        endpoint = "/api/v2/mix/account/set-leverage"
        body = {
            "symbol": "BTCUSDT",
            "productType": "USDT-FUTURES",
            "marginCoin": "USDT",
            "leverage": str(leverage)
        }
        return self._make_request("POST", endpoint, body=body)

    def place_order(self, size, side, expected_minutes=None, leverage=5, stop_loss_roe=5.0, take_profit_roe=10.0):
        """
        주문 실행 (One-way position mode)
        Args:
            size: 주문 수량 (BTC)
            side: 주문 방향 (buy/sell)
            expected_minutes: 예상 보유 시간 (분)
            leverage: 레버리지 배수 (기본값: 5)
            stop_loss_roe: Stop Loss 가격 변동률 % (AI가 제공한 값)
            take_profit_roe: Take Profit 가격 변동률 % (AI가 제공한 값)
        """
        try:
            # 새로운 포지션 생성 시 청산 로그 플래그 리셋
            self._position_closed_logged = False
            
            ticker = self.get_ticker()
            if not ticker or 'data' not in ticker or not ticker['data']:
                raise Exception("Failed to get ticker info")
            
            current_price = float(ticker['data'][0]['lastPr'])
            
            leverage_result = self.set_leverage(leverage)
            if not leverage_result or leverage_result.get('code') != '00000':
                raise Exception("Failed to set leverage")
            
            actual_leverage = float(leverage_result['data']['longLeverage'])
            
            # AI가 제공한 가격 변동률을 그대로 사용
            if side == "buy":
                stop_loss_price = round(current_price * (1 - (stop_loss_roe / 100)), 1)
                take_profit_price = round(current_price * (1 + (take_profit_roe / 100)), 1)
            else:
                stop_loss_price = round(current_price * (1 + (stop_loss_roe / 100)), 1)
                take_profit_price = round(current_price * (1 - (take_profit_roe / 100)), 1)
            
            endpoint = "/api/v2/mix/order/place-order"
            body = {
                "symbol": "BTCUSDT",
                "productType": "USDT-FUTURES",
                "marginMode": "isolated",
                "marginCoin": "USDT",
                "size": size,
                "side": side,
                "orderType": "market",
                # ✅ Preset TPSL을 주문과 함께 설정 (가장 안정적인 방법)
                "presetStopSurplusPrice": str(take_profit_price),
                "presetStopLossPrice": str(stop_loss_price)
            }
            
            print(f"\n=== 주문 생성 요청 (TPSL 포함) ===")
            print(f"Body: {json.dumps(body, indent=2)}")
            print(f"Take Profit 가격: {take_profit_price}")
            print(f"Stop Loss 가격: {stop_loss_price}")
            
            order_result = self._make_request("POST", endpoint, body=body)
            
            print(f"\n=== 주문 생성 결과 ===")
            print(f"결과: {json.dumps(order_result, indent=2) if order_result else 'None'}")
            
            if not order_result:
                raise Exception("No response from order API")
            
            if order_result.get('code') != '00000':
                error_msg = order_result.get('msg', 'Unknown error')
                raise Exception(f"Order failed: {error_msg}")
            
            print(f"\n✅ 주문 체결 및 TPSL 설정 완료 (Preset 방식)")
            
            if expected_minutes:
                self.expected_close_time = datetime.now() + timedelta(minutes=expected_minutes)
                print(f"Expected close time: {self.expected_close_time}")
            self._start_stop_loss_monitoring()
            
            return order_result
            
        except Exception as e:
            print(f"주문 실행 중 에러: {str(e)}")
            return {
                "code": "ERROR",
                "msg": str(e),
                "data": None
            }

    def _start_stop_loss_monitoring(self):
        """Stop-loss 청산 모니터링 시작"""
        import threading
        import time
        
        def monitor_position():
            initial_position = self.get_positions()
            while True:
                time.sleep(1)  # 1초마다 체크
                current_position = self.get_positions()
                
                # Stop-loss 또는 Take-profit으로 인한 청산 감지
                if self._is_position_closed_early(initial_position, current_position):
                    print("Stop-loss 또는 Take-profit에 의한 청산 감지됨")
                    
                    # 트레이딩 어시스턴트에 청산 감지 신호 전송
                    from .trading_assistant import TradingAssistant
                    # 싱글톤 인스턴스를 가져옴 (새로 생성하지 않음)
                    trading_assistant = TradingAssistant._instance
                    
                    # 인스턴스가 없는 경우 처리
                    if trading_assistant is None:
                        print("TradingAssistant 인스턴스가 없습니다. 청산 감지를 처리할 수 없습니다.")
                        break
                    
                    # 청산 플래그 설정 - 포지션 모니터링 스레드에서 처리하도록 함
                    trading_assistant._liquidation_detected = True
                    print("청산 감지 플래그 설정됨 - 포지션 모니터링 스레드에서 처리됩니다.")
                    print(f"TradingAssistant 인스턴스 ID: {id(trading_assistant)}")
                    
                    # 이전 코드 제거: 직접 분석 작업을 예약하지 않고 포지션 모니터링 스레드에서 처리하도록 함
                    break
        
        # 모니터링 스레드 시작
        monitor_thread = threading.Thread(target=monitor_position)
        monitor_thread.daemon = True
        monitor_thread.start()

    def _is_position_closed_early(self, initial_position, current_position):
        """Stop-loss 또는 Take-profit에 의한 조기 청산 여부 확인"""
        try:
            if not initial_position or not current_position:
                return False
                
            initial_data = initial_position.get('data', [])
            current_data = current_position.get('data', [])
            
            # 포지션이 청산되었는지 확인
            position_closed = False
            
            # 초기에 포지션이 있었는데 현재 없는 경우
            if initial_data and not current_data:
                position_closed = True
            
            # 포지션 크기가 0이 되었는지 확인
            for pos in current_data:
                if pos['symbol'] == 'BTCUSDT' and float(pos.get('total', 0)) == 0:
                    position_closed = True
                    break
            
            if position_closed:
                # 이미 청산 로그를 출력했다면 중복 방지
                if self._position_closed_logged:
                    return False if self.expected_close_time and datetime.now() >= self.expected_close_time else True
                
                # expected_close_time이 설정되어 있고, 현재 시간이 expected_close_time 이전인 경우
                # Stop-loss 또는 Take-profit으로 판단
                if self.expected_close_time and datetime.now() < self.expected_close_time:
                    print("조기 청산 감지: Expected time 이전에 포지션 청산됨")
                    self._position_closed_logged = True
                    return True
                else:
                    print("정상 청산 감지: Expected time 이후에 포지션 청산됨")
                    self._position_closed_logged = True
                    return False
            else:
                # 포지션이 다시 생성되면 플래그 리셋
                self._position_closed_logged = False
            
            return False
        except Exception as e:
            print(f"청산 확인 중 에러: {str(e)}")
            return False

    def close_position(self, position_size=1.0):
        """
        포지션 청산 (전체 또는 일부)
        Args:
            position_size: 청산할 포지션 비율 (0.1~1.0, 기본값 1.0은 전체 청산)
        """
        try:
            # 1. 현재 포지션 조회
            positions = self.get_positions()
            if not positions or 'data' not in positions or not positions['data']:
                print("No active positions to close")
                return {
                    "success": True,
                    "message": "No active positions to close"
                }
            
            # 2. BTCUSDT 포지션 찾기
            btc_positions = [pos for pos in positions['data'] 
                            if pos['symbol'] == 'BTCUSDT' and float(pos.get('total', 0)) != 0]
            
            if not btc_positions:
                print("No active BTC positions to close")
                return {
                    "success": True,
                    "message": "No active BTC positions to close"
                }
            
            # 3. 각 포지션 청산
            results = []
            for position in btc_positions:
                # 포지션 정보 추출
                side = position.get('holdSide', '')  # long 또는 short
                total_size = float(position.get('total', 0))
                
                # 청산할 크기 계산 (비율 적용)
                close_size = total_size * position_size
                
                # 청산을 위한 반대 방향 주문 실행
                # long 포지션은 sell로 청산, short 포지션은 buy로 청산
                close_side = "sell" if side.lower() == "long" else "buy"
                
                print(f"\n=== 포지션 청산 상세 ===")
                print(f"포지션 방향: {side}")
                print(f"전체 크기: {total_size} BTC")
                print(f"청산 비율: {position_size * 100}%")
                print(f"청산 크기: {close_size} BTC")
                print(f"청산 방향: {close_side}")
                
                # 주문 실행
                order_result = self.place_order(
                    size=str(close_size),
                    side=close_side
                )
                
                results.append({
                    "position": position,
                    "close_size": close_size,
                    "order_result": order_result
                })
            
            return {
                "success": True,
                "message": f"Closed {position_size * 100}% of positions",
                "results": results
            }
            
        except Exception as e:
            print(f"Error closing position: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to close position: {str(e)}"
            }

    def partial_close_position(self, percentage=50):
        """
        포지션 부분 청산
        Args:
            percentage: 청산할 비율 (기본값: 50, 즉 50%)
        Returns:
            청산 결과
        """
        try:
            print(f"\n=== 부분 청산 시작 ({percentage}%) ===")
            
            # 1. 현재 포지션 확인
            positions = self.get_positions()
            if not positions or 'data' not in positions:
                raise Exception("포지션 정보를 가져올 수 없음")
            
            # 2. 청산할 포지션 찾기
            target_position = None
            for pos in positions['data']:
                if float(pos.get('total', 0)) > 0:
                    target_position = pos
                    break
            
            if not target_position:
                return {
                    "success": False,
                    "message": "청산할 포지션이 없습니다."
                }
            
            # 3. 포지션 정보 추출
            position_size = float(target_position.get('total', 0))
            position_side = target_position.get('holdSide')  # 'long' or 'short'
            
            print(f"현재 포지션: {position_side}")
            print(f"포지션 크기: {position_size} BTC")
            print(f"청산할 비율: {percentage}%")
            
            # 4. 청산할 수량 계산
            close_size = position_size * (percentage / 100)
            close_size = round(close_size, 4)  # 소수점 4자리로 반올림
            
            print(f"청산할 수량: {close_size} BTC")
            
            # 5. 반대 방향 주문으로 포지션 축소
            # 롱 포지션이면 sell 주문, 숏 포지션이면 buy 주문
            opposite_side = "sell" if position_side == "long" else "buy"
            
            endpoint = "/api/v2/mix/order/place-order"
            body = {
                "symbol": "BTCUSDT",
                "productType": "USDT-FUTURES",
                "marginMode": "crossed",
                "marginCoin": "USDT",
                "size": str(close_size),
                "side": opposite_side,
                "orderType": "market",
                "reduceOnly": "YES"  # 포지션 축소만 가능, 새로운 반대 포지션 생성 안 함
            }
            
            print(f"부분 청산 주문: {opposite_side} {close_size} BTC (reduceOnly)")
            
            # 6. 주문 실행
            result = self._make_request("POST", endpoint, body=body)
            
            if result and result.get('code') == '00000':
                print(f"부분 청산 성공: {percentage}% ({close_size} BTC)")
                return {
                    "success": True,
                    "message": f"{percentage}% 부분 청산 완료",
                    "closed_size": close_size,
                    "remaining_size": position_size - close_size,
                    "order_result": result
                }
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                print(f"부분 청산 실패: {error_msg}")
                return {
                    "success": False,
                    "message": f"부분 청산 실패: {error_msg}",
                    "order_result": result
                }
                
        except Exception as e:
            print(f"부분 청산 중 오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"부분 청산 중 오류: {str(e)}"
            }

    def execute_trade(self):
        """전체 거래 프로세스 실행"""
        try:
            # 1. 마진 모드 설정
            margin_result = self.set_margin_mode()
            print("Margin mode set result:", margin_result)
            if not margin_result or margin_result.get('code') != '00000':
                raise Exception(f"Failed to set margin mode: {margin_result.get('msg') if margin_result else 'No response'}")

            # 2. 레버리지 설정
            leverage_result = self.set_leverage()
            print("Leverage set result:", leverage_result)
            if not leverage_result or leverage_result.get('code') != '00000':
                raise Exception(f"Failed to set leverage: {leverage_result.get('msg') if leverage_result else 'No response'}")

            # 3. 계정 잔고 조회
            account_info = self.get_account_info()
            if not account_info or 'data' not in account_info:
                raise Exception("Failed to get account info")

            # 4. USDT 잔고 찾기 및 계산
            usdt_account = next((acc for acc in account_info['data'] if acc['marginCoin'] == 'USDT'), None)
            if not usdt_account:
                raise Exception("USDT account not found")
            
            # 전체 계정 가치 사용
            margin = float(usdt_account['equity'])
            if margin <= 0:
                raise Exception("Insufficient balance")
            
            # 레버리지를 고려한 실제 주문 가능 금액 계산
            total_order_value = margin * 2  # 레버리지 2배
            print(f"Margin: {margin} USDT")
            print(f"Total order value (with 2x leverage): {total_order_value} USDT")

            # 5. 현재 BTC 가격 조회
            ticker = self.get_ticker()
            if not ticker or 'data' not in ticker or not isinstance(ticker['data'], list) or not ticker['data']:
                raise Exception("Failed to get ticker info")
            
            # API 문서에 따라 첫 번째 항목의 lastPr 사용
            ticker_data = ticker['data'][0]
            if 'lastPr' not in ticker_data:
                raise Exception("Last price not found in ticker data")
            
            current_price = float(ticker_data['lastPr'])
            if current_price <= 0:
                raise Exception("Invalid current price")
            
            print(f"Current BTC price: {current_price} USDT")

            # 6. 주문 수량 계산 수정
            safety_factor = 0.95  # 수수료와 슬리피지를 위한 안전 계수
            usable_margin = margin * safety_factor  # 실제 사용할 증거금

            # 레버리지를 고려한 주문 수량 계산
            order_size = round((usable_margin * 2) / current_price, 4)  # BTC 수량

            print(f"Total margin: {margin} USDT")
            print(f"Usable margin (after safety factor): {usable_margin} USDT")
            print(f"Calculated order size: {order_size} BTC")
            print(f"Position value: {order_size * current_price} USDT")  # 실제 포지션 가치
            print(f"Required margin: {usable_margin} USDT")  # 필요한 증거금

            # 7. 주문 실행
            order_result = self.place_order(str(order_size))
            print("Order result:", order_result)
            if not order_result or order_result.get('code') != '00000':
                raise Exception(f"Order failed: {order_result.get('msg') if order_result else 'No response'}")

            return {
                "success": True,
                "message": "Trade executed successfully",
                "order_result": order_result,
                "details": {
                    "balance_used": total_order_value,
                    "order_size": order_size,
                    "price": current_price
                }
            }

        except Exception as e:
            print(f"Error executing trade: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to execute trade: {str(e)}"
            }

    def _format_account_data(self, account_info):
        """계정 정보 포맷팅"""
        try:
            if not account_info:
                print("계정 정보가 없습니다.")
                return self._get_default_account_data()
            
            print("\n=== Format Account Data ===")
            print(f"Account info type: {type(account_info)}")
            print(f"Account info: {account_info}")
            
            if not isinstance(account_info, dict) or 'data' not in account_info:
                print("계정 데이터가 없거나 올바른 형식이 아닙니다.")
                return self._get_default_account_data()
            
            account_data = account_info['data']
            print(f"Account data: {account_data}")

            # API 응답의 실제 키 이름 확인
            if isinstance(account_data, dict):
                print(f"Available keys in account data: {account_data.keys()}")
                
                # API 문서 기반 키 매핑
                result = {
                    "equity": float(account_data.get('accountEquity', 0)),
                    "available_balance": float(account_data.get('available', 0)),
                    "used_margin": float(account_data.get('locked', 0)),
                    "unrealized_pnl": float(account_data.get('unrealizedPL', 0))
                }
                
                print(f"Formatted result: {result}")
                return result
            else:
                print("Account data is not in expected format")
                return self._get_default_account_data()
            
        except Exception as e:
            print(f"Error in _format_account_data: {str(e)}")
            print(f"Error details: {e.__class__.__name__}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return self._get_default_account_data()
    
    def _get_default_account_data(self):
        """기본 계정 데이터 반환"""
        return {
            "equity": 0,
            "available_balance": 0,
            "used_margin": 0,
            "unrealized_pnl": 0
        }

    def close_positions(self, symbol="BTCUSDT", hold_side=None):
        """포지션 강제 청산 (Flash Close)
        Args:
            symbol (str): 거래 쌍 (예: BTCUSDT)
            hold_side (str, optional): 포지션 방향 (long/short). None이면 양방향 모두 청산
        Returns:
            dict: 청산 결과
        """
        try:
            endpoint = "/api/v2/mix/order/close-positions"
            
            # API 요청 파라미터
            body = {
                "symbol": symbol,
                "productType": "USDT-FUTURES"
            }
            
            # hold_side가 지정된 경우에만 포함
            if hold_side:
                body["holdSide"] = hold_side
            
            # API 요청 실행
            response = self._make_request("POST", endpoint, body=body)
            
            if response:
                success_count = len(response.get('data', {}).get('successList', []))
                failure_count = len(response.get('data', {}).get('failureList', []))
                
                print(f"\n=== 포지션 청산 결과 ===")
                print(f"성공: {success_count}건")
                print(f"실패: {failure_count}건")
                
                if failure_count > 0:
                    print("\n실패 상세:")
                    for failure in response['data']['failureList']:
                        print(f"- Symbol: {failure['symbol']}")
                        print(f"  Error: {failure['errorMsg']} (Code: {failure['errorCode']})")
                
                return {
                    'success': success_count > 0 and failure_count == 0,
                    'message': f"Successfully closed {success_count} positions" if success_count > 0 else "No positions closed",
                    'data': response['data']
                }
            
            return {
                'success': False,
                'message': "Failed to close positions",
                'data': None
            }
            
        except Exception as e:
            print(f"포지션 청산 중 오류: {str(e)}")
            return {
                'success': False,
                'message': str(e),
                'data': None
            }
    
    def get_plan_orders(self, plan_type=None):
        """
        미체결 Plan Order 조회
        
        Args:
            plan_type: 'pos_profit', 'pos_loss', 'normal_plan', 'track_plan' 등
        
        Returns:
            dict: Plan Order 목록
        """
        try:
            endpoint = "/api/v2/mix/order/orders-plan-pending"
            params = {
                "symbol": "BTCUSDT",
                "productType": "usdt-futures"  # ⚠️ 소문자 사용 (Plan Order API는 소문자 요구)
            }
            
            # planType은 선택적 파라미터이므로 None이 아닐 때만 추가
            # (이전 수정에서 None으로 호출하여 에러 방지)
            if plan_type:
                params['planType'] = plan_type
            
            # _make_request에 params를 직접 전달 (자동으로 쿼리스트링 생성 및 서명 처리)
            result = self._make_request("GET", endpoint, params=params)
            return result
            
        except Exception as e:
            print(f"Plan Order 조회 중 오류: {str(e)}")
            return None
    
    def cancel_plan_order(self, order_id, plan_type):
        """
        Plan Order 취소
        
        Args:
            order_id: 취소할 주문 ID
            plan_type: 'pos_profit', 'pos_loss' 등
        
        Returns:
            dict: 취소 결과
        """
        try:
            endpoint = "/api/v2/mix/order/cancel-plan-order"
            body = {
                "symbol": "BTCUSDT",
                "productType": "usdt-futures",  # ⚠️ 소문자 사용
                "marginCoin": "USDT",
                "orderId": order_id,
                "planType": plan_type
            }
            
            result = self._make_request("POST", endpoint, body=body)
            return result
            
        except Exception as e:
            print(f"Plan Order 취소 중 오류: {str(e)}")
            return None

    def find_candle_by_time(self, candles, target_time_str):
        """
        캔들 데이터에서 특정 시간과 일치하는 캔들 찾기
        
        Args:
            candles: 캔들 데이터 리스트 (각 캔들은 timestamp 필드 포함)
            target_time_str: 찾을 시간 문자열 (예: "2025-10-11 06:00")
        
        Returns:
            dict: 찾은 캔들 정보 (index, timestamp, low/high, volume 등)
                  찾지 못하면 None 반환
        """
        try:
            print(f"\n=== 캔들 검색 시작 ===")
            print(f"검색 대상 시간: {target_time_str}")
            print(f"전체 캔들 개수: {len(candles)}")
            
            # 목표 시간을 분 단위까지만 파싱 (초는 무시)
            # "YYYY-MM-DD HH:MM" 또는 "YYYY-MM-DD HH:MM:SS" 형식 모두 지원
            target_time_parts = target_time_str.strip().split(':')
            if len(target_time_parts) >= 2:
                target_time_minute = ':'.join(target_time_parts[:2])  # YYYY-MM-DD HH:MM까지만
            else:
                target_time_minute = target_time_str.strip()
            
            print(f"파싱된 목표 시간 (분 단위): {target_time_minute}")
            
            # 캔들 리스트 순회
            for idx, candle in enumerate(candles):
                candle_timestamp_ms = candle.get('timestamp', 0)
                
                if candle_timestamp_ms > 0:
                    # UTC 시간으로 변환 후 KST로 변환
                    from datetime import datetime, timedelta
                    dt_utc = datetime.utcfromtimestamp(candle_timestamp_ms / 1000)
                    dt_kst = dt_utc + timedelta(hours=9)
                    
                    # 분 단위까지만 문자열로 변환 (YYYY-MM-DD HH:MM)
                    candle_time_str = dt_kst.strftime('%Y-%m-%d %H:%M')
                    
                    # 목표 시간과 비교 (분 단위까지만)
                    if candle_time_str == target_time_minute:
                        print(f"✅ 캔들 발견! 인덱스: {idx}, 시간: {candle_time_str}")
                        
                        # 캔들 정보 반환
                        result = {
                            'index': idx,
                            'timestamp': candle_time_str,
                            'timestamp_ms': candle_timestamp_ms,
                            'open': candle.get('open'),
                            'high': candle.get('high'),
                            'low': candle.get('low'),
                            'close': candle.get('close'),
                            'volume': candle.get('volume')
                        }
                        print(f"반환 정보: {result}")
                        return result
            
            print(f"⚠️ 해당 시간의 캔들을 찾지 못했습니다.")
            return None
            
        except Exception as e:
            print(f"캔들 검색 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def update_position_tpsl(self, stop_loss_roe, take_profit_roe):
        """
        현재 포지션의 Take Profit과 Stop Loss 업데이트
        
        Args:
            stop_loss_roe: Stop Loss 가격 변동률 % (AI가 제공한 값)
            take_profit_roe: Take Profit 가격 변동률 % (AI가 제공한 값)
        
        Returns:
            dict: 업데이트 결과
        """
        try:
            print(f"\n=== Take Profit / Stop Loss 업데이트 ===")
            print(f"Stop Loss ROE: {stop_loss_roe}%")
            print(f"Take Profit ROE: {take_profit_roe}%")
            
            # 현재 포지션 정보 조회
            positions = self.get_positions()
            if not positions or 'data' not in positions:
                return {
                    'success': False,
                    'message': "포지션 정보를 가져올 수 없습니다."
                }
            
            # 활성 포지션 찾기
            active_position = None
            for pos in positions['data']:
                if float(pos.get('total', 0)) > 0:
                    active_position = pos
                    break
            
            if not active_position:
                return {
                    'success': False,
                    'message': "활성 포지션이 없습니다."
                }
            
            # 현재가 조회 (모니터링 시점 기준)
            ticker = self.get_ticker()
            if not ticker or 'data' not in ticker or not ticker['data']:
                return {
                    'success': False,
                    'message': "현재가 조회 실패"
                }
            
            current_price = float(ticker['data'][0]['lastPr'])
            position_hold_side = active_position.get('holdSide')  # 포지션의 holdSide ('long' 또는 'short')
            position_size = active_position.get('total')
            entry_price = float(active_position.get('openPriceAvg', 0))
            
            # One-way 모드: Plan Order API용 holdSide 변환
            # 포지션의 holdSide ('long'/'short') → Plan Order holdSide ('buy'/'sell')
            hold_side = 'buy' if position_hold_side == 'long' else 'sell'
            
            # ⚠️ 모니터링 분석: 현재가를 기준으로 TPSL 가격 계산
            # (모니터링 시점에서 새로 분석하는 것이므로 현재가 기준이 맞음)
            if position_hold_side == 'long':
                stop_loss_price = round(current_price * (1 - (stop_loss_roe / 100)), 1)
                take_profit_price = round(current_price * (1 + (take_profit_roe / 100)), 1)
            else:  # short
                stop_loss_price = round(current_price * (1 + (stop_loss_roe / 100)), 1)
                take_profit_price = round(current_price * (1 - (take_profit_roe / 100)), 1)
            
            print(f"포지션 방향: {position_hold_side}")
            print(f"Plan Order holdSide (One-way 모드): {hold_side}")
            print(f"포지션 크기: {position_size}")
            print(f"진입가: {entry_price}")
            print(f"현재가: {current_price} (TPSL 계산 기준)")
            print(f"새 Stop Loss ROE: {stop_loss_roe}% → 가격: {stop_loss_price}")
            print(f"새 Take Profit ROE: {take_profit_roe}% → 가격: {take_profit_price}")
            
            # 1단계: 기존 TPSL Plan Order 조회
            print("\n[1단계] 기존 TPSL Plan Order 조회 중...")
            
            # 모든 Plan Order 조회 (planType 파라미터 없이)
            all_orders = self.get_plan_orders(plan_type=None)
            
            print(f"\n📋 Plan Order 조회 결과:")
            print(f"  응답 코드: {all_orders.get('code') if all_orders else 'None'}")
            print(f"  전체 응답: {json.dumps(all_orders, indent=2) if all_orders else 'None'}")
            
            existing_tp_order = None
            existing_sl_order = None
            
            # Plan Order가 있는지 확인
            if all_orders and all_orders.get('code') == '00000' and all_orders.get('data'):
                order_list = all_orders['data'].get('entrustedList', [])
                print(f"  Plan Order 개수: {len(order_list)}")
                
                # BTCUSDT 심볼의 TPSL Order 찾기
                for order in order_list:
                    print(f"  - Order: symbol={order.get('symbol')}, planType={order.get('planType')}, orderId={order.get('orderId')}")
                    if order.get('symbol') == 'BTCUSDT':
                        order_plan_type = order.get('planType')
                        
                        if order_plan_type == 'pos_profit':
                            existing_tp_order = order
                            print(f"  ✅ 기존 Take Profit Order 발견: {order.get('orderId')}, 현재 가격: {order.get('triggerPrice')}")
                        elif order_plan_type == 'pos_loss':
                            existing_sl_order = order
                            print(f"  ✅ 기존 Stop Loss Order 발견: {order.get('orderId')}, 현재 가격: {order.get('triggerPrice')}")
            else:
                print(f"  ⚠️ 기존 Plan Order 조회 실패 또는 없음")
                if all_orders:
                    print(f"  응답 메시지: {all_orders.get('msg', 'No message')}")
            
            # 2단계: TPSL Order 수정 또는 생성
            print("\n[2단계] TPSL Order 수정/생성 중...")
            
            tp_result = None
            sl_result = None
            
            # Take Profit 처리
            if existing_tp_order:
                # 기존 TP Order 수정 (modify API 사용)
                print(f"\n✏️ Take Profit Order 수정 중... (가격: {take_profit_price})")
                endpoint_modify = "/api/v2/mix/order/modify-tpsl-order"
                
                tp_modify_body = {
                    "orderId": existing_tp_order.get('orderId'),
                    "marginCoin": "USDT",
                    "productType": "usdt-futures",  # ⚠️ 소문자 사용
                    "symbol": "BTCUSDT",
                    "triggerPrice": str(take_profit_price),
                    "triggerType": "mark_price",  # 마크 프라이스 기준
                    "executePrice": "0",  # 시장가 실행
                    "size": ""  # ⚠️ 포지션 익절/손절의 경우 빈 문자열
                }
                
                print(f"수정 요청 Body: {json.dumps(tp_modify_body, indent=2)}")
                tp_result = self._make_request("POST", endpoint_modify, body=tp_modify_body)
            else:
                # 새 TP Order 생성 (place API 사용)
                print(f"\n➕ Take Profit Order 생성 중... (가격: {take_profit_price})")
                endpoint_place = "/api/v2/mix/order/place-tpsl-order"
                
                tp_place_body = {
                    "symbol": "BTCUSDT",
                    "productType": "usdt-futures",  # ⚠️ 소문자 사용
                    "marginCoin": "USDT",
                    "planType": "pos_profit",
                    "triggerPrice": str(take_profit_price),
                    "triggerType": "mark_price",
                    "executePrice": "0",
                    "holdSide": hold_side,
                    "size": ""  # ⚠️ 포지션 익절/손절의 경우 빈 문자열
                }
                
                print(f"생성 요청 Body: {json.dumps(tp_place_body, indent=2)}")
                tp_result = self._make_request("POST", endpoint_place, body=tp_place_body)
            
            # Stop Loss 처리
            if existing_sl_order:
                # 기존 SL Order 수정 (modify API 사용)
                print(f"\n✏️ Stop Loss Order 수정 중... (가격: {stop_loss_price})")
                endpoint_modify = "/api/v2/mix/order/modify-tpsl-order"
                
                sl_modify_body = {
                    "orderId": existing_sl_order.get('orderId'),
                    "marginCoin": "USDT",
                    "productType": "usdt-futures",  # ⚠️ 소문자 사용
                    "symbol": "BTCUSDT",
                    "triggerPrice": str(stop_loss_price),
                    "triggerType": "mark_price",  # 마크 프라이스 기준
                    "executePrice": "0",  # 시장가 실행
                    "size": ""  # ⚠️ 포지션 익절/손절의 경우 빈 문자열
                }
                
                print(f"수정 요청 Body: {json.dumps(sl_modify_body, indent=2)}")
                sl_result = self._make_request("POST", endpoint_modify, body=sl_modify_body)
            else:
                # 새 SL Order 생성 (place API 사용)
                print(f"\n➕ Stop Loss Order 생성 중... (가격: {stop_loss_price})")
                endpoint_place = "/api/v2/mix/order/place-tpsl-order"
                
                sl_place_body = {
                    "symbol": "BTCUSDT",
                    "productType": "usdt-futures",  # ⚠️ 소문자 사용
                    "marginCoin": "USDT",
                    "planType": "pos_loss",
                    "triggerPrice": str(stop_loss_price),
                    "triggerType": "mark_price",
                    "executePrice": "0",
                    "holdSide": hold_side,
                    "size": ""  # ⚠️ 포지션 익절/손절의 경우 빈 문자열
                }
                
                print(f"생성 요청 Body: {json.dumps(sl_place_body, indent=2)}")
                sl_result = self._make_request("POST", endpoint_place, body=sl_place_body)
            
            print(f"\nTake Profit 설정 결과: {tp_result}")
            print(f"Stop Loss 설정 결과: {sl_result}")
            
            # 결과 확인
            tp_success = tp_result and tp_result.get('code') == '00000'
            sl_success = sl_result and sl_result.get('code') == '00000'
            
            if tp_success and sl_success:
                action_desc = "수정" if (existing_tp_order or existing_sl_order) else "생성"
                print(f"\n✅ Take Profit과 Stop Loss가 성공적으로 {action_desc}되었습니다.")
                return {
                    'success': True,
                    'message': f'Take Profit과 Stop Loss가 {action_desc}되었습니다.',
                    'take_profit_price': take_profit_price,
                    'stop_loss_price': stop_loss_price,
                    'modified': bool(existing_tp_order or existing_sl_order)
                }
            else:
                error_msg = []
                if not tp_success:
                    tp_error = tp_result.get('msg', 'Unknown error') if tp_result else 'No response'
                    error_msg.append(f"Take Profit 설정 실패: {tp_error}")
                if not sl_success:
                    sl_error = sl_result.get('msg', 'Unknown error') if sl_result else 'No response'
                    error_msg.append(f"Stop Loss 설정 실패: {sl_error}")
                
                return {
                    'success': False,
                    'message': ' / '.join(error_msg)
                }
            
        except Exception as e:
            print(f"TPSL 업데이트 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': str(e)
            } 