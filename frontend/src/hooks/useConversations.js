import { useState, useEffect, useCallback } from 'react';
import { fetchConversations } from '../utils/api';

/**
 * Fetches the last N conversations and auto-refreshes every 10s.
 */
export function useConversations(limit = 50) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchConversations(limit);
      setConversations(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, [refresh]);

  return { conversations, loading, error, refresh };
}
