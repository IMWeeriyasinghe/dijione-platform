import { Cake, LayoutGrid, Sparkles, Users } from "lucide-react";

export function ModuleIcon({ iconKey, className }: { iconKey: string; className?: string }) {
  switch (iconKey) {
    case "Users":
      return <Users className={className} />;
    case "Cake":
      return <Cake className={className} />;
    case "Sparkles":
      return <Sparkles className={className} />;
    default:
      return <LayoutGrid className={className} />;
  }
}
