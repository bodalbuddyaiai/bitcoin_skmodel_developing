import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.response.use(
  response => response,
  error => {
    if (error.code === 'ERR_NETWORK' || error.code === 'ECONNABORTED') {
      console.log('Network error or timeout occurred:', error.message);
      return Promise.resolve({ 
        data: { 
          success: true, 
          is_running: false,
          error: error.message 
        } 
      });
    }
    return Promise.reject(error);
  }
);

export const getTradingData = async () => {
  try {
    const response = await api.get('/api/trading/data');
    return response.data;
  } catch (error) {
    console.error('Error getting trading data:', error);
    return { success: false, error: error.message };
  }
};

// 트레이딩 히스토리 조회
export const getTradingHistory = async (limit = 50) => {
  try {
    const response = await api.get(`/api/trading/history?limit=${limit}`);
    return response.data;
  } catch (error) {
    console.error('Error getting trading history:', error);
    return { success: true, data: [] };
  }
};

// 자동 트레이딩 시작
export const startTrading = async () => {
  try {
    // 자동 트레이딩 시작 요청
    const response = await api.post('/api/trading/start');
    console.log('Start trading response:', response.data);
    
    if (!response.data.success) {
      throw new Error(response.data.message || 'Failed to start trading');
    }

    // 분석 결과가 없어도 성공으로 처리
    if (!response.data.analysis) {
      console.log('No analysis result received, but trading started successfully');
      return {
        ...response.data,
        analysis: { action: "PROCESSING", reason: "Trading started, waiting for analysis" }
      };
    }

    return response.data;
  } catch (error) {
    console.error('Error starting trading:', error);
    throw error;
  }
};

// 트레이딩 상태 조회
export const fetchTradingStatus = async () => {
  try {
    console.log('트레이딩 상태 조회 요청 시작...');
    const response = await fetch(`${API_BASE_URL}/api/trading/status`);
    const data = await response.json();
    console.log('API 응답 (fetchTradingStatus):', JSON.stringify(data, null, 2));
    
    // 청산 감지 로깅
    if (data.liquidation_detected) {
      console.log('청산 감지됨!', {
        reason: data.liquidation_reason,
        price: data.liquidation_price,
        nextAnalysis: data.next_analysis
      });
    }
    
    // 포지션 데이터 유효성 검사 및 처리
    if (data.current_position) {
      // 숫자 필드를 숫자 타입으로 변환
      if (data.current_position.size) {
        data.current_position.size = parseFloat(data.current_position.size);
      }
      if (data.current_position.entry_price) {
        data.current_position.entry_price = parseFloat(data.current_position.entry_price);
      }
      if (data.current_position.unrealized_pnl) {
        data.current_position.unrealized_pnl = parseFloat(data.current_position.unrealized_pnl);
      }
    } else {
      console.log('현재 포지션 없음');
    }
    
    // 현재 가격 처리
    if (data.current_price) {
      data.current_price = parseFloat(data.current_price);
    }
    
    return data;
  } catch (error) {
    console.error('트레이딩 상태 조회 중 에러:', error);
    // 기본 상태 반환 (UI가 깨지지 않도록)
    return {
      status: "error",
      message: "트레이딩 상태 조회 중 에러 발생",
      current_position: null,
      current_price: 0
    };
  }
};

// 자동 트레이딩 중지
export const stopTrading = async () => {
  try {
    const response = await api.post('/api/trading/stop');
    return response.data;
  } catch (error) {
    console.error('Error stopping trading:', error);
    throw error;
  }
};

// 예약된 작업 목록 조회
export const getScheduledJobs = async () => {
  try {
    const response = await api.get('/api/trading/scheduled-jobs');
    return response.data;
  } catch (error) {
    console.error('Error getting scheduled jobs:', error);
    return { success: true, jobs: {} };
  }
};

// 예약된 작업 취소
export const cancelScheduledJobs = async () => {
  try {
    const response = await api.post('/api/trading/cancel-jobs');
    return response.data;
  } catch (error) {
    console.error('Error cancelling scheduled jobs:', error);
    throw error;
  }
};

// AI 분석만 수행 (거래 없음)
export const analyzeOnly = async () => {
  try {
    const response = await api.post('/api/trading/analyze-only');
    console.log('Analyze only response:', response.data);
    return response.data;
  } catch (error) {
    console.error('Error analyzing market:', error);
    throw error;
  }
};

 