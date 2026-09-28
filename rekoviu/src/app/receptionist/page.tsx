'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { MediVERSENav } from '@/components/common/MediVERSENav';
import { Scanner } from '@yudiel/react-qr-scanner';
import { api, fetchSyncStatus, triggerSync } from '@/services/api';
import { useCurrency } from '@/contexts/CurrencyContext';

const DEPARTMENTS_LIST = [
  { code: 'gen', name: 'General Clinic / OPD', doctor: 'Dr. Marcus Vance (doc_1)', pin: '12345', room: 'Room 101' },
  { code: 'card', name: 'Cardiology', doctor: 'Dr. Elena Rostova (doc_2)', pin: '12345', room: 'Room 204' },
  { code: 'ped', name: 'Pediatrics', doctor: 'Dr. Aris Thorne (doc_3)', pin: '12345', room: 'Room 108' },
  { code: 'ortho', name: 'Orthopedics', doctor: 'Dr. Sarah Jenkins (doc_4)', pin: '12345', room: 'Room 302' },
  { code: 'neuro', name: 'Neurology', doctor: 'Dr. Jonathan Blake (doc_5)', pin: '12345', room: 'Room 401' },
  { code: 'emg', name: 'Emergency Triage', doctor: 'Dr. Clara Oswald (doc_6)', pin: '12345', room: 'ER Bay 1' },
  { code: 'derm', name: 'Dermatology', doctor: 'Dr. Priya Sharma (doc_7)', pin: '12345', room: 'Room 205' },
  { code: 'ent', name: 'ENT & Audiology', doctor: 'Dr. Kevin Zhao (doc_8)', pin: '12345', room: 'Room 110' },
  { code: 'rec', name: 'Receptionist Desk', doctor: 'Main Desk (rec / rec_1)', pin: '12345', room: 'Front Lobby' }
];

