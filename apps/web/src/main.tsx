import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { FRAMEWORK_NAME } from '@v3/shared';
import './styles.css';

function App() {
  return (
    <main>
      <p className="eyebrow">Adaptive engineering control plane</p>
      <h1>{FRAMEWORK_NAME}</h1>
      <p>The runtime foundation is installed. Managed projects and lifecycle views arrive in later milestones.</p>
    </main>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing application root');
createRoot(root).render(<StrictMode><App /></StrictMode>);
