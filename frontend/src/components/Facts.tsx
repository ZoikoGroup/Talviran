import { useState } from 'react'
import { toast } from 'sonner'
import {
  Table2,
  Download,
  BarChart3,
  PieChart as PieChartIcon,
  LineChart as LineChartIcon,
  Activity,
  Target,
} from 'lucide-react'
import { ResponsiveContainer, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { cn } from '@/lib/utils'
import type { FactTable } from '@/data/mockReply'

export default function Facts({ title, rows }: FactTable) {
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
    toast.success('CSV downloaded successfully')
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
    <div className="mt-3.5 animate-rise overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all hover:shadow-md">
      <div className="flex items-center gap-2 border-b border-border bg-secondary/60 px-3.5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <div className="flex flex-1 items-center gap-2">
          {view === 'table' ? <Table2 className="h-3.5 w-3.5" /> : <BarChart3 className="h-3.5 w-3.5" />}
          {title}
        </div>
        
        <div className="flex items-center gap-2">
          {isChartable && view === 'chart' && (
            <div className="mr-2 flex items-center gap-1 border-r border-border pr-2">
              <button onClick={() => setChartType('area')} className={cn("rounded p-1 transition-all duration-200", chartType === 'area' ? "bg-primary/20 text-primary scale-110" : "hover:bg-secondary hover:text-foreground hover:scale-105")} title="Area Chart">
                <LineChartIcon className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('line')} className={cn("rounded p-1 transition-all duration-200", chartType === 'line' ? "bg-primary/20 text-primary scale-110" : "hover:bg-secondary hover:text-foreground hover:scale-105")} title="Line Chart">
                <Activity className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('bar')} className={cn("rounded p-1 transition-all duration-200", chartType === 'bar' ? "bg-primary/20 text-primary scale-110" : "hover:bg-secondary hover:text-foreground hover:scale-105")} title="Bar Chart">
                <BarChart3 className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('pie')} className={cn("rounded p-1 transition-all duration-200", chartType === 'pie' ? "bg-primary/20 text-primary scale-110" : "hover:bg-secondary hover:text-foreground hover:scale-105")} title="Pie Chart">
                <PieChartIcon className="h-3 w-3" />
              </button>
              <button onClick={() => setChartType('radar')} className={cn("rounded p-1 transition-all duration-200", chartType === 'radar' ? "bg-primary/20 text-primary scale-110" : "hover:bg-secondary hover:text-foreground hover:scale-105")} title="Radar Chart">
                <Target className="h-3 w-3" />
              </button>
            </div>
          )}
          {isChartable && (
            <button
              onClick={() => setView(v => v === 'table' ? 'chart' : 'table')}
              className="flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-semibold transition-all duration-200 hover:bg-secondary hover:text-foreground active:scale-95"
            >
              {view === 'table' ? 'View Chart' : 'View Table'}
            </button>
          )}
          <button
            onClick={handleDownloadCSV}
            className="flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-semibold transition-all duration-200 hover:bg-secondary hover:text-foreground active:scale-95"
            title="Download CSV"
          >
            <Download className="h-3 w-3" />
            CSV
          </button>
        </div>
      </div>
      
      <div className="relative transition-all duration-500 ease-in-out">
        {view === 'table' ? (
          <div className="flex animate-in fade-in slide-in-from-bottom-2 flex-col">
            {rows.map(([k, v], i) => (
              <div
                key={k}
                className="group flex items-baseline gap-3 border-b border-border px-3.5 py-2.5 text-[13.5px] transition-colors hover:bg-secondary/30 last:border-b-0"
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <span className="basis-[42%] text-muted-foreground transition-colors group-hover:text-foreground">{k}</span>
                <span className="font-mono text-[13px] font-medium">{v}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex w-full animate-in fade-in zoom-in-95 flex-col bg-card/40">
            <div className="grid grid-cols-3 gap-3 p-4 pb-0">
              <div className="rounded-lg border border-border/60 bg-secondary/50 p-3 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Minimum</div>
                <div className="mt-0.5 font-mono text-xl font-bold text-primary">{minValue}</div>
              </div>
              <div className="rounded-lg border border-border/60 bg-secondary/50 p-3 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Maximum</div>
                <div className="mt-0.5 font-mono text-xl font-bold text-primary">{maxValue}</div>
              </div>
              <div className="rounded-lg border border-border/60 bg-secondary/50 p-3 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Average</div>
                <div className="mt-0.5 font-mono text-xl font-bold text-primary">{avgValue}</div>
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
                    <Tooltip cursor={{ stroke: 'hsl(var(--primary))', strokeWidth: 1, strokeDasharray: '4 4' }} contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} />
                    <Area type="monotone" dataKey="value" stroke="hsl(var(--primary))" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" activeDot={{ r: 6, className: 'animate-pulse' }} />
                  </AreaChart>
                ) : chartType === 'bar' ? (
                  <BarChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dy={10} />
                    <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dx={-10} />
                    <Tooltip cursor={{ fill: 'hsl(var(--secondary))', opacity: 0.5 }} contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} />
                    <Bar dataKey="value" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} barSize={30} className="transition-all duration-300 hover:opacity-80" />
                  </BarChart>
                ) : chartType === 'line' ? (
                  <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dy={10} />
                    <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} dx={-10} />
                    <Tooltip cursor={{ stroke: 'hsl(var(--border))' }} contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', fontSize: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }} itemStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }} />
                    <Line type="monotone" dataKey="value" stroke="hsl(var(--primary))" strokeWidth={3} dot={{ fill: 'hsl(var(--primary))', r: 4, strokeWidth: 2, stroke: 'hsl(var(--background))' }} activeDot={{ r: 7, strokeWidth: 0 }} />
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
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} className="transition-all duration-300 hover:opacity-80 outline-none" />
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
    </div>
  )
}
