import { useMemo } from 'react';

interface GaugeChartProps {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  sublabel?: string;
}

export function GaugeChart({
  value,
  max = 100,
  size = 160,
  strokeWidth = 12,
  label,
  sublabel,
}: GaugeChartProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * Math.PI; // Half circle
  const percentage = Math.min(value / max, 1);
  const offset = circumference * (1 - percentage);

  const center = size / 2;

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size / 2 + 20} className="overflow-visible">
        {/* Background arc */}
        <path
          d={`M ${strokeWidth / 2} ${center} A ${radius} ${radius} 0 0 1 ${size - strokeWidth / 2} ${center}`}
          fill="none"
          stroke="hsl(var(--gauge-background))"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Value arc */}
        <path
          d={`M ${strokeWidth / 2} ${center} A ${radius} ${radius} 0 0 1 ${size - strokeWidth / 2} ${center}`}
          fill="none"
          stroke="hsl(var(--gauge-fill))"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-500"
        />
        {/* Center text */}
        <text
          x={center}
          y={center - 10}
          textAnchor="middle"
          className="fill-foreground text-2xl font-bold"
        >
          {value}%
        </text>
      </svg>
      {(label || sublabel) && (
        <div className="text-center -mt-2">
          {label && <p className="text-sm font-medium text-foreground">{label}</p>}
          {sublabel && <p className="text-xs text-muted-foreground">{sublabel}</p>}
        </div>
      )}
    </div>
  );
}
