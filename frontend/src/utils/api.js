/**
 * API utility — all fetch calls to the SIFRA:MIND backend.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '';

async function apiFetch(endpoint, options = {}) {
  try {
    const url = `${BASE_URL}${endpoint}`;
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error(`API call failed [${endpoint}]:`, error);
    throw error;
  }
}

export async function fetchState() {
  return apiFetch('/api/state');
}

export async function fetchMemories(category = null) {
  const params = category ? `?category=${category}` : '';
  return apiFetch(`/api/memories${params}`);
}

export async function fetchConversations(limit = 50) {
  return apiFetch(`/api/conversations?limit=${limit}`);
}

export async function fetchMoodHistory(days = 7) {
  return apiFetch(`/api/mood_history?days=${days}`);
}

export async function addMemory(content, category = 'core', importance = 5) {
  return apiFetch('/api/memories', {
    method: 'POST',
    body: JSON.stringify({ content, category, importance }),
  });
}

export async function deleteMemory(memoryId) {
  return apiFetch(`/api/memories/${memoryId}/delete`, {
    method: 'POST',
  });
}

export async function fetchHealth() {
  return apiFetch('/health');
}

// --- Reset / Factory Wipe ---

export async function resetMemories() {
  return apiFetch('/api/reset/memories', { method: 'POST' });
}

export async function resetConversations() {
  return apiFetch('/api/reset/conversations', { method: 'POST' });
}

export async function factoryReset() {
  return apiFetch('/api/reset/full', { method: 'POST' });
}

