export default function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center w-full py-16 gap-4">
      <div className="relative w-12 h-12">
        <div className="absolute inset-0 rounded-full border-4 border-met-gold/20" />
        <div className="absolute inset-0 rounded-full border-4 border-t-met-gold animate-spin" />
      </div>
      <p className="text-met-charcoal/70 text-sm tracking-wide">
        Searching the collection…
      </p>
    </div>
  );
}
