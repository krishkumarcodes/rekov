import React from 'react';
import { Department } from '@/types';

interface CategoryNavProps {
  departments: Department[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const DEPT_SYMBOLS: Record<string, string> = {
  'GEN': '\u2695',
  'CARD': '\u2661',
  'PED': '\u2606',
  'ORTH': '\u2726',
  'RX': '\u271A',
  'EMG': '\u26A0',
};

export const CategoryNav: React.FC<CategoryNavProps> = ({ departments, selectedId, onSelect }) => {
  return (
    <>
      <style>{`
        .category-scroll-container::-webkit-scrollbar {
          width: 24px;
        }
        .category-scroll-container::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .category-scroll-container::-webkit-scrollbar-thumb {
          background: #D91636;
          border-radius: 12px;
          border: 4px solid #111; /* Gives it a padded pill look */
        }
        .category-scroll-container::-webkit-scrollbar-thumb:hover {
          background: #ff2d55;
        }
      `}</style>
      <div 
        className="category-scroll-container"
        style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', 
          gap: 8,
          maxHeight: '50vh', // Ensures it scrolls if there are many items
          overflowY: 'auto',
          paddingRight: '16px' // Space for the scrollbar
        }}
      >
        {departments.map((dep) => {
          const isSelected = selectedId === dep.id;
          const sym = DEPT_SYMBOLS[dep.code] || '\u2695';

          return (
            <button
              key={dep.id}
              onClick={() => onSelect(dep.id)}
              style={{
                padding: '28px 20px', textAlign: 'center', cursor: 'pointer',
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                background: isSelected ? 'rgba(255,45,85,.08)' : 'var(--bg-card)',
                border: `1px solid ${isSelected ? 'rgba(255,45,85,.3)' : 'var(--border-color)'}`,
                transition: 'background .2s, border-color .2s',
                position: 'relative'
              }}
            >
              <span style={{ fontSize: 28, marginBottom: 10, color: isSelected ? '#D91636' : 'var(--text-secondary)' }}>{sym}</span>
              <h3 style={{
                fontFamily: "'Space Grotesk'", fontSize: 'clamp(16px, 1.7vw, 20px)', fontWeight: 700,
                color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)', marginBottom: 4
              }}>{dep.name}</h3>
              <p style={{
                fontFamily: "'Space Grotesk'", fontSize: 'clamp(13px, 1.3vw, 17px)',
                color: 'var(--text-muted)', lineHeight: 1.4
              }}>{dep.description}</p>
              {dep.wait_time_minutes > 0 && (
                <span style={{
                  position: 'absolute', top: 8, right: 8,
                  fontFamily: "'Space Grotesk'", fontSize: 'clamp(11px, 1.1vw, 15px)', fontWeight: 700,
                  padding: '2px 8px', background: 'var(--bg-card)',
                  border: '1px solid var(--border-color)', color: 'var(--text-secondary)'
                }}>
                  {dep.wait_time_minutes}m
                </span>
              )}
            </button>
          );
        })}
      </div>
    </>
  );
};
