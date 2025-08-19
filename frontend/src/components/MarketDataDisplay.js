import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { 
  Card, CardContent, Typography, Grid, Button, 
  Table, TableBody, TableCell, TableContainer, 
  TableHead, TableRow, Paper, CircularProgress, Alert, AlertTitle,
  Accordion, AccordionSummary, AccordionDetails
} from '@mui/material';
import { 
  getTradingData, 
  fetchTradingStatus, 
  startTrading, 
  stopTrading,
  getScheduledJobs,
  cancelScheduledJobs
} from '../services/api';
import { formatDateTime } from '../utils/dateUtils';
import TradingStatus from './TradingStatus';
import PositionInfoCard from './PositionInfoCard';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

// 시장 데이터 카드 컴포넌트 분리
const MarketDataCard = React.memo(({ data }) => {
  if (!data || !data.current_market) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6">No market data available</Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h5" gutterBottom>Current Market</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1">
              Price: ${parseFloat(data.current_market?.price).toLocaleString()}
            </Typography>
          </Grid>
          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1">
              24h High: ${parseFloat(data.current_market?.['24h_high']).toLocaleString()}
            </Typography>
          </Grid>
          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1">
              24h Low: ${parseFloat(data.current_market?.['24h_low']).toLocaleString()}
            </Typography>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
});

