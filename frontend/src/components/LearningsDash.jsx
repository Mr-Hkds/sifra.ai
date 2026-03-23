import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { BrainCircuit, Database, GitMerge, RefreshCw } from 'lucide-react';
import { fetchLearnings as apiFetchLearnings } from '../utils/api';

export default function LearningsDash() {
  const [data, setData] = useState({ stats: null, learnings: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLearnings = async () => {
    try {
      setLoading(true);
      const json = await apiFetchLearnings();
      
      setData({
        stats: json.stats,
        learnings: json.learnings || []
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLearnings();
  }, []);

  if (loading && !data.stats) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center">
        <div className="w-5 h-5 rounded-full bg-[var(--color-accent-green)] animate-ping" />
        <div className="text-[10px] text-[var(--color-text-muted)] mt-4 tracking-widest uppercase">
          Synthesizing Neural Patterns...
        </div>
      </div>
    );
  }

  const { stats, learnings } = data;

  return (
    <div className="flex-1 max-w-[1400px] mx-auto w-full flex flex-col gap-6 py-8 px-6 overflow-y-auto">
      
      {/* Header & Controls */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-wide text-[var(--color-text-primary)]">
            Observation Learning Center
          </h2>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
            Analyzing behavioral patterns from @irarumikbot via Telegram group shadowing.
          </p>
        </div>
        
        <button 
          onClick={fetchLearnings}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-md hover:border-[var(--color-accent-green)] transition-all text-sm group"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : "group-hover:text-[var(--color-accent-green)] transition-colors"} />
          <span>Sync Core</span>
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-900/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
          Neural Sync Error: {error}
        </div>
      )}

      {/* Stats Grid */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard 
            icon={<Database size={16} />}
            label="Total Observations"
            value={stats.total_observations}
            color="var(--color-accent-blue)"
          />
          <StatCard 
            icon={<BrainCircuit size={16} />}
            label="Patterns Analyzed"
            value={stats.analyzed}
            color="var(--color-accent-purple)"
          />
          <StatCard 
            icon={<RefreshCw size={16} />}
            label="Pending Batch"
            value={stats.pending}
            color="var(--color-accent-yellow)"
          />
          <StatCard 
            icon={<GitMerge size={16} />}
            label="Learned Behaviors"
            value={stats.learnings_count}
            color="var(--color-accent-green)"
          />
        </div>
      )}

      {/* Learnings Table */}
      <div className="flex-1 flex flex-col bg-[var(--color-bg-card)] border border-[var(--color-border-subtle)] rounded-xl overflow-hidden mt-4">
        <div className="px-5 py-4 border-b border-[var(--color-border-subtle)] bg-[var(--color-bg-primary)]/50">
          <h3 className="text-sm font-semibold tracking-wider text-[var(--color-text-secondary)]">SYNTHESIZED PATTERNS (LAYER 7 PROMPT INJECTION)</h3>
        </div>
        
        <div className="flex-1 overflow-y-auto p-0">
          {learnings.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12 text-[var(--color-text-muted)]">
              <Database size={32} className="opacity-20 mb-4" />
              <p>No patterns learned yet. Waiting for enough observations to trigger batch analysis.</p>
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-[var(--color-bg-card)] border-b border-[var(--color-border-subtle)]">
                <tr>
                  <th className="px-5 py-3 text-[10px] tracking-widest text-[var(--color-text-muted)] font-medium uppercase">Category</th>
                  <th className="px-5 py-3 text-[10px] tracking-widest text-[var(--color-text-muted)] font-medium uppercase">Pattern / Rule</th>
                  <th className="px-5 py-3 text-[10px] tracking-widest text-[var(--color-text-muted)] font-medium uppercase">Confidence</th>
                  <th className="px-5 py-3 text-[10px] tracking-widest text-[var(--color-text-muted)] font-medium uppercase">Examples</th>
                </tr>
              </thead>
              <tbody>
                {learnings.map((l, i) => (
                  <motion.tr 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    key={l.id} 
                    className="border-b border-[var(--color-border-subtle)]/50 hover:bg-[var(--color-bg-primary)]/30 transition-colors"
                  >
                    <td className="px-5 py-3 text-sm font-medium text-[var(--color-accent-blue)]">
                      {l.category}
                    </td>
                    <td className="px-5 py-3 text-sm text-[var(--color-text-primary)] relative group">
                      <span className="line-clamp-2">{l.pattern}</span>
                      {/* Tooltip for full text */}
                      <div className="hidden group-hover:block absolute z-10 left-0 bottom-full mb-2 w-[400px] p-3 bg-[#111] border border-[var(--color-border)] rounded shadow-2xl text-xs leading-relaxed whitespace-pre-wrap">
                        {l.pattern}
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-[var(--color-bg-primary)] rounded-full overflow-hidden">
                          <div 
                            className="h-full rounded-full transition-all" 
                            style={{ 
                              width: `${l.confidence * 100}%`,
                              backgroundColor: l.confidence > 0.8 ? 'var(--color-accent-green)' : 'var(--color-accent-yellow)'
                            }} 
                          />
                        </div>
                        <span className="text-xs text-[var(--color-text-muted)]">{(l.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-sm text-[var(--color-text-secondary)] relative group">
                      <span className="line-clamp-2 italic opacity-80">{l.examples || "No explicit examples"}</span>
                      {l.examples && (
                        <div className="hidden group-hover:block absolute z-10 right-0 bottom-full mb-2 w-[400px] p-3 bg-[#111] border border-[var(--color-border)] rounded shadow-2xl text-xs leading-relaxed whitespace-pre-wrap">
                          {l.examples}
                        </div>
                      )}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, color }) {
  return (
    <div className="flex items-center gap-4 bg-[var(--color-bg-card)] border border-[var(--color-border-subtle)] p-4 rounded-xl">
      <div 
        className="flex items-center justify-center p-2.5 rounded-lg bg-opacity-10"
        style={{ color: color, backgroundColor: `${color}20` }}
      >
        {icon}
      </div>
      <div>
        <div className="text-[20px] font-bold text-[var(--color-text-primary)] leading-none mb-1">
          {value}
        </div>
        <div className="text-[10px] text-[var(--color-text-muted)] tracking-widest uppercase">
          {label}
        </div>
      </div>
    </div>
  );
}
