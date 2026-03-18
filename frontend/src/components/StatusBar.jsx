import React from 'react';
import { motion } from 'framer-motion';
import { Cpu, MessageSquare, Database, Clock } from 'lucide-react';

/**
 * StatusBar — bottom status bar with system stats.
 * Memory count | Conversations today | Uptime | System status
 */
export default function StatusBar({ memoryCount, conversationCount, state }) {
  const isOnline = !!state.last_active;

  return (
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-bg-primary)] px-5 py-2">
      <div className="flex items-center justify-between">
        {/* Left stats */}
        <div className="flex items-center gap-5">
          <StatusItem
            icon={<Database size={10} />}
            label="memories"
            value={memoryCount}
          />
          <StatusItem
            icon={<MessageSquare size={10} />}
            label="messages"
            value={conversationCount}
          />
          <StatusItem
            icon={<Clock size={10} />}
            label="mode"
            value={state.personality_mode || 'normal'}
          />
        </div>

        {/* Right status */}
        <div className="flex items-center gap-2">
          <motion.div
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: isOnline ? '#00ff9d' : '#ff3c78' }}
          />
          <span className="text-[10px] text-[var(--color-text-muted)] tracking-widest uppercase">
            {isOnline ? 'system operational' : 'offline'}
          </span>
          <Cpu size={10} className="text-[var(--color-text-muted)] ml-1" />
        </div>
      </div>
    </footer>
  );
}

function StatusItem({ icon, label, value }) {
  return (
    <div className="flex items-center gap-1.5 text-[10px]">
      <span className="text-[var(--color-text-muted)]">{icon}</span>
      <span className="text-[var(--color-text-muted)] tracking-wide">{label}:</span>
      <span className="text-[var(--color-text-secondary)] font-semibold">{value}</span>
    </div>
  );
}
