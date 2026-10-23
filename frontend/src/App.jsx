import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  Upload,
  Camera,
  CheckCircle2,
  XCircle,
  FileText,
  RefreshCw,
  Search,
  ArrowRightLeft,
  Pencil,
  Lock,
  Unlock,
  AlertOctagon,
  ChevronDown,
  Sparkles,
  Layers,
  ZoomIn,
  Activity,
  Sliders,
  Check,
  X,
  Stethoscope,
  ClipboardCheck,
  Eye
} from 'lucide-react';

const API_BASE = '';

export default function App() {
  const [samples, setSamples] = useState([]);
  const [activePrescription, setActivePrescription] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [editingLineId, setEditingLineId] = useState(null);
  const [customForm, setCustomForm] = useState({ drug: '', dose: '', freq: '', duration: '', notes: '' });
  const [searchResults, setSearchResults] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCropPreview, setSelectedCropPreview] = useState(null);
  const [showCaseDropdown, setShowCaseDropdown] = useState(false);
  const [showDispenseModal, setShowDispenseModal] = useState(false);
  const [processingStage, setProcessingStage] = useState('Analyzing optical quality...');
  
  const fileInputRef = useRef(null);
  const dropdownRef = useRef(null);

  useEffect(() => {
    fetchSamples();
    
    // Close dropdown on outside click
    const handleOutsideClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowCaseDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const fetchSamples = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sample-prescriptions`);
      if (res.ok) {
        const data = await res.json();
        setSamples(data);
      }
    } catch (e) {
      console.error('Error fetching clinical cases:', e);
    }
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    setLoading(true);
    setUploadError(null);
    setActivePrescription(null);
    setProcessingStage('Inspecting blur, lighting & glare...');

    const stageTimer1 = setTimeout(() => {
      setProcessingStage('Segmenting prescription lines & deskewing...');
    }, 1200);
    const stageTimer2 = setTimeout(() => {
      setProcessingStage('Transcribing handwriting & catalog matching...');
    }, 2800);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/api/prescriptions/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Prescription ingestion failed');
      }

      const data = await res.json();
      setActivePrescription(data);
    } catch (e) {
      setUploadError(e.message);
    } finally {
      clearTimeout(stageTimer1);
      clearTimeout(stageTimer2);
      setLoading(false);
    }
  };

  const loadSample = async (sampleId) => {
    setLoading(true);
    setUploadError(null);
    setShowCaseDropdown(false);
    setProcessingStage('Loading clinical case file...');

    try {
      const res = await fetch(`${API_BASE}/api/sample-prescriptions/${sampleId}/load`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to load clinical case');
      const data = await res.json();
      setActivePrescription(data);
    } catch (e) {
      setUploadError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmLine = async (lineId, correctionData = null) => {
    if (!activePrescription) return;
    try {
      const body = correctionData ? JSON.stringify(correctionData) : null;
      const res = await fetch(
        `${API_BASE}/api/prescriptions/${activePrescription.prescription_id}/lines/${lineId}/confirm`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body,
        }
      );

      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Confirmation failed');
        return;
      }

      // Update state locally
      setActivePrescription((prev) => {
        const updatedLines = prev.lines.map((l) => {
          if (l.line_id === lineId) {
            if (correctionData) {
              return {
                ...l,
                status: 'corrected',
                final_drug: correctionData.final_drug,
                final_dose: correctionData.final_dose,
                final_freq: correctionData.final_freq,
                final_duration: correctionData.final_duration,
                confidence: { ...l.confidence, can_confirm: true, level: 'green' },
              };
            }
            return { ...l, status: 'confirmed' };
          }
          return l;
        });

        const hasUnapprovedRed = updatedLines.some(
          (l) => l.confidence.level === 'red' && l.status === 'pending'
        );

        return {
          ...prev,
          lines: updatedLines,
          all_can_confirm: !hasUnapprovedRed,
        };
      });

      setEditingLineId(null);
    } catch (e) {
      alert(`Error confirming line: ${e.message}`);
    }
  };

  const handleConfirmAll = async () => {
    if (!activePrescription) return;
    try {
      const res = await fetch(`${API_BASE}/api/prescriptions/${activePrescription.prescription_id}/confirm-all`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Batch confirmation failed');
        return;
      }

      setActivePrescription((prev) => ({
        ...prev,
        lines: prev.lines.map((l) => ({ ...l, status: 'confirmed' })),
        all_can_confirm: true,
      }));

      setShowDispenseModal(true);
    } catch (e) {
      alert(`Error confirming prescription: ${e.message}`);
    }
  };

  const handleDrugSearch = async (query) => {
    setSearchQuery(query);
    if (!query || query.length < 2) {
      setSearchResults([]);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/drugs/search?q=${encodeURIComponent(query)}`);
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data);
      }
    } catch (e) {
      console.error('Drug search error:', e);
    }
  };

  const unreviewedRedCount = activePrescription?.lines?.filter(
    (l) => l.confidence.level === 'red' && l.status === 'pending'
  ).length || 0;

  const totalLines = activePrescription?.lines?.length || 0;
  const confirmedLinesCount = activePrescription?.lines?.filter(
    (l) => l.status === 'confirmed' || l.status === 'corrected'
  ).length || 0;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Professional Hospital Workstation Navbar */}
      <header
        style={{
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          background: 'rgba(8, 13, 26, 0.85)',
          backdropFilter: 'blur(20px)',
          position: 'sticky',
          top: 0,
          zIndex: 50,
          padding: '12px 28px',
        }}
      >
        <div
          style={{
            maxWidth: 1520,
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          {/* Brand Logo & Clinical System Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                background: 'linear-gradient(135deg, #06b6d4 0%, #0284c7 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 20px rgba(6, 182, 212, 0.35)',
              }}
            >
              <Stethoscope size={24} color="#ffffff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <h1 style={{ fontSize: '1.25rem', fontWeight: 800, letterSpacing: '-0.02em', color: '#ffffff' }}>
                  MEDMATCH <span style={{ color: '#06b6d4' }}>RX</span>
                </h1>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.68rem',
                    padding: '2px 8px',
                    borderRadius: 4,
                    background: 'rgba(6, 182, 212, 0.15)',
                    color: '#38bdf8',
                    border: '1px solid rgba(6, 182, 212, 0.3)',
                    fontWeight: 700,
                  }}
                >
                  CLINICAL WORKSTATION
                </span>
              </div>
              <p style={{ fontSize: '0.76rem', color: 'var(--text-sub)', marginTop: 1 }}>
                Handwriting Reading · Look-Alike Safety Verification · Clinical Validation
              </p>
            </div>
          </div>

          {/* System Telemetry Badges */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="glass-pill" style={{ borderColor: 'rgba(16, 185, 129, 0.25)', color: '#34d399' }}>
              <span className="pulse-dot" style={{ background: '#10b981' }} />
              <span>NLEM 2022 CATALOG (91 DRUGS)</span>
            </div>

            <div className="glass-pill" style={{ borderColor: 'rgba(6, 182, 212, 0.25)', color: '#38bdf8' }}>
              <ShieldCheck size={14} color="#06b6d4" />
              <span>LASA GUARD ACTIVE</span>
            </div>

            {/* Quick Test Case Loader Dropdown */}
            <div style={{ position: 'relative' }} ref={dropdownRef}>
              <button
                className="btn btn-secondary"
                style={{ padding: '8px 14px', fontSize: '0.82rem', gap: 6 }}
                onClick={() => setShowCaseDropdown(!showCaseDropdown)}
              >
                <ClipboardCheck size={15} color="#06b6d4" />
                <span>Load Test Case</span>
                <ChevronDown size={14} color="var(--text-muted)" />
              </button>

              {showCaseDropdown && (
                <div className="dropdown-menu">
                  <div style={{ padding: '8px 14px', fontSize: '0.7rem', color: 'var(--text-sub)', fontWeight: 700, textTransform: 'uppercase' }}>
                    Select Clinical Scenario
                  </div>
                  {samples.map((s) => (
                    <div
                      key={s.id}
                      className="dropdown-item"
                      onClick={() => loadSample(s.id)}
                    >
                      <div>
                        <div style={{ fontSize: '0.84rem', fontWeight: 600, color: '#f8fafc' }}>{s.name}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{s.description}</div>
                      </div>
                      <span
                        className="badge-tag"
                        style={{
                          background:
                            s.category === 'clean' ? 'rgba(16, 185, 129, 0.2)' :
                            s.category === 'lookalike' ? 'rgba(239, 68, 68, 0.2)' :
                            s.category === 'messy' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(148, 163, 184, 0.2)',
                          color:
                            s.category === 'clean' ? '#34d399' :
                            s.category === 'lookalike' ? '#f87171' :
                            s.category === 'messy' ? '#fbbf24' : '#94a3b8',
                        }}
                      >
                        {s.category}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {activePrescription && (
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setActivePrescription(null);
                  setUploadError(null);
                }}
                style={{ padding: '8px 12px' }}
                title="Start new prescription"
              >
                <RefreshCw size={15} />
                <span style={{ fontSize: '0.82rem' }}>New Upload</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Workspace Stage */}
      <main style={{ maxWidth: 1520, margin: '0 auto', padding: '24px 28px', width: '100%', flex: 1 }}>
        {/* Upload Hero Section (Shown when no prescription loaded) */}
        {!activePrescription && (
          <div style={{ maxWidth: 960, margin: '20px auto 40px' }}>
            {/* Hero Header */}
            <div style={{ textAlign: 'center', marginBottom: 32 }}>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 14px',
                  borderRadius: 9999,
                  background: 'rgba(6, 182, 212, 0.1)',
                  border: '1px solid rgba(6, 182, 212, 0.25)',
                  color: '#38bdf8',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  marginBottom: 16,
                }}
              >
                <Activity size={15} />
                <span>INTELLIGENT PRESCRIPTION VERIFICATION WORKSTATION</span>
              </div>
              <h2 style={{ fontSize: '2.2rem', fontWeight: 800, letterSpacing: '-0.03em', marginBottom: 12 }}>
                High-Precision Clinical Handwriting Ingestion
              </h2>
              <p style={{ fontSize: '0.96rem', color: 'var(--text-muted)', maxWidth: 640, margin: '0 auto', lineHeight: 1.6 }}>
                Upload doctor prescriptions, outpatient slips, or handwritten order sheets. Automatically verified against the Indian National List of Essential Medicines with sound-alike hazard safeguards.
              </p>
            </div>

            {/* Prescription Ingestion Dropzone */}
            <div
              className="glass-panel"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
              }}
              style={{
                padding: '48px 32px',
                textAlign: 'center',
                position: 'relative',
                overflow: 'hidden',
                border: '2px dashed rgba(6, 182, 212, 0.35)',
                cursor: 'pointer',
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              {loading && <div className="scan-line" />}

              <input
                id="file-upload-input"
                type="file"
                ref={fileInputRef}
                accept="image/*"
                style={{ display: 'none' }}
                onChange={(e) => {
                  if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
                }}
              />

              <div
                style={{
                  width: 76,
                  height: 76,
                  borderRadius: 20,
                  background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.15) 0%, rgba(2, 132, 199, 0.25) 100%)',
                  border: '1px solid rgba(6, 182, 212, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 20px',
                  color: '#06b6d4',
                  boxShadow: '0 0 25px rgba(6, 182, 212, 0.25)',
                }}
              >
                <Upload size={34} />
              </div>

              <h3 style={{ fontSize: '1.35rem', fontWeight: 700, marginBottom: 8, color: '#f8fafc' }}>
                Drag & Drop Handwritten Prescription
              </h3>
              <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginBottom: 24 }}>
                Supports JPG, PNG, WEBP, or direct camera captures. Automatically deskewed and enhanced.
              </p>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14 }}>
                <button
                  id="btn-select-file"
                  className="btn btn-primary"
                  style={{ padding: '12px 24px', fontSize: '0.92rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  <FileText size={18} /> Select Image File
                </button>
                <button
                  id="btn-camera-capture"
                  className="btn btn-secondary"
                  style={{ padding: '12px 20px', fontSize: '0.92rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  <Camera size={18} /> Snap Photo
                </button>
              </div>

              {/* Loading Indicator */}
              {loading && (
                <div
                  style={{
                    marginTop: 32,
                    padding: '16px 24px',
                    borderRadius: 12,
                    background: 'rgba(6, 182, 212, 0.1)',
                    border: '1px solid rgba(6, 182, 212, 0.3)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 14,
                  }}
                >
                  <RefreshCw size={22} className="pulse-dot" color="#06b6d4" />
                  <span style={{ fontSize: '0.92rem', color: '#38bdf8', fontWeight: 600 }}>
                    {processingStage}
                  </span>
                </div>
              )}

              {uploadError && (
                <div
                  style={{
                    marginTop: 24,
                    padding: '14px 20px',
                    borderRadius: 10,
                    background: 'var(--red-bg)',
                    border: '1px solid var(--red-border)',
                    color: '#f87171',
                    fontSize: '0.9rem',
                    textAlign: 'left',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  <AlertTriangle size={20} color="#f87171" />
                  <span>{uploadError}</span>
                </div>
              )}
            </div>

            {/* Quick Test Case Chips (Integrated naturally) */}
            <div style={{ marginTop: 24, textAlign: 'center' }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-sub)', fontWeight: 600, marginRight: 12 }}>
                OR RUN PRELOADED CLINICAL CASES:
              </span>
              <div style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                {samples.map((s) => (
                  <button
                    key={s.id}
                    className="btn btn-secondary"
                    style={{ padding: '6px 14px', fontSize: '0.8rem', borderRadius: 9999 }}
                    onClick={() => loadSample(s.id)}
                  >
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        background:
                          s.category === 'clean' ? '#10b981' :
                          s.category === 'lookalike' ? '#ef4444' :
                          s.category === 'messy' ? '#f59e0b' : '#94a3b8',
                      }}
                    />
                    <span>{s.name}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Quality Check Rejection Banner */}
        {activePrescription && !activePrescription.quality_check.passed && (
          <div
            id="qc-rejection-banner"
            className="glass-panel"
            style={{
              padding: '28px',
              border: '1px solid var(--red-border)',
              background: 'rgba(239, 68, 68, 0.08)',
              marginBottom: 28,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 20 }}>
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: 14,
                  background: 'rgba(239, 68, 68, 0.2)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ef4444',
                  flexShrink: 0,
                }}
              >
                <XCircle size={30} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f87171' }}>
                    Optical Quality Gating Failed — Retake Required
                  </h3>
                  <span className="glass-pill" style={{ color: '#f87171', borderColor: 'var(--red-border)' }}>
                    SAFETY INTERCEPT
                  </span>
                </div>
                <p style={{ fontSize: '0.92rem', color: 'var(--text-main)', marginBottom: 16 }}>
                  {activePrescription.quality_check.message}
                </p>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
                  <div className="glass-pill" style={{ fontFamily: 'var(--font-mono)' }}>
                    Focus Clarity: {activePrescription.quality_check.blur_score} (min threshold: 70.0)
                  </div>
                  <div className="glass-pill" style={{ fontFamily: 'var(--font-mono)' }}>
                    Mean Illumination: {activePrescription.quality_check.mean_brightness}/255 (min threshold: 50.0)
                  </div>
                  <div className="glass-pill" style={{ fontFamily: 'var(--font-mono)' }}>
                    Specular Glare: {(activePrescription.quality_check.glare_share * 100).toFixed(1)}% (max allowed: 10%)
                  </div>
                </div>

                <button
                  id="btn-retake-photo"
                  className="btn btn-primary"
                  onClick={() => {
                    setActivePrescription(null);
                    fileInputRef.current?.click();
                  }}
                >
                  <Camera size={16} /> Retake Prescription Photo
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Prescription Verification Review Stage */}
        {activePrescription && activePrescription.quality_check.passed && (
          <div>
            {/* Top Verification Header Bar */}
            <div
              className="glass-panel"
              style={{
                padding: '18px 24px',
                marginBottom: 24,
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 20,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 10,
                    background: 'rgba(6, 182, 212, 0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#06b6d4',
                  }}
                >
                  <FileText size={22} />
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 800 }}>
                      PRESCRIPTION <span style={{ fontFamily: 'var(--font-mono)', color: '#06b6d4' }}>#{activePrescription.prescription_id}</span>
                    </h3>
                    <span className="glass-pill" style={{ fontSize: '0.74rem' }}>
                      {totalLines} Medication Lines Extracted
                    </span>
                  </div>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2 }}>
                    Auto-Deskew: {activePrescription.quality_check.deskew_angle}° rotation applied · Blur Score: {activePrescription.quality_check.blur_score}
                  </p>
                </div>
              </div>

              {/* Safety Lock & Batch Approve */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                {unreviewedRedCount > 0 ? (
                  <div
                    style={{
                      padding: '8px 14px',
                      borderRadius: 10,
                      background: 'rgba(239, 68, 68, 0.15)',
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      color: '#f87171',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                    }}
                  >
                    <AlertTriangle size={15} color="#f87171" />
                    <span>{unreviewedRedCount} Red Line{unreviewedRedCount > 1 ? 's' : ''} Require Pharmacist Sign-Off</span>
                  </div>
                ) : (
                  <div
                    style={{
                      padding: '8px 14px',
                      borderRadius: 10,
                      background: 'rgba(16, 185, 129, 0.12)',
                      border: '1px solid rgba(16, 185, 129, 0.35)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      color: '#34d399',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                    }}
                  >
                    <CheckCircle2 size={15} color="#34d399" />
                    <span>All {totalLines} Lines Clinically Verified</span>
                  </div>
                )}

                <button
                  id="btn-confirm-all-prescription"
                  className="btn btn-success"
                  disabled={unreviewedRedCount > 0}
                  onClick={handleConfirmAll}
                  style={{ padding: '10px 20px' }}
                >
                  {unreviewedRedCount > 0 ? <Lock size={16} /> : <Unlock size={16} />}
                  <span>Sign-Off & Dispense Rx</span>
                </button>
              </div>
            </div>

            {/* Split View: Prescription Image Stage + Line Verification Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 24, alignItems: 'start' }}>
              {/* Left Column: Full Prescription Viewer & Quality Radar */}
              <div style={{ position: 'sticky', top: 90 }}>
                <div className="glass-panel" style={{ padding: '18px', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase' }}>
                      SOURCE PRESCRIPTION IMAGE
                    </span>
                    <button
                      className="glass-pill"
                      style={{ cursor: 'pointer', fontSize: '0.74rem' }}
                      onClick={() => setSelectedCropPreview(activePrescription.image_url)}
                    >
                      <ZoomIn size={13} /> Fullscreen
                    </button>
                  </div>

                  <div
                    style={{
                      borderRadius: 12,
                      overflow: 'hidden',
                      background: '#040711',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      maxHeight: 460,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <img
                      src={activePrescription.image_url}
                      alt="Prescription Scan"
                      style={{ width: '100%', height: 'auto', maxHeight: 460, objectFit: 'contain' }}
                      onError={(e) => {
                        e.target.style.display = 'none';
                      }}
                    />
                  </div>

                  {/* Optical Gating HUD */}
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', marginBottom: 8 }}>
                      OPTICAL QUALITY AUDIT
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                      <div style={{ background: 'rgba(255, 255, 255, 0.03)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.68rem', color: 'var(--text-sub)' }}>Focus (Blur)</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#34d399', marginTop: 2 }}>
                          {activePrescription.quality_check.blur_score}
                        </div>
                      </div>
                      <div style={{ background: 'rgba(255, 255, 255, 0.03)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.68rem', color: 'var(--text-sub)' }}>Illumination</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#38bdf8', marginTop: 2 }}>
                          {activePrescription.quality_check.mean_brightness}
                        </div>
                      </div>
                      <div style={{ background: 'rgba(255, 255, 255, 0.03)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.68rem', color: 'var(--text-sub)' }}>Glare Wash</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#a78bfa', marginTop: 2 }}>
                          {(activePrescription.quality_check.glare_share * 100).toFixed(1)}%
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column: Line-by-Line Medication Verification Stream */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {activePrescription.lines.map((line) => {
                  const isRed = line.confidence.level === 'red';
                  const isYellow = line.confidence.level === 'yellow';
                  const isGreen = line.confidence.level === 'green';
                  const isConfirmed = line.status === 'confirmed' || line.status === 'corrected';
                  const isEditing = editingLineId === line.line_id;

                  return (
                    <div
                      key={line.line_id}
                      id={`line-card-${line.line_id}`}
                      className="glass-panel"
                      style={{
                        padding: '22px 24px',
                        borderLeft: `5px solid ${
                          isConfirmed ? '#10b981' : isRed ? '#ef4444' : isYellow ? '#f59e0b' : '#10b981'
                        }`,
                        background: isConfirmed ? 'rgba(16, 185, 129, 0.04)' : 'var(--bg-card)',
                      }}
                    >
                      {/* Line Card Header */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span
                            style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.85rem',
                              fontWeight: 700,
                              padding: '4px 10px',
                              borderRadius: 6,
                              background: 'rgba(255, 255, 255, 0.08)',
                              color: '#ffffff',
                            }}
                          >
                            LINE #{line.line_id}
                          </span>

                          <span
                            className={`glass-pill badge-${line.confidence.level}`}
                            style={{ fontWeight: 700, fontSize: '0.78rem' }}
                          >
                            <span
                              className="pulse-dot"
                              style={{
                                background: isGreen ? '#10b981' : isYellow ? '#f59e0b' : '#ef4444',
                              }}
                            />
                            {line.confidence.level.toUpperCase()} CONFIDENCE ({(line.confidence.score * 100).toFixed(0)}%)
                          </span>

                          {line.status === 'corrected' && (
                            <span className="glass-pill" style={{ color: '#38bdf8', borderColor: 'rgba(56, 189, 248, 0.3)' }}>
                              <Pencil size={12} /> Pharmacist Corrected
                            </span>
                          )}
                          {line.status === 'confirmed' && (
                            <span className="glass-pill" style={{ color: '#34d399', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                              <CheckCircle2 size={12} /> Approved
                            </span>
                          )}
                        </div>

                        {/* Top Line Action Buttons */}
                        {!isEditing && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <button
                              id={`btn-edit-line-${line.line_id}`}
                              className="btn btn-secondary"
                              style={{ padding: '6px 14px', fontSize: '0.82rem' }}
                              onClick={() => {
                                setEditingLineId(line.line_id);
                                const cleanVal = (v) => (!v || v.toLowerCase() === 'unreadable' || v.toLowerCase() === 'unknown') ? '' : v;
                                setCustomForm({
                                  drug: cleanVal(line.final_drug || line.selected_candidate?.brand_name),
                                  dose: cleanVal(line.final_dose || line.dose_raw),
                                  freq: cleanVal(line.final_freq || line.freq_raw),
                                  duration: cleanVal(line.final_duration || line.duration_raw),
                                  notes: '',
                                });
                              }}
                            >
                              <Pencil size={14} /> Modify
                            </button>

                            <button
                              id={`btn-approve-line-${line.line_id}`}
                              className={`btn ${isConfirmed ? 'btn-secondary' : 'btn-success'}`}
                              style={{ padding: '6px 16px', fontSize: '0.82rem' }}
                              disabled={isRed && line.status === 'pending'}
                              onClick={() => handleConfirmLine(line.line_id)}
                              title={isRed && line.status === 'pending' ? 'Pharmacist review required for red line' : 'Approve this line'}
                            >
                              <CheckCircle2 size={15} />
                              {isConfirmed ? 'Re-Verify' : 'Approve Line'}
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Main Line Content: Crop vs Drug Identification */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 1fr) 2fr', gap: 24 }}>
                        {/* Left: Original Handwritten Crop Preview */}
                        <div>
                          <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-sub)', marginBottom: 8, textTransform: 'uppercase' }}>
                            ORIGINAL HANDWRITTEN SEGMENT:
                          </div>
                          <div
                            style={{
                              background: '#ffffff',
                              borderRadius: 12,
                              padding: 10,
                              border: '1px solid rgba(255, 255, 255, 0.1)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              cursor: 'zoom-in',
                              boxShadow: '0 4px 14px rgba(0, 0, 0, 0.3)',
                            }}
                            onClick={() => setSelectedCropPreview(line.crop)}
                            title="Click to zoom image"
                          >
                            <img
                              src={line.crop}
                              alt={`Handwritten Line ${line.line_id}`}
                              style={{ maxWidth: '100%', maxHeight: 95, objectFit: 'contain' }}
                              onError={(e) => {
                                e.target.style.display = 'none';
                              }}
                            />
                          </div>

                          <div style={{ marginTop: 10, fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                            <span style={{ color: 'var(--text-sub)' }}>Detected Handwriting: </span>
                            <span style={{ fontFamily: 'var(--font-mono)', color: '#f8fafc', fontWeight: 600 }}>
                              {line.guesses.join(', ') || 'unreadable'}
                            </span>
                          </div>
                        </div>

                        {/* Right: Identified Drug, Safety Hazard & Regimen */}
                        <div>
                          {/* Identified Drug Brand & Generic */}
                          <div style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                              <span style={{ fontSize: '1.45rem', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.02em' }}>
                                {line.final_drug || line.selected_candidate?.brand_name || 'Illegible / Unreadable'}
                              </span>
                              {line.selected_candidate?.generic_name && (
                                <span style={{ fontSize: '0.92rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                                  ({line.selected_candidate.generic_name})
                                </span>
                              )}
                              {line.selected_candidate?.form && (
                                <span
                                  style={{
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.72rem',
                                    padding: '2px 8px',
                                    borderRadius: 4,
                                    background: 'rgba(6, 182, 212, 0.15)',
                                    color: '#38bdf8',
                                    fontWeight: 600,
                                  }}
                                >
                                  {line.selected_candidate.form}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Look-Alike / Sound-Alike (LASA) Confusable Pair Alert */}
                          {line.lookalike?.is_flagged && (
                            <div
                              id={`lookalike-warning-${line.line_id}`}
                              style={{
                                padding: '12px 16px',
                                borderRadius: 10,
                                background: 'rgba(239, 68, 68, 0.14)',
                                border: '1px solid rgba(239, 68, 68, 0.45)',
                                marginBottom: 16,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: 14,
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <AlertOctagon size={22} color="#f87171" />
                                <span style={{ fontSize: '0.84rem', color: '#fca5a5', lineHeight: 1.45, fontWeight: 500 }}>
                                  {line.lookalike.warning_message}
                                </span>
                              </div>

                              {line.lookalike.paired_drug && (
                                <button
                                  className="btn btn-secondary"
                                  style={{
                                    padding: '6px 14px',
                                    fontSize: '0.78rem',
                                    background: 'rgba(239, 68, 68, 0.25)',
                                    borderColor: 'rgba(239, 68, 68, 0.55)',
                                    color: '#ffffff',
                                    whiteSpace: 'nowrap',
                                    fontWeight: 700,
                                  }}
                                  onClick={() => {
                                    handleConfirmLine(line.line_id, {
                                      final_drug: line.lookalike.paired_drug,
                                      final_dose: line.final_dose || line.dose_raw,
                                      final_freq: line.final_freq || line.freq_raw,
                                      final_duration: line.final_duration || line.duration_raw,
                                      corrected_by: 'pharmacist',
                                      notes: `Swapped confusable pair from ${line.selected_candidate?.brand_name} to ${line.lookalike.paired_drug}`,
                                    });
                                  }}
                                >
                                  <ArrowRightLeft size={14} /> Swap to {line.lookalike.paired_drug}
                                </button>
                              )}
                            </div>
                          )}

                          {/* Clinical Regimen Fields Grid */}
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
                            {/* Dose */}
                            <div
                              style={{
                                background: 'rgba(255, 255, 255, 0.04)',
                                borderRadius: 10,
                                padding: '10px 14px',
                                border: !line.validation.dose_valid ? '1px solid var(--yellow-border)' : '1px solid var(--bg-card-border)',
                              }}
                            >
                              <div style={{ fontSize: '0.72rem', color: 'var(--text-sub)', fontWeight: 700, textTransform: 'uppercase' }}>
                                Prescribed Dose
                              </div>
                              <div style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 2 }}>
                                {line.final_dose || line.validation.dose_standardized || line.dose_raw || 'Missing'}
                              </div>
                              {!line.validation.dose_valid && (
                                <div style={{ fontSize: '0.7rem', color: '#fbbf24', marginTop: 4, fontWeight: 500 }}>
                                  {line.validation.dose_flag}
                                </div>
                              )}
                            </div>

                            {/* Frequency */}
                            <div
                              style={{
                                background: 'rgba(255, 255, 255, 0.04)',
                                borderRadius: 10,
                                padding: '10px 14px',
                                border: !line.validation.freq_valid ? '1px solid var(--yellow-border)' : '1px solid var(--bg-card-border)',
                              }}
                            >
                              <div style={{ fontSize: '0.72rem', color: 'var(--text-sub)', fontWeight: 700, textTransform: 'uppercase' }}>
                                Standard Frequency
                              </div>
                              <div style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 2 }}>
                                {line.final_freq || line.validation.freq_standardized || line.freq_raw || 'Missing'}
                              </div>
                              {!line.validation.freq_valid && (
                                <div style={{ fontSize: '0.7rem', color: '#fbbf24', marginTop: 4, fontWeight: 500 }}>
                                  {line.validation.freq_flag}
                                </div>
                              )}
                            </div>

                            {/* Duration */}
                            <div
                              style={{
                                background: 'rgba(255, 255, 255, 0.04)',
                                borderRadius: 10,
                                padding: '10px 14px',
                                border: !line.validation.duration_valid ? '1px solid var(--yellow-border)' : '1px solid var(--bg-card-border)',
                              }}
                            >
                              <div style={{ fontSize: '0.72rem', color: 'var(--text-sub)', fontWeight: 700, textTransform: 'uppercase' }}>
                                Duration
                              </div>
                              <div style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 2 }}>
                                {line.final_duration || line.validation.duration_standardized || line.duration_raw || 'Missing'}
                              </div>
                              {!line.validation.duration_valid && (
                                <div style={{ fontSize: '0.7rem', color: '#fbbf24', marginTop: 4, fontWeight: 500 }}>
                                  {line.validation.duration_flag}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* One-Click Fast Fix Candidates */}
                          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                            <span style={{ fontSize: '0.74rem', color: 'var(--text-sub)', fontWeight: 700, textTransform: 'uppercase' }}>
                              One-Click Fast Fix:
                            </span>
                            {line.top_candidates?.map((cand, cIdx) => (
                              <button
                                key={cIdx}
                                id={`one-click-pill-${line.line_id}-${cand.brand_name}`}
                                className="btn btn-secondary"
                                style={{
                                  padding: '4px 12px',
                                  fontSize: '0.8rem',
                                  borderRadius: 9999,
                                  background:
                                    (line.final_drug || line.selected_candidate?.brand_name) === cand.brand_name
                                      ? 'rgba(6, 182, 212, 0.22)'
                                      : 'rgba(255, 255, 255, 0.05)',
                                  borderColor:
                                    (line.final_drug || line.selected_candidate?.brand_name) === cand.brand_name
                                      ? '#06b6d4'
                                      : 'rgba(255, 255, 255, 0.1)',
                                }}
                                onClick={() => {
                                  handleConfirmLine(line.line_id, {
                                    final_drug: cand.brand_name,
                                    final_dose: line.final_dose || line.dose_raw,
                                    final_freq: line.final_freq || line.freq_raw,
                                    final_duration: line.final_duration || line.duration_raw,
                                    corrected_by: 'pharmacist',
                                    notes: `Selected candidate #${cIdx + 1} from match ranking`,
                                  });
                                }}
                              >
                                {cand.brand_name} ({(cand.combined_score * 100).toFixed(0)}%)
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Inline Pharmacist Modification Drawer */}
                      {isEditing && (
                        <div
                          style={{
                            marginTop: 20,
                            padding: '20px',
                            borderRadius: 12,
                            background: 'rgba(15, 23, 42, 0.95)',
                            border: '1px solid rgba(6, 182, 212, 0.35)',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <Pencil size={16} color="#06b6d4" />
                              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc' }}>
                                Pharmacist Manual Verification & Override
                              </h4>
                            </div>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                              onClick={() => setEditingLineId(null)}
                            >
                              <X size={14} /> Cancel
                            </button>
                          </div>

                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 14 }}>
                            {/* Search Drug */}
                            <div style={{ position: 'relative' }}>
                              <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-sub)', marginBottom: 4, fontWeight: 700 }}>
                                MEDICATION BRAND NAME
                              </label>
                              <input
                                type="text"
                                value={customForm.drug}
                                onChange={(e) => {
                                  setCustomForm({ ...customForm, drug: e.target.value });
                                  handleDrugSearch(e.target.value);
                                }}
                                placeholder="Type drug name..."
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  background: 'rgba(255, 255, 255, 0.06)',
                                  border: '1px solid rgba(255, 255, 255, 0.15)',
                                  borderRadius: 8,
                                  color: '#ffffff',
                                  fontSize: '0.85rem',
                                  outline: 'none',
                                }}
                              />
                              {searchResults.length > 0 && (
                                <div
                                  style={{
                                    position: 'absolute',
                                    top: '100%',
                                    left: 0,
                                    right: 0,
                                    background: '#0f172a',
                                    border: '1px solid rgba(255, 255, 255, 0.15)',
                                    borderRadius: 8,
                                    marginTop: 4,
                                    zIndex: 50,
                                    maxHeight: 180,
                                    overflowY: 'auto',
                                    boxShadow: '0 8px 20px rgba(0,0,0,0.5)',
                                  }}
                                >
                                  {searchResults.map((d, dIdx) => (
                                    <div
                                      key={dIdx}
                                      style={{
                                        padding: '8px 12px',
                                        fontSize: '0.8rem',
                                        cursor: 'pointer',
                                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                                      }}
                                      onMouseDown={() => {
                                        setCustomForm({ ...customForm, drug: d.brand_name });
                                        setSearchResults([]);
                                      }}
                                    >
                                      <strong>{d.brand_name}</strong> ({d.generic_name})
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>

                            {/* Dose Input */}
                            <div>
                              <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-sub)', marginBottom: 4, fontWeight: 700 }}>
                                DOSE / STRENGTH
                              </label>
                              <input
                                type="text"
                                value={customForm.dose}
                                onChange={(e) => setCustomForm({ ...customForm, dose: e.target.value })}
                                placeholder="e.g. 500mg, 10ml"
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  background: 'rgba(255, 255, 255, 0.06)',
                                  border: '1px solid rgba(255, 255, 255, 0.15)',
                                  borderRadius: 8,
                                  color: '#ffffff',
                                  fontSize: '0.85rem',
                                  outline: 'none',
                                }}
                              />
                            </div>

                            {/* Frequency Input */}
                            <div>
                              <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-sub)', marginBottom: 4, fontWeight: 700 }}>
                                FREQUENCY
                              </label>
                              <input
                                type="text"
                                value={customForm.freq}
                                onChange={(e) => setCustomForm({ ...customForm, freq: e.target.value })}
                                placeholder="e.g. 1-0-1, OD, TDS"
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  background: 'rgba(255, 255, 255, 0.06)',
                                  border: '1px solid rgba(255, 255, 255, 0.15)',
                                  borderRadius: 8,
                                  color: '#ffffff',
                                  fontSize: '0.85rem',
                                  outline: 'none',
                                }}
                              />
                            </div>

                            {/* Duration Input */}
                            <div>
                              <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-sub)', marginBottom: 4, fontWeight: 700 }}>
                                DURATION
                              </label>
                              <input
                                type="text"
                                value={customForm.duration}
                                onChange={(e) => setCustomForm({ ...customForm, duration: e.target.value })}
                                placeholder="e.g. 5 days, 1 week"
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  background: 'rgba(255, 255, 255, 0.06)',
                                  border: '1px solid rgba(255, 255, 255, 0.15)',
                                  borderRadius: 8,
                                  color: '#ffffff',
                                  fontSize: '0.85rem',
                                  outline: 'none',
                                }}
                              />
                            </div>
                          </div>

                          {/* Pharmacist Notes */}
                          <div style={{ marginBottom: 16 }}>
                            <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-sub)', marginBottom: 4, fontWeight: 700 }}>
                              CLINICAL AUDIT JUSTIFICATION
                            </label>
                            <input
                              type="text"
                              value={customForm.notes}
                              onChange={(e) => setCustomForm({ ...customForm, notes: e.target.value })}
                              placeholder="Clinical rationale for override..."
                              style={{
                                width: '100%',
                                padding: '8px 12px',
                                background: 'rgba(255, 255, 255, 0.06)',
                                border: '1px solid rgba(255, 255, 255, 0.15)',
                                borderRadius: 8,
                                color: '#ffffff',
                                fontSize: '0.85rem',
                                outline: 'none',
                              }}
                            />
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                            <button
                              className="btn btn-secondary"
                              onClick={() => setEditingLineId(null)}
                            >
                              Cancel
                            </button>
                            <button
                              className="btn btn-success"
                              onClick={() => {
                                handleConfirmLine(line.line_id, {
                                  final_drug: customForm.drug || line.final_drug,
                                  final_dose: customForm.dose || line.final_dose,
                                  final_freq: customForm.freq || line.final_freq,
                                  final_duration: customForm.duration || line.final_duration,
                                  corrected_by: 'pharmacist',
                                  notes: customForm.notes || 'Pharmacist verified & confirmed override',
                                });
                              }}
                            >
                              Save & Sign Line
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Verified Electronic Dispense Modal */}
      {showDispenseModal && (
        <div className="modal-overlay" onClick={() => setShowDispenseModal(false)}>
          <div
            className="glass-panel"
            style={{ maxWidth: 640, width: '100%', padding: '32px', background: '#0b1120' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ textAlign: 'center', marginBottom: 24 }}>
              <div
                style={{
                  width: 60,
                  height: 60,
                  borderRadius: '50%',
                  background: 'rgba(16, 185, 129, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 16px',
                  color: '#10b981',
                }}
              >
                <CheckCircle2 size={36} />
              </div>
              <h3 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#f8fafc' }}>
                Prescription Verified & Approved for Dispense
              </h3>
              <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginTop: 4 }}>
                All medication lines have passed clinical safety checks and look-alike verification.
              </p>
            </div>

            <div
              style={{
                background: 'rgba(255, 255, 255, 0.03)',
                borderRadius: 12,
                padding: '16px 20px',
                marginBottom: 24,
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, fontSize: '0.82rem' }}>
                <span style={{ color: 'var(--text-sub)' }}>Prescription Number:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: '#38bdf8', fontWeight: 700 }}>
                  #{activePrescription?.prescription_id}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, fontSize: '0.82rem' }}>
                <span style={{ color: 'var(--text-sub)' }}>Approved Lines:</span>
                <span style={{ color: '#10b981', fontWeight: 700 }}>{activePrescription?.lines?.length} of {activePrescription?.lines?.length} Verified</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem' }}>
                <span style={{ color: 'var(--text-sub)' }}>Pharmacist Signature:</span>
                <span style={{ color: '#f8fafc', fontWeight: 600 }}>LIC# IN-PHARM-88219 (Logged to Audit Table)</span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowDispenseModal(false)}
              >
                Close
              </button>
              <button
                className="btn btn-primary"
                onClick={() => {
                  setShowDispenseModal(false);
                  setActivePrescription(null);
                }}
              >
                Proceed to Next Prescription
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Image Zoom Modal */}
      {selectedCropPreview && (
        <div className="modal-overlay" onClick={() => setSelectedCropPreview(null)}>
          <div
            className="glass-panel"
            style={{ padding: 20, background: '#ffffff', borderRadius: 16, maxWidth: 840 }}
            onClick={(e) => e.stopPropagation()}
          >
            <img src={selectedCropPreview} alt="Zoomed Segment" style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain' }} />
            <div style={{ marginTop: 14, textAlign: 'right' }}>
              <button className="btn btn-secondary" style={{ color: '#000', borderColor: '#cbd5e1' }} onClick={() => setSelectedCropPreview(null)}>
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clinical Workstation Footer */}
      <footer
        style={{
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          padding: '16px 28px',
          textAlign: 'center',
          fontSize: '0.78rem',
          color: 'var(--text-sub)',
          background: 'rgba(8, 13, 26, 0.6)',
        }}
      >
        MedMatch Rx™ · Hospital Clinical Pharmacist Ingestion Workstation · NLEM Pharmacopeia Verified · Real-Time LASA Prevention
      </footer>
    </div>
  );
}
