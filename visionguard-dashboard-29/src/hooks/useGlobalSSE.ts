import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { buildApiUrl } from '@/config/api';

/**
 * Global SSE Hook
 * Connects to the /api/stream/global endpoint and populates the
 * React Query cache automatically. This allows all components to
 * instantly re-render with fresh data without polling the backend.
 */
export function useGlobalSSE() {
  const queryClient = useQueryClient();
  const isConnected = useRef(false);
  // Track the last known event total to detect genuinely new events
  const lastEventTotal = useRef<number | null>(null);
  // Track the last known alert total to detect genuinely new alerts
  const lastAlertTotal = useRef<number | null>(null);

  useEffect(() => {
    // Only open one connection
    if (isConnected.current) return;

    const sseUrl = buildApiUrl('/stream/global');
    const eventSource = new EventSource(sseUrl);
    isConnected.current = true;

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);

        if (payload.error) {
          console.error('[Global SSE] Backend stream error:', payload.error);
          return;
        }

        // 1. System Status & Metrics (Used by Dashboard, Analytics, Settings)
        if (payload.status) {
          queryClient.setQueryData(['dashboard-system'], payload.status);
          queryClient.setQueryData(['settings-status'], payload.status);
        }
        if (payload.metrics) {
          queryClient.setQueryData(['settings-metrics'], payload.metrics);
        }

        // 2. Camera List (Used by Cameras, Dashboard, Analytics, LiveMonitoring)
        if (payload.cameras) {
          queryClient.setQueryData(['dashboard-cameras'], payload.cameras);
          queryClient.setQueryData(['cameras-list'], payload.cameras);
        }

        // 3. Event Stats (Used by Dashboard, Analytics)
        if (payload.stats) {
          queryClient.setQueryData(['dashboard-stats'], payload.stats);
          queryClient.setQueryData(['analytics-stats'], payload.stats);
        }

        // 4. Recent Events (Used by Dashboard & Header Bell icon)
        if (payload.recentEvents) {
          queryClient.setQueryData(['dashboard-recent-events'], payload.recentEvents);

          const newTotal: number = payload.recentEvents?.total ?? 0;
          const newestEvent = payload.recentEvents?.events?.[0]; // Full event object from SSE

          if (lastEventTotal.current !== null && newTotal > lastEventTotal.current && newestEvent) {
            console.log(`[Global SSE] New event detected (${lastEventTotal.current} → ${newTotal}). Injecting directly into cache (no HTTP).`);

            // Level 3: Incremental Cache Shift
            // Find ALL active incidents queries in the cache (any filter/page combo).
            // For page-1 queries: inject the new event at the top + pop the 50th item off.
            // For page 2+ queries: just update the total count so pagination math stays correct.
            // No HTTP request is made regardless of which page the user is on.
            const allIncidentQueries = queryClient.getQueriesData<any>({ queryKey: ['incidents'] });

            for (const [queryKey, queryData] of allIncidentQueries) {
              if (!queryData) continue;

              // queryKey shape: ['incidents', filters, page]
              const pageInKey = queryKey[2] ?? 1;

              if (pageInKey === 1) {
                // Page 1: prepend new event, drop the 50th item (it logically moves to page 2)
                const currentEvents: any[] = queryData.events ?? [];
                const updatedEvents = [newestEvent, ...currentEvents].slice(0, 50);
                queryClient.setQueryData(queryKey, {
                  ...queryData,
                  total: newTotal,
                  events: updatedEvents,
                });
              } else {
                // Page 2+: user is not watching page 1, just update the total count
                // so the pagination "Showing X–Y of Z" counter and Next/Prev buttons stay accurate.
                queryClient.setQueryData(queryKey, {
                  ...queryData,
                  total: newTotal,
                });
              }
            }
          }
          lastEventTotal.current = newTotal;
        }

        // Active Events (For Header Bell icon)
        if (payload.activeEvents) {
          queryClient.setQueryData(['active-alerts'], payload.activeEvents);
        }

        // 5. Live Bounding Boxes (Used by LiveMonitoring)
        if (payload.boxes) {
          queryClient.setQueryData(['live-boxes'], payload.boxes);
        }

        // 6. Alert History (Used by AlertContacts)
        // Level 3: Incremental Cache Shift — same pattern as Incidents.
        // SSE carries the newest alert object. We inject it into the page-1 cache directly.
        // No HTTP request is made when a new alert arrives.
        if (payload.alerts) {
          const newAlertTotal: number = payload.alerts?.total ?? 0;
          const newestAlert = payload.alerts?.alerts?.[0]; // Newest alert object from SSE

          if (lastAlertTotal.current !== null && newAlertTotal > lastAlertTotal.current && newestAlert) {
            console.log(`[Global SSE] New alert detected (${lastAlertTotal.current} → ${newAlertTotal}). Injecting directly into cache (no HTTP).`);

            const allAlertQueries = queryClient.getQueriesData<any>({ queryKey: ['alert-history'] });

            for (const [queryKey, queryData] of allAlertQueries) {
              if (!queryData) continue;

              // queryKey shape: ['alert-history', page]
              const pageInKey = queryKey[1] ?? 1;

              if (pageInKey === 1) {
                // Page 1: prepend new alert, drop the 50th item off the bottom
                const currentAlerts: any[] = queryData.alerts ?? [];
                const updatedAlerts = [newestAlert, ...currentAlerts].slice(0, 50);
                queryClient.setQueryData(queryKey, {
                  ...queryData,
                  total: newAlertTotal,
                  alerts: updatedAlerts,
                });
              } else {
                // Page 2+: just update total count so pagination counters stay accurate
                queryClient.setQueryData(queryKey, {
                  ...queryData,
                  total: newAlertTotal,
                });
              }
            }
          }
          lastAlertTotal.current = newAlertTotal;
        }

      } catch (err) {
        console.error('[Global SSE] Parse error:', err);
      }
    };

    eventSource.onerror = (error) => {
      console.error('[Global SSE] Connection lost. Reconnecting...', error);
      // EventSource auto-reconnects, but we log it
    };

    return () => {
      eventSource.close();
      isConnected.current = false;
    };
  }, [queryClient]);
}
