import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from '@/App'
import { AnalyticsPage } from '@/analytics/AnalyticsPage'
// PROTOTYPE, throwaway: the System 1 Turn panel prototype (ticket 10 of #124), at /?prototype=system1-turn.
import { System1TurnPrototype, system1TurnActive } from '@/components/turn/system1/System1Turn.prototype'

const queryClient = new QueryClient()
// Two pages, each a full page load: the game at /, the Ranking at /analytics (FastAPI serves both).
const Page = system1TurnActive
  ? System1TurnPrototype
  : window.location.pathname.replace(/\/$/, '') === '/analytics'
    ? AnalyticsPage
    : App

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>
  </StrictMode>,
)
