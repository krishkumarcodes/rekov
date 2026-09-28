'use client';

import { Suspense, useState, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { MediVERSENav } from '@/components/common/MediVERSENav';
import { useVoiceCall } from '@/contexts/VoiceCallContext';

function MicIcon({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="11" rx="3"></rect>
      <path d="M5 10v2a7 7 0 0 0 14 0v-2"></path>
      <line x1="12" y1="19" x2="12" y2="22"></line>
      <line x1="8" y1="22" x2="16" y2="22"></line>
    </svg>
  );
}

function SpeakerIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
    </svg>
  );
}

function VoiceAssistantContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    isCallActive,
    callStatus,
    isMuted,
    liveTranscript,
    messages,
    latestTicket,
    startCall,
    endCall,
    toggleCall,
    toggleMute,
    sendTextMessage,
    interruptAI,
    addMessage,
    isIvrMode
  } = useVoiceCall();

  const [inputVal, setInputVal] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true;
      const pdf = searchParams?.get('pdf');
      const ticketId = searchParams?.get('ticket');
      let ticketContext = '';
      
      if (typeof window !== 'undefined') {
        try {
          const stored = localStorage.getItem('current_ticket');
          if (stored) {
            const t = JSON.parse(stored);
            ticketContext = `Token: ${t.token_number} | Dr. ${t.doctor_name} | ${t.room_number}`;
          }
        } catch {}
      }

      if (pdf && ticketId) {
        addMessage({
          role: 'assistant',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          content: `Here is your digital receipt${ticketContext ? ` (${ticketContext})` : ''}. Click [DOWNLOAD PDF](${pdf}) to save it.`
        });
        
        // Clean URL after injection
        router.replace('/voice-assistant');
      }
    }
  }, [searchParams, addMessage, router]);

  // Auto-start call on mounting voice-assistant page if not active
  useEffect(() => {
    if (!isCallActive) {
      startCall();
    }
  }, []);

  // Scroll chat to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, liveTranscript]);

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputVal.trim()) return;
    const txt = inputVal.trim();
    setInputVal('');
    sendTextMessage(txt);
  };

  const isUserSpeaking = callStatus === 'USER_SPEAKING';
  const isAISpeaking = callStatus === 'AI_SPEAKING';
  const isThinking = callStatus === 'AI_THINKING';

  const statusText = isMuted
    ? 'MIC MUTED'
    : isAISpeaking
    ? (isIvrMode ? 'IVR SPEAKING...' : 'AI SPEAKING...')
    : isThinking
    ? 'THINKING...'
    : liveTranscript
    ? `WORD DETECTED: "${liveTranscript}"`
    : isUserSpeaking
    ? 'HEARING SPEECH...'
    : isCallActive
    ? 'OPEN MIC LISTENING 24/7...'
    : 'CALL INACTIVE';

  return (
    <>
      <MediVERSENav currentModule="voice-assistant" />
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.06)} }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
      `}} />

      <div style={{
        position: 'relative', zIndex: 10,
        height: '100vh', display: 'flex', flexDirection: 'row',
        background: 'transparent', color: 'var(--text-primary)',
        overflow: 'hidden'
      }}>

        {/* LEFT: Chat History */}
        <div style={{
          flex: '1 1 60%', display: 'flex', flexDirection: 'column',
          borderRight: '1px solid var(--border-color)',
          paddingTop: 80
        }}>
          {/* Messages Container */}
          <div style={{
            flex: 1, overflowY: 'auto', padding: '16px 24px',
            display: 'flex', flexDirection: 'column', gap: 12
          }}>
            {messages.length === 0 && (
              <div style={{
                textAlign: 'center', margin: 'auto 0', color: 'var(--text-secondary)',
                fontFamily: "'Space Grotesk', sans-serif"
              }}>
                <div style={{ fontSize: 44, marginBottom: 12 }}>Mic</div>
                <h3 style={{ fontSize: 22, color: 'var(--text-primary)', marginBottom: 6 }}>
                  RITMO
                </h3>
                <p style={{ fontSize: 14 }}>
                  Speak naturally into your microphone or type a message below.
                </p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start'
              }}>
                <div style={{
                  maxWidth: '80%',
                  padding: '12px 18px',
                  borderRadius: msg.role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                  background: msg.role === 'user' ? 'rgba(217, 22, 54, 0.2)' : 'var(--bg-card)',
                  border: msg.role === 'user' ? '1px solid rgba(217, 22, 54, 0.5)' : '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                  fontFamily: "'Space Grotesk', sans-serif",
                  fontSize: 15,
                  lineHeight: 1.5,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
                }}>
                  {/* Basic markdown link parser for [text](url) */}
                  {msg.content.split(/(\[.*?\]\(.*?\))/g).map((part, pIdx) => {
                    const match = part.match(/\[(.*?)\]\((.*?)\)/);
                    if (match) {
                      return <a key={pIdx} href={match[2]} target="_blank" rel="noopener noreferrer" style={{ color: '#64d2ff', textDecoration: 'underline' }}>{match[1]}</a>;
                    }
                    return <span key={pIdx}>{part}</span>;
                  })}
                </div>
                <span style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 4, padding: '0 4px' }}>
                  {msg.timestamp}
                </span>
              </div>
            ))}

            {/* Live Interim Transcript */}
            {liveTranscript && (
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <div style={{
                  maxWidth: '80%', padding: '10px 16px', borderRadius: '18px 18px 4px 18px',
                  background: 'rgba(100, 210, 255, 0.15)', border: '1px dashed #64d2ff',
                  color: '#64d2ff', fontFamily: "'Space Grotesk', sans-serif", fontSize: 14
                }}>
                  "{liveTranscript}"
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Bottom Text Input Bar */}
          <form onSubmit={handleTextSubmit} style={{
            padding: '14px 24px', borderTop: '1px solid var(--border-color)',
            display: 'flex', gap: 12, background: 'rgba(0,0,0,0.4)'
          }}>
            <input
              type="text"
              value={inputVal}
              onChange={e => setInputVal(e.target.value)}
              placeholder="Type your message or speak naturally..."
              style={{
                flex: 1, padding: '12px 18px', borderRadius: 24,
                background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                color: 'var(--text-primary)', fontFamily: "'Space Grotesk', sans-serif",
                fontSize: 14, outline: 'none'
              }}
            />
            <button
              type="submit"
              style={{
                padding: '0 24px', borderRadius: 24, background: '#D91636', color: '#fff',
                border: 'none', fontWeight: 700, fontFamily: "'Space Grotesk', sans-serif",
                cursor: 'pointer'
              }}
            >
              SEND
            </button>
          </form>
        </div>

        {/* RIGHT: Voice Visualizer & Call Control Console */}
        <div style={{
          flex: '1 1 40%', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', padding: 32,
          paddingTop: 90, background: 'rgba(0,0,0,0.2)'
        }}>
          {/* Main Visualizer Orb */}
          <div
            onClick={toggleCall}
            style={{
              position: 'relative', width: 220, height: 220, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', marginBottom: 32
            }}
          >
            {/* Outer Pulsing Glow Ring */}
            <div style={{
              position: 'absolute', width: 220, height: 220, borderRadius: '50%',
              background: isMuted ? 'rgba(255,59,48,0.15)' : isAISpeaking ? (isIvrMode ? 'rgba(0,122,255,0.2)' : 'rgba(191,90,242,0.2)') : isUserSpeaking ? 'rgba(100,210,255,0.2)' : isCallActive ? 'rgba(48,209,88,0.15)' : 'rgba(217,22,54,0.15)',
              border: `2px solid ${isMuted ? '#ff3b30' : isAISpeaking ? (isIvrMode ? '#007aff' : '#bf5af2') : isUserSpeaking ? '#64d2ff' : isCallActive ? '#30d158' : '#D91636'}`,
              boxShadow: `0 0 40px ${isMuted ? 'rgba(255,59,48,0.4)' : isAISpeaking ? (isIvrMode ? 'rgba(0,122,255,0.5)' : 'rgba(191,90,242,0.5)') : isUserSpeaking ? 'rgba(100,210,255,0.5)' : isCallActive ? 'rgba(48,209,88,0.4)' : 'rgba(217,22,54,0.4)'}`,
              animation: isUserSpeaking || isAISpeaking ? 'pulse 1.2s infinite ease-in-out' : 'none'
            }} />

            {/* Inner Core Button */}
            <div style={{
              position: 'relative', zIndex: 2, width: 140, height: 140, borderRadius: '50%',
              background: isMuted ? '#ff3b30' : isAISpeaking ? (isIvrMode ? '#007aff' : '#bf5af2') : isUserSpeaking ? '#64d2ff' : isCallActive ? '#30d158' : '#D91636',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
              boxShadow: '0 8px 32px rgba(0,0,0,0.5)', transition: 'all 0.3s ease'
            }}>
              {isAISpeaking ? (
                <SpeakerIcon size={56} />
              ) : (
                <MicIcon size={56} />
              )}
            </div>
          </div>

          {/* Status Label */}
          <div style={{
            fontFamily: "'Space Grotesk', sans-serif", fontSize: 16, fontWeight: 700,
            color: isMuted ? '#ff3b30' : isAISpeaking ? (isIvrMode ? '#007aff' : '#bf5af2') : isUserSpeaking ? '#64d2ff' : isCallActive ? '#30d158' : '#ff4757',
            letterSpacing: '0.06em', textAlign: 'center', marginBottom: 24
          }}>
            {statusText}
          </div>

          {/* Controls Bar */}
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            {/* Interrupt AI Button */}
            {isAISpeaking && (
              <button
                onClick={interruptAI}
                style={{
                  padding: '12px 20px', borderRadius: 24, background: 'rgba(255, 159, 10, 0.2)',
                  border: '1px solid #ff9f0a', color: '#ff9f0a', fontFamily: "'Space Grotesk', sans-serif",
                  fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8
                }}
              >
                [HALT] INTERRUPT AI
              </button>
            )}

            {/* Mute Button */}
            <button
              onClick={toggleMute}
              style={{
                padding: '12px 24px', borderRadius: 24,
                background: isMuted ? 'rgba(255, 59, 48, 0.2)' : 'rgba(255, 255, 255, 0.1)',
                border: isMuted ? '1px solid #ff3b30' : '1px solid var(--border-color)',
                color: isMuted ? '#ff3b30' : 'var(--text-primary)',
                fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, cursor: 'pointer'
              }}
            >
              {isMuted ? 'UNMUTE MIC' : 'MUTE MIC'}
            </button>

            {/* Start / End Call Button */}
            <button
              onClick={toggleCall}
              style={{
                padding: '12px 28px', borderRadius: 24,
                background: isCallActive ? '#ff2d55' : '#30d158',
                color: '#fff', border: 'none',
                fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, cursor: 'pointer',
                boxShadow: '0 4px 16px rgba(0,0,0,0.3)'
              }}
            >
              {isCallActive ? 'END CALL' : 'START VOICE CALL'}
            </button>
          </div>

          {/* Latest Ticket Confirmation Card if issued */}
          {latestTicket && (
            <div style={{
              marginTop: 32, width: '100%', maxWidth: 360, background: 'var(--bg-card)',
              border: '1px solid #30d158', borderRadius: 16, padding: 18,
              boxShadow: '0 4px 20px rgba(48,209,88,0.2)', textAlign: 'center'
            }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#30d158', letterSpacing: '.08em' }}>
                TICKET ISSUED SUCCESSFULLY
              </span>
              <h4 style={{ fontSize: 24, margin: '6px 0', fontFamily: "'Bebas Neue', sans-serif" }}>
                TOKEN: {latestTicket.token_number}
              </h4>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>
                {latestTicket.department_name} • {latestTicket.patient_name}
              </p>
              <button
                onClick={() => router.push(`/receipt?id=${latestTicket.ticket_id}`)}
                style={{
                  marginTop: 12, padding: '8px 16px', background: '#30d158', color: '#000',
                  border: 'none', borderRadius: 12, fontWeight: 700, fontSize: 12, cursor: 'pointer'
                }}
              >
                VIEW DIGITAL RECEIPT
              </button>
            </div>
          )}
        </div>

      </div>
    </>
  );
}

export default function VoiceAssistantPage() {
  return (
    <Suspense fallback={<div style={{ padding: 40, color: 'white', textAlign: 'center' }}>Loading Voice Assistant...</div>}>
      <VoiceAssistantContent />
    </Suspense>
  );
}