// 계정 정보 카드 컴포넌트 분리
const AccountInfoCard = React.memo(({ data }) => {
  if (!data || !data.account) {
    return null;
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h5" gutterBottom>Account Information</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1">
              Available: {parseFloat(data.account?.available).toLocaleString()} USDT
            </Typography>
          </Grid>
          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1">
              Equity: {parseFloat(data.account?.equity).toLocaleString()} USDT
            </Typography>
          </Grid>
          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1">
              Unrealized PL: {parseFloat(data.account?.unrealizedPL).toLocaleString()} USDT
            </Typography>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
});

// 예약된 작업 카드 컴포넌트 분리
const ScheduledJobsCard = React.memo(({ scheduledJobs, loading, handleCancelJobs }) => {
  return (
    <Card>
      <CardContent>
        <Typography variant="h5" gutterBottom>Scheduled Analysis</Typography>
        {scheduledJobs && Object.keys(scheduledJobs).length > 0 ? (
          <>
            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Job ID</TableCell>
                    <TableCell>Scheduled Time</TableCell>
                    <TableCell>Previous Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(scheduledJobs).map(([jobId, jobInfo]) => (
                    <TableRow key={jobId}>
                      <TableCell>{jobId.substring(0, 8)}...</TableCell>
                      <TableCell>
                        {new Date(jobInfo.scheduled_time).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        {jobInfo.analysis_result?.action || 'N/A'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Button 
              variant="contained" 
              color="warning" 
              onClick={handleCancelJobs}
              disabled={loading}
              sx={{ mt: 2 }}
            >
              Cancel All Scheduled Jobs
            </Button>
          </>
        ) : (
          <Typography>No scheduled jobs</Typography>
        )}
      </CardContent>
    </Card>
  );
});

function MarketDataDisplay({ data = {} }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [scheduledJobs, setScheduledJobs] = useState({});
  const [tradingStatus, setTradingStatus] = useState({ is_running: false });
  const [currentPosition, setCurrentPosition] = useState(null);
  const [lastPositionSide, setLastPositionSide] = useState(null);
  const [nextAnalysisTime, setNextAnalysisTime] = useState(null);
  const [liquidationDetected, setLiquidationDetected] = useState(false);
  const [liquidationReason, setLiquidationReason] = useState(null);
  const [liquidationPrice, setLiquidationPrice] = useState(0);
  const [nextAnalysisAfterLiquidation, setNextAnalysisAfterLiquidation] = useState(null);
  const [currentPrice, setCurrentPrice] = useState(0);
  const [isTrading, setIsTrading] = useState(false);

  // 거래 상태 조회
  const updateTradingStatus = async () => {
    try {
      const response = await fetchTradingStatus();
      console.log('Trading status response:', response);
      
      if (response) {
        // 트레이딩 상태 설정
        setTradingStatus(response);
        
        // 포지션 정보 처리 개선
        if (response.current_position && parseFloat(response.current_position.size) > 0) {
          console.log('유효한 포지션 감지:', response.current_position);
          setCurrentPosition(response.current_position);
        } else {
          console.log('포지션 없음 또는 크기가 0');
          setCurrentPosition(null);
        }
        
        setLastPositionSide(response.last_position_side || null);
        
        // 다음 분석 시간 설정 (새로운 형식 지원)
        if (response.next_analysis) {
          // 문자열 형식이면 그대로 사용
          if (typeof response.next_analysis === 'string') {
            setNextAnalysisTime(response.next_analysis);
          } 
          // 객체 형식이면 scheduled_time 필드 사용
          else if (response.next_analysis.scheduled_time) {
            setNextAnalysisTime(response.next_analysis.scheduled_time);
          }
        } else {
          setNextAnalysisTime(null);
        }
        
        // 청산 감지 정보 설정
        const wasLiquidated = response.liquidation_detected || false;
        setLiquidationDetected(wasLiquidated);
        setLiquidationReason(response.liquidation_reason || null);
        setLiquidationPrice(response.liquidation_price || 0);
        
        // 청산 후 다음 분석 시간 설정
        if (wasLiquidated && response.next_analysis) {
          setNextAnalysisAfterLiquidation(response.next_analysis);
          console.log('청산 후 다음 분석 시간:', response.next_analysis);
        }
        
        // 현재 가격 설정
        if (response.current_price) {
          setCurrentPrice(response.current_price);
        }
        
        // 마지막 분석 결과 설정
        if (response.last_analysis_result) {
          console.log('마지막 분석 결과 수신:', response.last_analysis_result);
          
          const analysisResult = response.last_analysis_result;
          setResult({
            success: true,
            analysis: analysisResult.reason,
            action: analysisResult.action,
            position_size: analysisResult.position_size,
            leverage: analysisResult.leverage,
            expected_minutes: analysisResult.expected_minutes,
            reason: analysisResult.reason,
            next_analysis_time: analysisResult.next_analysis_time
          });
          
          console.log('분석 결과 상태 업데이트됨:', {
            success: true,
            analysis: analysisResult.reason,
            action: analysisResult.action,
            position_size: analysisResult.position_size,
            leverage: analysisResult.leverage,
            expected_minutes: analysisResult.expected_minutes,
            reason: analysisResult.reason,
            next_analysis_time: analysisResult.next_analysis_time
          });
          
          // 트레이딩 상태 설정 (청산 감지 시에도 running 상태 유지)
          const is_running = response.status === 'running' || wasLiquidated;
          setIsTrading(is_running);
          
          // 청산 감지 시 로그 추가
          if (wasLiquidated) {
            console.log('청산 감지됨! 자동 재시작 예정:', response.next_analysis);
            console.log('청산 이유:', response.liquidation_reason);
            console.log('다음 분석 시간:', response.next_analysis);
            console.log('다음 분석 작업 ID:', response.next_analysis_job_id);
          }
        }
      }
    } catch (error) {
      console.error('Error fetching trading status:', error);
    }
  };

  // 자동 트레이딩 시작 - useCallback으로 최적화
  const handleStartTrading = useCallback(async () => {
    try {
      setLoading(true);
      const response = await startTrading();
      setResult(response);
      console.log('Trading started:', response);
      
      // 즉시 상태 업데이트 후 짧은 간격으로 재확인
      updateTradingStatus();
      setTimeout(updateTradingStatus, 2000); // 2초 후 다시 확인
      setTimeout(updateTradingStatus, 5000); // 5초 후 다시 확인
    } catch (error) {
      console.error('Error starting trading:', error);
      setResult({ error: error.message });
    } finally {
      setLoading(false);
    }
  }, []);

  // 자동 트레이딩 중지 - useCallback으로 최적화
  const handleStopTrading = useCallback(async () => {
    try {
      setLoading(true);
      const response = await stopTrading();
      setResult(response);
      console.log('Trading stopped:', response);
      
      // 즉시 상태 업데이트 후 짧은 간격으로 재확인
      updateTradingStatus();
      setTimeout(updateTradingStatus, 2000); // 2초 후 다시 확인
      setTimeout(updateTradingStatus, 5000); // 5초 후 다시 확인
    } catch (error) {
      console.error('Error stopping trading:', error);
      setResult({ error: error.message });
    } finally {
      setLoading(false);
    }
  }, []);

  // 예약된 작업 조회
  const fetchScheduledJobs = async () => {
    try {
      const response = await getScheduledJobs();
      if (response.success) {
        setScheduledJobs(response.jobs);
        
        // 예약된 작업이 있으면 가장 빠른 시간을 다음 분석 시간으로 설정
        if (Object.keys(response.jobs).length > 0) {
          // 모든 작업의 예약 시간을 날짜 객체로 변환하여 정렬
          const scheduledTimes = Object.values(response.jobs)
            .map(job => new Date(job.scheduled_time))
            .sort((a, b) => a - b);
          
          // 가장 빠른 시간을 다음 분석 시간으로 설정
          if (scheduledTimes.length > 0) {
            const nextTime = scheduledTimes[0].toISOString();
            console.log('예약된 작업에서 다음 분석 시간 업데이트:', nextTime);
            setNextAnalysisTime(nextTime);
          }
        }
      }
    } catch (error) {
      console.error('Error fetching scheduled jobs:', error);
    }
  };
  
  // 예약된 작업 취소 - useCallback으로 최적화
  const handleCancelJobs = useCallback(async () => {
    try {
      setLoading(true);
      const response = await cancelScheduledJobs();
      setResult(response);
      console.log('Jobs cancelled:', response);
      fetchScheduledJobs();  // 작업 목록 갱신
    } catch (error) {
      console.error('Error cancelling jobs:', error);
      setResult({ error: error.message });
    } finally {
      setLoading(false);
    }
  }, []);

  // 컴포넌트 마운트 시 예약된 작업 조회 및 거래 상태 조회
  useEffect(() => {
    // 초기 데이터 로드
    fetchScheduledJobs();
    updateTradingStatus();
    
    // 10초마다 예약된 작업 목록 및 거래 상태 갱신
    const interval = setInterval(() => {
      fetchScheduledJobs().catch(err => {
        console.error('Error fetching scheduled jobs:', err);
      });
      
      updateTradingStatus().catch(err => {
        console.error('Error fetching trading status:', err);
      });
    }, 10000); // 10초로 변경
    
    return () => clearInterval(interval);
  }, []);

  // 결과 데이터 표시를 최적화
  const renderResultData = () => {
    // data.last_analysis_result 대신 result 상태 변수 사용
    const analysisResult = result || {};
    console.log('분석 결과 렌더링:', analysisResult);

    const simplifiedResult = {
      action: analysisResult.action || 'PROCESSING',
      reason: analysisResult.reason || 'Trading started, waiting for analysis.',
      position_size: analysisResult.position_size,
      leverage: analysisResult.leverage,
      expected_minutes: analysisResult.expected_minutes,
      next_analysis: analysisResult.next_analysis_time
    };

    return (
      <Paper sx={{ mt: 2, p: 2 }}>
        <Typography variant="subtitle1" fontWeight="bold" color="primary">
          최근 분석 결과:
        </Typography>
        <Grid container spacing={1} sx={{ mt: 1 }}>
          <Grid item xs={12}>
            <Typography variant="body1" fontWeight="bold">
              거래 방향: {simplifiedResult.action}
            </Typography>
          </Grid>
          <Grid item xs={12}>
            <Accordion>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="body2" fontWeight="bold">분석 이유 (클릭하여 펼치기/접기)</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Typography 
                  variant="body2" 
                  sx={{ 
                    whiteSpace: 'pre-wrap', 
                    wordBreak: 'break-word',
                    maxHeight: '300px',
                    overflowY: 'auto',
                    padding: '8px',
                    backgroundColor: '#f5f5f5',
                    borderRadius: '4px'
                  }}
                >
                  {simplifiedResult.reason}
                </Typography>
              </AccordionDetails>
            </Accordion>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2">
              포지션 크기: {simplifiedResult.position_size || '정보 없음'}
            </Typography>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2">
              레버리지: {simplifiedResult.leverage || '정보 없음'}
            </Typography>
          </Grid>
          <Grid item xs={12}>
            <Typography variant="body2">
              예상 시간(분): {simplifiedResult.expected_minutes || '정보 없음'}
            </Typography>
          </Grid>
          <Grid item xs={12}>
            <Typography variant="body2">
              다음 분석: {simplifiedResult.next_analysis ? formatDateTime(simplifiedResult.next_analysis) : '정보 없음'}
            </Typography>
          </Grid>
        </Grid>
      </Paper>
    );
  };

  return (
    <div>
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h5" gutterBottom>Trading Controls</Typography>
              <Button 
                variant="contained" 
                color="success" 
                onClick={handleStartTrading}
                disabled={loading || isTrading}
                sx={{ mr: 2, opacity: isTrading ? 0.5 : 1 }}
              >
                Start Auto Trading
              </Button>
              <Button 
                variant="contained" 
                color="error" 
                onClick={handleStopTrading}
                disabled={loading || !isTrading}
                sx={{ opacity: !isTrading ? 0.5 : 1 }}
              >
                Stop Auto Trading
              </Button>
              
              {loading && <CircularProgress size={24} sx={{ ml: 2 }} />}
              
              {isTrading && currentPosition && (
                <Typography variant="subtitle1" sx={{ mt: 1, color: 'green' }}>
                  트레이딩 상태: 실행 중 (포지션 있음)
                  {nextAnalysisTime && (
                    <span> (다음 분석: {formatDateTime(nextAnalysisTime)})</span>
                  )}
                </Typography>
              )}
              
              {isTrading && !currentPosition && (
                <Typography variant="subtitle1" sx={{ mt: 1, color: 'blue' }}>
                  트레이딩 상태: 대기 중 (포지션 없음)
                  {nextAnalysisTime && (
                    <span> (다음 분석: {formatDateTime(nextAnalysisTime)})</span>
                  )}
                </Typography>
              )}
              
              {liquidationDetected && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                  <AlertTitle>포지션 청산 감지됨</AlertTitle>
                  <p>청산 이유: {liquidationReason || '알 수 없음'}</p>
                  <p>청산 가격: ${liquidationPrice.toLocaleString()}</p>
                  <p>다음 분석 예정: {formatDateTime(nextAnalysisTime)}</p>
                </Alert>
              )}
              
              {renderResultData()}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* 현재 시장 데이터 */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <MarketDataCard data={data} />
        </Grid>
      </Grid>

      {/* 계정 정보 */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <AccountInfoCard data={data} />
        </Grid>
      </Grid>

      {/* 포지션 정보 */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <PositionInfoCard 
            currentPosition={currentPosition} 
            currentPrice={currentPrice} 
          />
        </Grid>
      </Grid>

      {/* 예약된 작업 목록 */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <ScheduledJobsCard 
            scheduledJobs={scheduledJobs} 
            loading={loading} 
            handleCancelJobs={handleCancelJobs} 
          />
        </Grid>
      </Grid>

      {/* 트레이딩 상태 컴포넌트 */}
      <TradingStatus />
    </div>
  );
}

export default React.memo(MarketDataDisplay); 