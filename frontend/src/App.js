import React, { useEffect, useState } from 'react';
import { Container, CircularProgress } from '@mui/material';
import MarketDataDisplay from './components/MarketDataDisplay';
import TradingControls from './components/TradingControls';
import AIModelSelector from './components/AIModelSelector';
import AnalysisOnlySection from './components/AnalysisOnlySection';
import TradingSettings from './components/TradingSettings';
import { fetchTradingStatus } from './services/api';
import { connectWebSocket, useWebSocket, WS_EVENT_TYPES } from './services/websocket';

function App() {
  const [marketData, setMarketData] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // WebSocket 연결 및 이벤트 구독
  const { status, messages, isConnected } = useWebSocket([
    WS_EVENT_TYPES.MARKET_UPDATE,
    WS_EVENT_TYPES.POSITION_UPDATE,
    WS_EVENT_TYPES.LIQUIDATION_DETECTED,
    WS_EVENT_TYPES.ANALYSIS_RESULT,
    WS_EVENT_TYPES.TRADING_STATUS,
    WS_EVENT_TYPES.SCHEDULED_JOBS,
    WS_EVENT_TYPES.ANALYSIS_ONLY_RESULT
  ]);

  // WebSocket 메시지 처리
  useEffect(() => {
    if (messages && messages.length > 0) {
      const latestMessage = messages[messages.length - 1];
      console.log('Received WebSocket message:', latestMessage);

      if (latestMessage.event_type === WS_EVENT_TYPES.ANALYSIS_RESULT) {
        console.log('분석 결과 메시지 수신:', latestMessage);
        setMarketData(prevData => ({
          ...prevData,
          last_analysis_result: {
            success: true,
            action: latestMessage.data.action,
            position_size: latestMessage.data.position_size,
            leverage: latestMessage.data.leverage,
            expected_minutes: latestMessage.data.expected_minutes,
            reason: latestMessage.data.reason,
            next_analysis: latestMessage.data.next_analysis_time
          }
        }));
      }
      
      if (latestMessage.event_type === WS_EVENT_TYPES.MARKET_UPDATE) {
        console.log('실시간 시장 데이터 업데이트:', latestMessage);
        setMarketData(prevData => ({
          ...prevData,
          current_market: latestMessage.data
        }));
      }
      
      if (latestMessage.event_type === WS_EVENT_TYPES.POSITION_UPDATE) {
        console.log('실시간 포지션 업데이트:', latestMessage);
        setMarketData(prevData => ({
          ...prevData,
          current_position: latestMessage.data
        }));
      }
      
      if (latestMessage.event_type === WS_EVENT_TYPES.LIQUIDATION_DETECTED) {
        console.log('청산 감지 알림:', latestMessage);
        setMarketData(prevData => ({
          ...prevData,
          liquidation_detected: true,
          liquidation_reason: latestMessage.data.reason,
          liquidation_price: latestMessage.data.price,
          next_analysis: latestMessage.data.next_analysis
        }));
      }
      
      if (latestMessage.event_type === WS_EVENT_TYPES.TRADING_STATUS) {
        console.log('트레이딩 상태 업데이트:', latestMessage);
        setMarketData(prevData => ({
          ...prevData,
          ...latestMessage.data
        }));
      }
      
      if (latestMessage.event_type === WS_EVENT_TYPES.SCHEDULED_JOBS) {
        console.log('예약된 작업 업데이트:', latestMessage);
        setMarketData(prevData => ({
          ...prevData,
          scheduled_jobs: latestMessage.data
        }));
      }
    }
  }, [messages]);

  // 초기 데이터 로드
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const status = await fetchTradingStatus();
        console.log('Received market data:', status);
        
        // 마지막 분석 결과가 있으면 result 필드에도 설정
        if (status.last_analysis_result) {
          console.log('초기 로드 시 마지막 분석 결과 발견:', status.last_analysis_result);
          status.result = status.last_analysis_result;
        }
        
        setMarketData(status);
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    
    // WebSocket 연결 상태 로깅
    console.log('WebSocket 연결 상태:', status);
  }, [status]);

  console.log('Current marketData:', marketData);
  console.log('Loading state:', loading);
  console.log('WebSocket connected:', isConnected);

  if (loading && !marketData) {
    return (
      <Container sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Container>
    );
  }

  return (
    <Container maxWidth="lg">
      <MarketDataDisplay data={marketData} />
      <AIModelSelector />
      <AnalysisOnlySection />
      <TradingControls />
      <TradingSettings />
    </Container>
  );
}

export default App; 