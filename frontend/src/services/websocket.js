import React, { useState, useEffect, useCallback } from 'react';

// WebSocket 연결 상태 상수
export const WS_STATUS = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3
};

// WebSocket 이벤트 타입
export const WS_EVENT_TYPES = {
  MARKET_UPDATE: 'MARKET_UPDATE',
  POSITION_UPDATE: 'POSITION_UPDATE',
  LIQUIDATION_DETECTED: 'LIQUIDATION_DETECTED',
  ANALYSIS_RESULT: 'ANALYSIS_RESULT',
  TRADING_STATUS: 'TRADING_STATUS',
  SCHEDULED_JOBS: 'SCHEDULED_JOBS',
  ANALYSIS_ONLY_RESULT: 'ANALYSIS_ONLY_RESULT'
};

// WebSocket 연결 설정
const WS_URL = 'ws://localhost:8000/ws';
let ws = null;
let reconnectAttempts = 0;
let reconnectTimeout = null;
const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY = 1000; // 1초

// 상태 리스너 관리
const statusListeners = new Set();
const messageListeners = new Map();

// WebSocket 상태 관리
let currentStatus = WS_STATUS.CLOSED;

/**
 * WebSocket 연결 함수
 */
export const connectWebSocket = () => {
  if (ws && (ws.readyState === WS_STATUS.OPEN || ws.readyState === WS_STATUS.CONNECTING)) {
    console.log('WebSocket 이미 연결됨 또는 연결 중');
    return;
  }

  try {
    console.log('WebSocket 연결 시도...');
    ws = new WebSocket(WS_URL);
    currentStatus = WS_STATUS.CONNECTING;
    notifyStatusChange();

    ws.onopen = () => {
      console.log('WebSocket 연결 성공');
      currentStatus = WS_STATUS.OPEN;
      reconnectAttempts = 0;
      notifyStatusChange();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('WebSocket 메시지 수신:', data);
        
        // type 또는 event_type을 기준으로 리스너에게 알림
        const eventType = data.type || data.event_type;
        if (eventType && messageListeners.has(eventType)) {
          messageListeners.get(eventType).forEach(listener => {
            try {
              listener(data);
            } catch (error) {
              console.error(`메시지 리스너 실행 중 오류:`, error);
            }
          });
        }
      } catch (error) {
        console.error('WebSocket 메시지 처리 중 오류:', error);
      }
    };

    ws.onclose = (event) => {
      console.log(`WebSocket 연결 종료: 코드=${event.code}, 이유=${event.reason}`);
      currentStatus = WS_STATUS.CLOSED;
      notifyStatusChange();
      
      // 자동 재연결 시도
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        scheduleReconnect();
      } else {
        console.error('최대 재연결 시도 횟수 초과');
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket 오류:', error);
    };
  } catch (error) {
    console.error('WebSocket 연결 시도 중 오류:', error);
    currentStatus = WS_STATUS.CLOSED;
    notifyStatusChange();
    scheduleReconnect();
  }
};

/**
 * WebSocket 연결 종료 함수
 */
export const disconnectWebSocket = () => {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }

  if (ws && ws.readyState === WS_STATUS.OPEN) {
    console.log('WebSocket 연결 종료 중...');
    currentStatus = WS_STATUS.CLOSING;
    notifyStatusChange();
    ws.close();
  }
};

/**
 * WebSocket 메시지 리스너 추가
 * @param {string} eventType - 이벤트 타입
 * @param {function} callback - 콜백 함수
 */
export const addWebSocketListener = (eventType, callback) => {
  if (!messageListeners.has(eventType)) {
    messageListeners.set(eventType, new Set());
  }
  messageListeners.get(eventType).add(callback);
  
  console.log(`${eventType} 이벤트에 리스너 추가됨`);
  return () => removeWebSocketListener(eventType, callback);
};

/**
 * WebSocket 메시지 리스너 제거
 * @param {string} eventType - 이벤트 타입
 * @param {function} callback - 콜백 함수
 */
export const removeWebSocketListener = (eventType, callback) => {
  if (messageListeners.has(eventType)) {
    messageListeners.get(eventType).delete(callback);
    console.log(`${eventType} 이벤트에서 리스너 제거됨`);
  }
};

/**
 * WebSocket 상태 변경 알림
 */
const notifyStatusChange = () => {
  statusListeners.forEach(listener => {
    try {
      listener(currentStatus);
    } catch (error) {
      console.error('상태 리스너 실행 중 오류:', error);
    }
  });
};

/**
 * 재연결 스케줄링
 */
const scheduleReconnect = () => {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
  }

  reconnectAttempts++;
  const delay = BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);
  console.log(`${delay}ms 후 WebSocket 재연결 시도 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
  
  reconnectTimeout = setTimeout(() => {
    connectWebSocket();
  }, delay);
};

/**
 * WebSocket 상태 가져오기
 * @returns {number} 현재 WebSocket 상태
 */
export const getWebSocketStatus = () => {
  return currentStatus;
};

/**
 * WebSocket 메시지 전송
 * @param {object} data - 전송할 데이터
 * @returns {boolean} 전송 성공 여부
 */
export const sendWebSocketMessage = (data) => {
  if (ws && ws.readyState === WS_STATUS.OPEN) {
    try {
      ws.send(JSON.stringify(data));
      return true;
    } catch (error) {
      console.error('WebSocket 메시지 전송 중 오류:', error);
      return false;
    }
  }
  console.warn('WebSocket이 연결되지 않아 메시지를 전송할 수 없습니다');
  return false;
};

/**
 * React 컴포넌트에서 WebSocket 사용을 위한 훅
 * @param {string[]} eventTypes - 구독할 이벤트 타입 배열
 * @returns {object} WebSocket 관련 상태 및 함수
 */
export const useWebSocket = (eventTypes = []) => {
  const [status, setStatus] = useState(currentStatus);
  const [messages, setMessages] = useState({});

  // 상태 변경 리스너
  useEffect(() => {
    const statusListener = (newStatus) => {
      setStatus(newStatus);
    };
    
    statusListeners.add(statusListener);
    return () => {
      statusListeners.delete(statusListener);
    };
  }, []);

  // 메시지 리스너
  useEffect(() => {
    const listeners = {};
    
    eventTypes.forEach(eventType => {
      const listener = (data) => {
        setMessages(prev => ({
          ...prev,
          [eventType]: data
        }));
      };
      
      listeners[eventType] = listener;
      addWebSocketListener(eventType, listener);
    });
    
    return () => {
      Object.entries(listeners).forEach(([eventType, listener]) => {
        removeWebSocketListener(eventType, listener);
      });
    };
  }, [eventTypes]);

  // 연결 관리
  const connect = useCallback(() => {
    connectWebSocket();
  }, []);
  
  const disconnect = useCallback(() => {
    disconnectWebSocket();
  }, []);
  
  const send = useCallback((data) => {
    return sendWebSocketMessage(data);
  }, []);

  // 컴포넌트 마운트 시 자동 연결
  useEffect(() => {
    connect();
    return () => {
      // 컴포넌트가 언마운트될 때 리스너만 제거하고 연결은 유지
      // 다른 컴포넌트에서도 WebSocket을 사용할 수 있도록
    };
  }, [connect]);

  return {
    status,
    messages,
    connect,
    disconnect,
    send,
    isConnected: status === WS_STATUS.OPEN
  };
}; 