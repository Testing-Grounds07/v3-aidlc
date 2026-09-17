import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { plainStatus, type ProjectDashboard } from '@v3/dashboard';
import './styles.css';

const demo: ProjectDashboard = {
  project: { id: 'PRJ-V3-AIDLC', name: 'V3-AIDLC', outcome: 'Make AI-assisted delivery adaptive, verifiable, and understandable.', status: 'active' },
  summary: { completed: 7, active: 2, waiting: 1, blocked: 0 },
  work: [
    { id: 'WP-8', title: 'Project dashboard', workstream: 'Product experience', stage: 'Implementation', mode: 'Feature development', posture: 'Balanced', status: 'running', progress: 68, summary: 'Building a clear view of progress, proof, and decisions.', lastUpdatedAt: new Date() },
    { id: 'WP-9', title: 'Process health', workstream: 'Framework intelligence', stage: 'Investigation', mode: 'Measurement', posture: 'Explore', status: 'planned', progress: 12, summary: 'Defining useful signals for speed, rework, and verification quality.', lastUpdatedAt: new Date() },
    { id: 'WP-7', title: 'Human approvals', workstream: 'Governance', stage: 'Verification', mode: 'Independent review', posture: 'Assured', status: 'reviewing', progress: 92, summary: 'Checking that choices and delegated authority stay safe and understandable.', lastUpdatedAt: new Date() },
  ],
  decisions: [{ id: 'DR-1', headline: 'Choose the first hosted environment', question: 'Should the first shared deployment use a team sandbox or production controls?', impact: 'The choice changes setup effort and who can use it.', optionCount: 2, requestedAt: new Date() }],
  evidence: { passed: 27, failed: 0, inconclusive: 1, updatedAt: new Date() },
};

function Dashboard({ snapshot }: { readonly snapshot: ProjectDashboard }) {
  const totalEvidence = snapshot.evidence.passed + snapshot.evidence.failed + snapshot.evidence.inconclusive;
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">V3</span><span>Adaptive delivery</span></div>
      <nav aria-label="Primary navigation"><a className="active" href="#overview">Overview</a><a href="#work">Work</a><a href="#decisions">Decisions</a><a href="#evidence">Evidence</a></nav>
      <div className="system-status"><span className="status-dot" />Framework online<br /><small>State is up to date</small></div>
    </aside>
    <main>
      <header className="topbar"><div><p className="eyebrow">Managed project</p><h1>{snapshot.project.name}</h1></div><button type="button">View activity</button></header>
      <section className="outcome" id="overview"><p className="eyebrow">What we are trying to achieve</p><h2>{snapshot.project.outcome}</h2></section>
      <section className="metrics" aria-label="Project summary"><article><span>{snapshot.summary.completed}</span><p>Complete</p></article><article><span>{snapshot.summary.active}</span><p>In progress</p></article><article><span>{snapshot.summary.waiting}</span><p>Waiting</p></article><article><span>{snapshot.summary.blocked}</span><p>Blocked</p></article></section>
      <div className="content-grid">
        <section className="panel work-panel" id="work"><div className="panel-heading"><div><p className="eyebrow">Current work</p><h2>What is happening now</h2></div><span>{snapshot.work.length}</span></div>
          <div className="work-list">{snapshot.work.map((item) => <article className="work-card" key={item.id}>
            <div className="work-card-top"><div><p className="workstream">{item.workstream}</p><h3>{item.title}</h3></div><span className={`pill status-${item.status}`}>{plainStatus(item.status)}</span></div>
            <p>{item.summary}</p><div className="tags"><span>{item.stage}</span><span>{item.mode}</span><span>{item.posture}</span></div>
            <div className="progress-row"><div className="progress-track"><span style={{ width: `${item.progress}%` }} /></div><strong>{item.progress}%</strong></div>
          </article>)}</div>
        </section>
        <div className="side-stack">
          <section className="panel decision-panel" id="decisions"><div className="panel-heading"><div><p className="eyebrow">Your attention</p><h2>Decisions</h2></div><span>{snapshot.decisions.length}</span></div>
            {snapshot.decisions.length === 0 ? <p className="empty">Nothing needs your input right now.</p> : snapshot.decisions.map((decision) => <article className="decision" key={decision.id}><h3>{decision.headline}</h3><p>{decision.question}</p><small>{decision.impact}</small><button type="button">Review choices</button></article>)}
          </section>
          <section className="panel evidence-panel" id="evidence"><p className="eyebrow">Accepted proof</p><h2>Evidence health</h2><div className="evidence-score"><span>{totalEvidence === 0 ? 0 : Math.round(snapshot.evidence.passed / totalEvidence * 100)}%</span><p>of checks are passing</p></div><dl><div><dt>Passed</dt><dd>{snapshot.evidence.passed}</dd></div><div><dt>Needs attention</dt><dd>{snapshot.evidence.failed}</dd></div><div><dt>Still checking</dt><dd>{snapshot.evidence.inconclusive}</dd></div></dl></section>
        </div>
      </div>
    </main>
  </div>;
}

function App() {
  const [snapshot, setSnapshot] = useState<ProjectDashboard | null>(null);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (query.get('demo') === '1') { setSnapshot(demo); return; }
    const projectId = query.get('project') ?? 'PRJ-V3-AIDLC';
    fetch(`/projects/${encodeURIComponent(projectId)}/dashboard`).then(async (response) => {
      if (!response.ok) throw new Error('This project dashboard is not available yet.');
      return response.json() as Promise<ProjectDashboard>;
    }).then(setSnapshot).catch((error: unknown) => setProblem(error instanceof Error ? error.message : 'Unable to load the dashboard.'));
  }, []);
  if (problem) return <div className="center-card"><p className="eyebrow">Dashboard unavailable</p><h1>We could not load this project.</h1><p>{problem}</p><a href="?demo=1">Open the example dashboard</a></div>;
  if (snapshot === null) return <div className="center-card"><p className="eyebrow">Loading</p><h1>Getting the latest project state…</h1></div>;
  return <Dashboard snapshot={snapshot} />;
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing application root');
createRoot(root).render(<StrictMode><App /></StrictMode>);
