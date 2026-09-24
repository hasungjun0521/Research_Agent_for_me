const input = document.getElementById('projectInput');
const clearButton = document.getElementById('clearButton');
const fileControls = document.getElementById('fileControls');
const serverControls = document.getElementById('serverControls');
const projectSelect = document.getElementById('projectSelect');
const refreshButton = document.getElementById('refreshButton');
const refreshStatus = document.getElementById('refreshStatus');
const notice = document.getElementById('notice');
const dashboardSearch = document.getElementById('dashboardSearch');
const pauseButton = document.getElementById('pauseButton');
const clearFiltersButton = document.getElementById('clearFiltersButton');
const drawerBackdrop = document.getElementById('drawerBackdrop');
const detailDrawer = document.getElementById('detailDrawer');
const drawerClose = document.getElementById('drawerClose');
const copyDrawerJson = document.getElementById('copyDrawerJson');
const copyDrawerCli = document.getElementById('copyDrawerCli');

const refreshIntervalMs = 5000;
let refreshTimer = null;
let refreshInFlight = false;
let serverMode = false;
let lastData = null;
let detailRegistry = new Map();
let activeDetail = null;

const uiState = {
  view: 'overview',
  statusFilter: 'all',
  query: '',
  paused: false
};

const {
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
  terminalActivityEvents,
  terminalActivityStatuses,
  text,
  valueList
} = window.DashboardCore;

function setNotice(message, tone = 'error') {
  notice.textContent = message || '';
  notice.classList.toggle('info', tone === 'info');
  notice.style.display = message ? 'block' : 'none';
}

function updateSummaryCardLabels(data) {
  const labels = summaryLabels(data);
  const targets = [
    ['.korean-summary-card.work .korean-summary-title', labels.work],
    ['.korean-summary-card.result .korean-summary-title', labels.result],
    ['.korean-summary-card.next .korean-summary-title', labels.next]
  ];
  for (const [selector, label] of targets) {
    const node = document.querySelector(selector);
    if (node) node.textContent = label;
  }
}

function koreanStatusLabel(status) {
  const labels = {
    blocked: '막힘',
    deferred: '보류',
    done: '완료',
    failed: '실패',
    idle: '대기',
    'in progress': '진행 중',
    open: '열림',
    planned: '예정',
    running: '진행 중',
    succeeded: '성공',
    waiting: '대기 중'
  };
  return labels[normalizeStatus(status)] || text(status, '기록 없음');
}

function koreanPriorityLabel(priority) {
  const labels = { high: '높은', medium: '중간', low: '낮은' };
  return labels[normalizeStatus(priority)] || text(priority, '기록된');
}

function englishStatusLabel(status) {
  return titleCaseCompact(normalizeStatus(status) || status || 'not recorded');
}

function englishPriorityLabel(priority) {
  return normalizeStatus(priority) || 'recorded';
}

function actionOutputFiles(item) {
  const files = [
    ...valueList(item?.output_files),
    ...valueList(item?.expected_outputs),
    ...valueList(item?.outputs),
    ...valueList(item?.last_output_files),
    ...valueList(item?.evidence_files)
  ].filter(Boolean);
  return [...new Set(files)];
}

function titleCaseCompact(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return raw
    .replace(/[_-]+/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(' ');
}

function inferMethodName(value) {
  const lower = String(value || '').toLowerCase();
  const official = lower.match(/\/([^/]+)_official\//);
  if (official) return titleCaseCompact(official[1]);
  return '';
}

function expIdFromPath(value) {
  return String(value || '').match(/03_experiments\/([^/]+)/)?.[1] || '';
}

function humanReadableOutput(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const lower = raw.toLowerCase();
  const method = inferMethodName(raw);
  const expId = expIdFromPath(raw);
  if (lower.includes('09_report/paper/main.tex')) return '최종 LaTeX paper';
  if (lower.includes('09_report/results/experiment_results.csv')) return '실험 결과표';
  if (lower.includes('09_report/results/claim_evidence_board.csv')) return 'claim-evidence board 요약표';
  if (lower.includes('09_report/results/claim_evidence.csv')) return 'claim-evidence 표';
  if (lower.includes('09_report/results/research_audit.csv')) return '연구 준비도 audit 표';
  if (lower.includes('09_report/results/statistical_robustness.csv')) return '통계 강건성 표';
  if (lower.includes('preregistration.md')) return `${expId || '실험'} 사전등록`;
  if (lower.includes('reproducibility_manifest.json')) return `${expId || '실험'} 재현성 manifest`;
  if (lower.includes('05_results/statistical_robustness.md')) return '통계 강건성 작업 기록';
  if (lower.includes('07_reviews/reviewer_attack_matrix.md')) return '리뷰어 공격 matrix';
  if (lower.includes('09_report/analysis')) return '보고서 분석 코드';
  if (lower.includes('09_report/src')) return '보고서용 코드';
  if (lower.includes('09_report/figures')) return '최종 figure';
  if (lower.includes('baseline_registry.json')) return 'baseline 재현 상태 기록';
  if (lower.includes('source_snapshots') && lower.includes('baseline-smoke')) {
    return method ? `${method} baseline smoke 결과` : '공식 baseline smoke 결과';
  }
  if (lower.includes('source_snapshots')) return `${method || 'baseline'} source snapshot 기록`;
  if (expId && lower.endsWith('/run_log.md')) return `${expId} 실행 로그`;
  if (expId && lower.includes('/results/')) return `${expId} 결과 파일`;
  if (expId && lower.endsWith('/analysis.md')) return `${expId} 분석 메모`;
  if (lower.includes('05_results/aggregate_results.md')) return '통합 결과 요약';
  if (lower.includes('05_results/interpretation.md')) return '결과 해석 문서';
  if (lower.includes('05_results/failure_cases.md')) return '실패 사례 정리';
  if (lower.includes('06_writing/draft.md')) return '논문 초안';
  if (lower.includes('06_writing/method.md')) return 'method section 초안';
  if (lower.includes('07_reviews/revision_plan.md')) return '수정 계획';
  if (lower.includes('state/loop_summary.json')) return '대시보드 loop 요약';
  if (lower.includes('state/command_queue.json')) return 'command queue 상태';
  if (lower.includes('state/agent_status.json')) return 'agent 진행 상태';
  if (lower.endsWith('.md')) return `${titleCaseCompact(raw.split('/').pop().replace(/\.md$/i, ''))} 문서`;
  if (lower.endsWith('.json')) return `${titleCaseCompact(raw.split('/').pop().replace(/\.json$/i, ''))} 기록`;
  return titleCaseCompact(raw.split('/').pop()) || raw;
}

function itemOutputs(item) {
  const readable = actionOutputFiles(item).map(humanReadableOutput).filter(Boolean);
  return compactKoreanList(readable, 3);
}

function rawItemOutputs(item) {
  return compactKoreanList(actionOutputFiles(item), 3);
}

function completionText(item) {
  const doneWhen = String(item?.done_when || item?.doneWhen || '').trim();
  if (doneWhen) return `완료 기준: ${doneWhen}`;
  const readable = itemOutputs(item);
  if (!readable) return '';
  return `완료되면 확인할 항목: ${readable}.`;
}

function inferWorkSubject(item) {
  const haystack = [
    item?.action,
    item?.notes,
    ...actionOutputFiles(item)
  ].join(' ').toLowerCase();
  const method = inferMethodName(haystack);
  const expId = expIdFromPath(haystack);
  if (haystack.includes('baseline-smoke') && method) return `${method} 공식 baseline smoke 검증`;
  if (haystack.includes('baseline-smoke')) return '공식 baseline smoke 검증';
  if (haystack.includes('source_snapshots') && method) return `${method} baseline 재현 준비`;
  if (expId && haystack.includes('run_log')) return `${expId} 실험 실행`;
  if (haystack.includes('09_report/paper/main.tex')) return '최종 LaTeX paper 정리';
  if (haystack.includes('09_report/results/experiment_results')) return '실험 결과표 정리';
  if (haystack.includes('09_report/results/claim_evidence')) return 'claim-evidence 표 정리';
  if (haystack.includes('09_report/results/statistical_robustness')) return '통계 강건성 표 정리';
  if (haystack.includes('preregistration.md')) return `${expId || '실험'} 사전등록 정리`;
  if (haystack.includes('reproducibility_manifest.json')) return `${expId || '실험'} 재현성 manifest 정리`;
  if (haystack.includes('05_results/statistical_robustness')) return '통계 강건성 검증';
  if (haystack.includes('07_reviews/reviewer_attack_matrix')) return '리뷰어 공격 matrix 정리';
  if (haystack.includes('09_report/analysis')) return '보고서 분석 코드 정리';
  if (haystack.includes('09_report/src')) return '보고서용 코드 정리';
  if (haystack.includes('09_report/figures')) return '최종 figure 정리';
  if (haystack.includes('baseline_registry')) return 'baseline 재현 상태 갱신';
  return '';
}

function readableActionTitle(item) {
  const explicit = firstMeaningful([item], ['display_ko', 'summary_ko', 'action_ko', 'title_ko']);
  if (explicit) return explicit;
  const raw = String(item?.action || '').trim();
  if (hasKorean(raw)) return raw;
  const subject = inferWorkSubject(item);
  if (subject) return subject;
  return koreanizeTask(raw || item?.notes, raw || '다음 command 처리');
}

function readableActionSummary(item) {
  const displaySummary = String(item?.display_summary || item?.displaySummary || '').trim();
  const whyNow = String(item?.why_now || item?.whyNow || '').trim();
  const notes = String(item?.notes || '').trim();
  const title = readableActionTitle(item);
  const base = displaySummary || (hasKorean(notes) ? notes : `${title}을 진행합니다.`);
  const why = whyNow ? `이유: ${whyNow}` : '';
  const completion = completionText(item);
  return [base, why, completion].filter(Boolean).join(' ');
}

function koreanizeTask(value, fallback) {
  const raw = String(value || '').trim();
  if (!raw) return fallback;
  if (hasKorean(raw)) return raw;
  const lower = raw.toLowerCase();
  if (lower.includes('monitor') && lower.includes('heartbeat')) return '실행 중인 작업을 모니터링하고 대시보드 heartbeat를 계속 갱신합니다.';
  if (lower.includes('summarize') && lower.includes('rebuttal')) return '완료된 결과를 요약하고 rebuttal evidence 파일을 갱신합니다.';
  if (lower.includes('metric') && lower.includes('sanity')) return 'metric-bias sanity check를 준비하거나 실행합니다.';
  if (lower.includes('oracle') && lower.includes('diagnostic') && lower.includes('completed')) return 'oracle/fixed-composer 진단 실험이 완료되어 새 evidence로 기록됐습니다.';
  if (lower.includes('diagnostic') && lower.includes('completed')) return '진단 실험이 완료되어 결과가 기록됐습니다.';
  if (lower.includes('2x2') && (lower.includes('design') || lower.includes('ready'))) return 'full-data 2x2 분리 실험 설계가 준비됐습니다.';
  if (lower.includes('run') && lower.includes('experiment')) return '실험을 실행하고 로그와 결과를 기록합니다.';
  if (lower.startsWith('run ')) return '실험 또는 검증 작업을 실행합니다.';
  if (lower.startsWith('design ')) return '실험 설계와 실행 계획을 정리합니다.';
  if (lower.startsWith('update ')) return '관련 상태 파일과 산출물을 갱신합니다.';
  if (lower.startsWith('draft ') || lower.includes('write')) return '작성 작업을 진행하고 결과 문서를 갱신합니다.';
  if (lower.includes('review')) return '리뷰 내용을 검토하고 후속 수정 항목을 정리합니다.';
  return fallback;
}

function koreanMeaning(item, fields, fallback) {
  const explicit = firstMeaningful([item], ['display_ko', 'summary_ko', 'result_ko', 'action_ko', 'notes_ko', 'title_ko']);
  if (explicit) return explicit;
  for (const field of fields) {
    const value = item?.[field];
    const translated = koreanizeTask(value, '');
    if (translated) return translated;
  }
  return fallback;
}

function shellQuote(value) {
  return `'${String(value ?? '').replaceAll("'", "'\"'\"'")}'`;
}

async function copyText(value) {
  const textValue = String(value || '');
  if (!textValue) return;
  try {
    await navigator.clipboard.writeText(textValue);
    setNotice('Copied to clipboard.', 'info');
    window.setTimeout(() => setNotice(''), 1200);
  } catch {
    setNotice('Clipboard is unavailable in this browser context.');
  }
}

function searchableText(item) {
  return JSON.stringify(item || {}).toLowerCase();
}

function matchesQuery(item) {
  if (!uiState.query) return true;
  return searchableText(item).includes(uiState.query);
}

function itemStatus(item) {
  return normalizeStatus(item?.status || item?.current_status || item?.state || '');
}

function matchesStatus(item) {
  if (uiState.statusFilter === 'all') return true;
  const status = itemStatus(item);
  return status === uiState.statusFilter || actionStatusClass(status) === uiState.statusFilter;
}

function applyInteractiveFilters(items) {
  return items.filter((item) => matchesQuery(item) && matchesStatus(item));
}

function registerDetail(kind, title, item, cli = '') {
  const key = `${kind}-${detailRegistry.size}`;
  detailRegistry.set(key, { kind, title, item, cli });
  return key;
}

function detailButton(key) {
  return `<button class="micro-button" type="button" data-detail-key="${escapeHtml(key)}">Inspect</button>`;
}

function copyButton(key) {
  return `<button class="secondary micro-button" type="button" data-copy-cli-key="${escapeHtml(key)}">Copy CLI</button>`;
}

function projectNameForCli(data) {
  const project = String(data.project || '').trim();
  if (project && !project.includes('/')) return project;
  const pathProject = String(data.projectPath || '').split('/').filter(Boolean).pop();
  return pathProject || project || 'template';
}

function fileList(files) {
  if (!Array.isArray(files) || files.length === 0) return '<span>None recorded</span>';
  return files.slice(0, 3).map((file) => `<code>${escapeHtml(file)}</code>`).join(' ');
}

function findFile(files, suffix) {
  return files.find((file) => file.webkitRelativePath.endsWith(suffix));
}

function filesMatchingSource(files, source) {
  if (source.pattern) {
    return files.filter((file) => source.pattern.test(String(file.webkitRelativePath || '')));
  }
  const suffix = `/${source.path}`;
  return files.filter((file) => String(file.webkitRelativePath || '').endsWith(suffix));
}

function fileUpdatedAt(file) {
  return file?.lastModified ? new Date(file.lastModified).toISOString() : '';
}

function newestFileUpdate(files) {
  return files.reduce((latest, file) => Math.max(latest, Number(file.lastModified || 0)), 0);
}

function buildDirectDataSources(files, status) {
  const sources = dashboardSourceDefinitions.map((source) => {
    const matches = filesMatchingSource(files, source);
    const latest = newestFileUpdate(matches);
    return {
      key: source.key,
      label: source.label,
      path: source.path,
      required: source.required,
      status: matches.length ? 'available' : (source.required ? 'missing' : 'empty'),
      records: matches.length ? source.records(status) : 0,
      updated_at: latest ? new Date(latest).toISOString() : ''
    };
  });
  const available = sources.filter((source) => source.status === 'available').length;
  return {
    generated_at: new Date().toISOString(),
    last_source_update: fileUpdatedAt(files.reduce((latest, file) => (
      Number(file.lastModified || 0) > Number(latest?.lastModified || 0) ? file : latest
    ), null)),
    coverage: {
      available,
      total: sources.length,
      required_missing: sources
        .filter((source) => source.required && source.status !== 'available')
        .map((source) => source.path)
    },
    sources
  };
}

async function readMatchingFile(files, suffix) {
  const file = findFile(files, suffix);
  return file ? file.text() : '';
}

async function readMatchingJson(files, suffix, fallback = null) {
  const textValue = await readMatchingFile(files, suffix);
  if (!textValue) return fallback;
  return JSON.parse(textValue);
}

async function readRunStates(files) {
  const runStateFiles = files.filter((file) => file.webkitRelativePath.endsWith('/run_state.json'));
  const states = [];
  for (const file of runStateFiles) {
    states.push(JSON.parse(await file.text()));
  }
  return states;
}

async function readAgentEvents(files) {
  const textValue = await readMatchingFile(files, '/state/agent_events.jsonl');
  if (!textValue) return [];
  return textValue
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function readSessions(files) {
  const sessionFiles = files.filter((file) => /\/state\/sessions\/[^/]+\/session\.json$/.test(file.webkitRelativePath));
  const sessions = [];
  for (const file of sessionFiles) {
    sessions.push(JSON.parse(await file.text()));
  }
  return sessions;
}

function projectRelativePath(file) {
  const parts = String(file.webkitRelativePath || file.name || '').split('/').filter(Boolean);
  return parts.length > 1 ? parts.slice(1).join('/') : parts.join('/');
}

async function readReportSnapshot(files) {
  const readme = await readMatchingFile(files, '/09_report/README.md');
  const reportFiles = files.filter((file) => String(file.webkitRelativePath || '').includes('/09_report/'));
  const tables = [];
  const latestFiles = [];
  for (const file of reportFiles) {
    const relative = projectRelativePath(file);
    if (!relative || relative === '09_report/README.md') continue;
    const updatedAt = file.lastModified ? new Date(file.lastModified).toISOString() : '';
    if (/^09_report\/results\/.*\.csv$/i.test(relative)) {
      const textValue = await file.text();
      const parsed = parseCsv(textValue);
      const rows = Math.max(0, parsed.length - 1);
      tables.push({
        path: relative,
        name: file.name,
        rows,
        updated_at: updatedAt,
        columns: parsed[0] || [],
        preview_rows: parsed.slice(1, 6),
        preview_limit: 5,
        preview_truncated: rows > 5
      });
    }
    if (/^09_report\/(results|analysis|figures)\//i.test(relative)) {
      latestFiles.push({
        path: relative,
        name: file.name,
        kind: file.name.split('.').pop() || 'file',
        updated_at: updatedAt
      });
    }
  }
  latestFiles.sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  return {
    readme_path: readme ? '09_report/README.md' : '',
    readme_excerpt: readme,
    tables,
    latest_files: latestFiles.slice(0, 12),
    updated_at: latestFiles[0]?.updated_at || ''
  };
}

function parseCsv(textValue) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  const inputText = String(textValue || '');
  for (let index = 0; index < inputText.length; index += 1) {
    const char = inputText[index];
    const next = inputText[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      field += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === ',' && !inQuotes) {
      row.push(field);
      field = '';
      continue;
    }
    if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && next === '\n') index += 1;
      row.push(field);
      if (row.some((cell) => String(cell).trim())) rows.push(row);
      row = [];
      field = '';
      continue;
    }
    field += char;
  }
  row.push(field);
  if (row.some((cell) => String(cell).trim())) rows.push(row);
  return rows;
}

