import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  FormControl,
  FormLabel,
  RadioGroup,
  FormControlLabel,
  Radio,
  Button,
  Alert,
  Box,
  Chip
} from '@mui/material';
import { styled } from '@mui/material/styles';
import axios from 'axios';

// axios 기본 URL 설정
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const StyledCard = styled(Card)(({ theme }) => ({
  marginBottom: theme.spacing(2),
  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  color: 'white',
}));

const StyledCardContent = styled(CardContent)({
  '&:last-child': {
    paddingBottom: 16,
  },
});

const AIModelSelector = () => {
  const [currentModel, setCurrentModel] = useState('gpt');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info');

  // 컴포넌트 마운트 시 현재 모델 조회
  useEffect(() => {
    fetchCurrentModel();
  }, []);

  const fetchCurrentModel = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/ai/model`);
      const data = response.data;
      
      if (data.success) {
        setCurrentModel(data.current_model);
      }
    } catch (error) {
      console.error('현재 AI 모델 조회 실패:', error);
      setMessage('현재 AI 모델 정보를 가져올 수 없습니다.');
      setMessageType('error');
    }
  };

  const handleModelChange = (event) => {
    setCurrentModel(event.target.value);
  };

  const handleApplyModel = async () => {
    setLoading(true);
    setMessage('');

    try {
      const response = await axios.post(`${API_BASE_URL}/api/ai/model`, {
        model: currentModel
      });

      const data = response.data;

      if (data.success) {
        setMessage(data.message);
        setMessageType('success');
      } else {
        setMessage('AI 모델 설정에 실패했습니다.');
        setMessageType('error');
      }
    } catch (error) {
      console.error('AI 모델 설정 실패:', error);
      setMessage('AI 모델 설정 중 오류가 발생했습니다.');
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const getModelDescription = (model) => {
    switch (model) {
      case 'gpt':
        return 'OpenAI GPT-4 모델을 사용하여 시장 분석을 수행합니다.';
      case 'claude':
        return 'Anthropic Claude-4-Sonnet 모델을 사용하여 시장 분석을 수행합니다.';
      case 'claude-opus':
        return 'Anthropic Claude-Opus-4 모델을 사용하여 시장 분석을 수행합니다. (고성능)';
      case 'claude-opus-4.1':
        return 'Anthropic Claude-Opus-4.1 모델을 사용하여 시장 분석을 수행합니다. (최신 최고 성능, 우수한 추론 능력)';
      case 'claude-sonnet-4.5':
        return 'Anthropic Claude-Sonnet-4.5 모델을 사용하여 시장 분석을 수행합니다. (2025년 최신 모델, 향상된 추론 능력)';
      case 'deepseek-chat':
        return 'DeepSeek AI Non-Thinking Mode를 사용하여 시장 분석을 수행합니다. (빠른 분석)';
      case 'deepseek-reasoner':
        return 'DeepSeek AI Thinking Mode를 사용하여 시장 분석을 수행합니다. (심층 추론 분석)';
      default:
        return '';
    }
  };

  const getModelChipColor = (model) => {
    switch (model) {
      case 'gpt':
        return 'primary';
      case 'claude':
        return 'secondary';
      case 'claude-opus':
        return 'warning';
      case 'claude-opus-4.1':
        return 'error';
      case 'claude-sonnet-4.5':
        return 'success';
      case 'deepseek-chat':
        return 'info';
      case 'deepseek-reasoner':
        return 'secondary';
      default:
        return 'default';
    }
  };

  return (
    <StyledCard>
      <StyledCardContent>
        <Typography variant="h6" gutterBottom>
          🤖 AI 모델 선택
        </Typography>
        
        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ opacity: 0.9 }}>
            분석에 사용할 AI 모델을 선택하세요
          </Typography>
          <Chip 
            label={`현재: ${currentModel.toUpperCase()}`}
            color={getModelChipColor(currentModel)}
            size="small"
            sx={{ mt: 1 }}
          />
        </Box>

        <FormControl component="fieldset" sx={{ width: '100%', mb: 2 }}>
          <FormLabel component="legend" sx={{ color: 'white', mb: 1 }}>
            AI 모델
          </FormLabel>
          <RadioGroup
            value={currentModel}
            onChange={handleModelChange}
            sx={{ 
              '& .MuiFormControlLabel-label': { 
                color: 'white',
                fontSize: '0.9rem'
              },
              '& .MuiRadio-root': {
                color: 'white',
                '&.Mui-checked': {
                  color: '#90caf9'
                }
              }
            }}
          >
            <FormControlLabel 
              value="gpt" 
              control={<Radio />} 
              label={
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    GPT-4 (OpenAI)
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    OpenAI의 GPT-4 모델 사용
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel 
              value="claude" 
              control={<Radio />} 
              label={
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    Claude-4-Sonnet (Anthropic)
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    Anthropic의 Claude-4-Sonnet 모델 사용
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel 
              value="claude-opus" 
              control={<Radio />} 
              label={
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    Claude-Opus-4 (Anthropic) ⭐
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    Anthropic의 고성능 Claude-Opus-4 모델 사용
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="claude-opus-4.1"
              control={<Radio />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    Claude-Opus-4.1 (Anthropic) 🏆
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    Anthropic의 최신 최고 성능 모델 - 우수한 추론 능력
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="claude-sonnet-4.5"
              control={<Radio />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    Claude-Sonnet-4.5 (2025) 🚀
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    2025년 최신 Claude-Sonnet-4.5 모델 - 향상된 추론 능력
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="deepseek-chat"
              control={<Radio />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    DeepSeek AI (Non-Thinking Mode) ⚡
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    빠른 분석 모드 - DeepSeek-V3.2-Exp
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="deepseek-reasoner"
              control={<Radio />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    DeepSeek AI (Thinking Mode) 🧠
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    심층 추론 분석 모드 - DeepSeek-V3.2-Exp
                  </Typography>
                </Box>
              }
            />
          </RadioGroup>
        </FormControl>

        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ 
            opacity: 0.9, 
            fontStyle: 'italic',
            backgroundColor: 'rgba(255,255,255,0.1)',
            padding: 1,
            borderRadius: 1
          }}>
            {getModelDescription(currentModel)}
          </Typography>
        </Box>

        {message && (
          <Alert 
            severity={messageType} 
            sx={{ mb: 2, backgroundColor: 'rgba(255,255,255,0.9)' }}
          >
            {message}
          </Alert>
        )}

        <Button
          variant="contained"
          onClick={handleApplyModel}
          disabled={loading}
          fullWidth
          sx={{
            backgroundColor: 'rgba(255,255,255,0.2)',
            color: 'white',
            '&:hover': {
              backgroundColor: 'rgba(255,255,255,0.3)',
            },
            '&:disabled': {
              backgroundColor: 'rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.5)',
            }
          }}
        >
          {loading ? '적용 중...' : 'AI 모델 적용'}
        </Button>
      </StyledCardContent>
    </StyledCard>
  );
};

export default AIModelSelector; 