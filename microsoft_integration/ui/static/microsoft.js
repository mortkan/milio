/**
 * microsoft.js — Dashboard UI logic for /microsoft
 */
(async () => {
  let currentAccountId = null;
  let deviceFlowInterval = null;

  // ---- Helper: show banner ------------------------------------------------
  function showBanner(msg, type = 'info') {
    const el = document.getElementById('status-banner');
    el.textContent = msg;
    el.className = `ms-banner ms-banner--${type}`;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 5000);
  }

  // ---- Load initial state -------------------------------------------------
  async function init() {
    try {
      const health = await MsApi.health();
      const schedulerEl = document.getElementById('scheduler-status');
      if (schedulerEl) {
        schedulerEl.textContent = health.scheduler === 'running' ? 'Activo' : 'Detenido';
        schedulerEl.className = `ms-status ms-status--${health.scheduler === 'running' ? 'ok' : 'warn'}`;
      }
    } catch (e) { /* service may not be ready */ }

    const accounts = await MsApi.getAccounts().catch(() => []);
    if (!accounts.length) {
      document.getElementById('no-account').style.display = 'block';
      document.getElementById('dashboard').style.display = 'none';
    } else {
      const account = accounts[0];
      currentAccountId = account.id;
      showDashboard(account);
      loadConfig(account.id);
      loadHistory(account.id);
      loadConflictBadge();
    }
  }

  function showDashboard(account) {
    document.getElementById('no-account').style.display = 'none';
    document.getElementById('dashboard').style.display = 'block';
    document.getElementById('account-name').textContent = account.display_name || '—';
    document.getElementById('account-email').textContent = account.email || '—';

    const statusEl = document.getElementById('account-status');
    if (account.needs_reauthentication) {
      statusEl.textContent = 'Reautorización requerida';
      statusEl.className = 'ms-status ms-status--warn';
    } else if (account.enabled) {
      statusEl.textContent = 'Conectada';
      statusEl.className = 'ms-status ms-status--ok';
    } else {
      statusEl.textContent = 'Desconectada';
      statusEl.className = 'ms-status ms-status--off';
    }
  }

  async function loadConfig(accountId) {
    const config = await MsApi.getAccountConfig(accountId).catch(() => null);
    if (!config) return;

    const calName = document.getElementById('cal-name');
    const calStatus = document.getElementById('cal-status');
    const todoName = document.getElementById('todo-name');
    const todoStatus = document.getElementById('todo-status');
    const interval = document.getElementById('sync-interval');

    if (calName) calName.textContent = config.calendar_name || '(no configurado)';
    if (calStatus) {
      calStatus.textContent = config.calendar_sync_enabled ? 'Activo' : 'Desactivado';
      calStatus.className = `ms-status ms-status--${config.calendar_sync_enabled ? 'ok' : 'off'}`;
    }
    if (todoName) todoName.textContent = config.todo_list_name || '(no configurado)';
    if (todoStatus) {
      todoStatus.textContent = config.todo_sync_enabled ? 'Activo' : 'Desactivado';
      todoStatus.className = `ms-status ms-status--${config.todo_sync_enabled ? 'ok' : 'off'}`;
    }
    if (interval) interval.textContent = `${config.sync_interval_seconds}s`;
  }

  async function loadHistory(accountId) {
    const runs = await MsApi.getSyncHistory(accountId, 5).catch(() => []);
    const tbody = document.getElementById('history-body');
    if (!tbody) return;
    if (!runs.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="ms-table__empty">Sin historial de sincronización</td></tr>';
      return;
    }
    tbody.innerHTML = runs.map(r => {
      const statusClass = r.status === 'success' ? 'ok' : r.status === 'running' ? 'warn' : 'err';
      return `<tr>
        <td>${new Date(r.started_at).toLocaleString('es-ES')}</td>
        <td><span class="ms-status ms-status--${statusClass}">${r.status}</span></td>
        <td>${r.calendar_created + r.calendar_updated}</td>
        <td>${r.tasks_created + r.tasks_updated}</td>
        <td>${r.conflicts_detected || 0}</td>
      </tr>`;
    }).join('');
  }

  async function loadConflictBadge() {
    const conflicts = await MsApi.getConflicts({ status: 'pending' }).catch(() => []);
    const badge = document.getElementById('conflict-badge');
    if (badge && conflicts.length > 0) {
      badge.textContent = conflicts.length;
      badge.style.display = 'inline';
    }
  }

  // ---- Device Code Flow ---------------------------------------------------
  function startDeviceFlow() {
    MsApi.startDeviceFlow().then(flow => {
      const modal = document.getElementById('device-flow-modal');
      const codeEl = document.getElementById('device-flow-code');
      const urlEl = document.getElementById('device-flow-url');
      const statusEl = document.getElementById('device-flow-status');

      codeEl.textContent = flow.user_code;
      urlEl.href = flow.verification_uri;
      urlEl.textContent = flow.verification_uri;
      statusEl.textContent = 'Esperando autorización...';
      modal.style.display = 'flex';

      // Poll for completion
      deviceFlowInterval = setInterval(async () => {
        const status = await MsApi.getDeviceFlowStatus(flow.flow_id).catch(() => null);
        if (!status) return;
        if (status.status === 'completed') {
          clearInterval(deviceFlowInterval);
          modal.style.display = 'none';
          showBanner('✓ Cuenta Microsoft conectada', 'ok');
          init();
        } else if (status.status === 'failed' || status.status === 'expired') {
          clearInterval(deviceFlowInterval);
          modal.style.display = 'none';
          showBanner('✗ La autenticación falló o expiró', 'err');
        }
      }, 3000);
    }).catch(e => showBanner('Error iniciando autenticación: ' + e.message, 'err'));
  }

  // ---- Sync now -----------------------------------------------------------
  async function syncNow() {
    if (!currentAccountId) return;
    const btn = document.getElementById('btn-sync-now');
    btn.disabled = true;
    btn.textContent = 'Sincronizando...';
    try {
      const run = await MsApi.syncNow(currentAccountId);
      showSyncResult(run);
      loadHistory(currentAccountId);
      showBanner('Sincronización completada', run.status === 'success' ? 'ok' : 'info');
    } catch (e) {
      showBanner('Error en sincronización: ' + e.message, 'err');
    } finally {
      btn.disabled = false;
      btn.textContent = '⟳ Sincronizar ahora';
    }
  }

  function showSyncResult(run) {
    const el = document.getElementById('sync-result');
    const body = document.getElementById('sync-result-body');
    if (!el || !body) return;
    el.style.display = 'block';
    body.innerHTML = [
      { label: 'Cal. creados', value: run.calendar_created },
      { label: 'Cal. actualizados', value: run.calendar_updated },
      { label: 'Tareas creadas', value: run.tasks_created },
      { label: 'Tareas actualizadas', value: run.tasks_updated },
      { label: 'Conflictos', value: run.conflicts_detected },
      { label: 'Errores', value: run.errors_count },
    ].map(item => `
      <div class="ms-result-item">
        <div class="ms-result-item__value">${item.value}</div>
        <div class="ms-result-item__label">${item.label}</div>
      </div>`).join('');
  }

  // ---- Sync preview -------------------------------------------------------
  async function syncPreview() {
    if (!currentAccountId) return;
    try {
      const preview = await MsApi.syncPreview(currentAccountId);
      const lines = [
        `Tareas se crearían en Microsoft: ${preview.tasks_would_create_remote || 0}`,
        `Tareas se importarían de Microsoft: ${preview.tasks_would_create_local || 0}`,
        `Eventos se crearían en Microsoft: ${preview.events_would_create_remote || 0}`,
        `Conflictos detectados: ${preview.conflicts_detected || 0}`,
      ];
      alert('Vista previa de sincronización:\n\n' + lines.join('\n'));
    } catch (e) {
      showBanner('Error en vista previa: ' + e.message, 'err');
    }
  }

  // ---- Event listeners ----------------------------------------------------
  const btnConnect = document.getElementById('btn-connect');
  if (btnConnect) btnConnect.onclick = startDeviceFlow;

  const btnCancelFlow = document.getElementById('btn-cancel-flow');
  if (btnCancelFlow) btnCancelFlow.onclick = () => {
    clearInterval(deviceFlowInterval);
    document.getElementById('device-flow-modal').style.display = 'none';
  };

  const btnSyncNow = document.getElementById('btn-sync-now');
  if (btnSyncNow) btnSyncNow.onclick = syncNow;

  const btnPreview = document.getElementById('btn-sync-preview');
  if (btnPreview) btnPreview.onclick = syncPreview;

  const btnTest = document.getElementById('btn-test-connection');
  if (btnTest) btnTest.onclick = async () => {
    if (!currentAccountId) return;
    const res = await MsApi.testConnection(currentAccountId).catch(e => ({ status: 'error', detail: e.message }));
    showBanner(
      res.status === 'ok' ? `✓ Conectado como ${res.display_name}` : `✗ ${res.detail}`,
      res.status === 'ok' ? 'ok' : 'err'
    );
  };

  const btnDisconnect = document.getElementById('btn-disconnect');
  if (btnDisconnect) btnDisconnect.onclick = async () => {
    if (!currentAccountId) return;
    if (!confirm('¿Desconectar esta cuenta Microsoft? Los mappings de sincronización se conservarán.')) return;
    await MsApi.disconnectAccount(currentAccountId).catch(() => {});
    showBanner('Cuenta desconectada', 'info');
    currentAccountId = null;
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('no-account').style.display = 'block';
  };

  // ---- Init ---------------------------------------------------------------
  init();
})();
