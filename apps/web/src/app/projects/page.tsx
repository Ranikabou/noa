'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { listProjects } from '@/lib/api';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Array<{ id: string; name: string; status: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-zinc-400">Loading…</div>;
  if (error) return <div className="p-8 text-red-400">{error}</div>;

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-semibold text-zinc-100 mb-6">Projects</h1>
        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.id}>
              <Link
                href={`/projects/${p.id}`}
                className="block px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-indigo-500/50 transition-colors"
              >
                <span className="text-zinc-100">{p.name}</span>
                <span className="ml-2 text-xs text-zinc-500">{p.status}</span>
              </Link>
            </li>
          ))}
        </ul>
        {projects.length === 0 && (
          <p className="text-zinc-500">No projects yet. Create one from the home page.</p>
        )}
        <Link href="/" className="mt-6 inline-block text-indigo-400 hover:text-indigo-300 text-sm">
          ← Back
        </Link>
      </div>
    </main>
  );
}
