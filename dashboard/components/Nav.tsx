"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Nav({ markets }: { markets: { id: string; label: string }[] }) {
  const path = usePathname();
  const links = [{ href: "/", label: "Overview" }, ...markets.map((m) => ({ href: `/markets/${m.id}`, label: m.label })), { href: "/data", label: "Data" }];
  return (
    <nav className="nav" aria-label="Main">
      {links.map((l) => (
        <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
