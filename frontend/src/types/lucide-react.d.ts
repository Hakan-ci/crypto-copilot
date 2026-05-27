declare module "lucide-react" {
  import type {
    ForwardRefExoticComponent,
    RefAttributes,
    SVGProps
  } from "react";

  export interface LucideProps extends SVGProps<SVGSVGElement> {
    size?: string | number;
    absoluteStrokeWidth?: boolean;
  }

  export type LucideIcon = ForwardRefExoticComponent<
    Omit<LucideProps, "ref"> & RefAttributes<SVGSVGElement>
  >;

  export const Activity: LucideIcon;
  export const AlertTriangle: LucideIcon;
  export const ArrowDown: LucideIcon;
  export const ArrowUp: LucideIcon;
  export const BadgeDollarSign: LucideIcon;
  export const BarChart3: LucideIcon;
  export const BookOpenCheck: LucideIcon;
  export const Cable: LucideIcon;
  export const Check: LucideIcon;
  export const CheckCircle2: LucideIcon;
  export const CircleDollarSign: LucideIcon;
  export const ClipboardCheck: LucideIcon;
  export const Download: LucideIcon;
  export const HelpCircle: LucideIcon;
  export const ListChecks: LucideIcon;
  export const Percent: LucideIcon;
  export const Plus: LucideIcon;
  export const ReceiptText: LucideIcon;
  export const RefreshCw: LucideIcon;
  export const Save: LucideIcon;
  export const Settings: LucideIcon;
  export const ShieldCheck: LucideIcon;
  export const Sparkles: LucideIcon;
  export const TrendingDown: LucideIcon;
  export const TrendingUp: LucideIcon;
  export const Trash2: LucideIcon;
  export const XCircle: LucideIcon;
}
