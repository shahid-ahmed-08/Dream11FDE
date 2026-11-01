import React, { useEffect, useState } from 'react'

const PRESETS = [
  {
    key: 'safe_pick',
    name: 'Safe Pick',
    captain: 'Shubman Gill',
    vice_captain: 'WP Saha',
    desc: 'Consistent performers, low risk',
    color: '#10b981',
  },
  {
    key: 'differential',
    name: 'Differential',
    captain: 'Rashid Khan',
    vice_captain: 'SP Narine',
    desc: 'High upside, hat-trick captain',
    color: '#f59e0b',
  },
  {
    key: 'finisher_fan',
    name: 'Finisher Fan',
    captain: 'AD Russell',
    vice_captain: 'RK Singh',
    desc: 'Death-over specialist picks',
    color: '#ef4444',
  },
]

export default function StartScreen({ lang, onSelect }) {
  const [loading, setLoading] = useState(null)
  const [error, setError] = useState(null)

  async function handleSelect(preset) {
    setLoading(preset.key)
    setError(null)
    try {
      const res = await fetch('/api/fan/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset: preset.key }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      onSelect(data.session_id, { ...preset, ...data })
    } catch (e) {
      setError(e.message)
      setLoading(null)
    }
  }

  return (
    <main className="screen-pad">
      <h2 className="section-title">
        {lang === 'en' ? 'Choose Your Team' : 'अपनी टीम चुनो'}
      </h2>
      <p className="section-sub">
        {lang === 'en'
          ? 'Replay the match ball-by-ball and see why your rank moved.'
          : 'Match replay देखो ball-by-ball और समझो rank क्यों हिली।'}
      </p>
      <div className="team-cards">
        {PRESETS.map(p => (
          <button
            key={p.key}
            className="team-card"
            style={{ '--card-accent': p.color }}
            onClick={() => handleSelect(p)}
            disabled={!!loading}
          >
            <div className="team-card-header">
              <span className="team-name">{p.name}</span>
              {loading === p.key && <span className="spinner" />}
            </div>
            <p className="team-desc">{p.desc}</p>
            <div className="team-roles">
              <span className="role-badge c">C: {p.captain}</span>
              <span className="role-badge vc">VC: {p.vice_captain}</span>
            </div>
          </button>
        ))}
      </div>
      {error && <p className="error-msg">Error: {error}</p>}
    </main>
  )
}

