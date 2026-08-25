import { useSearchParams } from 'react-router-dom';
import LabRequestForm from './LabRequestForm';
import WorkshopOrderForm from './WorkshopOrderForm';

export default function EnvironmentRequest() {
  const [searchParams, setSearchParams] = useSearchParams();
  const workshopMode = searchParams.get('type') === 'workshop';

  const selectMode = (type: 'individual' | 'workshop') => {
    const next = new URLSearchParams(searchParams);
    if (type === 'workshop') next.set('type', 'workshop');
    else next.delete('type');
    setSearchParams(next);
  };

  return <div className="mx-auto max-w-2xl px-4 py-10">
    <h1 className="text-3xl font-bold text-white">Request an Environment</h1>
    <p className="mt-2 text-[#8A8D90]">Choose an individual lab or one multi-seat workshop order.</p>

    <div className="my-8 grid grid-cols-2 rounded-md border border-[#333] bg-[#212121] p-1" role="tablist" aria-label="Environment type">
      <button role="tab" aria-selected={!workshopMode} onClick={() => selectMode('individual')} className={`rounded px-4 py-3 text-sm font-semibold transition ${!workshopMode ? 'bg-[#0071C5] text-white' : 'text-[#B8BBBE] hover:bg-white/5 hover:text-white'}`}>
        Individual Lab
        <span className="mt-1 block text-xs font-normal opacity-75">One person · one environment</span>
      </button>
      <button role="tab" aria-selected={workshopMode} onClick={() => selectMode('workshop')} className={`rounded px-4 py-3 text-sm font-semibold transition ${workshopMode ? 'bg-[#0071C5] text-white' : 'text-[#B8BBBE] hover:bg-white/5 hover:text-white'}`}>
        Multi-seat Workshop
        <span className="mt-1 block text-xs font-normal opacity-75">One order · up to 25 seats</span>
      </button>
    </div>

    {workshopMode ? <WorkshopOrderForm embedded /> : <LabRequestForm embedded />}
  </div>;
}
