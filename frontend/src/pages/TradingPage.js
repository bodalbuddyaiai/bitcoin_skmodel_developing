import React, { useState } from 'react';
import { Row, Col, message } from 'antd';
import TradingControls from '../components/TradingControls';
import TradingStatus from '../components/TradingStatus';
import MarketDataDisplay from '../components/MarketDataDisplay';
import TradingSettings from '../components/TradingSettings';
import { startTrading, stopTrading } from '../services/api';

const TradingPage = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [marketData, setMarketData] = useState(null);

  const handleStartTrading = async () => {
    try {
      setIsLoading(true);
      const response = await startTrading();
      
      if (response.success) {
        message.success('트레이딩이 시작되었습니다.');
        if (response.market_data) {
          setMarketData(response.market_data);
        }
      } else {
        message.error(response.message || '트레이딩 시작 실패');
      }
    } catch (error) {
      console.error('트레이딩 시작 중 오류:', error);
      message.error('트레이딩 시작 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopTrading = async () => {
    try {
      setIsLoading(true);
      const response = await stopTrading();
      
      if (response.success) {
        message.success('트레이딩이 중지되었습니다.');
      } else {
        message.error(response.message || '트레이딩 중지 실패');
      }
    } catch (error) {
      console.error('트레이딩 중지 중 오류:', error);
      message.error('트레이딩 중지 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="trading-page">
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={24}>
          <TradingStatus />
        </Col>
        
        <Col xs={24} lg={24}>
          <TradingControls 
            onStartTrading={handleStartTrading} 
            onStopTrading={handleStopTrading}
            isLoading={isLoading}
          />
        </Col>
        
        <Col xs={24} lg={24}>
          <MarketDataDisplay marketData={marketData} />
        </Col>
        
        <Col xs={24} lg={24}>
          <TradingSettings />
        </Col>
      </Row>
    </div>
  );
};

export default TradingPage; 