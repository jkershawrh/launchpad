import { Link, useSearchParams } from 'react-router-dom';
import { useBranding } from '../context/BrandingContext';

const EXPERIENCES = [
  {
    title: 'Quick Start Labs',
    description: 'Prebuilt, guided, fast-start demos. Get up and running in minutes with proven AI workloads on Intel hardware.',
    category: 'quick_start',
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    title: 'Guided Build Areas',
    description: 'Template-driven build spaces for AI ideas. Follow guided paths to create RAG apps, fine-tune models, and more.',
    category: 'guided_build',
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
      </svg>
    ),
  },
  {
    title: 'Open Sandboxes',
    description: 'Flexible partner namespaces with quotas, tools, and observability. Experiment freely with full hardware access.',
    category: 'open_sandbox',
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
];

export default function Home() {
  const { profile } = useBranding();
  const [searchParams] = useSearchParams();

  const primaryColor = profile?.primary_color || '#EE0000';
  const secondaryColor = profile?.secondary_color || '#0071C5';
  const headerBg = (profile?.metadata?.header_bg as string) || '#151515';
  const title = profile?.title || 'Partner AI Launchpad';
  const logoRefs = profile?.logo_refs || ['/logos/redhat.png', '/logos/intel.png'];

  const brandParam = searchParams.get('brand');
  const brandQuery = brandParam ? `?brand=${brandParam}` : '';

  const cardColors = [primaryColor, secondaryColor, '#3E8635'];

  return (
    <div>
      <section style={{ backgroundColor: headerBg }} className="text-white py-24 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="flex justify-center items-center gap-6 mb-8">
            {logoRefs.map((logo, i) => (
              <span key={i} className="flex items-center gap-6">
                {i > 0 && <span className="text-white text-2xl font-bold mx-3">X</span>}
                <img src={logo} alt="" style={{ height: i === 0 ? '48px' : '36px', width: 'auto' }} />
              </span>
            ))}
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold mb-5 tracking-tight">
            {title}
          </h1>
          <p className="text-lg text-gray-300 max-w-2xl mx-auto leading-relaxed">
            Reusable AI demo environments, guided labs, and open sandboxes for partners and clients.
          </p>
          <Link
            to={`/demos${brandQuery}`}
            style={{ backgroundColor: primaryColor }}
            className="inline-block mt-8 px-6 py-3 text-white rounded font-medium hover:opacity-90 transition-opacity"
          >
            Explore Demos
          </Link>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16">
        <h2 className="text-2xl font-semibold text-center mb-3 text-[#151515]">
          Choose Your Experience
        </h2>
        <p className="text-center text-[#6A6E73] mb-12">
          Three ways to get started with AI on Red Hat OpenShift and Intel hardware.
        </p>
        <div className="grid md:grid-cols-3 gap-6">
          {EXPERIENCES.map((exp, i) => (
            <Link
              key={exp.category}
              to={exp.category === 'open_sandbox' ? `/sandbox${brandQuery}` : `/demos${brandQuery}`}
              className="block bg-white rounded border border-[#D2D2D2] border-t-4 p-8 hover:shadow-md transition-shadow"
              style={{ borderTopColor: cardColors[i] }}
            >
              <div className="mb-5" style={{ color: cardColors[i] }}>{exp.icon}</div>
              <h3 className="text-lg font-semibold text-[#151515] mb-3">{exp.title}</h3>
              <p className="text-[#6A6E73] text-sm leading-relaxed">{exp.description}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="bg-white border-t border-[#D2D2D2] py-14 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-xl font-semibold text-[#151515] mb-4">Repeatable Process</h2>
          <p className="text-[#6A6E73] mb-8">
            Every lab follows the same lifecycle — no hand-built snowflakes.
          </p>
          <div className="flex justify-center gap-2 text-xs sm:text-sm overflow-x-auto">
            {['Request', 'Provision', 'Validate', 'Ready', 'Active', 'Observe', 'Report', 'Reclaim'].map(
              (step, i) => (
                <div key={step} className="flex items-center gap-2 shrink-0">
                  <span className="bg-[#F0F0F0] border border-[#D2D2D2] px-3 py-1.5 rounded text-[#151515] font-medium whitespace-nowrap">
                    {step}
                  </span>
                  {i < 7 && <span className="text-[#6A6E73]">{"→"}</span>}
                </div>
              )
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
