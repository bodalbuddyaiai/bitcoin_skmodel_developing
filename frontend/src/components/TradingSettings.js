import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Grid,
  TextField,
  Button,
  CircularProgress,
  Alert,
  Box,
  Checkbox,
  FormControlLabel,
  Radio,
  RadioGroup,
  FormControl,
  FormLabel
} from '@mui/material';
import { getSettings, updateSetting, getEmailSettings, updateEmailSettings, getDiagonalSettings, updateDiagonalSettings } from '../services/api';

function TradingSettings() {
  const [settings, setSettings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [localSettings, setLocalSettings] = useState({});
  
  // 이메일 설정 상태
  const [emailSettings, setEmailSettings] = useState({
    email_address: '',
    send_main_analysis: true,
    send_monitoring_analysis: true
  });
  const [originalEmailSettings, setOriginalEmailSettings] = useState({});
  
  // 빗각 설정 상태
  const [diagonalSettings, setDiagonalSettings] = useState({
    diagonal_type: null,  // 'uptrend' 또는 'downtrend'
    point_a_time: '',
    point_second_time: '',
    point_b_time: ''
  });
  const [originalDiagonalSettings, setOriginalDiagonalSettings] = useState({});

  // 설정 로드
  useEffect(() => {
    loadSettings();
    loadEmailSettings();
    loadDiagonalSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await getSettings();
      
      if (Array.isArray(response)) {
        setSettings(response);
        
        // 로컬 상태 초기화
        const initialSettings = {};
        response.forEach(setting => {
          initialSettings[setting.setting_name] = setting.setting_value;
        });
        setLocalSettings(initialSettings);
      }
    } catch (error) {
      console.error('Error loading settings:', error);
      setMessage({ type: 'error', text: '설정을 불러오는데 실패했습니다.' });
    } finally {
      setLoading(false);
    }
  };
  
  const loadEmailSettings = async () => {
    try {
      const response = await getEmailSettings();
      
      if (response.id) {
        const emailData = {
          email_address: response.email_address || '',
          send_main_analysis: response.send_main_analysis !== false,
          send_monitoring_analysis: response.send_monitoring_analysis !== false
        };
        setEmailSettings(emailData);
        setOriginalEmailSettings(emailData);
      }
    } catch (error) {
      console.error('Error loading email settings:', error);
    }
  };
  
  const loadDiagonalSettings = async () => {
    try {
      const response = await getDiagonalSettings();
      
      if (response.id) {
        const diagonalData = {
          diagonal_type: response.diagonal_type || null,
          point_a_time: response.point_a_time || '',
          point_second_time: response.point_second_time || '',
          point_b_time: response.point_b_time || ''
        };
        setDiagonalSettings(diagonalData);
        setOriginalDiagonalSettings(diagonalData);
      }
    } catch (error) {
      console.error('Error loading diagonal settings:', error);
    }
  };

  const handleChange = (settingName, value) => {
    setLocalSettings(prev => ({
      ...prev,
      [settingName]: parseInt(value) || 0
    }));
  };

  const handleSave = async (settingName) => {
    try {
      setLoading(true);
      const response = await updateSetting(settingName, localSettings[settingName]);
      
      if (response.success) {
        setMessage({ type: 'success', text: '설정이 저장되었습니다.' });
        await loadSettings(); // 설정 새로고침
        
        // 3초 후 메시지 제거
        setTimeout(() => setMessage(null), 3000);
      } else {
        setMessage({ type: 'error', text: response.error || '설정 저장에 실패했습니다.' });
      }
    } catch (error) {
      console.error('Error saving setting:', error);
      setMessage({ type: 'error', text: '설정 저장 중 오류가 발생했습니다.' });
    } finally {
      setLoading(false);
    }
  };
  
  const handleEmailChange = (field, value) => {
    setEmailSettings(prev => ({
      ...prev,
      [field]: value
    }));
  };
  
  const handleEmailSave = async () => {
    try {
      setLoading(true);
      const response = await updateEmailSettings(emailSettings);
      
      if (response.success) {
        setMessage({ type: 'success', text: '이메일 설정이 저장되었습니다.' });
        await loadEmailSettings(); // 이메일 설정 새로고침
        
        // 3초 후 메시지 제거
        setTimeout(() => setMessage(null), 3000);
      } else {
        setMessage({ type: 'error', text: response.error || '이메일 설정 저장에 실패했습니다.' });
      }
    } catch (error) {
      console.error('Error saving email settings:', error);
      setMessage({ type: 'error', text: '이메일 설정 저장 중 오류가 발생했습니다.' });
    } finally {
      setLoading(false);
    }
  };
  
  const isEmailSettingsChanged = () => {
    return emailSettings.email_address !== originalEmailSettings.email_address ||
           emailSettings.send_main_analysis !== originalEmailSettings.send_main_analysis ||
           emailSettings.send_monitoring_analysis !== originalEmailSettings.send_monitoring_analysis;
  };
  
  const handleDiagonalChange = (field, value) => {
    setDiagonalSettings(prev => ({
      ...prev,
      [field]: value
    }));
  };
  
  const handleDiagonalSave = async () => {
    try {
      setLoading(true);
      const response = await updateDiagonalSettings(diagonalSettings);
      
      if (response.success) {
        setMessage({ type: 'success', text: '빗각 설정이 저장되었습니다.' });
        await loadDiagonalSettings();
        setTimeout(() => setMessage(null), 3000);
      } else {
        setMessage({ type: 'error', text: response.error || '빗각 설정 저장에 실패했습니다.' });
      }
    } catch (error) {
      console.error('Error saving diagonal settings:', error);
      setMessage({ type: 'error', text: '빗각 설정 저장 중 오류가 발생했습니다.' });
    } finally {
      setLoading(false);
    }
  };
  
  const isDiagonalSettingsChanged = () => {
    return JSON.stringify(diagonalSettings) !== JSON.stringify(originalDiagonalSettings);
  };

  const getSettingLabel = (settingName) => {
    const labels = {
      'stop_loss_reanalysis_minutes': '손절 후 재분석 시간 (분)',
      'normal_reanalysis_minutes': '일반 청산 후 재분석 시간 (분)',
      'monitoring_interval_minutes': '포지션 모니터링 주기 (분)'
    };
    return labels[settingName] || settingName;
  };

  const getSettingDescription = (settingName) => {
    const descriptions = {
      'stop_loss_reanalysis_minutes': '손절가(Stop Loss ROE)에 도달하여 강제 청산된 경우, 다음 분석까지 기다리는 시간입니다.',
      'normal_reanalysis_minutes': 'HOLD, Take Profit 도달, Expected Minutes 도달, 사용자 수동 청산, AI 모니터링 분석 결과 반대 방향 등의 경우 다음 분석까지 기다리는 시간입니다.',
      'monitoring_interval_minutes': '포지션 진입 후 주기적으로 시장 상황을 모니터링하는 주기입니다.'
    };
    return descriptions[settingName] || '';
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h5" gutterBottom>
          트레이딩 설정
        </Typography>
        
        {message && (
          <Alert severity={message.type} sx={{ mb: 2 }}>
            {message.text}
          </Alert>
        )}

        {loading && settings.length === 0 ? (
          <Box display="flex" justifyContent="center" p={3}>
            <CircularProgress />
          </Box>
        ) : (
          <Grid container spacing={3}>
            {/* 이메일 알림 설정 */}
            <Grid item xs={12}>
              <Card variant="outlined" sx={{ bgcolor: '#f5f5f5' }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ color: '#1976d2' }}>
                    📧 이메일 알림 설정
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    AI 분석 결과를 이메일로 받아보실 수 있습니다.
                  </Typography>
                  
                  <Grid container spacing={2}>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        type="email"
                        label="이메일 주소"
                        value={emailSettings.email_address}
                        onChange={(e) => handleEmailChange('email_address', e.target.value)}
                        disabled={loading}
                        placeholder="example@email.com"
                        helperText="분석 결과를 받을 이메일 주소를 입력하세요"
                      />
                    </Grid>
                    
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={emailSettings.send_main_analysis}
                            onChange={(e) => handleEmailChange('send_main_analysis', e.target.checked)}
                            disabled={loading}
                            color="primary"
                          />
                        }
                        label="본분석 결과 이메일 받기"
                      />
                    </Grid>
                    
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={emailSettings.send_monitoring_analysis}
                            onChange={(e) => handleEmailChange('send_monitoring_analysis', e.target.checked)}
                            disabled={loading}
                            color="primary"
                          />
                        }
                        label="모니터링분석 결과 이메일 받기"
                      />
                    </Grid>
                    
                    <Grid item xs={12}>
                      <Button
                        variant="contained"
                        color="primary"
                        onClick={handleEmailSave}
                        disabled={loading || !isEmailSettingsChanged()}
                        fullWidth
                      >
                        이메일 설정 저장
                      </Button>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
            
            {/* 빗각 설정 */}
            <Grid item xs={12}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    📐 빗각 분석 포인트 설정
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                    차트를 보면서 중요한 포인트의 시간을 입력하세요. 형식: YYYY-MM-DD HH:MM (예: 2025-10-11 06:00)
                  </Typography>
                  
                  <Grid container spacing={3}>
                    {/* 빗각 타입 선택 */}
                    <Grid item xs={12}>
                      <FormControl component="fieldset">
                        <FormLabel component="legend">빗각 타입 선택</FormLabel>
                        <RadioGroup
                          value={diagonalSettings.diagonal_type || ''}
                          onChange={(e) => handleDiagonalChange('diagonal_type', e.target.value || null)}
                        >
                          <FormControlLabel 
                            value="uptrend" 
                            control={<Radio />} 
                            label="📈 상승 빗각 (상승 추세선)" 
                            disabled={loading}
                          />
                          <FormControlLabel 
                            value="downtrend" 
                            control={<Radio />} 
                            label="📉 하락 빗각 (하락 추세선)" 
                            disabled={loading}
                          />
                        </RadioGroup>
                      </FormControl>
                    </Grid>
                    
                    {/* 포인트 입력 필드 */}
                    {diagonalSettings.diagonal_type && (
                      <Grid item xs={12}>
                        <Box sx={{ 
                          border: '1px solid #e0e0e0', 
                          borderRadius: 2, 
                          p: 2, 
                          bgcolor: diagonalSettings.diagonal_type === 'uptrend' ? '#f5f5f5' : '#fff3e0' 
                        }}>
                          <Typography variant="h6" gutterBottom>
                            {diagonalSettings.diagonal_type === 'uptrend' ? 
                              '📈 상승 빗각 포인트 입력' : 
                              '📉 하락 빗각 포인트 입력'}
                          </Typography>
                          
                          <Grid container spacing={2}>
                            <Grid item xs={12} md={4}>
                              <TextField
                                fullWidth
                                label={diagonalSettings.diagonal_type === 'uptrend' ? 
                                  "Point A (역사적 저점) 시간" : 
                                  "Point A (역사적 고점) 시간"}
                                value={diagonalSettings.point_a_time}
                                onChange={(e) => handleDiagonalChange('point_a_time', e.target.value)}
                                disabled={loading}
                                placeholder="2025-10-11 06:00"
                                helperText={diagonalSettings.diagonal_type === 'uptrend' ? 
                                  "전체 데이터에서 가장 낮은 지점" : 
                                  "전체 데이터에서 가장 높은 지점"}
                              />
                            </Grid>
                            <Grid item xs={12} md={4}>
                              <TextField
                                fullWidth
                                label={diagonalSettings.diagonal_type === 'uptrend' ? 
                                  "두 번째 저점 시간" : 
                                  "두 번째 고점 시간"}
                                value={diagonalSettings.point_second_time}
                                onChange={(e) => handleDiagonalChange('point_second_time', e.target.value)}
                                disabled={loading}
                                placeholder="2025-10-17 19:00"
                                helperText={diagonalSettings.diagonal_type === 'uptrend' ? 
                                  "Point A 이후 형성된 의미있는 저점" : 
                                  "Point A 이후 형성된 의미있는 고점"}
                              />
                            </Grid>
                            <Grid item xs={12} md={4}>
                              <TextField
                                fullWidth
                                label="Point B (변곡점) 시간"
                                value={diagonalSettings.point_b_time}
                                onChange={(e) => handleDiagonalChange('point_b_time', e.target.value)}
                                disabled={loading}
                                placeholder="2025-10-17 01:00"
                                helperText={diagonalSettings.diagonal_type === 'uptrend' ? 
                                  "거래량 터지며 급락 시작 지점" : 
                                  "거래량 터지며 급등 시작 지점"}
                              />
                            </Grid>
                          </Grid>
                        </Box>
                      </Grid>
                    )}
                    
                    {/* 저장 버튼 */}
                    <Grid item xs={12}>
                      <Button
                        variant="contained"
                        color="primary"
                        onClick={handleDiagonalSave}
                        disabled={loading || !isDiagonalSettingsChanged()}
                        fullWidth
                        size="large"
                      >
                        빗각 설정 저장
                      </Button>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
            
            {/* 기존 트레이딩 설정 */}
            {settings.map((setting) => (
              <Grid item xs={12} key={setting.id}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {getSettingLabel(setting.setting_name)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {getSettingDescription(setting.setting_name)}
                    </Typography>
                    <Grid container spacing={2} alignItems="center">
                      <Grid item xs={12} sm={6}>
                        <TextField
                          fullWidth
                          type="number"
                          label="값 (분)"
                          value={localSettings[setting.setting_name] || 0}
                          onChange={(e) => handleChange(setting.setting_name, e.target.value)}
                          disabled={loading}
                          inputProps={{ min: 1 }}
                        />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Button
                          variant="contained"
                          color="primary"
                          onClick={() => handleSave(setting.setting_name)}
                          disabled={loading || localSettings[setting.setting_name] === setting.setting_value}
                          fullWidth
                        >
                          저장
                        </Button>
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </CardContent>
    </Card>
  );
}

export default TradingSettings;

