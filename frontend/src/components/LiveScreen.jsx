import React, { useEffect, useRef, useState, useCallback } from 'react'

const SPEEDS = ['1x', '5x', 'instant']

export default function LiveScreen({ sessionId, teamInfo, lang, onFinished, onRestart }) {
  const [ticker, setTicker] = useState(null)
  const [points, setPoints] = useState(0)
  const [delta, setDelta] = useState(null)
  const [rank, setRank] = useState(null)
  const [rankMovement, setRankMovement] = useState(null)
  const [feed, setFeed] = useState([])
  const [paused, setPaused] = useState(false)
  const [speed, setSpeed] = useState('1x')
  const [status, setStatus] = useState('connecting')
  const esRef = useRef(null)
  const pausedRef = useRef(false)
  const bufferRef = useRef([])
  const feedRef = useRef([])

  const connect = useCallback((spd) => {
    if (esRef.current) esRef.current.close()
    setStatus('connecting')
    setFeed([])
    feedRef.current = []
    setPoints(0)
    setDelta(null)
    setRank(null)
    setRankMovement(null)
    setTicker(null)

    const url = `/api/fan/sessions/${sessionId}/stream?speed=${spd}`
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setStatus('live')

    es.onmessage = (e) => {
      if (pausedRef.current) {
        bufferRef.current.push(e.data)
        return
      }
      processEvent(e.data)
    }

    es.onerror = () => {
      setStatus('error')
      es.close()
    }
  }, [sessionId])

  function processEvent(raw) {
    let item
    try { item = JSON.parse(raw) } catch { return }

    if (item.item_type === 'marker') {
      const mt = item.marker?.marker_type
      if (mt === 'innings_break') {
        addFeedItem({ type: 'break', text: '— Innings Break —', id: `break-${Date.now()}` })
      } else if (mt === 'match_finished') {
        setStatus('finished')
        onFinished(item.marker?.final_summary || null)
      }
      return
    }

    // delivery event
    if (item.delivery) {
      const d = item.delivery
      const sit = d.situation || {}
      setTicker({
        batting_team: d.batting_team,
        score: sit.score,
        wickets: sit.wickets,
        overs: sit.overs_completed,
        ball: d.ball_display,
        last_ball: d.runs_scored != null ? `${d.runs_scored} runs` : '',
        event: d.event,
        extra_type: d.extra_type,
      })
      setPoints(item.team_points ?? 0)
      setDelta(item.points_delta ?? null)
      setRank(item.simulated_rank ?? null)
      setRankMovement(item.rank_movement ?? null)

      if (item.key_moment?.is_key_moment) {
        const km = item.key_moment
        const expl = km.explanation || {}
        const facts = km.facts || {}
        const isHattrick = facts.is_hattrick
        const isFinalOver = d.ball_display && String(d.ball_display).startsWith('19.')

        addFeedItem({
          type: 'moment',
          id: `km-${item.stream_index}`,
          ball: d.ball_display,
          en: expl.explanation_en,
          hi: expl.explanation_hi,
          watchEn: expl.watch_next_en,
          watchHi: expl.watch_next_hi,
          delta: item.points_delta,
          reasons: km.reasons || [],
          isHattrick,
          isFinalOver,
          isFallback: expl.is_fallback,
        })
      }
    }
  }

  function addFeedItem(item) {
    feedRef.current = [item, ...feedRef.current].slice(0, 60)
    setFeed([...feedRef.current])
  }

  useEffect(() => {
    pausedRef.current = false
    connect(speed)
    return () => esRef.current?.close()
  }, [sessionId])

  function togglePause() {
    const nowPaused = !paused
    setPaused(nowPaused)
    pausedRef.current = nowPaused
    if (!nowPaused) {
      // flush buffer
      const buf = bufferRef.current.splice(0)
      buf.forEach(processEvent)
    }
  }

  function handleSpeed(spd) {
    setSpeed(spd)
    connect(spd)
  }

  function handleRestart() {
    esRef.current?.close()
    onRestart()
  }

  const deltaColor = delta > 0 ? '#10b981' : delta < 0 ? '#ef4444' : '#94a3b8'
  const rankColor = rankMovement > 0 ? '#10b981' : rankMovement < 0 ? '#ef4444' : '#94a3b8'

  return (
    <main className="screen-pad live-screen">
      {/* Score Ticker */}
      <div className="score-ticker">
        <div className="ticker-team">{ticker?.batting_team || '—'}</div>
        <div className="ticker-score">
          {ticker ? `${ticker.score ?? '?'}/${ticker.wickets ?? '?'}` : '—/—'}
          <span className="ticker-overs"> ({ticker?.overs ?? '?'} ov)</span>
        </div>
        <div className="ticker-ball">
          Ball {ticker?.ball || '—'} · {ticker?.last_ball || ''}
          {ticker?.event && ticker.event !== 'normal' && (
            <span className="ball-event"> [{ticker.event}]</span>
          )}
        </div>
        <span className={`status-dot ${status}`} title={status} />
      </div>

      {/* My Team Card */}
      <div className="my-team-card">
        <div className="team-header-row">
          <span className="my-team-name">{teamInfo?.name}</span>
          <span className="c-vc-label">C: {teamInfo?.captain} &nbsp; VC: {teamInfo?.vice_captain}</span>
        </div>
        <div className="points-row">
          <div className="big-points">{(points || 0).toFixed(1)}</div>
          {delta !== null && (
            <div className="delta-badge" style={{ color: deltaColor }}>
              {delta > 0 ? '+' : ''}{delta.toFixed(1)} pts
            </div>
          )}
        </div>
        <div className="rank-row">
          <span className="rank-label">simulated rank among 10,000 sample teams</span>
          {rank !== null && (
            <span className="rank-value" style={{ color: rankColor }}>
              #{rank}
              {rankMovement !== null && rankMovement !== 0 && (
                <span> ({rankMovement > 0 ? '▲' : '▼'}{Math.abs(rankMovement)})</span>
              )}
            </span>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="controls-row">
        <button className="ctrl-btn" onClick={togglePause}>
          {paused ? '▶ Resume' : '⏸ Pause'}
        </button>
        <button className="ctrl-btn" onClick={handleRestart}>↩ Restart</button>
        <div className="speed-group">
          {SPEEDS.map(s => (
            <button
              key={s}
              className={`speed-btn ${speed === s ? 'active' : ''}`}
              onClick={() => handleSpeed(s)}
            >{s}</button>
          ))}
        </div>
      </div>

      {/* Feed */}
      <div className="feed-label">
        {lang === 'en' ? 'Why it moved' : 'क्यों हिला?'}
      </div>
      <div className="feed-list">
        {feed.length === 0 && (
          <p className="feed-empty">
            {status === 'connecting' ? 'Connecting…' : 'Waiting for key moments…'}
          </p>
        )}
        {feed.map(item => {
          if (item.type === 'break') {
            return (
              <div key={item.id} className="innings-break">{item.text}</div>
            )
          }
          const highlight = item.isHattrick
            ? 'hattrick'
            : item.isFinalOver
            ? 'final-over'
            : ''
          const text = lang === 'en' ? item.en : item.hi
          const watch = lang === 'en' ? item.watchEn : item.watchHi
          const dc = (item.delta || 0) >= 0 ? '#10b981' : '#ef4444'
          return (
            <div key={item.id} className={`feed-item ${highlight}`}>
              <div className="feed-top">
                <span className="feed-ball">Ball {item.ball}</span>
                <span className="feed-delta" style={{ color: dc }}>
                  {(item.delta || 0) >= 0 ? '+' : ''}{(item.delta || 0).toFixed(1)}
                </span>
                {item.isHattrick && <span className="badge-hat">🎩 Hat-trick!</span>}
                {item.isFinalOver && !item.isHattrick && <span className="badge-final">🏁 Final Over</span>}
                {item.isFallback && <span className="badge-fallback">auto</span>}
              </div>
              <p className="feed-text">{text || '—'}</p>
              {watch && <p className="feed-watch">👀 {watch}</p>}
            </div>
          )
        })}
      </div>
    </main>
  )
}

