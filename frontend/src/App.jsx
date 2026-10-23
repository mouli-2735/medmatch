import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Upload,
  Camera,
  CheckCircle2,
  XCircle,
  FileText,
  BarChart3,
  RefreshCw,
  Search,
  Sparkles,
  ChevronRight,
  ArrowRightLeft,
  Pencil,
  Eye,
  Info,
  Lock,
  Unlock,
  AlertOctagon
} from 'lucide-react';

const API_BASE = '';

export default function App() {
  const [samples, setSamples] = useState([]);
  const [activePrescription, setActivePrescription] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [benchmarkMetrics, setBenchmarkMetrics] = useState(null);
  const [showBenchmarkModal, setShowBenchmarkModal] = useState(false);
  const [editingLineId, setEditingLineId] = useState(null);
  const [customForm, setCustomForm] = useState({ drug: '', dose: '', freq: '', duration: '', notes: '' });
  const [searchResults, setSearchResults] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCropPreview, setSelectedCropPreview] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchSamples();
    fetchMetrics();
  }, []);

  const fetchSamples = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sample-prescriptions`);
      if (res.ok) {
        const data = await res.json();
        setSamples(data);
      }
    } catch (e) {
      console.error('Error fetching samples:', e);
    }
  };

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/benchmark/metrics`);
      if (res.ok) {
        const data = await res.json();
        setBenchmarkMetrics(data);
      }
    } catch (e) {
      console.error('Error fetching metrics:', e);
    }
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    setLoading(true);
    setUploadError(null);
    setActivePrescription(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/api/prescriptions/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload failed');
      }

      const data = await res.json();
      setActivePrescription(data);
    } catch (e) {
      setUploadError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadSample = async (sampleId) => {
    setLoading(true);
    setUploadError(null);
    try {
      const res = await fetch(`${API_BASE}/api/sample-prescriptions/${sampleId}/load`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to load sample');
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

        // Recheck all_can_confirm
        const allReviewed = updatedLines.every(
          (l) => l.status === 'confirmed' || l.status === 'corrected' || l.confidence.can_confirm
        );

        return { ...prev, lines: updatedLines, all_can_confirm: allReviewed };
      });

      setEditingLineId(null);
    } catch (e) {
      alert(e.message);
    }
  };

  const handleConfirmAll = async () => {
    if (!activePrescription) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/prescriptions/${activePrescription.prescription_id}/confirm-all`,
        { method: 'POST' }
      );
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Error confirming all');
        return;
      }
      alert('All lines verified and prescription successfully archived into hospital database.');
      setActivePrescription((prev) => ({
        ...prev,
        lines: prev.lines.map((l) => ({ ...l, status: 'confirmed' })),
      }));
    } catch (e) {
      alert(e.message);
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
      console.error(e);
    }
  };

  // Determine if confirm all is blocked by low-confidence unreviewed red lines
  const unreviewedRedCount = activePrescription?.lines
    ? activePrescription.lines.filter(
        (l) => l.confidence.level === 'red' && l.status === 'pending'
      ).length
    : 0;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Header */}
      <header
        style={{
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          background: 'rgba(11, 15, 25, 0.85)',
          backdropFilter: 'blur(12px)',
          position: 'sticky',
          top: 0,
          zIndex: 50,
          padding: '14px 28px',
        }}
      >
        <div style={{ maxWidth: 1400, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 10,
                background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 15px rgba(6, 182, 212, 0.4)',
              }}
            >
              <ShieldCheck size={24} color="#ffffff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <h1 style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '-0.02em' }}>MedMatch Rx</h1>
                <span className="glass-pill" style={{ color: '#10b981', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                  <span className="pulse-dot" style={{ background: '#10b981' }} /> Active
                </span>
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>
                Handwriting Reading · Look-Alike Safety Verification · Clinical Validation
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="glass-pill" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
              <Sparkles size={14} color="#06b6d4" /> Gemini 3.8 Flash + OpenCV
            </span>

            <button
              id="btn-slide7-metrics"
              className="btn btn-secondary"
              onClick={() => setShowBenchmarkModal(true)}
              style={{ padding: '8px 14px', fontSize: '0.82rem' }}
            >
              <BarChart3 size={16} color="#06b6d4" />
              Slide 7 Benchmark
            </button>

            {activePrescription && (
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setActivePrescription(null);
                  setUploadError(null);
                }}
                style={{ padding: '8px 12px' }}
                title="Reset session"
              >
                <RefreshCw size={15} />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ maxWidth: 1400, margin: '0 auto', padding: '24px', width: '100%', flex: 1 }}>
        {/* Step 11: Demo Scenarios Selector for Slide 7 */}
        <section style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Slide 7 Demo Scenarios
              </span>
              <span className="glass-pill" style={{ fontSize: '0.72rem' }}>1-Click Instant Run</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
            {samples.map((s) => (
              <div
                key={s.id}
                id={`scenario-card-${s.id}`}
                className="glass-panel"
                onClick={() => loadSample(s.id)}
                style={{
                  padding: '14px 16px',
                  cursor: 'pointer',
                  border: activePrescription?.prescription_id === s.id ? '1px solid #06b6d4' : '1px solid var(--bg-card-border)',
                  background: activePrescription?.prescription_id === s.id ? 'rgba(6, 182, 212, 0.12)' : 'var(--bg-card)',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      padding: '2px 8px',
                      borderRadius: 4,
                      background:
                        s.category === 'clean'
                          ? 'rgba(16, 185, 129, 0.2)'
                          : s.category === 'lookalike'
                          ? 'rgba(239, 68, 68, 0.2)'
                          : s.category === 'messy'
                          ? 'rgba(245, 158, 11, 0.2)'
                          : 'rgba(148, 163, 184, 0.2)',
                      color:
                        s.category === 'clean'
                          ? '#34d399'
                          : s.category === 'lookalike'
                          ? '#f87171'
                          : s.category === 'messy'
                          ? '#fbbf24'
                          : '#94a3b8',
                    }}
                  >
                    {s.category}
                  </span>
                  <ChevronRight size={15} color="var(--text-sub)" />
                </div>
                <h4 style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: 4 }}>
                  {s.name}
                </h4>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                  {s.description}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Upload Zone (Visible if no prescription or if uploading) */}
        {!activePrescription && (
          <section className="glass-panel" style={{ padding: '36px', textAlign: 'center', marginBottom: 24 }}>
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
              }}
              style={{
                border: '2px dashed rgba(6, 182, 212, 0.35)',
                borderRadius: 16,
                padding: '40px 20px',
                background: 'rgba(6, 182, 212, 0.03)',
                cursor: 'pointer',
              }}
              onClick={() => fileInputRef.current?.click()}
            >
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
                  width: 64,
                  height: 64,
                  borderRadius: '50%',
                  background: 'rgba(6, 182, 212, 0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 16px',
                  color: '#06b6d4',
                }}
              >
                <Upload size={30} />
              </div>

              <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: 8 }}>
                Upload Handwritten Doctor Prescription
              </h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', maxWidth: 500, margin: '0 auto 18px' }}>
                Drag and drop image or snap with phone camera. Evaluated with OpenCV blur/glare inspection and Gemini 3.8 Flash multimodal recognition.
              </p>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
                <button
                  id="btn-select-file"
                  className="btn btn-primary"
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  <FileText size={16} /> Choose Image File
                </button>
                <button
                  id="btn-camera-capture"
                  className="btn btn-secondary"
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  <Camera size={16} /> Camera Photo
                </button>
              </div>
            </div>

            {loading && (
              <div style={{ marginTop: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
                <RefreshCw size={20} className="pulse-dot" color="#06b6d4" />
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                  Processing image with OpenCV Deskew + Gemini OCR + RapidFuzz Matching...
                </span>
              </div>
            )}

            {uploadError && (
              <div
                style={{
                  marginTop: 20,
                  padding: '12px 16px',
                  borderRadius: 10,
                  background: 'var(--red-bg)',
                  border: '1px solid var(--red-border)',
                  color: '#f87171',
                  fontSize: '0.88rem',
                }}
              >
                {uploadError}
              </div>
            )}
          </section>
        )}

        {/* Step 7: Image Quality Rejected Banner */}
        {activePrescription && !activePrescription.quality_check.passed && (
          <section
            id="qc-rejection-banner"
            className="glass-panel"
            style={{
              padding: '24px',
              border: '1px solid var(--red-border)',
              background: 'rgba(239, 68, 68, 0.1)',
              marginBottom: 24,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 12,
                  background: 'rgba(239, 68, 68, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ef4444',
                  flexShrink: 0,
                }}
              >
                <XCircle size={28} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f87171' }}>
                    Photo Quality Check Failed — Retake Required
                  </h3>
                  <span className="glass-pill" style={{ color: '#f87171', borderColor: 'var(--red-border)' }}>
                    OpenCV Guard Active
                  </span>
                </div>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: 12 }}>
                  {activePrescription.quality_check.message}
                </p>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                  <div className="glass-pill" style={{ fontFamily: 'var(--font-mono)' }}>
                    Focus Score: {activePrescription.quality_check.blur_score} (min: 70.0)
                  </div>
                  <div className="glass-pill" style={{ fontFamily: 'var(--font-mono)' }}>
                    Mean Brightness: {activePrescription.quality_check.mean_brightness}/255 (min: 50.0)
                  </div>
                  <div className="glass-pill" style={{ fontFamily: 'var(--font-mono)' }}>
                    Glare Washout: {(activePrescription.quality_check.glare_share * 100).toFixed(1)}% (max: 10%)
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
          </section>
        )}

        {/* Step 9: Review Screen (Prescription details and line item cards) */}
        {activePrescription && activePrescription.quality_check.passed && (
          <section>
            {/* Header info bar */}
            <div
              className="glass-panel"
              style={{
                padding: '16px 20px',
                marginBottom: 20,
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 16,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <FileText size={22} color="#06b6d4" />
                <div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>
                    Prescription ID: <span style={{ fontFamily: 'var(--font-mono)', color: '#06b6d4' }}>{activePrescription.prescription_id}</span>
                  </h3>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    {activePrescription.total_lines} lines detected · OpenCV Deskew: {activePrescription.quality_check.deskew_angle}° tilt corrected
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                {unreviewedRedCount > 0 ? (
                  <span className="glass-pill" style={{ color: '#f87171', borderColor: 'var(--red-border)' }}>
                    <AlertTriangle size={14} color="#f87171" />
                    {unreviewedRedCount} Red line{unreviewedRedCount > 1 ? 's' : ''} require pharmacist review
                  </span>
                ) : (
                  <span className="glass-pill" style={{ color: '#34d399', borderColor: 'var(--green-border)' }}>
                    <CheckCircle2 size={14} color="#34d399" />
                    All lines verified
                  </span>
                )}

                <button
                  id="btn-confirm-all-prescription"
                  className="btn btn-success"
                  disabled={unreviewedRedCount > 0}
                  onClick={handleConfirmAll}
                  title={
                    unreviewedRedCount > 0
                      ? 'Confirm button blocked until every red line is reviewed'
                      : 'Approve full prescription'
                  }
                >
                  {unreviewedRedCount > 0 ? <Lock size={16} /> : <Unlock size={16} />}
                  Confirm Full Prescription
                </button>
              </div>
            </div>

            {/* Line items list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
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
                      padding: '20px',
                      borderLeft: `4px solid ${
                        isConfirmed ? '#10b981' : isRed ? '#ef4444' : isYellow ? '#f59e0b' : '#10b981'
                      }`,
                      transition: 'all 0.2s ease',
                    }}
                  >
                    {/* Top Row: Line number + Confidence Badge + Status */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.85rem',
                            fontWeight: 700,
                            padding: '3px 8px',
                            borderRadius: 6,
                            background: 'rgba(255, 255, 255, 0.08)',
                          }}
                        >
                          Line #{line.line_id}
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
                          <span className="glass-pill" style={{ color: '#38bdf8' }}>
                            <Pencil size={12} /> Pharmacist Corrected
                          </span>
                        )}
                        {line.status === 'confirmed' && (
                          <span className="glass-pill" style={{ color: '#34d399' }}>
                            <CheckCircle2 size={12} /> Approved
                          </span>
                        )}
                      </div>

                      {/* Right Action: Quick Approve */}
                      {!isEditing && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <button
                            id={`btn-edit-line-${line.line_id}`}
                            className="btn btn-secondary"
                            style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                            onClick={() => {
                              setEditingLineId(line.line_id);
                              setCustomForm({
                                drug: line.final_drug || line.selected_candidate?.brand_name || '',
                                dose: line.final_dose || line.dose_raw || '',
                                freq: line.final_freq || line.freq_raw || '',
                                duration: line.final_duration || line.duration_raw || '',
                                notes: '',
                              });
                            }}
                          >
                            <Pencil size={14} /> Edit
                          </button>

                          <button
                            id={`btn-approve-line-${line.line_id}`}
                            className={`btn ${isConfirmed ? 'btn-secondary' : 'btn-success'}`}
                            style={{ padding: '6px 14px', fontSize: '0.8rem' }}
                            disabled={isRed && line.status === 'pending'}
                            onClick={() => handleConfirmLine(line.line_id)}
                          >
                            <CheckCircle2 size={14} />
                            {isConfirmed ? 'Re-Approve' : 'Approve Line'}
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Middle Section: Line Crop next to Extracted Fields */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) 2fr', gap: 20 }}>
                      {/* Left: Cropped handwritten image */}
                      <div>
                        <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-sub)', marginBottom: 6 }}>
                          ORIGINAL HANDWRITTEN CROP:
                        </div>
                        <div
                          style={{
                            background: '#ffffff',
                            borderRadius: 10,
                            padding: 8,
                            border: '1px solid rgba(255,255,255,0.1)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            cursor: 'zoom-in',
                          }}
                          onClick={() => setSelectedCropPreview(line.crop)}
                        >
                          <img
                            src={line.crop}
                            alt={`Crop Line ${line.line_id}`}
                            style={{ maxWidth: '100%', maxHeight: 90, objectFit: 'contain' }}
                            onError={(e) => {
                              e.target.style.display = 'none';
                            }}
                          />
                        </div>

                        {/* Raw OCR output readout */}
                        <div style={{ marginTop: 8, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          <span style={{ color: 'var(--text-sub)' }}>Gemini Raw Guesses: </span>
                          <span style={{ fontFamily: 'var(--font-mono)' }}>{line.guesses.join(', ') || 'unreadable'}</span>
                        </div>
                      </div>

                      {/* Right: Matched Drug, Dose, Freq, Duration */}
                      <div>
                        {/* Drug Name Header */}
                        <div style={{ marginBottom: 12 }}>
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                            <span style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>
                              {line.final_drug || line.selected_candidate?.brand_name || 'Unreadable'}
                            </span>
                            {line.selected_candidate?.generic_name && (
                              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                ({line.selected_candidate.generic_name})
                              </span>
                            )}
                            {line.selected_candidate?.form && (
                              <span className="glass-pill" style={{ fontSize: '0.72rem' }}>
                                {line.selected_candidate.form}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Step 6: Confusable Look-Alike Warning Banner */}
                        {line.lookalike?.is_flagged && (
                          <div
                            id={`lookalike-warning-${line.line_id}`}
                            style={{
                              padding: '10px 14px',
                              borderRadius: 8,
                              background: 'rgba(239, 68, 68, 0.15)',
                              border: '1px solid rgba(239, 68, 68, 0.4)',
                              marginBottom: 14,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: 12,
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                              <AlertOctagon size={20} color="#f87171" />
                              <span style={{ fontSize: '0.82rem', color: '#fca5a5', lineHeight: 1.4 }}>
                                {line.lookalike.warning_message}
                              </span>
                            </div>

                            {/* 1-Click Swap Button for look-alike pair */}
                            {line.lookalike.paired_drug && (
                              <button
                                className="btn btn-secondary"
                                style={{
                                  padding: '5px 10px',
                                  fontSize: '0.75rem',
                                  background: 'rgba(239, 68, 68, 0.25)',
                                  borderColor: 'rgba(239, 68, 68, 0.5)',
                                  color: '#ffffff',
                                  whiteSpace: 'nowrap',
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
                                <ArrowRightLeft size={13} /> Swap to {line.lookalike.paired_drug}
                              </button>
                            )}
                          </div>
                        )}

                        {/* Clinical Validation Badges Grid */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 14 }}>
                          {/* Dose */}
                          <div
                            style={{
                              background: 'rgba(255, 255, 255, 0.04)',
                              borderRadius: 8,
                              padding: '8px 12px',
                              border: !line.validation.dose_valid ? '1px solid var(--yellow-border)' : '1px solid var(--bg-card-border)',
                            }}
                          >
                            <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)', textTransform: 'uppercase' }}>Dose</div>
                            <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-main)', marginTop: 2 }}>
                              {line.final_dose || line.validation.dose_standardized || line.dose_raw || 'Missing'}
                            </div>
                            {!line.validation.dose_valid && (
                              <div style={{ fontSize: '0.68rem', color: '#fbbf24', marginTop: 4 }}>
                                {line.validation.dose_flag}
                              </div>
                            )}
                          </div>

                          {/* Frequency */}
                          <div
                            style={{
                              background: 'rgba(255, 255, 255, 0.04)',
                              borderRadius: 8,
                              padding: '8px 12px',
                              border: !line.validation.freq_valid ? '1px solid var(--yellow-border)' : '1px solid var(--bg-card-border)',
                            }}
                          >
                            <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)', textTransform: 'uppercase' }}>Frequency</div>
                            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', marginTop: 2 }}>
                              {line.final_freq || line.validation.freq_standardized || line.freq_raw || 'Missing'}
                            </div>
                            {!line.validation.freq_valid && (
                              <div style={{ fontSize: '0.68rem', color: '#fbbf24', marginTop: 4 }}>
                                {line.validation.freq_flag}
                              </div>
                            )}
                          </div>

                          {/* Duration */}
                          <div
                            style={{
                              background: 'rgba(255, 255, 255, 0.04)',
                              borderRadius: 8,
                              padding: '8px 12px',
                              border: !line.validation.duration_valid ? '1px solid var(--yellow-border)' : '1px solid var(--bg-card-border)',
                            }}
                          >
                            <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)', textTransform: 'uppercase' }}>Duration</div>
                            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', marginTop: 2 }}>
                              {line.final_duration || line.validation.duration_standardized || line.duration_raw || 'Missing'}
                            </div>
                            {!line.validation.duration_valid && (
                              <div style={{ fontSize: '0.68rem', color: '#fbbf24', marginTop: 4 }}>
                                {line.validation.duration_flag}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Step 4 & 9: One-Click Fix Pills (Top 3 Candidates) */}
                        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-sub)', fontWeight: 600 }}>ONE-CLICK FIX:</span>
                          {line.top_candidates?.map((cand, cIdx) => (
                            <button
                              key={cIdx}
                              id={`one-click-pill-${line.line_id}-${cand.brand_name}`}
                              className="btn btn-secondary"
                              style={{
                                padding: '4px 10px',
                                fontSize: '0.78rem',
                                borderRadius: 9999,
                                background:
                                  (line.final_drug || line.selected_candidate?.brand_name) === cand.brand_name
                                    ? 'rgba(6, 182, 212, 0.2)'
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
                                  notes: `Selected candidate #${cIdx + 1} from top-3 suggestions`,
                                });
                              }}
                            >
                              {cand.brand_name} ({(cand.combined_score * 100).toFixed(0)}%)
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Inline Pharmacist Edit Drawer */}
                    {isEditing && (
                      <div
                        style={{
                          marginTop: 18,
                          padding: 16,
                          borderRadius: 12,
                          background: 'rgba(15, 23, 42, 0.95)',
                          border: '1px solid rgba(6, 182, 212, 0.3)',
                        }}
                      >
                        <h5 style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: 12, color: '#38bdf8' }}>
                          Pharmacist Manual Prescription Correction
                        </h5>

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 12 }}>
                          {/* Searchable Medicine */}
                          <div style={{ position: 'relative' }}>
                            <label style={{ fontSize: '0.72rem', color: 'var(--text-sub)', display: 'block', marginBottom: 4 }}>
                              Medicine Name (Search Drug Catalog)
                            </label>
                            <input
                              type="text"
                              value={customForm.drug}
                              onChange={(e) => {
                                setCustomForm({ ...customForm, drug: e.target.value });
                                handleDrugSearch(e.target.value);
                              }}
                              placeholder="e.g. Augmentin, Celebrex..."
                              style={{
                                width: '100%',
                                padding: '8px 12px',
                                borderRadius: 8,
                                background: '#1e293b',
                                border: '1px solid #334155',
                                color: '#ffffff',
                                fontSize: '0.85rem',
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
                                  border: '1px solid #334155',
                                  borderRadius: 8,
                                  zIndex: 20,
                                  maxHeight: 180,
                                  overflowY: 'auto',
                                  boxShadow: '0 10px 20px rgba(0,0,0,0.5)',
                                }}
                              >
                                {searchResults.map((r, rIdx) => (
                                  <div
                                    key={rIdx}
                                    style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #1e293b', fontSize: '0.8rem' }}
                                    onClick={() => {
                                      setCustomForm({ ...customForm, drug: r.brand_name });
                                      setSearchResults([]);
                                    }}
                                  >
                                    <span style={{ fontWeight: 600, color: '#ffffff' }}>{r.brand_name}</span>{' '}
                                    <span style={{ color: 'var(--text-sub)' }}>({r.generic_name})</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>

                          {/* Dose */}
                          <div>
                            <label style={{ fontSize: '0.72rem', color: 'var(--text-sub)', display: 'block', marginBottom: 4 }}>
                              Dose / Strength
                            </label>
                            <input
                              type="text"
                              value={customForm.dose}
                              onChange={(e) => setCustomForm({ ...customForm, dose: e.target.value })}
                              placeholder="e.g. 625mg, 200mg"
                              style={{
                                width: '100%',
                                padding: '8px 12px',
                                borderRadius: 8,
                                background: '#1e293b',
                                border: '1px solid #334155',
                                color: '#ffffff',
                                fontSize: '0.85rem',
                              }}
                            />
                          </div>

                          {/* Frequency */}
                          <div>
                            <label style={{ fontSize: '0.72rem', color: 'var(--text-sub)', display: 'block', marginBottom: 4 }}>
                              Frequency
                            </label>
                            <input
                              type="text"
                              value={customForm.freq}
                              onChange={(e) => setCustomForm({ ...customForm, freq: e.target.value })}
                              placeholder="e.g. 1-0-1, OD, TDS"
                              style={{
                                width: '100%',
                                padding: '8px 12px',
                                borderRadius: 8,
                                background: '#1e293b',
                                border: '1px solid #334155',
                                color: '#ffffff',
                                fontSize: '0.85rem',
                              }}
                            />
                          </div>

                          {/* Duration */}
                          <div>
                            <label style={{ fontSize: '0.72rem', color: 'var(--text-sub)', display: 'block', marginBottom: 4 }}>
                              Duration
                            </label>
                            <input
                              type="text"
                              value={customForm.duration}
                              onChange={(e) => setCustomForm({ ...customForm, duration: e.target.value })}
                              placeholder="e.g. 5d, 7 days"
                              style={{
                                width: '100%',
                                padding: '8px 12px',
                                borderRadius: 8,
                                background: '#1e293b',
                                border: '1px solid #334155',
                                color: '#ffffff',
                                fontSize: '0.85rem',
                              }}
                            />
                          </div>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                          <button className="btn btn-secondary" onClick={() => setEditingLineId(null)}>
                            Cancel
                          </button>
                          <button
                            id={`btn-save-edit-${line.line_id}`}
                            className="btn btn-primary"
                            onClick={() => {
                              handleConfirmLine(line.line_id, {
                                final_drug: customForm.drug,
                                final_dose: customForm.dose,
                                final_freq: customForm.freq,
                                final_duration: customForm.duration,
                                corrected_by: 'pharmacist',
                                notes: 'Manual pharmacist correction from drawer',
                              });
                            }}
                          >
                            Save & Verify Line
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </main>

      {/* Slide 7 Verified Performance Modal */}
      {showBenchmarkModal && (
        <div className="modal-overlay" onClick={() => setShowBenchmarkModal(false)}>
          <div
            className="glass-panel"
            style={{ maxWidth: 680, width: '100%', padding: '28px', background: '#0f172a' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <BarChart3 size={24} color="#06b6d4" />
                <h3 style={{ fontSize: '1.25rem', fontWeight: 800 }}>Slide 7 Benchmark Report</h3>
              </div>
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 8px', borderRadius: '50%' }}
                onClick={() => setShowBenchmarkModal(false)}
              >
                ✕
              </button>
            </div>

            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 20 }}>
              Verified test numbers across synthetic doctor prescriptions benchmark including clean, messy cursive, look-alike confusable pairs, and bad camera shots.
            </p>

            {benchmarkMetrics ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>Top-1 Drug Recognition</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#10b981', marginTop: 4 }}>
                    {benchmarkMetrics.top_1_drug_accuracy_percent}%
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Exact match on first candidate</div>
                </div>

                <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>Top-3 Drug Recognition</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#06b6d4', marginTop: 4 }}>
                    {benchmarkMetrics.top_3_drug_accuracy_percent}%
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Correct drug in 3 guesses</div>
                </div>

                <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>Look-Alike Hazard Recall</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#f59e0b', marginTop: 4 }}>
                    {benchmarkMetrics.lookalike_hazard_detection_rate_percent}%
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Confusable pairs flagged</div>
                </div>

                <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>Clinical Field Accuracy</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#a855f7', marginTop: 4 }}>
                    {benchmarkMetrics.overall_field_accuracy_percent}%
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Dose + Frequency + Duration</div>
                </div>

                <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>Pharmacist Review Time</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#38bdf8', marginTop: 4 }}>
                    {benchmarkMetrics.average_pharmacist_review_seconds}s
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Down from 2-3 minutes manual</div>
                </div>

                <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>Photo QC Rejection Rate</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#f43f5e', marginTop: 4 }}>
                    {benchmarkMetrics.qc_rejection_rate_percent}%
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Filtered blur, dark & glare</div>
                </div>
              </div>
            ) : (
              <p>Loading benchmark data...</p>
            )}

            <div style={{ marginTop: 20, textAlign: 'right' }}>
              <button className="btn btn-primary" onClick={() => setShowBenchmarkModal(false)}>
                Done
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
            style={{ padding: 16, background: '#ffffff', borderRadius: 16, maxWidth: 800 }}
            onClick={(e) => e.stopPropagation()}
          >
            <img src={selectedCropPreview} alt="Zoomed Crop" style={{ maxWidth: '100%', maxHeight: '70vh' }} />
            <div style={{ marginTop: 12, textAlign: 'right' }}>
              <button className="btn btn-secondary" style={{ color: '#000' }} onClick={() => setSelectedCropPreview(null)}>
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer
        style={{
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          padding: '16px 28px',
          textAlign: 'center',
          fontSize: '0.78rem',
          color: 'var(--text-sub)',
        }}
      >
        MedMatch Rx · Clinical Pharmacist Decision Support System · Google DeepMind Build Plan
      </footer>
    </div>
  );
}