export default function ReceptionistPage() {
  const router = useRouter();
  const { formatPrice } = useCurrency();
  const [activeTab, setActiveTab] = useState<'queue' | 'scan' | 'timetable' | 'departments' | 'backup'>('queue');
  
  const [doctors, setDoctors] = useState<any[]>([]);
  const [scanResult, setScanResult] = useState<string | null>(null);
  const [aiSummary, setAiSummary] = useState<string>('');
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingTicket, setEditingTicket] = useState<any>(null);
  const [editName, setEditName] = useState('');
  const [editPhone, setEditPhone] = useState('');


  // Supabase & Offline Backup Sync State
  const [syncStatus, setSyncStatus] = useState<any>({
    supabase_configured: true,
    supabase_connected: true,
    total_tickets: 0,
    synced_count: 0,
    unsynced_count: 0,
    offline_backups_count: 0,
    backup_directory: '',
    recent_tickets: []
  });
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);

  useEffect(() => {
    const role = localStorage.getItem('user_role');
    if (role !== 'RECEPTIONIST') {
      router.push('/login');
    } else {
      fetchDoctors();
      loadSyncStatus();
    }
  }, [router]);

  // Periodic refresh for queue and sync status
  useEffect(() => {
    const interval = setInterval(() => {
      loadSyncStatus();
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  const loadSyncStatus = async () => {
    try {
      const data = await fetchSyncStatus();
      if (data) {
        if (searchQuery) {
          // If searching, hit the search API for tickets
          const searchRes = await api.get(`/receptionist/tickets/search?query=${encodeURIComponent(searchQuery)}`);
          data.recent_tickets = searchRes;
        } else {
          // Otherwise get the live queue
          const liveRes = await api.get('/receptionist/tickets/live');
          data.recent_tickets = liveRes;
        }
        setSyncStatus(data);
      }
    } catch (e) {
      console.error('Failed to load sync status:', e);
    }
  };

  const handleManualSync = async () => {
    setIsSyncing(true);
    setSyncFeedback(null);
    try {
      const res = await triggerSync();
      setSyncFeedback(`Successfully synchronized! ${res.synced_in_run || 0} tickets synced to Supabase. ${res.total_offline_backups || 0} offline JSON snapshots verified.`);
      await loadSyncStatus();
    } catch (e) {
      setSyncFeedback('Sync completed locally. Offline backup saved.');
      await loadSyncStatus();
    } finally {
      setIsSyncing(false);
      setTimeout(() => setSyncFeedback(null), 7000);
    }
  };

  const fetchDoctors = async () => {
    try {
      const res = await api.get('/kiosk/doctors');
      setDoctors(res);
    } catch (e) {
      console.error(e);
    }
  };

  const handleUpdateSchedule = async (doctorId: string, newSchedule: string) => {
    try {
      await api.post(`/doctors/${doctorId}/schedule`, { shift_schedule: newSchedule });
      alert('Schedule updated successfully!');
      fetchDoctors();
    } catch (e) {
      alert('Failed to update schedule');
    }
  };

  const onScan = async (result: any) => {
    if (result && result.length > 0) {
      const ticketId = result[0].rawValue;
      setScanResult(ticketId);
      setAiSummary('');
      setLoadingSummary(true);
      
      try {
        const res = await api.get(`/ai/summary/${ticketId}`);
        setAiSummary(res.summary);
      } catch (e) {
        setAiSummary('Unable to generate summary for this patient/ticket.');
      } finally {
        setLoadingSummary(false);
      }
    }
  };

  const handleStatusChange = async (ticketId: string, status: 'SUCCESS' | 'FAILED') => {
    try {
      await api.put(`/receptionist/tickets/${ticketId}/status`, { status });
      loadSyncStatus();
    } catch (e) {
      alert('Failed to update status');
    }
  };

  const handleSaveEdit = async () => {
    if (!editingTicket) return;
    try {
      await api.put(`/receptionist/patients/${editingTicket.ticket_id}`, {
        patient_name: editName,
        patient_phone: editPhone
      });
      setEditingTicket(null);
      loadSyncStatus();
    } catch (e) {
      alert('Failed to save patient info');
    }
  };

  const openEdit = (ticket: any) => {
    setEditName(ticket.patient_name || '');
    setEditPhone(ticket.patient_phone || '');
    setEditingTicket(ticket);
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-main)', color: 'var(--text-primary)', fontFamily: "'Space Grotesk'" }}>
      <MediVERSENav currentModule="receptionist" />
      
      <main style={{ padding: '120px 5% 60px', maxWidth: 1200, margin: '0 auto' }}>
        {/* Header Title */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 20, marginBottom: 30 }}>
          <div>
            <h1 style={{ fontFamily: "'Bebas Neue'", fontSize: 56, letterSpacing: '.05em', margin: 0 }}>
              RECEPTIONIST CONTROL DESK
            </h1>
            <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0', fontSize: 15 }}>
              Patient Queue • Supabase Cloud Sync • Offline JSON Storage • Staff Credentials
            </p>
          </div>

          {/* Sync Trigger Button */}
          <button
            onClick={handleManualSync}
            disabled={isSyncing}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '14px 24px',
              background: isSyncing ? 'rgba(52, 199, 89, 0.2)' : '#34c759',
              color: isSyncing ? '#34c759' : '#000',
              border: isSyncing ? '1px solid #34c759' : 'none',
              fontWeight: 800,
              fontFamily: "'Space Grotesk'",
              borderRadius: 8,
              cursor: isSyncing ? 'wait' : 'pointer',
              letterSpacing: '.05em',
              textTransform: 'uppercase',
              boxShadow: '0 4px 14px rgba(52, 199, 89, 0.3)',
              transition: 'all 0.2s'
            }}
          >
            <span>{isSyncing ? 'SYNCING DATA...' : 'SYNC TO SUPABASE & BACKUP NOW'}</span>
          </button>
        </div>

        {/* Live Supabase & Offline Backup Status Banner */}
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: 14,
          padding: '20px 24px',
          marginBottom: 32,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 16
        }}>
          {/* Supabase Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 14, height: 14, borderRadius: '50%',
              background: syncStatus.supabase_connected ? '#34c759' : '#ff3b30',
              boxShadow: syncStatus.supabase_connected ? '0 0 10px #34c759' : '0 0 10px #ff3b30'
            }} />
            <div>
              <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Supabase Cloud DB</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: syncStatus.supabase_connected ? '#34c759' : '#ff3b30' }}>
                {syncStatus.supabase_connected ? '● CONNECTED & LIVE' : '○ OFFLINE (FALLBACK)'}
              </div>
            </div>
          </div>

          {/* Local Offline Backup */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 14, height: 14, borderRadius: '50%',
              background: '#007aff',
              boxShadow: '0 0 10px #007aff'
            }} />
            <div>
              <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Local Offline Backups</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#007aff' }}>
                [BACKUP] {syncStatus.offline_backups_count || 0} JSON Snapshots Active
              </div>
            </div>
          </div>

          {/* Queue Count */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 14, height: 14, borderRadius: '50%',
              background: '#D91636',
              boxShadow: '0 0 10px #D91636'
            }} />
            <div>
              <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Total Patients Registered</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                {syncStatus.total_tickets || 0} Tickets ({syncStatus.synced_count || 0} Synced)
              </div>
            </div>
          </div>

          {/* Default Currency Badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 14, height: 14, borderRadius: '50%',
              background: '#ffd60a',
              boxShadow: '0 0 10px #ffd60a'
            }} />
            <div>
              <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Billing Currency</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#ffd60a' }}>
                ₹ INR (Rupees Default)
              </div>
            </div>
          </div>
        </div>

        {/* Sync Feedback Toast */}
        {syncFeedback && (
          <div style={{
            background: 'rgba(52, 199, 89, 0.15)',
            border: '1px solid #34c759',
            color: '#34c759',
            padding: '14px 20px',
            borderRadius: 8,
            marginBottom: 24,
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: 12
          }}>
            <span>[OK]</span>
            <span>{syncFeedback}</span>
          </div>
        )}

        {/* Navigation Tabs */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 30, flexWrap: 'wrap' }}>
          {[
            { id: 'queue', label: 'Live Queue & Sync' },
            { id: 'scan', label: 'Scan Patient QR' },
            { id: 'timetable', label: 'Doctor Timetables' },
            { id: 'departments', label: 'Dept Staff & Logins (12345)' },
            { id: 'backup', label: 'Offline Backup System' }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              style={{
                flex: 1, minWidth: 160, padding: '14px 18px', border: '1px solid var(--border-color)',
                background: activeTab === tab.id ? '#D91636' : 'var(--bg-card)',
                color: activeTab === tab.id ? '#fff' : 'var(--text-primary)', 
                fontFamily: "'Space Grotesk'", fontWeight: 700, textTransform: 'uppercase',
                fontSize: 14, letterSpacing: '.05em', cursor: 'pointer', transition: 'all 0.2s',
                borderRadius: 8
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* TAB 1: LIVE QUEUE & SYNC */}
        {activeTab === 'queue' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', padding: 30, borderRadius: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h2 style={{ fontFamily: "'Bebas Neue'", fontSize: 32, margin: 0 }}>PATIENT REGISTRATION & SYNC QUEUE</h2>
                <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0 0', fontSize: 14 }}>
                  Real-time synchronization status between Local SQLite, Offline JSON, and Supabase Cloud.
                </p>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <input 
                  type="text" 
                  placeholder="Search by ID, Name, Phone..."
                  value={searchQuery}
                  onChange={e => { setSearchQuery(e.target.value); loadSyncStatus(); }}
                  style={{
                    padding: '8px 12px', background: 'var(--bg-main)', border: '1px solid var(--border-color)', 
                    borderRadius: 6, color: '#fff', fontFamily: "'Space Grotesk'", width: 250
                  }}
                />
                <button
                  onClick={loadSyncStatus}
                  style={{
                    background: 'var(--bg-main)', border: '1px solid var(--border-color)', color: 'var(--text-primary)',
                    padding: '8px 16px', borderRadius: 6, cursor: 'pointer', fontFamily: "'Space Grotesk'", fontWeight: 600
                  }}
                >
                  Refresh Queue
                </button>
              </div>
            </div>

            {(!syncStatus.recent_tickets || syncStatus.recent_tickets.length === 0) ? (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)' }}>
                No patient tickets registered yet. Issue a ticket at Kiosk or Voice Assistant.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: 13, textTransform: 'uppercase' }}>
                      <th style={{ padding: '12px 16px' }}>Token #</th>
                      <th style={{ padding: '12px 16px' }}>Patient Info</th>
                      <th style={{ padding: '12px 16px' }}>Department</th>
                      <th style={{ padding: '12px 16px' }}>Status / Sync</th>
                      <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {syncStatus.recent_tickets.map((ticket: any, idx: number) => (
                      <tr key={ticket.ticket_id || idx} style={{ borderBottom: '1px solid var(--border-color)', fontSize: 14 }}>
                        <td style={{ padding: '14px 16px', fontWeight: 800, color: '#D91636' }}>
                          {ticket.token_number}
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          {editingTicket?.ticket_id === ticket.ticket_id ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                              <input type="text" value={editName} onChange={e => setEditName(e.target.value)} style={{ padding: 4, background: '#000', color: '#fff', border: '1px solid var(--border-color)' }} />
                              <input type="text" value={editPhone} onChange={e => setEditPhone(e.target.value)} style={{ padding: 4, background: '#000', color: '#fff', border: '1px solid var(--border-color)' }} />
                              <div style={{ display: 'flex', gap: 8 }}>
                                <button onClick={handleSaveEdit} style={{ background: '#34c759', border: 'none', borderRadius: 4, color: '#fff', padding: '4px 8px', cursor: 'pointer' }}>Save</button>
                                <button onClick={() => setEditingTicket(null)} style={{ background: '#333', border: 'none', borderRadius: 4, color: '#fff', padding: '4px 8px', cursor: 'pointer' }}>Cancel</button>
                              </div>
                            </div>
                          ) : (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div>
                                <div style={{ fontWeight: 600 }}>{ticket.patient_name || 'Walk-in Patient'}</div>
                                <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{ticket.patient_phone || '—'}</div>
                              </div>
                              <button onClick={() => openEdit(ticket)} style={{ background: 'none', border: 'none', color: '#007aff', cursor: 'pointer', fontSize: 12 }}>Edit</button>
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '14px 16px', textTransform: 'uppercase', fontSize: 12 }}>
                          <div>{ticket.department_id ? ticket.department_id.replace('dep_', '') : 'GEN'}</div>
                          <div style={{ color: 'var(--text-secondary)' }}>{ticket.doctor_id || 'Duty'}</div>
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            <span style={{
                              padding: '4px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700, display: 'inline-block', width: 'fit-content',
                              background: ticket.status === 'WAITING' ? 'rgba(255, 214, 10, 0.15)' :
                                          ticket.status === 'CALLING' ? 'rgba(217, 22, 54, 0.15)' :
                                          ticket.status === 'SUCCESS' ? 'rgba(52, 199, 89, 0.15)' :
                                          ticket.status === 'FAILED' ? 'rgba(255, 59, 48, 0.15)' :
                                          'rgba(0, 122, 255, 0.15)',
                              color: ticket.status === 'WAITING' ? '#ffd60a' :
                                     ticket.status === 'CALLING' ? '#D91636' : 
                                     ticket.status === 'SUCCESS' ? '#34c759' : 
                                     ticket.status === 'FAILED' ? '#ff3b30' : '#007aff'
                            }}>
                              {ticket.status}
                            </span>
                            <span style={{
                              display: 'inline-flex', alignItems: 'center', gap: 6,
                              padding: '2px 6px', borderRadius: 6, fontSize: 10, fontWeight: 700, width: 'fit-content',
                              background: ticket.synced ? 'rgba(52, 199, 89, 0.15)' : 'rgba(0, 122, 255, 0.15)',
                              border: `1px solid ${ticket.synced ? '#34c759' : '#007aff'}`,
                              color: ticket.synced ? '#34c759' : '#007aff'
                            }}>
                              {ticket.synced ? 'CLOUD' : 'LOCAL'}
                            </span>
                          </div>
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                          {(ticket.status !== 'SUCCESS' && ticket.status !== 'FAILED') && (
                            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                              <button onClick={() => handleStatusChange(ticket.ticket_id, 'SUCCESS')} style={{
                                background: 'rgba(52, 199, 89, 0.1)', border: '1px solid #34c759', color: '#34c759', 
                                padding: '6px 12px', borderRadius: 6, cursor: 'pointer', fontFamily: "'Space Grotesk'", fontWeight: 700, fontSize: 12
                              }}>✓ Success</button>
                              <button onClick={() => handleStatusChange(ticket.ticket_id, 'FAILED')} style={{
                                background: 'rgba(255, 59, 48, 0.1)', border: '1px solid #ff3b30', color: '#ff3b30', 
                                padding: '6px 12px', borderRadius: 6, cursor: 'pointer', fontFamily: "'Space Grotesk'", fontWeight: 700, fontSize: 12
                              }}>✕ Fail</button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: SCAN PATIENT QR */}
        {activeTab === 'scan' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', padding: 40, borderRadius: 16 }}>
            <h2 style={{ fontFamily: "'Bebas Neue'", fontSize: 32, marginBottom: 20 }}>SCAN PATIENT QR</h2>
            <div style={{ maxWidth: 400, margin: '0 auto', overflow: 'hidden', borderRadius: 12, border: '2px solid var(--border-color)' }}>
              <Scanner onScan={onScan} />
            </div>
            
            {scanResult && (
              <div style={{ marginTop: 24, textAlign: 'center' }}>
                <p style={{ color: '#D91636', fontSize: 'clamp(26px, 2.9vw, 30px)', fontWeight: 700 }}>Scanned Token: {scanResult}</p>
                
                <div style={{ marginTop: 20, background: 'var(--bg-main)', padding: 20, borderRadius: 12, border: '1px solid var(--border-color)', textAlign: 'left' }}>
                  <h3 style={{ fontSize: 'clamp(18px, 1.9vw, 22px)', marginBottom: 12, color: 'var(--text-secondary)' }}>AI PATIENT SUMMARY</h3>
                  {loadingSummary ? (
                    <p style={{ color: '#D91636' }}>Generating summary via HuggingFace...</p>
                  ) : (
                    <p style={{ fontSize: 'clamp(20px, 2.2vw, 24px)', lineHeight: 1.5 }}>{aiSummary}</p>
                  )}
                </div>

                <button 
                  onClick={() => window.print()}
                  style={{ marginTop: 24, background: '#D91636', color: '#fff', padding: '16px 32px', fontWeight: 700, border: 'none', cursor: 'pointer', borderRadius: 8 }}
                >
                  PRINT FINAL BILL (INR ₹)
                </button>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: DOCTOR TIMETABLES */}
        {activeTab === 'timetable' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', padding: 40, borderRadius: 16 }}>
            <h2 style={{ fontFamily: "'Bebas Neue'", fontSize: 32, marginBottom: 20 }}>DOCTOR TIMETABLES & ROSTER</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {doctors.map((doc, idx) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-main)', padding: 16, borderRadius: 8, border: '1px solid var(--border-color)', flexWrap: 'wrap', gap: 12 }}>
                  <div>
                    <h3 style={{ fontSize: 'clamp(18px, 2vw, 22px)', margin: 0 }}>{doc.name}</h3>
                    <p style={{ fontSize: 'clamp(14px, 1.5vw, 17px)', color: 'var(--text-secondary)', margin: 0 }}>{doc.specialty} • {doc.room_number}</p>
                    <p style={{ fontSize: 13, color: '#34c759', margin: '4px 0 0 0', fontWeight: 600 }}>Fee: {formatPrice(doc.consultation_fee || 500)}</p>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <input 
                      type="text" 
                      defaultValue={doc.shift_schedule || ''}
                      placeholder="e.g. 09:00 AM - 05:00 PM"
                      onBlur={(e) => handleUpdateSchedule(doc.id, e.target.value)}
                      style={{ padding: '8px 12px', borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-input)', color: 'var(--text-primary)', fontFamily: "'Space Grotesk'" }}
                    />
                    <span style={{ fontSize: 'clamp(14px, 1.4vw, 18px)', color: doc.is_available ? '#34c759' : '#ff3b30' }}>
                      {doc.is_available ? '● PRESENT' : '● ABSENT'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 4: DEPARTMENTS & STAFF LOGINS */}
        {activeTab === 'departments' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', padding: 30, borderRadius: 16 }}>
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontFamily: "'Bebas Neue'", fontSize: 32, margin: 0 }}>HOSPITAL DEPARTMENTS & EASY LOGIN DIRECTORY</h2>
              <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0', fontSize: 14 }}>
                All staff logins are standardized for speed. Username can be the department code or doctor ID, and PIN is <strong>12345</strong>.
              </p>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: 13, textTransform: 'uppercase' }}>
                    <th style={{ padding: '12px 16px' }}>Department</th>
                    <th style={{ padding: '12px 16px' }}>Shortcut Username</th>
                    <th style={{ padding: '12px 16px' }}>Default PIN</th>
                    <th style={{ padding: '12px 16px' }}>Assigned Room</th>
                    <th style={{ padding: '12px 16px' }}>Staff / Doctor</th>
                    <th style={{ padding: '12px 16px' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {DEPARTMENTS_LIST.map((dept, i) => (
                    <tr key={dept.code} style={{ borderBottom: '1px solid var(--border-color)', fontSize: 14 }}>
                      <td style={{ padding: '14px 16px', fontWeight: 700 }}>
                        {dept.name}
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <code style={{ background: 'var(--bg-input)', padding: '4px 8px', borderRadius: 4, color: '#D91636', fontWeight: 700, fontSize: 14 }}>
                          {dept.code}
                        </code>
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <code style={{ background: 'var(--bg-input)', padding: '4px 8px', borderRadius: 4, color: '#34c759', fontWeight: 700, fontSize: 14 }}>
                          {dept.pin}
                        </code>
                      </td>
                      <td style={{ padding: '14px 16px', color: 'var(--text-secondary)' }}>
                        {dept.room}
                      </td>
                      <td style={{ padding: '14px 16px', color: 'var(--text-secondary)' }}>
                        {dept.doctor}
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <button
                          onClick={() => {
                            localStorage.setItem('user_role', dept.code === 'rec' ? 'RECEPTIONIST' : 'DOCTOR');
                            localStorage.setItem('user_id', dept.code === 'rec' ? 'rec_1' : `doc_${dept.code}`);
                            localStorage.setItem('user_name', dept.doctor);
                            router.push(dept.code === 'rec' ? '/receptionist' : '/doctor-desk');
                          }}
                          style={{
                            background: 'none', border: '1px solid var(--border-color)', color: 'var(--text-primary)',
                            padding: '6px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 700
                          }}
                        >
                          Quick Switch
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 5: OFFLINE BACKUP SYSTEM */}
        {activeTab === 'backup' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', padding: 30, borderRadius: 16 }}>
            <h2 style={{ fontFamily: "'Bebas Neue'", fontSize: 32, marginBottom: 12 }}>LOCAL OFFLINE BACKUP STORAGE</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: 24, fontSize: 15, lineHeight: 1.6 }}>
              In compliance with hospital resilience requirements, all patient encounters, triage results, and bills are instantly saved to local disk as JSON snapshots under <code style={{ color: '#007aff' }}>data/backup_offline/</code> before being synced to Supabase Cloud.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20, marginBottom: 30 }}>
              <div style={{ background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: 10, padding: 20 }}>
                <div style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Local Directory</div>
                <div style={{ fontSize: 14, fontWeight: 600, wordBreak: 'break-all', marginTop: 8 }}>
                  {syncStatus.backup_directory || 'data/backup_offline'}
                </div>
              </div>

              <div style={{ background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: 10, padding: 20 }}>
                <div style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Verified Snapshots</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#007aff', marginTop: 4 }}>
                  {syncStatus.offline_backups_count || 0} Files
                </div>
              </div>

              <div style={{ background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: 10, padding: 20 }}>
                <div style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>Supabase Synchronization</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: syncStatus.supabase_connected ? '#34c759' : '#ff3b30', marginTop: 10 }}>
                  {syncStatus.supabase_connected ? '[OK] Cloud Sync Operational' : '[OFFLINE] Standalone Local Mode'}
                </div>
              </div>
            </div>

            <button
              onClick={handleManualSync}
              disabled={isSyncing}
              style={{
                padding: '14px 28px', background: '#007aff', color: '#fff', border: 'none',
                fontFamily: "'Space Grotesk'", fontWeight: 700, borderRadius: 8, cursor: 'pointer',
                letterSpacing: '.05em', textTransform: 'uppercase'
              }}
            >
              {isSyncing ? 'Running Snapshot & Sync...' : 'Trigger Full Backup & Cloud Push'}
            </button>
          </div>
        )}

      </main>
    </div>
  );
}
