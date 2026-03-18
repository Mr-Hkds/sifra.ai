import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Terminal, User, Bot } from 'lucide-react';

/**
 * LiveFeed — center column terminal-style conversation log.
 * Shows user messages in white, Sifra messages in green.
 */
export default function LiveFeed({ conversations }) {
  const scrollRef = useRef(null);

  // Auto-scroll to bottom when new messages come in
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [conversations]);

  function formatTimestamp(ts) {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch {
      return '';
    }
  }

  function formatDate(ts) {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
    } catch {
      return '';
    }
  }

  // Group messages by date
  const grouped = [];
  let currentDate = '';
  for (const msg of conversations) {
    const date = formatDate(msg.timestamp);
    if (date !== currentDate) {
      grouped.push({ type: 'date', date });
      currentDate = date;
    }
    grouped.push({ type: 'message', ...msg });
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border)]">
        <Terminal size={13} className="text-[var(--color-accent-green)]" />
        <h2 className="text-[12px] font-semibold text-[var(--color-text-secondary)] tracking-wider">
          // activity.log
        </h2>
        <span className="text-[9px] text-[var(--color-text-muted)] ml-auto tracking-wide">
          {conversations.length} messages
        </span>
      </div>

      {/* Message stream */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        {grouped.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-[var(--color-text-muted)]">
            <Terminal size={20} className="mb-2 opacity-40" />
            <span className="text-[11px]">No activity yet</span>
          </div>
        ) : (
          grouped.map((item, i) => {
            if (item.type === 'date') {
              return (
                <div key={`date-${i}`} className="flex items-center gap-2 py-2">
                  <div className="flex-1 h-px bg-[var(--color-border)]" />
                  <span className="text-[9px] text-[var(--color-text-muted)] tracking-wider uppercase">
                    {item.date}
                  </span>
                  <div className="flex-1 h-px bg-[var(--color-border)]" />
                </div>
              );
            }

            const isUser = item.role === 'user';
            const isSifra = item.role === 'sifra';

            return (
              <motion.div
                key={item.id || `msg-${i}`}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
                className="group flex gap-2 py-1.5 px-2 rounded hover:bg-[var(--color-bg-card)] transition-colors duration-150"
              >
                {/* Timestamp gutter */}
                <span className="text-[9px] text-[var(--color-text-muted)] w-10 shrink-0 pt-0.5 font-mono">
                  {formatTimestamp(item.timestamp)}
                </span>

                {/* Role indicator */}
                <span className="shrink-0 pt-0.5">
                  {isUser ? (
                    <User size={11} className="text-[var(--color-text-secondary)]" />
                  ) : (
                    <Bot size={11} className="text-[var(--color-accent-green)]" />
                  )}
                </span>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <p
                    className={`text-[12px] leading-relaxed break-words ${
                      isUser
                        ? 'text-[var(--color-text-primary)]'
                        : 'text-[var(--color-accent-green)]'
                    }`}
                  >
                    {item.content}
                  </p>

                  {/* Mood tag for Sifra messages */}
                  {isSifra && item.mood_detected && (
                    <span className="inline-block mt-1 text-[8px] text-[var(--color-text-muted)] bg-[var(--color-bg-primary)] px-1.5 py-0.5 rounded tracking-wider uppercase">
                      mood: {item.mood_detected}
                    </span>
                  )}
                </div>
              </motion.div>
            );
          })
        )}
      </div>

      {/* Input area indicator */}
      <div className="px-4 py-2 border-t border-[var(--color-border)]">
        <div className="flex items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
          <span className="text-[var(--color-accent-green)] animate-pulse-green">▋</span>
          <span className="tracking-wide">listening on telegram...</span>
        </div>
      </div>
    </div>
  );
}
