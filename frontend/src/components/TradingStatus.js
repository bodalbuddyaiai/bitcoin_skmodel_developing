import React, { useState, useEffect } from 'react';
import { Card, Badge, Row, Col } from 'react-bootstrap';
import { fetchTradingStatus } from '../services/api';
import { formatDateTime } from '../utils/dateUtils';

const TradingStatus = () => {
  const [tradingStatus, setTradingStatus] = useState({});
  const [currentPosition, setCurrentPosition] = useState(null);
  const [liquidationDetected, setLiquidationDetected] = useState(false);
  const [liquidationReason, setLiquidationReason] = useState(null);
  const [currentPrice, setCurrentPrice] = useState(0);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetchTradingStatus();
        console.log('TradingStatus 컴포넌트 응답:', response);
        
        if (response) {
          setTradingStatus(response);
          
          // 포지션 정보 처리 개선
          if (response.current_position && parseFloat(response.current_position.size) > 0) {
            console.log('TradingStatus: 유효한 포지션 감지:', response.current_position);
            setCurrentPosition(response.current_position);
          } else {
            console.log('TradingStatus: 포지션 없음 또는 크기가 0');
            setCurrentPosition(null);
          }
          
          // 청산 감지 정보 설정
          setLiquidationDetected(response.liquidation_detected || false);
          setLiquidationReason(response.liquidation_reason || null);
          
          // 현재 가격 설정
          if (response.current_price) {
            setCurrentPrice(response.current_price);
          }
        }
      } catch (error) {
        console.error('Error fetching trading status:', error);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000); // 5초마다 상태 업데이트

    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = () => {
    if (tradingStatus.status === 'running') {
      return <Badge bg="success">실행 중</Badge>;
    } else {
      return <Badge bg="secondary">대기 중</Badge>;
    }
  };

  const getPositionBadge = () => {
    if (!currentPosition) {
      return <Badge bg="info">포지션 없음</Badge>;
    }
    
    const side = currentPosition.side;
    if (side === 'long') {
      return <Badge bg="danger">롱 포지션</Badge>;
    } else if (side === 'short') {
      return <Badge bg="primary">숏 포지션</Badge>;
    } else {
      return <Badge bg="info">포지션 없음</Badge>;
    }
  };

  const getLiquidationBadge = () => {
    if (liquidationDetected) {
      return <Badge bg="warning">청산 감지: {liquidationReason}</Badge>;
    }
    return null;
  };

  return (
    <Card className="mb-4">
      <Card.Header>트레이딩 상태</Card.Header>
      <Card.Body>
        <Row>
          <Col>
            <div className="mb-2">
              <strong>상태:</strong> {getStatusBadge()}
            </div>
            <div className="mb-2">
              <strong>포지션:</strong> {getPositionBadge()}
            </div>
            {getLiquidationBadge() && (
              <div className="mb-2">
                {getLiquidationBadge()}
              </div>
            )}
          </Col>
          <Col>
            {currentPosition && (
              <>
                <div className="mb-2">
                  <strong>크기:</strong> {parseFloat(currentPosition.size).toFixed(4)} BTC
                </div>
                <div className="mb-2">
                  <strong>진입가:</strong> ${parseFloat(currentPosition.entry_price).toFixed(2)}
                </div>
                <div className="mb-2">
                  <strong>현재 PNL:</strong> ${parseFloat(currentPosition.unrealized_pnl).toFixed(2)}
                </div>
              </>
            )}
            {currentPrice > 0 && (
              <div className="mb-2">
                <strong>현재 가격:</strong> ${parseFloat(currentPrice).toFixed(2)}
              </div>
            )}
          </Col>
        </Row>
      </Card.Body>
    </Card>
  );
};

export default TradingStatus; 