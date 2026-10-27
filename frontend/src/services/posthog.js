import posthog from 'posthog-js';
import { post } from './api';

export const cloudTracking = Boolean(import.meta.env.VITE_POSTHOG_KEY && import.meta.env.VITE_POSTHOG_TEST_PROJECT === 'true');
console.info('[PostHog] Tracking', cloudTracking ? 'enabled' : 'disabled (check VITE_POSTHOG_KEY and VITE_POSTHOG_TEST_PROJECT)');
if (cloudTracking) posthog.init(import.meta.env.VITE_POSTHOG_KEY, {
  api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
  autocapture: false, capture_pageview: false, capture_pageleave: false,
  disable_session_recording: true, person_profiles: 'identified_only',
});
export function identify(userId) {
  sessionStorage.removeItem('nutee-product-demo-v1:tracking-session');
  if (cloudTracking) {
    posthog.reset();
    posthog.identify(userId);
    console.info('[PostHog] identify called', { distinct_id: userId });
  }
}
export function getSessionId() {
  const now = Date.now();
  let session;
  try { session = JSON.parse(sessionStorage.getItem('nutee-product-demo-v1:tracking-session')); } catch { /* start a fresh session */ }
  if (!session || now - session.lastActivity > 30 * 60 * 1000) session = { id: crypto.randomUUID() };
  session.lastActivity = now;
  sessionStorage.setItem('nutee-product-demo-v1:tracking-session', JSON.stringify(session));
  return session.id;
}
export function captureCloud(event) {
  const properties = { ...event, session_id: event.session_id || getSessionId(), environment: event.environment || 'dev', app: 'nutee', synthetic: true, $insert_id: event.event_id };
  if (!cloudTracking) {
    console.info('[PostHog] capture skipped: tracking disabled', { event: event.event_name, properties });
    return;
  }
  try {
    posthog.capture(event.event_name, properties, { timestamp: new Date(event.timestamp) });
    // capture can batch requests; this log does not confirm server ingestion.
    console.info('[PostHog] capture called (delivery not confirmed)', { event: event.event_name, properties });
  } catch (error) {
    console.error('[PostHog] capture failed', { event: event.event_name, event_id: event.event_id });
    throw error;
  }
}
export async function track(userId, eventName, properties = {}) {
  const event = { event_id: crypto.randomUUID(), ...properties, timestamp: new Date().toISOString(), distinct_id: userId,
    page: properties.page || (window.location.pathname === '/' ? 'home' : window.location.pathname === '/cart' ? 'cart' : window.location.pathname.startsWith('/products/') ? 'product_detail' : new URLSearchParams(window.location.search).get('q') ? 'search' : 'catalog'),
    event_name: eventName, source: 'website', session_id: getSessionId(), synthetic: true, environment: 'dev' };
  console.info('[Tracking] event created', event);
  try {
    await post('/events', event);
    console.info('[Tracking] local database acknowledged', { event_id: event.event_id, session_id: event.session_id });
  } catch (error) {
    console.error('[PostHog] capture skipped: local /events request failed', {
      event: eventName, event_id: event.event_id, distinct_id: userId,
    });
    throw error;
  }
  captureCloud(event);
  return event;
}
