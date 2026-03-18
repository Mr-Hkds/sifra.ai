import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { Eye, TrendingUp, Code } from 'lucide-react';
import { fetchMoodHistory } from '../utils/api';

/**
 * SignalAnalysis — right column panel.
 * Shows live context JSON, mood graph (7 days), personality mode history.
 */

const MOOD_COLORS = {
  happy: '#00ff9d',
  neutral: '#888888',
  stressed: '#ff3c78',
  sad: '#3b82f6',
  bored: '#ffd60a',
  excited: '#a855f7',
  tired: '#ff3c78',
  anxious: '#ffd60a',
  angry: '#ff3c78',
  curious: '#3b82f6',
  playful: '#a855f7',
  frustrated: '#ff3c78',
};

function ContextDisplay({ state }) {
  const contextObj = {
    mood: state.current_mood || 'neutral',
    energy: state.energy_level || 7,
    mode: state.personality_mode || 'normal',
    active_mem: (state.active_memories || []).length,
    last_active: state.last_active ? new Date(state.last_active).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : 'unknown',
  };

  const jsonStr = JSON.stringify(contextObj, null, 2);
  const lines = jsonStr.split('\n');

  return (
    <div className="bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg p-3">
      <div className="text-[10px] text-[var(--color-text-muted)] tracking-wider uppercase mb-2">
        live context
      </div>
      <pre className="text-[11px] leading-loose">
        {lines.map((line, i) => (
          <div key={i} className="flex">
            <span className="line-number">{i + 1}</span>
            <span className="ml-2">
              {line.split('').map((char, j) => {
                if (char === '"') return <span key={j} className="text-[var(--color-text-muted)]">{char}</span>;
                if (char === ':') return <span key={j} className="text-[var(--color-accent-pink)]">{char}</span>;
                if (char === '{' || char === '}') return <span key={j} className="text-[var(--color-accent-yellow)]">{char}</span>;
                if (/[0-9]/.test(char)) return <span key={j} className="text-[var(--color-accent-green)]">{char}</span>;
                return <span key={j} className="text-[var(--color-text-secondary)]">{char}</span>;
              })}
            </span>
          </div>
        ))}
      </pre>
    </div>
  );
}

function MoodGraph({ data }) {
  // Transform data for recharts
  const chartData = data.map(day => {
    const total = Object.values(day.moods).reduce((a, b) => a + b, 0);
    const dominant = Object.entries(day.moods).sort((a, b) => b[1] - a[1])[0];
    return {
      date: day.date.slice(5), // MM-DD
      total,
      dominant: dominant ? dominant[0] : 'neutral',
      ...day.moods,
    };
  });

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-[var(--color-text-muted)] text-[11px]">
        No mood data yet
      </div>
    );
  }

  // Get unique moods across all days
  const allMoods = [...new Set(data.flatMap(d => Object.keys(d.moods)))];

  return (
    <div className="h-36">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
          <defs>
            {allMoods.map(mood => (
              <linearGradient key={mood} id={`grad-${mood}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={MOOD_COLORS[mood] || '#888'} stopOpacity={0.3} />
                <stop offset="95%" stopColor={MOOD_COLORS[mood] || '#888'} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: '#555' }}
            axisLine={{ stroke: '#222' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 9, fill: '#555' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: '#111',
              border: '1px solid #222',
              borderRadius: '6px',
              fontSize: '10px',
              color: '#e0e0e0',
            }}
          />
          {allMoods.map(mood => (
            <Area
              key={mood}
              type="monotone"
              dataKey={mood}
              stroke={MOOD_COLORS[mood] || '#888'}
              fill={`url(#grad-${mood})`}
              strokeWidth={1.5}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function PersonalityHistory({ state }) {
  const modes = [
    { mode: 'normal', desc: 'Balanced, everyday Sifra', color: '#00ff9d' },
    { mode: 'late_night', desc: 'Quiet, introspective', color: '#3b82f6' },
    { mode: 'grind', desc: 'Focused, sharp', color: '#ffd60a' },
    { mode: 'playful', desc: 'Teasing, light', color: '#a855f7' },
    { mode: 'quiet', desc: 'Gentle, present', color: '#ff3c78' },
  ];

  return (
    <div className="space-y-1.5">
      {modes.map(({ mode, desc, color }) => (
        <div
          key={mode}
          className={`flex items-center gap-2 px-2 py-1.5 rounded text-[11px] transition-all duration-200 ${
            state.personality_mode === mode
              ? 'bg-[var(--color-bg-card)]  border border-[var(--color-border)]'
              : ''
          }`}
        >
          <div
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{
              backgroundColor: state.personality_mode === mode ? color : '#333',
              boxShadow: state.personality_mode === mode ? `0 0 6px ${color}40` : 'none',
            }}
          />
          <span
            className="font-semibold tracking-wide"
            style={{ color: state.personality_mode === mode ? color : '#555' }}
          >
            {mode}
          </span>
          <span className="text-[9px] text-[var(--color-text-muted)] ml-auto hidden xl:block">
            {desc}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function SignalAnalysis({ state }) {
  const [moodHistory, setMoodHistory] = useState([]);
  const [loadingMood, setLoadingMood] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchMoodHistory();
        setMoodHistory(data);
      } catch {
        // silent fail
      } finally {
        setLoadingMood(false);
      }
    }
    load();
    const interval = setInterval(load, 60000); // refresh every minute
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border)]">
        <Eye size={13} className="text-[var(--color-accent-green)]" />
        <h2 className="text-[12px] font-semibold text-[var(--color-text-secondary)] tracking-wider">
          // peek.signals
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
        {/* Live context JSON */}
        <ContextDisplay state={state} />

        {/* Mood graph */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={12} className="text-[var(--color-accent-pink)]" />
            <span className="text-[10px] text-[var(--color-text-muted)] tracking-wider uppercase">
              mood · 7 days
            </span>
          </div>
          {loadingMood ? (
            <div className="h-36 flex items-center justify-center">
              <span className="text-[11px] text-[var(--color-text-muted)] animate-pulse">Loading...</span>
            </div>
          ) : (
            <MoodGraph data={moodHistory} />
          )}
        </div>

        {/* Personality modes */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Code size={12} className="text-[var(--color-accent-purple)]" />
            <span className="text-[10px] text-[var(--color-text-muted)] tracking-wider uppercase">
              personality modes
            </span>
          </div>
          <PersonalityHistory state={state} />
        </div>
      </div>
    </div>
  );
}
