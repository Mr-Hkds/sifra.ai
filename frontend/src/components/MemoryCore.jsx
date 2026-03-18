import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, Database, X } from 'lucide-react';

/**
 * MemoryCore — left column panel.
 * Terminal-style memory cards with category badges, decay indicators.
 */

const CATEGORIES = ['all', 'core', 'emotional', 'habit', 'preference', 'event'];

function DecayText({ score }) {
  return (
    <span className="text-[10px] text-[var(--color-text-muted)] font-mono tracking-wider">
      DECAY: {(score || 0).toFixed(2)}
    </span>
  );
}

function MemoryCard({ memory, onDelete }) {
  const { content, category, importance, decay_score, times_referenced } = memory;
  const decayOpacity = Math.max(0.3, decay_score || 1.0);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: decayOpacity, y: 0 }}
      exit={{ opacity: 0, x: -20, scale: 0.95 }}
      transition={{ duration: 0.3 }}
      className="group bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-lg p-3 hover:border-[var(--color-border-subtle)] hover:bg-[var(--color-bg-card-hover)] transition-all duration-200"
    >
      {/* Top row: category + importance */}
      <div className="flex items-center justify-between mb-2">
        <span className={`badge badge-${category || 'event'}`}>{category}</span>
        <div className="flex items-center gap-2">
          <div className="flex gap-[2px]">
            {Array.from({ length: 10 }, (_, i) => (
              <div
                key={i}
                className="w-1 h-2 rounded-sm"
                style={{
                  backgroundColor: i < (importance || 5) ? '#00ff9d' : '#222',
                }}
              />
            ))}
          </div>
          <button
            onClick={() => onDelete(memory.id)}
            className="opacity-0 group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-accent-pink)] transition-all duration-200 active:scale-90"
            aria-label="Delete memory"
          >
            <Trash2 size={11} />
          </button>
        </div>
      </div>

      {/* Content */}
      <p className="text-[12px] text-[var(--color-text-primary)] leading-relaxed mb-2">
        {content}
      </p>

      {/* Bottom: decay + refs */}
      <div className="flex items-center justify-between mt-1 pt-2 border-t border-[var(--color-border-subtle)]">
        <DecayText score={decay_score} />
        <span className="text-[10px] text-[var(--color-text-muted)] font-mono tracking-wider">
          REF: {times_referenced || 0}
        </span>
      </div>
    </motion.div>
  );
}

function AddMemoryModal({ onClose, onAdd }) {
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('core');
  const [importance, setImportance] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    try {
      await onAdd(content.trim(), category, importance);
      onClose();
    } catch {
      setSubmitting(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl p-5 w-full max-w-md"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[var(--color-accent-green)]">
            // add_memory
          </h3>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] active:scale-90">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[11px] text-[var(--color-text-muted)] mb-1 uppercase tracking-wider">Content</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-[12px] text-[var(--color-text-primary)] focus:border-[var(--color-accent-green)] focus:ring-1 focus:ring-[var(--color-accent-green-glow)] outline-none resize-none h-20"
              placeholder="What should Sifra remember?"
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-[11px] text-[var(--color-text-muted)] mb-1 uppercase tracking-wider">Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-[12px] text-[var(--color-text-primary)] focus:border-[var(--color-accent-green)] outline-none"
              >
                {['core', 'emotional', 'habit', 'preference', 'event'].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <div className="w-24">
              <label className="block text-[11px] text-[var(--color-text-muted)] mb-1 uppercase tracking-wider">Weight</label>
              <input
                type="number"
                min={1}
                max={10}
                value={importance}
                onChange={(e) => setImportance(Number(e.target.value))}
                className="w-full bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-[12px] text-[var(--color-text-primary)] focus:border-[var(--color-accent-green)] outline-none"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={!content.trim() || submitting}
            className="w-full bg-[var(--color-accent-green)]/10 text-[var(--color-accent-green)] border border-[var(--color-accent-green)]/30 rounded-lg px-4 py-2.5 text-[12px] font-semibold hover:bg-[var(--color-accent-green)]/20 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 tracking-wider uppercase"
          >
            {submitting ? 'Storing...' : 'Store Memory'}
          </button>
        </form>
      </motion.div>
    </motion.div>
  );
}

export default function MemoryCore({ memories, onAdd, onDelete }) {
  const [activeFilter, setActiveFilter] = useState('all');
  const [showModal, setShowModal] = useState(false);

  const filtered = activeFilter === 'all'
    ? memories
    : memories.filter(m => m.category === activeFilter);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <Database size={13} className="text-[var(--color-accent-green)]" />
          <h2 className="text-[12px] font-semibold text-[var(--color-text-secondary)] tracking-wider">
            // memory.mesh
          </h2>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1 text-[10px] text-[var(--color-accent-green)] hover:text-[var(--color-accent-green-dim)] active:scale-95 transition-all duration-200 tracking-wider uppercase font-semibold"
        >
          <Plus size={12} />
          add
        </button>
      </div>

      {/* Category filters */}
      <div className="flex gap-1 px-4 py-2 border-b border-[var(--color-border)] overflow-x-auto">
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => setActiveFilter(cat)}
            className={`px-2 py-0.5 rounded text-[10px] font-semibold tracking-wide uppercase transition-all duration-200 active:scale-95 ${
              activeFilter === cat
                ? 'bg-[var(--color-accent-green)]/15 text-[var(--color-accent-green)]'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Memory list */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        <AnimatePresence mode="popLayout">
          {filtered.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center h-32 text-[var(--color-text-muted)]"
            >
              <Database size={20} className="mb-2 opacity-40" />
              <span className="text-[11px]">No memories found</span>
            </motion.div>
          ) : (
            filtered.map(memory => (
              <MemoryCard
                key={memory.id}
                memory={memory}
                onDelete={onDelete}
              />
            ))
          )}
        </AnimatePresence>
      </div>

      {/* Add Memory Modal */}
      <AnimatePresence>
        {showModal && (
          <AddMemoryModal onClose={() => setShowModal(false)} onAdd={onAdd} />
        )}
      </AnimatePresence>
    </div>
  );
}
