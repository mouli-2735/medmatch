import React, { StrictMode, Component } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Clinical Workstation Error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            background: '#060a12',
            color: '#ffffff',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          <div
            style={{
              maxWidth: 520,
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: 16,
              padding: 28,
              textAlign: 'center',
            }}
          >
            <h2 style={{ color: '#ef4444', marginBottom: 12 }}>Clinical Workstation Notification</h2>
            <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: 20 }}>
              {this.state.error?.message || 'An error occurred during component rendering.'}
            </p>
            <button
              onClick={() => window.location.reload()}
              style={{
                background: '#06b6d4',
                color: '#040914',
                border: 'none',
                padding: '10px 22px',
                borderRadius: 8,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Reload Workstation
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
);
