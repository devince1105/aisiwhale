import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "default" | "subtle" | "danger";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-ink hover:opacity-90",
  default: "border border-line bg-surface hover:bg-canvas",
  subtle: "text-muted hover:bg-canvas hover:text-ink",
  danger: "border border-danger-line bg-danger-soft text-danger hover:border-danger",
};

/** The back office's button look, for a <button> or a link that acts like one. */
export function buttonClass(variant: ButtonVariant = "default", size: "sm" | "md" = "md"): string {
  const box = size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1.5 text-sm";
  return `inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 ${box} ${VARIANT[variant]}`;
}

export function Button({
  variant = "default",
  size = "md",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm" | "md" }) {
  return <button type={type} className={`${buttonClass(variant, size)} ${className}`} {...props} />;
}
