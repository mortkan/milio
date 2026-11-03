/**
 * Microsoft Integration API client (backend proxy — no direct MS calls)
 * All requests go to /api/microsoft/* on the same origin.
 */
const MsApi = (() => {
  const BASE = '/api/microsoft';

  async function req(method, path, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(BASE + path, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    if (res.status === 204) return null;
    return res.json().catch(() => null);
  }

  return {
    // Health
    health: () => req('GET', '/health'),

    // Accounts
    getAccounts: () => req('GET', '/accounts'),
    getAccount: (id) => req('GET', `/accounts/${id}`),
    disconnectAccount: (id) => req('POST', `/accounts/${id}/disconnect`),
    reauthorizeAccount: (id) => req('POST', `/accounts/${id}/reauthorize`),
    testConnection: (id) => req('GET', `/accounts/${id}/connection-test`),

    // Auth
    startDeviceFlow: () => req('POST', '/auth/device/start'),
    getDeviceFlowStatus: (flowId) => req('GET', `/auth/device/${flowId}/status`),

    // Config
    listCalendars: (id) => req('GET', `/accounts/${id}/calendars`),
    listTodoLists: (id) => req('GET', `/accounts/${id}/todo-lists`),
    getAccountConfig: (id) => req('GET', `/accounts/${id}/config`),
    updateAccountConfig: (id, data) => req('PUT', `/accounts/${id}/config`, data),

    // Sync
    syncNow: (id) => req('POST', `/accounts/${id}/sync`),
    fullResync: (id) => req('POST', `/accounts/${id}/full-resync`),
    syncPreview: (id) => req('POST', `/accounts/${id}/sync-preview`),
    getSyncHistory: (id, limit = 50) => req('GET', `/accounts/${id}/sync-history?limit=${limit}`),

    // Conflicts
    getConflicts: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return req('GET', `/conflicts${qs ? '?' + qs : ''}`);
    },
    getConflict: (id) => req('GET', `/conflicts/${id}`),
    resolveConflict: (id, resolution) => req('POST', `/conflicts/${id}/resolve`, { resolution }),
  };
})();
