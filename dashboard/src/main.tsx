import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/panels.css'
import App from './App.tsx'
import LoginGate from './features/auth/LoginGate.tsx'

// The gate sits above App so nothing in it, ticket polling included, runs before an analyst signs in.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LoginGate>
      <App />
    </LoginGate>
  </StrictMode>,
)
