import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // shadcn/ui semantic borderRadius derived from --radius (see index.css).
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      // Deliberate type system (see index.css for the CSS-var source of truth).
      // `font-sans` = Inter (UI/body), `font-serif` = Source Serif 4 (report + brand).
      fontFamily: {
        sans: ['Inter Variable', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        serif: ['Source Serif 4 Variable', 'Songti SC', 'SimSun', 'Georgia', 'serif'],
        // Monospace for display metric numerals (Bloomberg-style tabular numbers).
        mono: ['JetBrains Mono Variable', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      // QA Replay "upgrade reveal": ~1s scale + glow as the badge flips
      // Weak → Strong when pass-2 completes.
      keyframes: {
        upgrade: {
          '0%': { transform: 'scale(1)' },
          '40%': { transform: 'scale(1.25)' },
          '100%': { transform: 'scale(1)' },
        },
        // Credibility "真闭环确认" seal: a one-shot calm green glow (strong-evidence
        // token #2e9e5a) that settles into a thin ring — reads as "this passed QA".
        loopSeal: {
          '0%': { boxShadow: '0 0 0 0 rgb(46 158 90 / 0)' },
          '40%': { boxShadow: '0 0 0 3px rgb(46 158 90 / 0.28), 0 6px 22px -4px rgb(46 158 90 / 0.40)' },
          '100%': { boxShadow: '0 0 0 1px rgb(46 158 90 / 0.5), 0 4px 18px -4px rgb(46 158 90 / 0.30)' },
        },
        // ShineBorder: a slow background-position drift for a restrained shimmering
        // border. Applied via `motion-safe:animate-shine` so it is automatically
        // disabled under prefers-reduced-motion. RESERVED for the credibility hero.
        shine: {
          '0%': { backgroundPosition: '0% 0%' },
          '50%': { backgroundPosition: '100% 100%' },
          '100%': { backgroundPosition: '0% 0%' },
        },
      },
      animation: {
        upgrade: 'upgrade 1s ease-out',
        loopSeal: 'loopSeal 1.1s ease-out',
        shine: 'shine var(--duration, 14s) infinite linear',
      },
      colors: {
        // shadcn/ui semantic palette — consumes the RGB-channel CSS vars from
        // index.css. `<alpha-value>` lets opacity modifiers (bg-primary/90) work.
        border: 'rgb(var(--border) / <alpha-value>)',
        input: 'rgb(var(--input) / <alpha-value>)',
        ring: 'rgb(var(--ring) / <alpha-value>)',
        background: 'rgb(var(--background) / <alpha-value>)',
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--primary) / <alpha-value>)',
          foreground: 'rgb(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--secondary) / <alpha-value>)',
          foreground: 'rgb(var(--secondary-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'rgb(var(--destructive) / <alpha-value>)',
          foreground: 'rgb(var(--destructive-foreground) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'rgb(var(--muted) / <alpha-value>)',
          foreground: 'rgb(var(--muted-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          foreground: 'rgb(var(--accent-foreground) / <alpha-value>)',
        },
        popover: {
          DEFAULT: 'rgb(var(--popover) / <alpha-value>)',
          foreground: 'rgb(var(--popover-foreground) / <alpha-value>)',
        },
        card: {
          DEFAULT: 'rgb(var(--card) / <alpha-value>)',
          foreground: 'rgb(var(--card-foreground) / <alpha-value>)',
        },
        // Brand neutral scale — warm-cool "ink", replaces default Tailwind gray
        // in the app shell. Text uses ink-900; borders ink-200; surfaces ink-50.
        // Dark-intelligence INVERTED ink scale: ink-50 = near-black canvas …
        // ink-900 = near-white text. The app uses ink semantically (50=surface,
        // 900=text), so inverting the hex values flips the whole UI to dark with
        // no component edits. See docs/DESIGN.md.
        ink: {
          50: '#0a0e10',
          100: '#11171a',
          200: '#1b2329',
          300: '#2a343b',
          400: '#8b969c',
          500: '#a0acb2',
          600: '#a7b4ba',
          700: '#c5cfd4',
          800: '#dfe6e9',
          900: '#f1f5f6',
        },
        // Data accent — reserved for the credibility hero (+43% repair_delta / 真闭环)
        // and improvement/gain data. NOT a general UI color.
        lime: {
          400: '#a3e635',
          500: '#84cc16',
          600: '#65a30d',
        },
        // Brand accent — "mirror" teal. Primary action = mirror-600.
        // Replaces the default indigo-600 AI-slop signature.
        // Teal accent ramp for dark: 50/100 are now DARK teal SURFACE tints (used
        // as bg-mirror-50 accent bands / active nav); 300/400 are the BRIGHT
        // text/icon shades that pop on dark. 600/700 kept for borders/mid use.
        mirror: {
          50: '#0f2422',
          100: '#15302d',
          200: '#1c4543',
          300: '#71bbb6',
          400: '#449a96',
          500: '#2d807c',
          600: '#3f9692',
          700: '#a6d7d3',
          800: '#c9e6e3',
          900: '#e6f4f2',
        },
        // Shared semantic palette used across Badge, SourceProvenanceTag, etc.
        // Calm, accessible scheme — no semantic overloading of red.
        // Strength palette retuned for the dark canvas: deep-tint bg, high-luminance
        // text, visible border. Never red-for-weak (honest scheme preserved).
        strong: {
          bg: '#11271b',
          text: '#5fd08a',
          border: '#2e9e5a',
        },
        moderate: {
          bg: '#16182e',
          text: '#9aa0ee',
          border: '#6060b8',
        },
        weak: {
          bg: '#241f10',
          text: '#d9c06a',
          border: '#b89830',
        },
        live: {
          bg: '#11271b',
          text: '#5fd08a',
        },
        cached: {
          bg: '#1b2329',
          text: '#a7b4ba',
        },
      },
      // Elevation system — soft ink-tinted shadows. Use instead of border-everywhere
      // so surfaces read as layered, not as a wireframe.
      boxShadow: {
        xs: '0 1px 2px 0 rgb(22 27 28 / 0.04)',
        sm: '0 1px 3px 0 rgb(22 27 28 / 0.06), 0 1px 2px -1px rgb(22 27 28 / 0.05)',
        DEFAULT: '0 2px 6px -1px rgb(22 27 28 / 0.08), 0 1px 3px -1px rgb(22 27 28 / 0.06)',
        md: '0 4px 12px -2px rgb(22 27 28 / 0.10), 0 2px 6px -2px rgb(22 27 28 / 0.06)',
        lg: '0 12px 28px -6px rgb(22 27 28 / 0.14), 0 4px 10px -4px rgb(22 27 28 / 0.08)',
        card: '0 1px 3px 0 rgb(22 27 28 / 0.06), 0 1px 2px -1px rgb(22 27 28 / 0.05)',
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
