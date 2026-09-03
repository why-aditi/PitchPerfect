"use client";

import { useEffect, useState } from "react";
import { cx } from "./ui";

const KEY = "pp-theme";

type Theme = "light" | "dark";

/**
 * Runs before hydration so the first paint is already in the chosen theme. Without it a
 * dark-preferring operator sees a white flash on every navigation. Only a stored choice is
 * stamped; with none, globals.css follows the system preference on its own.
 */
export function ThemeScript() {
  const code = `(function(){try{var t=localStorage.getItem(${JSON.stringify(KEY)});if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}})();`;
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}

function current(): Theme {
  const stamped = document.documentElement.getAttribute("data-theme");
  if (stamped === "light" || stamped === "dark") return stamped;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle({ className }: { className?: string }) {
  // Unknown until mounted: the server cannot know the preference, and guessing would
  // render the wrong icon for a frame.
  const [theme, setTheme] = useState<Theme | null>(null);

  // Read once after mount, in a microtask, so hydration renders the same blank knob the
  // server did and the real icon fills in a frame later.
  useEffect(() => {
    const id = requestAnimationFrame(() => setTheme(current()));
    return () => cancelAnimationFrame(id);
  }, []);

  function flip() {
    const next: Theme = current() === "dark" ? "light" : "dark";
    const root = document.documentElement;
    // Suppress every transition for one frame so the whole page flips at once.
    root.classList.add("theme-switching");
    root.setAttribute("data-theme", next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* private mode; the choice lasts for this page only */
    }
    requestAnimationFrame(() => root.classList.remove("theme-switching"));
    setTheme(next);
  }

  const dark = theme === "dark";

  return (
    <button
      type="button"
      onClick={flip}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Light theme" : "Dark theme"}
      className={cx(
        "relative inline-flex h-8 w-14 shrink-0 items-center rounded-full border border-line bg-raised",
        "transition-colors hover:border-brand/50",
        className,
      )}
    >
      <span
        aria-hidden
        className={cx(
          "absolute top-0.5 flex h-[26px] w-[26px] items-center justify-center rounded-full bg-panel text-ink shadow-sm",
          "transition-[left] duration-200 ease-out",
          theme === null ? "opacity-0" : dark ? "left-[26px]" : "left-0.5",
        )}
      >
        {dark ? <Moon /> : <Sun />}
      </span>
    </button>
  );
}

function Sun() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
    </svg>
  );
}

function Moon() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
      <path d="M13.5 9.8A5.5 5.5 0 0 1 6.2 2.5a5.5 5.5 0 1 0 7.3 7.3Z" />
    </svg>
  );
}
