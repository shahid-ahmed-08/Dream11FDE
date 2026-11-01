import React, { useState } from 'react'
import StartScreen from './components/StartScreen'
import LiveScreen from './components/LiveScreen'
import FinishedScreen from './components/FinishedScreen'

export default function App() {
  const [screen, setScreen] = useState('start') // 'start' | 'live' | 'finished'
  const [sessionId, setSessionId] = useState(null)
  const [teamInfo, setTeamInfo] = useState(null)
  const [lang, setLang] = useState('en')
  const [finalData, setFinalData] = useState(null)

  function handleTeamSelect(sid, info) {
    setSessionId(sid)
    setTeamInfo(info)
    setScreen('live')
  }

  function handleMatchFinished(data) {
    setFinalData(data)
    setScreen('finished')
  }

  function handleRestart() {
    setScreen('start')
    setSessionId(null)
    setTeamInfo(null)
    setFinalData(null)
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1 className="app-title">Why Did My Rank Drop?</h1>
          <p className="app-subtitle">GT vs KKR · IPL 2023</p>
        </div>
        <button
          className="lang-toggle"
          onClick={() => setLang(l => l === 'en' ? 'hi' : 'en')}
        >
          {lang === 'en' ? 'हिं' : 'EN'}
        </button>
      </header>

      {screen === 'start' && (
        <StartScreen lang={lang} onSelect={handleTeamSelect} />
      )}
      {screen === 'live' && (
        <LiveScreen
          sessionId={sessionId}
          teamInfo={teamInfo}
          lang={lang}
          onFinished={handleMatchFinished}
          onRestart={handleRestart}
        />
      )}
      {screen === 'finished' && (
        <FinishedScreen
          sessionId={sessionId}
          finalData={finalData}
          lang={lang}
          onRestart={handleRestart}
        />
      )}

      <footer className="app-footer">
        Replay of GT vs KKR, IPL 2023. Simulated live.
      </footer>
    </div>
  )
}
