import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchState } from '../utils/api';

/**
 * Polls /api/state every 10 seconds for Sifra's current state.
 */
export function useSifraState() {
  const [state, setState] = useState({
    current_mood: 'neutral',
    energy_level: 7,
    last_active: null,
    active_memories: [],
    today_summary: '',
    personality_mode: 'normal',
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchState();
      setState(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    intervalRef.current = setInterval(refresh, 10000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [refresh]);

  return { state, loading, error, refresh };
}
