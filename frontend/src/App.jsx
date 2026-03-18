import React from 'react';
import NeuralHeader from './components/NeuralHeader';
import MemoryCore from './components/MemoryCore';
import LiveFeed from './components/LiveFeed';
import SignalAnalysis from './components/SignalAnalysis';
import StatusBar from './components/StatusBar';
import { useSifraState } from './hooks/useSifraState';
import { useMemories } from './hooks/useMemories';
import { useConversations } from './hooks/useConversations';

/**
 * App — Main SIFRA:MIND dashboard layout.
 * Three zones: Neural Header → Three-column grid → Status Bar
 */
export default function App() {
  const { state, loading: stateLoading } = useSifraState();
  const { memories, addMemory, removeMemory, loading: memLoading } = useMemories();
  const { conversations, loading: convLoading } = useConversations();

  // Show minimal loading state
  if (stateLoading && memLoading && convLoading) {
    return (
      <div className="h-screen flex flex-col items-center justify-center bg-[var(--color-bg-primary)]">
        <div className="text-[var(--color-accent-green)] text-sm font-semibold tracking-widest animate-pulse-green">
          SIFRA:MIND
        </div>
        <div className="text-[10px] text-[var(--color-text-muted)] mt-2 tracking-wider">
          initializing neural mesh...
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[var(--color-bg-primary)]">
      {/* ZONE 1 — Neural Header */}
      <NeuralHeader state={state} />

      {/* ZONE 2 — Spatial Three Column Grid */}
      <main className="flex-1 max-w-[1400px] mx-auto w-full grid grid-cols-1 lg:grid-cols-[300px_1fr_300px] gap-8 py-8 px-6 overflow-hidden">
        {/* Left — Memory Core */}
        <div className="overflow-hidden flex flex-col bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border-subtle)]">
          <MemoryCore
            memories={memories}
            onAdd={addMemory}
            onDelete={removeMemory}
          />
        </div>

        {/* Center — Live Feed */}
        <div className="overflow-hidden flex flex-col bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border-subtle)] shadow-2xl">
          <LiveFeed conversations={conversations} />
        </div>

        {/* Right — Signal Analysis */}
        <div className="overflow-hidden flex flex-col bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border-subtle)]">
          <SignalAnalysis state={state} />
        </div>
      </main>

      {/* ZONE 3 — Status Bar */}
      <StatusBar
        memoryCount={memories.length}
        conversationCount={conversations.length}
        state={state}
      />
    </div>
  );
}
