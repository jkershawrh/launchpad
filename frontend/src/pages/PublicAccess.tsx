import { useState } from 'react';
import { api } from '../api/client';

export default function PublicAccess() {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState<{seat_ref:string; public_url:string}|null>(null);
  const orderId = new URLSearchParams(window.location.search).get('order') || '';
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError('');
    try { setResult(await api.claimPublicAccess({order_id:orderId, email, code})); }
    catch { setError('Access request cannot be completed. Check the link and instructor code.'); }
  };
  return <main className="min-h-screen bg-[#151515] px-5 py-16 text-white"><div className="mx-auto max-w-md rounded-lg border border-[#333] bg-[#212121] p-8"><h1 className="text-2xl font-bold">Join your lab</h1><p className="mt-2 text-sm text-[#B8BBBE]">Use the email label and code supplied by your instructor. Email ownership is not verified.</p>{error && <p className="mt-5 rounded bg-red-950 p-3 text-sm text-red-200">{error}</p>}{result ? <div className="mt-6"><p className="text-green-300">Seat {result.seat_ref} is ready.</p><a className="mt-4 block rounded bg-[#EE0000] px-4 py-3 text-center font-semibold" href={result.public_url}>Open participant home</a></div> : <form className="mt-6 space-y-5" onSubmit={submit}><label className="block text-sm">Email<input className="mt-1 w-full rounded border border-[#777] bg-[#151515] px-3 py-2" type="email" required value={email} onChange={(e)=>setEmail(e.target.value)}/></label><label className="block text-sm">Instructor code<input className="mt-1 w-full rounded border border-[#777] bg-[#151515] px-3 py-2 font-mono uppercase" required value={code} onChange={(e)=>setCode(e.target.value)}/></label><button className="w-full rounded bg-[#EE0000] px-4 py-3 font-semibold">Join lab</button></form>}</div></main>;
}
