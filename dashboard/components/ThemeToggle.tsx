"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";
const ORDER: Theme[] = ["system", "light", "dark"];
const KEY = "loop-theme";

function apply(theme: Theme) {
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
}

/** Cycles system → light → dark. The choice is a per-viewer convenience only. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY) as Theme | null;
      if (saved && ORDER.includes(saved)) {
        setTheme(saved);
        apply(saved);
      }
    } catch {
      /* storage may be unavailable (private mode); the default still works */
    }
  }, []);

  function next() {
    const value = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length] as Theme;
    setTheme(value);
    apply(value);
    try {
      localStorage.setItem(KEY, value);
    } catch {
      /* ignore */
    }
  }

  return (
    <button type="button" className="theme-toggle" onClick={next} aria-label={`Theme: ${theme}. Change theme`}>
      Theme: {theme}
    </button>
  );
}
