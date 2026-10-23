import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from '@/App'
import { AnalyticsPage } from '@/analytics/AnalyticsPage'

const queryClient = new QueryClient()
// Two pages, each a full page load: the game at /, the Ranking at /analytics (FastAPI serves both).
const Page = window.location.pathname.replace(/\/$/, '') === '/analytics' ? AnalyticsPage : App

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>
  </StrictMode>,
)
