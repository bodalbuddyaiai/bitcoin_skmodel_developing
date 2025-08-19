import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { getTradingHistory } from '../services/api';
import { 
  Box, 
  Card, 
  CardContent, 
  Typography, 
  Table, 
  TableBody, 
  TableCell, 
  TableContainer, 
  TableHead, 
  TableRow, 
  Paper 
} from '@mui/material';

const TradingHistory = () => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        setLoading(true);
        const response = await getTradingHistory();
        setHistory(response.data);
      } catch (error) {
        console.error('Error loading history:', error);
      } finally {
        setLoading(false);
      }
    };
    loadHistory();
  }, []);

  const formatToKST = (timestamp) => {
    const date = new Date(timestamp);
    return new Intl.DateTimeFormat('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: 'Asia/Seoul'
    }).format(date);
  };

  if (loading) return <Typography>Loading...</Typography>;
  if (error) return <Typography color="error">{error}</Typography>;

  return (
    <Box sx={{ mt: 4 }}>
      <Typography variant="h5" gutterBottom>
        Trading History
      </Typography>
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Leverage</TableCell>
              <TableCell>Position Size</TableCell>
              <TableCell>Expected Minutes</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {history.map((record) => (
              <TableRow key={record.id}>
                <TableCell>
                  {formatToKST(record.timestamp)}
                </TableCell>
                <TableCell>{record.action}</TableCell>
                <TableCell>{record.leverage}x</TableCell>
                <TableCell>{(record.position_size * 100).toFixed(1)}%</TableCell>
                <TableCell>{record.expected_minutes} min</TableCell>
                <TableCell>
                  {record.execution_result?.success ? 'Success' : 'Failed'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* 상세 정보 표시 */}
      {history.length > 0 && (
        <Card sx={{ mt: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Latest Analysis
            </Typography>
            <Box sx={{ 
              '& p': { margin: '0.5em 0' },  // 마크다운 단락 스타일링
              '& strong': { fontWeight: 'bold' },  // 볼드 텍스트 스타일링
              '& ul, & ol': { marginLeft: '1.5em' },  // 리스트 스타일링
            }}>
              <ReactMarkdown>
                {history[0].reason}
              </ReactMarkdown>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default TradingHistory; 