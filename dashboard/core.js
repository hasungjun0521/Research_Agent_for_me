(function () {
  const RECENT_ACTIVITY_WINDOW_MS = 15 * 60 * 1000;
  const COMPLETED_COMMAND_DISPLAY_LIMIT = 4;
  const terminalActivityStatuses = new Set(['done', 'idle', 'deferred', 'succeeded', 'failed', 'cancelled', 'complete', 'completed']);
  const terminalActivityEvents = new Set(['finish', 'finished', 'complete', 'completed', 'result']);
  const dashboardSourceDefinitions = [
    { key: 'agent_status', label: 'Agent Status', path: 'state/agent_status.json', required: true, records: (status) => status.agents?.length || 0 },
    { key: 'command_queue', label: 'Command Queue', path: 'state/command_queue.json', required: true, records: (status) => status.command_queue?.commands?.length || 0 },
    { key: 'loop_summary', label: 'Loop Summary', path: 'state/loop_summary.json', required: true, records: () => 1 },
    { key: 'agent_events', label: 'Agent Events', path: 'state/agent_events.jsonl', required: true, records: (status) => status.agent_events?.length || 0 },
    { key: 'agent_messages', label: 'Agent Messages', path: 'state/agent_messages.json', required: false, records: (status) => status.agent_messages?.messages?.length || 0 },
    { key: 'agent_votes', label: 'Vote Gates', path: 'state/agent_votes.json', required: false, records: (status) => status.agent_votes?.votes?.length || 0 },
    { key: 'pattern_memory', label: 'Pattern Memory', path: 'state/pattern_memory.json', required: false, records: (status) => status.pattern_memory?.patterns?.length || 0 },
    { key: 'ralph_loop', label: 'Ralph Loops', path: 'state/ralph_loop.json', required: false, records: (status) => status.ralph_loop?.runs?.length || 0 },
    { key: 'gpu_queue', label: 'GPU Queue', path: 'state/gpu_experiment_queue.json', required: false, records: (status) => status.gpu_experiment_queue?.jobs?.length || 0 },
    { key: 'current_state', label: 'Current State', path: 'state/current_state.md', required: true, records: () => 1 },
    { key: 'next_actions', label: 'Next Actions', path: 'state/next_actions.md', required: true, records: () => 1 },
    { key: 'report_readme', label: 'Report README', path: '09_report/README.md', required: true, records: (status) => status.report_snapshot?.readme_path ? 1 : 0 },
    { key: 'sessions', label: 'Session Workspaces', path: 'state/sessions/*/session.json', required: false, pattern: /\/state\/sessions\/[^/]+\/session\.json$/, records: (status) => status.sessions?.length || 0 },
    { key: 'experiment_runs', label: 'Experiment Runs', path: '03_experiments/exp_*/run_state.json', required: false, pattern: /\/03_experiments\/exp_[^/]+\/run_state\.json$/, records: (status) => status.experiment_runs?.length || 0 },
    { key: 'report_tables', label: 'Report Tables', path: '09_report/results/*.csv', required: false, pattern: /\/09_report\/results\/.*\.csv$/i, records: (status) => status.report_snapshot?.tables?.length || 0 },
    { key: 'report_artifacts', label: 'Report Artifacts', path: '09_report/{results,analysis,figures}', required: false, pattern: /\/09_report\/(results|analysis|figures)\//i, records: (status) => status.report_snapshot?.latest_files?.length || 0 }
  ];

  const statusRank = {
    running: 0,
    blocked: 1,
    waiting: 2,
    idle: 3,
    done: 4
  };

  const priorityRank = {
    high: 0,
    medium: 1,
    low: 2
  };

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function text(value, fallback = '-') {
    if (value === undefined || value === null || value === '') return fallback;
    return String(value);
  }

  function normalizeStatus(status) {
    return String(status || 'idle').trim().toLowerCase();
  }

  function formatDisplayTime(value) {
    const textValue = String(value || '').trim();
    if (!textValue || textValue === '-') return '-';
    return textValue
      .replace(/([+-]\d{2}:\d{2}|Z)$/i, '')
      .replace('T', ' ');
  }

  function parseTimeMs(value) {
    const parsed = Date.parse(String(value || ''));
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function firstMeaningful(items, fields) {
    for (const item of items || []) {
      for (const field of fields) {
        const value = item?.[field];
        if (typeof value === 'string' && value.trim()) return value.trim();
        if (Array.isArray(value) && value.length) return value.join(', ');
      }
    }
    return '';
  }

  function hasKorean(value) {
    return /[가-힣]/.test(String(value || ''));
  }

  function normalizeWorkspaceProfile(profile) {
    const source = profile && typeof profile === 'object' ? profile : {};
    const display = source.display && typeof source.display === 'object' ? source.display : {};
    const labels = display.top_summary_labels && typeof display.top_summary_labels === 'object'
      ? display.top_summary_labels
      : {};
    return {
      display: {
        summary_language: String(display.summary_language || 'en').toLowerCase(),
        top_summary_labels: {
          work: labels.work || 'What happened this instruction',
          result: labels.result || 'Result analysis',
          next: labels.next || 'Next action'
        }
      },
      agent_output: source.agent_output && typeof source.agent_output === 'object' ? source.agent_output : {},
      gpu: source.gpu && typeof source.gpu === 'object' ? source.gpu : {}
    };
  }

  function summaryLanguage(data) {
    return String(data.workspaceProfile?.display?.summary_language || 'en').toLowerCase();
  }

  function isKoreanSummary(data) {
    return summaryLanguage(data).startsWith('ko');
  }

  function summaryLabels(data) {
    return data.workspaceProfile?.display?.top_summary_labels || {
      work: 'What happened this instruction',
      result: 'Result analysis',
      next: 'Next action'
    };
  }

  function compactKoreanList(value, maxItems = 2) {
    const values = Array.isArray(value)
      ? value
      : String(value || '').split(',').map((item) => item.trim());
    const clean = values.filter(Boolean);
    if (clean.length === 0) return '';
    const shown = clean.slice(0, maxItems).join(', ');
    return clean.length > maxItems ? `${shown} 외 ${clean.length - maxItems}개` : shown;
  }

  function valueList(value) {
    if (Array.isArray(value)) return value.map((item) => String(item || '').trim()).filter(Boolean);
    return String(value || '').split(',').map((item) => item.trim()).filter(Boolean);
  }

  window.DashboardCore = {
    COMPLETED_COMMAND_DISPLAY_LIMIT,
    RECENT_ACTIVITY_WINDOW_MS,
    compactKoreanList,
    dashboardSourceDefinitions,
    escapeHtml,
    firstMeaningful,
    formatDisplayTime,
    hasKorean,
    isKoreanSummary,
    normalizeStatus,
    normalizeWorkspaceProfile,
    parseTimeMs,
    priorityRank,
    statusRank,
    summaryLabels,
    summaryLanguage,
    terminalActivityEvents,
    terminalActivityStatuses,
    text,
    valueList
  };
}());
