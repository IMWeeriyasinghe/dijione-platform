import { initials } from "../utils";

export function Avatar({
  name,
  color,
  size = 36,
}: {
  name: string;
  color?: string | null;
  size?: number;
}) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: color ?? "var(--dt-burnt-orange)",
      }}
      aria-hidden
    >
      {initials(name) || "?"}
    </div>
  );
}
