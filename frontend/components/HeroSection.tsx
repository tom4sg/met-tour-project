export default function HeroSection() {
  return (
    <section className="w-full bg-met-cream bg-gradient-to-b from-met-cream to-met-cream/80 px-4 py-12 md:py-20">
      <div className="max-w-3xl mx-auto text-center">
        <p className="text-met-gold text-sm font-semibold uppercase tracking-widest mb-3">
          The Metropolitan Museum of Art
        </p>

        <h1 className="font-serif text-4xl md:text-5xl text-met-charcoal mb-5 leading-tight">
          Explore 44,000 Works of Art
        </h1>

        <p className="text-met-charcoal/70 text-base md:text-lg mb-10 max-w-xl mx-auto">
          Describe what moves you: a mood, a period, a subject. Discover
          matching works from the permanent collection, then plan your walk
          through the galleries.
        </p>

        {/* Gold divider */}
        <div className="w-24 h-0.5 bg-met-gold mx-auto mb-10" />

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-xl mx-auto">
          <div className="bg-white/60 border border-met-gold/50 rounded-lg px-6 py-6 text-center">
            <span className="text-3xl mb-3 block">📝</span>
            <h3 className="font-serif text-met-charcoal font-semibold mb-1">
              Semantic Search
            </h3>
            <p className="text-met-charcoal/60 text-sm">
              Describe what you&apos;re looking for in your own words
            </p>
          </div>

          <div className="bg-white/60 border border-met-gold/50 rounded-lg px-6 py-6 text-center">
            <span className="text-3xl mb-3 block">🗺️</span>
            <h3 className="font-serif text-met-charcoal font-semibold mb-1">
              Gallery Tour
            </h3>
            <p className="text-met-charcoal/60 text-sm">
              Optimised walking route through your results, floor by floor
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
