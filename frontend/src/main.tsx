import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Bundled variable fonts (no CDN — survives an offline demo).
// Inter = UI/body; Source Serif 4 = report headings + brand wordmark.
import '@fontsource-variable/inter'
import '@fontsource-variable/source-serif-4'
// JetBrains Mono = display metric numerals (Bloomberg-style tabular numbers).
import '@fontsource-variable/jetbrains-mono/index.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
