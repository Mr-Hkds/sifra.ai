import React from 'react';
import { motion } from 'framer-motion';
import { Brain, Zap, Clock, Activity } from 'lucide-react';
import { Brain, Zap, Clock, Activity } from 'lucide-react';

/**
 * NeuralHeader — the top bar of SIFRA:MIND
 * Shows logo, mood pill, energy bar, personality mode, last active, EKG line
 */
export default function NeuralHeader({ state }) {
  const {
    current_mood = 'neutral',
    energy_level = 7,
    personality_mode = 'normal',
    last_active = null,
  } = state;

  const moodColors = {
    neutral: 'bg-[var(--color-accent-green)]/15 text-[var(--color-accent-green)]',
    cheerful: 'bg-[var(--color-accent-green)]/15 text-[var(--color-accent-green)]',
    energetic: 'bg-[var(--color-accent-yellow)]/15 text-[var(--color-accent-yellow)]',
    empathetic: 'bg-[var(--color-accent-pink)]/15 text-[var(--color-accent-pink)]',
    concerned: 'bg-[var(--color-accent-pink)]/15 text-[var(--color-accent-pink)]',
    playful: 'bg-[var(--color-accent-purple)]/15 text-[var(--color-accent-purple)]',
    chill: 'bg-[var(--color-accent-green)]/15 text-[var(--color-accent-green)]',
    introspective: 'bg-[var(--color-accent-blue)]/15 text-[var(--color-accent-blue)]',
  };

  const moodColor = moodColors[current_mood] || moodColors.neutral;

  function formatLastActive(ts) {
    if (!ts) return 'unknown';
    try {
      const d = new Date(ts);
      const now = new Date();
      const diffMs = now - d;
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1) return 'just now';
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHr = Math.floor(diffMin / 60);
      if (diffHr < 24) return `${diffHr}h ago`;
      return `${Math.floor(diffHr / 24)}d ago`;
    } catch {
      return 'unknown';
    }
  }

  return (
    <header className="border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]">
      {/* Header content */}
      <div className="flex items-center justify-between px-5 py-3">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <motion.div
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
            className="text-[var(--color-accent-green)]"
          >
            <Brain size={20} />
          </motion.div>
          <h1 className="text-base font-bold tracking-wider">
            <span className="text-[var(--color-accent-green)]">SIFRA</span>
            <span className="text-[var(--color-text-muted)]">:</span>
            <span className="text-[var(--color-text-primary)]">MIND</span>
          </h1>
          <span className="text-[10px] text-[var(--color-text-muted)] tracking-widest uppercase mt-0.5">
            v1.0
          </span>
        </div>

        {/* Status indicators */}
        <div className="flex items-center gap-4">
          {/* Mood pill */}
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-wide uppercase ${moodColor}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse-green" />
            {current_mood}
          </div>

          {/* Energy bar */}
          <div className="flex items-center gap-2">
            <Zap size={13} className="text-[var(--color-accent-yellow)]" />
            <div className="flex gap-[2px]">
              {Array.from({ length: 10 }, (_, i) => (
                <div
                  key={i}
                  className="w-[3px] h-3 rounded-sm transition-all duration-300"
                  style={{
                    backgroundColor: i < energy_level ? '#ff6a00' : '#222',
                  }}
                />
              ))}
            </div>
            <span className="text-[10px] text-[var(--color-text-muted)]">{energy_level}/10</span>
          </div>

          {/* Personality mode */}
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-secondary)]">
            <Activity size={12} />
            <span className="tracking-wide">{personality_mode}</span>
          </div>

          {/* Last active */}
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
            <Clock size={12} />
            <span>{formatLastActive(last_active)}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
