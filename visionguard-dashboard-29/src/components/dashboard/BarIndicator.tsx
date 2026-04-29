interface BarIndicatorProps {
  value: number;
  max: number;
  label?: string;
  valueLabel?: string;
  unit?: string;
  className?: string;
}

export function BarIndicator({ value, max, label, valueLabel, unit = 'GB', className }: BarIndicatorProps) {
  const percentage = Math.max(0, Math.min((value / max) * 100, 100));

  return (
    <div className={className}>
      {label && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">{label}</span>
          <span className="text-sm text-muted-foreground">{valueLabel}</span>
        </div>
      )}
      <div className="relative h-28 w-full rounded-xl bg-secondary/50 overflow-hidden border border-border/50 shadow-inner">
        <div
          className="absolute bottom-0 left-0 right-0 bg-primary/70 transition-all duration-700 ease-out rounded-xl"
          style={{ height: `${percentage}%` }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-medium text-foreground">
            {valueLabel || `${value.toFixed(1)} ${unit}`}
          </span>
        </div>
      </div>
    </div>
  );
}
