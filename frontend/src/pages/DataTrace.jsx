import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';

export default function DataTrace() {
  const [origin, setOrigin] = useState('synthetic');
  const [eventId, setEventId] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  async function refresh() {
    const request = ++sequence.current;
    setBusy(true); setError('');
    try {
      const [events, status] = await Promise.all([
        api(`/internal/events?origin=${origin}&limit=30${eventId ? `&event_id=${encodeURIComponent(eventId)}` : ''}`),
        api(`/analytics/status?origin=${origin}`),
      ]);
      if (request === sequence.current) setData({ events, status });
    } catch (e) { if (request === sequence.current) setError(e.message); }
    finally { if (request === sequence.current) setBusy(false); }
  }
  useEffect(() => { setData(null); refresh(); }, [origin]);
  return <section className="page-section"><span className="eyebrow green">DEVELOPER DATA TRACE</span><h1>Follow the event.</h1>
    <p>Local writes and events imported back from PostHog are shown separately. Match the event_id to trace the same action.</p>
    <form className="catalog-tools" onSubmit={e => { e.preventDefault(); refresh(); }}><select aria-label="Dataset origin" value={origin} onChange={e => setOrigin(e.target.value)}><option value="synthetic">Synthetic / demo</option><option value="real">Real / consented</option></select><input className="trace-input" aria-label="Event ID" placeholder="Paste event_id, or leave empty for latest events" value={eventId} onChange={e => setEventId(e.target.value)}/><button className="button dark" disabled={busy}>{busy ? 'Loading…' : 'Refresh trace'}</button></form>
    {error && <p className="error" role="alert">{error}</p>}
    {data && <><div className="pipeline-note"><span>Origin: {origin} · Local events: {data.status.events} · PostHog imports: {data.status.posthog_imported}</span><span>Silver events: {data.status.pipeline.events || 0} · Rejected: {data.status.pipeline.rejected || 0}</span></div>
      <details className="trace-panel"><summary>Pipeline status</summary><pre>{JSON.stringify({ pipeline: data.status.pipeline }, null, 2)}</pre></details>
      {['local', 'posthog_imported'].map(source => <section className="trace-panel" key={source}><h2>{source === 'local' ? '1. Local database' : '2. Imported from PostHog'}</h2>{!data.events[source].length && <p>No matching events. PostHog imports appear after running the export command.</p>}{data.events[source].map(e => <details key={e.event_id}><summary>{e.event_name || 'Invalid event'} · {e.distinct_id} · {e.event_id}</summary><pre>{JSON.stringify(e, null, 2)}</pre></details>)}</section>)}
    </>}
  </section>;
}
