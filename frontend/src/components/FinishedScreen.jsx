import React, { useEffect, useState } from 'react'

export default function FinishedScreen({ sessionId, finalData, lang, onRestart }) {
  const [data, setData] = useState(finalData)

  useEffect(() => {
    if (!data && sessionId) {
      fetch(`/api/fan/sessions/${sessionId}/summary`)
        .then(r => r.json())
        .then(setData)
        .catch(() => {})
    }
  }, [sessionId, data])

  if (!data) {
    return (
      <main className="screen-pad">
        <p style={{ color: '#94a3b8' }}>Loading final summary…</p>
      </main>
    )
  }

  const pct = data.percentile ? data.percentile.toFixed(1) : '—'
  const best = data.best_moment
  const worst = data.worst_moment

  return (
    <main className="screen-pad">
      <div className="finished-hero">
        <div className="finished-title">
          {lang === 'en' ? '🏆 Match Over' : '🏆 मैच खत्म!'}
        </div>
        <div className="finished-team">{data.fan_team_name}</div>
        <div className="finished-pts">{(data.final_points || 0).toFixed(1)} pts</div>
        <div className="finished-rank">
          #{data.final_simulated_rank}
          <span className="rank-pct"> · Top {100 - pct}%</span>
        </div>
        <div className="rank-sublabel">simulated rank among 10,000 sample teams</div>
      </div>

      {best && (
        <div className="moment-card best">
          <div className="moment-label">🔥 {lang === 'en' ? 'Best Moment' : 'सबसे अच्छा पल'}</div>
          <div className="moment-ball">Ball {best.ball}</div>
          <div className="moment-reasons">{(best.reasons || []).join(' · ')}</div>
          <div className="moment-delta">+{(best.team_delta || 0).toFixed(1)} pts</div>
        </div>
      )}

      {worst && (
        <div className="moment-card worst">
          <div className="moment-label">📉 {lang === 'en' ? 'Worst Moment' : 'सबसे बुरा पल'}</div>
          <div className="moment-ball">Ball {worst.ball}</div>
          <div className="moment-reasons">{(worst.reasons || []).join(' · ')}</div>
          <div className="moment-delta" style={{ color: '#ef4444' }}>
            {(worst.team_delta || 0).toFixed(1)} pts
          </div>
        </div>
      )}

      <button className="ctrl-btn full-width" onClick={onRestart}>
        {lang === 'en' ? '↩ Play Again' : '↩ फिर खेलो'}
      </button>
    </main>
  )
}

