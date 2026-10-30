import React from 'react';
export default function Svg({ width, height, viewBox, children }) {
  return <svg width={width} height={height} viewBox={viewBox} fill="none" style={{ display: 'block', flexShrink: 0 }}>{children}</svg>;
}
export function Path({ d, stroke, strokeWidth, strokeLinecap, strokeLinejoin, fill }) {
  return <path d={d} stroke={stroke} strokeWidth={strokeWidth} strokeLinecap={strokeLinecap} strokeLinejoin={strokeLinejoin} fill={fill || 'none'} />;
}
