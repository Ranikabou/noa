'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { createProject } from '@/lib/api';

const DEV_OWNER_ID = '00000000-0000-0000-0000-000000000001';

export default function Home() {
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const project = await createProject(name || 'Untitled', DEV_OWNER_ID);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="max-w-md w-full">
        <h1 className="text-3xl font-semibold text-zinc-100 mb-2">NOA AI</h1>
        <p className="text-zinc-400 mb-8">Floorplan-to-3D Architectural Intelligence</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm text-zinc-400 mb-1">
              Project name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My floorplan project"
              className="w-full px-4 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium disabled:opacity-50"
          >
            {loading ? 'Creating…' : 'Create project'}
          </button>
        </form>

        <Link
          href="/projects"
          className="mt-6 block text-center text-sm text-indigo-400 hover:text-indigo-300"
        >
          View all projects →
        </Link>
      </div>
    </main>
  );
}
