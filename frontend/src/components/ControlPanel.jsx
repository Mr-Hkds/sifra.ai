import React, { useState, useCallback } from 'react';
import { resetMemories, resetConversations, factoryReset } from '../utils/api';

/**
 * ControlPanel — Factory reset controls for Sifra.
 * Premium danger-zone panel with confirmation states.
 */
export default function ControlPanel({ onResetComplete }) {
  const [status, setStatus] = useState(null); // { type: 'success'|'error', msg: string }
  const [confirming, setConfirming] = useState(null); // 'memories' | 'conversations' | 'full'
  const [processing, setProcessing] = useState(false);

  const handleAction = useCallback(async (type) => {
    if (confirming !== type) {
      setConfirming(type);
      setStatus(null);
      return;
    }

    setProcessing(true);
    setStatus(null);

    try {
      let result;
      if (type === 'memories') {
        result = await resetMemories();
        setStatus({ type: 'success', msg: `Cleared ${result.memories_cleared} memories` });
      } else if (type === 'conversations') {
        result = await resetConversations();
        setStatus({ type: 'success', msg: `Cleared ${result.conversations_cleared} conversations` });
      } else {
        result = await factoryReset();
        setStatus({
          type: 'success',
          msg: `Factory reset — ${result.memories_cleared} memories, ${result.conversations_cleared} conversations cleared`,
        });
      }
      if (onResetComplete) onResetComplete();
    } catch (err) {
      setStatus({ type: 'error', msg: err.message || 'Reset failed' });
    } finally {
      setProcessing(false);
      setConfirming(null);
    }
  }, [confirming, onResetComplete]);

  const cancel = useCallback(() => {
    setConfirming(null);
    setStatus(null);
  }, []);

  return (
    <div className="p-5 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="h-px w-6 bg-red-500/60" />
        <span className="text-[10px] font-semibold tracking-[0.15em] text-[var(--color-text-muted)] uppercase">
          System Controls
        </span>
      </div>

      {/* Buttons */}
      <div className="flex flex-col gap-2">
        <ResetButton
          label="Clear Memories"
          description="Wipe all stored memories"
          isConfirming={confirming === 'memories'}
          isProcessing={processing && confirming === 'memories'}
          onClick={() => handleAction('memories')}
          onCancel={cancel}
        />
        <ResetButton
          label="Clear Chat History"
          description="Wipe all conversation logs"
          isConfirming={confirming === 'conversations'}
          isProcessing={processing && confirming === 'conversations'}
          onClick={() => handleAction('conversations')}
          onCancel={cancel}
        />
        <ResetButton
          label="Factory Reset"
          description="Wipe everything, start fresh"
          isDanger
          isConfirming={confirming === 'full'}
          isProcessing={processing && confirming === 'full'}
          onClick={() => handleAction('full')}
          onCancel={cancel}
        />
      </div>

      {/* Status feedback */}
      {status && (
        <div
          className={`text-[11px] font-mono px-3 py-2 rounded-md border animate-fade-in ${
            status.type === 'success'
              ? 'bg-emerald-950/30 border-emerald-800/30 text-emerald-400'
              : 'bg-red-950/30 border-red-800/30 text-red-400'
          }`}
        >
          {status.type === 'success' ? '✓' : '✗'} {status.msg}
        </div>
      )}
    </div>
  );
}

function ResetButton({ label, description, isDanger, isConfirming, isProcessing, onClick, onCancel }) {
  if (isProcessing) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-[var(--color-bg-card)] border border-[var(--color-border)]">
        <div className="w-3 h-3 border-2 border-[var(--color-accent-green)] border-t-transparent rounded-full animate-spin" />
        <span className="text-xs text-[var(--color-text-secondary)]">Processing...</span>
      </div>
    );
  }

  if (isConfirming) {
    return (
      <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-950/20 border border-red-800/30 animate-fade-in">
        <span className="text-xs text-red-400 flex-1">
          {isDanger ? '⚠ This is irreversible. Confirm?' : 'Are you sure?'}
        </span>
        <button
          onClick={onClick}
          className="text-[10px] font-bold tracking-wider text-red-400 bg-red-950/50 hover:bg-red-900/60
            px-3 py-1.5 rounded border border-red-700/40 hover:border-red-600
            active:scale-95 transition-all duration-200 cursor-pointer"
        >
          YES
        </button>
        <button
          onClick={onCancel}
          className="text-[10px] font-bold tracking-wider text-[var(--color-text-muted)]
            hover:text-[var(--color-text-secondary)] px-3 py-1.5 rounded border border-[var(--color-border)]
            hover:border-[var(--color-text-muted)]
            active:scale-95 transition-all duration-200 cursor-pointer"
        >
          NO
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={onClick}
      className={`
        group flex items-center justify-between px-4 py-3 rounded-lg
        border transition-all duration-200 cursor-pointer active:scale-[0.98]
        ${isDanger
          ? 'border-red-900/30 hover:border-red-700/50 hover:bg-red-950/20'
          : 'border-[var(--color-border)] hover:border-[var(--color-text-muted)] hover:bg-[var(--color-bg-card-hover)]'
        }
      `}
    >
      <div className="flex flex-col items-start gap-0.5">
        <span className={`text-xs font-semibold tracking-wide ${isDanger ? 'text-red-400/80' : 'text-[var(--color-text-secondary)]'}`}>
          {label}
        </span>
        <span className="text-[10px] text-[var(--color-text-muted)]">{description}</span>
      </div>
      <span
        className={`text-[10px] opacity-0 group-hover:opacity-100 transition-opacity ${
          isDanger ? 'text-red-500/60' : 'text-[var(--color-text-muted)]'
        }`}
      >
        →
      </span>
    </button>
  );
}
