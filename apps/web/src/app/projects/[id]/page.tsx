'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  getProject,
  uploadFloorplan,
  projectStatusSSEUrl,
  getParsedPlan,
  triggerParse,
  createBoard,
  listBoards,
  uploadInspirationItem,
  listBoardItems,
  getStyleProfile,
  triggerStyleInference,
  getGeometryRules,
  triggerGeometryRules,
  getFloorplanAsset,
  assetUrl,
  triggerBuild,
  getModel,
  listExports,
} from '@/lib/api';
import Script from 'next/script';

type JobEvent = {
  event: string;
  data: {
    job_id?: string;
    job_type?: string;
    status?: string;
    progress?: number;
    stage?: string;
    error?: { message: string };
    result_ref?: string;
  };
};

type ParsedPlan = {
  id: string;
  status: string;
  confidence_overall: number;
  walls: { id: string; geometry: number[][]; confidence: number }[];
  openings: { id: string; geometry: number[][]; confidence: number }[];
  rooms: { id: string; geometry: number[][]; confidence: number; label?: string }[];
  bounding_box_px: { min_x: number; min_y: number; max_x: number; max_y: number };
  ambiguity_flags: { id: string; description: string }[];
};

type Board = {
  id: string;
  name: string;
  item_count: number;
  is_primary: boolean;
};

type BoardItem = {
  id: string;
  storage_key: string | null;
  upload_status: string;
};

type MaterialEntry = {
  name: string;
  category?: string;
  finish?: string;
  color_hex?: string;
  usage?: string;
};

type StyleProfileData = {
  id: string;
  style_signals: {
    massing_tendency: string;
    facade_rhythm: string;
    material_palette: MaterialEntry[];
    lighting_mood: string;
    surface_language: string;
    compositional_balance: string;
    emotional_tone: string[];
    negative_preferences: string[];
    roof_tendency: string;
    glazing_ratio: number;
    overhang_tendency: string;
  };
  confidence_per_signal: Record<string, number>;
};

type GeometryRule = {
  rule_type: string;
  [key: string]: unknown;
};

type GeometryRuleSetData = {
  id: string;
  confidence_overall: number;
  rules: GeometryRule[];
};

const ROOM_COLORS = [
  'rgba(99, 102, 241, 0.25)',
  'rgba(168, 85, 247, 0.25)',
  'rgba(236, 72, 153, 0.25)',
  'rgba(34, 211, 238, 0.25)',
  'rgba(74, 222, 128, 0.25)',
  'rgba(251, 191, 36, 0.25)',
  'rgba(248, 113, 113, 0.25)',
  'rgba(96, 165, 250, 0.25)',
];

