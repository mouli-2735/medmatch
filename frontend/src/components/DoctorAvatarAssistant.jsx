import React, { useState, useEffect } from 'react';
import {
  MessageSquare,
  Sparkles,
  ShieldAlert,
  HelpCircle,
  X,
  Stethoscope,
  ChevronRight,
  Volume2,
  VolumeX,
  AlertOctagon
} from 'lucide-react';

export default function DoctorAvatarAssistant({
  activePrescription,
  loading,
  processingStage,
  hoveredLineId
}) {
  const [isOpen, setIsOpen] = useState(true);
  const [activeSpeech, setActiveSpeech] = useState(
    "Hello! I'm Dr. Alex, your AI Clinical Pharmacist. Drag any handwritten prescription onto the desk to begin analysis!"
  );
  const [showConsultModal, setShowConsultModal] = useState(false);
  const [consultQuestion, setConsultQuestion] = useState(null);

  // Update Doctor Speech based on application state
  useEffect(() => {
    if (loading) {
      setActiveSpeech(`"Currently processing: ${processingStage} Applying contrast filters to handwriting strokes."`);
    } else if (activePrescription) {
      if (!activePrescription.quality_check.passed) {
        setActiveSpeech(
          `"Warning: The prescription photo failed optical gating (${activePrescription.quality_check.message}). Please snap a clearer photo with even lighting."`
        );
      } else {
        const redLines = activePrescription.lines.filter(
          (l) => l.confidence.level === 'red' && l.status === 'pending'
        );
        const lookalikes = activePrescription.lines.filter((l) => l.lookalike?.is_flagged);

        if (hoveredLineId) {
          const targetLine = activePrescription.lines.find((l) => l.line_id === hoveredLineId);
          if (targetLine) {
            if (targetLine.lookalike?.is_flagged) {
              setActiveSpeech(
                `"High Alert on Line #${targetLine.line_id}: ${targetLine.selected_candidate?.brand_name} carries high confusion risk with ${targetLine.lookalike.paired_drug}. Check patient symptoms!"`
              );
            } else if (targetLine.confidence.level === 'red') {
              setActiveSpeech(
                `"Line #${targetLine.line_id} is marked RED because the cursive characters are ambiguous. Pharmacist verification is mandatory."`
              );
            } else {
              setActiveSpeech(
                `"Line #${targetLine.line_id}: ${targetLine.selected_candidate?.brand_name} (${targetLine.selected_candidate?.generic_name}) looks clean. Dosage ${targetLine.final_dose || targetLine.dose_raw} matches standard clinical dosing."`
              );
            }
            return;
          }
        }

        if (lookalikes.length > 0) {
          setActiveSpeech(
            `"Safety Warning: I detected a confusable Look-Alike pair (${lookalikes[0].lookalike.warning_message}). Use the 1-Click Swap button if an alternate was intended."`
          );
        } else if (redLines.length > 0) {
          setActiveSpeech(
            `"Review Needed: There are ${redLines.length} red-flagged lines that require your clinical sign-off before full prescription approval is unlocked."`
          );
        } else {
          setActiveSpeech(
            `"All ${activePrescription.lines.length} lines have been clinically verified against NLEM 2022 standards. The prescription is ready for digital dispense!"`
          );
        }
      }
    } else {
      setActiveSpeech(
        "Welcome to MedMatch Rx! I'm Dr. Alex. Drop any handwritten prescription onto the desk to begin analysis."
      );
    }
  }, [loading, processingStage, activePrescription, hoveredLineId]);

  const clinicalQAs = [
    {
      q: 'Celebrex vs. Celexa: What is the clinical hazard?',
      a: 'Celebrex (Celecoxib) is an NSAID for arthritis and pain, whereas Celexa (Citalopram) is an SSRI antidepressant. Confusing these two drugs leads to severe adverse events, including untreated pain, serotonin syndrome, or gastrointestinal bleeding. Our LASA shield automatically intercepts this pair.'
    },
    {
      q: 'How does NLEM 2022 frequency standardization work?',
      a: 'We map Indian Latin shorthand (OD, BD, TDS, QID) and regional numeric patterns (1-0-1, 1-1-1, 0-1-0) into ISO standardized timing instructions (e.g., 1-0-1 converts to "Morning and Night - Twice Daily after food").'
    },
    {
      q: 'When does the Safety Lock prevent dispensing?',
      a: 'If any line exhibits low confidence (<55%) or illegible cursive strokes, the system blocks the "Sign-Off & Dispense Rx" button until the pharmacist enters an explicit override and clinical rationale in the audit log.'
    }
  ];

  return (
    <>
      {/* Floating 3D Doctor Avatar Dock */}
      <div
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 90,
          display: 'flex',
          alignItems: 'flex-end',
          gap: 14,
        }}
      >
        {/* Animated Speech Bubble */}
        {isOpen && (
          <div
            className="glass-panel"
            style={{
              maxWidth: 340,
              padding: '16px 18px',
              borderRadius: '16px 16px 4px 16px',
              background: 'rgba(11, 18, 36, 0.94)',
              border: '1px solid rgba(6, 182, 212, 0.35)',
              boxShadow: '0 12px 35px rgba(0, 0, 0, 0.65), 0 0 25px rgba(6, 182, 212, 0.2)',
              position: 'relative',
              animation: 'fadeInModal 0.25s ease',
            }}
          >
            {/* Header info */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="pulse-dot" style={{ background: '#10b981', width: 7, height: 7 }} />
                <span style={{ fontSize: '0.74rem', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.04em' }}>
                  DR. ALEX (AI CLINICIAN)
                </span>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-sub)', cursor: 'pointer' }}
              >
                <X size={14} />
              </button>
            </div>

            {/* Speech dialogue */}
            <p style={{ fontSize: '0.82rem', color: '#f8fafc', lineHeight: 1.45, marginBottom: 12 }}>
              {activeSpeech}
            </p>

            {/* Quick Consultation Trigger */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 10px', fontSize: '0.72rem', borderRadius: 9999, borderColor: 'rgba(6, 182, 212, 0.4)' }}
                onClick={() => setShowConsultModal(true)}
              >
                <Sparkles size={12} color="#06b6d4" /> Ask Dr. Alex
              </button>
            </div>
          </div>
        )}

        {/* 3D Doctor Avatar Button / Card */}
        <div
          onClick={() => setIsOpen(!isOpen)}
          style={{
            width: 72,
            height: 72,
            borderRadius: 22,
            overflow: 'hidden',
            border: '2px solid #06b6d4',
            boxShadow: '0 8px 30px rgba(6, 182, 212, 0.4), 0 0 15px #06b6d4',
            cursor: 'pointer',
            background: '#0a0f1d',
            transition: 'transform 0.2s ease, box-shadow 0.2s ease',
            position: 'relative',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.08)')}
          onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
          title="Click to toggle Doctor Assistant dialogue"
        >
          <img
            src="/assets/doctor_3d_avatar.jpg"
            alt="Dr. Alex 3D Avatar"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
          <div
            style={{
              position: 'absolute',
              bottom: 2,
              right: 2,
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: '#10b981',
              border: '2px solid #080d1a',
            }}
          />
        </div>
      </div>

      {/* Doctor Consultation Modal */}
      {showConsultModal && (
        <div className="modal-overlay" onClick={() => setShowConsultModal(false)}>
          <div
            className="glass-panel"
            style={{ maxWidth: 640, width: '100%', padding: '28px', background: '#0c1326' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 14,
                    overflow: 'hidden',
                    border: '1.5px solid #06b6d4',
                  }}
                >
                  <img src="/assets/doctor_3d_avatar.jpg" alt="Doctor" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
                <div>
                  <h3 style={{ fontSize: '1.2rem', fontWeight: 800 }}>Clinical Pharmacist Consultation</h3>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>
                    Ask Dr. Alex about medication hazards, dosing guidelines & safety protocols
                  </p>
                </div>
              </div>
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 8px', borderRadius: '50%' }}
                onClick={() => setShowConsultModal(false)}
              >
                ✕
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
              {clinicalQAs.map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: '14px 16px',
                    borderRadius: 12,
                    background: consultQuestion === idx ? 'rgba(6, 182, 212, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                    border: consultQuestion === idx ? '1px solid #06b6d4' : '1px solid rgba(255, 255, 255, 0.08)',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                  onClick={() => setConsultQuestion(consultQuestion === idx ? null : idx)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#f8fafc' }}>
                      {item.q}
                    </span>
                    <ChevronRight
                      size={16}
                      color="#06b6d4"
                      style={{
                        transform: consultQuestion === idx ? 'rotate(90deg)' : 'none',
                        transition: 'transform 0.2s ease',
                      }}
                    />
                  </div>
                  {consultQuestion === idx && (
                    <p style={{ fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.5, marginTop: 10, borderTop: '1px solid rgba(255, 255, 255, 0.06)', paddingTop: 10 }}>
                      {item.a}
                    </p>
                  )}
                </div>
              ))}
            </div>

            <div style={{ textAlign: 'right' }}>
              <button className="btn btn-primary" onClick={() => setShowConsultModal(false)}>
                Understood, Return to Review
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
