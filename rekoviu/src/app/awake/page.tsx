'use client';

import { useEffect, useState, useCallback } from 'react';

// ── Types ──────────────────────────────────────────────────────────────────

interface PingTarget {
  total:    number;
  success:  number;
  fail:     number;
  last_ok:  string | null;
  last_err: string | null;
  last_ms:  number | null;
}

interface AwakeStats {
  uptime_seconds: number;
  uptime_human:   string;
  started_at:     string;
  total_packets:  number;
  supabase:       PingTarget;
  render:         PingTarget;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE    = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4040/api/v1';
const REPO_URL    = 'https://github.com/pheonix14/rekov';
const AUTHOR_URL  = 'https://github.com/pheonix14';
const REFRESH_MS  = 10_000;   // refresh stats every 10 s

// ── Helpers ───────────────────────────────────────────────────────────────────

function healthRate(t: PingTarget): number {
  if (t.total === 0) return 1;
  return t.success / t.total;
}

function formatTs(ts: string | null): string {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 19) + ' UTC';
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatBar({ value, max = 1, color }: { value: number; max?: number; color: string }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  return (
    <div className="relative h-2 w-full rounded-full bg-white/10 overflow-hidden">
      <div
        className="absolute inset-y-0 left-0 rounded-full transition-all duration-700"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

function PingCard({
  label,
  icon,
  data,
  accent,
}: {
  label:  string;
  icon:   string;
  data:   PingTarget;
  accent: string;
}) {
  const rate     = healthRate(data);
  const statusTx = rate >= 0.9 ? 'ONLINE' : rate >= 0.5 ? 'DEGRADED' : data.total === 0 ? 'WAITING' : 'FAILING';
  const statusCl = rate >= 0.9 ? 'text-emerald-400' : rate >= 0.5 ? 'text-yellow-400' : 'text-red-400';

  return (
    <div
      className="relative rounded-2xl p-6 border backdrop-blur-md overflow-hidden"
      style={{
        background:   `linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%)`,
        borderColor:  accent + '33',
        boxShadow:    `0 0 40px ${accent}18`,
      }}
    >
      {/* glow */}
      <div
        className="pointer-events-none absolute -top-8 -right-8 w-32 h-32 rounded-full blur-2xl opacity-20"
        style={{ background: accent }}
      />

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{icon}</span>
          <span className="text-lg font-bold tracking-wide text-white">{label}</span>
        </div>
        <span className={`text-xs font-bold tracking-widest uppercase px-2 py-1 rounded-full bg-white/10 ${statusCl}`}>
          {statusTx}
        </span>
      </div>

      <StatBar value={rate} color={accent} />

      <div className="mt-4 grid grid-cols-3 gap-3 text-center">
        {[
          { label: 'Total',  val: data.total },
          { label: 'OK',     val: data.success, cl: 'text-emerald-400' },
          { label: 'Fail',   val: data.fail,    cl: data.fail > 0 ? 'text-red-400' : 'text-white/40' },
        ].map(({ label: l, val, cl }) => (
          <div key={l} className="rounded-xl bg-white/5 p-3">
            <div className={`text-xl font-bold ${cl || 'text-white'}`}>{val}</div>
            <div className="text-xs text-white/40 mt-0.5">{l}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-1.5 text-xs text-white/50">
        {data.last_ms !== null && (
          <div>Last latency <span className="text-white/70">{data.last_ms} ms</span></div>
        )}
        {data.last_ok && (
          <div>Last OK <span className="text-emerald-400/80">{formatTs(data.last_ok)}</span></div>
        )}
        {data.last_err && (
          <div className="text-red-400/70 truncate" title={data.last_err}>
            {data.last_err.slice(0, 70)}
          </div>
        )}
      </div>
    </div>
  );
}


function MetricPill({
  label,
  value,
  sub,
  accent,
}: {
  label:  string;
  value:  string | number;
  sub?:   string;
  accent: string;
}) {
  return (
    <div
      className="flex flex-col items-center rounded-2xl px-6 py-4 border backdrop-blur-md"
      style={{
        background:  'rgba(255,255,255,0.04)',
        borderColor: accent + '33',
      }}
    >
      <div className="text-xs uppercase tracking-widest text-white/40 mb-1">{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-white/30 mt-0.5">{sub}</div>}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  Page
// ═══════════════════════════════════════════════════════════════════════════════

export default function AwakePage() {
  const [stats,   setStats]   = useState<AwakeStats | null>(null);
  const [error,   setError]   = useState<string>('');
  const [lastFetch, setLastFetch] = useState<string>('');
  const [pinging, setPinging] = useState(false);
  const [pingRes, setPingRes] = useState<string>('');

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/awake/stats`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AwakeStats = await res.json();
      setStats(data);
      setError('');
      setLastFetch(new Date().toLocaleTimeString());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const id = setInterval(fetchStats, REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchStats]);

  const handleManualPing = async () => {
    setPinging(true);
    setPingRes('');
    try {
      const res  = await fetch(`${API_BASE}/awake/ping`);
      const data = await res.json();
      const sb   = data.supabase?.ok ? `Supabase OK (${data.supabase.ms}ms)` : `Supabase FAIL`;
      const rd   = data.render?.ok   ? `Render OK (${data.render.ms}ms)`     : `Render FAIL`;
      setPingRes(`${sb}  ·  ${rd}`);
      fetchStats();
    } catch (e: unknown) {
      setPingRes(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPinging(false);
    }
  };

  return (
    <div
      className="min-h-screen text-white font-sans"
      style={{
        background: 'radial-gradient(ellipse at 20% 20%, #0f1a1a 0%, #050c0e 60%, #000 100%)',
        fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
      }}
    >
      {/* Google Font */}
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');`}</style>

      <div className="max-w-4xl mx-auto px-4 py-12">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="text-center mb-12">
          {/* ASCII logo area */}
          <div
            className="inline-block rounded-2xl px-8 py-5 mb-6 border"
            style={{
              background:  'rgba(20, 255, 200, 0.04)',
              borderColor: '#14ffca33',
              fontFamily:  'monospace',
            }}
          >
            <pre className="text-xs leading-tight" style={{ color: '#14ffca' }}>
{` █████╗ ██╗    ██╗ █████╗ ██╗  ██╗███████╗
██╔══██╗██║    ██║██╔══██╗██║ ██╔╝██╔════╝
███████║██║ █╗ ██║███████║█████╔╝ █████╗
██╔══██║██║███╗██║██╔══██║██╔═██╗ ██╔══╝
██║  ██║╚███╔███╔╝██║  ██║██║  ██╗███████╗
╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝`}
            </pre>
          </div>

          <h1 className="text-3xl font-extrabold tracking-tight mb-2">
            <span style={{ color: '#14ffca' }}>Awake</span>
            <span className="text-white/60 font-normal text-xl ml-3">Keep-Alive Monitor</span>
          </h1>
          <p className="text-white/40 text-sm max-w-md mx-auto">
            Keeps Supabase active and Render from sleeping.
            Sends keep-alive packets every 5 minutes, automatically.
          </p>

          {/* Credits */}
          <div className="mt-4 flex items-center justify-center gap-3 text-xs text-white/30">
            <span>Awake System by</span>
            <a
              href={AUTHOR_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold hover:text-white transition-colors"
              style={{ color: '#14ffca' }}
            >
              ★ pheonix14
            </a>
            <span>·</span>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-white transition-colors underline underline-offset-2"
            >
              github.com/pheonix14/rekov
            </a>
          </div>
        </div>

        {/* ── Error banner ───────────────────────────────────────────── */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-3 text-sm text-red-400">
            Backend unreachable — {error}
            <span className="text-white/30 ml-2">(retrying every 10s)</span>
          </div>
        )}

        {/* ── Top metric pills ────────────────────────────────────────── */}
        {stats && (
          <div className="grid grid-cols-3 gap-4 mb-8">
            <MetricPill
              label="Uptime"
              value={stats.uptime_human}
              sub={`since ${stats.started_at.slice(0, 10)}`}
              accent="#14ffca"
            />
            <MetricPill
              label="Total Packets"
              value={stats.total_packets}
              sub="pings sent"
              accent="#7c3aed"
            />
            <MetricPill
              label="Last Refresh"
              value={lastFetch || '—'}
              sub="auto every 10s"
              accent="#f59e0b"
            />
          </div>
        )}

        {/* ── Loading skeleton ────────────────────────────────────────── */}
        {!stats && !error && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            {[0, 1].map(i => (
              <div key={i} className="h-56 rounded-2xl bg-white/5 animate-pulse" />
            ))}
          </div>
        )}

        {/* ── Ping cards ──────────────────────────────────────────────── */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <PingCard
              label="Supabase"
              icon="🟢"
              data={stats.supabase}
              accent="#3ecf8e"
            />
            <PingCard
              label="Render"
              icon="🟣"
              data={stats.render}
              accent="#7c3aed"
            />
          </div>
        )}

        {/* ── Manual ping button ──────────────────────────────────────── */}
        <div className="flex flex-col items-center gap-3 mb-10">
          <button
            onClick={handleManualPing}
            disabled={pinging}
            className="group relative px-8 py-3 rounded-xl font-semibold text-sm tracking-wide transition-all duration-200 disabled:opacity-50"
            style={{
              background:  'linear-gradient(135deg, #14ffca22, #7c3aed22)',
              border:      '1px solid #14ffca44',
              color:       '#14ffca',
            }}
          >
            {pinging ? (
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
                Pinging...
              </span>
            ) : (
              'Send Manual Ping'
            )}
          </button>
          {pingRes && (
            <p className="text-xs text-white/50 text-center max-w-xs">{pingRes}</p>
          )}
        </div>

        {/* ── About / Repo section ────────────────────────────────────── */}
        <div
          className="rounded-2xl p-6 border mb-8"
          style={{
            background:  'rgba(255,255,255,0.03)',
            borderColor: '#14ffca22',
          }}
        >
          <h2 className="text-sm font-bold uppercase tracking-widest text-white/50 mb-4">
            About REKOV Awake System
          </h2>
          <div className="space-y-2 text-sm text-white/50 leading-relaxed">
            <p>
              The <span className="text-white/80">REKOV Awake System</span> prevents free-tier
              infrastructure from entering idle/sleep/paused states.
            </p>
            <p>
              <span className="text-emerald-400/80">Supabase</span> free projects pause after ~1 week of
              inactivity. REKOV Awake pings the REST API every 5 minutes to keep the project active.
            </p>
            <p>
              <span style={{ color: '#7c3aed' }}>Render</span> free dynos sleep after 15 minutes of
              inactivity. REKOV Awake pings the health endpoint every 5 minutes to keep the dyno warm.
            </p>
            <p>
              Both loops run as daemon threads inside the REKOV backend — zero extra processes needed.
            </p>
          </div>

          <div className="mt-5 pt-5 border-t border-white/10 flex flex-wrap gap-4 items-center">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg transition-all hover:opacity-80"
              style={{ background: '#14ffca18', color: '#14ffca', border: '1px solid #14ffca33' }}
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              pheonix14/rekov
            </a>
            <span className="text-white/20 text-xs">·</span>
            <span className="text-white/30 text-xs">
              Awake System v1.0.0  ·  by{' '}
              <a href={AUTHOR_URL} target="_blank" rel="noopener noreferrer"
                 className="text-white/50 hover:text-white transition-colors">pheonix14</a>
            </span>
          </div>
        </div>

        {/* ── Footer watermark ────────────────────────────────────────── */}
        <footer className="text-center text-xs text-white/20 pb-4">
          <span className="font-bold" style={{ color: '#14ffca66' }}>REKOV</span>
          {' '}· Awake System ·{' '}
          <a href={AUTHOR_URL} className="hover:text-white/40 transition-colors">pheonix14</a>
          {' '}·{' '}
          <a href={REPO_URL} className="hover:text-white/40 transition-colors">github.com/pheonix14/rekov</a>
        </footer>
      </div>
    </div>
  );
}
