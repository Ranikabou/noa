const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function createProject(name: string, ownerId: string): Promise<{ id: string }> {
  const res = await fetch(
    `${API_URL}/v1/projects?name=${encodeURIComponent(name)}&owner_id=${encodeURIComponent(ownerId)}`,
    { method: 'POST' }
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getProject(id: string) {
  const res = await fetch(`${API_URL}/v1/projects/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listProjects() {
  const res = await fetch(`${API_URL}/v1/projects`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadFloorplan(projectId: string, file: File): Promise<unknown> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/floorplan`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function projectStatusSSEUrl(projectId: string): string {
  return `${API_URL}/v1/projects/${projectId}/status`;
}

export function assetUrl(storageKey: string): string {
  return `${API_URL}/v1/assets/${storageKey}`;
}

export async function getFloorplanAsset(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/floorplan`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}

export async function triggerParse(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/parse`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getParsedPlan(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/parsed-plan`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}

export async function listBoards(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/boards`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createBoard(projectId: string, name = 'My Board') {
  const res = await fetch(
    `${API_URL}/v1/projects/${projectId}/boards?name=${encodeURIComponent(name)}`,
    { method: 'POST' }
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadInspirationItem(projectId: string, boardId: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(
    `${API_URL}/v1/projects/${projectId}/boards/${boardId}/items`,
    { method: 'POST', body: form }
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listBoardItems(projectId: string, boardId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/boards/${boardId}/items`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function triggerStyleInference(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/style/infer`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStyleProfile(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/style`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}

export async function triggerGeometryRules(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/geometry-rules/generate`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function triggerBuild(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/build`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getModel(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/model`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}

export async function listExports(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/exports`);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(await res.text());
  }
  return res.json();
}

export async function getGeometryRules(projectId: string) {
  const res = await fetch(`${API_URL}/v1/projects/${projectId}/geometry-rules`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}
