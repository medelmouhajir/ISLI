import { useMemo } from 'react'
import { Calendar, dateFnsLocalizer, Views } from 'react-big-calendar'
import { format, parse, startOfWeek, getDay } from 'date-fns'
import { enUS } from 'date-fns/locale/en-US'
import 'react-big-calendar/lib/css/react-big-calendar.css'
import { useTasks } from '@/hooks/useTasks'
import { useNavigate } from 'react-router-dom'
import { Calendar as CalendarIcon } from 'lucide-react'

const locales = {
  'en-US': enUS,
}

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek,
  getDay,
  locales,
})

export function CalendarPage() {
  const { data: tasks = [] } = useTasks()
  const navigate = useNavigate()

  const events = useMemo(() => {
    return tasks.map((task) => {
      const start = new Date(task.scheduled_at || task.created_at)
      const end = new Date(start.getTime() + 60 * 60 * 1000)
      
      return {
        id: task.id,
        title: task.title,
        start,
        end,
        resource: task,
      }
    })
  }, [tasks])

  const eventPropGetter = (event: any) => {
    const task = event.resource
    let colorVar = '--accent-cyan'
    
    if (task.status === 'completed' || task.status === 'done') {
      colorVar = '--accent-green'
    } else if (task.status === 'in_progress' || task.status === 'doing') {
      colorVar = '--accent-amber'
    } else if (task.status === 'failed' || task.status === 'error') {
      colorVar = '--accent-red'
    }

    return {
      className: 'industrial-event',
      style: {
        '--event-color': `var(${colorVar})`,
        '--event-glow': `var(${colorVar.replace('--accent', '--glow')})`,
      } as React.CSSProperties,
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-bg-base font-mono-data min-w-0">
      <header className="px-6 py-4 border-b border-border-dim flex items-center justify-between bg-bg-surface/30 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 flex items-center justify-center border border-accent-cyan/30 bg-accent-cyan/5">
              <CalendarIcon className="w-5 h-5 text-accent-cyan" />
            </div>
            {/* Industrial corner accents */}
            <div className="absolute -top-px -left-px w-2 h-2 border-t border-l border-accent-cyan" />
            <div className="absolute -bottom-px -right-px w-2 h-2 border-b border-r border-accent-cyan" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold uppercase tracking-[0.2em] text-text-primary">Timeline.Matrix</h1>
              <span className="px-1.5 py-0.5 text-[9px] border border-border-bright text-text-muted font-bold tracking-tighter uppercase">Beta</span>
            </div>
            <p className="text-[10px] text-text-secondary uppercase tracking-widest mt-0.5">Scheduling Engine / Active Tasks</p>
          </div>
        </div>
      </header>

      <main className="flex-1 px-4 md:px-6 overflow-hidden">
        <div className="h-full flex flex-col">
          <Calendar
            localizer={localizer}
            events={events}
            startAccessor="start"
            endAccessor="end"
            views={['month', 'week', 'day']}
            defaultView={Views.MONTH}
            onSelectEvent={(event: any) => navigate(`/calendar?task=${event.id}`)}
            eventPropGetter={eventPropGetter}
            className="isli-industrial-calendar"
          />
        </div>
      </main>

      <style>{`
        .isli-industrial-calendar {
          height: 100%;
          color: var(--text-primary);
        }

        /* Toolbar / Navigation */
        .rbc-toolbar {
          margin-bottom: 2rem !important;
          flex-direction: row-reverse !important;
        }
        .rbc-toolbar-label {
          font-family: inherit !important;
          font-weight: 900 !important;
          font-size: 1.25rem !important;
          letter-spacing: -0.05em !important;
          text-transform: uppercase !important;
          text-align: left !important;
          flex-grow: 1 !important;
        }
        .rbc-btn-group {
          background: var(--bg-elevated) !important;
          padding: 2px !important;
          border: 1px solid var(--border-dim) !important;
        }
        .rbc-toolbar button {
          background: transparent !important;
          border: none !important;
          color: var(--text-secondary) !important;
          border-radius: 0 !important;
          font-size: 10px !important;
          font-weight: 800 !important;
          text-transform: uppercase !important;
          letter-spacing: 0.1em !important;
          padding: 8px 16px !important;
          transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }
        .rbc-toolbar button:hover {
          color: var(--text-primary) !important;
          background: var(--bg-surface) !important;
        }
        .rbc-toolbar button.rbc-active {
          background: var(--bg-surface) !important;
          color: var(--accent-cyan) !important;
          box-shadow: inset 0 -2px 0 var(--accent-cyan) !important;
        }

        /* Grid Structure */
        .rbc-month-view, .rbc-time-view {
          border: 1px solid var(--border-dim) !important;
          background: var(--bg-surface)/20 !important;
        }
        .rbc-month-row {
          border-top: 1px solid var(--border-dim) !important;
        }
        .rbc-day-bg + .rbc-day-bg {
          border-left: 1px solid var(--border-dim) !important;
        }
        .rbc-header {
          padding: 16px !important;
          border-bottom: 2px solid var(--border-bright) !important;
          font-size: 9px !important;
          font-weight: 900 !important;
          text-transform: uppercase !important;
          letter-spacing: 0.2em !important;
          color: var(--text-muted) !important;
        }
        .rbc-off-range-bg {
          background: repeating-linear-gradient(
            45deg,
            transparent,
            transparent 10px,
            rgba(0,0,0,0.05) 10px,
            rgba(0,0,0,0.05) 20px
          ) !important;
        }
        .rbc-today {
          background: var(--bg-elevated) !important;
        }
        .rbc-today::after {
          content: 'CURRENT_PERIOD';
          position: absolute;
          top: 8px;
          right: 8px;
          font-size: 7px;
          font-weight: 900;
          color: var(--accent-cyan);
          letter-spacing: 0.1em;
          opacity: 0.5;
        }

        /* Day Cells */
        .rbc-date-cell {
          padding: 8px !important;
          font-size: 10px !important;
          font-weight: 900 !important;
          color: var(--text-secondary) !important;
        }
        .rbc-now.rbc-date-cell {
          color: var(--accent-cyan) !important;
        }

        /* Events */
        .industrial-event {
          background: var(--bg-surface) !important;
          border: 1px solid var(--border-dim) !important;
          border-left: 3px solid var(--event-color) !important;
          border-radius: 0 !important;
          padding: 4px 8px !important;
          margin: 1px 4px !important;
          box-shadow: 2px 2px 0 rgba(0,0,0,0.1) !important;
        }
        .industrial-event:hover {
          border-color: var(--border-bright) !important;
          transform: translateY(-1px) !important;
          box-shadow: 4px 4px 0 rgba(0,0,0,0.15) !important;
          z-index: 10 !important;
        }
        .rbc-event-label {
          display: none !important;
        }
        .rbc-event-content {
          font-size: 9px !important;
          font-weight: 700 !important;
          text-transform: uppercase !important;
          letter-spacing: 0.05em !important;
          color: var(--text-primary) !important;
          white-space: nowrap !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
        }

        /* Time View Specifics */
        .rbc-time-header-content {
          border-left: 1px solid var(--border-dim) !important;
        }
        .rbc-timeslot-group {
          border-bottom: 1px solid var(--border-dim) !important;
          min-height: 60px !important;
        }
        .rbc-time-axis-cell {
          font-size: 9px !important;
          font-weight: 700 !important;
          color: var(--text-muted) !important;
          padding: 8px !important;
        }

        /* Custom "Reticle" Decoration for Day Cells */
        .rbc-day-bg {
          position: relative;
        }
        .rbc-day-bg::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          width: 4px;
          height: 4px;
          border-top: 1px solid var(--border-dim);
          border-left: 1px solid var(--border-dim);
        }
      `}</style>
    </div>
  )
}
