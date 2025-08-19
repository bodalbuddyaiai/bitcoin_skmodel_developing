import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Paper, 
  Typography, 
  Button, 
  CircularProgress,
  Alert,
  Chip,
  Grid,
  Card,
  CardContent,
  Divider
} from '@mui/material';
import { 
  Psychology as PsychologyIcon,
  TrendingUp,
  TrendingDown,
  ShowChart,
  AccessTime,
  Analytics
} from '@mui/icons-material';
import { analyzeOnly } from '../services/api';
import { useWebSocket, WS_EVENT_TYPES } from '../services/websocket';

function AnalysisOnlySection() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [error, setError] = useState(null);
  
  // WebSocket 연결 및 이벤트 구독
  const { messages } = useWebSocket(['ANALYSIS_ONLY_RESULT']);
  
  // WebSocket 메시지 처리
  useEffect(() => {
    if (messages && messages.length > 0) {
      const latestMessage = messages[messages.length - 1];
      
      if (latestMessage.event_type === 'ANALYSIS_ONLY_RESULT') {
        console.log('분석 전용 결과 수신:', latestMessage);
        setAnalysisResult(latestMessage.data);
        setIsAnalyzing(false);
      }
    }
  }, [messages]);

  const handleAnalyzeOnly = async () => {
    try {
      setIsAnalyzing(true);
      setError(null);
      
      const response = await analyzeOnly();
      
      if (response.success) {
        setAnalysisResult(response);
      } else {
        setError(response.message || 'AI 분석 실패');
      }
    } catch (err) {
      console.error('분석 중 오류:', err);
      setError(err.message || 'AI 분석 중 오류가 발생했습니다.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const getActionColor = (action) => {
    switch(action) {
      case 'LONG':
      case 'ENTER_LONG':
        return 'success';
      case 'SHORT':
      case 'ENTER_SHORT':
        return 'error';
      case 'CLOSE_POSITION':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getActionIcon = (action) => {
    switch(action) {
      case 'LONG':
      case 'ENTER_LONG':
        return <TrendingUp />;
      case 'SHORT':
      case 'ENTER_SHORT':
        return <TrendingDown />;
      case 'CLOSE_POSITION':
        return <ShowChart />;
      default:
        return <Analytics />;
    }
  };

  const formatPercentage = (value) => {
    if (!value) return '0%';
    return `${(value * 100).toFixed(1)}%`;
  };

  return (
    <Paper elevation={3} sx={{ p: 3, mt: 3 }}>
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={3}>
        <Box display="flex" alignItems="center">
          <PsychologyIcon sx={{ mr: 1, fontSize: 28 }} color="primary" />
          <Typography variant="h5" component="h2" fontWeight="bold">
            AI 분석 전용 모드
          </Typography>
        </Box>
        
        <Button
          variant="contained"
          color="secondary"
          onClick={handleAnalyzeOnly}
          disabled={isAnalyzing}
          startIcon={isAnalyzing ? <CircularProgress size={20} /> : <PsychologyIcon />}
          sx={{ 
            minWidth: 180,
            background: 'linear-gradient(45deg, #9C27B0 30%, #BA68C8 90%)',
            '&:hover': {
              background: 'linear-gradient(45deg, #7B1FA2 30%, #9C27B0 90%)',
            }
          }}
        >
          {isAnalyzing ? '분석 중...' : '분석만 실행'}
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {analysisResult && (
        <Box>
          <Grid container spacing={3}>
            {/* AI 모델 정보 */}
            <Grid item xs={12} md={4}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                    AI 모델
                  </Typography>
                  <Typography variant="h6" fontWeight="bold">
                    {analysisResult.model ? analysisResult.model.toUpperCase() : 'Unknown'}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            {/* 거래 방향 */}
            <Grid item xs={12} md={4}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                    추천 거래 방향
                  </Typography>
                  <Box display="flex" alignItems="center">
                    {getActionIcon(analysisResult.analysis?.action)}
                    <Chip 
                      label={analysisResult.analysis?.action || 'N/A'}
                      color={getActionColor(analysisResult.analysis?.action)}
                      sx={{ ml: 1, fontWeight: 'bold' }}
                    />
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* 예상 시간 */}
            <Grid item xs={12} md={4}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                    예상 포지션 유지 시간
                  </Typography>
                  <Box display="flex" alignItems="center">
                    <AccessTime sx={{ mr: 1 }} />
                    <Typography variant="h6" fontWeight="bold">
                      {analysisResult.analysis?.expected_minutes || 30}분
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* 포지션 상세 정보 */}
            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                    포지션 설정
                  </Typography>
                  <Divider sx={{ my: 1 }} />
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        포지션 크기
                      </Typography>
                      <Typography variant="body1" fontWeight="medium">
                        {formatPercentage(analysisResult.analysis?.position_size || 1.0)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        레버리지
                      </Typography>
                      <Typography variant="body1" fontWeight="medium">
                        {analysisResult.analysis?.leverage || 2}x
                      </Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            {/* 시장 데이터 */}
            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                    시장 상태
                  </Typography>
                  <Divider sx={{ my: 1 }} />
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        현재 가격
                      </Typography>
                      <Typography variant="body1" fontWeight="medium">
                        ${analysisResult.market_data?.current_price?.toLocaleString() || 'N/A'}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        RSI
                      </Typography>
                      <Typography variant="body1" fontWeight="medium">
                        {analysisResult.market_data?.rsi?.toFixed(2) || 'N/A'}
                      </Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            {/* 분석 이유 */}
            <Grid item xs={12}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                    AI 분석 이유
                  </Typography>
                  <Divider sx={{ my: 1 }} />
                  <Typography 
                    variant="body2" 
                    sx={{ 
                      whiteSpace: 'pre-wrap',
                      backgroundColor: '#f5f5f5',
                      p: 2,
                      borderRadius: 1,
                      fontFamily: 'monospace',
                      fontSize: '0.9rem',
                      lineHeight: 1.6
                    }}
                  >
                    {analysisResult.analysis?.reason || '분석 이유가 제공되지 않았습니다.'}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            {/* 현재 포지션 정보 (있는 경우) */}
            {analysisResult.current_position && (
              <Grid item xs={12}>
                <Card elevation={2} sx={{ backgroundColor: '#fff3e0' }}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                      현재 보유 포지션
                    </Typography>
                    <Divider sx={{ my: 1 }} />
                    <Grid container spacing={2}>
                      <Grid item xs={6} md={3}>
                        <Typography variant="body2" color="textSecondary">
                          방향
                        </Typography>
                        <Typography variant="body1" fontWeight="medium">
                          {analysisResult.current_position.side || 'N/A'}
                        </Typography>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Typography variant="body2" color="textSecondary">
                          크기
                        </Typography>
                        <Typography variant="body1" fontWeight="medium">
                          {analysisResult.current_position.total || 'N/A'}
                        </Typography>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Typography variant="body2" color="textSecondary">
                          진입가
                        </Typography>
                        <Typography variant="body1" fontWeight="medium">
                          ${analysisResult.current_position.averageOpenPrice || 'N/A'}
                        </Typography>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Typography variant="body2" color="textSecondary">
                          미실현 PnL
                        </Typography>
                        <Typography 
                          variant="body1" 
                          fontWeight="medium"
                          color={analysisResult.current_position.unrealizedPL > 0 ? 'success.main' : 'error.main'}
                        >
                          ${analysisResult.current_position.unrealizedPL || 'N/A'}
                        </Typography>
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              </Grid>
            )}
          </Grid>

          {/* 분석 시간 */}
          <Box mt={2} textAlign="right">
            <Typography variant="caption" color="textSecondary">
              분석 시간: {analysisResult.timestamp ? new Date(analysisResult.timestamp).toLocaleString('ko-KR') : ''}
            </Typography>
          </Box>
        </Box>
      )}

      {!analysisResult && !error && !isAnalyzing && (
        <Box textAlign="center" py={4}>
          <Typography variant="body1" color="textSecondary">
            버튼을 클릭하여 AI 분석을 시작하세요.
          </Typography>
          <Typography variant="caption" color="textSecondary">
            실제 거래는 실행되지 않고 분석 결과만 확인할 수 있습니다.
          </Typography>
        </Box>
      )}
    </Paper>
  );
}

export default AnalysisOnlySection;