function projectNameFromFiles(files) {
  const first = files[0]?.webkitRelativePath || '';
  return first.split('/')[0] || 'selected_project';
}

function extractCurrentStage(textValue) {
  const lines = textValue.split(/\r?\n/);
  const index = lines.findIndex((line) => line.trim().toLowerCase() === '## current stage');
  if (index === -1) return '';
  for (const line of lines.slice(index + 1)) {
    const stripped = line.trim().replaceAll('`', '');
    if (stripped) return stripped;
  }
  return '';
}

function extractSectionText(markdown, heading) {
  const lines = markdown.split(/\r?\n/);
  const target = `## ${heading}`.toLowerCase();
  const start = lines.findIndex((line) => line.trim().toLowerCase() === target);
  if (start === -1) return '';
  const collected = [];
  for (const line of lines.slice(start + 1)) {
    if (line.trim().startsWith('## ')) break;
    if (line.trim()) collected.push(line.trim().replaceAll('`', ''));
  }
  return collected.join(' ').trim();
}

function splitMarkdownRow(line) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function parseActionTable(markdown) {
  const lines = markdown.split(/\r?\n/);
  const headerIndex = lines.findIndex((line) => /^\|\s*Action\s*\|\s*Owner Agent\s*\|/i.test(line.trim()));
  if (headerIndex === -1) return [];
  const actions = [];
  for (const line of lines.slice(headerIndex + 1)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('|')) break;
    if (/^\|\s*-+/.test(trimmed)) continue;
    const cells = splitMarkdownRow(trimmed);
    if (cells.length < 6) continue;
    actions.push({
      action: cells[0],
      owner: cells[1],
      inputs: cells[2],
      outputs: cells[3],
      priority: cells[4],
      status: cells[5]
    });
  }
  return actions;
}

function commandFromJson(command) {
  return {
    id: command.id || '',
    action: command.action || '',
    owner: command.owner_agent || command.owner || '',
    inputs: Array.isArray(command.required_inputs) ? command.required_inputs.join(', ') : '',
    outputs: Array.isArray(command.expected_outputs) ? command.expected_outputs.join(', ') : '',
    expected_outputs: Array.isArray(command.expected_outputs) ? command.expected_outputs : [],
    display_summary: command.display_summary || '',
    why_now: command.why_now || '',
    done_when: command.done_when || '',
    priority: command.priority || '',
    status: command.status || '',
    notes: command.notes || '',
    result: command.result || '',
    updatedAt: command.updated_at || command.finished_at || command.created_at || ''
  };
}

function parseStructuredCommands(queue) {
  if (!queue || !Array.isArray(queue.commands)) return [];
  return queue.commands.map(commandFromJson);
}

function defaultLoopSummary(project) {
  return {
    project,
    loop_id: '',
    status: 'planned',
    goal: 'No loop summary recorded.',
    summary: 'Update state/loop_summary.json when a loop starts or finishes.',
    outcome: '',
    started_at: '',
    finished_at: '',
    last_updated: '',
    completed_commands: [],
    results: [],
    next_actions: []
  };
}

function normalizeLoopSummary(loopSummary, project) {
  if (!loopSummary || typeof loopSummary !== 'object') return defaultLoopSummary(project);
  return {
    ...defaultLoopSummary(project),
    ...loopSummary,
    completed_commands: Array.isArray(loopSummary.completed_commands) ? loopSummary.completed_commands : [],
    results: Array.isArray(loopSummary.results) ? loopSummary.results : [],
    next_actions: Array.isArray(loopSummary.next_actions) ? loopSummary.next_actions : []
  };
}

function commandFromLoop(command) {
  return {
    id: command.id || '',
    action: command.action || '',
    owner: command.owner_agent || command.owner || '',
    outputs: Array.isArray(command.output_files) ? command.output_files.join(', ') : '',
    output_files: Array.isArray(command.output_files) ? command.output_files : [],
    display_summary: command.display_summary || '',
    why_now: command.why_now || '',
    done_when: command.done_when || '',
    priority: command.priority || '',
    status: command.status || 'done',
    notes: command.notes || '',
    result: command.result || '',
    updatedAt: command.updated_at || ''
  };
}

function isCompletedAction(action) {
  const status = normalizeStatus(action.status);
  return status === 'done' || status === 'deferred' || status === 'succeeded';
}

function activeActions(actions) {
  return actions.filter((action) => !isCompletedAction(action));
}