export default function ProjectPage() {
  const params = useParams();
  const projectId = params.id as string;
  const [project, setProject] = useState<{
    id: string;
    name: string;
    status: string;
    floorplan_asset_id?: string | null;
    inspiration_board_id?: string | null;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [parsedPlan, setParsedPlan] = useState<ParsedPlan | null>(null);
  const [parsing, setParsing] = useState(false);

  // Inspiration state
  const [boards, setBoards] = useState<Board[]>([]);
  const [activeBoard, setActiveBoard] = useState<Board | null>(null);
  const [boardItems, setBoardItems] = useState<BoardItem[]>([]);
  const [uploadingInspiration, setUploadingInspiration] = useState(false);

  // Style + Geometry state
  const [styleProfile, setStyleProfile] = useState<StyleProfileData | null>(null);
  const [inferringStyle, setInferringStyle] = useState(false);
  const [geometryRules, setGeometryRules] = useState<GeometryRuleSetData | null>(null);
  const [generatingRules, setGeneratingRules] = useState(false);

  // 3D Model + Exports
  const [modelData, setModelData] = useState<{ id: string; glb_storage_key: string | null; elements: any } | null>(null);
  const [exports, setExports] = useState<{ id: string; format: string; storage_key: string }[]>([]);
  const [building, setBuilding] = useState(false);
  const viewerRef = useRef<HTMLDivElement>(null);
  const threeInitRef = useRef(false);

  // Floorplan image
  const [floorplanStorageKey, setFloorplanStorageKey] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);

  const loadProject = useCallback(async () => {
    try {
      const p = await getProject(projectId);
      setProject(p);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project');
    }
  }, [projectId]);

  const loadFloorplanAsset = useCallback(async () => {
    try {
      const asset = await getFloorplanAsset(projectId);
      if (asset?.storage_key) setFloorplanStorageKey(asset.storage_key);
    } catch {
      // not uploaded yet
    }
  }, [projectId]);

  const loadParsedPlan = useCallback(async () => {
    try {
      const plan = await getParsedPlan(projectId);
      if (plan) setParsedPlan(plan);
    } catch {
      // 404 is fine — not parsed yet
    }
  }, [projectId]);

  const loadBoards = useCallback(async () => {
    try {
      const b = await listBoards(projectId);
      setBoards(b);
      if (b.length > 0 && !activeBoard) {
        setActiveBoard(b[0]);
      }
    } catch {
      // ignore
    }
  }, [projectId, activeBoard]);

  const loadBoardItems = useCallback(async () => {
    if (!activeBoard) return;
    try {
      const items = await listBoardItems(projectId, activeBoard.id);
      setBoardItems(items);
    } catch {
      // ignore
    }
  }, [projectId, activeBoard]);

  const loadStyleProfile = useCallback(async () => {
    try {
      const sp = await getStyleProfile(projectId);
      if (sp) setStyleProfile(sp);
    } catch {
      // not ready yet
    }
  }, [projectId]);

  const loadGeometryRules = useCallback(async () => {
    try {
      const gr = await getGeometryRules(projectId);
      if (gr) setGeometryRules(gr);
    } catch {
      // not ready yet
    }
  }, [projectId]);

  const loadModel = useCallback(async () => {
    try {
      const m = await getModel(projectId);
      if (m) setModelData(m);
    } catch {
      // not built yet
    }
  }, [projectId]);

  const loadExports = useCallback(async () => {
    try {
      const e = await listExports(projectId);
      if (e) setExports(e);
    } catch {
      // ignore
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
    loadFloorplanAsset();
    loadParsedPlan();
    loadBoards();
    loadStyleProfile();
    loadGeometryRules();
    loadModel();
    loadExports();
  }, [loadProject, loadFloorplanAsset, loadParsedPlan, loadBoards, loadStyleProfile, loadGeometryRules, loadModel, loadExports]);

  useEffect(() => {
    loadBoardItems();
  }, [loadBoardItems]);

  // SSE connection
  useEffect(() => {
    if (!projectId) return;
    const url = projectStatusSSEUrl(projectId);
    const es = new EventSource(url);

    es.onmessage = (e) => {
      try {
        const ev: JobEvent = JSON.parse(e.data);
        if (ev.event === 'job_update' && ev.data) {
          if (ev.data.progress != null) setProgress(ev.data.progress);
          if (ev.data.stage) setStage(ev.data.stage);

          if (ev.data.job_type === 'floorplan_parse') {
            if (ev.data.status === 'running') {
              setParsing(true);
              setStage(ev.data.stage || 'analyzing');
            }
            if (ev.data.status === 'complete') {
              setParsing(false);
              loadParsedPlan();
              loadProject();
            }
            if (ev.data.status === 'failed' && ev.data.error) {
              setParsing(false);
              setError(ev.data.error.message);
            }
          }

          if (ev.data.job_type === 'floorplan_upload' && ev.data.status === 'complete') {
            setUploading(false);
            loadProject();
          }

          if (ev.data.job_type === 'style_inference') {
            if (ev.data.status === 'running') {
              setInferringStyle(true);
            }
            if (ev.data.status === 'complete') {
              setInferringStyle(false);
              loadStyleProfile();
            }
            if (ev.data.status === 'failed') {
              setInferringStyle(false);
            }
          }

          if (ev.data.job_type === 'model_reconstruct') {
            if (ev.data.status === 'running') {
              setBuilding(true);
              setStage(ev.data.stage || 'building');
            }
            if (ev.data.status === 'complete') {
              setBuilding(false);
              loadModel();
              loadExports();
              loadProject();
            }
            if (ev.data.status === 'failed') {
              setBuilding(false);
            }
          }

          if (ev.data.job_type === 'geometry_rules') {
            if (ev.data.status === 'running') {
              setGeneratingRules(true);
            }
            if (ev.data.status === 'complete') {
              setGeneratingRules(false);
              loadGeometryRules();
            }
            if (ev.data.status === 'failed') {
              setGeneratingRules(false);
            }
          }

          if (ev.data.status === 'failed' && ev.data.error) {
            setError(ev.data.error.message);
            setUploading(false);
            setParsing(false);
          }
        }
      } catch {
        // heartbeat
      }
    };

    es.onerror = () => {
      es.close();
    };

    return () => es.close();
  }, [projectId, loadParsedPlan, loadProject, loadStyleProfile, loadGeometryRules, loadModel, loadExports]);

  // Draw parsed plan on canvas
  useEffect(() => {
    if (!parsedPlan || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { bounding_box_px: bbox } = parsedPlan;
    const planW = bbox.max_x - bbox.min_x || 800;
    const planH = bbox.max_y - bbox.min_y || 600;

    const maxCanvasW = 700;
    const scale = Math.min(maxCanvasW / planW, maxCanvasW / planH, 1);
    canvas.width = planW * scale;
    canvas.height = planH * scale;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#18181b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw rooms
    parsedPlan.rooms.forEach((room, i) => {
      if (!room.geometry || room.geometry.length < 3) return;
      ctx.fillStyle = ROOM_COLORS[i % ROOM_COLORS.length];
      ctx.strokeStyle = ROOM_COLORS[i % ROOM_COLORS.length].replace('0.25', '0.7');
      ctx.lineWidth = 1;
      ctx.beginPath();
      room.geometry.forEach(([x, y], j) => {
        const sx = (x - bbox.min_x) * scale;
        const sy = (y - bbox.min_y) * scale;
        j === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy);
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Room label
      if (room.geometry.length > 0) {
        const cx = room.geometry.reduce((s, [x]) => s + x, 0) / room.geometry.length;
        const cy = room.geometry.reduce((s, [, y]) => s + y, 0) / room.geometry.length;
        ctx.fillStyle = '#e4e4e7';
        ctx.font = `${Math.max(10, 12 * scale)}px system-ui`;
        ctx.textAlign = 'center';
        ctx.fillText(
          (room as any).label || `Room ${i + 1}`,
          (cx - bbox.min_x) * scale,
          (cy - bbox.min_y) * scale
        );
      }
    });

    // Draw walls
    ctx.strokeStyle = '#e4e4e7';
    ctx.lineWidth = Math.max(2, 3 * scale);
    parsedPlan.walls.forEach((wall) => {
      if (!wall.geometry || wall.geometry.length < 2) return;
      ctx.beginPath();
      wall.geometry.forEach(([x, y], j) => {
        const sx = (x - bbox.min_x) * scale;
        const sy = (y - bbox.min_y) * scale;
        j === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy);
      });
      ctx.stroke();
    });

    // Draw openings
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = Math.max(2, 2.5 * scale);
    ctx.setLineDash([4, 4]);
    parsedPlan.openings.forEach((opening) => {
      if (!opening.geometry || opening.geometry.length < 2) return;
      ctx.beginPath();
      opening.geometry.forEach(([x, y], j) => {
        const sx = (x - bbox.min_x) * scale;
        const sy = (y - bbox.min_y) * scale;
        j === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy);
      });
      if (opening.geometry.length > 2) ctx.closePath();
      ctx.stroke();
    });
    ctx.setLineDash([]);
  }, [parsedPlan]);

  async function handleFile(file: File) {
    setError(null);
    setUploading(true);
    setProgress(0);
    setStage('uploading');
    try {
      await uploadFloorplan(projectId, file);
      setStage('processing');
      await loadProject();
      await loadFloorplanAsset();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setUploading(false);
    }
  }

  async function handleReParse() {
    setError(null);
    setParsing(true);
    setStage('queuing parse');
    try {
      await triggerParse(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Parse failed');
      setParsing(false);
    }
  }

  async function handleCreateBoard() {
    try {
      const board = await createBoard(projectId);
      setBoards((prev) => [...prev, board]);
      setActiveBoard(board);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create board');
    }
  }

  async function handleInspirationUpload(file: File) {
    if (!activeBoard) return;
    setUploadingInspiration(true);
    try {
      await uploadInspirationItem(projectId, activeBoard.id, file);
      await loadBoardItems();
      await loadBoards();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploadingInspiration(false);
    }
  }

  async function handleTriggerStyle() {
    setError(null);
    setInferringStyle(true);
    try {
      await triggerStyleInference(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Style inference failed');
      setInferringStyle(false);
    }
  }

  async function handleTriggerGeometry() {
    setError(null);
    setGeneratingRules(true);
    try {
      await triggerGeometryRules(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Geometry rules failed');
      setGeneratingRules(false);
    }
  }

  async function handleBuild() {
    setError(null);
    setBuilding(true);
    try {
      await triggerBuild(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Build failed');
      setBuilding(false);
    }
  }

  // Three.js viewer initialization
  useEffect(() => {
    if (!modelData?.glb_storage_key || !viewerRef.current) return;
    const container = viewerRef.current;

    // Clear previous viewer on rebuild
    while (container.firstChild) container.removeChild(container.firstChild);
    threeInitRef.current = true;

    const glbUrl = assetUrl(modelData.glb_storage_key);

    import('three').then(async (THREE) => {
      const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js' as any);
      const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js' as any);

      const w = container.clientWidth;
      const h = 500;
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x1a1a2e);

      const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 1000);
      camera.position.set(20, 15, 20);

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(w, h);
      renderer.setPixelRatio(window.devicePixelRatio);
      renderer.shadowMap.enabled = true;
      container.appendChild(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.05;
      controls.target.set(0, 1.5, 0);

      // Lighting
      const ambient = new THREE.AmbientLight(0xffffff, 0.6);
      scene.add(ambient);
      const dir = new THREE.DirectionalLight(0xffffff, 1.0);
      dir.position.set(10, 20, 10);
      dir.castShadow = true;
      scene.add(dir);
      const fill = new THREE.DirectionalLight(0x8888ff, 0.3);
      fill.position.set(-10, 10, -10);
      scene.add(fill);

      // Grid
      const grid = new THREE.GridHelper(40, 40, 0x333366, 0x222244);
      scene.add(grid);

      // Load GLB
      const loader = new GLTFLoader();
      loader.load(glbUrl, (gltf: any) => {
        const model = gltf.scene;
        scene.add(model);

        const box = new THREE.Box3().setFromObject(model);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        camera.position.set(center.x + maxDim, center.y + maxDim * 0.8, center.z + maxDim);
        controls.target.copy(center);
        controls.update();
      });

      function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
      }
      animate();

      const onResize = () => {
        const nw = container.clientWidth;
        camera.aspect = nw / h;
        camera.updateProjectionMatrix();
        renderer.setSize(nw, h);
      };
      window.addEventListener('resize', onResize);
    });
  }, [modelData]);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && (f.type === 'application/pdf' || f.type.startsWith('image/'))) {
      handleFile(f);
    } else {
      setError('Please upload a PDF or image (JPEG, PNG, WebP)');
    }
  }

  if (!project) {
    return (
      <main className="min-h-screen p-8">
        {error ? (
          <p className="text-red-400">{error}</p>
        ) : (
          <p className="text-zinc-400">Loading…</p>
        )}
      </main>
    );
  }

  const showUpload = !project.floorplan_asset_id && !uploading;
  const showParsing = parsing || (project.floorplan_asset_id && !parsedPlan && !uploading);

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <Link
          href="/projects"
          className="text-sm text-indigo-400 hover:text-indigo-300 mb-4 block"
        >
          ← Projects
        </Link>
        <h1 className="text-2xl font-semibold text-zinc-100 mb-1">{project.name}</h1>
        <p className="text-zinc-500 text-sm mb-6">Status: {project.status}</p>

        {/* ── STEP 1: Upload ─────────────────── */}
        {(showUpload || uploading) && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-zinc-200 mb-3">1. Upload Floorplan</h2>
            <div
              onDrop={onDrop}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              className={`
                border-2 border-dashed rounded-xl p-12 text-center transition-colors
                ${dragOver ? 'border-indigo-500 bg-indigo-500/10' : 'border-zinc-700 bg-zinc-900/50'}
                ${uploading ? 'pointer-events-none opacity-80' : 'cursor-pointer'}
              `}
            >
              <input
                type="file"
                accept=".pdf,image/jpeg,image/png,image/webp"
                className="hidden"
                id="file-input"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                }}
              />
              <label htmlFor="file-input" className="cursor-pointer block">
                {uploading ? (
                  <>
                    <p className="text-zinc-300 mb-2">Processing…</p>
                    <div className="w-full max-w-xs mx-auto h-2 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 transition-all duration-300"
                        style={{ width: `${(progress ?? 0) * 100}%` }}
                      />
                    </div>
                    {stage && <p className="text-zinc-500 text-sm mt-2">{stage}</p>}
                  </>
                ) : (
                  <>
                    <p className="text-zinc-300 mb-1">Drop floorplan here or click to upload</p>
                    <p className="text-zinc-500 text-sm">PDF, JPEG, PNG, WebP — max 50MB</p>
                  </>
                )}
              </label>
            </div>
          </section>
        )}

        {/* ── Upload done badge + image ────── */}
        {project.floorplan_asset_id && !showUpload && !uploading && (
          <div className="mb-6">
            <div className="flex items-center gap-2 text-sm text-green-400 mb-3">
              <span>Floorplan uploaded</span>
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            {floorplanStorageKey && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-2 inline-block">
                <img
                  src={assetUrl(floorplanStorageKey)}
                  alt="Uploaded floorplan"
                  className="max-w-md max-h-64 rounded object-contain"
                />
              </div>
            )}
          </div>
        )}

        {/* ── STEP 2: Parsing Status / Results ─ */}
        {(showParsing || parsedPlan) && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-medium text-zinc-200">2. Parsed Floorplan</h2>
              {parsedPlan && (
                <button
                  onClick={handleReParse}
                  disabled={parsing}
                  className="text-sm text-indigo-400 hover:text-indigo-300 disabled:opacity-50"
                >
                  Re-parse
                </button>
              )}
            </div>

            {parsing && !parsedPlan && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-8 text-center">
                <div className="inline-block w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-zinc-300">Analyzing floorplan with AI…</p>
                {stage && <p className="text-zinc-500 text-sm mt-1">{stage}</p>}
              </div>
            )}

            {parsedPlan && (
              <div className="space-y-4">
                {/* Stats */}
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { label: 'Walls', value: parsedPlan.walls.length },
                    { label: 'Rooms', value: parsedPlan.rooms.length },
                    { label: 'Openings', value: parsedPlan.openings.length },
                    {
                      label: 'Confidence',
                      value: `${Math.round(parsedPlan.confidence_overall * 100)}%`,
                    },
                  ].map((stat) => (
                    <div
                      key={stat.label}
                      className="rounded-lg bg-zinc-800/80 border border-zinc-700 p-3 text-center"
                    >
                      <p className="text-xl font-semibold text-zinc-100">{stat.value}</p>
                      <p className="text-xs text-zinc-500">{stat.label}</p>
                    </div>
                  ))}
                </div>

                {/* Canvas visualization */}
                <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-4 overflow-auto">
                  <canvas ref={canvasRef} className="mx-auto rounded" />
                </div>

                {/* Room list */}
                {parsedPlan.rooms.length > 0 && (
                  <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-4">
                    <h3 className="text-sm font-medium text-zinc-300 mb-2">Detected Rooms</h3>
                    <div className="flex flex-wrap gap-2">
                      {parsedPlan.rooms.map((room, i) => (
                        <span
                          key={room.id}
                          className="px-2 py-1 rounded text-xs text-zinc-200 border border-zinc-600"
                          style={{
                            backgroundColor: ROOM_COLORS[i % ROOM_COLORS.length],
                          }}
                        >
                          {(room as any).label || `Room ${i + 1}`}
                          <span className="ml-1 text-zinc-400">
                            {Math.round(room.confidence * 100)}%
                          </span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Ambiguity flags */}
                {parsedPlan.ambiguity_flags.length > 0 && (
                  <div className="rounded-xl border border-amber-800/50 bg-amber-900/20 p-4">
                    <h3 className="text-sm font-medium text-amber-300 mb-2">Ambiguities</h3>
                    <ul className="text-sm text-amber-200/80 space-y-1">
                      {parsedPlan.ambiguity_flags.map((flag) => (
                        <li key={flag.id}>• {flag.description}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* ── STEP 3: Inspiration Board ──────── */}
        {project.floorplan_asset_id && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-medium text-zinc-200">3. Inspiration Board</h2>
              {boards.length === 0 && (
                <button
                  onClick={handleCreateBoard}
                  className="text-sm px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white"
                >
                  Create Board
                </button>
              )}
            </div>

            {boards.length === 0 ? (
              <p className="text-zinc-500 text-sm">
                Create an inspiration board to upload reference images for style extraction.
              </p>
            ) : (
              <div className="space-y-4">
                {/* Board tabs */}
                <div className="flex gap-2">
                  {boards.map((b) => (
                    <button
                      key={b.id}
                      onClick={() => setActiveBoard(b)}
                      className={`px-3 py-1.5 rounded text-sm transition-colors ${
                        activeBoard?.id === b.id
                          ? 'bg-indigo-600 text-white'
                          : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                      }`}
                    >
                      {b.name} ({b.item_count})
                    </button>
                  ))}
                  <button
                    onClick={handleCreateBoard}
                    className="px-3 py-1.5 rounded text-sm bg-zinc-800 text-zinc-500 hover:text-zinc-300"
                  >
                    +
                  </button>
                </div>

                {/* Item grid */}
                <div className="grid grid-cols-4 gap-3">
                  {boardItems.map((item) => (
                    <div
                      key={item.id}
                      className="aspect-square rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs text-zinc-500 overflow-hidden"
                    >
                      {item.upload_status === 'ready' && item.storage_key ? (
                        <img
                          src={assetUrl(item.storage_key)}
                          alt="Inspiration"
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="flex flex-col items-center gap-1">
                          <div className="w-5 h-5 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin" />
                          <span>Processing…</span>
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Upload button */}
                  <label
                    className={`aspect-square rounded-lg border-2 border-dashed border-zinc-700 flex flex-col items-center justify-center cursor-pointer hover:border-indigo-500 hover:bg-indigo-500/5 transition-colors ${
                      uploadingInspiration ? 'opacity-50 pointer-events-none' : ''
                    }`}
                  >
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleInspirationUpload(f);
                      }}
                    />
                    <svg
                      className="w-6 h-6 text-zinc-500 mb-1"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M12 4v16m8-8H4"
                      />
                    </svg>
                    <span className="text-xs text-zinc-500">
                      {uploadingInspiration ? 'Uploading…' : 'Add image'}
                    </span>
                  </label>
                </div>
              </div>
            )}
          </section>
        )}

        {/* ── STEP 4: Style Profile ────────── */}
        {boards.length > 0 && boardItems.length > 0 && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-medium text-zinc-200">4. Style Profile</h2>
              {!inferringStyle && (
                <button
                  onClick={handleTriggerStyle}
                  className="text-sm text-indigo-400 hover:text-indigo-300"
                >
                  {styleProfile ? 'Re-analyze' : 'Analyze Style'}
                </button>
              )}
            </div>

            {inferringStyle && !styleProfile && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-8 text-center">
                <div className="inline-block w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-zinc-300">Analyzing style from inspiration images…</p>
              </div>
            )}

            {styleProfile && (
              <div className="space-y-4">
                {/* Emotional tone */}
                <div className="flex flex-wrap gap-2">
                  {styleProfile.style_signals.emotional_tone?.map((tone) => (
                    <span
                      key={tone}
                      className="px-3 py-1 rounded-full text-sm bg-purple-900/40 text-purple-200 border border-purple-700/50"
                    >
                      {tone}
                    </span>
                  ))}
                </div>

                {/* Key signals grid */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: 'Massing', value: styleProfile.style_signals.massing_tendency },
                    { label: 'Facade', value: styleProfile.style_signals.facade_rhythm },
                    { label: 'Lighting', value: styleProfile.style_signals.lighting_mood },
                    { label: 'Surface', value: styleProfile.style_signals.surface_language },
                    { label: 'Balance', value: styleProfile.style_signals.compositional_balance },
                    { label: 'Roof', value: styleProfile.style_signals.roof_tendency },
                    { label: 'Glazing', value: `${Math.round((styleProfile.style_signals.glazing_ratio || 0) * 100)}%` },
                    { label: 'Overhang', value: styleProfile.style_signals.overhang_tendency },
                  ].map((s) => (
                    <div
                      key={s.label}
                      className="rounded-lg bg-zinc-800/80 border border-zinc-700 p-3"
                    >
                      <p className="text-xs text-zinc-500 mb-1">{s.label}</p>
                      <p className="text-sm text-zinc-200 capitalize">
                        {String(s.value || '—').replace(/_/g, ' ')}
                      </p>
                    </div>
                  ))}
                </div>

                {/* Material palette */}
                {styleProfile.style_signals.material_palette?.length > 0 && (
                  <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-4">
                    <h3 className="text-sm font-medium text-zinc-300 mb-3">Material Palette</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {styleProfile.style_signals.material_palette.map((mat, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-3 rounded-lg bg-zinc-800 p-2"
                        >
                          {mat.color_hex && (
                            <div
                              className="w-8 h-8 rounded border border-zinc-600 flex-shrink-0"
                              style={{ backgroundColor: mat.color_hex }}
                            />
                          )}
                          <div className="min-w-0">
                            <p className="text-sm text-zinc-200 truncate">{mat.name}</p>
                            <p className="text-xs text-zinc-500 truncate">
                              {[mat.category, mat.finish].filter(Boolean).join(' · ')}
                              {mat.usage ? ` — ${mat.usage}` : ''}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Negative preferences */}
                {styleProfile.style_signals.negative_preferences?.length > 0 && (
                  <div className="rounded-xl border border-red-900/30 bg-red-900/10 p-4">
                    <h3 className="text-sm font-medium text-red-300 mb-2">Avoid</h3>
                    <div className="flex flex-wrap gap-2">
                      {styleProfile.style_signals.negative_preferences.map((neg) => (
                        <span
                          key={neg}
                          className="px-2 py-1 rounded text-xs text-red-200 bg-red-900/30 border border-red-800/40"
                        >
                          {neg}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* ── STEP 5: Geometry Rules ─────────── */}
        {styleProfile && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-medium text-zinc-200">5. Geometry Rules</h2>
              {!generatingRules && (
                <button
                  onClick={handleTriggerGeometry}
                  className="text-sm text-indigo-400 hover:text-indigo-300"
                >
                  {geometryRules ? 'Regenerate' : 'Generate Rules'}
                </button>
              )}
            </div>

            {generatingRules && !geometryRules && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-8 text-center">
                <div className="inline-block w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-zinc-300">Generating geometry rules…</p>
              </div>
            )}

            {geometryRules && (
              <div className="space-y-3">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-sm text-zinc-400">
                    {geometryRules.rules.length} rules
                  </span>
                  <span className="text-sm text-zinc-500">·</span>
                  <span className="text-sm text-zinc-400">
                    {Math.round(geometryRules.confidence_overall * 100)}% confidence
                  </span>
                </div>
                {geometryRules.rules.map((rule, i) => (
                  <div
                    key={i}
                    className="rounded-lg bg-zinc-800/80 border border-zinc-700 p-3"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="px-2 py-0.5 rounded text-xs font-mono bg-zinc-700 text-zinc-300">
                        {rule.rule_type}
                      </span>
                      {typeof rule.confidence === 'number' && (
                        <span className="text-xs text-zinc-500">
                          {Math.round((rule.confidence as number) * 100)}%
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-zinc-300 mt-1">
                      {rule.rule_type === 'glazing_ratio' && (
                        <span>Target {Math.round(((rule.target_ratio as number) || 0) * 100)}% glass on {rule.applies_to}</span>
                      )}
                      {rule.rule_type === 'roof_form' && (
                        <span>{String(rule.form)} roof{rule.pitch_degrees ? ` at ${rule.pitch_degrees}°` : ''}</span>
                      )}
                      {rule.rule_type === 'floor_height' && (
                        <span>{rule.height_meters}m ceiling — {String(rule.applies_to || 'all')}</span>
                      )}
                      {rule.rule_type === 'material_hint' && (
                        <span>
                          <strong className="text-zinc-200">{String(rule.material)}</strong>
                          {' on '}{String(rule.target_surface)}
                          {rule.room_ids && Array.isArray(rule.room_ids) && rule.room_ids.length > 0
                            ? ` (${(rule.room_ids as string[]).length} rooms)`
                            : ' (all rooms)'}
                          {rule.finish ? ` — ${rule.finish}` : ''}
                        </span>
                      )}
                      {rule.rule_type === 'overhang' && (
                        <span>{rule.depth_meters}m overhang on {String(rule.applies_to)}</span>
                      )}
                      {rule.rule_type === 'facade_grid' && (
                        <span>{rule.module_width_meters}m × {rule.module_height_meters}m grid module</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* ── STEP 6: 3D Model ─────────────── */}
        {geometryRules && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-medium text-zinc-200">6. 3D Model</h2>
              {!building && (
                <button
                  onClick={handleBuild}
                  className="text-sm text-indigo-400 hover:text-indigo-300"
                >
                  {modelData ? 'Rebuild' : 'Build 3D Model'}
                </button>
              )}
            </div>

            {building && !modelData && (
              <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-8 text-center">
                <div className="inline-block w-6 h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-zinc-300">Reconstructing 3D model…</p>
                {stage && <p className="text-zinc-500 text-sm mt-1">{stage}</p>}
              </div>
            )}

            {modelData && (
              <div className="space-y-4">
                {/* Three.js Viewer */}
                <div
                  ref={viewerRef}
                  className="rounded-xl border border-zinc-700 bg-zinc-900 overflow-hidden"
                  style={{ minHeight: 500 }}
                />

                {/* Model stats */}
                <div className="grid grid-cols-5 gap-3">
                  {[
                    { label: 'Walls', value: modelData.elements?.walls?.length || 0 },
                    { label: 'Rooms', value: modelData.elements?.rooms?.length || 0 },
                    { label: 'Windows', value: modelData.elements?.windows?.length || 0 },
                    { label: 'Doors', value: modelData.elements?.doors?.length || 0 },
                    { label: 'Fidelity', value: modelData.fidelity_scores?.overall != null
                        ? `${(modelData.fidelity_scores.overall * 100).toFixed(0)}%` : '—' },
                  ].map((stat) => (
                    <div
                      key={stat.label}
                      className="rounded-lg bg-zinc-800/80 border border-zinc-700 p-3 text-center"
                    >
                      <p className="text-xl font-semibold text-zinc-100">{stat.value}</p>
                      <p className="text-xs text-zinc-500">{stat.label}</p>
                    </div>
                  ))}
                </div>

                {/* Construction parameters */}
                {modelData.params_used && (
                  <div className="rounded-lg bg-zinc-800/50 border border-zinc-700/50 p-4">
                    <p className="text-xs font-medium text-zinc-400 mb-2 uppercase tracking-wider">Construction Parameters</p>
                    <div className="grid grid-cols-3 gap-x-6 gap-y-1 text-sm">
                      <div className="flex justify-between"><span className="text-zinc-500">Floor Height</span><span className="text-zinc-200">{modelData.params_used.floor_height}m</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">Wall Thickness</span><span className="text-zinc-200">{modelData.params_used.wall_thickness}m</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">Slab Thickness</span><span className="text-zinc-200">{modelData.params_used.slab_thickness}m</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">Glazing Ratio</span><span className="text-zinc-200">{(modelData.params_used.glazing_ratio * 100).toFixed(0)}%</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">Roof Form</span><span className="text-zinc-200 capitalize">{modelData.params_used.roof_form}</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">Scale</span><span className="text-zinc-200">{modelData.coordinate_system?.px_per_meter?.toFixed(1)} px/m</span></div>
                    </div>
                  </div>
                )}

                {/* Provenance summary */}
                {modelData.provenance && (
                  <div className="rounded-lg bg-zinc-800/50 border border-zinc-700/50 p-4">
                    <p className="text-xs font-medium text-zinc-400 mb-2 uppercase tracking-wider">Element Provenance</p>
                    <div className="flex gap-4 text-sm">
                      {(() => {
                        const prov = modelData.provenance;
                        const counts = { observed: 0, inferred: 0, assumed: 0 };
                        Object.values(prov).forEach((p: any) => {
                          const t = p.observation_type || 'assumed';
                          if (t in counts) counts[t as keyof typeof counts]++;
                        });
                        return (
                          <>
                            <span className="text-emerald-400">{counts.observed} observed</span>
                            <span className="text-amber-400">{counts.inferred} inferred</span>
                            {counts.assumed > 0 && <span className="text-red-400">{counts.assumed} assumed</span>}
                            <span className="text-zinc-500 ml-auto">{Object.keys(prov).length} total elements</span>
                          </>
                        );
                      })()}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* ── STEP 7: Export & Download ──────── */}
        {modelData && exports.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-zinc-200 mb-3">7. Export & Download</h2>
            <div className="space-y-3">
              {exports.map((exp) => (
                <div
                  key={exp.id}
                  className="rounded-lg bg-zinc-800/80 border border-zinc-700 p-4 flex items-center justify-between"
                >
                  <div>
                    <span className="px-2 py-0.5 rounded text-xs font-mono bg-cyan-900/40 text-cyan-300 border border-cyan-700/50 uppercase">
                      {exp.format}
                    </span>
                    <span className="ml-3 text-sm text-zinc-300">3D Building Model</span>
                  </div>
                  <a
                    href={assetUrl(exp.storage_key)}
                    download={`noa-model.${exp.format}`}
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
                  >
                    Download .{exp.format.toUpperCase()}
                  </a>
                </div>
              ))}
            </div>
          </section>
        )}

        {error && <p className="mt-4 text-red-400 text-sm">{error}</p>}
      </div>
    </main>
  );
}
