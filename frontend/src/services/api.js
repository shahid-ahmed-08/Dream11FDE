/**
 * API Service for Why Did My Rank Drop
 * Communicates with FastAPI backend.
 * Note: Never includes or requires Gemini API keys; all AI and analysis logic stays on the backend.
 */

const BASE_URL = '' // Uses Vite reverse-proxy during dev

export async function fetchHealth() {
  const res = await fetch(`${BASE_URL}/health`)
  if (!res.ok) throw new Error(`Healthcheck failed: ${res.statusText}`)
  return res.json()
}

export async function fetchMatchSummary(matchId = '1359487') {
  const res = await fetch(`${BASE_URL}/api/match/summary?match_id=${matchId}`)
  if (!res.ok) throw new Error(`Failed to fetch match summary: ${res.statusText}`)
  return res.json()
}

export async function fetchSquads(matchId = '1359487') {
  const res = await fetch(`${BASE_URL}/api/match/squads?match_id=${matchId}`)
  if (!res.ok) throw new Error(`Failed to fetch squads: ${res.statusText}`)
  return res.json()
}

export async function fetchEvents(matchId = '1359487', innings = null, limit = null) {
  const params = new URLSearchParams({ match_id: matchId })
  if (innings) params.append('innings', innings)
  if (limit) params.append('limit', limit)

  const res = await fetch(`${BASE_URL}/api/match/events?${params.toString()}`)
  if (!res.ok) throw new Error(`Failed to fetch events: ${res.statusText}`)
  return res.json()
}


// Replay Engine API Endpoints
export async function createReplaySession(matchId = '1359487') {
  const res = await fetch(`${BASE_URL}/api/replay/sessions?match_id=${matchId}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to create replay session: ${res.statusText}`)
  return res.json()
}

export async function fetchSessionState(sessionId) {
  const res = await fetch(`${BASE_URL}/api/replay/sessions/${sessionId}`)
  if (!res.ok) throw new Error(`Failed to fetch session state: ${res.statusText}`)
  return res.json()
}

export async function sendReplayControl(sessionId, action, speed = null) {
  const res = await fetch(`${BASE_URL}/api/replay/sessions/${sessionId}/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, speed }),
  })
  if (!res.ok) throw new Error(`Failed to send control: ${res.statusText}`)
  return res.json()
}

export async function fetchReplayEvents(sessionId, fromIndex = 0) {
  const res = await fetch(`${BASE_URL}/api/replay/sessions/${sessionId}/events?from_index=${fromIndex}`)
  if (!res.ok) throw new Error(`Failed to fetch replay events: ${res.statusText}`)
  return res.json()
}

export function subscribeToReplayStream(sessionId, fromIndex = null, onMessage, onComplete, onError) {
  const url = fromIndex !== null
    ? `${BASE_URL}/api/replay/sessions/${sessionId}/stream?from_index=${fromIndex}`
    : `${BASE_URL}/api/replay/sessions/${sessionId}/stream`
  
  const eventSource = new EventSource(url)
  eventSource.addEventListener('replay_item', (e) => {
    try {
      const data = JSON.parse(e.data)
      onMessage(data)
    } catch (err) {
      console.error('Failed to parse SSE data', err)
    }
  })
  eventSource.addEventListener('complete', () => {
    onComplete && onComplete()
    eventSource.close()
  })
  eventSource.onerror = (err) => {
    onError && onError(err)
  }
  return eventSource
}
