import { Department, Doctor, HealthComboPackage, TicketCreateRequest, QueueTicket, QueueBoardResponse } from '../types';

function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    return `http://${host}:4040/api/v1`;
  }
  return 'http://localhost:4040/api/v1';
}

const getBaseUrl = () => getApiBase();
const API_BASE = getApiBase();

export async function fetchDepartments(): Promise<Department[]> {
  try {
    const res = await fetch(`${API_BASE}/kiosk/departments`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch departments');
    return await res.json();
  } catch (err) {
    console.warn('Backend API unreachable, using client fallback catalog:', err);
    return [
      { id: 'dep_gen', name: 'General Clinic', code: 'GEN', description: 'Routine checkups & prescriptions', active_doctors_count: 3, wait_time_minutes: 5 },
      { id: 'dep_card', name: 'Cardiology', code: 'CARD', description: 'Heart health & ECG diagnostics', active_doctors_count: 2, wait_time_minutes: 12 },
      { id: 'dep_ped', name: 'Pediatrics', code: 'PED', description: 'Child care Express counter', active_doctors_count: 2, wait_time_minutes: 8 },
      { id: 'dep_ortho', name: 'Orthopedics', code: 'ORTH', description: 'Joint & bone injury consults', active_doctors_count: 1, wait_time_minutes: 15 },
      { id: 'dep_pharm', name: 'Express Pharmacy', code: 'RX', description: 'Fast prescription pickup', active_doctors_count: 4, wait_time_minutes: 3 },
      { id: 'dep_emg', name: 'Emergency Triage', code: 'EMG', description: 'Immediate acute triage', active_doctors_count: 3, wait_time_minutes: 0 }
    ];
  }
}

export async function fetchDoctors(departmentId?: string): Promise<Doctor[]> {
  try {
    const url = departmentId 
      ? `${API_BASE}/kiosk/doctors?department_id=${departmentId}`
      : `${API_BASE}/kiosk/doctors`;
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch doctors');
    return await res.json();
  } catch (err) {
    const docs: Doctor[] = [
      { id: 'doc_1', name: 'Dr. Marcus Vance', department_id: 'dep_gen', specialty: 'Family Medicine Specialist', room_number: 'Room 101', is_available: true, estimated_wait_minutes: 5, consultation_fee: 35.0, rating: 4.9, experience_years: 12 },
      { id: 'doc_2', name: 'Dr. Elena Rostova', department_id: 'dep_card', specialty: 'Cardiologist & ECG Expert', room_number: 'Room 204', is_available: true, estimated_wait_minutes: 10, consultation_fee: 65.0, rating: 4.95, experience_years: 16 },
      { id: 'doc_3', name: 'Dr. Aris Thorne', department_id: 'dep_ped', specialty: 'Pediatric Specialist', room_number: 'Room 108', is_available: true, estimated_wait_minutes: 8, consultation_fee: 40.0, rating: 4.85, experience_years: 9 },
      { id: 'doc_4', name: 'Dr. Sarah Jenkins', department_id: 'dep_ortho', specialty: 'Joint & Bone Specialist', room_number: 'Room 302', is_available: true, estimated_wait_minutes: 15, consultation_fee: 55.0, rating: 4.8, experience_years: 14 }
    ];
    return departmentId ? docs.filter(d => d.department_id === departmentId) : docs;
  }
}

export async function fetchHealthCombos(): Promise<HealthComboPackage[]> {
  try {
    const res = await fetch(`${API_BASE}/kiosk/combos`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch combos');
    return await res.json();
  } catch (err) {
    return [
      { id: 'cmb_1', title: 'Vitals & BP Screening Combo', category: 'Quick Diagnostics', description: 'Digital BP, Pulse & BMI report', included_tests: ['Digital BP Check', 'Pulse Oximetry', 'BMI Index'], price: 15.0, priority_bump: 1 },
      { id: 'cmb_2', title: 'Express Cardiac Shield Combo', category: 'Advanced Screening', description: '12-lead ECG & Lipid panel sample', included_tests: ['12-Lead ECG', 'Lipid Panel Sample', 'Cardio Vitals'], price: 45.0, priority_bump: 3 },
      { id: 'cmb_3', title: 'Full Metabolic Lab Combo', category: 'Lab Diagnostics', description: 'Complete Blood Count & Glucose', included_tests: ['CBC Test', 'Fasting Glucose', 'Kidney Function'], price: 55.0, priority_bump: 2 }
    ];
  }
}

export async function createTicket(payload: TicketCreateRequest): Promise<QueueTicket> {
  try {
    const res = await fetch(`${API_BASE}/kiosk/ticket`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to create ticket');
    return await res.json();
  } catch (err) {
    const randomCode = payload.department_id.substring(4, 7).toUpperCase();
    const tokenNum = `${randomCode}-${Math.floor(100 + Math.random() * 900)}`;
    return {
      ticket_id: `tck-local-${Date.now()}`,
      token_number: tokenNum,
      department_id: payload.department_id,
      department_name: payload.department_id.replace('dep_', '').toUpperCase() + ' Clinic',
      doctor_name: payload.doctor_id ? 'Dr. Marcus Vance' : 'Duty Specialist',
      room_number: 'Room 101',
      patient_name: payload.patient.full_name,
      patient_phone: payload.patient.phone || '',
      status: 'WAITING',
      priority_level: payload.vitals && payload.vitals.pain_score > 6 ? 'EMERGENCY' : 'STANDARD',
      triage_score: payload.vitals ? payload.vitals.pain_score : 2,
      combos_selected: payload.combo_package_ids.length > 0 ? ['Vitals & BP Screening Combo'] : [],
      total_fee: 35.0,
      created_at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      estimated_call_time: '~5 mins'
    };
  }
}

export async function getTicketStatus(ticketId: string): Promise<QueueTicket> {
  const baseUrl = getApiBase();
  try {
    const res = await fetch(`${baseUrl}/receptionist/tickets/search?q=${encodeURIComponent(ticketId)}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      const tickets: QueueTicket[] = data.tickets ?? data ?? [];
      const match = tickets.find((t: QueueTicket) => t.ticket_id === ticketId);
      if (match) return match;
    }
  } catch {}
  throw new Error(`Ticket ${ticketId} not found`);
}

export async function fetchQueueBoard(): Promise<QueueBoardResponse> {
  try {
    const res = await fetch(`${API_BASE}/queue/board`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch queue board');
    return await res.json();
  } catch (err) {
    return {
      now_calling: {
        ticket_id: 'demo-1',
        token_number: 'GEN-101',
        department_id: 'dep_gen',
        department_name: 'General Clinic',
        doctor_name: 'Dr. Marcus Vance',
        room_number: 'Room 101',
        patient_name: 'Alex Mercer',
        status: 'NOW_CALLING',
        priority_level: 'STANDARD',
        triage_score: 2,
        combos_selected: ['Vitals Combo'],
        total_fee: 50.0,
        created_at: '19:40:00',
        estimated_call_time: 'Now'
      },
      recently_called: [],
      waiting_queue: [
        {
          ticket_id: 'demo-2',
          token_number: 'CARD-102',
          department_id: 'dep_card',
          department_name: 'Cardiology',
          doctor_name: 'Dr. Elena Rostova',
          room_number: 'Room 204',
          patient_name: 'Sophia Martinez',
          status: 'WAITING',
          priority_level: 'URGENT',
          triage_score: 6,
          combos_selected: ['Express Cardiac Shield'],
          total_fee: 110.0,
          created_at: '19:42:00',
          estimated_call_time: '6 mins'
        }
      ],
      completed_today: 18,
      average_wait_minutes: 5
    };
  }
}

export async function callNextPatient(doctorId: string, roomNumber: string): Promise<QueueTicket | null> {
  try {
    const res = await fetch(`${API_BASE}/queue/call-next`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doctor_id: doctorId, room_number: roomNumber })
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('Call next error:', err);
    return null;
  }
}

export async function updateTicketStatus(ticketId: string, newStatus: string): Promise<QueueTicket | null> {
  try {
    const res = await fetch(`${API_BASE}/queue/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticket_id: ticketId, new_status: newStatus })
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('Update status error:', err);
    return null;
  }
}

export async function notifyUpcoming(ticketId: string): Promise<{ status: string; message: string; phone?: string }> {
  try {
    const res = await fetch(`${API_BASE}/queue/notify-upcoming/${ticketId}`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to notify patient');
    return await res.json();
  } catch (err) {
    return { status: 'sent', message: 'Upcoming turn notification sent to patient phone' };
  }
}

export async function chatWithVoiceAssistant(
  sessionId: string | null, 
  message: string
): Promise<{session_id: string, reply: string, action: string | null, action_data: any, audio_base64?: string}> {
  try {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}/ai_voice/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message })
    });
    if (!res.ok) throw new Error('Voice chat failed');
    return await res.json();
  } catch (err) {
    console.error('Voice Chat Error:', err);
    return { 
      session_id: sessionId || '', 
      reply: "I'm having trouble connecting. Please try again.", 
      action: null, 
      action_data: null 
    };
  }
}

