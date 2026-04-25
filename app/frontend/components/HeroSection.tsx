const features = [
  {
    icon: "📝",
    title: "Search by Text",
    description: "Describe what you're looking for",
  },
  {
    icon: "🖼️",
    title: "Search by Image",
    description: "Upload a photo to find similar works",
  },
  {
    icon: "✨",
    title: "Search by Both",
    description: "Combine text and image for precision",
  },
];

export default function HeroSection() {
  return (
    <section className="w-full bg-met-cream bg-gradient-to-b from-met-cream to-met-cream/80 px-4 py-12 md:py-20">
      <div className="max-w-3xl mx-auto text-center">
        <h1 className="font-serif text-4xl md:text-5xl text-met-charcoal mb-4">
          Explore the Collection
        </h1>

        <p className="text-met-charcoal/70 text-base md:text-lg mb-8 max-w-xl mx-auto">
          Search over 44,000 works of art from The Metropolitan Museum of Art
          using text, image, or both.
        </p>

        {/* Gold divider */}
        <div className="w-24 h-0.5 bg-met-gold mx-auto mb-10" />

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {features.map((f) => (
            <div
              key={f.title}
              className="bg-met-cream border border-met-gold rounded-lg px-5 py-6 text-center"
            >
              <span className="text-3xl mb-3 block">{f.icon}</span>
              <h3 className="font-serif text-met-charcoal font-semibold mb-1">
                {f.title}
              </h3>
              <p className="text-met-charcoal/60 text-sm">{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
