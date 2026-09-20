interface Props {
  state: 'draft';
}

export default function IntakeStageBadge({ state }: Props) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[#F0AB00]/40 bg-[#2B2414] px-2.5 py-1 text-xs font-semibold text-[#F8C95E]">
      <span className="h-1.5 w-1.5 rounded-full bg-[#F0AB00]" aria-hidden="true" />
      {state === 'draft' ? 'Draft' : state}
    </span>
  );
}
