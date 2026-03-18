import { useState, useEffect, useCallback } from 'react';
import { fetchMemories, addMemory as apiAddMemory, deleteMemory as apiDeleteMemory } from '../utils/api';

/**
 * Fetches and manages Sifra's memories with optimistic UI.
 */
export function useMemories() {
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMemories(filter);
      setMemories(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [refresh]);

  const addMemory = useCallback(async (content, category, importance) => {
    // Optimistic add
    const tempId = `temp-${Date.now()}`;
    const tempMemory = {
      id: tempId,
      content,
      category,
      importance,
      decay_score: 1.0,
      times_referenced: 0,
      created_at: new Date().toISOString(),
      last_referenced: new Date().toISOString(),
    };
    setMemories(prev => [tempMemory, ...prev]);

    try {
      const result = await apiAddMemory(content, category, importance);
      setMemories(prev => prev.map(m => m.id === tempId ? result : m));
      return result;
    } catch (err) {
      setMemories(prev => prev.filter(m => m.id !== tempId));
      throw err;
    }
  }, []);

  const removeMemory = useCallback(async (memoryId) => {
    const backup = memories;
    setMemories(prev => prev.filter(m => m.id !== memoryId));

    try {
      await apiDeleteMemory(memoryId);
    } catch (err) {
      setMemories(backup);
      throw err;
    }
  }, [memories]);

  return { memories, loading, error, filter, setFilter, addMemory, removeMemory, refresh };
}
