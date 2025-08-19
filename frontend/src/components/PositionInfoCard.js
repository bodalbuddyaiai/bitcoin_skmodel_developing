import React from 'react';
import { Card, Badge } from 'react-bootstrap';

const PositionInfoCard = ({ currentPosition, currentPrice }) => {
  if (!currentPosition) {
    return (
      <Card className="mb-3">
        <Card.Header>현재 포지션</Card.Header>
        <Card.Body>
          <div className="text-center">
            <Badge bg="secondary" className="p-2">포지션 없음</Badge>
          </div>
        </Card.Body>
      </Card>
    );
  }

  // 포지션 정보 계산
  const size = parseFloat(currentPosition.size);
  const entryPrice = parseFloat(currentPosition.entry_price);
  const unrealizedPnl = parseFloat(currentPosition.unrealized_pnl);
  const side = currentPosition.side.toLowerCase();
  
  // 수익률 계산
  let profitPercentage = 0;
  if (entryPrice > 0 && currentPrice > 0) {
    if (side === 'long') {
      profitPercentage = ((currentPrice - entryPrice) / entryPrice) * 100;
    } else if (side === 'short') {
      profitPercentage = ((entryPrice - currentPrice) / entryPrice) * 100;
    }
  }

  // 배지 색상 결정
  const getBadgeColor = () => {
    if (side === 'long') return 'danger';
    if (side === 'short') return 'primary';
    return 'secondary';
  };

  // PNL 배지 색상
  const getPnlBadgeColor = () => {
    if (unrealizedPnl > 0) return 'success';
    if (unrealizedPnl < 0) return 'danger';
    return 'secondary';
  };

  return (
    <Card className="mb-3">
      <Card.Header>현재 포지션</Card.Header>
      <Card.Body>
        <div className="d-flex justify-content-between align-items-center mb-3">
          <Badge bg={getBadgeColor()} className="p-2">
            {side === 'long' ? '롱 포지션' : '숏 포지션'}
          </Badge>
          <Badge bg={getPnlBadgeColor()} className="p-2">
            {unrealizedPnl > 0 ? '+' : ''}{unrealizedPnl.toFixed(2)} USDT ({profitPercentage.toFixed(2)}%)
          </Badge>
        </div>
        
        <div className="mb-2">
          <strong>크기:</strong> {size.toFixed(4)} BTC
        </div>
        <div className="mb-2">
          <strong>진입가:</strong> ${entryPrice.toFixed(2)}
        </div>
        <div className="mb-2">
          <strong>현재가:</strong> ${currentPrice.toFixed(2)}
        </div>
        <div className="mb-2">
          <strong>미실현 손익:</strong> ${unrealizedPnl.toFixed(2)}
        </div>
      </Card.Body>
    </Card>
  );
};

export default PositionInfoCard; 