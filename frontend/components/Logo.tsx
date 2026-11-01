const ROTACAO = (-28 * Math.PI) / 180;

const SATELITES = [200, 320, 70].map((graus) => {
  const a = (graus * Math.PI) / 180;
  const x = 25 * Math.cos(a);
  const y = 10 * Math.sin(a);
  return [
    Math.round((32 + x * Math.cos(ROTACAO) - y * Math.sin(ROTACAO)) * 100) / 100,
    Math.round((32 + x * Math.sin(ROTACAO) + y * Math.cos(ROTACAO)) * 100) / 100,
  ];
});

export function Logo({ titulo = "Apogeu" }: { titulo?: string }) {
  return (
    <svg viewBox="0 0 64 64" role="img" aria-label={titulo}>
      <ellipse cx="32" cy="32" rx="25" ry="10" transform="rotate(-28 32 32)" fill="none" stroke="currentColor" strokeWidth="3" />
      <circle cx="32" cy="32" r="8" fill="currentColor" />
      {SATELITES.map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="4.5" fill="currentColor" />
      ))}
    </svg>
  );
}
