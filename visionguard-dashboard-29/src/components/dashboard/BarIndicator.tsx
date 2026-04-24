interface BarIndicatorProps {
  value: number;
  max: number;
  label?: string;
  valueLabel?: string;
  className?: string;
}

export function BarIndicator({ value, max, label, valueLabel, className }: BarIndicatorProps) {
  const percentage = Math.min((value / max) * 100, 100);

  return (
    <div className={className}>
      {label && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">{label}</span>
          <span className="text-sm text-muted-foreground">{valueLabel}</span>
        </div>
      )}
      <div className="relative h-20 w-full rounded-lg bg-muted overflow-hidden">
        <div
          className="absolute bottom-0 left-0 right-0 bg-primary/60 transition-all duration-500 rounded-lg"
          style={{ height: `${percentage}%` }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-medium text-foreground">
            {value.toFixed(1)} GB
          </span>
        </div>
      </div>
    </div>
  );
}