function completedActions(actions, loopSummary) {
  const seen = new Set();
  const fromLoop = (loopSummary.completed_commands || []).map(commandFromLoop);
  const fromQueue = actions.filter(isCompletedAction);
  return [...fromLoop, ...fromQueue]
    .filter((action) => {
      const key = action.id || `${action.action}:${action.owner}:${action.updatedAt}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
}

function actionFromLoopNext(action) {
  return {
    action: action.action || '',
    owner: action.owner_agent || action.owner || '',
    outputs: Array.isArray(action.expected_outputs) ? action.expected_outputs.join(', ') : '',
    expected_outputs: Array.isArray(action.expected_outputs) ? action.expected_outputs : [],
    display_summary: action.display_summary || '',
    why_now: action.why_now || '',
    done_when: action.done_when || '',
    priority: action.priority || '',
    status: action.status || 'open',
    notes: action.notes || ''
  };
}

function actionStatusClass(status) {
  const normalized = normalizeStatus(status).replace(/\s+/g, '-');
  if (normalized.includes('progress')) return 'running';
  if (normalized.includes('active')) return 'running';
  if (normalized.includes('blocked')) return 'blocked';
  if (normalized.includes('rejected') || normalized.includes('cancelled') || normalized.includes('deprecated')) return 'blocked';
  if (normalized.includes('done') || normalized.includes('succeed') || normalized.includes('approved')) return 'done';
  if (normalized.includes('open') || normalized.includes('waiting') || normalized.includes('planned') || normalized.includes('queued') || normalized.includes('candidate')) return 'waiting';
  return 'idle';
}

function chooseNextAction(actions) {
  const candidates = actions.filter((action) => {
    const status = normalizeStatus(action.status);
    return status !== 'done' && status !== 'deferred';
  });
  return candidates.sort((a, b) => {
    const statusA = actionStatusClass(a.status);
    const statusB = actionStatusClass(b.status);
    const statusScoreA = statusA === 'running' ? 0 : statusA === 'waiting' ? 1 : statusA === 'blocked' ? 2 : 3;
    const statusScoreB = statusB === 'running' ? 0 : statusB === 'waiting' ? 1 : statusB === 'blocked' ? 2 : 3;
    if (statusScoreA !== statusScoreB) return statusScoreA - statusScoreB;
    return (priorityRank[normalizeStatus(a.priority)] ?? 9) - (priorityRank[normalizeStatus(b.priority)] ?? 9);
  })[0] || null;
}

function sortedAgents(agents) {
  return [...agents].sort((a, b) => {
    const rankA = statusRank[normalizeStatus(a.status)] ?? 9;
    const rankB = statusRank[normalizeStatus(b.status)] ?? 9;
    if (rankA !== rankB) return rankA - rankB;
    return String(a.display_name || a.name || '').localeCompare(String(b.display_name || b.name || ''));
  });
}

function loopUpdateCli(data) {
  const project = shellQuote(projectNameForCli(data));
  const summary = data.loopSummary?.summary || data.directorDecision || 'Update loop summary.';
  return `python -m scripts.commands.review.loop_summary update --project ${project} --summary ${shellQuote(summary)}`;
}

function agentHeartbeatCli(data, agent) {
  const selected = agent || data.runningAgents[0] || data.agents.find((candidate) => candidate.name);
  if (!selected?.name) return '';
  return [
    'python -m scripts.commands.agents.agent_status heartbeat',
    `--project ${shellQuote(projectNameForCli(data))}`,
    `--agent ${shellQuote(selected.name)}`,
    `--task ${shellQuote(selected.current_task || 'Continue current task.')}`,
    '--append-note',
    `--note ${shellQuote('Progress update.')}`
  ].join(' ');
}

function commandUpdateCli(data, action) {
  const selected = action || chooseNextAction(data.activeActions) || data.completedActions[0];
  if (!selected?.id) return '';
  const status = isCompletedAction(selected) ? 'done' : (selected.status || 'in progress');
  return [
    'python -m scripts.commands.review.command_queue update',
    `--project ${shellQuote(projectNameForCli(data))}`,
    `--id ${shellQuote(selected.id)}`,
    `--status ${shellQuote(status)}`,
    `--note ${shellQuote(selected.result || selected.notes || 'Progress update.')}`
  ].join(' ');
}

function runHeartbeatCli(data, run) {
  if (!run?.exp_id) return '';
  return [
    'python -m scripts.commands.experiments.run_state heartbeat',
    `--project ${shellQuote(projectNameForCli(data))}`,
    `--exp-id ${shellQuote(run.exp_id)}`,
    `--note ${shellQuote('Progress update.')}`
  ].join(' ');
}

function isTerminalActivity(event) {
  const status = normalizeStatus(event?.status);
  const eventName = normalizeStatus(event?.event);
  return terminalActivityStatuses.has(status) || terminalActivityEvents.has(eventName);
}

function isRecentActivityEvent(event, nowMs = Date.now()) {
  if (!event || !(event.task || event.notes || event.event)) return false;
  if (isTerminalActivity(event)) return false;
  const timestampMs = parseTimeMs(event.timestamp);
  if (!timestampMs) return false;
  return nowMs - timestampMs <= RECENT_ACTIVITY_WINDOW_MS;
}

function recentActivityFromEvents(agents, events, nowMs = Date.now()) {
  const displayNames = new Map();
  agents.forEach((agent) => {
    if (agent?.name) displayNames.set(agent.name, agent.display_name || agent.name);
  });
  return [...(events || [])]
    .filter((event) => isRecentActivityEvent(event, nowMs))
    .sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')))
    .slice(0, 4)
    .map((event) => ({
      name: event.agent || 'agent_event',
      display_name: displayNames.get(event.agent) || event.agent || 'Agent event',
      status: event.status || 'running',
      current_task: event.task || event.notes || 'Activity recorded.',
      updated_at: event.timestamp || '',
      activity_event: event.event || 'activity'
    }));
}

function completedActivityFromEvents(agents, events) {
  const displayNames = new Map();
  agents.forEach((agent) => {
    if (agent?.name) displayNames.set(agent.name, agent.display_name || agent.name);
  });
  return [...(events || [])]
    .filter((event) => isTerminalActivity(event) && (event.task || event.notes || event.command_id))
    .sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')))
    .slice(0, 8)
    .map((event, index) => ({
      id: event.command_id || `event_${index + 1}`,
      action: event.task || event.notes || event.event || 'Completed activity',
      owner: event.agent || 'agent_event',
      owner_agent: event.agent || 'agent_event',
      owner_display: displayNames.get(event.agent) || event.agent || 'Agent event',
      status: event.status || event.event || 'done',
      result: event.task || event.notes || '',
      notes: event.notes || '',
      updatedAt: event.timestamp || '',
      source_event: event.event || 'event'
    }));
}

function statusData(status, currentState, nextActions, projectPath, sourceUpdated = '-') {
  const agents = Array.isArray(status.agents) ? status.agents : [];
  const agentEvents = Array.isArray(status.agent_events) ? status.agent_events : [];
  const activeValues = new Set((status.active_status_values || ['running']).map(normalizeStatus));
  const running = agents
    .filter((agent) => activeValues.has(normalizeStatus(agent.status)))
    .filter((agent) => agent.display_name || agent.name);
  const waiting = agents
    .filter((agent) => normalizeStatus(agent.status) === 'waiting')
    .map((agent) => agent.display_name || agent.name)
    .filter(Boolean);
  const structuredActions = parseStructuredCommands(status.command_queue);
  const actions = structuredActions.length ? structuredActions : parseActionTable(nextActions);
  const loopSummary = normalizeLoopSummary(status.loop_summary, status.project || projectPath);
  const agentMessages = normalizeAgentMessages(status.agent_messages, status.project || projectPath);
  const agentVotes = normalizeAgentVotes(status.agent_votes, status.project || projectPath);
  const patternMemory = normalizePatternMemory(status.pattern_memory, status.project || projectPath);
  const ralphLoop = normalizeRalphLoop(status.ralph_loop, status.project || projectPath);
  const reportSnapshot = normalizeReportSnapshot(status.report_snapshot);
  const dataSources = normalizeDataSources(status.data_sources);
  const workspaceProfile = normalizeWorkspaceProfile(status.workspace_profile);
  const loopNextActions = loopSummary.next_actions.map(actionFromLoopNext);
  const active = activeActions(actions);
  const completed = completedActions(actions, loopSummary);
  const completedEventActions = completedActivityFromEvents(agents, agentEvents);
  return {
    project: status.project || projectPath,
    projectPath,
    lastUpdated: status.last_updated || '-',
    sourceUpdated,
    currentStage: extractCurrentStage(currentState) || '-',
    directorDecision: extractSectionText(currentState, 'Director Decision'),
    agents,
    currentState,
    nextActions,
    actions,
    activeActions: active,
    completedActions: completed,
    completedEventActions,
    loopSummary,
    agentMessages,
    agentEvents,
    agentVotes,
    sessions: Array.isArray(status.sessions) ? status.sessions : [],
    patternMemory,
    ralphLoop,
    reportSnapshot,
    dataSources,
    workspaceProfile,
    commandRunner: status.command_runner && typeof status.command_runner === 'object'
      ? {
          enabled: Boolean(status.command_runner.enabled),
          commands: Array.isArray(status.command_runner.commands) ? status.command_runner.commands : []
        }
      : { enabled: false, commands: [] },
    gpuQueue: status.gpu_experiment_queue || { jobs: [] },
    datasetRegistry: status.dataset_registry || { datasets: [] },
    metricRegistry: status.metric_registry || { metrics: [] },
    loopNextActions,
    experimentRuns: Array.isArray(status.experiment_runs) ? status.experiment_runs : [],
    healthWarnings: Array.isArray(status.health_warnings) ? status.health_warnings : [],
    running: running.map((agent) => agent.display_name || agent.name).filter(Boolean),
    runningAgents: running,
    recentActivity: recentActivityFromEvents(agents, agentEvents),
    waiting,
    activeCount: running.length,
    waitingCount: waiting.length,
    blockedCount: agents.filter((agent) => normalizeStatus(agent.status) === 'blocked').length
  };
}

function liveAgent(agent) {
  const meta = [
    agent.activity_event ? `Event: ${agent.activity_event}` : '',
    agent.updated_at ? `Updated: ${formatDisplayTime(agent.updated_at)}` : ''
  ].filter(Boolean).join(' · ');
  return `
    <div class="live-item">
      <div class="live-name">${escapeHtml(agent.display_name || agent.name)}</div>
      <div class="live-task">${escapeHtml(agent.current_task || agent.task || agent.notes || 'No current task recorded.')}</div>
      ${meta ? `<div class="live-meta">${escapeHtml(meta)}</div>` : ''}
    </div>
  `;
}

function renderActivityStack(data, limit = 4) {
  const items = data.runningAgents.length ? data.runningAgents : (data.recentActivity || []);
  if (items.length === 0) {
    return '<div class="empty-state">No agents are running right now; no recent hook activity is active.</div>';
  }
  return items.slice(0, limit).map(liveAgent).join('');
}

function renderRunningStack(data) {
  return renderActivityStack(data);
}

function chip(label, value, className = '') {
  if (!value) return '';
  return `<span class="chip ${escapeHtml(className)}">${escapeHtml(label)}: ${escapeHtml(value)}</span>`;
}

function commandCard(action, index, detailKey) {
  const statusClass = actionStatusClass(action.status);
  const title = readableActionTitle(action);
  const summary = readableActionSummary(action);
  const rawOutputs = rawItemOutputs(action);
  return `
    <article class="command-card ${escapeHtml(statusClass)}">
      <div class="command-main">
        <div class="command-index">${index + 1}</div>
        <div>
          <div class="command-title">${escapeHtml(title || 'Untitled action')}</div>
          <div class="chips" style="margin-top: 7px;">
            ${chip('Owner', action.owner)}
            ${chip('Priority', action.priority)}
            ${chip('Status', action.status, statusClass)}
          </div>
        </div>
      </div>
      ${summary ? `<div class="command-output primary">${escapeHtml(summary)}</div>` : ''}
      ${action.result ? `<div class="command-output">Result: ${escapeHtml(action.result)}</div>` : ''}
      ${action.updatedAt ? `<div class="command-output">Updated: ${escapeHtml(formatDisplayTime(action.updatedAt))}</div>` : ''}
      ${action.notes ? `<div class="command-output">Notes: ${escapeHtml(action.notes)}</div>` : ''}
      ${rawOutputs ? `<div class="command-output trace">Trace files: ${escapeHtml(rawOutputs)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function compactCommandCard(action, index, detailKey) {
  const statusClass = actionStatusClass(action.status);
  const title = readableActionTitle(action);
  const summary = readableActionSummary(action);
  return `
    <article class="command-card compact ${escapeHtml(statusClass)}">
      <div class="command-title">${index + 1}. ${escapeHtml(title || 'Untitled command')}</div>
      <div class="chips">
        ${chip('Owner', action.owner)}
        ${chip('Status', action.status, statusClass)}
      </div>
      ${summary ? `<div class="command-output primary">${escapeHtml(summary)}</div>` : ''}
      ${action.result ? `<div class="command-output">Result: ${escapeHtml(action.result)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function loopItem(title, copy = '', chipsHtml = '', detailKey = '') {
  return `
    <div class="loop-item">
      <div class="loop-item-title">${escapeHtml(title || '-')}</div>
      ${chipsHtml ? `<div class="chips">${chipsHtml}</div>` : ''}
      ${copy ? `<div class="loop-item-copy">${escapeHtml(copy)}</div>` : ''}
      ${detailKey ? `<div class="card-actions">${detailButton(detailKey)}</div>` : ''}
    </div>
  `;
}

function renderLoopResults(data) {
  const results = [...(data.loopSummary.results || [])].sort((a, b) => {
    const timeDiff = parseTimeMs(b.updated_at) - parseTimeMs(a.updated_at);
    if (timeDiff !== 0) return timeDiff;
    return String(b.title || b.summary || '').localeCompare(String(a.title || a.summary || ''));
  });
  if (results.length === 0 && data.loopSummary.outcome) {
    return loopItem('Loop outcome', data.loopSummary.outcome);
  }
  if (results.length === 0) {
    return '<div class="empty-state">No result recorded for this loop yet.</div>';
  }
  return results.slice(0, 4).map((result) => {
    const title = result.title || result.summary || 'Untitled result';
    const copy = result.summary || (Array.isArray(result.evidence_files) ? result.evidence_files.join(', ') : '');
    const key = registerDetail('loop_result', title, result);
    return loopItem(title, copy, chip('Status', result.status || 'recorded', actionStatusClass(result.status || 'done')), key);
  }).join('');
}

function renderLoopNextActions(data) {
  const next = data.loopNextActions.length ? data.loopNextActions : activeActions(data.actions).slice(0, 4);
  if (next.length === 0) {
    return '<div class="empty-state">No next action recorded.</div>';
  }
  return next.slice(0, 4).map((action) => {
    const meta = [
      chip('Owner', action.owner),
      chip('Priority', action.priority),
      chip('Status', action.status, actionStatusClass(action.status))
    ].join('');
    const key = registerDetail('next_action', action.action || 'Untitled action', action, commandUpdateCli(data, action));
    return loopItem(readableActionTitle(action), readableActionSummary(action), meta, key);
  }).join('');
}

function renderLoopSummary(data) {
  const loop = data.loopSummary;
  document.getElementById('loopGoal').textContent = loop.goal || '-';
  document.getElementById('loopSummary').textContent = loop.summary || 'No loop summary recorded.';
  document.getElementById('loopOutcome').textContent = loop.outcome || 'Not recorded';
  document.getElementById('loopMeta').innerHTML = [
    chip('Loop', loop.loop_id || '-'),
    chip('Status', loop.status || 'planned', actionStatusClass(loop.status || 'planned')),
    chip('Updated', formatDisplayTime(loop.last_updated || data.lastUpdated || '-'))
  ].join('');
  document.getElementById('loopResults').innerHTML = renderLoopResults(data);
  document.getElementById('loopNextActions').innerHTML = renderLoopNextActions(data);
}

function englishActionTitle(item) {
  return firstMeaningful([item], ['display_summary', 'action', 'title', 'summary', 'id']) || 'the next command';
}

function renderEnglishSummary(data) {
  const loop = data.loopSummary || {};
  const completed = Array.isArray(loop.completed_commands) ? loop.completed_commands : [];
  const results = Array.isArray(loop.results) ? loop.results : [];
  const reportTables = Array.isArray(data.reportSnapshot?.tables) ? data.reportSnapshot.tables : [];
  const reportFiles = Array.isArray(data.reportSnapshot?.latest_files) ? data.reportSnapshot.latest_files : [];
  const latestCompleted = completed.slice().reverse()[0] || data.completedActions[0] || null;
  const latestCompletedEvent = Array.isArray(data.completedEventActions) ? data.completedEventActions[0] : null;
  const latestResult = results.slice().reverse()[0] || null;
  const latestReportTable = reportTables.find((table) => Number(table.rows || 0) > 0) || reportTables[0] || null;
  const latestReportFile = reportFiles[0] || latestReportTable;
  const next = nextPromptAction(data);
  const completedCount = completed.length || data.completedActions.length || data.completedEventActions.length;

  const workSummary = latestCompleted
    ? [
        `${completedCount} completed item${completedCount === 1 ? '' : 's'} are recorded for this instruction.`,
        latestCompleted.id ? `Latest command: ${latestCompleted.id}.` : '',
        `${latestCompleted.owner_agent || latestCompleted.owner || 'Owner'} finished with status ${englishStatusLabel(latestCompleted.status || 'done')}.`,
        firstMeaningful([latestCompleted], ['result', 'action', 'notes']) || 'Inspect the command detail for the exact work.',
        rawItemOutputs(latestCompleted) ? `Outputs: ${rawItemOutputs(latestCompleted)}.` : ''
      ].filter(Boolean).join(' ')
    : latestCompletedEvent
      ? [
          `${completedCount} completion event${completedCount === 1 ? '' : 's'} are recorded for this instruction.`,
          `${latestCompletedEvent.owner_display || latestCompletedEvent.owner || 'Owner'} finished with status ${englishStatusLabel(latestCompletedEvent.status || 'done')}.`,
          firstMeaningful([latestCompletedEvent], ['result', 'action', 'notes']) || 'A completed event was recorded.',
          latestCompletedEvent.updatedAt ? `Recorded at ${formatDisplayTime(latestCompletedEvent.updatedAt)}.` : ''
        ].filter(Boolean).join(' ')
      : firstMeaningful([{ summary: loop.summary }, { summary: data.directorDecision }], ['summary']) || 'No completed work is recorded for this instruction yet.';

  const resultSummary = latestResult
    ? [
        `${results.length} result item${results.length === 1 ? '' : 's'} are recorded; latest status is ${englishStatusLabel(latestResult.status || 'done')}.`,
        firstMeaningful([latestResult], ['summary', 'title', 'notes']) || 'The latest result is recorded, but interpretation still needs detail.',
        Array.isArray(latestResult.evidence_files) && latestResult.evidence_files.length
          ? `Evidence: ${latestResult.evidence_files.slice(0, 3).join(', ')}.`
          : 'No evidence file is recorded yet.'
      ].filter(Boolean).join(' ')
    : latestReportTable
      ? [
          `${reportTables.length} result table${reportTables.length === 1 ? '' : 's'} are connected under 09_report.`,
          `Representative table: ${latestReportTable.path} with ${Number(latestReportTable.rows || 0)} data row${Number(latestReportTable.rows || 0) === 1 ? '' : 's'}.`,
          latestReportTable.updated_at ? `Last updated: ${formatDisplayTime(latestReportTable.updated_at)}.` : '',
          'Final result tables remain visible even when loop_summary is sparse.'
        ].filter(Boolean).join(' ')
      : latestReportFile
        ? [
            `${reportFiles.length} report file${reportFiles.length === 1 ? '' : 's'} detected under 09_report.`,
            `Latest file: ${latestReportFile.path}.`,
            latestReportFile.updated_at ? `Last updated: ${formatDisplayTime(latestReportFile.updated_at)}.` : ''
          ].filter(Boolean).join(' ')
        : firstMeaningful([{ summary: loop.outcome }], ['summary']) || 'No separate result analysis is recorded yet.';

  const nextSummary = next
    ? [
        `Next: ${displayAgentName(data, next.owner || 'director')} should run ${englishActionTitle(next)} with ${englishPriorityLabel(next.priority)} priority.`,
        next.id ? `Target command: ${next.id}.` : '',
        firstMeaningful([next], ['notes', 'why_now']) ? `Context: ${firstMeaningful([next], ['notes', 'why_now'])}` : '',
        String(next.done_when || '').trim() ? `Done when: ${next.done_when}` : 'No done condition is recorded yet.',
        rawItemOutputs(next) ? 'Inspect shows the supporting file paths.' : ''
      ].filter(Boolean).join(' ')
    : 'No next action is recorded yet. The director should choose the next command.';

  document.getElementById('koreanWorkSummary').textContent = workSummary;
  document.getElementById('koreanResultSummary').textContent = resultSummary;
  document.getElementById('koreanNextSummary').textContent = nextSummary;
}

function renderKoreanSummary(data) {
  updateSummaryCardLabels(data);
  if (!isKoreanSummary(data)) {
    renderEnglishSummary(data);
    return;
  }
  const loop = data.loopSummary || {};
  const completed = Array.isArray(loop.completed_commands) ? loop.completed_commands : [];
  const results = Array.isArray(loop.results) ? loop.results : [];
  const reportTables = Array.isArray(data.reportSnapshot?.tables) ? data.reportSnapshot.tables : [];
  const reportFiles = Array.isArray(data.reportSnapshot?.latest_files) ? data.reportSnapshot.latest_files : [];
  const latestCompleted = completed.slice().reverse()[0] || data.completedActions[0] || null;
  const latestCompletedEvent = Array.isArray(data.completedEventActions) ? data.completedEventActions[0] : null;
  const latestResult = results.slice().reverse()[0] || null;
  const latestReportTable = reportTables.find((table) => Number(table.rows || 0) > 0) || reportTables[0] || null;
  const latestReportFile = reportFiles[0] || latestReportTable;
  const next = nextPromptAction(data);
  const completedCount = completed.length || data.completedActions.length || data.completedEventActions.length;
  const workSummary = latestCompleted
    ? [
        `이번 instruction에서 완료로 기록된 작업은 ${completedCount}개입니다.`,
        latestCompleted.id ? `최근 완료 command는 ${latestCompleted.id}입니다.` : '',
        `${latestCompleted.owner_agent || latestCompleted.owner || '담당 에이전트'}가 ${koreanStatusLabel(latestCompleted.status || 'done')} 상태로 마쳤습니다.`,
        koreanMeaning(latestCompleted, ['result', 'action', 'notes'], '세부 작업은 command 상세에서 확인합니다.'),
        itemOutputs(latestCompleted) ? `산출물: ${itemOutputs(latestCompleted)}.` : ''
      ].filter(Boolean).join(' ')
    : latestCompletedEvent
      ? [
          `이번 instruction에서 완료 이벤트 ${completedCount}개가 기록됐습니다.`,
          `${latestCompletedEvent.owner_display || latestCompletedEvent.owner || '담당 에이전트'}가 ${koreanStatusLabel(latestCompletedEvent.status || 'done')} 상태로 마쳤습니다.`,
          koreanMeaning(latestCompletedEvent, ['result', 'action', 'notes'], latestCompletedEvent.action || '완료된 작업입니다.'),
          latestCompletedEvent.updatedAt ? `기록 시각: ${formatDisplayTime(latestCompletedEvent.updatedAt)}.` : ''
        ].filter(Boolean).join(' ')
    : koreanizeTask(loop.summary || data.directorDecision, '이번 instruction에서 완료한 작업 기록이 아직 없습니다.');
  const resultSummary = latestResult
    ? [
        `결과 항목은 ${results.length}개 기록되어 있고 최근 상태는 ${koreanStatusLabel(latestResult.status || 'done')}입니다.`,
        koreanMeaning(latestResult, ['summary', 'title', 'notes'], '최근 결과는 대시보드에 기록됐지만 자세한 해석은 아직 보강이 필요합니다.'),
        itemOutputs({ evidence_files: latestResult.evidence_files, outputs: latestResult.evidence_files }) ? `근거 파일: ${itemOutputs({ evidence_files: latestResult.evidence_files, outputs: latestResult.evidence_files })}.` : '근거 파일은 아직 기록되지 않았습니다.'
      ].filter(Boolean).join(' ')
    : latestReportTable
      ? [
          `09_report에는 결과표 ${reportTables.length}개가 연결되어 있습니다.`,
          `대표 결과는 ${humanReadableOutput(latestReportTable.path)}이고 ${Number(latestReportTable.rows || 0)}개 data row가 있습니다.`,
          latestReportTable.updated_at ? `최근 갱신: ${formatDisplayTime(latestReportTable.updated_at)}.` : '',
          'loop_summary 결과가 비어 있어도 최종 산출물 표는 Report Results에서 바로 확인할 수 있습니다.'
        ].filter(Boolean).join(' ')
      : latestReportFile
        ? [
            `09_report 결과 파일이 ${reportFiles.length}개 감지됐습니다.`,
            `최근 파일은 ${humanReadableOutput(latestReportFile.path)}입니다.`,
            latestReportFile.updated_at ? `최근 갱신: ${formatDisplayTime(latestReportFile.updated_at)}.` : ''
          ].filter(Boolean).join(' ')
    : koreanizeTask(loop.outcome, '아직 별도 결과 분석이 기록되지 않았습니다.');
  const nextSummary = next
    ? [
        `다음 할 일: ${displayAgentName(data, next.owner || 'director')}가 ${koreanPriorityLabel(next.priority)} 우선순위로 ${readableActionTitle(next)}을 진행합니다.`,
        next.id ? `대상 command는 ${next.id}입니다.` : '',
        hasKorean(next.notes) ? `맥락: ${next.notes}` : '',
        completionText(next) || '완료 기준은 아직 기록되지 않았습니다.',
        rawItemOutputs(next) ? '자세한 파일 경로는 Inspect에서 확인합니다.' : ''
      ].filter(Boolean).join(' ')
    : '다음 작업이 아직 기록되지 않았습니다. director가 다음 command를 정해야 합니다.';

  document.getElementById('koreanWorkSummary').textContent = workSummary;
  document.getElementById('koreanResultSummary').textContent = resultSummary;
  document.getElementById('koreanNextSummary').textContent = nextSummary;
}

function latestCompletedWork(data) {
  const loopCompleted = Array.isArray(data.loopSummary?.completed_commands) ? data.loopSummary.completed_commands : [];
  return loopCompleted.slice().reverse()[0] || data.completedActions[0] || data.completedEventActions?.[0] || null;
}

function meaningfulLoopSummary(summary) {
  const value = String(summary || '').trim();
  if (!value) return '';
  const lower = value.toLowerCase();
  if (lower.includes('no completed loop has been recorded')) return '';
  if (lower.includes('update state/loop_summary.json')) return '';
  if (lower.includes('no loop summary recorded')) return '';
  return value;
}

function overviewAutoSummary(data) {
  const loop = data.loopSummary || {};
  const parts = [];
  const loopSummary = meaningfulLoopSummary(loop.summary || data.directorDecision);
  if (loopSummary) parts.push(loopSummary);

  const completed = latestCompletedWork(data);
  if (completed) {
    const title = readableActionTitle(completed) || completed.action || completed.result || completed.id || 'completed work';
    const owner = completed.owner_agent || completed.owner || completed.owner_display || '';
    const result = completed.result || completed.notes || '';
    parts.push([
      `최근 완료 작업: ${title}.`,
      owner ? `담당: ${displayAgentName(data, owner)}.` : '',
      result && result !== title ? `결과: ${result}.` : ''
    ].filter(Boolean).join(' '));
  }

  const loopResults = Array.isArray(loop.results) ? loop.results : [];
  const latestResult = loopResults.slice().reverse()[0] || null;
  if (latestResult) {
    parts.push([
      `최근 결과: ${latestResult.title || latestResult.summary || '기록된 결과'}.`,
      latestResult.summary && latestResult.summary !== latestResult.title ? latestResult.summary : ''
    ].filter(Boolean).join(' '));
  } else {
    const reportTables = Array.isArray(data.reportSnapshot?.tables) ? data.reportSnapshot.tables : [];
    const latestTable = reportTables.find((table) => Number(table.rows || 0) > 0) || reportTables[0] || null;
    if (latestTable) {
      const rows = Number(latestTable.rows || 0);
      parts.push(`09_report 결과표 확인됨: ${latestTable.path || latestTable.name}에 ${rows}개 data row가 있습니다.`);
    }
  }

  if (parts.length) return parts.join(' ');
  return '아직 loop summary나 report result가 기록되지 않았습니다.';
}

function overviewItem(title, body = '', meta = '') {
  return `
    <div class="overview-item">
      <div class="overview-item-title">${escapeHtml(title || '-')}</div>
      ${body ? `<div class="overview-item-body">${escapeHtml(body)}</div>` : ''}
      ${meta ? `<div class="overview-item-meta">${escapeHtml(meta)}</div>` : ''}
    </div>
  `;
}

function overviewEmpty(message) {
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderOverviewNow(data) {
  const running = data.runningAgents.length ? data.runningAgents : (data.recentActivity || []);
  if (running.length === 0) {
    const next = nextPromptAction(data);
    return overviewEmpty(next
      ? 'No agent is running right now. The next command is ready to start.'
      : 'No active work is recorded. Ask the director to select the next command.');
  }
  return running.slice(0, 3).map((agent) => overviewItem(
    agent.display_name || agent.name || 'Agent',
    agent.current_task || agent.task || agent.notes || 'Activity recorded.',
    [
      koreanStatusLabel(agent.status || 'running'),
      agent.updated_at ? `updated ${formatDisplayTime(agent.updated_at)}` : ''
    ].filter(Boolean).join(' · ')
  )).join('');
}

function renderOverviewCompleted(data) {
  const latest = latestCompletedWork(data);
  const completed = [
    latest,
    ...data.completedActions.filter((item) => item !== latest)
  ].filter(Boolean);
  if (completed.length === 0) {
    return overviewEmpty('No completed command is recorded yet.');
  }
  return completed.slice(0, 3).map((item) => overviewItem(
    readableActionTitle(item) || item.id || 'Completed work',
    item.result || readableActionSummary(item) || item.notes || 'Marked complete.',
    [
      item.id || '',
      item.owner_agent || item.owner || item.owner_display || '',
      item.updatedAt ? formatDisplayTime(item.updatedAt) : ''
    ].filter(Boolean).join(' · ')
  )).join('');
}

function renderOverviewResults(data) {
  const loopResults = Array.isArray(data.loopSummary?.results) ? data.loopSummary.results : [];
  const tables = Array.isArray(data.reportSnapshot?.tables) ? data.reportSnapshot.tables : [];
  const files = Array.isArray(data.reportSnapshot?.latest_files) ? data.reportSnapshot.latest_files : [];
  const items = [];
  const latestResult = loopResults.slice().reverse()[0];
  if (latestResult) {
    items.push(overviewItem(
      latestResult.title || latestResult.summary || 'Loop result',
      latestResult.summary || 'Result recorded in loop_summary.',
      latestResult.status ? koreanStatusLabel(latestResult.status) : 'recorded'
    ));
  }
  tables.slice(0, 3).forEach((table) => {
    items.push(overviewItem(
      humanReadableOutput(table.path || table.name || 'result table'),
      `${Number(table.rows || 0)} data row${Number(table.rows || 0) === 1 ? '' : 's'} in ${table.path || table.name}.`,
      table.updated_at ? `updated ${formatDisplayTime(table.updated_at)}` : '09_report/results'
    ));
  });
  if (items.length === 0 && files.length) {
    files.slice(0, 2).forEach((file) => {
      items.push(overviewItem(
        humanReadableOutput(file.path || file.name),
        file.path || file.name || 'Report artifact detected.',
        file.updated_at ? `updated ${formatDisplayTime(file.updated_at)}` : '09_report'
      ));
    });
  }
  return items.length ? items.join('') : overviewEmpty('No final report artifact or result table is visible yet.');
}

function blockedOverviewItems(data) {
  const items = [];
  (data.activeActions || [])
    .filter((action) => actionStatusClass(action.status) === 'blocked')
    .forEach((action) => {
      items.push({
        title: readableActionTitle(action) || action.id || 'Blocked command',
        body: readableActionSummary(action) || action.notes || 'Command is blocked.',
        meta: [action.id, action.owner].filter(Boolean).join(' · ')
      });
    });
  (data.agentMessages?.messages || [])
    .filter((message) => normalizeStatus(message.kind) === 'blocker' && !['resolved', 'cancelled'].includes(normalizeStatus(message.status)))
    .forEach((message) => {
      items.push({
        title: message.subject || 'Open blocker message',
        body: message.body || message.required_response || 'Agent blocker is open.',
        meta: [message.from_agent && message.to_agent ? `${message.from_agent} -> ${message.to_agent}` : '', message.priority].filter(Boolean).join(' · ')
      });
    });
  (data.agents || [])
    .filter((agent) => normalizeStatus(agent.status) === 'blocked')
    .forEach((agent) => {
      items.push({
        title: agent.display_name || agent.name || 'Blocked agent',
        body: agent.current_task || agent.notes || 'Agent status is blocked.',
        meta: agent.stage || ''
      });
    });
  return items;
}

function renderOverviewBlocked(data) {
  const items = blockedOverviewItems(data);
  if (items.length === 0) {
    return overviewEmpty('No blocker is currently recorded.');
  }
  return items.slice(0, 3).map((item) => overviewItem(item.title, item.body, item.meta)).join('');
}

function blockerCategory(item) {
  const haystack = `${item.title || ''} ${item.body || ''} ${item.meta || ''}`.toLowerCase();
  if (haystack.includes('dataset') || haystack.includes('data') || haystack.includes('metric')) return 'Data';
  if (haystack.includes('experiment') || haystack.includes('run') || haystack.includes('gpu')) return 'Experiment';
  if (haystack.includes('paper') || haystack.includes('write') || haystack.includes('report')) return 'Writing';
  if (haystack.includes('claim') || haystack.includes('evidence') || haystack.includes('question') || haystack.includes('approval')) return 'Research';
  return 'Workflow';
}

function blockerTriageRows(data) {
  const commandBlockers = (data.activeActions || [])
    .filter((action) => actionStatusClass(action.status) === 'blocked')
    .map((action) => ({
      category: 'Workflow',
      title: readableActionTitle(action) || action.id || 'Blocked command',
      body: readableActionSummary(action) || action.notes || 'Command is blocked.',
      owner: action.owner ? displayAgentName(data, action.owner) : 'unassigned',
      next: completionText(action) || 'Resolve the command blocker, then mark the command through python -m scripts.commands.review.command_queue.',
      item: action,
      cli: commandUpdateCli(data, action)
    }));
  const messageBlockers = (data.agentMessages?.messages || [])
    .filter((message) => normalizeStatus(message.kind) === 'blocker' && !['resolved', 'cancelled'].includes(normalizeStatus(message.status)))
    .map((message) => ({
      category: blockerCategory({ title: message.subject, body: message.body, meta: message.related_command_id }),
      title: message.subject || 'Open blocker message',
      body: message.body || message.required_response || 'Agent blocker is open.',
      owner: message.to_agent ? displayAgentName(data, message.to_agent) : 'director',
      next: message.required_response || 'Respond to the blocker message or update the related command.',
      item: message,
      cli: messageCli(data, message)
    }));
  const agentBlockers = (data.agents || [])
    .filter((agent) => normalizeStatus(agent.status) === 'blocked')
    .map((agent) => ({
      category: 'Research',
      title: agent.display_name || agent.name || 'Blocked agent',
      body: agent.current_task || agent.notes || 'Agent status is blocked.',
      owner: agent.name || 'agent',
      next: 'Update the agent through python -m scripts.commands.agents.agent_status after the blocker is resolved.',
      item: agent,
      cli: agentHeartbeatCli(data, agent)
    }));
  return [...commandBlockers, ...messageBlockers, ...agentBlockers];
}

function blockerTriageCard(data, row, index) {
  const key = registerDetail('blocker_triage', row.title || `Blocker ${index + 1}`, row.item || row, row.cli || '');
  return `
    <article class="blocker-triage-card ${escapeHtml(row.category.toLowerCase())}">
      <div class="blocker-triage-head">
        <span class="status-pill blocked">${escapeHtml(row.category)}</span>
        <span class="hint">${escapeHtml(row.owner || 'unassigned')}</span>
      </div>
      <div class="run-title">${escapeHtml(row.title || 'Blocker')}</div>
      <div class="command-output primary">${escapeHtml(row.body || 'No blocker detail recorded.')}</div>
      <div class="command-output">Next: ${escapeHtml(row.next || 'Resolve and update dashboard state.')}</div>
      <div class="card-actions">
        ${detailButton(key)}
        ${row.cli ? copyButton(key) : ''}
      </div>
    </article>
  `;
}

function renderBlockerTriage(data) {
  const rows = blockerTriageRows(data);
  const filtered = applyInteractiveFilters(rows);
  document.getElementById('blockerTriageCount').textContent = `${filtered.length}/${rows.length} blocker${rows.length === 1 ? '' : 's'}`;
  document.getElementById('blockerTriageList').innerHTML = filtered.length
    ? filtered.slice(0, 10).map((row, index) => blockerTriageCard(data, row, index)).join('')
    : '<div class="empty-state">No blocker requires triage right now.</div>';
}

function renderOverviewNext(data) {
  const next = nextPromptAction(data);
  if (!next) {
    return overviewEmpty('No next command is recorded. The director should inspect state and choose one.');
  }
  return overviewItem(
    readableActionTitle(next) || 'Next command',
    readableActionSummary(next) || next.action || 'Continue the highest-priority open command.',
    [
      next.id || 'loop_summary.next_actions',
      next.owner ? displayAgentName(data, next.owner) : 'director',
      next.priority || ''
    ].filter(Boolean).join(' · ')
  );
}

function renderOverviewBoard(data) {
  document.getElementById('overviewNow').innerHTML = renderOverviewNow(data);
  document.getElementById('overviewCompleted').innerHTML = renderOverviewCompleted(data);
  document.getElementById('overviewResults').innerHTML = renderOverviewResults(data);
  document.getElementById('overviewBlocked').innerHTML = renderOverviewBlocked(data);
  document.getElementById('overviewNext').innerHTML = renderOverviewNext(data);
  document.getElementById('overviewNextPromptText').textContent = buildNextPrompt(data);
}

const researchPhases = [
  { key: 'brief', label: 'Brief', match: ['brief', 'motivation', 'problem'] },
  { key: 'literature', label: 'Literature', match: ['literature', 'related'] },
  { key: 'planning', label: 'Plan', match: ['planning', 'plan', 'director'] },
  { key: 'design', label: 'Design', match: ['design', 'hypothesis'] },
  { key: 'experiment', label: 'Experiment', match: ['experiment', 'run', 'code'] },
  { key: 'analysis', label: 'Analysis', match: ['analysis', 'result'] },
  { key: 'writing', label: 'Writing', match: ['writing', 'draft'] },
  { key: 'review', label: 'Review', match: ['review', 'critique', 'venue'] },
  { key: 'report', label: 'Report', match: ['report', 'final'] }
];

function currentPhaseIndex(data) {
  const haystack = [
    data.currentStage,
    data.loopSummary?.goal,
    data.loopSummary?.summary,
    nextPromptAction(data)?.action,
    nextPromptAction(data)?.owner,
    ...(data.runningAgents || []).map((agent) => agent.stage || agent.current_task || '')
  ].join(' ').toLowerCase();
  const index = researchPhases.findIndex((phase) => phase.match.some((token) => haystack.includes(token)));
  return index === -1 ? 0 : index;
}

function hasTableRows(data, namePart) {
  return (data.reportSnapshot?.tables || []).some((table) => {
    const path = String(table.path || table.name || '').toLowerCase();
    return path.includes(namePart) && Number(table.rows || 0) > 0;
  });
}

function tableRowCount(data, namePart) {
  return (data.reportSnapshot?.tables || []).reduce((total, table) => {
    const path = String(table.path || table.name || '').toLowerCase();
    return path.includes(namePart) ? total + Number(table.rows || 0) : total;
  }, 0);
}

function tableByName(data, namePart) {
  const needle = String(namePart || '').toLowerCase();
  return (data.reportSnapshot?.tables || []).find((table) => {
    const path = String(table.path || table.name || '').toLowerCase();
    return path.includes(needle);
  }) || null;
}

function tableObjects(table) {
  const columns = Array.isArray(table?.columns) ? table.columns : [];
  const rows = Array.isArray(table?.preview_rows) ? table.preview_rows : [];
  return rows.map((row) => {
    const record = {};
    columns.forEach((column, index) => {
      record[column] = row[index] ?? '';
    });
    return record;
  });
}

function dataSourceMissing(data) {
  return data.dataSources?.coverage?.required_missing || [];
}

function runReadinessVerdict(data) {
  const blockers = blockedOverviewItems(data);
  const next = nextPromptAction(data);
  const missingSources = dataSourceMissing(data);
  const evidenceRows = tableRowCount(data, 'claim_evidence');
  const experimentRows = tableRowCount(data, 'experiment_results');
  if (missingSources.length) {
    return {
      label: 'Missing source',
      status: 'blocker',
      detail: `${missingSources.length} required dashboard source${missingSources.length === 1 ? '' : 's'} missing.`
    };
  }
  if (blockers.length) {
    return {
      label: 'Blocked',
      status: 'blocker',
      detail: `${blockers.length} blocker${blockers.length === 1 ? '' : 's'} need triage before the next run.`
    };
  }
  if (!next) {
    return {
      label: 'Needs next command',
      status: 'waiting',
      detail: 'The project has context, but the director has not selected the next executable command.'
    };
  }
  if (!evidenceRows && experimentRows) {
    return {
      label: 'Needs evidence',
      status: 'warn',
      detail: 'Experiment rows exist, but claim-evidence rows are not populated yet.'
    };
  }
  if (data.runningAgents.length || data.activeActions.some((action) => actionStatusClass(action.status) === 'running')) {
    return {
      label: 'Running',
      status: 'running',
      detail: 'Work is already in progress; monitor updates before launching another run.'
    };
  }
  return {
    label: 'Ready to run',
    status: 'pass',
    detail: 'Required sources are loaded, no blockers are open, and the next command is selected.'
  };
}

function renderRunReadinessGate(data) {
  const verdict = runReadinessVerdict(data);
  const next = nextPromptAction(data);
  const items = [
    {
      title: verdict.label,
      body: verdict.detail,
      meta: verdict.status
    },
    {
      title: 'Next command',
      body: next ? readableActionTitle(next) : 'No next command selected.',
      meta: next ? [next.id, next.owner ? displayAgentName(data, next.owner) : 'director', next.priority].filter(Boolean).join(' · ') : 'director decision needed'
    },
    {
      title: 'Evidence',
      body: `${tableRowCount(data, 'claim_evidence')} claim row${tableRowCount(data, 'claim_evidence') === 1 ? '' : 's'} · ${tableRowCount(data, 'experiment_results')} experiment row${tableRowCount(data, 'experiment_results') === 1 ? '' : 's'}`,
      meta: data.reportSnapshot?.updated_at ? `updated ${formatDisplayTime(data.reportSnapshot.updated_at)}` : '09_report/results'
    },
    {
      title: 'Sources',
      body: `${data.dataSources?.coverage?.available || 0}/${data.dataSources?.coverage?.total || 0} dashboard sources available`,
      meta: dataSourceMissing(data).length ? `missing ${dataSourceMissing(data).join(', ')}` : 'required sources loaded'
    }
  ];
  document.getElementById('runReadinessVerdict').textContent = verdict.label;
  document.getElementById('runReadinessVerdict').className = `readiness-verdict ${escapeHtml(verdict.status)}`;
  document.getElementById('runReadinessSummary').textContent = verdict.detail;
  document.getElementById('runReadinessGate').innerHTML = items
    .map((item) => `<div class="readiness-decision ${escapeHtml(verdict.status)}">${overviewItem(item.title, item.body, item.meta)}</div>`)
    .join('');
}

function readinessChecks(data) {
  const next = nextPromptAction(data);
  const activeCount = data.activeActions.length;
  const blockedCount = blockedOverviewItems(data).length;
  const reportTables = data.reportSnapshot?.tables || [];
  const experimentRuns = data.experimentRuns || [];
  const hasReadme = Boolean(data.reportSnapshot?.readme_path);
  return [
    {
      title: 'Question',
      status: data.currentStage && data.currentStage !== '-' ? 'pass' : 'waiting',
      detail: data.currentStage && data.currentStage !== '-' ? `Current stage: ${data.currentStage}` : 'No stage recorded.'
    },
    {
      title: 'Next Task',
      status: next ? 'pass' : 'blocker',
      detail: next ? readableActionTitle(next) : 'Director must choose the next command.'
    },
    {
      title: 'Work Queue',
      status: blockedCount ? 'blocker' : activeCount ? 'warn' : 'pass',
      detail: blockedCount ? `${blockedCount} blocker${blockedCount === 1 ? '' : 's'} need attention.` : `${activeCount} open command${activeCount === 1 ? '' : 's'}.`
    },
    {
      title: 'Evidence Tables',
      status: reportTables.some((table) => Number(table.rows || 0) > 0) ? 'pass' : 'warn',
      detail: `${reportTables.length} table${reportTables.length === 1 ? '' : 's'}, ${reportTables.reduce((sum, table) => sum + Number(table.rows || 0), 0)} data rows.`
    },
    {
      title: 'Claims',
      status: hasTableRows(data, 'claim_evidence') ? 'pass' : 'warn',
      detail: `${tableRowCount(data, 'claim_evidence')} claim row${tableRowCount(data, 'claim_evidence') === 1 ? '' : 's'} visible.`
    },
    {
      title: 'Final Report',
      status: hasReadme ? 'pass' : 'waiting',
      detail: hasReadme ? '09_report/README.md is visible.' : 'No report README visible.'
    },
    {
      title: 'Experiments',
      status: experimentRuns.some((run) => ['succeeded', 'done', 'completed'].includes(normalizeStatus(run.status))) ? 'pass' : experimentRuns.length ? 'warn' : 'waiting',
      detail: `${experimentRuns.length} run_state file${experimentRuns.length === 1 ? '' : 's'} loaded.`
    }
  ];
}

function renderResearchReadiness(data) {
  const checks = readinessChecks(data);
  const passCount = checks.filter((check) => check.status === 'pass').length;
  const score = Math.round((passCount / checks.length) * 100);
  const blockers = checks.filter((check) => check.status === 'blocker').length;
  document.getElementById('readinessScore').textContent = `${score}%`;
  document.getElementById('readinessSummary').textContent = blockers
    ? `${blockers} blocker${blockers === 1 ? '' : 's'} before the workflow is research-ready`
    : 'No critical dashboard blockers';
  document.getElementById('readinessGrid').innerHTML = checks.map((check) => `
    <div class="readiness-check ${escapeHtml(check.status)}">
      <div class="readiness-check-title">${escapeHtml(check.title)}</div>
      <div class="readiness-check-copy">${escapeHtml(check.detail)}</div>
    </div>
  `).join('');
}

function renderResearchPhaseTrack(data) {
  const currentIndex = currentPhaseIndex(data);
  document.getElementById('researchPhaseTrack').innerHTML = researchPhases.map((phase, index) => {
    const state = index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'waiting';
    const meta = state === 'current' ? 'current focus' : state === 'done' ? 'has context' : 'upcoming';
    return `
      <div class="phase-step ${state}">
        <div class="phase-step-title">${escapeHtml(phase.label)}</div>
        <div class="phase-step-meta">${escapeHtml(meta)}</div>
      </div>
    `;
  }).join('');
}

function commandBoardLanes(data) {
  const blocked = data.activeActions.filter((action) => actionStatusClass(action.status) === 'blocked');
  const running = data.activeActions.filter((action) => actionStatusClass(action.status) === 'running');
  const queued = data.activeActions.filter((action) => !blocked.includes(action) && !running.includes(action));
  return [
    { title: 'Running', items: running, empty: 'No command is running.' },
    { title: 'Queued', items: queued, empty: 'No queued command.' },
    { title: 'Blocked', items: blocked, empty: 'No blocked command.' },
    { title: 'Completed', items: data.completedActions.slice(0, 5), empty: 'No completed command.' }
  ];
}

function renderCommandBoard(data) {
  const lanes = commandBoardLanes(data);
  const total = lanes.reduce((sum, lane) => sum + lane.items.length, 0);
  document.getElementById('commandBoardCount').textContent = `${total} command${total === 1 ? '' : 's'}`;
  document.getElementById('commandBoard').innerHTML = lanes.map((lane) => `
    <div class="command-lane">
      <div class="command-lane-head">
        <span>${escapeHtml(lane.title)}</span>
        <span class="hint">${lane.items.length}</span>
      </div>
      <div class="command-lane-body">
        ${lane.items.length ? lane.items.slice(0, 5).map((action, index) => {
          const key = registerDetail('command_board', action.action || `Command ${index + 1}`, action, commandUpdateCli(data, action));
          return compactCommandCard(action, index, key);
        }).join('') : overviewEmpty(lane.empty)}
      </div>
    </div>
  `).join('');
}

function runCard(run, detailKey) {
  const status = normalizeStatus(run.status || 'planned');
  const summary = run.display_summary || run.current_step || 'No run step recorded.';
  const judgement = run.judgement || run.notes || '';
  const nextAction = run.next_action || '';
  return `
    <article class="run-card ${escapeHtml(status)}">
      <div class="run-title">${escapeHtml(run.exp_id || 'unknown_exp')}</div>
      <div class="chips">
        ${chip('Status', status, status)}
        ${chip('Owner', run.owner_agent || '')}
        ${chip('GPU', run.gpu_type || '')}
        ${chip('Node', run.node || '')}
      </div>
      <div class="command-output primary">${escapeHtml(summary)}</div>
      ${judgement ? `<div class="command-output">판정: ${escapeHtml(judgement)}</div>` : ''}
      ${nextAction ? `<div class="command-output">다음 조치: ${escapeHtml(nextAction)}</div>` : ''}
      <div class="command-output">Updated: ${escapeHtml(formatDisplayTime(run.updated_at || '-'))}</div>
      ${run.tmux_session ? `<div class="command-output">tmux: ${escapeHtml(run.tmux_session)}</div>` : ''}
      ${run.slurm_job_name ? `<div class="command-output">SLURM: ${escapeHtml(run.slurm_job_name)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function gpuJobCli(data, job) {
  if (!job?.id) return `python -m scripts.commands.experiments.gpu_scheduler list --project ${shellQuote(projectNameForCli(data))}`;
  return [
    'python -m scripts.commands.experiments.gpu_scheduler update',
    `--project ${shellQuote(projectNameForCli(data))}`,
    `--id ${shellQuote(job.id)}`,
    `--status ${shellQuote(job.status || 'running')}`,
    `--note ${shellQuote('Progress update.')}`
  ].join(' ');
}

function gpuJobCard(job, detailKey) {
  const status = normalizeStatus(job.status || 'queued');
  const title = job.id || job.exp_id || 'gpu_job';
  const summary = job.command || job.notes || 'No GPU command recorded.';
  return `
    <article class="run-card ${escapeHtml(status)}">
      <div class="run-title">${escapeHtml(title)}</div>
      <div class="chips">
        ${chip('Status', status, status)}
        ${chip('Exp', job.exp_id || '')}
        ${chip('GPU', `${job.gpu_type || 'auto'} x${job.gpus || 1}`)}
        ${chip('Priority', job.priority || '')}
      </div>
      <div class="command-output primary">${escapeHtml(summary)}</div>
      ${job.tmux_session ? `<div class="command-output">tmux: ${escapeHtml(job.tmux_session)}</div>` : ''}
      ${job.slurm_job_name ? `<div class="command-output">SLURM: ${escapeHtml(job.slurm_job_name)}</div>` : ''}
      ${job.result_path ? `<div class="command-output trace">Result: ${escapeHtml(job.result_path)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderGpuQueue(data) {
  const jobs = Array.isArray(data.gpuQueue?.jobs) ? data.gpuQueue.jobs : [];
  const filtered = applyInteractiveFilters(jobs);
  document.getElementById('gpuQueueCount').textContent = `${filtered.length}/${jobs.length} job${jobs.length === 1 ? '' : 's'}`;
  document.getElementById('gpuQueueList').innerHTML = filtered.length
    ? filtered.slice(0, 8).map((job, index) => {
        const key = registerDetail('gpu_job', job.id || `GPU job ${index + 1}`, job, gpuJobCli(data, job));
        return gpuJobCard(job, key);
      }).join('')
    : '<div class="empty-state">No GPU jobs are queued or running.</div>';
}

function registryCard(kind, item, detailKey) {
  const status = normalizeStatus(item.status || 'candidate');
  const title = item.id || item.name || kind;
  const subtitle = kind === 'dataset'
    ? [item.name, item.split, item.source].filter(Boolean).join(' · ')
    : [item.name, item.direction, item.implementation].filter(Boolean).join(' · ');
  return `
    <article class="run-card ${escapeHtml(status)}">
      <div class="run-title">${escapeHtml(title)}</div>
      <div class="chips">
        ${chip('Kind', kind)}
        ${chip('Status', status, actionStatusClass(status))}
      </div>
      <div class="command-output primary">${escapeHtml(subtitle || 'No registry detail recorded.')}</div>
      <div class="card-actions">${detailButton(detailKey)}</div>
    </article>
  `;
}

function renderRegistry(data) {
  const datasets = Array.isArray(data.datasetRegistry?.datasets) ? data.datasetRegistry.datasets : [];
  const metrics = Array.isArray(data.metricRegistry?.metrics) ? data.metricRegistry.metrics : [];
  const items = [
    ...datasets.map((item) => ({ kind: 'dataset', item })),
    ...metrics.map((item) => ({ kind: 'metric', item }))
  ];
  const filtered = applyInteractiveFilters(items.map((entry) => ({ ...entry.item, kind: entry.kind })));
  document.getElementById('registryCount').textContent = `${datasets.length} dataset${datasets.length === 1 ? '' : 's'} · ${metrics.length} metric${metrics.length === 1 ? '' : 's'}`;
  document.getElementById('registryGrid').innerHTML = filtered.length
    ? filtered.slice(0, 8).map((item, index) => {
        const key = registerDetail(`${item.kind}_registry`, item.id || `${item.kind} ${index + 1}`, item);
        return registryCard(item.kind, item, key);
      }).join('')
    : '<div class="empty-state">No dataset or metric registry rows yet.</div>';
}

function normalizeAgentMessages(raw, project) {
  const fallback = {
    project,
    schema_version: 1,
    last_updated: '',
    messages: []
  };
  const data = raw && typeof raw === 'object' ? raw : fallback;
  return {
    ...fallback,
    ...data,
    messages: Array.isArray(data.messages) ? data.messages : []
  };
}

function normalizeAgentVotes(raw, project) {
  const fallback = {
    project,
    schema_version: 1,
    last_updated: '',
    decisions: []
  };
  const data = raw && typeof raw === 'object' ? raw : fallback;
  return {
    ...fallback,
    ...data,
    decisions: Array.isArray(data.decisions) ? data.decisions : []
  };
}

function normalizePatternMemory(raw, project) {
  const fallback = {
    project,
    schema_version: 1,
    last_updated: '',
    patterns: []
  };
  const data = raw && typeof raw === 'object' ? raw : fallback;
  return {
    ...fallback,
    ...data,
    patterns: Array.isArray(data.patterns) ? data.patterns : []
  };
}

function normalizeRalphLoop(raw, project) {
  const fallback = {
    project,
    schema_version: 1,
    last_updated: '',
    active_run_id: '',
    runs: []
  };
  const data = raw && typeof raw === 'object' ? raw : fallback;
  return {
    ...fallback,
    ...data,
    runs: Array.isArray(data.runs) ? data.runs : []
  };
}

function normalizeReportSnapshot(raw) {
  const data = raw && typeof raw === 'object' ? raw : {};
  return {
    readme_path: data.readme_path || '',
    readme_excerpt: data.readme_excerpt || '',
    tables: Array.isArray(data.tables) ? data.tables : [],
    latest_files: Array.isArray(data.latest_files) ? data.latest_files : [],
    updated_at: data.updated_at || ''
  };
}

function normalizeDataSources(raw) {
  const data = raw && typeof raw === 'object' ? raw : {};
  const sources = Array.isArray(data.sources) ? data.sources : [];
  const available = Number(data.coverage?.available ?? sources.filter((source) => source.status === 'available').length);
  const total = Number(data.coverage?.total ?? sources.length);
  return {
    generated_at: data.generated_at || '',
    last_source_update: data.last_source_update || '',
    coverage: {
      available,
      total,
      required_missing: Array.isArray(data.coverage?.required_missing) ? data.coverage.required_missing : []
    },
    sources
  };
}

function messageCli(data, message) {
  const project = shellQuote(data.project || 'template');
  if (!message?.id) return `python -m scripts.commands.agents.agent_messages list --project ${project}`;
  if (normalizeStatus(message.status) === 'resolved') {
    return `python -m scripts.commands.agents.agent_messages list --project ${project} --agent ${shellQuote(message.to_agent || '')}`;
  }
  return [
    'python -m scripts.commands.agents.agent_messages respond',
    `--project ${project}`,
    `--id ${shellQuote(message.id)}`,
    `--from-agent ${shellQuote(message.to_agent || '')}`,
    '--response "<write response>"'
  ].join(' ');
}

function messageCard(message, index, detailKey) {
  const status = normalizeStatus(message.status || 'open');
  const statusClass = actionStatusClass(status);
  const route = `${message.from_agent || '?'} -> ${message.to_agent || '?'}`;
  const related = [
    message.related_command_id ? `command ${message.related_command_id}` : '',
    message.related_claim_id ? `claim ${message.related_claim_id}` : '',
    message.related_exp_id ? `experiment ${message.related_exp_id}` : ''
  ].filter(Boolean).join(', ');
  return `
    <article class="command-card ${escapeHtml(statusClass)}">
      <div class="command-main">
        <div class="command-index">${index + 1}</div>
        <div>
          <div class="command-title">${escapeHtml(message.subject || 'Untitled message')}</div>
          <div class="chips" style="margin-top: 7px;">
            ${chip('Route', route)}
            ${chip('Kind', message.kind || 'request')}
            ${chip('Priority', message.priority || 'medium')}
            ${chip('Status', status, statusClass)}
          </div>
        </div>
      </div>
      ${message.body ? `<div class="command-output primary">${escapeHtml(message.body)}</div>` : ''}
      ${message.required_response ? `<div class="command-output">Required response: ${escapeHtml(message.required_response)}</div>` : ''}
      ${message.response ? `<div class="command-output">Response: ${escapeHtml(message.response)}</div>` : ''}
      ${related ? `<div class="command-output trace">Related: ${escapeHtml(related)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderAgentMessages(data) {
  const messages = Array.isArray(data.agentMessages?.messages) ? data.agentMessages.messages : [];
  const activeMessages = messages.filter((message) => !['resolved', 'cancelled'].includes(normalizeStatus(message.status)));
  const filtered = applyInteractiveFilters(activeMessages);
  document.getElementById('messageCount').textContent = `${filtered.length}/${activeMessages.length} open`;
  document.getElementById('agentMessages').innerHTML = filtered.length
    ? filtered.slice(0, 8).map((message, index) => {
        const key = registerDetail('agent_message', message.subject || `Message ${index + 1}`, message, messageCli(data, message));
        return messageCard(message, index, key);
      }).join('')
    : '<div class="empty-state">No open agent-to-agent messages.</div>';
}

function voteCounts(decision) {
  const counts = { approve: 0, reject: 0, abstain: 0 };
  (decision.votes || []).forEach((vote) => {
    const value = normalizeStatus(vote.vote);
    if (Object.prototype.hasOwnProperty.call(counts, value)) counts[value] += 1;
  });
  return counts;
}

function voteCli(data, decision) {
  const project = shellQuote(projectNameForCli(data));
  if (!decision?.id) return `python -m scripts.commands.agents.agent_vote status --project ${project}`;
  return `python -m scripts.commands.agents.agent_vote status --project ${project} --id ${shellQuote(decision.id)}`;
}

function voteCard(decision, detailKey) {
  const status = normalizeStatus(decision.status || 'open');
  const counts = voteCounts(decision);
  const voters = (decision.required_voters || []).join(', ');
  return `
    <article class="run-card ${escapeHtml(actionStatusClass(status))}">
      <div class="run-title">${escapeHtml(decision.title || decision.id || 'vote decision')}</div>
      <div class="chips">
        ${chip('Status', status, actionStatusClass(status))}
        ${chip('Risk', decision.risk_level || '')}
        ${chip('Command', decision.related_command_id || '')}
      </div>
      <div class="command-output primary">${escapeHtml(decision.rationale || 'No rationale recorded.')}</div>
      <div class="command-output">Votes: approve ${counts.approve}, reject ${counts.reject}, abstain ${counts.abstain}</div>
      ${voters ? `<div class="command-output trace">Required voters: ${escapeHtml(voters)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderAgentVotes(data) {
  const decisions = Array.isArray(data.agentVotes?.decisions) ? data.agentVotes.decisions : [];
  const sorted = [...decisions].sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  const filtered = applyInteractiveFilters(sorted);
  document.getElementById('voteCount').textContent = `${filtered.length}/${decisions.length} decision${decisions.length === 1 ? '' : 's'}`;
  document.getElementById('voteList').innerHTML = filtered.length
    ? filtered.slice(0, 6).map((decision, index) => {
        const key = registerDetail('vote_decision', decision.title || `Vote ${index + 1}`, decision, voteCli(data, decision));
        return voteCard(decision, key);
      }).join('')
    : '<div class="empty-state">No vote decisions are recorded.</div>';
}

function sessionCli(data, session) {
  const project = shellQuote(projectNameForCli(data));
  if (!session?.session_id) return `python -m scripts.commands.review.session_state list --project ${project}`;
  return `python -m scripts.commands.review.session_state list --project ${project}`;
}

function sessionCard(session, detailKey) {
  const status = normalizeStatus(session.status || 'running');
  const commands = Array.isArray(session.command_ids) ? session.command_ids.join(', ') : '';
  return `
    <article class="run-card ${escapeHtml(actionStatusClass(status))}">
      <div class="run-title">${escapeHtml(session.session_id || 'session')}</div>
      <div class="chips">
        ${chip('Status', status, actionStatusClass(status))}
        ${chip('Loop', session.loop_id || '')}
      </div>
      <div class="command-output primary">${escapeHtml(session.goal || 'No session goal recorded.')}</div>
      ${commands ? `<div class="command-output trace">Commands: ${escapeHtml(commands)}</div>` : ''}
      ${session.notes ? `<div class="command-output">Notes: ${escapeHtml(session.notes)}</div>` : ''}
      <div class="command-output">Updated: ${escapeHtml(formatDisplayTime(session.updated_at || '-'))}</div>
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderSessions(data) {
  const sessions = Array.isArray(data.sessions) ? data.sessions : [];
  const sorted = [...sessions].sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  const filtered = applyInteractiveFilters(sorted);
  document.getElementById('sessionCount').textContent = `${filtered.length}/${sessions.length} session${sessions.length === 1 ? '' : 's'}`;
  document.getElementById('sessionList').innerHTML = filtered.length
    ? filtered.slice(0, 6).map((session, index) => {
        const key = registerDetail('session', session.session_id || `Session ${index + 1}`, session, sessionCli(data, session));
        return sessionCard(session, key);
      }).join('')
    : '<div class="empty-state">No session workspaces are recorded.</div>';
}

function eventCard(event, detailKey) {
  const status = normalizeStatus(event.status || event.event || 'recorded');
  return `
    <article class="run-card ${escapeHtml(actionStatusClass(status))}">
      <div class="run-title">${escapeHtml(event.event || 'event')}</div>
      <div class="chips">
        ${chip('Agent', event.agent || '')}
        ${chip('Status', event.status || '')}
        ${chip('Command', event.command_id || '')}
      </div>
      <div class="command-output primary">${escapeHtml(event.task || event.notes || 'No event detail recorded.')}</div>
      <div class="command-output">At: ${escapeHtml(formatDisplayTime(event.timestamp || '-'))}</div>
      <div class="card-actions">${detailButton(detailKey)}</div>
    </article>
  `;
}

function renderAgentEvents(data) {
  const events = Array.isArray(data.agentEvents) ? data.agentEvents : [];
  const sorted = [...events].sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')));
  const filtered = applyInteractiveFilters(sorted);
  document.getElementById('eventCount').textContent = `${filtered.length}/${events.length} event${events.length === 1 ? '' : 's'}`;
  document.getElementById('eventList').innerHTML = filtered.length
    ? filtered.slice(0, 8).map((event, index) => {
        const key = registerDetail('agent_event', `${event.event || 'Event'} ${index + 1}`, event);
        return eventCard(event, key);
      }).join('')
    : '<div class="empty-state">No agent lifecycle events are recorded.</div>';
}

function patternCli(data, pattern) {
  const project = shellQuote(projectNameForCli(data));
  if (!pattern?.id) return `python -m scripts.commands.review.pattern_memory list --project ${project}`;
  return `python -m scripts.commands.review.pattern_memory search --project ${project} --query ${shellQuote(pattern.id)}`;
}

function patternCard(pattern, detailKey) {
  const status = normalizeStatus(pattern.status || 'candidate');
  const tags = Array.isArray(pattern.tags) ? pattern.tags.join(', ') : '';
  const triggers = Array.isArray(pattern.triggers) ? pattern.triggers.join(', ') : '';
  return `
    <article class="run-card ${escapeHtml(actionStatusClass(status))}">
      <div class="run-title">${escapeHtml(pattern.title || pattern.id || 'pattern')}</div>
      <div class="chips">
        ${chip('Status', status, actionStatusClass(status))}
        ${chip('Tags', tags)}
      </div>
      <div class="command-output primary">${escapeHtml(pattern.summary || 'No pattern summary recorded.')}</div>
      ${pattern.recommendation ? `<div class="command-output">Recommendation: ${escapeHtml(pattern.recommendation)}</div>` : ''}
      ${triggers ? `<div class="command-output trace">Triggers: ${escapeHtml(triggers)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderPatternMemory(data) {
  const patterns = Array.isArray(data.patternMemory?.patterns) ? data.patternMemory.patterns : [];
  const active = patterns.filter((pattern) => normalizeStatus(pattern.status) !== 'deprecated');
  const filtered = applyInteractiveFilters(active);
  document.getElementById('patternCount').textContent = `${filtered.length}/${patterns.length} pattern${patterns.length === 1 ? '' : 's'}`;
  document.getElementById('patternList').innerHTML = filtered.length
    ? filtered.slice(0, 6).map((pattern, index) => {
        const key = registerDetail('pattern', pattern.title || `Pattern ${index + 1}`, pattern, patternCli(data, pattern));
        return patternCard(pattern, key);
      }).join('')
    : '<div class="empty-state">No reusable workflow patterns are recorded.</div>';
}

function ralphCli(data, run) {
  const project = shellQuote(projectNameForCli(data));
  if (!run?.id) return `python -m scripts.commands.review.ralph_loop status --project ${project}`;
  return `python -m scripts.commands.review.ralph_loop status --project ${project} --id ${shellQuote(run.id)}`;
}

function ralphRemaining(run) {
  const deadline = Date.parse(run.deadline_at || '');
  if (!deadline || Number.isNaN(deadline)) return '';
  const remaining = Math.max(0, Math.round((deadline - Date.now()) / 1000));
  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m remaining`;
  return `${minutes}m remaining`;
}

function ralphCard(run, detailKey) {
  const status = normalizeStatus(run.status || 'idle');
  const iterations = Array.isArray(run.iterations) ? run.iterations.length : 0;
  const resultFiles = Array.isArray(run.result_files) ? run.result_files.join(', ') : '';
  return `
    <article class="run-card ${escapeHtml(actionStatusClass(status))}">
      <div class="run-title">${escapeHtml(run.id || 'ralph_run')}</div>
      <div class="chips">
        ${chip('Status', status, actionStatusClass(status))}
        ${chip('Command', run.command_id || '')}
        ${chip('Iterations', String(iterations))}
        ${chip('Budget', ralphRemaining(run))}
      </div>
      <div class="command-output primary">${escapeHtml(run.goal || 'No Ralph goal recorded.')}</div>
      ${run.stop_reason ? `<div class="command-output">Stop reason: ${escapeHtml(run.stop_reason)}</div>` : ''}
      ${run.last_prompt_file ? `<div class="command-output trace">Prompt: ${escapeHtml(run.last_prompt_file)}</div>` : ''}
      ${resultFiles ? `<div class="command-output trace">Result files: ${escapeHtml(resultFiles)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderRalphLoop(data) {
  const runs = Array.isArray(data.ralphLoop?.runs) ? data.ralphLoop.runs : [];
  const sorted = [...runs].sort((a, b) => String(b.started_at || '').localeCompare(String(a.started_at || '')));
  const filtered = applyInteractiveFilters(sorted);
  document.getElementById('ralphCount').textContent = `${filtered.length}/${runs.length} run${runs.length === 1 ? '' : 's'}`;
  document.getElementById('ralphList').innerHTML = filtered.length
    ? filtered.slice(0, 6).map((run, index) => {
        const key = registerDetail('ralph_loop', run.id || `Ralph ${index + 1}`, run, ralphCli(data, run));
        return ralphCard(run, key);
      }).join('')
    : '<div class="empty-state">No Ralph loop runs are recorded.</div>';
}

function reportCli(data, item) {
  const project = shellQuote(projectNameForCli(data));
  if (item?.path) return `python -m scripts.commands.reports.report_index refresh --project ${project}`;
  return `python -m scripts.commands.reports.report_index refresh --project ${project}`;
}

function reportResultCard(item, detailKey) {
  const path = item.path || '';
  const title = humanReadableOutput(path || item.name || 'report artifact');
  const rows = typeof item.rows === 'number' ? `${item.rows} data row${item.rows === 1 ? '' : 's'}` : '';
  const updated = item.updated_at ? `Updated: ${formatDisplayTime(item.updated_at)}` : '';
  const columns = Array.isArray(item.columns) && item.columns.length
    ? `Columns: ${item.columns.slice(0, 5).join(', ')}${item.columns.length > 5 ? '...' : ''}`
    : '';
  return `
    <article class="run-card done">
      <div class="run-title">${escapeHtml(title)}</div>
      <div class="chips">
        ${chip('Rows', rows)}
        ${chip('Kind', item.kind || (path.endsWith('.csv') ? 'csv' : 'file'))}
      </div>
      <div class="command-output primary">${escapeHtml(path || item.name || 'No report path recorded.')}</div>
      ${columns ? `<div class="command-output">${escapeHtml(columns)}</div>` : ''}
      ${updated ? `<div class="command-output">${escapeHtml(updated)}</div>` : ''}
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderTableHtml(table) {
  const columns = Array.isArray(table.columns) ? table.columns : [];
  const rows = Array.isArray(table.preview_rows) ? table.preview_rows : [];
  if (!columns.length) {
    return '<div class="empty-state" style="margin: 10px;">No columns were detected in this CSV.</div>';
  }
  const body = rows.length
    ? rows.map((row) => `
      <tr>
        ${columns.map((_, index) => `<td>${escapeHtml(row[index] ?? '')}</td>`).join('')}
      </tr>
    `).join('')
    : `<tr><td colspan="${columns.length}">No data rows.</td></tr>`;
  return `
    <div class="table-scroll">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column || '-')}</th>`).join('')}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function renderTablePreviewCard(table) {
  return `
    <article class="table-preview-card">
      <div class="table-preview-head">
        <div>
          <div class="run-title">${escapeHtml(humanReadableOutput(table.path || table.name))}</div>
          <div class="hint">${escapeHtml(table.path || table.name || '')}</div>
        </div>
        <div class="chips">
          ${chip('Rows', String(table.rows ?? 0))}
          ${chip('Columns', String((table.columns || []).length))}
        </div>
      </div>
      ${renderTableHtml(table)}
      ${table.preview_truncated ? '<div class="hint" style="padding: 8px 10px;">Preview truncated to the first rows.</div>' : ''}
    </article>
  `;
}

function renderTablePreviews(data) {
  const tables = Array.isArray(data.reportSnapshot?.tables) ? data.reportSnapshot.tables : [];
  const filtered = applyInteractiveFilters(tables);
  document.getElementById('tablePreviewCount').textContent = `${filtered.length}/${tables.length} table${tables.length === 1 ? '' : 's'}`;
  document.getElementById('tablePreviewList').innerHTML = filtered.length
    ? filtered.slice(0, 6).map(renderTablePreviewCard).join('')
    : '<div class="empty-state">No result tables match the current filters.</div>';
}

function evidenceMapRows(data) {
  const claimRows = tableObjects(tableByName(data, 'claim_evidence'));
  const resultRows = tableObjects(tableByName(data, 'experiment_results'));
  if (claimRows.length) {
    return claimRows.map((claim) => {
      const claimId = claim.claim_id || claim.id || '';
      const experiments = String(claim.experiments || '')
        .split(/[;,]/)
        .map((value) => value.trim())
        .filter(Boolean);
      const linkedResults = resultRows.filter((result) => (
        String(result.claim_id || '') === claimId
        || experiments.includes(String(result.experiment_id || result.exp_id || ''))
      ));
      return { claim, linkedResults };
    });
  }
  return resultRows.map((result) => ({
    claim: {
      claim_id: result.claim_id || 'unmapped',
      claim: 'Experiment result without claim row',
      status: result.status || 'observed',
      evidence: result.evidence || '',
      experiments: result.experiment_id || result.exp_id || ''
    },
    linkedResults: [result]
  }));
}

function evidenceMapCard(entry, index) {
  const claim = entry.claim || {};
  const linked = entry.linkedResults || [];
  const linkedSummary = linked.length
    ? linked.map((result) => [
        result.experiment_id || result.exp_id || 'experiment',
        result.method || '',
        result.metric ? `${result.metric}=${result.value || '-'}` : ''
      ].filter(Boolean).join(' · ')).join(' / ')
    : 'No linked experiment rows in the preview window.';
  return `
    <article class="evidence-card">
      <div class="evidence-card-head">
        <div>
          <div class="run-title">${escapeHtml(claim.claim_id || `claim_${index + 1}`)}</div>
          <div class="command-output primary">${escapeHtml(claim.claim || 'No claim text recorded.')}</div>
        </div>
        <span class="status-pill ${escapeHtml(actionStatusClass(claim.status || 'waiting'))}">${escapeHtml(claim.status || 'pending')}</span>
      </div>
      <div class="evidence-link-grid">
        <div><span>Evidence</span><strong>${escapeHtml(claim.evidence || 'not linked')}</strong></div>
        <div><span>Experiments</span><strong>${escapeHtml(claim.experiments || 'not linked')}</strong></div>
        <div><span>Results</span><strong>${escapeHtml(linkedSummary)}</strong></div>
      </div>
      ${claim.next_needed ? `<div class="command-output">Next needed: ${escapeHtml(claim.next_needed)}</div>` : ''}
    </article>
  `;
}

function renderEvidenceMap(data) {
  const rows = evidenceMapRows(data);
  const filtered = applyInteractiveFilters(rows);
  document.getElementById('evidenceMapCount').textContent = `${filtered.length}/${rows.length} claim${rows.length === 1 ? '' : 's'}`;
  document.getElementById('evidenceMapList').innerHTML = filtered.length
    ? filtered.slice(0, 8).map(evidenceMapCard).join('')
    : '<div class="empty-state">No claim-evidence or experiment-result rows are available for mapping.</div>';
}

function experimentComparisonRows(data) {
  return tableObjects(tableByName(data, 'experiment_results'));
}

function renderExperimentComparison(data) {
  const rows = applyInteractiveFilters(experimentComparisonRows(data));
  document.getElementById('experimentComparisonCount').textContent = `${rows.length} row${rows.length === 1 ? '' : 's'}`;
  if (!rows.length) {
    document.getElementById('experimentComparisonTable').innerHTML = '<div class="empty-state">No experiment result rows are available for comparison.</div>';
    return;
  }
  const columns = ['experiment_id', 'claim_id', 'method', 'baseline_id', 'metric', 'value', 'delta', 'status'];
  document.getElementById('experimentComparisonTable').innerHTML = `
    <div class="table-scroll comparison-table">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.slice(0, 20).map((row) => `
            <tr>
              ${columns.map((column) => `<td>${escapeHtml(row[column] ?? '')}</td>`).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function reportReadmePreview(textValue) {
  const textContent = String(textValue || '').trim();
  if (!textContent) return 'No 09_report/README.md excerpt is available.';
  const withoutMarkers = textContent
    .replace(/<!-- RESEARCH_AGENT_REPORT_INDEX:START -->/g, '')
    .replace(/<!-- RESEARCH_AGENT_REPORT_INDEX:END -->/g, '')
    .trim();
  const lines = withoutMarkers.split(/\r?\n/).slice(0, 80);
  return lines.join('\n').trim();
}

function renderReportSnapshot(data) {
  const snapshot = data.reportSnapshot || {};
  const tables = Array.isArray(snapshot.tables) ? snapshot.tables : [];
  const latestFiles = Array.isArray(snapshot.latest_files) ? snapshot.latest_files : [];
  const merged = [
    ...tables.map((item) => ({ ...item, kind: 'csv' })),
    ...latestFiles.filter((file) => !tables.some((table) => table.path === file.path))
  ];
  const filtered = applyInteractiveFilters(merged);
  document.getElementById('reportResultCount').textContent = `${filtered.length}/${merged.length} report file${merged.length === 1 ? '' : 's'}`;
  document.getElementById('reportResultList').innerHTML = filtered.length
    ? filtered.slice(0, 8).map((item, index) => {
        const key = registerDetail('report_result', item.path || item.name || `Report ${index + 1}`, item, reportCli(data, item));
        return reportResultCard(item, key);
      }).join('')
    : '<div class="empty-state">No report result files are visible yet. Refresh 09_report/README.md after material result changes.</div>';
  const tableRows = tables.reduce((total, table) => total + Number(table.rows || 0), 0);
  document.getElementById('reportSnapshotUpdated').textContent = snapshot.updated_at
    ? `Updated: ${formatDisplayTime(snapshot.updated_at)}`
    : 'No report snapshot';
  document.getElementById('reportSnapshotSummary').innerHTML = [
    overviewItem('README', snapshot.readme_path || '09_report/README.md not found', snapshot.readme_path ? 'reader-facing entry point' : 'missing'),
    overviewItem('Result tables', `${tables.length} table${tables.length === 1 ? '' : 's'} · ${tableRows} total data row${tableRows === 1 ? '' : 's'}`, '09_report/results'),
    overviewItem('Recent artifacts', `${latestFiles.length} file${latestFiles.length === 1 ? '' : 's'} visible in results, analysis, or figures`, 'final artifact folders')
  ].join('');
  document.getElementById('reportReadmeExcerpt').textContent = reportReadmePreview(snapshot.readme_excerpt);
}

function renderDataSources(data) {
  const manifest = data.dataSources || normalizeDataSources(null);
  const sources = manifest.sources || [];
  const coverage = manifest.coverage || { available: 0, total: sources.length, required_missing: [] };
  document.getElementById('sourceCoverageCount').textContent = `${coverage.available}/${coverage.total} sources`;
  const sourceRows = sources.map((source) => `
    <article class="source-item ${escapeHtml(source.status || 'missing')}">
      <div class="source-main">
        <div>
          <div class="source-title">${escapeHtml(source.label || source.key || source.path || 'Source')}</div>
          <div class="source-path">${escapeHtml(source.path || '-')}</div>
        </div>
        <span class="source-status">${escapeHtml(source.status || 'unknown')}</span>
      </div>
      <div class="source-meta">
        <span>${source.required ? 'required' : 'optional'}</span>
        <span>${Number(source.records || 0)} record${Number(source.records || 0) === 1 ? '' : 's'}</span>
        ${source.updated_at ? `<span>updated ${escapeHtml(formatDisplayTime(source.updated_at))}</span>` : '<span>not loaded</span>'}
      </div>
    </article>
  `);
  const validationRows = (data.healthWarnings || []).map((warning) => `
    <article class="source-item warning">
      <div class="source-main">
        <div>
          <div class="source-title">State Validation Warning</div>
          <div class="source-path">${escapeHtml(warning)}</div>
        </div>
        <span class="source-status">warning</span>
      </div>
    </article>
  `);
  const missing = coverage.required_missing || [];
  const summary = missing.length
    ? `<div class="source-note">Missing required source${missing.length === 1 ? '' : 's'}: ${escapeHtml(missing.join(', '))}</div>`
    : '<div class="source-note">All required dashboard sources are available.</div>';
  document.getElementById('sourceCoverageList').innerHTML = sources.length || validationRows.length
    ? `${summary}${sourceRows.join('')}${validationRows.join('')}`
    : '<div class="empty-state">No dashboard source manifest is available for this snapshot.</div>';
}

function agentCard(agent, detailKey) {
  const status = normalizeStatus(agent.status);
  return `
    <article class="agent ${escapeHtml(status)}">
      <div class="agent-top">
        <div>
          <div class="agent-name">${escapeHtml(agent.display_name || agent.name)}</div>
          <div class="role">${escapeHtml(agent.role || '')}</div>
        </div>
        <span class="status"><span class="dot"></span>${escapeHtml(status)}</span>
      </div>
      <p class="task">${escapeHtml(agent.current_task || 'No current task recorded.')}</p>
      <div class="meta">
        <div>Stage: <strong>${escapeHtml(agent.stage || '-')}</strong></div>
        <div>Started: <strong>${escapeHtml(formatDisplayTime(agent.started_at || '-'))}</strong></div>
        <div>Updated: <strong>${escapeHtml(formatDisplayTime(agent.updated_at || '-'))}</strong></div>
      </div>
      <div class="files">
        <div>Inputs: ${fileList(agent.last_input_files)}</div>
        <div>Outputs: ${fileList(agent.last_output_files)}</div>
      </div>
      <div class="card-actions">
        ${detailButton(detailKey)}
        ${copyButton(detailKey)}
      </div>
    </article>
  `;
}

function renderNextCommand(data) {
  const next = chooseNextAction(data.loopNextActions.length ? data.loopNextActions : data.activeActions);
  if (!next) {
    document.getElementById('nextCommandTitle').textContent = 'No open commands';
    document.getElementById('nextCommandMeta').innerHTML = '<span class="chip done">Status: clear</span>';
    document.getElementById('nextCommandOutput').textContent = '';
    return;
  }
  const statusClass = actionStatusClass(next.status);
  document.getElementById('nextCommandTitle').textContent = readableActionTitle(next) || 'Untitled action';
  document.getElementById('nextCommandMeta').innerHTML = [
    chip('Owner', next.owner),
    chip('Priority', next.priority),
    chip('Status', next.status, statusClass)
  ].join('');
  document.getElementById('nextCommandOutput').textContent = readableActionSummary(next);
}

function truncateText(value, maxLength = 34) {
  const textValue = String(value || '');
  return textValue.length > maxLength ? `${textValue.slice(0, maxLength - 1)}...` : textValue;
}

function ownerParts(owner) {
  const parts = String(owner || '')
    .replaceAll(',', '/')
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length ? parts : ['unassigned'];
}

function displayAgentName(data, agentName) {
  const match = data.agents.find((agent) => agent.name === agentName || agent.display_name === agentName);
  return match?.display_name || agentName;
}

function flowItems(data) {
  const commands = data.actions.map((action) => ({
    ...action,
    flowType: 'command',
    flowSource: 'Director / Loop'
  }));
  const loopActions = commands.length ? [] : data.loopNextActions.map((action, index) => ({
    ...action,
    id: `next_${index + 1}`,
    flowType: 'next_action',
    flowSource: 'Loop Summary'
  }));
  return applyInteractiveFilters([...commands, ...loopActions]).slice(0, 16);
}

function pipelineTimelineItems(data) {
  const next = nextPromptAction(data);
  const active = data.activeActions.slice(0, 4).map((action) => ({
    kind: 'Command',
    title: readableActionTitle(action) || action.id || 'Command',
    body: readableActionSummary(action) || 'No command summary recorded.',
    status: action.status || 'open',
    meta: [action.id, action.owner ? displayAgentName(data, action.owner) : '', action.priority].filter(Boolean).join(' · '),
    item: action,
    cli: commandUpdateCli(data, action)
  }));
  const terminalEvents = (data.completedEventActions || []).slice(0, 3).map((event) => ({
    kind: 'Event',
    title: event.source_event || event.status || 'Agent event',
    body: event.action || event.notes || 'Lifecycle event recorded.',
    status: event.status || 'done',
    meta: [event.owner_display || event.owner, formatDisplayTime(event.updatedAt)].filter(Boolean).join(' · '),
    item: event,
    cli: ''
  }));
  const ralphRuns = (data.ralphLoop?.runs || []).slice(-2).reverse().map((run) => ({
    kind: 'Ralph',
    title: run.id || 'Ralph run',
    body: run.stop_reason || run.goal || 'Bounded loop recorded.',
    status: run.status || 'idle',
    meta: [run.command_id, `${Array.isArray(run.iterations) ? run.iterations.length : 0} iter`].filter(Boolean).join(' · '),
    item: run,
    cli: ralphCli(data, run)
  }));
  const nextStep = next ? [{
    kind: 'Next',
    title: readableActionTitle(next) || 'Next action',
    body: completionText(next) || readableActionSummary(next) || 'Next command selected.',
    status: next.status || 'open',
    meta: [next.owner ? displayAgentName(data, next.owner) : 'director', next.priority].filter(Boolean).join(' · '),
    item: next,
    cli: commandUpdateCli(data, next)
  }] : [];
  return [...nextStep, ...active, ...terminalEvents, ...ralphRuns].slice(0, 8);
}

function pipelineStepCard(data, step, index) {
  const statusClass = actionStatusClass(step.status);
  const key = registerDetail('pipeline_step', step.title || `Pipeline step ${index + 1}`, step.item || step, step.cli || '');
  return `
    <article class="pipeline-step ${escapeHtml(statusClass)}">
      <div class="pipeline-step-head">
        <div class="pipeline-step-title">${escapeHtml(index + 1)}. ${escapeHtml(step.title || '-')}</div>
        <div class="pipeline-step-meta">${escapeHtml(step.kind || 'Step')}</div>
      </div>
      ${step.meta ? `<div class="chips">${chip('Route', step.meta)}${chip('Status', step.status, statusClass)}</div>` : `<div class="chips">${chip('Status', step.status, statusClass)}</div>`}
      <div class="pipeline-step-body">${escapeHtml(step.body || 'No detail recorded.')}</div>
      <div class="card-actions">${detailButton(key)}${step.cli ? copyButton(key) : ''}</div>
    </article>
  `;
}

function renderAgentFlow(data) {
  const steps = pipelineTimelineItems(data);
  document.getElementById('flowCount').textContent = `${steps.length} step${steps.length === 1 ? '' : 's'}`;
  document.getElementById('agentFlowLegend').innerHTML = [
    chip('Route', 'owner/agent'),
    chip('Risk', 'vote if high', 'waiting'),
    chip('Ralph', 'bounded loop', 'done'),
    chip('Handoff', 'dispatch block')
  ].join('');

  if (steps.length === 0) {
    document.getElementById('agentFlowDiagram').innerHTML = '<div class="empty-state" style="margin: 12px;">No pipeline steps are recorded yet.</div>';
    document.getElementById('agentFlowSummary').innerHTML = '<div class="empty-state">Add commands, events, or Ralph runs to see the handoff timeline.</div>';
    return;
  }

  document.getElementById('agentFlowDiagram').innerHTML = `
    <div class="pipeline-list">
      ${steps.map((step, index) => pipelineStepCard(data, step, index)).join('')}
    </div>
  `;
  const voteRecords = data.agentVotes?.decisions || data.agentVotes?.votes || [];
  const openVotes = voteRecords.filter((vote) => !['approved', 'rejected', 'cancelled'].includes(normalizeStatus(vote.status))).length;
  const routeOwners = [...new Set(data.activeActions.flatMap((item) => ownerParts(item.owner)).filter(Boolean))];
  document.getElementById('agentFlowSummary').innerHTML = [
    ['Next owner', nextPromptAction(data)?.owner ? displayAgentName(data, nextPromptAction(data).owner) : 'director'],
    ['Open commands', String(data.activeActions.length)],
    ['Open votes', String(openVotes)],
    ['Ralph runs', String((data.ralphLoop?.runs || []).length)],
    ['Owners in queue', routeOwners.length ? routeOwners.map((owner) => displayAgentName(data, owner)).join(', ') : '-']
  ].map(([label, value]) => `
    <div class="flow-summary-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join('');
}

function renderOperatorPanel(data) {
  document.getElementById('loopUpdateSnippet').textContent = loopUpdateCli(data);
  document.getElementById('agentHeartbeatSnippet').textContent = agentHeartbeatCli(data);
  document.getElementById('commandUpdateSnippet').textContent = commandUpdateCli(data);
}

function consoleCommands(data) {
  const project = shellQuote(projectNameForCli(data));
  const next = nextPromptAction(data);
  const nextId = next?.id ? shellQuote(next.id) : '';
  const nextOwner = next?.owner || 'director';
  const ralphId = `dashboard_${projectNameForCli(data).replace(/[^a-zA-Z0-9_]+/g, '_')}_loop`;
  const ralphGoal = next
    ? `Complete ${readableActionTitle(next)} and update dashboard-visible results.`
    : 'Inspect project state, choose the next research task, and update dashboard-visible results.';
  return [
    {
      title: 'Start Dashboard',
      copy: 'Serve the current project dashboard locally.',
      command: `python -m scripts.commands.agents.agent_dashboard --project ${project}`
    },
    {
      title: 'Refresh Dashboard Inputs',
      copy: 'Regenerate the claim board, research audit, report index, and data-source coverage.',
      runner_id: 'dashboard_refresh',
      command: `python -m scripts.commands.dashboard.dashboard_refresh --project ${project}`
    },
    {
      title: 'Project Closeout Audit',
      copy: 'Write a closeout audit that routes blockers to the right project skills.',
      runner_id: 'project_closeout',
      command: `python -m scripts.commands.projects.project_closeout --project ${project} --refresh-dashboard --write-report`
    },
    {
      title: 'Refresh Report Index',
      copy: 'Regenerate the reader-facing 09_report/README.md snapshot.',
      runner_id: 'report_refresh',
      command: `python -m scripts.commands.reports.report_index refresh --project ${project}`
    },
    {
      title: 'Validate Project',
      copy: 'Check project state and research workflow contracts.',
      runner_id: 'validate_project',
      command: `python -m scripts.commands.projects.validate_project --project ${project} --strict`
    },
    {
      title: 'Dashboard Source Check',
      copy: 'Verify which dashboard sources are present and fresh.',
      runner_id: 'dashboard_sources',
      command: `python -m scripts.commands.dashboard.dashboard_sources --project ${project}`
    },
    {
      title: 'Workflow Audit',
      copy: 'Check dashboard and harness wiring without changing project state.',
      runner_id: 'workflow_audit',
      command: 'python -m scripts.commands.release.workflow_audit'
    },
    {
      title: 'Get Next Orchestrator Prompt',
      copy: nextId ? 'Write a command-specific prompt for the next agent.' : 'Ask the orchestrator for the next command.',
      command: nextId
        ? `python -m scripts.commands.agents.agent_orchestrator prompt --project ${project} --id ${nextId} --write`
        : `python -m scripts.commands.agents.agent_orchestrator next --project ${project}`
    },
    {
      title: 'Start Agent Status',
      copy: 'Mark the next owner as running before work starts.',
      command: [
        'python -m scripts.commands.agents.agent_status start',
        `--project ${project}`,
        `--agent ${shellQuote(nextOwner)}`,
        nextId ? `--command-id ${nextId}` : '',
        `--task ${shellQuote(next ? readableActionTitle(next) : 'Inspect project state and choose the next task.')}`,
        `--stage ${shellQuote(data.currentStage || 'planning')}`
      ].filter(Boolean).join(' ')
    },
    {
      title: 'Ralph Loop Template',
      copy: 'Bounded fresh-context loop template; edit result-file and promise before running.',
      command: [
        'python -m scripts.commands.review.ralph_loop run',
        `--project ${project}`,
        `--id ${shellQuote(ralphId)}`,
        `--goal ${shellQuote(ralphGoal)}`,
        nextId ? `--command-id ${nextId}` : '',
        '--duration-minutes 60',
        '--result-file 09_report/README.md',
        '--completion-promise DASHBOARD_RESEARCH_LOOP_COMPLETE'
      ].filter(Boolean).join(' ')
    },
    {
      title: 'Harness Smoke',
      copy: 'Run the end-to-end harness smoke test.',
      runner_id: 'smoke_test',
      command: 'python -m scripts.commands.release.smoke_test'
    },
    {
      title: 'Full Harness Verification',
      copy: 'Run the publishable harness verification without paper build.',
      runner_id: 'verify_harness',
      command: `python -m scripts.commands.release.verify_harness --project ${project} --skip-paper-build`
    }
  ];
}

function consoleCommandCard(data, command, index) {
  const key = registerDetail('console_command', command.title, command, command.command);
  const canRun = Boolean(data.commandRunner?.enabled && command.runner_id);
  return `
    <article class="console-command">
      <div class="snippet-head">
        <div class="console-command-title">${escapeHtml(index + 1)}. ${escapeHtml(command.title)}</div>
        <div class="console-actions">
          ${canRun ? `<button class="micro-button" type="button" data-run-command="${escapeHtml(command.runner_id)}">Run</button>` : ''}
          ${copyButton(key)}
        </div>
      </div>
      <div class="console-command-copy">${escapeHtml(command.copy)}</div>
      <pre>${escapeHtml(command.command)}</pre>
    </article>
  `;
}

function consoleEventStream(data) {
  const events = (data.agentEvents || []).slice().sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || ''))).slice(0, 12);
  if (!events.length) return '$ no recent agent events recorded';
  return events.map((event) => {
    const at = formatDisplayTime(event.timestamp || '-');
    const agent = event.agent || 'agent';
    const status = event.status || event.event || 'event';
    const body = event.task || event.notes || event.command_id || '';
    return `$ ${at} ${agent} [${status}]\n  ${body}`;
  }).join('\n\n');
}

function renderCommandConsole(data) {
  const prompt = buildNextPrompt(data);
  document.getElementById('consoleProjectHint').textContent = data.commandRunner?.enabled
    ? `${projectNameForCli(data)} · safe runner enabled`
    : `${projectNameForCli(data)} · copy-ready runbook`;
  document.getElementById('consolePromptText').textContent = prompt;
  document.getElementById('consoleEventStream').textContent = consoleEventStream(data);
  document.getElementById('consoleCommandList').innerHTML = consoleCommands(data)
    .map((command, index) => consoleCommandCard(data, command, index))
    .join('');
  const output = document.getElementById('consoleRunOutput');
  if (output && !output.textContent.trim()) {
    output.textContent = data.commandRunner?.enabled
      ? '$ select an allowlisted runbook command'
      : 'Command runner is disabled unless the dashboard server is started with --enable-command-runner.';
  }
}

function nextPromptAction(data) {
  return data.loopNextActions[0] || chooseNextAction(data.activeActions) || chooseNextAction(data.actions) || null;
}

function buildNextPrompt(data) {
  const action = nextPromptAction(data);
  const project = projectNameForCli(data);
  const loop = data.loopSummary || {};
  const lines = [
    `Continue the research project ${project}.`,
    '',
    'Read these files first:',
    '- state/current_state.md',
    '- state/loop_summary.json',
    '- state/command_queue.json',
    '- state/agent_status.json',
    '- state/agent_votes.json',
    '- state/pattern_memory.json',
    '- state/ralph_loop.json',
    '',
    `Current stage: ${data.currentStage || '-'}`,
    `Current loop: ${loop.loop_id || '-'} (${loop.status || '-'})`,
    `Loop goal: ${loop.goal || '-'}`,
    `Loop summary: ${loop.summary || '-'}`,
    ''
  ];
  if (action) {
    lines.push('Next task, in plain language:');
    lines.push(readableActionSummary(action) || action.action || 'Continue the highest-priority open command.');
    lines.push(`Owner agent: ${action.owner || 'director'}`);
    lines.push(`Priority: ${action.priority || 'high'}`);
    lines.push(`Expected evidence files: ${rawItemOutputs(action) || action.outputs || 'Update the relevant project files and state files.'}`);
    if (action.notes) lines.push(`Notes: ${action.notes}`);
  } else {
    lines.push('Next task: inspect the project state and decide the next concrete action.');
  }
  lines.push('');
  lines.push('Execution rules:');
  lines.push('- Stay inside the active project folder. Do not delete, move, overwrite, or recursively clean any directory outside it.');
  lines.push('- Never run rm -rf, find -delete, git clean -fd, rsync --delete, or recursive delete scripts on parent folders, sibling projects, datasets, external repositories, or system paths.');
  lines.push('- Update state/agent_status.json through python -m scripts.commands.agents.agent_status before and after work.');
  lines.push('- Update state/loop_summary.json through python -m scripts.commands.review.loop_summary with completed work, result, and next action.');
  lines.push('- Keep state/command_queue.json synchronized through python -m scripts.commands.review.command_queue.');
  lines.push('- For important or high-risk commands, use python -m scripts.commands.agents.agent_vote and dispatch only after approval.');
  lines.push('- Record reusable lessons in state/pattern_memory.json through python -m scripts.commands.review.pattern_memory.');
  lines.push('- For bounded autonomous passes, use python -m scripts.commands.review.ralph_loop with a duration limit, result files, and a completion promise.');
  lines.push('- Write the next action and completion note in plain Korean or plain English first; put file paths only as supporting evidence.');
  lines.push('- If experiments are still running, verify run_state.json and keep heartbeats current.');
  lines.push('- Do not claim completion unless expected outputs exist or are explicitly blocked.');
  return lines.join('\n');
}

function renderNextPrompt(data) {
  const action = nextPromptAction(data);
  const prompt = buildNextPrompt(data);
  document.getElementById('nextPromptText').textContent = prompt;
  document.getElementById('heroNextPromptText').textContent = prompt;
  document.getElementById('nextPromptSource').textContent = action
    ? `Source: ${action.id || 'loop_summary.next_actions'}`
    : 'Source: project state';
  document.getElementById('heroNextPromptSource').textContent = action
    ? `Source: ${action.id || 'loop_summary.next_actions'}`
    : 'Source: project state';
  const key = registerDetail('next_prompt', 'Next agent prompt source', {
    prompt,
    selected_action: action,
    loop_summary: data.loopSummary,
    active_commands: data.activeActions
  });
  document.getElementById('inspectNextPrompt').dataset.detailKey = key;
}

function renderExecutiveSummary(data) {
  const loop = data.loopSummary || {};
  const action = nextPromptAction(data);
  document.getElementById('heroGoal').textContent = loop.goal || data.currentStage || '-';
  document.getElementById('heroSummary').textContent = overviewAutoSummary(data);
  document.getElementById('heroMeta').innerHTML = [
    chip('Loop', loop.loop_id || '-'),
    chip('Status', loop.status || 'planned', actionStatusClass(loop.status || 'planned')),
    chip('Updated', formatDisplayTime(loop.last_updated || data.lastUpdated || '-'))
  ].join('');
  document.getElementById('heroNextAction').textContent = action ? readableActionTitle(action) : 'No next action recorded.';
  document.getElementById('heroActiveCount').textContent = data.activeCount;
  document.getElementById('heroWaitingCount').textContent = data.waitingCount;
  document.getElementById('heroBlockedCount').textContent = data.blockedCount;
  document.getElementById('heroTotalCount').textContent = data.agents.length;
  document.getElementById('heroRunningStack').innerHTML = renderActivityStack(data, 2);
}

function updateControlState() {
  document.querySelectorAll('[data-view]').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === uiState.view);
  });
  document.querySelectorAll('[data-status-filter]').forEach((button) => {
    button.classList.toggle('active', button.dataset.statusFilter === uiState.statusFilter);
  });
  if (dashboardSearch.value !== uiState.query) dashboardSearch.value = uiState.query;
  pauseButton.textContent = uiState.paused ? 'Resume Live' : 'Pause Live';
}

function applyViewMode() {
  document.querySelectorAll('[data-dashboard-section]').forEach((section) => {
    const modes = String(section.dataset.dashboardSection || '').split(/\s+/);
    section.hidden = uiState.view !== 'all' && !modes.includes(uiState.view);
  });
}

function openDetail(key) {
  const entry = detailRegistry.get(key);
  if (!entry) return;
  activeDetail = entry;
  document.getElementById('drawerType').textContent = entry.kind.replaceAll('_', ' ');
  document.getElementById('drawerTitle').textContent = entry.title || 'Details';
  document.getElementById('drawerChips').innerHTML = [
    chip('Status', entry.item?.status || '', actionStatusClass(entry.item?.status || '')),
    chip('Owner', entry.item?.owner || entry.item?.owner_agent || ''),
    chip('Updated', formatDisplayTime(entry.item?.updatedAt || entry.item?.updated_at || ''))
  ].join('');
  document.getElementById('drawerBody').textContent = JSON.stringify(entry.item, null, 2);
  copyDrawerCli.disabled = !entry.cli;
  detailDrawer.hidden = false;
  drawerBackdrop.hidden = false;
  detailDrawer.setAttribute('aria-hidden', 'false');
  drawerClose.focus();
}

function closeDetail() {
  detailDrawer.hidden = true;
  drawerBackdrop.hidden = true;
  detailDrawer.setAttribute('aria-hidden', 'true');
  activeDetail = null;
}

function render(data) {
  lastData = data;
  detailRegistry = new Map();
  const agents = applyInteractiveFilters(sortedAgents(data.agents));
  const activeCommands = applyInteractiveFilters(data.activeActions);
  const completedCommands = applyInteractiveFilters(data.completedActions);
  const experimentRuns = applyInteractiveFilters(data.experimentRuns);
  renderLoopSummary(data);
  renderKoreanSummary(data);
  renderExecutiveSummary(data);
  renderRunReadinessGate(data);
  renderResearchReadiness(data);
  renderResearchPhaseTrack(data);
  document.getElementById('subtitle').textContent = `${data.project} · file-based agent state`;
  document.getElementById('focusStage').textContent = data.currentStage;
  document.getElementById('focusDecision').textContent = data.directorDecision || 'No director decision recorded.';
  document.getElementById('focusUpdated').textContent = formatDisplayTime(data.lastUpdated);
  document.getElementById('runningStack').innerHTML = renderRunningStack(data);
  document.getElementById('activeCount').textContent = data.activeCount;
  document.getElementById('waitingCount').textContent = data.waitingCount;
  document.getElementById('totalCount').textContent = data.agents.length;
  document.getElementById('blockedCount').textContent = data.blockedCount;
  document.getElementById('currentStage').textContent = data.currentStage;
  document.getElementById('lastUpdated').textContent = `Status updated: ${formatDisplayTime(data.lastUpdated)}`;
  document.getElementById('projectPath').textContent = data.projectPath;
  document.getElementById('runningNames').textContent = data.running.join(', ') || 'None';
  document.getElementById('waitingNames').textContent = data.waiting.join(', ') || 'None';
  document.getElementById('loadedAt').textContent = new Date().toLocaleString();
  document.getElementById('sourceUpdated').textContent = formatDisplayTime(data.sourceUpdated || '-');
  document.getElementById('currentState').textContent = data.currentState || 'No current state file loaded.';
  document.getElementById('nextActions').textContent = data.nextActions || 'No next actions file loaded.';
  document.getElementById('agentGrid').innerHTML = agents.length
    ? agents.map((agent, index) => {
        const key = registerDetail('agent', agent.display_name || agent.name || `Agent ${index + 1}`, agent, agentHeartbeatCli(data, agent));
        return agentCard(agent, key);
      }).join('')
    : '<div class="empty-state">No agents match the current filters.</div>';
  document.getElementById('commandCount').textContent = `${activeCommands.length}/${data.activeActions.length} active`;
  document.getElementById('commandQueue').innerHTML = activeCommands.length
    ? activeCommands.map((action, index) => {
        const key = registerDetail('active_command', action.action || `Command ${index + 1}`, action, commandUpdateCli(data, action));
        return commandCard(action, index, key);
      }).join('')
    : '<div class="empty-state">No open, in-progress, or blocked commands match the current filters.</div>';
  const visibleCompletedCommands = completedCommands.slice(0, COMPLETED_COMMAND_DISPLAY_LIMIT);
  const hiddenCompletedCount = Math.max(0, completedCommands.length - visibleCompletedCommands.length);
  document.getElementById('completedCommandCount').textContent = `${visibleCompletedCommands.length}/${data.completedActions.length} shown`;
  document.getElementById('completedCommandHistory').innerHTML = completedCommands.length
    ? visibleCompletedCommands.map((action, index) => {
        const key = registerDetail('completed_command', action.action || `Command ${index + 1}`, action, commandUpdateCli(data, action));
        return compactCommandCard(action, index, key);
      }).join('') + (hiddenCompletedCount
        ? `<div class="empty-state">${hiddenCompletedCount} older completed command${hiddenCompletedCount === 1 ? '' : 's'} hidden from the overview. Use search or the raw state files for the full history.</div>`
        : '')
    : '<div class="empty-state">No completed commands match the current filters.</div>';
  document.getElementById('runCount').textContent = `${experimentRuns.length}/${data.experimentRuns.length} run${data.experimentRuns.length === 1 ? '' : 's'}`;
  document.getElementById('runList').innerHTML = experimentRuns.length
    ? experimentRuns.map((run, index) => {
        const key = registerDetail('experiment_run', run.exp_id || `Run ${index + 1}`, run, runHeartbeatCli(data, run));
        return runCard(run, key);
      }).join('')
    : '<div class="empty-state">No run_state.json files found under 03_experiments/.</div>';
  renderGpuQueue(data);
  renderRegistry(data);
  renderDataSources(data);
  renderNextCommand(data);
  renderCommandBoard(data);
  renderAgentFlow(data);
  renderAgentMessages(data);
  renderBlockerTriage(data);
  renderAgentVotes(data);
  renderSessions(data);
  renderAgentEvents(data);
  renderPatternMemory(data);
  renderRalphLoop(data);
  renderReportSnapshot(data);
  renderEvidenceMap(data);
  renderExperimentComparison(data);
  renderTablePreviews(data);
  renderOperatorPanel(data);
  renderNextPrompt(data);
  renderCommandConsole(data);
  renderOverviewBoard(data);
  updateControlState();
  applyViewMode();
}

function clearDashboard() {
  stopAutoRefresh();
  serverMode = false;
  input.value = '';
  setNotice('');
  render(statusData({ project: 'No project loaded', agents: [] }, '', '', '-'));
  document.getElementById('subtitle').textContent = 'No project loaded.';
  document.getElementById('loadedAt').textContent = '-';
  document.getElementById('sourceUpdated').textContent = '-';
}

async function loadProject(event) {
  const files = Array.from(event.target.files || []);
  if (files.length === 0) return;
  try {
    const statusText = await readMatchingFile(files, '/state/agent_status.json');
    if (!statusText) {
      throw new Error('state/agent_status.json was not found in the selected folder.');
    }
    const status = JSON.parse(statusText);
    const currentState = await readMatchingFile(files, '/state/current_state.md');
    const nextActions = await readMatchingFile(files, '/state/next_actions.md');
    status.command_queue = await readMatchingJson(files, '/state/command_queue.json', null);
    status.loop_summary = await readMatchingJson(files, '/state/loop_summary.json', null);
    status.agent_messages = await readMatchingJson(files, '/state/agent_messages.json', null);
    status.agent_votes = await readMatchingJson(files, '/state/agent_votes.json', null);
    status.pattern_memory = await readMatchingJson(files, '/state/pattern_memory.json', null);
    status.ralph_loop = await readMatchingJson(files, '/state/ralph_loop.json', null);
    status.report_snapshot = await readReportSnapshot(files);
    status.agent_events = await readAgentEvents(files);
    status.sessions = await readSessions(files);
    status.gpu_experiment_queue = await readMatchingJson(files, '/state/gpu_experiment_queue.json', null);
    status.dataset_registry = await readMatchingJson(files, '/03_experiments/dataset_registry.json', null);
    status.metric_registry = await readMatchingJson(files, '/03_experiments/metric_registry.json', null);
    status.experiment_runs = await readRunStates(files);
    status.health_warnings = [];
    status.data_sources = buildDirectDataSources(files, status);
    const projectPath = projectNameFromFiles(files);
    render(statusData(status, currentState, nextActions, projectPath));
    refreshStatus.textContent = 'Snapshot mode';
    refreshStatus.className = 'refresh-indicator snapshot';
    setNotice('');
  } catch (error) {
    setNotice(error.message);
  }
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function apiPath(path, params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, value);
    }
  });
  const token = qs('token');
  if (token) search.set('token', token);
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

async function loadProjectsFromServer() {
  const response = await fetch(apiPath('/api/projects'), { cache: 'no-store' });
  if (!response.ok) throw new Error(`Project list failed: ${response.status}`);
  const data = await response.json();
  projectSelect.innerHTML = '';
  data.projects.forEach((project) => {
    const option = document.createElement('option');
    option.value = project;
    option.textContent = project;
    projectSelect.appendChild(option);
  });
  const requested = qs('project') || data.default_project || data.projects[0];
  if (requested) projectSelect.value = requested;
}

async function loadStatusFromServer() {
  const project = projectSelect.value || qs('project') || '';
  const response = await fetch(apiPath('/api/status', { project }), { cache: 'no-store' });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Status failed: ${response.status}`);
  }
  const data = await response.json();
  render(statusData(
    {
      project: data.project,
      last_updated: data.last_updated,
      active_status_values: data.active_status_values || ['running'],
      agents: data.agents || [],
      command_queue: data.command_queue || null,
      loop_summary: data.loop_summary || null,
      agent_messages: data.agent_messages || null,
      agent_events: data.agent_events || [],
      agent_votes: data.agent_votes || null,
      sessions: data.sessions || [],
      pattern_memory: data.pattern_memory || null,
      ralph_loop: data.ralph_loop || null,
      report_snapshot: data.report_snapshot || null,
      data_sources: data.data_sources || null,
      command_runner: data.command_runner || null,
      gpu_experiment_queue: data.gpu_experiment_queue || null,
      dataset_registry: data.dataset_registry || null,
      metric_registry: data.metric_registry || null,
      experiment_runs: data.experiment_runs || [],
      health_warnings: data.health_warnings || []
    },
    data.current_state_excerpt || '',
    data.next_actions_excerpt || '',
    data.project_path || '-',
    data.summary?.last_file_update || '-'
  ));
  refreshStatus.textContent = uiState.paused ? 'Live refresh paused' : `Live refresh: ${Math.round(refreshIntervalMs / 1000)}s`;
  refreshStatus.className = uiState.paused ? 'refresh-indicator snapshot' : 'refresh-indicator live';
  setNotice('');
}

async function runConsoleCommand(commandId) {
  const output = document.getElementById('consoleRunOutput');
  if (!serverMode) {
    setNotice('Command runner requires dashboard server mode.');
    return;
  }
  const project = projectSelect.value || qs('project') || projectNameForCli(lastData || {});
  output.textContent = `$ running ${commandId} for ${project} ...`;
  try {
    const response = await fetch(apiPath('/api/run-command'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
      body: JSON.stringify({ project, id: commandId })
    });
    const textBody = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(textBody);
    } catch {
      payload = { ok: false, returncode: response.status, stdout: '', stderr: textBody };
    }
    output.textContent = [
      `$ ${commandId} exit ${payload.returncode}`,
      payload.stdout ? `\n[stdout]\n${payload.stdout}` : '',
      payload.stderr ? `\n[stderr]\n${payload.stderr}` : ''
    ].join('').trim();
    if (!payload.ok) setNotice(`Command failed: ${commandId}`);
    if (payload.ok) {
      setNotice(`Command passed: ${commandId}`, 'info');
      await loadStatusFromServer();
    }
  } catch (error) {
    output.textContent = `$ ${commandId} failed\n${error.message}`;
    setNotice(error.message);
  }
}

function stopAutoRefresh() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function startAutoRefresh() {
  stopAutoRefresh();
  refreshTimer = window.setInterval(async () => {
    if (!serverMode || document.hidden || refreshInFlight || uiState.paused) return;
    refreshInFlight = true;
    try {
      await loadStatusFromServer();
    } catch (error) {
      setNotice(error.message);
    } finally {
      refreshInFlight = false;
    }
  }, refreshIntervalMs);
}

async function enableServerModeIfAvailable() {
  if (!['http:', 'https:'].includes(window.location.protocol)) return;
  try {
    await loadProjectsFromServer();
    serverMode = true;
    fileControls.hidden = true;
    serverControls.hidden = false;
    await loadStatusFromServer();
    startAutoRefresh();
  } catch {
    serverMode = false;
    stopAutoRefresh();
    fileControls.hidden = false;
    serverControls.hidden = true;
    refreshStatus.textContent = 'Snapshot mode';
    refreshStatus.className = 'refresh-indicator snapshot';
  }
}

input.addEventListener('change', loadProject);
clearButton.addEventListener('click', clearDashboard);
refreshButton.addEventListener('click', () => loadStatusFromServer().catch((error) => setNotice(error.message)));
pauseButton.addEventListener('click', () => {
  uiState.paused = !uiState.paused;
  updateControlState();
  refreshStatus.textContent = uiState.paused ? 'Live refresh paused' : `Live refresh: ${Math.round(refreshIntervalMs / 1000)}s`;
  refreshStatus.className = uiState.paused ? 'refresh-indicator snapshot' : 'refresh-indicator live';
});
clearFiltersButton.addEventListener('click', () => {
  uiState.view = 'overview';
  uiState.statusFilter = 'all';
  uiState.query = '';
  if (lastData) render(lastData);
});
dashboardSearch.addEventListener('input', (event) => {
  uiState.query = event.target.value.trim().toLowerCase();
  if (lastData) render(lastData);
});
document.querySelectorAll('[data-view]').forEach((button) => {
  button.addEventListener('click', () => {
    uiState.view = button.dataset.view || 'all';
    if (lastData) render(lastData);
  });
});
document.querySelectorAll('[data-status-filter]').forEach((button) => {
  button.addEventListener('click', () => {
    uiState.statusFilter = button.dataset.statusFilter || 'all';
    if (lastData) render(lastData);
  });
});
document.addEventListener('click', (event) => {
  const detailButtonElement = event.target.closest('[data-detail-key]');
  if (detailButtonElement) {
    openDetail(detailButtonElement.dataset.detailKey);
    return;
  }
  const copyCliButtonElement = event.target.closest('[data-copy-cli-key]');
  if (copyCliButtonElement) {
    const entry = detailRegistry.get(copyCliButtonElement.dataset.copyCliKey);
    copyText(entry?.cli || '');
    return;
  }
  const copySnippetButtonElement = event.target.closest('[data-copy-snippet]');
  if (copySnippetButtonElement) {
    const snippet = document.getElementById(copySnippetButtonElement.dataset.copySnippet);
    copyText(snippet?.textContent || '');
    return;
  }
  const runCommandButtonElement = event.target.closest('[data-run-command]');
  if (runCommandButtonElement) {
    runConsoleCommand(runCommandButtonElement.dataset.runCommand);
  }
});
drawerClose.addEventListener('click', closeDetail);
drawerBackdrop.addEventListener('click', closeDetail);
copyDrawerJson.addEventListener('click', () => copyText(activeDetail ? JSON.stringify(activeDetail.item, null, 2) : ''));
copyDrawerCli.addEventListener('click', () => copyText(activeDetail?.cli || ''));
document.addEventListener('keydown', (event) => {
  const detailButtonElement = event.target.closest?.('[data-detail-key]');
  if ((event.key === 'Enter' || event.key === ' ') && detailButtonElement) {
    event.preventDefault();
    openDetail(detailButtonElement.dataset.detailKey);
    return;
  }
  if (event.key === 'Escape' && !detailDrawer.hidden) closeDetail();
});
projectSelect.addEventListener('change', () => {
  const url = new URL(window.location.href);
  url.searchParams.set('project', projectSelect.value);
  window.history.replaceState(null, '', url);
  loadStatusFromServer().catch((error) => setNotice(error.message));
});
document.addEventListener('visibilitychange', () => {
  if (serverMode && !document.hidden) {
    loadStatusFromServer().catch((error) => setNotice(error.message));
  }
});

clearDashboard();
enableServerModeIfAvailable();
