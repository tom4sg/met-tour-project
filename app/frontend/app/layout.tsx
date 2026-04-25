import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MET Collection Search",
  description:
    "Search over 44,000 works of art from The Metropolitan Museum of Art using text, image, or both.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {/* Header */}
        <header className="sticky top-0 z-50 w-full bg-met-charcoal px-4 py-3 md:px-8 md:py-4 flex items-center justify-between">
          <div>
            <p className="font-serif text-white text-sm md:text-base leading-tight">
              The Metropolitan Museum of Art
            </p>
            <p className="text-met-gold text-xs tracking-widest uppercase mt-0.5">
              Collection Search
            </p>
          </div>

          {/* Decorative "M" monogram */}
          <span
            className="font-serif text-met-gold text-2xl md:text-3xl opacity-70 select-none"
            aria-hidden="true"
          >
            M
          </span>
        </header>

        {/* Main content */}
        <main className="min-h-screen bg-met-cream">{children}</main>

        {/* Footer */}
        <footer className="bg-met-charcoal py-4 text-center">
          <p className="text-met-cream/40 text-xs">
            &copy; The Metropolitan Museum of Art
          </p>
        </footer>
      </body>
    </html>
  );
}
