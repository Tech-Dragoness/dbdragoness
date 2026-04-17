import { useState, useEffect } from 'react';
import axios from 'axios';

const getSessionId = () => {
  let sessionId = localStorage.getItem('query_session_id');
  if (!sessionId) {
    sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    localStorage.setItem('query_session_id', sessionId);
  }
  return sessionId;
};

export const useQueryHistory = (context = 'global') => {
  const [sessionQueries, setSessionQueries] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [draftQuery, setDraftQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const sessionId = getSessionId();

  const fetchSessionQueries = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/api/query/history/session', {
        params: { context },
        headers: { 'X-Session-ID': sessionId }
      });

      if (response.data.success) {
        console.log('📜 Fetched session queries:', response.data.queries.length, 'for', response.data.handler);
        setSessionQueries(response.data.queries || []);
      }
    } catch (err) {
      console.error('❌ Failed to fetch session queries:', err);
    } finally {
      setLoading(false);
    }
  };

  // ✅ REMOVED db_type parameter - backend uses CURRENT_HANDLER_NAME
  const addQuery = async (query) => {
    try {
      console.log('➕ Adding query to history');
      
      await axios.post('/api/query/history/session', 
        { query },  // ✅ No db_type needed - backend knows current handler
        { headers: { 'X-Session-ID': sessionId } }
      );
      
      await fetchSessionQueries();
      setCurrentIndex(-1);
      setDraftQuery('');
      
      console.log('✅ Query added successfully');
    } catch (err) {
      console.error('❌ Failed to add query to history:', err);
    }
  };

  const clearHistory = async () => {
    try {
      await axios.delete('/api/query/history/session', {
        headers: { 'X-Session-ID': sessionId }
      });
      setSessionQueries([]);
      setCurrentIndex(-1);
      setDraftQuery('');
    } catch (err) {
      console.error('Failed to clear history:', err);
    }
  };

  const navigateHistory = (direction, currentQuery) => {
    if (sessionQueries.length === 0) return null;

    let newIndex = currentIndex;

    if (direction === 'up') {
      if (currentIndex === -1) {
        setDraftQuery(currentQuery);
        newIndex = sessionQueries.length - 1;
      } else if (currentIndex > 0) {
        newIndex = currentIndex - 1;
      } else {
        return null;
      }
    } else if (direction === 'down') {
      if (currentIndex === -1) {
        return null;
      } else if (currentIndex < sessionQueries.length - 1) {
        newIndex = currentIndex + 1;
      } else {
        setCurrentIndex(-1);
        return draftQuery;
      }
    }

    setCurrentIndex(newIndex);
    return sessionQueries[newIndex];
  };

  const resetNavigation = () => {
    setCurrentIndex(-1);
    setDraftQuery('');
  };

  useEffect(() => {
    fetchSessionQueries();
  }, [context]);

  return {
    sessionQueries,
    loading,
    addQuery,
    clearHistory,
    navigateHistory,
    resetNavigation,
    currentIndex,
    draftQuery,
    refreshHistory: fetchSessionQueries
  };
};