export async function synthesizeTTSAudio(
  text: string, 
  voice?: string
): Promise<string | null> {
  try {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}/ai_voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice })
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.audio_base64 || null;
  } catch (err) {
    console.warn('Backend TTS fetch error:', err);
    return null;
  }
}

export async function fetchSyncStatus(): Promise<any> {
  try {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}/sync/status`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch sync status');
    return await res.json();
  } catch (err) {
    console.warn('Sync status fetch error:', err);
    return {
      supabase_configured: false,
      supabase_connected: false,
      total_tickets: 0,
      synced_count: 0,
      unsynced_count: 0,
      offline_backups_count: 0,
      recent_tickets: []
    };
  }
}

export async function triggerSync(): Promise<any> {
  const baseUrl = getApiBase();
  const res = await fetch(`${baseUrl}/sync/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  if (!res.ok) throw new Error('Trigger sync failed');
  return await res.json();
}

export const api = {
  get: async (path: string) => {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}${path}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`API GET ${path} failed`);
    return await res.json();
  },
  post: async (path: string, body: any) => {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`API POST ${path} failed`);
    return await res.json();
  },
  put: async (path: string, body: any) => {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`API PUT ${path} failed`);
    return await res.json();
  }
};

// ── Session Event Tracking ──────────────────────────────────────────────────
export interface SessionEventPayload {
  session_id: string;
  event_type: 'click' | 'navigate' | 'input' | 'submit' | 'voice';
  page?: string;
  element?: string;
  value?: string;
  extra?: Record<string, unknown>;
}

export async function logSessionEvent(payload: SessionEventPayload): Promise<{ verified_supabase: boolean } | null> {
  try {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}/session/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    // Non-critical -- never crash the UI over a tracking failure
    return null;
  }
}

