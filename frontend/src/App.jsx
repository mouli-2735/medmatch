import React, { useState, useRef } from 'react';
import confetti from 'canvas-confetti';
import {
  AlertTriangle,
  Upload,
  Camera,
  CheckCircle2,
  XCircle,
  FileText,
  RefreshCw,
  ArrowRightLeft,
  Pencil,
  Lock,
  Unlock,
  AlertOctagon,
  Sparkles,
  ZoomIn,
  ZoomOut,
  RotateCw,
  X,
  Stethoscope,
  History,
  Target,
  Smile
} from 'lucide-react';

import ThreeDMedicalScene from './components/ThreeDMedicalScene';
import DoctorAvatarAssistant from './components/DoctorAvatarAssistant';
import InteractiveDoctor3D from './components/InteractiveDoctor3D';

const API_BASE = '';

export default function App() {
  const [activePrescription, setActivePrescription] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [editingLineId, setEditingLineId] = useState(null);
  const [customForm, setCustomForm] = useState({ drug: '', dose: '', freq: '', duration: '', notes: '' });
  const [searchResults, setSearchResults] = useState([]);
  const [selectedCropPreview, setSelectedCropPreview] = useState(null);
  const [showDispenseModal, setShowDispenseModal] = useState(false);
  const [showAuditDrawer, setShowAuditDrawer] = useState(false);
  const [processingStage, setProcessingStage] = useState('Analyzing optical quality...');
  
  // Interactive Canvas Image Controls
  const [zoomLevel, setZoomLevel] = useState(1);
  const [imageFilter, setImageFilter] = useState('normal'); // 'normal' | 'contrast' | 'invert'
  const [imageRotation, setImageRotation] = useState(0);
  const [hoveredLineId, setHoveredLineId] = useState(null);
  const [activeFilterTab, setActiveFilterTab] = useState('all'); // 'all' | 'red' | 'lookalike' | 'confirmed'
  const [auditLog, setAuditLog] = useState([]);

  // 3D Parallax Tilt for Hero Tablet Card
  const [tiltStyle, setTiltStyle] = useState({});
  const [heroViewMode, setHeroViewMode] = useState('doctor'); // 'doctor' | 'tablet'

  const fileInputRef = useRef(null);
  const heroCardRef = useRef(null);

  const handleHeroMouseMove = (e) => {
    if (!heroCardRef.current) return;
    const rect = heroCardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -8;
    const rotateY = ((x - centerX) / centerX) * 8;
    setTiltStyle({
      transform: `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`,
      transition: 'transform 0.1s ease',
    });
  };

  const handleHeroMouseLeave = () => {
    setTiltStyle({
      transform: 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)',
      transition: 'transform 0.5s ease',
    });
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    setLoading(true);
    setUploadError(null);
    setActivePrescription(null);
    setZoomLevel(1);
    setImageFilter('normal');
    setImageRotation(0);
    setProcessingStage('Inspecting blur, lighting & glare...');

    const stageTimer1 = setTimeout(() => {
      setProcessingStage('Segmenting prescription lines & deskewing...');
    }, 1200);
    const stageTimer2 = setTimeout(() => {
      setProcessingStage('Neural handwriting transcription & NLEM catalog match...');
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
      logAuditEvent('Ingestion', `Prescription #${data.prescription_id} uploaded and segmented (${data.lines?.length || 0} lines)`);
    } catch (e) {
      setUploadError(e.message);
    } finally {
      clearTimeout(stageTimer1);
      clearTimeout(stageTimer2);
      setLoading(false);
    }
  };



  const logAuditEvent = (action, detail) => {
    const entry = {
      id: Date.now(),
      timestamp: new Date().toLocaleTimeString(),
      action,
      detail,
      user: 'Dr. Alex Reed (Pharm.D)',
    };
    setAuditLog((prev) => [entry, ...prev]);
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

      if (correctionData) {
        logAuditEvent('Line Override', `Line #${lineId} modified: ${correctionData.final_drug} (${correctionData.notes || 'Pharmacist correction'})`);
      } else {
        logAuditEvent('Line Approved', `Line #${lineId} verified and signed off`);
      }

      setEditingLineId(null);
    } catch (e) {
      alert(`Error confirming line: ${e.message}`);
    }
  };

  const triggerCelebrationConfetti = () => {
    try {
      confetti({
        particleCount: 110,
        spread: 80,
        origin: { y: 0.6 },
        colors: ['#06b6d4', '#10b981', '#38bdf8', '#fbbf24', '#ffffff']
      });
    } catch (e) {
      // Graceful fallback
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

      logAuditEvent('Batch Approval', `Prescription #${activePrescription.prescription_id} fully approved and released to dispense queue`);
      triggerCelebrationConfetti();
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

  // Metrics calculation
  const unreviewedRedCount = activePrescription?.lines?.filter(
    (l) => l.confidence.level === 'red' && l.status === 'pending'
  ).length || 0;

  const lookalikeCount = activePrescription?.lines?.filter(
    (l) => l.lookalike?.is_flagged
  ).length || 0;

  const totalLines = activePrescription?.lines?.length || 0;
  const confirmedLinesCount = activePrescription?.lines?.filter(
    (l) => l.status === 'confirmed' || l.status === 'corrected'
  ).length || 0;

  // Filtered Lines based on active tab
  const filteredLines = (activePrescription?.lines || []).filter((l) => {
    if (activeFilterTab === 'red') return l.confidence.level === 'red' && l.status === 'pending';
    if (activeFilterTab === 'lookalike') return l.lookalike?.is_flagged;
    if (activeFilterTab === 'confirmed') return l.status === 'confirmed' || l.status === 'corrected';
    return true;
  });

  const getImageFilterStyle = () => {
    let filterString = '';
    if (imageFilter === 'contrast') filterString += 'contrast(190%) brightness(110%) saturate(120%) ';
    if (imageFilter === 'invert') filterString += 'invert(1) hue-rotate(180deg) contrast(150%) ';
    return {
      transform: `scale(${zoomLevel}) rotate(${imageRotation}deg)`,
      filter: filterString.trim() || 'none',
      transition: 'transform 0.25s ease, filter 0.25s ease',
      transformOrigin: 'center center',
    };
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {/* 3D Three.js Floating Molecule Scene in Background */}
      <ThreeDMedicalScene isScanning={loading} />

      {/* Floating 3D Doctor Avatar Assistant */}
      <DoctorAvatarAssistant
        activePrescription={activePrescription}
        loading={loading}
        processingStage={processingStage}
        hoveredLineId={hoveredLineId}
      />

      {/* Top Clinical Workstation Header with Animated ECG Pulse */}
      <header
        style={{
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          background: 'rgba(7, 11, 22, 0.92)',
          backdropFilter: 'blur(20px)',
          position: 'sticky',
          top: 0,
          zIndex: 50,
          padding: '12px 28px',
        }}
      >
        <div
          style={{
            maxWidth: 1600,
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          {/* Logo & Clinical System Pulse */}
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
                boxShadow: '0 0 20px rgba(6, 182, 212, 0.4)',
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

          {/* Animated ECG Pulse Telemetry in Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              className="glass-pill"
              style={{ padding: '6px 14px', gap: 10, borderColor: 'rgba(6, 182, 212, 0.25)' }}
            >
              <svg width="60" height="20" viewBox="0 0 100 30" style={{ overflow: 'visible' }}>
                <path
                  d="M0,15 L30,15 L35,5 L40,25 L45,10 L50,18 L55,15 L100,15"
                  fill="none"
                  stroke="#06b6d4"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="ecg-path"
                />
              </svg>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.74rem', color: '#38bdf8', fontWeight: 600 }}>
                SYSTEM ACTIVE
              </span>
            </div>

            <div className="glass-pill" style={{ borderColor: 'rgba(16, 185, 129, 0.25)', color: '#34d399' }}>
              <span className="pulse-dot" style={{ background: '#10b981' }} />
              <span>NLEM 2022 CATALOG (91 DRUGS)</span>
            </div>



            {/* Audit Trail Drawer Toggle */}
            <button
              className="btn btn-secondary"
              onClick={() => setShowAuditDrawer(!showAuditDrawer)}
              style={{ padding: '8px 12px' }}
              title="View Clinical Audit Trail"
            >
              <History size={16} color="#06b6d4" />
              <span style={{ fontSize: '0.82rem' }}>Audit Log</span>
              {auditLog.length > 0 && (
                <span
                  style={{
                    padding: '2px 6px',
                    borderRadius: 9999,
                    background: '#06b6d4',
                    color: '#080d1a',
                    fontSize: '0.7rem',
                    fontWeight: 800,
                  }}
                >
                  {auditLog.length}
                </span>
              )}
            </button>

            {activePrescription && (
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setActivePrescription(null);
                  setUploadError(null);
                  setAuditLog([]);
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
      <main style={{ maxWidth: 1600, margin: '0 auto', padding: '24px 28px', width: '100%', flex: 1, zIndex: 10 }}>
        {/* EDITORIAL HERO SECTION (Modeled after reference layout with Doctor Tablet Desk 3D Tilt) */}
        {!activePrescription && (
          <div>
            {/* Top Interactive Editorial Banner */}
            <div
              className="glass-panel"
              style={{
                marginBottom: 36,
                padding: '24px',
                borderRadius: 24,
                background: 'rgba(12, 19, 36, 0.85)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                display: 'grid',
                gridTemplateColumns: '1.2fr 1fr',
                gap: 36,
                alignItems: 'center',
              }}
            >
              {/* Left: Interactive 3D Doctor Studio OR Tablet Desk Card */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {/* View Switcher Controls */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button
                      className="glass-pill"
                      onClick={() => setHeroViewMode('doctor')}
                      style={{
                        background: heroViewMode === 'doctor' ? 'rgba(6, 182, 212, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                        borderColor: heroViewMode === 'doctor' ? '#06b6d4' : 'rgba(255, 255, 255, 0.1)',
                        color: heroViewMode === 'doctor' ? '#38bdf8' : 'var(--text-muted)',
                        fontWeight: 700,
                        cursor: 'pointer',
                        padding: '5px 14px',
                        fontSize: '0.76rem',
                      }}
                    >
                      <Smile size={13} color="#06b6d4" /> 3D Doctor Studio
                    </button>
                    <button
                      className="glass-pill"
                      onClick={() => setHeroViewMode('tablet')}
                      style={{
                        background: heroViewMode === 'tablet' ? 'rgba(6, 182, 212, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                        borderColor: heroViewMode === 'tablet' ? '#06b6d4' : 'rgba(255, 255, 255, 0.1)',
                        color: heroViewMode === 'tablet' ? '#38bdf8' : 'var(--text-muted)',
                        fontWeight: 700,
                        cursor: 'pointer',
                        padding: '5px 14px',
                        fontSize: '0.76rem',
                      }}
                    >
                      <FileText size={13} color="#06b6d4" /> Digital Tablet Desk
                    </button>
                  </div>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-sub)' }}>
                    {heroViewMode === 'doctor' ? 'Live Interactive WebGL' : '3D Perspective Tilt'}
                  </span>
                </div>

                {heroViewMode === 'doctor' ? (
                  <div style={{ width: '100%', height: 490 }}>
                    <InteractiveDoctor3D
                      activePrescription={activePrescription}
                      loading={loading}
                      processingStage={processingStage}
                      hoveredLineId={hoveredLineId}
                      onUploadClick={() => fileInputRef.current?.click()}
                    />
                  </div>
                ) : (
                  <div
                    ref={heroCardRef}
                    onMouseMove={handleHeroMouseMove}
                    onMouseLeave={handleHeroMouseLeave}
                    style={{
                      borderRadius: 20,
                      overflow: 'hidden',
                      position: 'relative',
                      boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6), 0 0 30px rgba(6, 182, 212, 0.25)',
                      cursor: 'pointer',
                      ...tiltStyle,
                    }}
                    onClick={() => fileInputRef.current?.click()}
                    title="Click to scan prescription on doctor's digital tablet"
                  >
                    <img
                      src="/assets/doctor_tablet_desk.jpg"
                      alt="Doctor Prescription Tablet Desk"
                      style={{ width: '100%', height: 'auto', display: 'block', objectFit: 'cover' }}
                    />
                    <div
                      style={{
                        position: 'absolute',
                        top: 16,
                        left: 16,
                        background: 'rgba(4, 8, 18, 0.75)',
                        backdropFilter: 'blur(10px)',
                        padding: '6px 14px',
                        borderRadius: 9999,
                        border: '1px solid rgba(6, 182, 212, 0.4)',
                        color: '#38bdf8',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      <Sparkles size={13} color="#06b6d4" />
                      <span>3D CLINICAL INGESTION TABLET</span>
                    </div>
                    {loading && <div className="laser-scanner-line" />}
                  </div>
                )}
              </div>

              {/* Right: Editorial Typography & Actions */}
              <div style={{ padding: '12px 10px' }}>
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 14px',
                    borderRadius: 9999,
                    background: 'rgba(6, 182, 212, 0.12)',
                    border: '1px solid rgba(6, 182, 212, 0.3)',
                    color: '#38bdf8',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    marginBottom: 16,
                  }}
                >
                  <Stethoscope size={15} />
                  <span>MEDMATCH RX CLINICAL INGESTION</span>
                </div>

                <h2
                  style={{
                    fontSize: '2.5rem',
                    fontWeight: 800,
                    letterSpacing: '-0.03em',
                    lineHeight: 1.15,
                    marginBottom: 16,
                    color: '#ffffff',
                  }}
                >
                  Precision in Every Script. <br />
                  <span style={{ color: '#06b6d4' }}>Clinical Pharmacist AI.</span>
                </h2>

                <p style={{ fontSize: '0.95rem', color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 24 }}>
                  Turn illegible doctor handwriting into standardized, error-free clinical orders. Cross-checked against 91 NLEM essential medicines and verified against high-risk Look-Alike Sound-Alike confusion hazards in real time.
                </p>

                <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                  <button
                    className="btn btn-primary"
                    style={{ padding: '12px 28px', fontSize: '0.94rem' }}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload size={18} /> Ingest Prescription
                  </button>
                  <button
                    className="btn btn-secondary"
                    style={{ padding: '12px 24px', fontSize: '0.94rem' }}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Camera size={18} color="#06b6d4" /> Snap Photo
                  </button>
                </div>
              </div>
            </div>

            {/* Prescription Drag & Drop Upload Zone */}
            <div
              className="glass-panel glass-panel-hoverable"
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
                marginBottom: 36,
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              {loading && <div className="laser-scanner-line" />}

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
                  borderRadius: 22,
                  background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.18) 0%, rgba(2, 132, 199, 0.3) 100%)',
                  border: '1px solid rgba(6, 182, 212, 0.45)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 18px',
                  color: '#06b6d4',
                  boxShadow: '0 0 30px rgba(6, 182, 212, 0.3)',
                }}
              >
                <Upload size={34} />
              </div>

              <h3 style={{ fontSize: '1.35rem', fontWeight: 800, marginBottom: 8, color: '#f8fafc' }}>
                Drag & Drop Handwritten Prescription Here
              </h3>
              <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginBottom: 22 }}>
                Supports JPG, PNG, WEBP, or phone camera snapshots. Auto-deskewed and enhanced.
              </p>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14 }}>
                <button
                  id="btn-select-file"
                  className="btn btn-primary"
                  style={{ padding: '12px 26px', fontSize: '0.92rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  <FileText size={18} /> Choose Image File
                </button>
                <button
                  id="btn-camera-capture"
                  className="btn btn-secondary"
                  style={{ padding: '12px 22px', fontSize: '0.92rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  <Camera size={18} /> Camera Snap
                </button>
              </div>

              {/* Multi-Stage Loading Indicator */}
              {loading && (
                <div
                  style={{
                    marginTop: 30,
                    padding: '16px 26px',
                    borderRadius: 14,
                    background: 'rgba(6, 182, 212, 0.12)',
                    border: '1px solid rgba(6, 182, 212, 0.35)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 14,
                    boxShadow: '0 0 25px rgba(6, 182, 212, 0.25)',
                  }}
                >
                  <RefreshCw size={22} className="pulse-dot" color="#06b6d4" />
                  <span style={{ fontSize: '0.94rem', color: '#38bdf8', fontWeight: 700 }}>
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

            {/* THREE SECTION CARDS (Modeled like Vision / Mission / Doctor Profile from reference image) */}
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <div style={{ fontSize: '0.74rem', fontWeight: 800, color: '#06b6d4', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                CLINICAL EXCELLENCE & STANDARDS
              </div>
              <h3 style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f8fafc', marginTop: 4 }}>
                Hospital Pharmacopeia Ecosystem
              </h3>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24, marginBottom: 40 }}>
              {/* Card 1: Our Clinical Vision */}
              <div
                className="glass-panel"
                style={{
                  padding: '28px',
                  borderRadius: 20,
                  background: 'rgba(16, 185, 129, 0.05)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                }}
              >
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    background: 'rgba(16, 185, 129, 0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#10b981',
                    marginBottom: 16,
                  }}
                >
                  <Compass size={24} />
                </div>
                <h4 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#ffffff', marginBottom: 10 }}>
                  Our Clinical Vision
                </h4>
                <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                  Eliminate preventable medication dispensing errors caused by unreadable handwriting in ambulatory clinics and hospital outpatient pharmacies across India.
                </p>
              </div>

              {/* Card 2: Our Safety Mission */}
              <div
                className="glass-panel"
                style={{
                  padding: '28px',
                  borderRadius: 20,
                  background: 'rgba(6, 182, 212, 0.05)',
                  border: '1px solid rgba(6, 182, 212, 0.25)',
                }}
              >
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    background: 'rgba(6, 182, 212, 0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#06b6d4',
                    marginBottom: 16,
                  }}
                >
                  <Target size={24} />
                </div>
                <h4 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#ffffff', marginBottom: 10 }}>
                  Our Safety Mission
                </h4>
                <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                  Embed automated Look-Alike Sound-Alike (LASA) safety checks and NLEM dose/frequency validation directly into the pharmacist workflow before any pill is dispensed.
                </p>
              </div>

              {/* Card 3: Doctor & Pharmacist Profile */}
              <div
                className="glass-panel"
                style={{
                  padding: '28px',
                  borderRadius: 20,
                  background: 'rgba(139, 92, 246, 0.05)',
                  border: '1px solid rgba(139, 92, 246, 0.25)',
                }}
              >
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    background: 'rgba(139, 92, 246, 0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#a78bfa',
                    marginBottom: 16,
                  }}
                >
                  <Award size={24} />
                </div>
                <h4 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#ffffff', marginBottom: 10 }}>
                  Clinical Pharmacist Team
                </h4>
                <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                  Overseen by Dr. Alex Reed (Pharm.D, BCPS) and hospital pharmacists. Every override is recorded with an immutable audit hash for full regulatory compliance.
                </p>
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
            {/* Live 3D Doctor Clinical Supervisor HUD */}
            <InteractiveDoctor3D
              activePrescription={activePrescription}
              loading={loading}
              processingStage={processingStage}
              hoveredLineId={hoveredLineId}
              compact={true}
            />

            {/* Top Workspace HUD Bar */}
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
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    background: 'rgba(6, 182, 212, 0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#06b6d4',
                  }}
                >
                  <FileText size={24} />
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <h3 style={{ fontSize: '1.15rem', fontWeight: 800 }}>
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

              {/* Progress Summary and Batch Sign-Off */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8 }}>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-sub)', fontWeight: 600 }}>PROGRESS:</span>
                  <div style={{ width: 120, height: 8, background: '#1e293b', borderRadius: 4, overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${totalLines ? (confirmedLinesCount / totalLines) * 100 : 0}%`,
                        height: '100%',
                        background: 'linear-gradient(90deg, #06b6d4 0%, #10b981 100%)',
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', fontWeight: 700, color: '#38bdf8' }}>
                    {confirmedLinesCount}/{totalLines}
                  </span>
                </div>

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
                  style={{ padding: '10px 22px' }}
                >
                  {unreviewedRedCount > 0 ? <Lock size={16} /> : <Unlock size={16} />}
                  <span>Sign-Off & Dispense Rx</span>
                </button>
              </div>
            </div>

            {/* Split View: Interactive Image Stage + Line Verification Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: '420px 1fr', gap: 26, alignItems: 'start' }}>
              {/* Left Column: Interactive Prescription Image Viewer */}
              <div style={{ position: 'sticky', top: 90 }}>
                <div className="glass-panel" style={{ padding: '20px', marginBottom: 16 }}>
                  {/* Canvas Header & Interactive Tools */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase' }}>
                      SOURCE PRESCRIPTION IMAGE
                    </span>

                    {/* Interactive Zoom & Rotate Tools */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                        onClick={() => setZoomLevel((z) => Math.min(2, +(z + 0.25).toFixed(2)))}
                        title="Zoom In"
                      >
                        <ZoomIn size={14} />
                      </button>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                        onClick={() => setZoomLevel((z) => Math.max(0.75, +(z - 0.25).toFixed(2)))}
                        title="Zoom Out"
                      >
                        <ZoomOut size={14} />
                      </button>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                        onClick={() => setImageRotation((r) => (r + 90) % 360)}
                        title="Rotate 90° Clockwise"
                      >
                        <RotateCw size={14} />
                      </button>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                        onClick={() => {
                          setZoomLevel(1);
                          setImageRotation(0);
                          setImageFilter('normal');
                        }}
                        title="Reset View"
                      >
                        100%
                      </button>
                    </div>
                  </div>

                  {/* Filter Pills (Normal / High Contrast / Invert) */}
                  <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                    <button
                      className={`filter-tab ${imageFilter === 'normal' ? 'active' : ''}`}
                      style={{ padding: '4px 10px', fontSize: '0.72rem' }}
                      onClick={() => setImageFilter('normal')}
                    >
                      Original
                    </button>
                    <button
                      className={`filter-tab ${imageFilter === 'contrast' ? 'active' : ''}`}
                      style={{ padding: '4px 10px', fontSize: '0.72rem' }}
                      onClick={() => setImageFilter('contrast')}
                    >
                      Enhance Ink
                    </button>
                    <button
                      className={`filter-tab ${imageFilter === 'invert' ? 'active' : ''}`}
                      style={{ padding: '4px 10px', fontSize: '0.72rem' }}
                      onClick={() => setImageFilter('invert')}
                    >
                      Invert (Darkroom)
                    </button>
                  </div>

                  {/* Prescription Image Box with Line Hover Highlights */}
                  <div
                    style={{
                      borderRadius: 12,
                      overflow: 'hidden',
                      background: '#040711',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      height: 440,
                      position: 'relative',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <img
                      src={activePrescription.image_url}
                      alt="Prescription Scan"
                      style={{
                        maxWidth: '100%',
                        maxHeight: '100%',
                        objectFit: 'contain',
                        ...getImageFilterStyle(),
                      }}
                      onError={(e) => {
                        e.target.style.display = 'none';
                      }}
                    />

                    {/* Interactive Line Highlights on Canvas */}
                    {activePrescription.lines.map((line) => {
                      const isHovered = hoveredLineId === line.line_id;
                      if (!isHovered) return null;
                      return (
                        <div
                          key={line.line_id}
                          style={{
                            position: 'absolute',
                            left: '8%',
                            right: '8%',
                            top: `${20 + (line.line_id - 1) * 22}%`,
                            height: '18%',
                            border: '2px solid #06b6d4',
                            background: 'rgba(6, 182, 212, 0.2)',
                            boxShadow: '0 0 20px #06b6d4',
                            borderRadius: 6,
                            pointerEvents: 'none',
                            transition: 'all 0.2s ease',
                          }}
                        >
                          <span
                            style={{
                              position: 'absolute',
                              top: -12,
                              left: 6,
                              background: '#06b6d4',
                              color: '#080d1a',
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.68rem',
                              fontWeight: 800,
                              padding: '1px 6px',
                              borderRadius: 3,
                            }}
                          >
                            LINE #{line.line_id}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Optical Gating HUD Meter Cards */}
                  <div style={{ marginTop: 18 }}>
                    <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-sub)', textTransform: 'uppercase', marginBottom: 10 }}>
                      OPTICAL QUALITY AUDIT
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                      <div style={{ background: 'rgba(255, 255, 255, 0.03)', borderRadius: 10, padding: '10px 12px', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>Focus (Laplacian)</div>
                        <div style={{ fontSize: '0.98rem', fontWeight: 800, color: '#34d399', marginTop: 2 }}>
                          {activePrescription.quality_check.blur_score}
                        </div>
                        <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>min: 70.0</div>
                      </div>
                      <div style={{ background: 'rgba(255, 255, 255, 0.03)', borderRadius: 10, padding: '10px 12px', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>Illumination</div>
                        <div style={{ fontSize: '0.98rem', fontWeight: 800, color: '#38bdf8', marginTop: 2 }}>
                          {activePrescription.quality_check.mean_brightness}
                        </div>
                        <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>min: 50.0</div>
                      </div>
                      <div style={{ background: 'rgba(255, 255, 255, 0.03)', borderRadius: 10, padding: '10px 12px', textAlign: 'center' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>Specular Glare</div>
                        <div style={{ fontSize: '0.98rem', fontWeight: 800, color: '#a78bfa', marginTop: 2 }}>
                          {(activePrescription.quality_check.glare_share * 100).toFixed(1)}%
                        </div>
                        <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>max: 10%</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column: Line-by-Line Medication Verification Stream */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                {/* Interactive Filter Tabs */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: '0.76rem', color: 'var(--text-sub)', fontWeight: 700, marginRight: 6 }}>
                    FILTER:
                  </span>
                  <button
                    className={`filter-tab ${activeFilterTab === 'all' ? 'active' : ''}`}
                    onClick={() => setActiveFilterTab('all')}
                  >
                    All Lines ({totalLines})
                  </button>
                  {unreviewedRedCount > 0 && (
                    <button
                      className={`filter-tab ${activeFilterTab === 'red' ? 'active' : ''}`}
                      style={{ color: '#f87171' }}
                      onClick={() => setActiveFilterTab('red')}
                    >
                      <AlertTriangle size={13} style={{ display: 'inline', marginRight: 4 }} />
                      Attention Needed ({unreviewedRedCount})
                    </button>
                  )}
                  {lookalikeCount > 0 && (
                    <button
                      className={`filter-tab ${activeFilterTab === 'lookalike' ? 'active' : ''}`}
                      style={{ color: '#fbbf24' }}
                      onClick={() => setActiveFilterTab('lookalike')}
                    >
                      <AlertOctagon size={13} style={{ display: 'inline', marginRight: 4 }} />
                      Look-Alike Risk ({lookalikeCount})
                    </button>
                  )}
                  <button
                    className={`filter-tab ${activeFilterTab === 'confirmed' ? 'active' : ''}`}
                    style={{ color: '#34d399' }}
                    onClick={() => setActiveFilterTab('confirmed')}
                  >
                    <CheckCircle2 size={13} style={{ display: 'inline', marginRight: 4 }} />
                    Approved ({confirmedLinesCount})
                  </button>
                </div>

                {/* Line Cards List */}
                {filteredLines.map((line, idx) => {
                  const isRed = line.confidence.level === 'red';
                  const isYellow = line.confidence.level === 'yellow';
                  const isGreen = line.confidence.level === 'green';
                  const isConfirmed = line.status === 'confirmed' || line.status === 'corrected';
                  const isEditing = editingLineId === line.line_id;
                  const isHovered = hoveredLineId === line.line_id;

                  // Circular SVG score calculations
                  const scorePercent = Math.round((line.confidence.score || 0) * 100);
                  const circleCircumference = 2 * Math.PI * 18;
                  const strokeOffset = circleCircumference - (scorePercent / 100) * circleCircumference;
                  const strokeColor = isGreen ? '#10b981' : isYellow ? '#f59e0b' : '#ef4444';

                  return (
                    <div
                      key={line.line_id}
                      id={`line-card-${line.line_id}`}
                      className="glass-panel animate-card-entry"
                      style={{
                        padding: '22px 24px',
                        borderLeft: `5px solid ${
                          isConfirmed ? '#10b981' : isRed ? '#ef4444' : isYellow ? '#f59e0b' : '#10b981'
                        }`,
                        background: isHovered
                          ? 'rgba(6, 182, 212, 0.08)'
                          : isConfirmed
                          ? 'rgba(16, 185, 129, 0.04)'
                          : 'var(--bg-card)',
                        animationDelay: `${idx * 0.08}s`,
                        transition: 'all 0.2s ease',
                      }}
                      onMouseEnter={() => setHoveredLineId(line.line_id)}
                      onMouseLeave={() => setHoveredLineId(null)}
                    >
                      {/* Line Card Header */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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

                          {/* Animated Radial SVG Confidence Meter */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <svg width="44" height="44" viewBox="0 0 44 44">
                              <circle
                                cx="22"
                                cy="22"
                                r="18"
                                fill="none"
                                stroke="#1e293b"
                                strokeWidth="3.5"
                              />
                              <circle
                                cx="22"
                                cy="22"
                                r="18"
                                fill="none"
                                stroke={strokeColor}
                                strokeWidth="3.5"
                                strokeDasharray={circleCircumference}
                                strokeDashoffset={strokeOffset}
                                strokeLinecap="round"
                                transform="rotate(-90 22 22)"
                                style={{ transition: 'stroke-dashoffset 0.8s ease' }}
                              />
                              <text
                                x="22"
                                y="26"
                                textAnchor="middle"
                                fill={strokeColor}
                                fontSize="11"
                                fontWeight="800"
                                fontFamily="var(--font-mono)"
                              >
                                {scorePercent}%
                              </text>
                            </svg>

                            <span
                              className={`glass-pill badge-${line.confidence.level}`}
                              style={{ fontWeight: 700, fontSize: '0.78rem' }}
                            >
                              <span className="pulse-dot" style={{ background: strokeColor }} />
                              {line.confidence.level.toUpperCase()} CONFIDENCE
                            </span>
                          </div>

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
                        {/* Left: Original Handwritten Crop Preview with Zoom Trigger */}
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
                              position: 'relative',
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
                            <div
                              style={{
                                position: 'absolute',
                                right: 8,
                                bottom: 8,
                                background: 'rgba(0, 0, 0, 0.6)',
                                borderRadius: 4,
                                padding: '2px 6px',
                                color: '#ffffff',
                                fontSize: '0.65rem',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                              }}
                            >
                              <Maximize2 size={11} /> Zoom
                            </div>
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
                              className="lasa-beacon"
                              style={{
                                padding: '14px 18px',
                                borderRadius: 12,
                                background: 'rgba(239, 68, 68, 0.15)',
                                border: '1px solid rgba(239, 68, 68, 0.5)',
                                marginBottom: 16,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: 16,
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <AlertOctagon size={24} color="#f87171" />
                                <div>
                                  <div style={{ fontSize: '0.86rem', color: '#fca5a5', fontWeight: 700 }}>
                                    CONFUSABLE LOOK-ALIKE HAZARD (LASA RISK)
                                  </div>
                                  <div style={{ fontSize: '0.82rem', color: '#fecaca', marginTop: 2 }}>
                                    {line.lookalike.warning_message}
                                  </div>
                                </div>
                              </div>

                              {line.lookalike.paired_drug && (
                                <button
                                  className="btn btn-secondary fast-fix-pill"
                                  style={{
                                    padding: '7px 16px',
                                    fontSize: '0.8rem',
                                    background: 'rgba(239, 68, 68, 0.28)',
                                    borderColor: 'rgba(239, 68, 68, 0.65)',
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
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 14 }}>
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

                          {/* One-Click Fast Fix Interactive Pills */}
                          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                            <span style={{ fontSize: '0.74rem', color: 'var(--text-sub)', fontWeight: 700, textTransform: 'uppercase' }}>
                              One-Click Fast Fix:
                            </span>
                            {line.top_candidates?.map((cand, cIdx) => (
                              <button
                                key={cIdx}
                                id={`one-click-pill-${line.line_id}-${cand.brand_name}`}
                                className="btn btn-secondary fast-fix-pill"
                                style={{
                                  padding: '5px 14px',
                                  fontSize: '0.82rem',
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
                            padding: '22px',
                            borderRadius: 14,
                            background: 'rgba(15, 23, 42, 0.95)',
                            border: '1px solid rgba(6, 182, 212, 0.4)',
                            boxShadow: '0 8px 30px rgba(0, 0, 0, 0.6)',
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

      {/* Slide-out Interactive Audit Log Drawer */}
      {showAuditDrawer && (
        <div className="modal-overlay" onClick={() => setShowAuditDrawer(false)}>
          <div
            className="glass-panel"
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              width: 440,
              maxWidth: '90vw',
              borderRadius: '20px 0 0 20px',
              padding: '24px',
              background: '#090e1c',
              overflowY: 'auto',
              borderLeft: '1px solid rgba(6, 182, 212, 0.3)',
              boxShadow: '-10px 0 40px rgba(0,0,0,0.8)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <History size={20} color="#06b6d4" />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 800 }}>Clinical Audit Trail</h3>
              </div>
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 8px', borderRadius: '50%' }}
                onClick={() => setShowAuditDrawer(false)}
              >
                ✕
              </button>
            </div>

            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 20 }}>
              Immutable event log recorded to SQLite audit table for compliance and clinical traceability.
            </p>

            {auditLog.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-sub)' }}>
                No events recorded in current session yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {auditLog.map((item) => (
                  <div
                    key={item.id}
                    style={{
                      padding: '12px 14px',
                      borderRadius: 10,
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#38bdf8' }}>
                        {item.action}
                      </span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--text-sub)' }}>
                        {item.timestamp}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.82rem', color: 'var(--text-main)', lineHeight: 1.4 }}>
                      {item.detail}
                    </p>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)', marginTop: 4 }}>
                      Signer: {item.user}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Verified Electronic Dispense Celebration Modal */}
      {showDispenseModal && (
        <div className="modal-overlay" onClick={() => setShowDispenseModal(false)}>
          <div
            className="glass-panel"
            style={{ maxWidth: 640, width: '100%', padding: '36px', background: '#0b1120' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ textAlign: 'center', marginBottom: 24 }}>
              <div
                style={{
                  width: 68,
                  height: 68,
                  borderRadius: '50%',
                  background: 'rgba(16, 185, 129, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 16px',
                  color: '#10b981',
                  boxShadow: '0 0 30px rgba(16, 185, 129, 0.35)',
                }}
              >
                <CheckCircle2 size={40} />
              </div>
              <h3 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#f8fafc' }}>
                Prescription Verified & Approved for Dispense
              </h3>
              <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginTop: 4 }}>
                All medication lines have passed clinical safety checks and look-alike verification.
              </p>
            </div>

            <div
              style={{
                background: 'rgba(255, 255, 255, 0.03)',
                borderRadius: 14,
                padding: '18px 22px',
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
                <span style={{ color: '#f8fafc', fontWeight: 600 }}>LIC# IN-PHARM-88219 (Dr. Alex Reed, Pharm.D)</span>
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
            style={{ padding: 20, background: '#ffffff', borderRadius: 16, maxWidth: 880 }}
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
          padding: '18px 28px',
          textAlign: 'center',
          fontSize: '0.78rem',
          color: 'var(--text-sub)',
          background: 'rgba(8, 13, 26, 0.7)',
          zIndex: 10,
        }}
      >
        MedMatch Rx™ · Hospital Clinical Pharmacist Ingestion Workstation · NLEM Pharmacopeia Verified · Real-Time LASA Prevention
      </footer>
    </div>
  );
}
