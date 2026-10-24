import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldCheck,
  Stethoscope,
  Lock,
  Mail,
  User,
  ArrowRight,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Eye,
  EyeOff
} from 'lucide-react';

export default function AuthScreens({ onAuthSuccess, initialScreen = 'login', apiBase = '' }) {
  const [screen, setScreen] = useState(initialScreen); // 'login' | 'register' | 'verify_otp' | 'forgot_password' | 'reset_password'
  const [otpPurpose, setOtpPurpose] = useState('verify'); // 'verify' | 'login' | 'reset'

  // Form Fields
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState('pharmacist');
  const [showPassword, setShowPassword] = useState(false);

  // 6-digit OTP boxes state
  const [otpDigits, setOtpDigits] = useState(['', '', '', '', '', '']);
  const otpInputRefs = useRef([]);

  // Cooldown countdown
  const [resendCooldown, setResendCooldown] = useState(0);

  // Status Alerts
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [loading, setLoading] = useState(false);

  // Reset alert messages when switching screens
  useEffect(() => {
    setErrorMsg(null);
    setSuccessMsg(null);
  }, [screen]);

  // Resend cooldown timer ticker
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  // Handle OTP digit box input
  const handleDigitChange = (index, value) => {
    const val = value.replace(/\D/g, '').slice(-1);
    const updated = [...otpDigits];
    updated[index] = val;
    setOtpDigits(updated);

    if (val && index < 5) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !otpDigits[index] && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (!pasted) return;
    const updated = [...otpDigits];
    for (let i = 0; i < 6; i++) {
      updated[i] = pasted[i] || '';
    }
    setOtpDigits(updated);
    const focusIdx = Math.min(pasted.length, 5);
    otpInputRefs.current[focusIdx]?.focus();
  };

  const getEnteredOtp = () => otpDigits.join('');

  // 1. Submit Registration
  const handleRegister = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (password.length < 8) {
      setErrorMsg('Password must be at least 8 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          password,
          confirm_password: confirmPassword,
          role,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Registration failed.');
      }

      setOtpPurpose('verify');
      setOtpDigits(['', '', '', '', '', '']);
      setResendCooldown(60);
      setSuccessMsg(data.message || 'Verification code sent to your email.');
      setScreen('verify_otp');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 2. Submit OTP (Account verification or Login 2FA)
  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    const code = getEnteredOtp();
    if (code.length !== 6) {
      setErrorMsg('Please enter all 6 digits of your verification code.');
      return;
    }

    setLoading(true);
    try {
      const endpoint =
        otpPurpose === 'login'
          ? `${apiBase}/api/auth/login-verify-otp`
          : `${apiBase}/api/auth/verify-otp`;

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          email: email.trim(),
          otp: code,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Invalid verification code.');
      }

      setSuccessMsg(data.message || 'Verification successful!');
      if (onAuthSuccess && data.user) {
        onAuthSuccess(data.user);
      }
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 3. Resend OTP
  const handleResendOtp = async () => {
    if (resendCooldown > 0 || loading) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    setLoading(true);

    try {
      const res = await fetch(`${apiBase}/api/auth/resend-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          email: email.trim(),
          purpose: otpPurpose,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to resend code.');
      }

      setResendCooldown(60);
      setSuccessMsg(data.message || 'New verification code has been dispatched to your email.');
      setOtpDigits(['', '', '', '', '', '']);
      otpInputRefs.current[0]?.focus();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 4. Submit Login
  const handleLogin = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);
    setLoading(true);

    try {
      const res = await fetch(`${apiBase}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          email: email.trim(),
          password,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        if (res.status === 403 && data.detail?.toLowerCase().includes('not verified')) {
          setOtpPurpose('verify');
          setScreen('verify_otp');
          setResendCooldown(60);
          setErrorMsg('Your account is not verified. A verification code is required.');
          return;
        }
        throw new Error(data.detail || 'Invalid email or password.');
      }

      if (data.otp_required) {
        setOtpPurpose('login');
        setOtpDigits(['', '', '', '', '', '']);
        setResendCooldown(60);
        setSuccessMsg(data.message || 'Two-factor authentication code sent to your email.');
        setScreen('verify_otp');
      } else {
        setSuccessMsg('Login successful!');
        if (onAuthSuccess && data.user) {
          onAuthSuccess(data.user);
        }
      }
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 5. Submit Forgot Password
  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);
    setLoading(true);

    try {
      const res = await fetch(`${apiBase}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          email: email.trim(),
        }),
      });

      const data = await res.json();
      setOtpPurpose('reset');
      setOtpDigits(['', '', '', '', '', '']);
      setResendCooldown(60);
      setSuccessMsg(data.message || 'Password reset code has been sent if this email is registered.');
      setScreen('reset_password');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 6. Submit Reset Password
  const handleResetPassword = async (e) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    const code = getEnteredOtp();
    if (code.length !== 6) {
      setErrorMsg('Please enter the 6-digit code sent to your email.');
      return;
    }
    if (password.length < 8) {
      setErrorMsg('New password must be at least 8 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          email: email.trim(),
          otp: code,
          new_password: password,
          confirm_password: confirmPassword,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Password reset failed.');
      }

      setSuccessMsg(data.message || 'Password updated successfully! Please log in.');
      setPassword('');
      setConfirmPassword('');
      setScreen('login');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px 16px',
        position: 'relative',
        zIndex: 50,
      }}
    >
      <div
        className="glass-card"
        style={{
          width: '100%',
          maxWidth: '480px',
          background: 'rgba(8, 22, 45, 0.88)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(56, 189, 248, 0.28)',
          borderRadius: '24px',
          padding: '36px 32px',
          boxShadow: '0 24px 60px -12px rgba(2, 44, 76, 0.75), 0 0 30px rgba(56, 189, 248, 0.2)',
          color: 'var(--text-main)',
        }}
      >
        {/* Brand Header */}
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '16px',
              background: 'linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 24px rgba(56, 189, 248, 0.35)',
              marginBottom: '14px',
            }}
          >
            <ShieldCheck size={32} color="#ffffff" />
          </div>
          <h1
            style={{
              fontSize: '1.65rem',
              fontWeight: 800,
              letterSpacing: '-0.02em',
              background: 'linear-gradient(135deg, #ffffff 0%, #bae6fd 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              marginBottom: '6px',
            }}
          >
            MedMatch Rx
          </h1>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-sub)' }}>
            Clinical Pharmacist Authentication & Security Portal
          </p>
        </div>

        {/* Status Alerts */}
        {errorMsg && (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              padding: '12px 14px',
              borderRadius: '12px',
              background: 'rgba(239, 68, 68, 0.16)',
              border: '1px solid rgba(239, 68, 68, 0.45)',
              color: '#fca5a5',
              fontSize: '0.84rem',
              marginBottom: '20px',
              lineHeight: 1.45,
            }}
          >
            <AlertCircle size={18} color="#ef4444" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>{errorMsg}</div>
          </div>
        )}

        {successMsg && (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              padding: '12px 14px',
              borderRadius: '12px',
              background: 'rgba(16, 185, 129, 0.16)',
              border: '1px solid rgba(16, 185, 129, 0.45)',
              color: '#86efac',
              fontSize: '0.84rem',
              marginBottom: '20px',
              lineHeight: 1.45,
            }}
          >
            <CheckCircle2 size={18} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>{successMsg}</div>
          </div>
        )}

        {/* ==================================================== */}
        {/* SCREEN 1: LOGIN                                      */}
        {/* ==================================================== */}
        {screen === 'login' && (
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Email Address
              </label>
              <div style={{ position: 'relative' }}>
                <Mail
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="pharmacist@hospital.org"
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd' }}>
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => setScreen('forgot_password')}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#38bdf8',
                    fontSize: '0.78rem',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  Forgot password?
                </button>
              </div>
              <div style={{ position: 'relative' }}>
                <Lock
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    padding: '10px 38px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                  }}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '12px',
                fontSize: '0.92rem',
                fontWeight: 700,
                marginTop: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? (
                <>
                  <RefreshCw size={16} className="spin" />
                  <span>Signing In...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>

            <div style={{ textAlign: 'center', marginTop: '14px', fontSize: '0.84rem', color: 'var(--text-sub)' }}>
              Don't have an account?{' '}
              <button
                type="button"
                onClick={() => setScreen('register')}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#38bdf8',
                  fontWeight: 700,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                Register Here
              </button>
            </div>
          </form>
        )}

        {/* ==================================================== */}
        {/* SCREEN 2: REGISTER                                   */}
        {/* ==================================================== */}
        {screen === 'register' && (
          <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Full Name
              </label>
              <div style={{ position: 'relative' }}>
                <User
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Dr. Alex Reed (Pharm.D)"
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Email Address
              </label>
              <div style={{ position: 'relative' }}>
                <Mail
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="pharmacist@hospital.org"
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Password (min 8 characters)
              </label>
              <div style={{ position: 'relative' }}>
                <Lock
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    padding: '10px 38px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                  }}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Confirm Password
              </label>
              <div style={{ position: 'relative' }}>
                <Lock
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Clinical Role
              </label>
              <div style={{ position: 'relative' }}>
                <Stethoscope
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.85)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                    cursor: 'pointer',
                  }}
                >
                  <option value="pharmacist">Clinical Pharmacist</option>
                  <option value="physician">Attending Physician</option>
                  <option value="nurse">Clinical Nurse Specialist</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '12px',
                fontSize: '0.92rem',
                fontWeight: 700,
                marginTop: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? (
                <>
                  <RefreshCw size={16} className="spin" />
                  <span>Submitting Registration...</span>
                </>
              ) : (
                <>
                  <span>Create Account & Send OTP</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>

            <div style={{ textAlign: 'center', marginTop: '10px', fontSize: '0.84rem', color: 'var(--text-sub)' }}>
              Already have an account?{' '}
              <button
                type="button"
                onClick={() => setScreen('login')}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#38bdf8',
                  fontWeight: 700,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                Sign In
              </button>
            </div>
          </form>
        )}

        {/* ==================================================== */}
        {/* SCREEN 3: VERIFY OTP (6 SEPARATE DIGIT BOXES)        */}
        {/* ==================================================== */}
        {screen === 'verify_otp' && (
          <form onSubmit={handleVerifyOtp} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  fontSize: '0.9rem',
                  color: 'var(--text-sub)',
                  marginBottom: '16px',
                  lineHeight: 1.5,
                }}
              >
                Enter the 6-digit code sent to{' '}
                <strong style={{ color: '#38bdf8' }}>{email}</strong>
              </div>

              {/* 6 Digit Input Boxes */}
              <div
                onPaste={handlePaste}
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  gap: '8px',
                  marginBottom: '10px',
                }}
              >
                {otpDigits.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => (otpInputRefs.current[idx] = el)}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleDigitChange(idx, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(idx, e)}
                    style={{
                      width: '46px',
                      height: '56px',
                      borderRadius: '12px',
                      background: 'rgba(15, 23, 42, 0.75)',
                      border: digit ? '2px solid #38bdf8' : '1px solid rgba(255, 255, 255, 0.22)',
                      boxShadow: digit ? '0 0 16px rgba(56, 189, 248, 0.35)' : 'none',
                      color: '#ffffff',
                      fontSize: '1.45rem',
                      fontWeight: 800,
                      textAlign: 'center',
                      outline: 'none',
                      fontFamily: 'var(--font-mono)',
                    }}
                  />
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || getEnteredOtp().length !== 6}
              className="btn btn-primary"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '12px',
                fontSize: '0.92rem',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: loading || getEnteredOtp().length !== 6 ? 'not-allowed' : 'pointer',
                opacity: loading || getEnteredOtp().length !== 6 ? 0.6 : 1,
              }}
            >
              {loading ? (
                <>
                  <RefreshCw size={16} className="spin" />
                  <span>Verifying Code...</span>
                </>
              ) : (
                <>
                  <KeyRound size={16} />
                  <span>Confirm & Activate</span>
                </>
              )}
            </button>

            {/* Resend Action with 60s Cooldown Countdown */}
            <div style={{ textAlign: 'center', marginTop: '4px' }}>
              <button
                type="button"
                disabled={resendCooldown > 0 || loading}
                onClick={handleResendOtp}
                style={{
                  background: 'none',
                  border: 'none',
                  color: resendCooldown > 0 ? 'var(--text-dim)' : '#38bdf8',
                  fontSize: '0.84rem',
                  fontWeight: 600,
                  cursor: resendCooldown > 0 ? 'not-allowed' : 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <RefreshCw size={14} className={loading ? 'spin' : ''} />
                <span>
                  {resendCooldown > 0
                    ? `Resend Code in ${resendCooldown}s`
                    : 'Resend Verification Code'}
                </span>
              </button>
            </div>

            <div style={{ textAlign: 'center', marginTop: '6px', fontSize: '0.8rem' }}>
              <button
                type="button"
                onClick={() => setScreen('login')}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-sub)',
                  cursor: 'pointer',
                }}
              >
                Back to Sign In
              </button>
            </div>
          </form>
        )}

        {/* ==================================================== */}
        {/* SCREEN 4: FORGOT PASSWORD                            */}
        {/* ==================================================== */}
        {screen === 'forgot_password' && (
          <form onSubmit={handleForgotPassword} style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <div style={{ fontSize: '0.86rem', color: 'var(--text-sub)', lineHeight: 1.45, textAlign: 'center' }}>
              Enter your registered clinical email. We will dispatch a 6-digit verification code to reset your password.
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Account Email
              </label>
              <div style={{ position: 'relative' }}>
                <Mail
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="pharmacist@hospital.org"
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '12px',
                fontSize: '0.92rem',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? (
                <>
                  <RefreshCw size={16} className="spin" />
                  <span>Dispatching Code...</span>
                </>
              ) : (
                <>
                  <span>Send Reset Code</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>

            <div style={{ textAlign: 'center', marginTop: '6px', fontSize: '0.84rem' }}>
              <button
                type="button"
                onClick={() => setScreen('login')}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#38bdf8',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Back to Sign In
              </button>
            </div>
          </form>
        )}

        {/* ==================================================== */}
        {/* SCREEN 5: RESET PASSWORD                             */}
        {/* ==================================================== */}
        {screen === 'reset_password' && (
          <form onSubmit={handleResetPassword} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ textAlign: 'center', marginBottom: '4px' }}>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-sub)' }}>
                Enter the 6-digit reset code sent to{' '}
                <strong style={{ color: '#38bdf8' }}>{email}</strong>
              </div>
            </div>

            {/* 6 Digit Input Boxes */}
            <div
              onPaste={handlePaste}
              style={{
                display: 'flex',
                justifyContent: 'center',
                gap: '8px',
                margin: '4px 0 8px 0',
              }}
            >
              {otpDigits.map((digit, idx) => (
                <input
                  key={idx}
                  ref={(el) => (otpInputRefs.current[idx] = el)}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleDigitChange(idx, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(idx, e)}
                  style={{
                    width: '46px',
                    height: '54px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.75)',
                    border: digit ? '2px solid #38bdf8' : '1px solid rgba(255, 255, 255, 0.22)',
                    boxShadow: digit ? '0 0 16px rgba(56, 189, 248, 0.35)' : 'none',
                    color: '#ffffff',
                    fontSize: '1.4rem',
                    fontWeight: 800,
                    textAlign: 'center',
                    outline: 'none',
                    fontFamily: 'var(--font-mono)',
                  }}
                />
              ))}
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                New Password (min 8 characters)
              </label>
              <div style={{ position: 'relative' }}>
                <Lock
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#bae6fd', marginBottom: '6px' }}>
                Confirm New Password
              </label>
              <div style={{ position: 'relative' }}>
                <Lock
                  size={16}
                  color="#94a3b8"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    padding: '10px 12px 10px 38px',
                    borderRadius: '12px',
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || getEnteredOtp().length !== 6}
              className="btn btn-primary"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '12px',
                fontSize: '0.92rem',
                fontWeight: 700,
                marginTop: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: loading || getEnteredOtp().length !== 6 ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? (
                <>
                  <RefreshCw size={16} className="spin" />
                  <span>Updating Password...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 size={16} />
                  <span>Set New Password & Sign In</span>
                </>
              )}
            </button>

            <div style={{ textAlign: 'center', marginTop: '6px', fontSize: '0.84rem' }}>
              <button
                type="button"
                onClick={() => setScreen('login')}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#38bdf8',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Back to Sign In
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
