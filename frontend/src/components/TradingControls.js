import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useWebSocket, WS_EVENT_TYPES } from '../services/websocket';

// axios 기본 URL 설정
axios.defaults.baseURL = 'http://localhost:8000';  // FastAPI 서버 주소

function TradingControls() {
    const [isLoading, setIsLoading] = useState(false);
    const [result, setResult] = useState(null);
    
    // 웹소켓 연결 설정
    const { messages } = useWebSocket([WS_EVENT_TYPES.ANALYSIS_RESULT]);
    
    // 웹소켓으로 분석 결과 수신 시 Trading Controls 정보 업데이트
    useEffect(() => {
        if (messages && messages[WS_EVENT_TYPES.ANALYSIS_RESULT]) {
            const analysisResult = messages[WS_EVENT_TYPES.ANALYSIS_RESULT].data;
            console.log('웹소켓으로 분석 결과 수신:', analysisResult);
            
            // Trading Controls 정보가 있으면 결과 업데이트
            if (analysisResult && analysisResult.trading_controls) {
                console.log('Trading Controls 정보 업데이트:', analysisResult.trading_controls);
                setResult(analysisResult);
            }
        }
    }, [messages]);

    const testTrade = async (action) => {
        try {
            setIsLoading(true);
            const response = await axios.post('/api/trading/test-trade', { action: action });
            setResult(response.data);
            console.log('Test trade result:', response.data);
        } catch (error) {
            console.error('Error:', error);
            setResult({ error: error.message });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="p-4">
            <div className="flex gap-4 mb-4">
                <button
                    className="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded"
                    onClick={() => testTrade('ENTER_LONG')}
                    disabled={isLoading}
                >
                    Test Long Position
                </button>
                <button
                    className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded"
                    onClick={() => testTrade('ENTER_SHORT')}
                    disabled={isLoading}
                >
                    Test Short Position
                </button>
            </div>
            
            {isLoading && (
                <div className="text-gray-600">Processing...</div>
            )}
            
            {result && (
                <div className="mt-4">
                    <h3 className="font-bold">Result:</h3>
                    <pre className="bg-gray-100 p-4 rounded mt-2">
                        {JSON.stringify(result, null, 2)}
                    </pre>
                </div>
            )}
        </div>
    );
}

export default TradingControls; 