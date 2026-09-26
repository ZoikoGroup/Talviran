import { useEffect, useState } from 'react'
import {
  ShieldCheck,
  Link2,
  FileText,
  BookOpen,
  Table2,
  ChevronDown,
  Info,
  Loader2,
  Download,
  BarChart3,
  PieChart as PieChartIcon,
  LineChart as LineChartIcon,
  Activity,
  Target,
} from 'lucide-react'
import { ResponsiveContainer, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { cn } from '@/lib/utils'
import { getResearchEvidence, type EvidenceItem } from '@/lib/api'
import brandIcon from '@/assets/brand/talvrin-icon.svg'
import type {
  ChatMessage,
  Citation,
  FactTable,
  Freshness,
} from '@/data/mockReply'

const CITE_ICON = { doc: FileText, book: BookOpen, link: Link2 } as const

const PILL_STYLE: Record<Freshness, string> = {
  CURRENT: 'bg-fresh/15 text-fresh',
  DELAYED: 'bg-delayed/15 text-delayed',
  STALE: 'bg-stale/15 text-stale',
  UNAVAILABLE: 'bg-unavailable/15 text-unavailable',
  SOURCE: 'bg-secondary text-muted-foreground',
}

/** Render **bold** spans without pulling in a markdown dependency. */
function RichText({ children }: { children: string }) {
  return (
    <>
      {children.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
        p.startsWith('**') && p.endsWith('**') ? (
          <strong key={i} className="font-semibold">
            {p.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </>
  )
}

function Facts({ title, rows }: FactTable) {
  const isChartable =
    rows.length >= 3 &&
    rows.every(([_, v]) => !isNaN(parseFloat(v.replace(/[%$,]/g, ''))))

  const [view, setView] = useState<'table' | 'chart'>(isChartable ? 'chart' : 'table')
  const [chartType, setChartType] = useState<'area' | 'bar' | 'pie' | 'line' | 'radar'>('area')

  const handleDownloadCSV = () => {
    const csvContent = rows.map(([k, v]) => `"${k}","${v}"`).join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `${title.replace(/\s+/g, '_').toLowerCase()}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const chartData = isChartable
    ? rows.map(([k, v]) => ({
        name: k,
        value: parseFloat(v.replace(/[%$,]/g, '')),
      }))
    : []

  const minValue = isChartable ? Math.min(...chartData.map(d => d.value)) : 0
  const maxValue = isChartable ? Math.max(...chartData.map(d => d.value)) : 0
  const avgValue = isChartable ? (chartData.reduce((a, b) => a + b.value, 0) / chartData.length).toFixed(4) : 0

  const COLORS = ['hsl(var(--primary))', '#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#a4de6c', '#d0ed57', '#83a6ed']

  return (
    <div className="mt-3.5 overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border bg-secondary/60 px-3.5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <div className="flex items-center gap-2 flex-1">
          {view === 'table' ? <Table2 className="h-3.5 w-3.5" /> : <BarChart3 className="h-3.5 w-3.5" />}
          {title}
        </div>
        
        <div className="flex items-center gap-2">
          {isChartable && view === 'chart' && (
            <div className="flex items-center gap-1 mr-2 border-r border-border pr-2">
              <button onClick={() => setChartType('area')} className={cn("p-1 rounded transition-colors", chartType === 'area' ? "bg-primary/20 text-primary" : "hover:bg-secondary")} title="Area Chart">
                <LineChartIcon className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('line')} className={cn("p-1 rounded transition-colors", chartType === 'line' ? "bg-primary/20 text-primary" : "hover:bg-secondary")} title="Line Chart">
                <Activity className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('bar')} className={cn("p-1 rounded transition-colors", chartType === 'bar' ? "bg-primary/20 text-primary" : "hover:bg-secondary")} title="Bar Chart">
                <BarChart3 className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('pie')} className={cn("p-1 rounded transition-colors", chartType === 'pie' ? "bg-primary/20 text-primary" : "hover:bg-secondary")} title="Pie Chart">
                <PieChartIcon className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('radar')} className={cn("p-1 rounded transition-colors", chartType === 'radar' ? "bg-primary/20 text-primary" : "hover:bg-secondary")} title="Radar Chart">
                <Target className="h-3 w-3" />
              </button>
            </div>
          )}
          {isChartable && (
            <button
              onClick={() => setView(v => v === 'table' ? 'chart' : 'table')}
              className="flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-semibold transition-colors hover:bg-secondary hover:text-foreground"
            >
              {view === 'table' ? 'View Chart' : 'View Table'}
            </button>
          )}
          <button
            onClick={handleDownloadCSV}
            className="flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-semibold transition-colors hover:bg-secondary hover:text-foreground"
            title="Download CSV"
          >
            <Download className="h-3 w-3" />
            CSV
          </button>
        </div>
      </div>
      
      {view === 'table' ? (
        <div className="flex flex-col">
          {rows.map(([k, v]) => (
            <div
              key={k}
              className="flex items-baseline gap-3 border-b border-border px-3.5 py-2.5 text-[13.5px] last:border-b-0"
            >
              <span className="basis-[42%] text-muted-foreground">{k}</span>
              <span className="font-mono text-[13px] font-medium">{v}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col w-full bg-card/40">
          <div className="grid grid-cols-3 gap-3 p-4 pb-0">
            <div className="bg-secondary/50 rounded-lg p-3 border border-border/60 shadow-sm">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Minimum</div>
              <div className="text-xl text-primary font-mono font-bold mt-0.5">{minValue}</div>
            </div>
            <div className="bg-secondary/50 rounded-lg p-3 border border-border/60 shadow-sm">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Maximum</div>
              <div className="text-xl text-primary font-mono font-bold mt-0.5">{maxValue}</div>
            </div>
            <div className="bg-secondary/50 rounded-lg p-3 border border-border/60 shadow-sm">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Average</div>
              <div className="text-xl text-primary font-mono font-bold mt-0.5">{avgValue}</div>
            </div>
          </div>
          <div className="h-64 w-full p-4 pt-6">
            <ResponsiveContainer width="100%" height="100%">
              {chartType === 'area' ? (
                <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dy={10} />
                  <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dx={-10} />
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} />
                  <Area type="monotone" dataKey="value" stroke="hsl(var(--primary))" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" />
                </AreaChart>
              ) : chartType === 'bar' ? (
                <BarChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dy={10} />
                  <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dx={-10} />
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} cursor={{ fill: 'hsl(var(--secondary))' }} />
                  <Bar dataKey="value" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} barSize={30} />
                </BarChart>
              ) : chartType === 'line' ? (
                <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dy={10} />
                  <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dx={-10} />
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} />
                  <Line type="monotone" dataKey="value" stroke="hsl(var(--primary))" strokeWidth={3} dot={{ fill: 'hsl(var(--primary))', r: 4, strokeWidth: 2, stroke: 'hsl(var(--background))' }} activeDot={{ r: 6 }} />
                </LineChart>
              ) : chartType === 'radar' ? (
                <RadarChart cx="50%" cy="50%" outerRadius="80%" data={chartData}>
                  <PolarGrid stroke="hsl(var(--border))" />
                  <PolarAngleAxis dataKey="name" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} />
                  <PolarRadiusAxis angle={30} domain={['auto', 'auto']} tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 10 }} />
                  <Radar name="Value" dataKey="value" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.4} />
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} />
                </RadarChart>
              ) : (
                <PieChart margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                  <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={85} paddingAngle={2} label={({ name, percent }) => `${name} (${((percent || 0) * 100).toFixed(0)}%)`} labelLine={false}>
                    {chartData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} />
                </PieChart>
              )}
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}

/** The resolved fact/calculation behind a citation - fetched on demand from
 * GET /research/{id}/evidence, not embedded in the reply itself (that
 * endpoint didn't exist when the citation list was first built). Only
 * fetched once, the first time the panel opens, for a message that came
 * from the real backend (mock replies have no messageId to fetch with). */
function RawEvidence({ messageId }: { messageId: string }) {
  const [state, setState] = useState<
    { status: 'loading' } | { status: 'error' } | { status: 'ready'; items: EvidenceItem[] }
  >({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    getResearchEvidence(messageId)
      .then((detail) => {
        if (!cancelled) setState({ status: 'ready', items: detail.items })
      })
      .catch((err: unknown) => {
        // A message with no evidence bundle at all (e.g. an advice-redirect
        // reply) never renders this component in the first place - Evidence
        // only mounts once citations.length > 0 - so any failure here is a
        // genuine fetch problem, not the normal "nothing to show" case.
        if (!cancelled) {
          console.error('Failed to load evidence detail', err)
          setState({ status: 'error' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [messageId])

  if (state.status === 'loading') {
    return (
      <div className="flex items-center gap-2 border-t border-border px-3.5 py-2.5 text-[12px] text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading resolved evidence…
      </div>
    )
  }

  if (state.status === 'error' || state.items.length === 0) {
    return null
  }

  return (
    <div className="border-t border-border bg-secondary/30 px-3.5 py-2.5">
      <div className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground/70">
        Resolved values
      </div>
      <div className="flex flex-col gap-1.5">
        {state.items.map((item, i) => (
          <div key={i} className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
            <span className="font-mono text-muted-foreground">{item.metricId ?? item.kind}</span>
            {item.basis === 'MODEL_IMPLIED' && (
              <span className="rounded bg-secondary px-1 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-muted-foreground">
                estimate
              </span>
            )}
            {item.asOf && <span className="text-muted-foreground/60">as of {item.asOf}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

function Evidence({
  citations,
  messageId,
}: {
  citations: Citation[]
  messageId?: string
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-3.5 overflow-hidden rounded-xl border border-border bg-card">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-[11.5px] font-semibold text-muted-foreground transition-colors hover:bg-secondary/60"
      >
        <ShieldCheck className="h-3.5 w-3.5" />
        Evidence
        <span className="ml-auto flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground/70">
          {citations.length} source{citations.length === 1 ? '' : 's'}
          <ChevronDown
            className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')}
          />
        </span>
      </button>

      {open && (
        <div className="border-t border-border">
          {citations.map((c, i) => {
            const Ico = CITE_ICON[c.kind] ?? Link2
            return (
              <div
                key={i}
                className="flex items-center gap-2.5 border-b border-border px-3.5 py-2.5 text-[13px] last:border-b-0"
              >
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-primary/15 text-primary">
                  <Ico className="h-3.5 w-3.5" />
                </span>
                <span className="min-w-0 flex-1">
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noreferrer" className="block truncate font-medium text-indigo-400 hover:underline">
                      {c.label}
                    </a>
                  ) : (
                    <span className="block truncate">{c.label}</span>
                  )}
                  {c.meta && (
                    <span className="mt-0.5 block text-[11.5px] text-muted-foreground/70">
                      {c.meta}
                    </span>
                  )}
                </span>
                <span
                  className={cn(
                    'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider',
                    PILL_STYLE[c.pill]
                  )}
                >
                  {c.pill}
                </span>
              </div>
            )
          })}
          {messageId && <RawEvidence messageId={messageId} />}
        </div>
      )}
    </div>
  )
}

export default function Message({
  role,
  text,
  model,
  facts,
  citations = [],
  note,
  messageId,
}: ChatMessage) {
  let displayContent = text
  let parsedFacts = facts
  let parsedCitations = citations || []

  if (displayContent) {
    const metaMatch = displayContent.match(/<!--METADATA\n([\s\S]*?)\n-->/)
    if (metaMatch) {
      try {
        const meta = JSON.parse(metaMatch[1])
        if (meta.facts && !parsedFacts) parsedFacts = meta.facts
        if (meta.citations && parsedCitations.length === 0) parsedCitations = meta.citations
        displayContent = displayContent.replace(/<!--METADATA\n[\s\S]*?\n-->/, '').trim()
      } catch (e) {
        console.error("Failed to parse metadata", e)
      }
    }
  }

  if (role === 'user') {
    return (
      <div className="mb-6 flex animate-rise justify-end">
        <div className="max-w-[78%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm border border-border bg-secondary px-4 py-2.5 text-[14.75px] leading-relaxed">
          {displayContent}
        </div>
      </div>
    )
  }

  return (
    <div className="mb-7 flex animate-rise gap-3.5">
      <img
        src={brandIcon}
        alt=""
        className="h-7 w-7 shrink-0 rounded-lg shadow-lg shadow-indigo-500/25"
      />

      <div className="min-w-0 flex-1 pt-0.5">
        <div className="mb-1.5 flex items-baseline gap-2 text-[13px] font-semibold">
          Talvrin
          {model && (
            <span className="font-normal text-[11.5px] text-muted-foreground">
              {model}
            </span>
          )}
        </div>
        <div className="whitespace-pre-wrap break-words text-[14.75px] leading-relaxed">
          <RichText>{displayContent}</RichText>
        </div>

        {parsedCitations.length > 0 && <Evidence citations={parsedCitations} messageId={messageId} />}
        {parsedFacts && <Facts {...parsedFacts} />}

        {note && (
          <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-primary/25 bg-primary/10 px-3 py-2.5 text-[12.25px] leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
            <span>{note}</span>
          </div>
        )}
      </div>
    </div>
  )
}
