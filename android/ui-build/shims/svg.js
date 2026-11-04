import React from 'react';
export default function Svg({ width, height, viewBox, children }) {
  return <svg width={width} height={height} viewBox={viewBox} fill="none" aria-hidden="true" style={{ display: 'block', flexShrink: 0, overflow: 'visible' }}>{children}</svg>;
}
export function Path({ d, stroke, strokeWidth, strokeLinecap, strokeLinejoin, fill }) {
  return <path d={d} stroke={stroke} strokeWidth={strokeWidth} strokeLinecap={strokeLinecap} strokeLinejoin={strokeLinejoin} fill={fill || 'none'} />;
}
export function Circle({ cx, cy, r, fill, stroke, strokeWidth, opacity }) {
  return <circle cx={cx} cy={cy} r={r} fill={fill || 'none'} stroke={stroke} strokeWidth={strokeWidth} opacity={opacity} />;
}
export function Defs({ children }) {
  return <defs>{children}</defs>;
}
export function RadialGradient({ id, cx, cy, r, fx, fy, children }) {
  return <radialGradient id={id} cx={cx} cy={cy} r={r} fx={fx} fy={fy}>{children}</radialGradient>;
}
export function LinearGradient({ id, x1, y1, x2, y2, children }) {
  return <linearGradient id={id} x1={x1} y1={y1} x2={x2} y2={y2}>{children}</linearGradient>;
}
export function Stop({ offset, stopColor, stopOpacity }) {
  return <stop offset={offset} stopColor={stopColor} stopOpacity={stopOpacity} />;
}
