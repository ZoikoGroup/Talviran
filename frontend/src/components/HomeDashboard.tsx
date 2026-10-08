import React, { useState } from 'react'
import {
  Search,
  ArrowRight,
  Globe,
  Bell,
  ChevronRight,
  BarChart3,
  FileText,
  Bookmark,
  Layers,
  Sparkles,
} from 'lucide-react'
import earthImg from '@/assets/earth_space_view.jpg'

interface HomeDashboardProps {
  onSearch: (query: string) => void
  onStartResearch: () => void
  onOpenMonitoring?: () => void
}

export default function HomeDashboard({
  onSearch,
  onStartResearch,
  onOpenMonitoring,
}: HomeDashboardProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSource, setSelectedSource] = useState('All sources')

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchQuery.trim()) {
      onSearch(searchQuery.trim())
    }
  }

  const quickPills = [
    'Compare 10Y gilts vs 10Y Treasuries',
    'Latest Fed policy decision',
    'NVIDIA financials',
    'UK inflation trend',
    'Global bond yields',
  ]

  const tickers = [
    {
      title: 'UK 10Y Gilt',
      value: '4.216%',
      change: '▼ 2.4 bps',
      isUp: false,
      isBps: true,
      sparkline: 'M0,18 C10,15 20,24 30,22 C40,20 50,26 60,18 C70,12 80,16 90,8',
    },
    {
      title: 'US 10Y Treasury',
      value: '4.327%',
      change: '▲ 1.1 bps',
      isUp: true,
      isBps: true,
      sparkline: 'M0,22 C12,24 24,18 36,19 C48,15 60,12 72,14 C84,8 90,4 100,2',
    },
    {
      title: 'S&P 500',
      value: '6,589.34',
      change: '▲ 0.62%',
      isUp: true,
      sparkline: 'M0,25 C15,22 25,26 35,20 C45,16 55,22 65,14 C75,10 85,12 95,2',
    },
    {
      title: 'FTSE 100',
      value: '8,261.40',
      change: '▲ 0.28%',
      isUp: true,
      sparkline: 'M0,24 C10,22 20,25 30,20 C40,16 50,19 60,14 C70,15 80,10 90,6',
    },
    {
      title: 'DXY',
      value: '100.18',
      change: '▼ 0.31%',
      isUp: false,
      sparkline: 'M0,8 C12,10 24,7 36,15 C48,12 60,18 72,22 C84,18 90,24 100,22',
    },
  ]

  const keyDevelopments = [
    {
      time: '2h',
      dotColor: 'bg-emerald-400',
      title: 'US Treasury yields edge higher after strong retail sales data',
      tags: ['US Treasury', 'Economic Data', 'Macro'],
    },
    {
      time: '4h',
      dotColor: 'bg-emerald-400',
      title: 'UK inflation falls to 2.2% in August',
      tags: ['UK Economy', 'Inflation', 'BoE'],
    },
    {
      time: '6h',
      dotColor: 'bg-blue-400',
      title: 'NVIDIA announces new AI chip platform',
      tags: ['NVIDIA', 'Equities', 'Company Filings'],
    },
    {
      time: '8h',
      dotColor: 'bg-blue-400',
      title: 'ECB signals cautious approach to further cuts',
      tags: ['ECB', 'Monetary Policy', 'Euro Area'],
    },
    {
      time: '1d',
      dotColor: 'bg-blue-400',
      title: 'China industrial output beats expectations',
      tags: ['China', 'Economic Data', 'Asia'],
    },
  ]

  const userAlerts = [
    {
      title: 'US 10Y yield moved above 4.30%',
      time: '12 minutes ago',
      color: 'bg-amber-400',
    },
    {
      title: 'UK CPI data released',
      time: '2 hours ago',
      color: 'bg-emerald-400',
    },
    {
      title: 'NVIDIA filing updated (10-Q)',
      time: '6 hours ago',
      color: 'bg-blue-500',
    },
  ]

  const economicCalendar = [
    { date: '18 Sep', time: '13:30', flag: '🇺🇸', code: 'US', event: 'Initial Jobless Claims' },
    { date: '18 Sep', time: '15:00', flag: '🇺🇸', code: 'US', event: 'Existing Home Sales' },
    { date: '19 Sep', time: '07:00', flag: '🇬🇧', code: 'UK', event: 'Retail Sales (MoM)' },
    { date: '19 Sep', time: '09:00', flag: '🇪🇺', code: 'EU', event: 'ECB President Speech' },
    { date: '19 Sep', time: '13:30', flag: '🇺🇸', code: 'US', event: 'Fed Balance Sheet' },
  ]

  const recentResearch = [
    {
      title: 'Compare the 10Y gilt and 10Y Treasury',
      time: 'Last edited 2 hours ago',
      icon: BarChart3,
    },
    {
      title: 'NVIDIA - latest financial performance',
      time: 'Last edited 5 hours ago',
      icon: FileText,
    },
    {
      title: 'UK inflation analysis',
      time: 'Last edited 1 day ago',
      icon: BarChart3,
    },
    {
      title: 'Global central bank policy comparison',
      time: 'Last edited 2 days ago',
      icon: Bookmark,
    },
  ]

  const savedWatchlists = [
    {
      title: 'Core Bonds',
      detail: '12 instruments',
      change: '▲ 0.18%',
      isUp: true,
      icon: Layers,
    },
    {
      title: 'Tech Leaders',
      detail: '8 instruments',
      change: '▲ 1.24%',
      isUp: true,
      icon: Sparkles,
    },
    {
      title: 'UK Equities',
      detail: '15 instruments',
      change: '▲ 0.32%',
      isUp: true,
      icon: FileText,
    },
    {
      title: 'Global ETFs',
      detail: '10 instruments',
      change: '▼ 0.21%',
      isUp: false,
      icon: Layers,
    },
  ]

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 scrollbar-slim lg:px-10">
      <div className="mx-auto max-w-[1480px] space-y-6">
        {/* Top Header Row: Greeting + Live Market Timezones & Global Coverage */}
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div>
            <div className="text-[13px] font-medium text-muted-foreground">Good afternoon,</div>
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Turn questions into evidence.
            </h1>
            <p className="mt-1 text-[14px] text-muted-foreground">
              Search authoritative sources. Get clear answers. Make better decisions.
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-6 rounded-xl border border-border/60 bg-card/60 px-4 py-2.5 backdrop-blur-md">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">London</div>
              <div className="text-[14px] font-semibold text-foreground">16:24</div>
              <div className="text-[10px] text-muted-foreground">Thu, 18 Sep 2026</div>
            </div>
            <div className="h-7 w-px bg-border/80" />
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">New York</div>
              <div className="text-[14px] font-semibold text-foreground">11:24</div>
              <div className="text-[10px] text-muted-foreground">Thu, 18 Sep 2026</div>
            </div>
            <div className="h-7 w-px bg-border/80" />
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Tokyo</div>
              <div className="text-[14px] font-semibold text-foreground">00:24</div>
              <div className="text-[10px] text-muted-foreground">Fri, 19 Sep 2026</div>
            </div>
            <div className="h-7 w-px bg-border/80" />
            <div className="flex items-center gap-2">
              <div className="grid h-7 w-7 place-items-center rounded-lg bg-primary/10 text-primary">
                <Globe className="h-4 w-4" />
              </div>
              <div>
                <div className="text-[11px] font-medium text-foreground">Global coverage</div>
                <div className="text-[10px] text-muted-foreground">211 countries</div>
              </div>
            </div>
          </div>
        </div>

        {/* Master Search Bar & Filter */}
        <div className="space-y-3">
          <form
            onSubmit={handleSearchSubmit}
            className="flex items-center gap-3 rounded-2xl border border-border/80 bg-card/90 px-4 py-3 shadow-lg shadow-black/20 ring-1 ring-border/40 backdrop-blur-xl focus-within:border-primary/80 focus-within:ring-2 focus-within:ring-primary/20"
          >
            <Search className="h-5 w-5 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Ask a question about markets, assets, companies or economic data..."
              className="flex-1 bg-transparent text-[15px] text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
            <div className="flex items-center gap-2">
              <select
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value)}
                className="rounded-lg border border-border/80 bg-background/80 px-2.5 py-1.5 text-[12.5px] font-medium text-muted-foreground outline-none hover:text-foreground cursor-pointer"
              >
                <option value="All sources">All sources</option>
                <option value="UK DMO & Gilts">UK DMO & Gilts</option>
                <option value="Bank of England">Bank of England</option>
                <option value="Tradeweb">Tradeweb</option>
                <option value="Twelve Data">Twelve Data</option>
                <option value="DBnomics">DBnomics</option>
              </select>
              <button
                type="submit"
                aria-label="Search"
                className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-md transition-all hover:brightness-110 active:scale-95"
              >
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </form>

          {/* Quick Filter Pill Buttons */}
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            {quickPills.map((pill) => (
              <button
                key={pill}
                type="button"
                onClick={() => {
                  setSearchQuery(pill)
                  onSearch(pill)
                }}
                className="rounded-full border border-border/60 bg-card/50 px-3.5 py-1 text-muted-foreground backdrop-blur-sm transition-colors hover:border-primary/50 hover:bg-card hover:text-foreground"
              >
                {pill}
              </button>
            ))}
          </div>
        </div>

        {/* Ticker Row */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
          {tickers.map((t) => (
            <div
              key={t.title}
              className="group relative flex flex-col justify-between rounded-xl border border-border/70 bg-card/70 p-3.5 shadow-sm backdrop-blur-md transition-all hover:border-border hover:bg-card"
            >
              <div className="flex items-start justify-between">
                <span className="text-[12px] font-medium text-muted-foreground">{t.title}</span>
                <span
                  className={`flex items-center text-[11px] font-semibold ${
                    t.isUp ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {t.change}
                </span>
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-[17px] font-bold tracking-tight text-foreground">{t.value}</span>
                {/* SVG Sparkline */}
                <svg className="h-6 w-16 overflow-visible" viewBox="0 0 100 30" fill="none">
                  <path
                    d={t.sparkline}
                    stroke={t.isUp ? '#34d399' : '#f87171'}
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>
          ))}

          <button
            onClick={() => onSearch('Global market overview')}
            className="flex items-center justify-center gap-1.5 rounded-xl border border-dashed border-border/80 bg-card/30 p-3.5 text-[12.5px] font-medium text-primary transition-colors hover:border-primary/50 hover:bg-primary/5"
          >
            <span>View markets</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Main Grid: Hero Banner + Key Developments + Alerts & Economic Calendar */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          {/* Left Column: Hero Banner (Deeper insight. Stronger decisions.) */}
          <div className="relative flex flex-col justify-between overflow-hidden rounded-2xl border border-border/80 bg-black/60 p-7 shadow-xl lg:col-span-4 min-h-[340px]">
            {/* Background space image */}
            <img
              src={earthImg}
              alt="Global view"
              className="absolute inset-0 h-full w-full object-cover object-center opacity-65 transition-transform duration-700 hover:scale-105"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent" />

            <div className="relative z-10 space-y-2">
              <span className="inline-block text-[10px] font-bold uppercase tracking-widest text-primary-foreground/90">
                GLOBAL MARKETS
              </span>
              <h2 className="text-2xl font-bold leading-tight text-white sm:text-3xl">
                Deeper insight.<br />Stronger decisions.
              </h2>
              <p className="text-[13px] text-white/80">
                Authoritative data. Verifiable sources.<br />A clearer view of what's next.
              </p>
            </div>

            <div className="relative z-10 pt-6">
              <button
                onClick={onStartResearch}
                className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-[13px] font-semibold text-black shadow-lg transition-all hover:bg-white/90 active:scale-95"
              >
                <span>Start new research</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Center Column: Key market developments */}
          <div className="flex flex-col justify-between rounded-2xl border border-border/70 bg-card/70 p-5 backdrop-blur-md lg:col-span-5">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-border/50">
                <h3 className="text-[14px] font-semibold text-foreground">Key market developments</h3>
                <button
                  onClick={() => onSearch('Latest market developments')}
                  className="flex items-center gap-1 text-[11.5px] font-medium text-primary hover:underline"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              <div className="mt-3 divide-y divide-border/40">
                {keyDevelopments.map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => onSearch(item.title)}
                    className="group flex cursor-pointer items-start gap-3 py-2.5 transition-colors hover:bg-accent/30 rounded-lg px-1.5"
                  >
                    <span className="w-5 shrink-0 text-[11.5px] font-mono text-muted-foreground">{item.time}</span>
                    <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${item.dotColor}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium text-foreground group-hover:text-primary leading-snug">
                        {item.title}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {item.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-md bg-secondary/80 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Your Alerts & Economic Calendar */}
          <div className="space-y-4 lg:col-span-3">
            {/* Alerts Box */}
            <div className="rounded-2xl border border-border/70 bg-card/70 p-4 backdrop-blur-md">
              <div className="flex items-center justify-between pb-2 border-b border-border/50">
                <h3 className="text-[13px] font-semibold text-foreground">Your alerts</h3>
                <button
                  onClick={onOpenMonitoring}
                  className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              <div className="mt-2 space-y-2">
                {userAlerts.map((a, i) => (
                  <div
                    key={i}
                    onClick={onOpenMonitoring}
                    className="flex cursor-pointer items-center justify-between rounded-xl border border-border/40 bg-background/50 p-2.5 transition-all hover:border-primary/40 hover:bg-background"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${a.color}`} />
                      <Bell className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 truncate">
                        <div className="text-[12px] font-medium text-foreground truncate">{a.title}</div>
                        <div className="text-[10px] text-muted-foreground">{a.time}</div>
                      </div>
                    </div>
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </div>

            {/* Economic Calendar */}
            <div className="rounded-2xl border border-border/70 bg-card/70 p-4 backdrop-blur-md">
              <div className="flex items-center justify-between pb-2 border-b border-border/50">
                <h3 className="text-[13px] font-semibold text-foreground">Economic calendar (next 5)</h3>
                <button
                  onClick={() => onSearch('Economic calendar schedule')}
                  className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              <div className="mt-2 divide-y divide-border/40 text-[11.5px]">
                {economicCalendar.map((ec, i) => (
                  <div
                    key={i}
                    onClick={() => onSearch(`${ec.event} ${ec.code}`)}
                    className="flex cursor-pointer items-center justify-between py-2 transition-colors hover:text-primary"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-muted-foreground">{ec.date}</span>
                      <span className="font-mono text-muted-foreground">{ec.time}</span>
                      <span className="text-[12px]">{ec.flag}</span>
                      <span className="font-semibold text-foreground">{ec.code}</span>
                      <span className="text-muted-foreground truncate max-w-[110px]">{ec.event}</span>
                    </div>
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom 3-Card Row: Continue Research + Saved Watchlists + The Talvrin Difference */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          {/* Continue your research */}
          <div className="rounded-2xl border border-border/70 bg-card/70 p-5 backdrop-blur-md lg:col-span-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/50">
              <h3 className="text-[14px] font-semibold text-foreground">Continue your research</h3>
              <button
                onClick={onStartResearch}
                className="flex items-center gap-1 text-[11.5px] font-medium text-primary hover:underline"
              >
                View all <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            <div className="mt-3 space-y-2">
              {recentResearch.map((item, idx) => (
                <div
                  key={idx}
                  onClick={() => onSearch(item.title)}
                  className="flex cursor-pointer items-center justify-between rounded-xl border border-border/40 bg-background/50 p-2.5 transition-all hover:border-primary/40 hover:bg-background"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <item.icon className="h-4 w-4 shrink-0 text-primary" />
                    <div className="min-w-0">
                      <div className="text-[12.5px] font-medium text-foreground truncate">{item.title}</div>
                      <div className="text-[10.5px] text-muted-foreground">{item.time}</div>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>
              ))}
            </div>
          </div>

          {/* Saved watchlists */}
          <div className="rounded-2xl border border-border/70 bg-card/70 p-5 backdrop-blur-md lg:col-span-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/50">
              <h3 className="text-[14px] font-semibold text-foreground">Saved watchlists</h3>
              <button
                onClick={() => onSearch('Watchlists and market portfolios')}
                className="flex items-center gap-1 text-[11.5px] font-medium text-primary hover:underline"
              >
                View all <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            <div className="mt-3 space-y-2">
              {savedWatchlists.map((w, idx) => (
                <div
                  key={idx}
                  onClick={() => onSearch(w.title)}
                  className="flex cursor-pointer items-center justify-between rounded-xl border border-border/40 bg-background/50 p-2.5 transition-all hover:border-primary/40 hover:bg-background"
                >
                  <div className="flex items-center gap-3">
                    <w.icon className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <div className="text-[12.5px] font-medium text-foreground">{w.title}</div>
                      <div className="text-[10.5px] text-muted-foreground">{w.detail}</div>
                    </div>
                  </div>
                  <span
                    className={`text-[12px] font-semibold ${
                      w.isUp ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {w.change}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* The Talvrin Difference Banner */}
          <div className="relative flex flex-col justify-between overflow-hidden rounded-2xl border border-primary/40 bg-gradient-to-br from-indigo-950/80 via-purple-950/40 to-black p-5 shadow-xl backdrop-blur-xl lg:col-span-4">
            <div>
              <span className="text-[10.5px] font-bold uppercase tracking-wider text-primary">
                THE TALVRIN DIFFERENCE
              </span>
              <h3 className="mt-1 text-xl font-bold text-white">Every answer has a source.</h3>
              <p className="mt-1 text-[12.5px] text-white/70">
                Explore the evidence behind the numbers.
              </p>

              {/* Stack diagram */}
              <div className="mt-4 flex flex-col items-center justify-center py-2">
                <div className="relative flex w-full max-w-[210px] flex-col items-center gap-1.5 text-[11px] font-medium text-white/90">
                  <div className="w-full rounded-md border border-indigo-400/30 bg-indigo-600/40 py-1.5 text-center shadow">
                    Answer
                  </div>
                  <div className="w-[85%] rounded-md border border-indigo-500/30 bg-indigo-700/40 py-1.5 text-center shadow">
                    Analysis
                  </div>
                  <div className="w-[70%] rounded-md border border-indigo-600/30 bg-indigo-800/40 py-1.5 text-center shadow">
                    Data
                  </div>
                  <div className="w-[55%] rounded-md border border-indigo-700/30 bg-indigo-900/40 py-1.5 text-center shadow">
                    Source
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-3">
              <button
                onClick={onStartResearch}
                className="inline-flex items-center gap-2 rounded-xl bg-white px-3.5 py-2 text-[12px] font-semibold text-black shadow transition-all hover:bg-white/90 active:scale-95"
              >
                <span>Learn more</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-col items-center justify-between gap-3 border-t border-border/50 pt-5 text-[11px] text-muted-foreground sm:flex-row pb-6">
          <div>© 2026 Talvrin. All rights reserved.</div>
          <div className="flex items-center gap-4">
            <span className="hover:text-foreground cursor-pointer">Terms</span>
            <span className="hover:text-foreground cursor-pointer">Privacy</span>
            <span className="hover:text-foreground cursor-pointer">Cookies</span>
            <span className="hover:text-foreground cursor-pointer">Disclaimers</span>
            <span className="hover:text-foreground cursor-pointer">Contact</span>
          </div>
        </div>
      </div>
    </div>
  )
}
