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
  Box
} from '@mui/material';
import { getSettings, updateSetting } from '../services/api';

function TradingSettings() {
  const [settings, setSettings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [localSettings, setLocalSettings] = useState({});

  // 설정 로드
  useEffect(() => {
    loadSettings();
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

