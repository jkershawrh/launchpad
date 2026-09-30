const stages = [
  {
    name: 'Show',
    command: 'launchpad-guided-start show',
    detail: 'See the mission and the environment prepared for this seat.',
  },
  {
    name: 'Learn',
    command: 'launchpad-guided-start learn',
    detail: 'Prove you can edit only your assigned OpenShift namespace.',
  },
  {
    name: 'Do',
    command: 'launchpad-guided-start do',
    detail: 'Deploy and inspect one small, private web workload.',
  },
  {
    name: 'Prove',
    command: 'launchpad-guided-start prove',
    detail: 'Make one live model completion when available and save evidence.',
  },
  {
    name: 'Clean up',
    command: 'launchpad-guided-start cleanup',
    detail: 'Remove the guided workload and prove no created resources remain.',
  },
];

export default function SandboxGuidedStart() {
  return (
    <section aria-labelledby="sandbox-guided-start-title" className="bg-[#1E1E1E] rounded-lg border border-[#3C3F42] p-5 mb-5">
      <p className="text-xs uppercase tracking-[0.16em] text-cyan-300 font-bold">Optional guided start</p>
      <h3 id="sandbox-guided-start-title" className="text-xl font-semibold text-white mt-2">
        Your first governed AI workload
      </h3>
      <p className="text-sm text-[#c7c7c7] mt-2 max-w-3xl">
        Prove your namespace boundary, deploy one tiny workload, call the shared Intel CPU model when it is available,
        capture evidence, and clean up. Your open sandbox stays open for exploration after this path.
      </p>
      <div className="grid md:grid-cols-5 gap-2 mt-4">
        {stages.map((stage) => (
          <div key={stage.name} className="rounded border border-[#3C3F42] bg-[#151515] p-3">
            <div className="text-sm font-semibold text-white">{stage.name}</div>
            <p className="text-xs text-[#9ca3af] mt-1 min-h-12">{stage.detail}</p>
            <code className="block text-[11px] text-green-400 font-mono mt-2 break-all">{stage.command}</code>
          </div>
        ))}
      </div>
      <p className="text-xs text-[#9ca3af] mt-3">
        The complete instructions are in <code className="text-white">GETTING_STARTED.md</code>. Evidence is saved to{' '}
        <code className="text-white">guided-start-proof.json</code>; credentials are never included.
      </p>
    </section>
  );
}
