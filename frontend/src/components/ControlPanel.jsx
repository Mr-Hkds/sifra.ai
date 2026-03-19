import React, { useState, useCallback } from 'react';
import { resetMemories, resetConversations, factoryReset } from '../utils/api';

/**
 * ControlPanel — Compact reset controls for the dashboard sidebar.
 * Inline confirmation → execute → feedback. No modals.
 */
export default function ControlPanel({ onResetComplete }) {
  const [status, setStatus] = useState(null);
  const [confirming, setConfirming] = useState(null);
  const [processing, setProcessing] = useState(false);

  const execute = useCallback(async (type) => {
    setProcessing(true);
    setStatus(null);
    try {
      let result;
      if (type === 'memories') {
        result = await resetMemories();
        setStatus({ ok: true, msg: `${result.memories_cleared} memories cleared` });
      } else if (type === 'conversations') {
        result = await resetConversations();
        setStatus({ ok: true, msg: `${result.conversations_cleared} conversations cleared` });
      } else {
        result = await factoryReset();
        setStatus({ ok: true, msg: `Reset done — ${result.memories_cleared} mem, ${result.conversations_cleared} conv` });
      }
      if (onResetComplete) onResetComplete();
    } catch (err) {
      setStatus({ ok: false, msg: err.message || 'Failed' });
    } finally {
      setProcessing(false);
      setConfirming(null);
    }
  }, [onResetComplete]);

  const handleClick = useCallback((type) => {
    if (confirming === type) {
      execute(type);
    } else {
      setConfirming(type);
      setStatus(null);
    }
  }, [confirming, execute]);

  const cancel = useCallback(() => {
    setConfirming(null);
    setStatus(null);
  }, []);

  const ACTIONS = [
    { key: 'memories', label: 'Memories', icon: '◈' },
    { key: 'conversations', label: 'Chat Log', icon: '◇' },
    { key: 'full', label: 'Full Reset', icon: '⚠', danger: true },
  ];

  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <div className="h-px w-4 bg-red-500/50" />
        <span className="text-[9px] font-bold tracking-[0.2em] text-[var(--color-text-muted)] uppercase">
          Reset
        </span>
      </div>

      {/* Buttons Row */}
      <div className="flex gap-2">
        {ACTIONS.map(({ key, label, icon, danger }) => {
          const isConfirming = confirming === key;
          const isProcessing = processing && confirming === key;

          if (isProcessing) {
            return (
              <div
                key={key}
                className="flex-1 flex items-center justify-center py-2 rounded-md
                  border border-[var(--color-border)] bg-[var(--color-bg-primary)]"
              >
                <div className="w-3 h-3 border-2 border-[var(--color-accent-green)] border-t-transparent rounded-full animate-spin" />
              </div>
            );
          }

          if (isConfirming) {
            return (
              <div
                key={key}
                className="flex-1 flex items-center gap-1 animate-fade-in"
              >
                <button
                  onClick={() => execute(key)}
                  className="flex-1 py-2 rounded-md text-[10px] font-bold tracking-wider
                    bg-red-950/40 border border-red-700/40 text-red-400
                    hover:bg-red-900/50 active:scale-95 transition-all cursor-pointer"
                >
                  YES
                </button>
                <button
                  onClick={cancel}
                  className="flex-1 py-2 rounded-md text-[10px] font-bold tracking-wider
                    border border-[var(--color-border)] text-[var(--color-text-muted)]
                    hover:text-[var(--color-text-secondary)] active:scale-95 transition-all cursor-pointer"
                >
                  NO
                </button>
              </div>
            );
          }

          return (
            <button
              key={key}
              onClick={() => handleClick(key)}
              className={`
                flex-1 flex flex-col items-center gap-1 py-2.5 rounded-md
                border transition-all duration-200 cursor-pointer active:scale-95
                ${danger
                  ? 'border-red-900/30 text-red-400/70 hover:border-red-700/50 hover:bg-red-950/20 hover:text-red-400'
                  : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-text-muted)] hover:bg-[var(--color-bg-card-hover)] hover:text-[var(--color-text-secondary)]'
                }
              `}
            >
              <span className="text-sm">{icon}</span>
              <span className="text-[9px] font-semibold tracking-wider">{label}</span>
            </button>
          );
        })}
      </div>

      {/* Feedback */}
      {status && (
        <div
          className={`mt-2 text-[10px] font-mono px-2 py-1.5 rounded border animate-fade-in ${
            status.ok
              ? 'bg-emerald-950/30 border-emerald-800/30 text-emerald-400'
              : 'bg-red-950/30 border-red-800/30 text-red-400'
          }`}
        >
          {status.ok ? '✓' : '✗'} {status.msg}
        </div>
      )}
    </div>
  );
}
