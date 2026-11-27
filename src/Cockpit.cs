using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using BepInEx.Logging;
using UnityEngine;
using UnityEngine.Rendering;

namespace TyphoonMod
{
    internal sealed class CockpitDef
    {
        public Vector3 Eye = new Vector3(0f, 1.16f, 6.5f);
        public Vector3 Stick;
        public bool HasStick;
        public readonly Dictionary<string, Vector3[]> Screens = new Dictionary<string, Vector3[]>();
        public readonly Dictionary<string, float> Proud = new Dictionary<string, float>();
        public sealed class KeyDef { public string State, Text; public Vector4 On, Off; }
        public readonly List<KeyDef> Keys = new List<KeyDef>();

        public static CockpitDef Load(string path, ManualLogSource log)
        {
            var d = new CockpitDef();
            if (!File.Exists(path)) { log.LogWarning("typhoon_cockpit.txt not found: the Typhoon cockpit interior is off."); return null; }
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                var t = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                try
                {
                    if (t[0] == "eye") d.Eye = V(t, 1);
                    else if (t[0] == "stick") { d.Stick = V(t, 1); d.HasStick = true; }
                    else if (t[0] == "screen" && t.Length >= 14)
                    {
                        d.Screens[t[1]] = new[] { V(t, 2), V(t, 5), V(t, 8), V(t, 11) };
                        float pr;
                        if (t.Length >= 15 && float.TryParse(t[14], NumberStyles.Float, CultureInfo.InvariantCulture, out pr))
                            d.Proud[t[1]] = Mathf.Clamp(pr, 0.0003f, 0.01f);
                    }
                }
                catch (Exception e) { log.LogWarning($"typhoon_cockpit.txt: bad line '{line}': {e.Message}"); }
            }
            try
            {
                string kp = Path.Combine(Path.GetDirectoryName(path) ?? "", "typhoon_keys.txt");
                if (File.Exists(kp))
                    foreach (var raw in File.ReadAllLines(kp))
                    {
                        var t = raw.Trim().Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                        if (t.Length < 10 || t[0] != "key") continue;
                        Func<int, float> f = i => float.Parse(t[i], CultureInfo.InvariantCulture);
                        d.Keys.Add(new KeyDef { State = t[1], On = new Vector4(f(2), f(3), f(4), f(5)), Off = new Vector4(f(6), f(7), f(8), f(9)),
                                                Text = t.Length > 10 ? string.Join(" ", t.Skip(10)) : "" });
                    }
            }
            catch (Exception e) { log.LogWarning("typhoon_keys.txt: " + e.Message); }
            return d;
        }

        static Vector3 V(string[] t, int i)
        {
            return new Vector3(float.Parse(t[i], CultureInfo.InvariantCulture), float.Parse(t[i + 1], CultureInfo.InvariantCulture),
                               float.Parse(t[i + 2], CultureInfo.InvariantCulture));
        }
    }

    internal static class CockpitCamera
    {
        internal static TyphoonCockpit Active;
        static bool _hooked;
        static readonly Dictionary<Transform, Vector3> Moved = new Dictionary<Transform, Vector3>();

        public static void Hook()
        {
            if (_hooked) return;
            _hooked = true;
            RenderPipelineManager.beginCameraRendering += Begin;
            RenderPipelineManager.endCameraRendering += End;
        }

        static int _pinFrame = -1;

        static void Begin(ScriptableRenderContext ctx, Camera cam)
        {
            try
            {
                if (Time.frameCount != _pinFrame) { _pinFrame = Time.frameCount; TyphoonVisual.EnforceAllPins(); }
                var a = Active;
                if (a == null || !a.ShiftOn || cam == null) return;
                if (cam.targetTexture != null || cam.cameraType != CameraType.Game) return;
                var t = cam.transform;
                if (Moved.ContainsKey(t)) return;
                for (var p = t.parent; p != null; p = p.parent) if (Moved.ContainsKey(p)) return;
                if ((t.position - a.PilotPosition).sqrMagnitude > 9f) return;
                Moved[t] = t.localPosition;
                t.position += a.CurrentShift();
            }
            catch { }
        }

        static void End(ScriptableRenderContext ctx, Camera cam)
        {
            try
            {
                if (cam == null) return;
                Vector3 p;
                if (Moved.TryGetValue(cam.transform, out p)) { cam.transform.localPosition = p; Moved.Remove(cam.transform); }
            }
            catch { }
        }

        public static void RestoreAll()
        {
            if (Moved.Count == 0) return;
            foreach (var kv in Moved) if (kv.Key != null) kv.Key.localPosition = kv.Value;
            Moved.Clear();
        }
    }

    internal sealed class TyphoonCockpit
    {
        internal static bool AlignEye = true, LiveDisplays = true, FlipTac;
        internal static Vector3 EyeOffset;
        internal static string TacArea = "auto";
        internal static bool OwnRadar = true;
        internal static float RadarZoom = 1.0f;
        internal static string NightMode = "on";
        internal static float FloodBrightness = 0f;
        internal static string GlowMode = "overlay";
        internal static float LegendBrightness = 1f;
        internal static float DisplayNight = 0.35f;
        internal static float DisplayGlow = 1.2f;
        internal static float DisplayBrightness = 1f;
        internal readonly List<Material> DisplayMats = new List<Material>();
        NightLighting _night;

        internal List<GameObject> LayerObjects = new List<GameObject>();
        internal int CockpitLayer, ExteriorLayer;
        int _layerState = -1;
        float _dumpAt = -1f;
        int _tacTries;
        TacScreen _tac;
        Camera _tacCam;
        GameObject _tgtDisp, _landDisp;
        Rect _radarUV, _shownUV;
        int _tacMode = -1;
        float _nextTacCheck;
        RenderTexture _tacHold;
        int _tacPending = -1;
        float _tacSwitchAt;
        Vector2 _blitScale = Vector2.one, _blitOffset = Vector2.zero;
        internal static float TacSwitchHold = 0.35f;
        internal static bool TacCopy = true;
        readonly Aircraft _ac;
        readonly Transform _root;
        Transform _pilot;
        Vector3 _eyeRoot;
        Vector3 _camRef; bool _hasRef, _wasInCockpit; float _enteredAt;
        internal bool ShiftOn;
        internal Vector3 WorldShift;
        Vector3 _shiftLocal;
        internal Vector3 CurrentShift() { return _root != null ? _root.TransformVector(_shiftLocal) : WorldShift; }
        internal Vector3 PilotPosition => _pilot != null ? _pilot.position : _root.position;

        sealed class Display
        {
            public string Name;
            public MeshRenderer Renderer;
            public Material Material;
            public MfdCanvas Canvas;
            public float Next;
            public MfdCanvas Alt, Linked;
            public bool Tac;
            public Mesh Mesh;
            public Vector3[] Base;
            public Vector3 N;
            public float Radius;
        }
        readonly List<Display> _displays = new List<Display>();
        Display _centre, _sadi;
        float _nextSadi;
        Texture _tacRT;
        float _nextTacSearch, _nextDraw;
        int _drawIndex;
        bool _loggedView;

        float _fuelPrev = -1f, _fuelFlow, _fuelT;
        static readonly MethodInfo GetInputsM = typeof(Aircraft).GetMethod("GetInputs", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        static readonly MethodInfo FuelQtyM = typeof(Aircraft).GetMethod("GetFuelQuantity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        static readonly FieldInfo RpmF = typeof(Turbojet).GetField("rpm", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo MaxRpmF = typeof(Turbojet).GetField("maxRPM", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo TacScreenF = typeof(Cockpit).GetField("tacScreen", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo TacRenderF = typeof(Cockpit).GetField("tacScreenRender", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo TacRTF = typeof(TacScreen).GetField("renderTexture", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo JoysticksF = typeof(Cockpit).GetField("joysticks", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        List<Turbojet> _engines;
        TyphoonVisual _visual;

        TyphoonCockpit(Aircraft ac, TyphoonVisual visual)
        {
            _ac = ac; _root = ac.transform; _visual = visual;
        }

        internal static Cockpit FindCockpit(Aircraft ac)
        {
            var c = ac.GetComponentInChildren<Cockpit>(true);
            if (c == null && ac.partLookup != null)
                foreach (var up in ac.partLookup) { if (up == null) continue; c = up.GetComponentInChildren<Cockpit>(true); if (c != null) break; }
            return c;
        }

        internal static Transform FindJoystick(Aircraft ac)
        {
            var c = FindCockpit(ac);
            var arr = c != null && JoysticksF != null ? JoysticksF.GetValue(c) as Array : null;
            if (arr == null) return null;
            foreach (var j in arr)
            {
                if (j == null) continue;
                var tf = j.GetType().GetField("transform", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)?.GetValue(j) as Transform;
                if (tf != null) return tf;
            }
            return null;
        }

        internal float[] Inputs()
        {
            try
            {
                var ci = GetInputsM?.Invoke(_ac, null) as ControlInputs;
                if (ci != null) return new[] { ci.pitch, ci.roll, ci.yaw, ci.throttle };
            }
            catch { }
            return new float[4];
        }

        public static TyphoonCockpit Setup(Aircraft ac, TyphoonVisual visual, CockpitDef def, Matrix4x4 modelToRoot, Transform parent, int layer, Transform pilot, ManualLogSource log)
        {
            var tc = new TyphoonCockpit(ac, visual) { _pilot = pilot };
            tc._eyeRoot = modelToRoot.MultiplyPoint3x4(def.Eye);
            tc._keyDefs = def.Keys;
            tc._engines = TyphoonSounds.Engines(ac);
            try { ac.onRadarWarning += tc.OnRadarWarning; } catch { }
            try { if (parent != null) tc._night = NightLighting.Setup(parent, tc._root, modelToRoot, visual, log); }
            catch (Exception e) { log.LogWarning("Typhoon cockpit night lighting: " + e.Message); }
            if (!LiveDisplays || parent == null) return tc;
            var unlit = Shader.Find("Universal Render Pipeline/Unlit");
            log.LogInfo(unlit != null ? "Cockpit displays use URP Unlit." : "URP Unlit not found; cockpit displays use URP Lit with emission.");
            Matrix4x4 toParent = parent.worldToLocalMatrix * tc._root.localToWorldMatrix * modelToRoot;
            Vector3 eyeP = toParent.MultiplyPoint3x4(def.Eye);
            foreach (var kv in def.Screens)
            {
                var c = kv.Value.Select(p => toParent.MultiplyPoint3x4(p)).ToArray();
                Vector3 centre = (c[0] + c[1] + c[2] + c[3]) * 0.25f;
                Vector3 n = Vector3.Cross(c[1] - c[0], c[3] - c[0]).normalized;
                if (Vector3.Dot(n, eyeP - centre) < 0) n = -n;
                float proud;
                if (!def.Proud.TryGetValue(kv.Key, out proud)) proud = 0.0025f;
                for (int i = 0; i < 4; i++) c[i] += n * proud;
                var cFull = (Vector3[])c.Clone();
                float rFull = CornerRadius * (c[1] - c[0]).magnitude;
                bool mfd = kv.Key.StartsWith("mfd_") || kv.Key == "dwp";
                float margin = mfd ? Mathf.Clamp(DisplayMargin, 0f, 0.012f) : 0f;
                if (margin > 0f)
                {
                    Vector3 ux = (c[1] - c[0]).normalized * margin, uy = (c[0] - c[3]).normalized * margin;
                    c[0] += ux - uy; c[1] += -ux - uy; c[2] += -ux + uy; c[3] += ux + uy;
                }
                var go = MakeQuad(parent, layer, "Typhoon_" + kv.Key, c, n, null);
                var mesh = go.GetComponent<MeshFilter>().sharedMesh;
                float rAbs = margin > 0f ? Mathf.Max(rFull - margin, 0.002f) : rFull;
                SetRounded(mesh, c, n, rAbs, true, true);
                var mr = go.GetComponent<MeshRenderer>();
                var mat = unlit != null ? new Material(unlit) : new Material(Shader.Find("Universal Render Pipeline/Lit"));
                mat.name = "Typhoon_" + kv.Key;
                mr.sharedMaterial = mat;
                var d = new Display { Name = kv.Key, Renderer = mr, Material = mat, Tac = kv.Key.EndsWith("_C"), Mesh = mesh, Base = (Vector3[])c.Clone(), N = n };
                d.Radius = rAbs;
                if (d.Tac || margin > 0f)
                {
                    var bc = (Vector3[])cFull.Clone();
                    for (int i = 0; i < 4; i++) bc[i] -= n * Mathf.Min(0.0007f, proud * 0.6f);
                    var backGo = MakeQuad(parent, layer, "Typhoon_" + kv.Key + "_back", bc, n, null);
                    SetRounded(backGo.GetComponent<MeshFilter>().sharedMesh, bc, n, rFull, true, true);
                    var back = backGo.GetComponent<MeshRenderer>();
                    var bm = unlit != null ? new Material(unlit) : new Material(Shader.Find("Universal Render Pipeline/Lit"));
                    if (bm.HasProperty("_BaseColor")) bm.SetColor("_BaseColor", new Color(0.02f, 0.025f, 0.03f, 1f));
                    bm.color = new Color(0.02f, 0.025f, 0.03f, 1f);
                    back.sharedMaterial = bm;
                    visual.Interior.Add(back);
                }
                if (d.Tac)
                {
                    tc._barTop = MakeBar(parent, layer, "Typhoon_mfd_C_bartop", unlit, visual);
                    tc._barBot = MakeBar(parent, layer, "Typhoon_mfd_C_barbot", unlit, visual);
                }
                float aspectWH = (c[1] - c[0]).magnitude / Mathf.Max(1e-4f, (c[0] - c[3]).magnitude);
                d.Canvas = aspectWH >= 1f ? new MfdCanvas(256, Mathf.Clamp(Mathf.RoundToInt(256f / aspectWH), 64, 256))
                                          : new MfdCanvas(Mathf.Clamp(Mathf.RoundToInt(256f * aspectWH), 64, 256), 256);
                SetTexture(mat, d.Canvas.Tex);
                if (kv.Key == "sadi") { d.Canvas = new MfdCanvas(128, 128); SetTexture(mat, d.Canvas.Tex); tc._sadi = d; }
                if (kv.Key == "mdef")
                {
                    d.Canvas = new MfdCanvas(136, Mathf.Clamp(Mathf.RoundToInt(136f / Mathf.Max(0.3f, aspectWH)), 40, 200));
                    SetTexture(mat, d.Canvas.Tex);
                    d.Alt = new MfdCanvas(96, Mathf.Clamp(Mathf.RoundToInt(96f / Mathf.Max(0.3f, aspectWH)), 34, 160));
                    d.Linked = d.Canvas;
                }
                tc._displays.Add(d);
                tc.DisplayMats.Add(mat);
                try { tc.MakeSmudge(parent, layer, kv.Key, cFull, n, rFull, visual); } catch (Exception e) { log.LogWarning("Typhoon display smudges: " + e.Message); }
                if (d.Tac) tc._centre = d;
                visual.Interior.Add(mr);
            }
            try { tc.MakeGhosts(parent, toParent, layer); } catch (Exception e) { log.LogWarning("Typhoon cockpit canopy reflections: " + e.Message); }
            log.LogInfo($"Typhoon cockpit: {tc._displays.Count} live displays.");
            return tc;
        }

        sealed class Bar { public MeshRenderer R; public Mesh Mesh; public Material M; public MfdCanvas C; }
        Bar _barTop, _barBot;
        bool _barsOn;
        float _lockUntil, _spikeUntil;

        void OnRadarWarning(Aircraft.OnRadarWarning e)
        {
            if (e.isTarget) _lockUntil = Time.unscaledTime + 2.5f;
            else _spikeUntil = Time.unscaledTime + 2f;
        }

        static Bar MakeBar(Transform parent, int layer, string name, Shader unlit, TyphoonVisual visual)
        {
            var z = new[] { Vector3.zero, Vector3.right * 0.01f, new Vector3(0.01f, -0.01f, 0), Vector3.down * 0.01f };
            var go = MakeQuad(parent, layer, name, z, Vector3.back, null);
            var b = new Bar { R = go.GetComponent<MeshRenderer>(), Mesh = go.GetComponent<MeshFilter>().sharedMesh };
            b.M = unlit != null ? new Material(unlit) : new Material(Shader.Find("Universal Render Pipeline/Lit"));
            b.M.name = name;
            b.R.sharedMaterial = b.M;
            b.R.enabled = false;
            visual.Interior.Add(b.R);
            return b;
        }

        void PlaceBar(Bar b, float top, float bottom)
        {
            var d = _centre; var c = d.Base;
            Vector3 down = c[3] - c[0], off = d.N * 0.0003f;
            var v = new[] { c[0] + down * top, c[1] + down * top, c[1] + down * bottom, c[0] + down * bottom };
            for (int i = 0; i < 4; i++) v[i] += off;
            SetRounded(b.Mesh, v, d.N, d.Radius, top <= 0f, bottom >= 1f);
            int h = Mathf.Clamp(Mathf.RoundToInt(256f * (bottom - top)), 16, 128);
            if (b.C == null || b.C.H != h) { b.C = new MfdCanvas(256, h); SetTexture(b.M, b.C.Tex); }
            b.R.enabled = true;
        }

        void BarsOff()
        {
            _barsOn = false;
            if (_barTop != null) _barTop.R.enabled = false;
            if (_barBot != null) _barBot.R.enabled = false;
        }

        static readonly FieldInfo CombatHudI = typeof(CombatHUD).BaseType?.GetField("i", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        static readonly FieldInfo WeaponStateF = typeof(CombatHUD).GetField("weaponState", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        static readonly FieldInfo GearSafetyF = typeof(WeaponStation).GetField("gearSafety", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        static readonly FieldInfo ScreenUIF = typeof(TargetCam).GetField("targetScreenUI", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        static readonly FieldInfo LasingIconF = typeof(TargetScreenUI).GetField("lasingIcon", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);

        static float GetF(object o, string name)
        {
            var f = o?.GetType().GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (f == null) return -1f;
            try { return Convert.ToSingle(f.GetValue(o)); } catch { return -1f; }
        }

        MfdPages.RadarInfo RadarData()
        {
            var r = new MfdPages.RadarInfo { Blink = (Time.unscaledTime % 0.8f) < 0.5f };
            float now = Time.unscaledTime;
            r.Spike = now < _spikeUntil;
            try { var mw = _ac.GetMissileWarningSystem(); r.MissileWarn = mw != null && mw.IsWarning(); } catch { }
            Vector3 fwd = _root.forward; fwd.y = 0f;
            if (fwd.sqrMagnitude < 1e-6f) fwd = Vector3.forward;
            fwd.Normalize();
            Vector3 right = Vector3.Cross(Vector3.up, fwd);
            float hd = Mathf.Atan2(fwd.x, fwd.z) * Mathf.Rad2Deg; if (hd < 0) hd += 360f;
            r.Heading = hd;
            var rad = _ac.radar;
            r.On = rad != null && rad.activated;
            try { if (rad != null) r.RadarRangeM = rad.GetRadarRange(); } catch { }
            System.Collections.Generic.List<Unit> sel = null;
            try { sel = _ac.weaponManager != null ? _ac.weaponManager.GetTargetList() : null; } catch { }
            var units = new System.Collections.Generic.List<Unit>();
            if (r.On && rad.detectedTargets != null) units.AddRange(rad.detectedTargets);
            if (sel != null) foreach (var u in sel) if (u != null && !units.Contains(u)) units.Add(u);
            if (units.Count == 0) return r;
            FactionHQ own = null;
            try { own = _ac.NetworkHQ; } catch { }
            Vector3 me = _root.position;
            foreach (var u in units)
            {
                if (u == null || u == _ac || u.disabled) continue;
                try
                {
                    Vector3 pos; float alt; bool live;
                    if (!Known(own, u, out pos, out alt, out live)) continue;
                    Vector3 d = pos - me;
                    var k = new MfdPages.RadarContact
                    {
                        Az = Mathf.Atan2(Vector3.Dot(d, right), Vector3.Dot(d, fwd)) * Mathf.Rad2Deg,
                        RangeM = new Vector2(d.x, d.z).magnitude,
                        Kind = u is Aircraft ? 0 : u is Missile ? 2 : 1,
                        Selected = sel != null && sel.Contains(u),
                        Stale = !live,
                        Name = u.definition != null && !string.IsNullOrEmpty(u.definition.code) ? u.definition.code : u.unitName
                    };
                    if (live)
                    {
                        k.AltFt = alt * 3.28084f;
                        try { var rb = u.rb; if (rb != null) { var v = rb.velocity; k.Vx = Vector3.Dot(v, right); k.Vz = Vector3.Dot(v, fwd); } } catch { }
                    }
                    FactionHQ hq = null;
                    try { hq = u.NetworkHQ; } catch { }
                    k.Side = own == null || hq == null ? 0 : hq == own ? 1 : -1;
                    r.Contacts.Add(k);
                }
                catch { }
            }
            return r;
        }

        static bool Known(FactionHQ own, Unit u, out Vector3 world, out float altitude, out bool live)
        {
            world = default(Vector3); altitude = 0f; live = false;
            if (own == null || u == null) return false;
            try
            {
                GlobalPosition gp;
                if (!own.TryGetKnownPosition(u, out gp)) return false;
                live = own.IsTargetBeingTracked(u);
                world = gp.ToLocalPosition();
                altitude = gp.y;
                return true;
            }
            catch { return false; }
        }

        MfdPages.TargetInfo TargetData()
        {
            var t = new MfdPages.TargetInfo { Blink = (Time.unscaledTime % 0.8f) < 0.5f };
            float now = Time.unscaledTime;
            try { var mw = _ac.GetMissileWarningSystem(); t.MissileWarn = mw != null && mw.IsWarning(); } catch { }
            t.RadarLock = now < _lockUntil;
            t.Spike = now < _spikeUntil;
            WeaponStation ws = null;
            try { ws = _ac.weaponManager != null ? _ac.weaponManager.currentWeaponStation : null; } catch { }
            WeaponInfo wi = ws != null ? ws.WeaponInfo : null;
            if (wi != null)
            {
                t.Weapon = (wi.shortName ?? wi.weaponName ?? "").ToUpperInvariant();
                t.Laser = wi.laserGuided;
                bool safe = false;
                try { safe = GearSafetyF != null && (bool)GearSafetyF.GetValue(ws) && _ac.gearDeployed; } catch { }
                t.State = ws.Ammo <= 0 ? "EMPTY" : ws.Reloading ? "RELOAD" : safe ? "SAFE" : "READY";
            }
            Unit first = null;
            try
            {
                var list = _ac.weaponManager != null ? _ac.weaponManager.GetTargetList() : null;
                if (list != null) { t.Targets = list.Count; first = list.FirstOrDefault(u => u != null); }
            }
            catch { }
            if (t.Laser)
                try
                {
                    var sui = ScreenUIF?.GetValue(_ac.targetCam);
                    var icon = sui != null ? LasingIconF?.GetValue(sui) as GameObject : null;
                    t.Lasing = icon != null && icon.activeInHierarchy;
                }
                catch { }
            if (first == null) return t;
            FactionHQ ownHq = null;
            try { ownHq = _ac.NetworkHQ; } catch { }
            Vector3 known; float knownAlt; bool knownLive;
            if (!Known(ownHq, first, out known, out knownAlt, out knownLive)) return t;
            Vector3 rel = _root.InverseTransformPoint(known);
            t.Range = rel.magnitude;
            t.OffAz = Mathf.Atan2(rel.x, rel.z) * Mathf.Rad2Deg;
            t.OffEl = Mathf.Atan2(rel.y, new Vector2(rel.x, rel.z).magnitude) * Mathf.Rad2Deg;
            try
            {
                var hud = CombatHudI?.GetValue(null) as CombatHUD;
                var state = hud != null && hud.aircraft == _ac ? WeaponStateF?.GetValue(hud) : null;
                if (state != null)
                {
                    float mn = GetF(state, "minRange"), mx = GetF(state, "maxRange"), ne = GetF(state, "noEscapeRange");
                    if (mx > 1f && !float.IsNaN(mx) && !float.IsInfinity(mx))
                    {
                        t.HasEnvelope = true; t.Min = Mathf.Max(0f, mn); t.Max = mx; t.NoEscape = ne > 1f && ne < mx ? ne : -1f;
                    }
                }
            }
            catch { }
            if (wi != null)
            {
                float own = _ac.speed;
                if (wi.gun) t.Tof = t.Range / Mathf.Max(100f, wi.muzzleVelocity + own);
                else if (wi.bomb && !wi.glideBomb) t.Tof = Mathf.Sqrt(2f * Mathf.Max(1f, -rel.y + 0f) / 9.81f);
                else if (wi.maxSpeed > 1f) t.Tof = t.Range / Mathf.Max(100f, 0.7f * wi.maxSpeed + 0.3f * own);
            }
            return t;
        }

        void DrawBars()
        {
            var t = TargetData();
            MfdPages.TargetTop(_barTop.C, t); _barTop.C.Apply();
            MfdPages.TargetBottom(_barBot.C, t); _barBot.C.Apply();
        }

        internal static float CornerRadius = 0.06f;
        internal static float DisplayMargin = 0.003f;

        static void SetRounded(Mesh m, Vector3[] c, Vector3 n, float rAbs, bool roundTop, bool roundBottom)
        {
            float w = (c[1] - c[0]).magnitude, h = (c[0] - c[3]).magnitude;
            float rx = Mathf.Min(0.49f, rAbs / Mathf.Max(1e-5f, w)), ry = Mathf.Min(0.49f, rAbs / Mathf.Max(1e-5f, h));
            var uv = new List<Vector2> { new Vector2(0.5f, 0.5f) };
            const int seg = 6;
            var corners = new[] {
                new { P = new Vector2(0, 1), C = new Vector2(rx, 1 - ry), A = 180f, R = roundTop },
                new { P = new Vector2(1, 1), C = new Vector2(1 - rx, 1 - ry), A = 90f, R = roundTop },
                new { P = new Vector2(1, 0), C = new Vector2(1 - rx, ry), A = 0f, R = roundBottom },
                new { P = new Vector2(0, 0), C = new Vector2(rx, ry), A = -90f, R = roundBottom } };
            foreach (var k in corners)
            {
                if (!k.R || rAbs <= 0f) { uv.Add(k.P); continue; }
                for (int i = 0; i <= seg; i++)
                {
                    float a = (k.A - 90f * i / seg) * Mathf.Deg2Rad;
                    uv.Add(new Vector2(k.C.x + Mathf.Cos(a) * rx, k.C.y + Mathf.Sin(a) * ry));
                }
            }
            var verts = new Vector3[uv.Count];
            for (int i = 0; i < uv.Count; i++)
            {
                Vector2 q = uv[i];
                Vector3 bottom = Vector3.Lerp(c[3], c[2], q.x), top = Vector3.Lerp(c[0], c[1], q.x);
                verts[i] = Vector3.Lerp(bottom, top, q.y);
            }
            int ring = uv.Count - 1;
            var tris = new int[ring * 3];
            bool front = Vector3.Dot(Vector3.Cross(verts[1] - verts[0], verts[2] - verts[0]), n) > 0;
            for (int i = 0; i < ring; i++)
            {
                int a = 1 + i, b = 1 + (i + 1) % ring;
                tris[i * 3] = 0;
                tris[i * 3 + 1] = front ? a : b;
                tris[i * 3 + 2] = front ? b : a;
            }
            m.triangles = new int[0];
            m.vertices = verts;
            m.uv = uv.ToArray();
            var ns = new Vector3[verts.Length]; for (int i = 0; i < ns.Length; i++) ns[i] = n;
            m.normals = ns;
            m.triangles = tris;
            m.RecalculateBounds();
        }

        static GameObject MakeQuad(Transform parent, int layer, string name, Vector3[] c, Vector3 n, Material m)
        {
            var mesh = new Mesh { name = name };
            mesh.vertices = c;
            mesh.uv = new[] { new Vector2(0, 1), new Vector2(1, 1), new Vector2(1, 0), new Vector2(0, 0) };
            mesh.normals = new[] { n, n, n, n };
            bool front = Vector3.Dot(Vector3.Cross(c[1] - c[0], c[2] - c[0]), n) > 0;
            mesh.triangles = front ? new[] { 0, 1, 2, 0, 2, 3 } : new[] { 0, 2, 1, 0, 3, 2 };
            mesh.RecalculateBounds();
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.shadowCastingMode = ShadowCastingMode.Off;
            if (m != null) mr.sharedMaterial = m;
            return go;
        }

        static Vector3[] Expand(Vector3[] c, float margin)
        {
            Vector3 right = (c[1] - c[0]) * margin, down = (c[3] - c[0]) * margin;
            return new[] { c[0] - right - down, c[1] + right - down, c[2] + right + down, c[3] - right + down };
        }

        static void SetTexture(Material m, Texture t)
        {
            if (m.HasProperty("_BaseMap")) m.SetTexture("_BaseMap", t);
            if (m.HasProperty("_MainTex")) m.SetTexture("_MainTex", t);
            if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", new Color(0.03f, 0.03f, 0.03f, 1f));
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.30f);
            if (m.HasProperty("_EmissionMap")) { m.SetTexture("_EmissionMap", t); m.SetColor("_EmissionColor", new Color(DisplayGlow, DisplayGlow, DisplayGlow, 1f)); m.EnableKeyword("_EMISSION"); }
        }

        Transform[] _needles; Vector3[] _nC, _nAx; bool _needleFail;
        internal static float NeedleSense = 1f;

        void UpdateNeedles()
        {
            if (_needleFail || _visual == null) return;
            try
            {
                if (_needles == null)
                {
                    var nd = new Transform[3]; _nC = new Vector3[3]; _nAx = new Vector3[3];
                    foreach (var r in _visual.Interior)
                    {
                        if (r == null) continue;
                        for (int n = 0; n < 3; n++)
                        {
                            if (r.name != "Typhoon_cockpit_sbyneedle_" + n) continue;
                            var mf = r.GetComponent<MeshFilter>();
                            if (mf == null || mf.sharedMesh == null) continue;
                            nd[n] = r.transform; _nC[n] = mf.sharedMesh.bounds.center;
                            var nn = mf.sharedMesh.normals; _nAx[n] = nn.Length > 0 ? nn[0].normalized : Vector3.forward;
                        }
                    }
                    if (nd[0] == null && nd[1] == null && nd[2] == null) { if (_visual.Interior.Count > 0) _needleFail = true; return; }
                    _needles = nd;
                }
                var f = FlightData();
                float kt = f.Speed * 1.94384f, fpm = f.Vs * 196.85f, ft = f.Altitude * 3.28084f;
                float a0 = Mathf.Clamp(kt, 0f, 800f) / 800f * 330f - 165f, a1 = Mathf.Clamp(fpm / 6000f, -1f, 1f) * 150f - 90f, a2 = Mathf.Repeat(ft, 1000f) / 1000f * 360f;
                for (int n = 0; n < 3; n++)
                {
                    if (_needles[n] == null) continue;
                    var q = Quaternion.AngleAxis((n == 0 ? a0 : n == 1 ? a1 : a2) * NeedleSense, _nAx[n]);
                    _needles[n].localRotation = q;
                    _needles[n].localPosition = _nC[n] - q * _nC[n];
                }
            }
            catch { _needleFail = true; }
        }

        public void Update(bool inCockpit, Camera cam)
        {
            if (inCockpit) UpdateNeedles();
            if (_ac == null) return;
            int ls = inCockpit ? 1 : 0;
            if (ls != _layerState)
            {
                _layerState = ls;
                int layer = inCockpit ? CockpitLayer : ExteriorLayer;
                foreach (var go in LayerObjects) if (go != null) go.layer = layer;
            }
            if (_dumpAt > 0f && Time.unscaledTime > _dumpAt) { _dumpAt = -1f; DumpTac(); }
            SoundTick(inCockpit);
            GhostTick(inCockpit);
            SmudgeTick(inCockpit);
            KeyTick();
            if (inCockpit && !_wasInCockpit) { _enteredAt = Time.unscaledTime; _hasRef = false; }
            _wasInCockpit = inCockpit;
            ShiftOn = false;
            if (inCockpit && cam != null && AlignEye)
            {
                Transform vp = null;
                try { vp = _ac != null ? _ac.cockpitViewPoint : null; } catch { }
                Vector3 d;
                if (vp != null)
                {
                    Vector3 rest = vp.position;
                    try { var csm = SceneSingleton<CameraStateManager>.i; if (csm != null) { Vector3 off = cam.transform.position - csm.transform.position; if (off.sqrMagnitude < 0.25f) rest += off; } } catch { }
                    d = _eyeRoot + EyeOffset - _root.InverseTransformPoint(rest);
                }
                else
                {
                    Vector3 camLocal = _root.InverseTransformPoint(cam.transform.position);
                    bool ahead = Vector3.Dot(cam.transform.forward, _root.forward) > 0.94f;
                    float since = Time.unscaledTime - _enteredAt;
                    if (!_hasRef) { _camRef = camLocal; _hasRef = true; }
                    else if (since < 2f) _camRef = camLocal;
                    else if (ahead) _camRef = Vector3.Lerp(_camRef, camLocal, Mathf.Clamp01(Time.unscaledDeltaTime / 4f));
                    d = _eyeRoot + EyeOffset - _camRef;
                }
                if (d.magnitude > 1.2f) d = d.normalized * 1.2f;
                _shiftLocal = d;
                WorldShift = _root.TransformVector(d);
                ShiftOn = true;
                if (!_loggedView)
                {
                    _loggedView = true;
                    LogView(cam, d);
                }
            }
            if (_night != null) { _night.CullingMask = (1 << CockpitLayer) | (1 << ExteriorLayer); _night.Update(DisplayMats); }
            if (inCockpit) KeyLightTick();
            if (inCockpit) CockpitCamera.Active = this;
            else if (CockpitCamera.Active == this) CockpitCamera.Active = null;

            if (_displays.Count == 0) return;
            if (_centre != null && _tacRT == null && Time.unscaledTime > _nextTacSearch && (inCockpit || _tacTries < 8))
            {
                _nextTacSearch = Time.unscaledTime + 1f;
                _tacTries++;
                FindTac();
            }
            if (_tacRT != null)
            {
                float now = Time.unscaledTime;
                int mode = _tgtDisp != null && _tgtDisp.activeInHierarchy ? 1 : _landDisp != null && _landDisp.activeInHierarchy ? 2 : 0;
                if (_tacMode < 0)
                {
                    _tacMode = mode; _tacPending = -1;
                    ApplyTacArea(mode == 0 ? _radarUV : AreaOf(mode == 1 ? _tgtDisp : _landDisp));
                }
                else if (mode != _tacMode)
                {
                    if (_tacPending != mode) { _tacPending = mode; _tacSwitchAt = now + (_tacHold != null ? TacSwitchHold : 0f); }
                    else if (now >= _tacSwitchAt)
                    {
                        Rect r = mode == 0 ? _radarUV : AreaOf(mode == 1 ? _tgtDisp : _landDisp);
                        TyphoonPlugin.Instance?.LogInfo($"Typhoon cockpit: centre display shows {(mode == 0 ? "radar" : mode == 1 ? "target camera" : "landing camera")}, area {r}.");
                        _tacMode = mode; _tacPending = -1;
                        ApplyTacArea(r);
                    }
                }
                else
                {
                    _tacPending = -1;
                    if (now > _nextTacCheck)
                    {
                        _nextTacCheck = now + 0.25f;
                        Rect r = mode == 0 ? _radarUV : AreaOf(mode == 1 ? _tgtDisp : _landDisp);
                        if (r != _shownUV || _ownApplied != OwnRadarShown) ApplyTacArea(r);
                    }
                }
                if (_tacPending < 0 && !OwnRadarShown && _tacHold != null && cam != null && (inCockpit || (cam.transform.position - _root.position).sqrMagnitude < 30f * 30f))
                {
                    if (!_tacHold.IsCreated()) _tacHold.Create();
                    var prevRT = RenderTexture.active;
                    Graphics.Blit(_tacRT, _tacHold, _blitScale, _blitOffset);
                    RenderTexture.active = prevRT;
                }
            }
            if (cam == null || (cam.transform.position - _root.position).sqrMagnitude > 60f * 60f) return;
            if (_sadi != null && Time.unscaledTime >= _nextSadi)
            {
                _nextSadi = Time.unscaledTime + 1f / Mathf.Clamp(30f * Mathf.Clamp(DisplaySmoothness, 0.25f, 2f), 5f, 60f);
                try { Draw(_sadi); } catch (Exception e) { TyphoonPlugin.Instance?.LogError("Standby ADI: " + e.Message); _displays.Remove(_sadi); _sadi = null; }
            }
            if (inCockpit)
                try { var gp = _ac.GlobalPosition(); var fw = _root.forward; float hd = Mathf.Atan2(fw.x, fw.z) * Mathf.Rad2Deg; if (hd < 0) hd += 360f; TerrainMap.Keep(gp.x, gp.z, hd); } catch { }
            TerrainMap.Tick();
            if (!inCockpit && Time.unscaledTime < _nextDraw) return;
            _nextDraw = Time.unscaledTime + 0.25f;
            float nowT = Time.unscaledTime;
            for (int pass = 0; pass < 2; pass++)
            {
                Display disp = null; float worst = 0f;
                foreach (var d in _displays)
                {
                    if (d == _sadi) continue;
                    float over = nowT - d.Next;
                    if (over >= 0f && (disp == null || over > worst)) { disp = d; worst = over; }
                }
                if (disp == null) break;
                disp.Next = nowT + 1f / Mathf.Clamp(PageRate(disp) * Mathf.Clamp(DisplaySmoothness, 0.25f, 2f), 2f, 60f);
                if (disp.Tac && _tacRT != null && OwnRadarShown) { try { Draw(disp); } catch (Exception e) { TyphoonPlugin.Instance?.LogError("Radar page: " + e.Message); OwnRadar = false; ApplyTacArea(_shownUV); } continue; }
                if (disp.Tac && _tacRT != null) { if (_barsOn) try { DrawBars(); } catch (Exception e) { TyphoonPlugin.Instance?.LogError("Target bars: " + e.Message); BarsOff(); _barTop = null; } continue; }
                try { Draw(disp); } catch (Exception e) { TyphoonPlugin.Instance?.LogError("Cockpit display: " + e.Message); _displays.Remove(disp); break; }
            }
        }

        internal static float DisplaySmoothness = 1f;

        float PageRate(Display d)
        {
            if (d.Name.EndsWith("_R")) return RightPage == 0 ? 30f : RightPage == 1 ? 20f : 6f;
            if (d.Name.EndsWith("_L")) return 24f;
            if (d.Tac) return 24f;
            return 6f;
        }

        void FindTac()
        {
            var ck = FindCockpit(_ac);
            if (ck == null) return;
            var ts = TacScreenF?.GetValue(ck) as TacScreen;
            Texture rt = ts != null ? TacRTF?.GetValue(ts) as Texture : null;
            if (rt == null)
            {
                var r = TacRenderF?.GetValue(ck) as Renderer;
                if (r != null && r.sharedMaterial != null)
                    foreach (var p in r.sharedMaterial.GetTexturePropertyNames())
                    {
                        var t = r.sharedMaterial.GetTexture(p) as RenderTexture;
                        if (t != null) { rt = t; break; }
                    }
            }
            if (rt == null) return;
            _tacRT = rt;
            try
            {
                var src = rt as RenderTexture;
                if (!TacCopy) throw new Exception("turned off in the config");
                _tacHold = src != null ? new RenderTexture(512, 512, 0, src.graphicsFormat) : new RenderTexture(512, 512, 0, RenderTextureFormat.ARGB32);
                _tacHold.name = "Typhoon_tac_copy"; _tacHold.useMipMap = false; _tacHold.filterMode = FilterMode.Bilinear; _tacHold.wrapMode = TextureWrapMode.Clamp;
                _tacHold.Create();
                SetTexture(_centre.Material, _tacHold);
            }
            catch (Exception e)
            {
                TyphoonPlugin.Instance?.LogInfo("Typhoon cockpit: no copy of the tactical screen (" + e.Message + "); showing it directly.");
                _tacHold = null;
                SetTexture(_centre.Material, rt);
            }
            Rect uv = new Rect(99f / 1024f, 1f - 353f / 512f, 346f / 1024f, 346f / 512f);
            string info = "default";
            try
            {
                var r = TacRenderF?.GetValue(ck) as Renderer;
                var mf = r != null ? r.GetComponent<MeshFilter>() : null;
                info = $"renderer '{(r != null ? r.name : "-")}', mesh '{(mf != null && mf.sharedMesh != null ? mf.sharedMesh.name : "-")}', readable {(mf != null && mf.sharedMesh != null && mf.sharedMesh.isReadable)}";
                if (mf != null && mf.sharedMesh != null && mf.sharedMesh.isReadable)
                {
                    var uvs = mf.sharedMesh.uv;
                    if (uvs != null && uvs.Length > 0)
                    {
                        float u0 = uvs.Min(v => v.x), u1 = uvs.Max(v => v.x), v0 = uvs.Min(v => v.y), v1 = uvs.Max(v => v.y);
                        info += $", uv {u0:0.###},{v0:0.###} - {u1:0.###},{v1:0.###}";

                    }
                }
            }
            catch { }
            if (TacArea == "auto")
            {
                float k = Mathf.Clamp(RadarZoom, 0.8f, 1.3f);
                float cx = 270f / 1024f, cy = 1f - 186f / 512f, hw = 165f / 1024f * k, hh = 165f / 512f * k;
                uv = new Rect(cx - hw, cy - hh, 2f * hw, 2f * hh);
                try { rt.wrapMode = TextureWrapMode.Clamp; } catch { }
                info += $", radar area x{k:0.00} on the scope";
            }
            if (TacArea != "auto")
            {
                var t = TacArea.Split(',');
                float x, y, w, h;
                if (t.Length == 4 && float.TryParse(t[0], NumberStyles.Float, CultureInfo.InvariantCulture, out x) && float.TryParse(t[1], NumberStyles.Float, CultureInfo.InvariantCulture, out y)
                    && float.TryParse(t[2], NumberStyles.Float, CultureInfo.InvariantCulture, out w) && float.TryParse(t[3], NumberStyles.Float, CultureInfo.InvariantCulture, out h) && w > 0.01f && h > 0.01f)
                    uv = new Rect(x, y, w, h);
            }
            TyphoonPlugin.Instance?.LogInfo("Typhoon cockpit: original tactical screen: " + info);
            if (!TyphoonPlugin.Locked) _dumpAt = Time.unscaledTime + 5f;
            _radarUV = uv;
            _tac = ts;
            if (ts != null)
            {
                const BindingFlags F = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
                _tacCam = typeof(TacScreen).GetField("cam", F)?.GetValue(ts) as Camera;
                _tgtDisp = typeof(TacScreen).GetField("targetCamDisplay", F)?.GetValue(ts) as GameObject;
                _landDisp = typeof(TacScreen).GetField("landingCamDisplay", F)?.GetValue(ts) as GameObject;
            }
            _tacMode = -1;
            TyphoonPlugin.Instance?.LogInfo($"Typhoon cockpit: tactical screen linked ({rt.width}x{rt.height}); target view '{(_tgtDisp != null ? _tgtDisp.name : "-")}', camera '{(_tacCam != null ? _tacCam.name : "-")}'.");
        }

        Rect AreaOf(GameObject go)
        {
            try
            {
                var rtf = go != null ? go.GetComponent<RectTransform>() : null;
                if (rtf == null || _tacCam == null) return new Rect(0, 0, 1, 1);
                var w = new Vector3[4];
                rtf.GetWorldCorners(w);
                float x0 = 1, y0 = 1, x1 = 0, y1 = 0;
                foreach (var p in w)
                {
                    var v = _tacCam.WorldToViewportPoint(p);
                    x0 = Mathf.Min(x0, v.x); y0 = Mathf.Min(y0, v.y); x1 = Mathf.Max(x1, v.x); y1 = Mathf.Max(y1, v.y);
                }
                x0 = Mathf.Clamp01(x0); y0 = Mathf.Clamp01(y0); x1 = Mathf.Clamp01(x1); y1 = Mathf.Clamp01(y1);
                if (x1 - x0 < 0.05f || y1 - y0 < 0.05f) return new Rect(0, 0, 1, 1);
                return new Rect(x0, y0, x1 - x0, y1 - y0);
            }
            catch { return new Rect(0, 0, 1, 1); }
        }

        bool _ownApplied;
        bool OwnRadarShown => OwnRadar && _tacMode == 0 && _centre != null && _centre.Canvas != null;

        void ApplyTacArea(Rect uv)
        {
            _shownUV = uv;
            var m = _centre.Material;
            _ownApplied = OwnRadarShown;
            if (OwnRadarShown)
            {
                SetTexture(m, _centre.Canvas.Tex);
                if (m.HasProperty("_BaseMap")) { m.SetTextureScale("_BaseMap", Vector2.one); m.SetTextureOffset("_BaseMap", Vector2.zero); }
                m.mainTextureScale = Vector2.one; m.mainTextureOffset = Vector2.zero;
                FitAspect(_centre, -1f);
                BarsOff();
                _nextDraw = 0f;
                return;
            }
            SetTexture(m, _tacHold != null ? (Texture)_tacHold : _tacRT);
            Vector2 scale = new Vector2(uv.width, uv.height), offset = new Vector2(uv.x, uv.y);
            if (FlipTac) { scale.y = -scale.y; offset.y = uv.y + uv.height; }
            if (_tacHold != null)
            {
                _blitScale = scale; _blitOffset = offset;
                scale = Vector2.one; offset = Vector2.zero;
            }
            if (m.HasProperty("_BaseMap")) { m.SetTextureScale("_BaseMap", scale); m.SetTextureOffset("_BaseMap", offset); }
            m.mainTextureScale = scale; m.mainTextureOffset = offset;
            float aspect = (uv.width * _tacRT.width) / Mathf.Max(1f, uv.height * _tacRT.height);
            FitAspect(_centre, Mathf.Abs(aspect - 1f) > 0.06f ? aspect : -1f);
            float bar = aspect > 1.06f ? (1f - 1f / aspect) * 0.5f : 0f;
            if (_tacMode == 1 && bar > 0.06f && _barTop != null && _barBot != null)
            {
                PlaceBar(_barTop, 0f, bar);
                PlaceBar(_barBot, 1f - bar, 1f);
                _barsOn = true;
                try { DrawBars(); } catch { }
            }
            else BarsOff();
        }

        void DumpTac()
        {
            var rt = _tacRT as RenderTexture;
            if (rt == null) return;
            try
            {
                var prev = RenderTexture.active;
                RenderTexture.active = rt;
                var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGBA32, false);
                tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                tex.Apply(false);
                RenderTexture.active = prev;
                var path = Path.Combine(BepInEx.Paths.ConfigPath, "TyphoonMod_tacscreen.png");
                File.WriteAllBytes(path, ImageConversion.EncodeToPNG(tex));
                UnityEngine.Object.Destroy(tex);
                TyphoonPlugin.Instance?.LogInfo("Typhoon cockpit: saved the tactical screen picture to " + path);
            }
            catch (Exception e) { TyphoonPlugin.Instance?.LogInfo("Typhoon cockpit: couldn't save the tactical screen picture: " + e.Message); }
        }

        static void FitAspect(Display d, float aspect)
        {
            if (d.Mesh == null || d.Base == null) return;
            var b = d.Base;
            if (aspect <= 0f) { SetRounded(d.Mesh, b, d.N, d.Radius, true, true); return; }
            Vector3 centre = (b[0] + b[1] + b[2] + b[3]) * 0.25f;
            Vector3 right = (b[1] - b[0]) * 0.5f, up = (b[0] - b[3]) * 0.5f;
            float w = right.magnitude, h = up.magnitude;
            float sx = 1f, sy = 1f;
            if (aspect > w / h) sy = (w / aspect) / h; else sx = (h * aspect) / w;
            right *= sx; up *= sy;
            SetRounded(d.Mesh, new[] { centre - right + up, centre + right + up, centre + right - up, centre - right - up }, d.N, 0f, false, false);
        }

        void LogView(Camera cam, Vector3 d)
        {
            try
            {
                var sb = new System.Text.StringBuilder();
                sb.AppendLine($"Typhoon cockpit view: eye shift {d.x:0.00}, {d.y:0.00}, {d.z:0.00} m (right, up, forward).");
                foreach (var c in Camera.allCameras)
                    sb.AppendLine($"  camera '{c.name}' depth {c.depth} near {c.nearClipPlane:0.###} mask 0x{c.cullingMask:X} rt {(c.targetTexture != null)} dist {(c.transform.position - PilotPosition).magnitude:0.0} m");
                var layers = _visual.OriginalCockpit.Where(r => r != null).GroupBy(r => r.gameObject.layer).Select(g => $"{g.Key}({LayerMask.LayerToName(g.Key)})x{g.Count()}");
                sb.AppendLine("  original cockpit layers: " + string.Join(", ", layers));
                sb.Append("  Typhoon interior layer: " + string.Join(", ", _visual.Interior.Where(r => r != null).Select(r => r.gameObject.layer).Distinct()));
                TyphoonPlugin.Instance?.LogInfo(sb.ToString());
            }
            catch { }
        }

        void Draw(Display d)
        {
            var c = d.Canvas;
            if (d.Name == "ufcp") MfdPages.Ufcp(c, UfcpData());
            else if (d.Name == "dwp") MfdPages.Dwp(c, DwpData());
            else if (d.Name == "sadi") MfdPages.Sadi(c, FlightData());
            else if (d.Name == "mdef")
            {
                var md = MdefData(d.Canvas);
                if (md.Text == null && d.Alt != null) c = d.Alt;
                if (d.Linked != c) { d.Linked = c; SetTexture(d.Material, c.Tex); }
                MfdPages.Mdef(c, md);
            }
            else if (d.Name.EndsWith("_L"))
            {
                if (LeftPage == 1) MfdPages.Fuel(c, EngineData());
                else if (LeftPage == 2) MfdPages.Hyd(c, EngineData(), FlightData());
                else MfdPages.Engine(c, EngineData());
            }
            else if (d.Name.EndsWith("_R"))
            {
                if (RightPage == 1)
                {
                    var fd = FlightData();
                    var mi = TerrainMap.Get(fd.PosX, fd.PosZ, fd.Heading);
                    if (mi == null && !TerrainMap.Unavailable) { MfdPages.Flight(c, fd); _nextDraw = 0f; }
                    else MfdPages.Map(c, fd, mi);
                }
                else if (RightPage == 2) MfdPages.Stores(c, StoresData());
                else MfdPages.Flight(c, FlightData());
            }
            else if (OwnRadar) MfdPages.Radar(c, RadarData());
            else MfdPages.Tac(c, FlightData());
            c.Apply();
        }

        MfdPages.UfcpInfo UfcpData()
        {
            var t = TargetData();
            var u = new MfdPages.UfcpInfo { Target = t, Blink = (Time.unscaledTime % 0.8f) < 0.5f };
            u.FuelLevel = Mathf.Clamp01(_ac.fuelLevel);
            try { if (FuelQtyM != null) u.FuelKg = Convert.ToSingle(FuelQtyM.Invoke(_ac, null)); } catch { }
            u.Time = Time.timeSinceLevelLoad;
            u.Armed = t.State == "READY" || t.State == "RELOAD";
            float ra = 9999f; try { ra = _ac.radarAlt; } catch { }
            u.GearWarn = !_ac.gearDeployed && ra < 120f && _ac.speed < 110f;
            u.Caution = u.FuelLevel < 0.15f || u.GearWarn;
            return u;
        }

        MfdPages.StoresInfo StoresData()
        {
            var s = new MfdPages.StoresInfo();
            try
            {
                var t = TargetData();
                s.State = t.State ?? "SAFE";
                s.Gear = _ac.gearDeployed;
                var cur = _ac.weaponManager != null ? _ac.weaponManager.currentWeaponStation : null;
                if (_ac.weaponStations != null)
                    foreach (var ws in _ac.weaponStations)
                    {
                        if (ws == null || ws.WeaponInfo == null) continue;
                        var wi = ws.WeaponInfo;
                        s.Items.Add(new MfdPages.StoreItem { Name = (wi.shortName ?? wi.weaponName ?? "?").ToUpperInvariant(), Ammo = ws.Ammo, Full = ws.FullAmmo, Selected = ws == cur });
                    }
                try { if (_ac.countermeasureManager != null) s.Flares = Mathf.Clamp01(_ac.countermeasureManager.GetFlareAmmoProportion()); } catch { }
            }
            catch { }
            return s;
        }

        internal static int LeftPage, RightPage;
        internal static KeyCode LeftPageKey = KeyCode.LeftBracket, RightPageKey = KeyCode.RightBracket;
        internal static float CanopyReflections = 0f;
        static TyphoonCockpit _active;

        internal static void KeyDown(KeyCode k)
        {
            if (_active == null || !_active._wasInCockpit) return;
            if (k == LeftPageKey) { LeftPage = (LeftPage + 1) % 3; CockpitSounds.Click(); _active._nextDraw = 0f; _active.PressKey("L" + LeftPage); }
            else if (k == RightPageKey) { RightPage = (RightPage + 1) % 3; CockpitSounds.Click(); _active._nextDraw = 0f; _active.PressKey("R" + RightPage); }
        }

        internal static bool KeyPressAnim = true;
        sealed class KeySlot { public Mesh Mesh; public int[] Idx; public Vector3 Off; }
        sealed class KeyPress { public List<KeySlot> Slots; public float T0; }
        Dictionary<string, List<KeySlot>> _keySlots;
        readonly Dictionary<Mesh, Vector3[]> _keyBase = new Dictionary<Mesh, Vector3[]>();
        readonly Dictionary<Mesh, Vector3[]> _keyWork = new Dictionary<Mesh, Vector3[]>();
        readonly List<KeyPress> _presses = new List<KeyPress>();
        bool _keyFail;
        const float KeyDepth = 0.0016f, KeyTime = 0.24f;

        sealed class KeyCluster { public float Lo, Hi, A0 = 1e9f, A1 = -1e9f, B0 = 1e9f, B1 = -1e9f; public List<int> Idx = new List<int>(); }

        static List<KeyCluster> Clusters(List<KeyValuePair<float, int>> pts, Vector2[] ab)
        {
            var res = new List<KeyCluster>();
            pts.Sort((x, y) => x.Key.CompareTo(y.Key));
            KeyCluster cur = null;
            foreach (var p in pts)
            {
                if (cur == null || p.Key - cur.Hi > 0.004f) { cur = new KeyCluster { Lo = p.Key }; res.Add(cur); }
                cur.Hi = p.Key; cur.Idx.Add(p.Value);
                var q = ab[p.Value];
                cur.A0 = Mathf.Min(cur.A0, q.x); cur.A1 = Mathf.Max(cur.A1, q.x); cur.B0 = Mathf.Min(cur.B0, q.y); cur.B1 = Mathf.Max(cur.B1, q.y);
            }
            return res;
        }

        void BuildKeySlots()
        {
            _keySlots = new Dictionary<string, List<KeySlot>>();
            Display dR = null;
            foreach (var d in _displays) if (d.Name == "mfd_R") dR = d;
            Transform keysT = null, labT = null; Mesh keysM = null, labM = null;
            foreach (var r in _visual.Interior)
            {
                if (r == null) continue;
                bool isK = r.name == "Typhoon_cockpit_keys", isL = r.name == "Typhoon_cockpit_labels";
                if (!isK && !isL) continue;
                var mf = r.GetComponent<MeshFilter>();
                if (mf == null || mf.sharedMesh == null || !mf.sharedMesh.isReadable) continue;
                if (isK) { keysT = r.transform; keysM = mf.sharedMesh; } else { labT = r.transform; labM = mf.sharedMesh; }
            }
            if (dR == null || dR.Renderer == null || keysM == null) { _keyFail = true; return; }
            var tr = dR.Renderer.transform;
            Vector3 tl = tr.TransformPoint(dR.Base[0]), trc = tr.TransformPoint(dR.Base[1]), br = tr.TransformPoint(dR.Base[2]), bl = tr.TransformPoint(dR.Base[3]);
            Vector3 o = (tl + trc + br + bl) * 0.25f, u = (trc - tl).normalized, v = (tl - bl).normalized;
            Vector3 n = tr.TransformDirection(dR.N).normalized;
            float mg = Mathf.Clamp(DisplayMargin, 0f, 0.012f);
            float hw = (trc - tl).magnitude * 0.5f + mg, hh = (tl - bl).magnitude * 0.5f + mg;
            var kv = keysM.vertices;
            var ab = new Vector2[kv.Length];
            var row = new List<KeyValuePair<float, int>>(); var col = new List<KeyValuePair<float, int>>();
            for (int i = 0; i < kv.Length; i++)
            {
                Vector3 p = keysT.TransformPoint(kv[i]) - o;
                float a = Vector3.Dot(p, u), b = Vector3.Dot(p, v), w = Vector3.Dot(p, n);
                ab[i] = new Vector2(a, b);
                if (Mathf.Abs(w) > 0.03f) continue;
                if (b > -hh - 0.038f && b < -hh - 0.003f && Mathf.Abs(a) < hw + 0.006f) row.Add(new KeyValuePair<float, int>(a, i));
                else if (a > hw + 0.003f && a < hw + 0.038f && Mathf.Abs(b) < hh + 0.016f) col.Add(new KeyValuePair<float, int>(b, i));
            }
            var rows = Clusters(row, ab); var cols = Clusters(col, ab);
            Vector3[] lv = labM != null ? labM.vertices : null;
            Vector3 offK = keysT.InverseTransformVector(-n * KeyDepth);
            Vector3 offL = labT != null ? labT.InverseTransformVector(-n * KeyDepth) : Vector3.zero;
            Action<string, List<KeyCluster>, int> add = (name, list, index) =>
            {
                if (index < 0 || index >= list.Count) return;
                var c = list[index];
                var slots = new List<KeySlot> { new KeySlot { Mesh = keysM, Idx = c.Idx.ToArray(), Off = offK } };
                if (lv != null)
                {
                    var li = new List<int>();
                    for (int i = 0; i < lv.Length; i++)
                    {
                        Vector3 p = labT.TransformPoint(lv[i]) - o;
                        float a = Vector3.Dot(p, u), b = Vector3.Dot(p, v);
                        if (a > c.A0 - 0.0015f && a < c.A1 + 0.0015f && b > c.B0 - 0.0015f && b < c.B1 + 0.0015f && Mathf.Abs(Vector3.Dot(p, n)) < 0.03f) li.Add(i);
                    }
                    if (li.Count > 0) slots.Add(new KeySlot { Mesh = labM, Idx = li.ToArray(), Off = offL });
                }
                _keySlots[name] = slots;
            };
            add("L0", rows, 1); add("L1", rows, 0); add("L2", rows, 2);
            add("R0", cols, 1); add("R1", rows, 3); add("R2", cols, 0);
            _keyBase[keysM] = kv; _keyWork[keysM] = (Vector3[])kv.Clone();
            if (lv != null) { _keyBase[labM] = lv; _keyWork[labM] = (Vector3[])lv.Clone(); }
            TyphoonPlugin.Instance?.LogInfo($"Soft keys: {rows.Count} in the right display's lower row, {cols.Count} in its right column; {_keySlots.Count} press when their page is called.");
        }

        void PressKey(string slot)
        {
            if (!KeyPressAnim || _keyFail || _visual == null) return;
            try
            {
                if (_keySlots == null) BuildKeySlots();
                List<KeySlot> s;
                if (_keySlots != null && _keySlots.TryGetValue(slot, out s)) _presses.Add(new KeyPress { Slots = s, T0 = Time.unscaledTime });
            }
            catch (Exception e) { _keyFail = true; TyphoonPlugin.Instance?.LogError("Soft key press: " + e.Message); }
        }

        void KeyTick()
        {
            if (_presses.Count == 0 || _keyFail) return;
            try
            {
                float now = Time.unscaledTime;
                _presses.RemoveAll(p => now - p.T0 > KeyTime);
                foreach (var kvp in _keyBase) Array.Copy(kvp.Value, _keyWork[kvp.Key], kvp.Value.Length);
                foreach (var p in _presses)
                {
                    float t = (now - p.T0) / KeyTime;
                    float k = t < 0.2f ? t / 0.2f : (t < 0.55f ? 1f : Mathf.Clamp01((1f - t) / 0.45f));
                    foreach (var s in p.Slots)
                    {
                        var w = _keyWork[s.Mesh];
                        Vector3 off = s.Off * k;
                        for (int i = 0; i < s.Idx.Length; i++) w[s.Idx[i]] += off;
                    }
                }
                foreach (var kvp in _keyWork) if (kvp.Key != null) kvp.Key.vertices = kvp.Value;
            }
            catch (Exception e) { _keyFail = true; TyphoonPlugin.Instance?.LogError("Soft key press: " + e.Message); }
        }

        bool _sGear, _sBrake, _sInit; string _sState, _sWeapon; float _nextSound;
        readonly HashSet<string> _redOn = new HashSet<string>();

        void SoundTick(bool inCockpit)
        {
            if (!inCockpit) { if (_sInit) { CockpitSounds.Missile(false); _sInit = false; } return; }
            _active = this;
            if (Time.unscaledTime < _nextSound) return;
            _nextSound = Time.unscaledTime + 0.1f;
            try
            {
                var t = TargetData();
                var f = FlightData();
                if (_sInit)
                {
                    if (f.Gear != _sGear) CockpitSounds.Clunk();
                    if (f.Airbrake != _sBrake) CockpitSounds.Click();
                    if ((t.State ?? "") != (_sState ?? "") && (t.State == "READY" || t.State == "SAFE")) CockpitSounds.Click();
                    if ((t.Weapon ?? "") != (_sWeapon ?? "")) CockpitSounds.Click();
                }
                _sGear = f.Gear; _sBrake = f.Airbrake; _sState = t.State; _sWeapon = t.Weapon;
                CockpitSounds.Missile(t.MissileWarn);
                var w = DwpData();
                bool fresh = false;
                foreach (var it in w.Items)
                {
                    if (!it.Red || it.Text == "MISSILE") continue;
                    if (it.On) { if (_redOn.Add(it.Text) && _sInit) fresh = true; }
                    else _redOn.Remove(it.Text);
                }
                if (fresh) CockpitSounds.Attention();
                _sInit = true;
            }
            catch { }
        }

        sealed class Ghost { public Material Src, Mat; public MeshRenderer R; }
        readonly List<Ghost> _ghosts = new List<Ghost>();
        float _nextGhost;

        void MakeGhosts(Transform parent, Matrix4x4 toParent, int layer)
        {
            if (CanopyReflections <= 0f) return;
            var sprite = Shader.Find("Sprites/Default");
            if (sprite == null) return;
            foreach (var d in _displays)
            {
                if (d.Tac || !(d.Name.EndsWith("_L") || d.Name.EndsWith("_R")) || d.Renderer == null) continue;
                var mf = d.Renderer.GetComponent<MeshFilter>();
                if (mf == null || mf.sharedMesh == null) continue;
                Matrix4x4 toP = parent.worldToLocalMatrix * d.Renderer.transform.localToWorldMatrix;
                for (int side = -1; side <= 1; side += 2)
                {
                    Vector3 p0 = toParent.MultiplyPoint3x4(new Vector3(side * 0.445f, 0.95f, 7.0f));
                    Vector3 n = toParent.MultiplyVector(new Vector3(side * 0.94f, 0.34f, 0f)).normalized;
                    var src = mf.sharedMesh;
                    var v = src.vertices;
                    for (int i = 0; i < v.Length; i++)
                    {
                        Vector3 q = toP.MultiplyPoint3x4(v[i]);
                        v[i] = q - 2f * Vector3.Dot(q - p0, n) * n;
                    }
                    var m = new Mesh { name = d.Name + "_ghost" };
                    m.vertices = v; m.uv = src.uv; m.triangles = src.triangles;
                    m.RecalculateBounds();
                    var go = new GameObject("Typhoon_" + d.Name + (side < 0 ? "_reflL" : "_reflR")) { layer = layer };
                    go.transform.SetParent(parent, false);
                    go.AddComponent<MeshFilter>().sharedMesh = m;
                    var mr = go.AddComponent<MeshRenderer>();
                    mr.shadowCastingMode = ShadowCastingMode.Off; mr.receiveShadows = false;
                    var mat = new Material(sprite) { name = "Typhoon_reflection", renderQueue = 3050 };
                    mat.color = new Color(0f, 0f, 0f, 0f);
                    mr.sharedMaterial = mat; mr.enabled = false;
                    LayerObjects.Add(go);
                    _ghosts.Add(new Ghost { Src = d.Material, Mat = mat, R = mr });
                }
            }
        }

        internal static float DisplaySmudges = 0f;
        sealed class Smudge { public MeshRenderer R; public Material Mat; }
        readonly List<Smudge> _smudges = new List<Smudge>();
        static readonly Dictionary<int, Texture2D> SmudgeTexs = new Dictionary<int, Texture2D>();
        float _nextSmudge;

        void MakeSmudge(Transform parent, int layer, string name, Vector3[] c, Vector3 n, float rAbs, TyphoonVisual visual)
        {
            if (DisplaySmudges <= 0f) return;
            var sprite = Shader.Find("Sprites/Default");
            if (sprite == null) return;
            var q = (Vector3[])c.Clone();
            for (int i = 0; i < 4; i++) q[i] += n * 0.0006f;
            var go = MakeQuad(parent, layer, "Typhoon_" + name + "_smudge", q, n, null);
            SetRounded(go.GetComponent<MeshFilter>().sharedMesh, q, n, rAbs, true, true);
            var mr = go.GetComponent<MeshRenderer>();
            mr.shadowCastingMode = ShadowCastingMode.Off; mr.receiveShadows = false;
            int seed = Math.Abs(name.GetHashCode()) % 5;
            var mat = new Material(sprite) { name = "Typhoon_smudge", renderQueue = 3040, mainTexture = SmudgeTex(seed) };
            mat.color = new Color(1f, 1f, 1f, 0f);
            mr.sharedMaterial = mat; mr.enabled = false;
            LayerObjects.Add(go);
            _smudges.Add(new Smudge { R = mr, Mat = mat });
        }

        static Texture2D SmudgeTex(int seed)
        {
            Texture2D t;
            if (SmudgeTexs.TryGetValue(seed, out t) && t != null) return t;
            const int S = 256;
            var rng = new System.Random(1234 + seed * 77);
            var a = new float[S * S];
            var g = new float[7 * 7];
            for (int i = 0; i < g.Length; i++) g[i] = (float)rng.NextDouble();
            for (int y = 0; y < S; y++)
                for (int x = 0; x < S; x++)
                {
                    float fx = x / (float)S * 6f, fy = y / (float)S * 6f;
                    int ix = (int)fx, iy = (int)fy; float tx = fx - ix, ty = fy - iy;
                    tx = tx * tx * (3 - 2 * tx); ty = ty * ty * (3 - 2 * ty);
                    float v = Mathf.Lerp(Mathf.Lerp(g[iy * 7 + ix], g[iy * 7 + ix + 1], tx), Mathf.Lerp(g[(iy + 1) * 7 + ix], g[(iy + 1) * 7 + ix + 1], tx), ty);
                    a[y * S + x] = 0.18f * v * v;
                }
            int nf = 6 + rng.Next(4);
            for (int k = 0; k < nf; k++)
            {
                bool edge = rng.NextDouble() < 0.7;
                float cx = edge ? (rng.NextDouble() < 0.5 ? 0.08f + 0.10f * (float)rng.NextDouble() : 0.82f + 0.10f * (float)rng.NextDouble()) : 0.2f + 0.6f * (float)rng.NextDouble();
                float cy = 0.1f + 0.8f * (float)rng.NextDouble();
                if (rng.NextDouble() < 0.5) { float tmp = cx; cx = cy; cy = tmp; }
                float rx = 0.035f + 0.02f * (float)rng.NextDouble(), ry = rx * (1.25f + 0.25f * (float)rng.NextDouble());
                float ang = (float)(rng.NextDouble() * Math.PI), ca = Mathf.Cos(ang), sa = Mathf.Sin(ang);
                float freq = 90f + 25f * (float)rng.NextDouble(), str = 0.30f + 0.25f * (float)rng.NextDouble();
                int x0 = Mathf.Max(0, (int)((cx - 0.08f) * S)), x1 = Mathf.Min(S - 1, (int)((cx + 0.08f) * S));
                int y0 = Mathf.Max(0, (int)((cy - 0.08f) * S)), y1 = Mathf.Min(S - 1, (int)((cy + 0.08f) * S));
                for (int y = y0; y <= y1; y++)
                    for (int x = x0; x <= x1; x++)
                    {
                        float dx = x / (float)S - cx, dy = y / (float)S - cy;
                        float u = (dx * ca + dy * sa) / rx, v = (-dx * sa + dy * ca) / ry;
                        float r = Mathf.Sqrt(u * u + v * v);
                        if (r > 1.3f) continue;
                        float env = Mathf.Exp(-r * r * 2.2f);
                        float ridge = 0.82f + 0.18f * Mathf.Sin(r * rx * freq * 6.2832f);
                        a[y * S + x] += str * env * ridge;
                    }
            }
            int nw = 1 + rng.Next(2);
            for (int k = 0; k < nw; k++)
            {
                float cx = (float)rng.NextDouble(), cy = -0.3f - 0.4f * (float)rng.NextDouble(), R = 0.9f + 0.5f * (float)rng.NextDouble(), w = 0.05f;
                for (int y = 0; y < S; y++)
                    for (int x = 0; x < S; x++)
                    {
                        float d = Mathf.Abs(Mathf.Sqrt(Mathf.Pow(x / (float)S - cx, 2) + Mathf.Pow(y / (float)S - cy, 2)) - R);
                        if (d < w) a[y * S + x] += 0.20f * (1 - d / w) * (0.6f + 0.4f * Mathf.Sin(x * 0.7f + y * 0.3f));
                    }
            }
            var px = new Color32[S * S];
            for (int i = 0; i < px.Length; i++) { byte al = (byte)Mathf.Clamp(a[i] * 255f, 0, 255); px[i] = new Color32(210, 214, 218, al); }
            t = new Texture2D(S, S, TextureFormat.RGBA32, true) { name = "Typhoon_smudge" + seed, wrapMode = TextureWrapMode.Clamp };
            t.SetPixels32(px); t.Apply(true, true);
            SmudgeTexs[seed] = t;
            return t;
        }

        void SmudgeTick(bool inCockpit)
        {
            if (_smudges.Count == 0 || Time.unscaledTime < _nextSmudge) return;
            _nextSmudge = Time.unscaledTime + 0.5f;
            float night = _night != null ? _night.Level : 0f;
            float a = inCockpit ? DisplaySmudges * Mathf.Lerp(1f, 0.2f, night) : 0f;
            foreach (var sm in _smudges)
            {
                if (sm.R == null) continue;
                bool on = a > 0.004f;
                if (sm.R.enabled != on) sm.R.enabled = on;
                if (on) sm.Mat.color = new Color(1f, 1f, 1f, a);
            }
        }

        void GhostTick(bool inCockpit)
        {
            if (_ghosts.Count == 0 || Time.unscaledTime < _nextGhost) return;
            _nextGhost = Time.unscaledTime + 0.5f;
            float night = _night != null ? _night.Level : 0f;
            float a = inCockpit ? Mathf.Clamp01(CanopyReflections * night) : 0f;
            foreach (var g in _ghosts)
            {
                if (g.R == null) continue;
                bool on = a > 0.004f && g.Src != null;
                if (g.R.enabled != on) g.R.enabled = on;
                if (!on) continue;
                Texture t = g.Src.HasProperty("_BaseMap") ? g.Src.GetTexture("_BaseMap") : g.Src.mainTexture;
                if (g.Mat.mainTexture != t) g.Mat.mainTexture = t;
                g.Mat.color = new Color(1f, 1f, 1f, a);
            }
        }

        MfdPages.MdefInfo MdefData(MfdCanvas c)
        {
            var f = FlightData();
            var m = new MfdPages.MdefInfo { PosX = f.PosX, PosZ = f.PosZ, Heading = f.Heading, Blink = (Time.unscaledTime % 0.8f) < 0.5f };
            int cols = Math.Max(6, (c.W - 6) / 10), rows = Math.Max(2, (c.H - 4) / 17);
            float age;
            var msg = ChatFeed.Current(cols * (rows - 1), out age);
            if (msg != null) { m.From = msg.From; m.Text = msg.Text; m.Age = age; }
            return m;
        }

        internal static bool KeyLights = true;
        List<CockpitDef.KeyDef> _keyDefs;
        sealed class KeyLight { public string State; public int[] Idx; public Vector2[] On, Off; public int Shown = -1; }
        List<KeyLight> _keyLights;
        Mesh _klMesh; Vector2[] _klUv;
        float _nextKeyLights;
        bool _klFail, _gearCycled, _klWasOn = true;
        static readonly FieldInfo IrModeF = typeof(TargetCam).GetField("IRMode", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);

        void BuildKeyLights()
        {
            _keyLights = new List<KeyLight>();
            if (_keyDefs == null || _keyDefs.Count == 0) { TyphoonPlugin.Instance?.LogInfo("Key lights: no typhoon_keys.txt in this model; the legends stay as painted."); return; }
            Mesh labM = null;
            foreach (var r in _visual.Interior)
            {
                if (r == null || r.name != "Typhoon_cockpit_labels") continue;
                var mf = r.GetComponent<MeshFilter>();
                if (mf != null && mf.sharedMesh != null && mf.sharedMesh.isReadable) labM = mf.sharedMesh;
            }
            if (labM == null) { _klFail = true; TyphoonPlugin.Instance?.LogInfo("Key lights: the label mesh (cockpit_labels) was not found or cannot be read."); return; }
            var uv = labM.uv;
            if (uv == null || uv.Length == 0) { _klFail = true; return; }
            const float E = 0.00012f;
            Func<Vector2, bool, Vector4, bool> onCorner = (q, fl, rc) =>
            {
                float v = fl ? 1f - q.y : q.y;
                return (Mathf.Abs(q.x - rc.x) < E || Mathf.Abs(q.x - rc.z) < E) && (Mathf.Abs(v - rc.y) < E || Mathf.Abs(v - rc.w) < E);
            };
            int best = -1; bool flip = false;
            for (int pass = 0; pass < 2; pass++)
            {
                int hit = 0;
                foreach (var k in _keyDefs)
                    for (int i = 0; i < uv.Length; i++)
                        if (onCorner(uv[i], pass == 1, k.On) || onCorner(uv[i], pass == 1, k.Off)) hit++;
                if (hit > best) { best = hit; flip = pass == 1; }
            }
            int partial = 0;
            foreach (var k in _keyDefs)
            {
                var idx = new List<int>(); var on = new List<Vector2>(); var off = new List<Vector2>();
                for (int i = 0; i < uv.Length; i++)
                {
                    bool isOn = onCorner(uv[i], flip, k.On), isOff = !isOn && onCorner(uv[i], flip, k.Off);
                    if (!isOn && !isOff) continue;
                    Vector4 rc = isOn ? k.On : k.Off;
                    float v = flip ? 1f - uv[i].y : uv[i].y;
                    bool right = Mathf.Abs(uv[i].x - rc.z) < E, top = Mathf.Abs(v - rc.w) < E;
                    float a1 = right ? k.On.z : k.On.x, b1 = top ? k.On.w : k.On.y;
                    float a0 = right ? k.Off.z : k.Off.x, b0 = top ? k.Off.w : k.Off.y;
                    idx.Add(i); on.Add(new Vector2(a1, flip ? 1f - b1 : b1)); off.Add(new Vector2(a0, flip ? 1f - b0 : b0));
                }
                if (idx.Count == 4 || idx.Count == 6) _keyLights.Add(new KeyLight { State = k.State, Idx = idx.ToArray(), On = on.ToArray(), Off = off.ToArray() });
                else if (idx.Count > 0) partial++;
            }
            if (_keyLights.Count < _keyDefs.Count)
                TyphoonPlugin.Instance?.LogInfo($"Key lights: {_keyDefs.Count - _keyLights.Count} legend(s) of typhoon_keys.txt were not found in the label mesh ({partial} with an odd number of corners) - typhoon_keys.txt and typhoon.obj must come from the same build.");
            if (_keyLights.Count * 2 < _keyDefs.Count) { _keyLights.Clear(); _klFail = true; TyphoonPlugin.Instance?.LogInfo("Key lights: off (too few legends found); the legends stay as painted."); return; }
            _klMesh = labM; _klUv = uv;
            TyphoonPlugin.Instance?.LogInfo($"Key lights: {_keyLights.Count} of {_keyDefs.Count} legends follow the aircraft's state (v {(flip ? "turned over" : "as written")}; {string.Join(", ", _keyLights.Select(k => k.State).Distinct().OrderBy(x => x))}).");
        }

        void KeyLightTick()
        {
            if (_klFail || _visual == null || Time.unscaledTime < _nextKeyLights) return;
            _nextKeyLights = Time.unscaledTime + 0.25f;
            try
            {
                if (_keyLights == null) BuildKeyLights();
                if (_keyLights == null || _keyLights.Count == 0 || _klMesh == null) return;
                if (!KeyLights && !_klWasOn) return;
                var st = new Dictionary<string, bool>();
                if (KeyLights)
                {
                    var t = TargetData();
                    float ra = 9999f; try { ra = _ac.radarAlt; } catch { }
                    bool air = ra > 15f, gear = _ac.gearDeployed;
                    float thr = Inputs()[3];
                    if (!air) _gearCycled = false; else if (!gear) _gearCycled = true;
                    bool radar = false; try { radar = _ac.radar != null && _ac.radar.activated; } catch { }
                    bool ir = false; try { ir = _ac.targetCam != null && IrModeF != null && (bool)IrModeF.GetValue(_ac.targetCam); } catch { }
                    bool dass = t.MissileWarn || t.RadarLock || t.Spike;
                    bool ready = t.State == "READY" || t.State == "RELOAD";
                    bool combat = air && !gear && (t.Targets > 0 || dass);
                    bool takeoff = (!air && thr > 0.6f) || (air && gear && !_gearCycled);
                    float fuel = Mathf.Clamp01(_ac.fuelLevel);
                    bool eng = false; try { eng = _ac.Ignition; } catch { }
                    bool fa = false; try { fa = _ac.flightAssist; } catch { }
                    st["radar"] = radar; st["noradar"] = !radar;
                    st["tcam"] = _tacMode == 1; st["map"] = _tacMode <= 0; st["ir"] = ir && _tacMode == 1;
                    st["dass"] = dass; st["wpn"] = ready; st["atk"] = combat; st["lock"] = t.Targets > 0;
                    st["stor"] = RightPage == 2; st["hud"] = RightPage == 0; st["wpt"] = RightPage == 1;
                    st["peng"] = LeftPage == 0; st["pfuel"] = LeftPage == 1; st["phyd"] = LeftPage == 2;
                    st["fuel"] = fuel < 0.25f; st["eng"] = eng; st["fa"] = fa;
                    st["app"] = (air && gear && _gearCycled) || _tacMode == 2;
                    st["low"] = air && ra < 150f;
                    st["mids"] = ChatFeed.Recent;
                    st["night"] = _night != null && _night.Level > 0.5f;
                    st["gnd"] = !air && !takeoff; st["to"] = takeoff; st["aa"] = combat; st["nav"] = air && !takeoff && !combat;
                    st["on"] = true; st["off"] = false;
                }
                bool changed = false;
                foreach (var k in _keyLights)
                {
                    bool on; if (!KeyLights) on = true; else if (!st.TryGetValue(k.State, out on)) on = false;
                    int want = on ? 1 : 0;
                    if (want == k.Shown) continue;
                    k.Shown = want; changed = true;
                    var src = on ? k.On : k.Off;
                    for (int i = 0; i < k.Idx.Length; i++) _klUv[k.Idx[i]] = src[i];
                }
                _klWasOn = KeyLights;
                if (changed) _klMesh.uv = _klUv;
            }
            catch (Exception e) { _klFail = true; TyphoonPlugin.Instance?.LogError("Key lights: " + e.Message); }
        }

        MfdPages.DwpInfo DwpData()
        {
            var f = FlightData();
            var t = TargetData();
            var w = new MfdPages.DwpInfo { Blink = (Time.unscaledTime % 0.8f) < 0.5f };
            float fuel = Mathf.Clamp01(_ac.fuelLevel);
            float ra = 9999f; try { ra = _ac.radarAlt; } catch { }
            bool air = ra > 15f;
            w.Items.Add(new MfdPages.DwpItem("FUEL LOW", fuel < 0.15f, true));
            w.Items.Add(new MfdPages.DwpItem("BINGO", fuel >= 0.15f && fuel < 0.25f, false));
            w.Items.Add(new MfdPages.DwpItem("GEAR", !_ac.gearDeployed && ra < 120f && _ac.speed < 110f, true));
            w.Items.Add(new MfdPages.DwpItem("PULL UP", air && ra < 150f && f.Vs < -40f, true));
            w.Items.Add(new MfdPages.DwpItem("MISSILE", t.MissileWarn, true));
            w.Items.Add(new MfdPages.DwpItem("RDR LOCK", Time.unscaledTime < _lockUntil, false));
            w.Items.Add(new MfdPages.DwpItem("SPIKE", Time.unscaledTime < _spikeUntil, false));
            w.Items.Add(new MfdPages.DwpItem("OVER G", Mathf.Abs(f.G) > 9f, false));
            w.Items.Add(new MfdPages.DwpItem("HIGH AOA", air && f.Aoa > 25f, false));
            w.Items.Add(new MfdPages.DwpItem("LOW SPEED", air && f.Speed < 60f, false));
            w.Items.Add(new MfdPages.DwpItem("AIRBRAKE", f.Airbrake, false));
            w.Items.Add(new MfdPages.DwpItem("MASTER ARM", t.State == "READY" || t.State == "RELOAD", false, true));
            return w;
        }

        MfdPages.EngineInfo EngineData()
        {
            var e = new MfdPages.EngineInfo();
            float[] inp = Inputs();
            e.Throttle = Mathf.Clamp01(inp[3]);
            e.Reheat = _visual.AfterburnerAmount();
            e.Nozzle = _visual.NozzleOpenness();
            var rpm = new List<float>();
            if (_engines != null)
                foreach (var en in _engines)
                {
                    if (en == null || RpmF == null || MaxRpmF == null) continue;
                    float mx = (float)MaxRpmF.GetValue(en);
                    if (mx > 1f) rpm.Add(Mathf.Clamp01((float)RpmF.GetValue(en) / mx));
                }
            if (rpm.Count == 0) rpm.Add(0f);
            if (rpm.Count == 1) rpm.Add(rpm[0]);
            e.RpmL = rpm[0]; e.RpmR = rpm[1];
            float qty = 0f;
            try { if (FuelQtyM != null) qty = Convert.ToSingle(FuelQtyM.Invoke(_ac, null)); } catch { }
            e.FuelKg = qty;
            e.FuelLevel = Mathf.Clamp01(_ac.fuelLevel);
            float now = Time.time;
            if (_fuelPrev < 0f) { _fuelPrev = qty; _fuelT = now; }
            else if (now - _fuelT > 0.5f)
            {
                float flow = Mathf.Max(0f, (_fuelPrev - qty) / (now - _fuelT) * 60f);
                _fuelFlow = Mathf.Lerp(_fuelFlow, flow, 0.3f);
                _fuelPrev = qty; _fuelT = now;
            }
            e.FuelFlow = _fuelFlow;
            e.Blink = (Time.unscaledTime % 1f) < 0.6f;
            return e;
        }

        MfdPages.FlightInfo FlightData()
        {
            var f = new MfdPages.FlightInfo();
            var t = _root;
            Vector3 fw = t.forward, r = t.right, u = t.up;
            f.Pitch = Mathf.Asin(Mathf.Clamp(fw.y, -1f, 1f)) * Mathf.Rad2Deg;
            f.Roll = -Mathf.Atan2(r.y, u.y) * Mathf.Rad2Deg;
            f.Heading = Mathf.Atan2(fw.x, fw.z) * Mathf.Rad2Deg; if (f.Heading < 0) f.Heading += 360f;
            f.Speed = _ac.speed;
            float sos = 340f;
            try { var gp = _ac.GlobalPosition(); sos = LevelInfo.GetSpeedOfSound(gp.y); f.Altitude = gp.y; f.PosX = gp.x; f.PosZ = gp.z; } catch { }
            f.Mach = f.Speed / Mathf.Max(1f, sos);
            Vector3 vel = _ac.rb != null ? _ac.rb.velocity : Vector3.zero;
            f.Vs = vel.y;
            Vector3 lv = t.InverseTransformDirection(vel);
            f.Aoa = lv.z > 1f ? Mathf.Atan2(-lv.y, lv.z) * Mathf.Rad2Deg : 0f;
            f.G = _ac.gForce;
            f.Gear = _ac.gearDeployed;
            f.Airbrake = _visual.AirbrakeOpen() > 0.05f;
            try
            {
                var ws = _ac.weaponManager != null ? _ac.weaponManager.currentWeaponStation : null;
                if (ws != null && ws.WeaponInfo != null)
                {
                    f.Weapon = (ws.WeaponInfo.shortName ?? ws.WeaponInfo.weaponName ?? "").ToUpperInvariant();
                    f.Ammo = ws.Ammo;
                }
            }
            catch { }
            return f;
        }
    }

    internal static class Frame
    {
        public const float Margin = 0.045f;
        public const float Inset = 0.022f;
        static Material _mat;

        public static Material Material()
        {
            if (_mat != null) return _mat;
            const int S = 256;
            var tex = new Texture2D(S, S, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Clamp, name = "Typhoon_mfd_frame" };
            var px = new Color32[S * S];
            float full = 1f + 2f * Margin;
            float a = Margin / full;
            float r = 0.045f;
            float h = 0.5f - a;
            for (int y = 0; y < S; y++)
                for (int x = 0; x < S; x++)
                {
                    float u = (x + 0.5f) / S - 0.5f, v = (y + 0.5f) / S - 0.5f;
                    float qx = Mathf.Abs(u) - (h - r), qy = Mathf.Abs(v) - (h - r);
                    float outside = Mathf.Sqrt(Mathf.Max(qx, 0f) * Mathf.Max(qx, 0f) + Mathf.Max(qy, 0f) * Mathf.Max(qy, 0f)) + Mathf.Min(Mathf.Max(qx, qy), 0f) - r;
                    float d = outside * S;
                    float alpha = Mathf.Clamp01(d + 0.5f);
                    float rim = Mathf.Clamp01(1f - Mathf.Abs(d - 2.5f) / 2f);
                    byte g = (byte)(30 + rim * 34);
                    float edge = Mathf.Min(0.5f - Mathf.Abs(u), 0.5f - Mathf.Abs(v)) * S;
                    alpha *= Mathf.Clamp01(edge / 4f);
                    px[y * S + x] = new Color32(g, (byte)(g + 2), (byte)(g + 4), (byte)(alpha * 255f));
                }
            tex.SetPixels32(px);
            tex.Apply(true);
            var lit = Shader.Find("Universal Render Pipeline/Lit");
            var m = new Material(lit) { name = "Typhoon_mfd_frame" };
            m.SetTexture("_BaseMap", tex);
            m.SetColor("_BaseColor", Color.white);
            m.SetFloat("_Smoothness", 0.25f);
            m.SetFloat("_Metallic", 0f);
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", 0f);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_ZWrite", 0f);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            _mat = m;
            return m;
        }
    }

    internal sealed class NightLighting
    {
        readonly List<Light> _lights = new List<Light>();
        readonly List<float> _lightK = new List<float>();
        readonly List<KeyValuePair<Material, Vector2>> _mats = new List<KeyValuePair<Material, Vector2>>();
        readonly List<KeyValuePair<Material, Vector2>> _glow = new List<KeyValuePair<Material, Vector2>>();
        readonly Dictionary<Material, Color> _tint = new Dictionary<Material, Color>();
        internal int CullingMask = ~0;
        float _next, _night = -1f, _shown = -1f;
        Light _sun; float _nextSun;

        static readonly Color Flood = new Color(0.20f, 1.00f, 0.70f);

        public static NightLighting Setup(Transform parent, Transform root, Matrix4x4 modelToRoot, TyphoonVisual visual, BepInEx.Logging.ManualLogSource log)
        {
            var n = new NightLighting();
            Matrix4x4 toParent = parent.worldToLocalMatrix * root.localToWorldMatrix * modelToRoot;
            var spots = new[] {
                new KeyValuePair<Vector3, float>(new Vector3(-0.28f, 0.65f, 6.60f), 1.0f),
                new KeyValuePair<Vector3, float>(new Vector3(0.28f, 0.70f, 6.60f), 1.0f),
                new KeyValuePair<Vector3, float>(new Vector3(-0.28f, 0.65f, 6.85f), 1.0f),
                new KeyValuePair<Vector3, float>(new Vector3(0.28f, 0.70f, 6.85f), 1.0f) };
            foreach (var sp in spots)
            {
                var go = new GameObject("Typhoon_flood");
                go.transform.SetParent(parent, false);
                go.transform.localPosition = toParent.MultiplyPoint3x4(sp.Key);
                var l = go.AddComponent<Light>();
                l.type = LightType.Point;
                l.color = Flood;
                l.range = 0.40f;
                l.intensity = 0f;
                l.shadows = LightShadows.None;
                l.renderMode = LightRenderMode.ForcePixel;
                l.enabled = false;
                n._lights.Add(l); n._lightK.Add(sp.Value);
            }
            foreach (var r in visual.Interior)
            {
                if (r == null) continue;
                foreach (var m in r.sharedMaterials)
                {
                    if (m == null || !m.IsKeywordEnabled("_EMISSION") || !m.HasProperty("_EmissionMap") || m.GetTexture("_EmissionMap") == null) continue;
                    if (n._mats.Any(kv => kv.Key == m)) continue;
                    string nm = m.name;
                    Vector2 dn;
                    if (nm.Contains("ckconsole")) dn = new Vector2(0f, 3.0f);
                    else if (nm.Contains("ckpanel")) dn = new Vector2(0.55f, 4.0f);
                    else if (nm.Contains("Typhoon_cockpit")) dn = new Vector2(m.GetColor("_EmissionColor").r, 2.5f);
                    else continue;
                    n._mats.Add(new KeyValuePair<Material, Vector2>(m, dn));
                }
            }
            int overlays = 0;
            try
            {
                var sprite = TyphoonCockpit.GlowMode == "overlay" ? Shader.Find("Sprites/Default") : null;
                string dir = System.IO.Path.GetDirectoryName(typeof(TyphoonPlugin).Assembly.Location);
                var made = new Dictionary<Material, Material>();
                if (sprite != null)
                    foreach (var r in visual.Interior)
                    {
                        if (r == null) continue;
                        var sm = r.sharedMaterials;
                        if (sm.Length != 1 || sm[0] == null) continue;
                        int idx = n._mats.FindIndex(kv => kv.Key == sm[0]);
                        if (idx < 0) continue;
                        Material g;
                        if (!made.TryGetValue(sm[0], out g))
                        {
                            string file = sm[0].name.Replace("Typhoon_", "") + "_glow.png";
                            if (System.IO.File.Exists(System.IO.Path.Combine(dir, file)))
                            {
                                g = new Material(sprite) { name = sm[0].name + "_glow", renderQueue = 3000 };
                                g.mainTexture = TexturedMaterials.LoadTex(dir, file, false);
                                g.color = new Color(0f, 0f, 0f, 0f);
                                float nightLevel = sm[0].name.Contains("ckpanel") ? 0.14f : 0.12f;
                                n._glow.Add(new KeyValuePair<Material, Vector2>(g, new Vector2(0f, nightLevel)));
                            }
                            made[sm[0]] = g;
                        }
                        if (g == null) continue;
                        r.sharedMaterials = new[] { sm[0], g };
                        overlays++;
                    }
                if (sprite != null)
                    foreach (var r in visual.Interior)
                    {
                        if (r == null) continue;
                        var sm = r.sharedMaterials;
                        if (sm.Length != 1 || sm[0] == null || !(sm[0].name.Contains("cklabel") || sm[0].name.Contains("ckunittxt") || sm[0].name.Contains("cksby"))) continue;
                        var tex = sm[0].HasProperty("_BaseMap") ? sm[0].GetTexture("_BaseMap") : null;
                        if (tex == null) continue;
                        var g = new Material(sprite) { name = sm[0].name + "_glow", renderQueue = 3010 };
                        g.mainTexture = tex;
                        g.color = new Color(0f, 0f, 0f, 0f);
                        n._glow.Add(new KeyValuePair<Material, Vector2>(g, new Vector2(0f, 0.40f)));
                        n._tint[g] = new Color(0.72f, 1f, 0.80f, 1f);
                        r.sharedMaterials = new[] { sm[0], g };
                        overlays++;
                    }
                foreach (var kv in made)
                    if (kv.Value != null)
                    {
                        int idx = n._mats.FindIndex(x => x.Key == kv.Key);
                        if (idx >= 0) n._mats[idx] = new KeyValuePair<Material, Vector2>(kv.Key, new Vector2(n._mats[idx].Value.x, n._mats[idx].Value.x));
                    }
            }
            catch (Exception e) { log.LogWarning("Typhoon cockpit legend overlays: " + e.Message); }
            log.LogInfo($"Typhoon cockpit night lighting: {n._lights.Count} floodlights, {n._mats.Count} backlit materials, {n._glow.Count} legend overlays on {overlays} parts (mode {TyphoonCockpit.NightMode}, glow {TyphoonCockpit.GlowMode}).");
            return n;
        }

        float Night()
        {
            string mode = TyphoonCockpit.NightMode;
            if (mode == "on") return 1f;
            if (mode == "off") return 0f;
            return Dark();
        }

        float Dark()
        {
            if (_sun == null || Time.unscaledTime > _nextSun)
            {
                _nextSun = Time.unscaledTime + 10f;
                _sun = RenderSettings.sun;
                if (_sun == null)
                    foreach (var l in UnityEngine.Object.FindObjectsOfType<Light>())
                        if (l.type == LightType.Directional && (_sun == null || l.intensity > _sun.intensity)) _sun = l;
            }
            if (_sun == null) return 0f;
            float elev = Mathf.Asin(Mathf.Clamp(-_sun.transform.forward.y, -1f, 1f)) * Mathf.Rad2Deg;
            float k = Mathf.Clamp01((6f - elev) / 12f);
            if (!_sun.isActiveAndEnabled || _sun.intensity < 0.05f) k = 1f;
            return k;
        }

        public float Level { get { return _night; } }

        public void Update(List<Material> displays)
        {
            if (Time.unscaledTime < _next) return;
            _next = Time.unscaledTime + 0.5f;
            _night = Night();
            float dark = TyphoonCockpit.NightMode == "off" ? 0f : Dark();
            float dg = Mathf.Lerp(1.2f, 1.2f * Mathf.Clamp(TyphoonCockpit.DisplayNight, 0.05f, 1f), dark) * Mathf.Clamp(TyphoonCockpit.DisplayBrightness, 0.3f, 3f);
            TyphoonCockpit.DisplayGlow = dg;
            if (displays != null)
                foreach (var dm in displays)
                    if (dm != null && dm.HasProperty("_EmissionColor")) dm.SetColor("_EmissionColor", new Color(dg, dg, dg, 1f));
            if (Mathf.Abs(_night - _shown) < 0.01f) return;
            _shown = _night;
            for (int i = 0; i < _lights.Count; i++)
            {
                var l = _lights[i];
                if (l == null) continue;
                l.intensity = _night * _lightK[i] * 0.031f * TyphoonCockpit.FloodBrightness;
                l.enabled = _night > 0.02f;
                l.cullingMask = CullingMask;
            }
            foreach (var kv in _mats)
            {
                if (kv.Key == null) continue;
                float e = Mathf.Lerp(kv.Value.x, kv.Value.y, _night);
                kv.Key.SetColor("_EmissionColor", new Color(e, e, e, 1f));
            }
            foreach (var kv in _glow)
            {
                if (kv.Key == null) continue;
                float e = Mathf.Lerp(kv.Value.x, kv.Value.y, _night) * Mathf.Max(TyphoonCockpit.LegendBrightness, 0f);
                float a = Mathf.Clamp01(e / 0.4f);
                float c = a > 0.001f ? Mathf.LinearToGammaSpace(e / a) : 0f;
                Color tn;
                if (!_tint.TryGetValue(kv.Key, out tn)) tn = Color.white;
                kv.Key.color = new Color(c * tn.r, c * tn.g, c * tn.b, a);
            }
        }
    }

    internal static class TerrainMap
    {
        const int N = 144;
        const float Cell = 18520f * 3.2f / N;
        const int Budget = 450;
        static MapSettings _ms;
        static float _nextFind, _nextFields;
        static bool _failed, _noRay;
        static Layer _front, _back;
        static int _next, _hits;
        static float _x, _z, _hdg;
        static float _lastAsk = -10f;
        static readonly System.Collections.Generic.List<MfdPages.MapField> _fields = new System.Collections.Generic.List<MfdPages.MapField>();

        sealed class Layer
        {
            public MfdPages.MapInfo Info;
            public int OX, OZ;
            public Color32[] Raw;
            public float[] H;
            public bool[] W, Done;
        }

        internal static MfdPages.MapInfo Get(float x, float z, float heading)
        {
            _x = x; _z = z; _hdg = heading; _lastAsk = Time.unscaledTime;
            if (_failed || _front == null) return null;
            _front.Info.PosX = x; _front.Info.PosZ = z;
            _front.Info.Fields = _fields;
            return _front.Info;
        }

        internal static bool Unavailable => _failed;

        internal static void Keep(float x, float z, float heading)
        {
            if (Time.unscaledTime - _lastAsk < 1f) return;
            _x = x; _z = z; _hdg = heading; _lastAsk = Time.unscaledTime - 0.999f;
        }

        internal static void Tick()
        {
            if (_failed || Time.unscaledTime - _lastAsk > 2f) return;
            try
            {
                if (_ms == null)
                {
                    _front = null; _back = null;
                    if (Time.unscaledTime < _nextFind) return;
                    _nextFind = Time.unscaledTime + 5f;
                    _ms = UnityEngine.Object.FindObjectOfType<MapSettings>();
                    if (_ms == null) return;
                    _noRay = false;
                    TyphoonPlugin.Instance?.LogInfo("Typhoon cockpit: moving map uses the terrain of '" + _ms.name + "'.");
                }
                if (Time.unscaledTime > _nextFields) { _nextFields = Time.unscaledTime + 10f; Fields(); }
                float h = _hdg * Mathf.Deg2Rad;
                float ax = _x + Mathf.Sin(h) * 9000f, az = _z + Mathf.Cos(h) * 9000f;
                if (_back == null && NeedNew(ax, az)) _back = NewLayer(ax, az);
                if (_back == null) return;
                int total = N * N, budget = _front == null ? Budget * 3 : Budget;
                while (budget > 0 && _next < total)
                {
                    int j = _next++;
                    if (_back.Done[j]) continue;
                    Sample(_back, j);
                    budget--;
                }
                if (_next >= total)
                {
                    if (!_noRay && _hits == 0)
                    {
                        _noRay = true; _back = null;
                        TyphoonPlugin.Instance?.LogInfo("Typhoon cockpit: moving map: no terrain colliders, water from colour only.");
                        return;
                    }
                    Relief(_back);
                    _front = _back; _back = null;
                }
            }
            catch (Exception e)
            {
                _failed = true;
                TyphoonPlugin.Instance?.LogError("Typhoon cockpit: moving map off: " + e.Message);
            }
        }

        static bool NeedNew(float ax, float az)
        {
            if (_front == null) return true;
            float cx = (_front.OX + N * 0.5f) * Cell, cz = (_front.OZ + N * 0.5f) * Cell;
            float lim = N * Cell * 0.5f - 24500f;
            return Mathf.Abs(ax - cx) > lim || Mathf.Abs(az - cz) > lim;
        }

        static Layer NewLayer(float cx, float cz)
        {
            var L = new Layer { OX = Mathf.RoundToInt(cx / Cell) - N / 2, OZ = Mathf.RoundToInt(cz / Cell) - N / 2 };
            L.Info = new MfdPages.MapInfo { N = N, Cell = Cell, X0 = L.OX * Cell, Z0 = L.OZ * Cell, Grid = new Color32[N * N] };
            L.Raw = new Color32[N * N]; L.H = new float[N * N]; L.W = new bool[N * N]; L.Done = new bool[N * N];
            _next = 0; _hits = 0;
            if (_front != null)
            {
                int dx = L.OX - _front.OX, dz = L.OZ - _front.OZ;
                for (int iz = 0; iz < N; iz++)
                {
                    int fz = iz + dz; if ((uint)fz >= N) continue;
                    for (int ix = 0; ix < N; ix++)
                    {
                        int fx = ix + dx; if ((uint)fx >= N) continue;
                        int j = iz * N + ix, f = fz * N + fx;
                        L.Raw[j] = _front.Raw[f]; L.H[j] = _front.H[f]; L.W[j] = _front.W[f]; L.Done[j] = true;
                    }
                }
                _hits = 1;
            }
            return L;
        }

        static void Sample(Layer L, int j)
        {
            int ix = j % N, iz = j / N;
            float gx = (L.OX + ix + 0.5f) * Cell, gz = (L.OZ + iz + 0.5f) * Cell;
            Color col = _ms.GetTerrainColorAtCoordinate(new GlobalPosition(gx, 0f, gz));
            float hgt = 0f; bool water;
            if (!_noRay)
            {
                Vector3 o = new GlobalPosition(gx, 6000f, gz).ToLocalPosition();
                RaycastHit hit;
                if (Physics.Raycast(o, Vector3.down, out hit, 7000f, ~0, QueryTriggerInteraction.Ignore)) { hgt = hit.point.ToGlobalPosition().y; _hits++; }
                water = hgt < 1.5f;
            }
            else water = col.b > col.r * 1.15f && col.b > col.g * 0.95f;
            L.H[j] = hgt; L.W[j] = water; L.Raw[j] = water ? Water : Land(col); L.Done[j] = true;
        }

        static readonly Color32 Water = new Color32(10, 30, 78, 255), Coast = new Color32(215, 215, 170, 255);

        static Color32 Land(Color c)
        {
            float l = (c.r + c.g + c.b) / 3f;
            float s = 1.25f, k = 0.62f;
            float r = Mathf.Clamp01((l + (c.r - l) * s) * k), g = Mathf.Clamp01((l + (c.g - l) * s) * k), b = Mathf.Clamp01((l + (c.b - l) * s) * k);
            return new Color32((byte)(r * 255), (byte)(g * 255), (byte)(b * 255), 255);
        }

        static void Relief(Layer L)
        {
            int n = N; float cell = Cell;
            var g = L.Info.Grid; var h = L.H; var w = L.W;
            for (int iz = 0; iz < n; iz++)
                for (int ix = 0; ix < n; ix++)
                {
                    int j = iz * n + ix;
                    g[j] = L.Raw[j];
                    if (w[j]) continue;
                    bool coast = false;
                    if (ix > 0 && w[j - 1]) coast = true; else if (ix < n - 1 && w[j + 1]) coast = true;
                    else if (iz > 0 && w[j - n]) coast = true; else if (iz < n - 1 && w[j + n]) coast = true;
                    if (coast) { g[j] = Coast; continue; }
                    if (_noRay) continue;
                    float dx = (h[Mathf.Min(ix + 1, n - 1) + iz * n] - h[Mathf.Max(ix - 1, 0) + iz * n]) / (2f * cell);
                    float dz = (h[ix + Mathf.Min(iz + 1, n - 1) * n] - h[ix + Mathf.Max(iz - 1, 0) * n]) / (2f * cell);
                    float shade = Mathf.Clamp(1f + (-dx + dz) * 4f, 0.55f, 1.45f) * (0.85f + 0.35f * Mathf.Clamp01(h[j] / 1500f));
                    var c = g[j];
                    g[j] = new Color32((byte)Mathf.Clamp(c.r * shade, 0, 255), (byte)Mathf.Clamp(c.g * shade, 0, 255), (byte)Mathf.Clamp(c.b * shade, 0, 255), 255);
                }
        }

        static void Fields()
        {
            _fields.Clear();
            foreach (var a in UnityEngine.Object.FindObjectsOfType<Airbase>())
            {
                try
                {
                    if (a == null || a.center == null) continue;
                    var c = a.center.position.ToGlobalPosition();
                    string nm = null;
                    try { nm = a.SavedAirbase != null ? a.SavedAirbase.DisplayName : null; } catch { }
                    var f = new MfdPages.MapField { Name = (nm ?? "").ToUpperInvariant(), X = c.x, Z = c.z };
                    var rw = new System.Collections.Generic.List<float>();
                    if (a.runways != null)
                        foreach (var r in a.runways)
                        {
                            if (r == null || r.Start == null || r.End == null) continue;
                            var p0 = r.Start.position.ToGlobalPosition(); var p1 = r.End.position.ToGlobalPosition();
                            rw.Add(p0.x); rw.Add(p0.z); rw.Add(p1.x); rw.Add(p1.z);
                        }
                    f.Rwy = rw.ToArray();
                    _fields.Add(f);
                }
                catch { }
            }
        }
    }

    internal sealed class MfdCanvas
    {
        public readonly int W, H;
        public readonly Texture2D Tex;
        readonly Color32[] _px;
        static byte[] _font, _fontHi;
        const int GW = 10, GH = 16;
        internal static int Sharp = 2;
        readonly int _s, _pw, _ph;

        public MfdCanvas(int w, int h)
        {
            W = w; H = h;
            _s = Mathf.Clamp(Sharp, 1, 2); _pw = w * _s; _ph = h * _s;
            Tex = new Texture2D(_pw, _ph, TextureFormat.RGBA32, _s > 1)
            { wrapMode = TextureWrapMode.Clamp, filterMode = _s > 1 ? FilterMode.Trilinear : FilterMode.Bilinear, anisoLevel = _s > 1 ? 8 : 1, name = "Typhoon_MFD" };
            if (_s > 1) Tex.mipMapBias = -Mathf.Min(0.4f, TexturedMaterials.CockpitSharpness);
            _px = new Color32[_pw * _ph];
            if (_font == null) _font = Convert.FromBase64String(FontData);
            if (_s > 1 && _fontHi == null) _fontHi = Convert.FromBase64String(FontHi.Data);
        }

        public void Clear(Color32 c) { for (int i = 0; i < _px.Length; i++) _px[i] = c; }
        public void Apply() { Tex.SetPixels32(_px); Tex.Apply(_s > 1); }

        void SetP(int x, int y, Color32 c)
        {
            if ((uint)x >= (uint)_pw || (uint)y >= (uint)_ph) return;
            _px[(_ph - 1 - y) * _pw + x] = c;
        }

        void BlendP(int x, int y, Color32 c, int a)
        {
            if ((uint)x >= (uint)_pw || (uint)y >= (uint)_ph || a <= 0) return;
            int i = (_ph - 1 - y) * _pw + x;
            if (a >= 255) { _px[i] = c; return; }
            var d = _px[i];
            _px[i] = new Color32((byte)(d.r + (c.r - d.r) * a / 255), (byte)(d.g + (c.g - d.g) * a / 255), (byte)(d.b + (c.b - d.b) * a / 255), 255);
        }

        public void Set(int x, int y, Color32 c)
        {
            if ((uint)x >= (uint)W || (uint)y >= (uint)H) return;
            if (_s == 1) { _px[(H - 1 - y) * W + x] = c; return; }
            for (int j = 0; j < _s; j++) for (int i = 0; i < _s; i++) _px[(_ph - 1 - (y * _s + j)) * _pw + x * _s + i] = c;
        }

        public void Fill(int x, int y, int w, int h, Color32 c)
        {
            int x0 = Mathf.Max(x, 0) * _s, y0 = Mathf.Max(y, 0) * _s, x1 = Mathf.Min(x + w, W) * _s, y1 = Mathf.Min(y + h, H) * _s;
            for (int j = y0; j < y1; j++)
            {
                int row = (_ph - 1 - j) * _pw;
                for (int i = x0; i < x1; i++) _px[row + i] = c;
            }
        }

        public void Box(int x, int y, int w, int h, Color32 c, int t)
        {
            Fill(x, y, w, t, c); Fill(x, y + h - t, w, t, c); Fill(x, y, t, h, c); Fill(x + w - t, y, t, h, c);
        }

        public void Line(float x0, float y0, float x1, float y1, Color32 c, int thick, int cx0 = 0, int cy0 = 0, int cx1 = 99999, int cy1 = 99999)
        {
            float k = _s, o = (_s - 1) * 0.5f;
            float X0 = x0 * k + o, Y0 = y0 * k + o, X1 = x1 * k + o, Y1 = y1 * k + o;
            int t = thick * _s;
            float len = Mathf.Max(Mathf.Abs(X1 - X0), Mathf.Abs(Y1 - Y0));
            int steps = Mathf.Max(1, Mathf.CeilToInt(len * 1.5f));
            int r0 = -(t - 1) / 2, r1 = t / 2;
            int px0 = cx0 * _s, py0 = cy0 * _s, px1 = cx1 > 90000 ? int.MaxValue : cx1 * _s, py1 = cy1 > 90000 ? int.MaxValue : cy1 * _s;
            for (int s = 0; s <= steps; s++)
            {
                float tt = s / (float)steps;
                int x = Mathf.RoundToInt(X0 + (X1 - X0) * tt), y = Mathf.RoundToInt(Y0 + (Y1 - Y0) * tt);
                for (int j = r0; j <= r1; j++)
                    for (int i = r0; i <= r1; i++)
                    {
                        int px = x + i, py = y + j;
                        if (px < px0 || py < py0 || px >= px1 || py >= py1) continue;
                        SetP(px, py, c);
                    }
            }
        }

        public void Circle(float cx, float cy, float r, Color32 c)
        {
            int n = Mathf.Max(24, Mathf.RoundToInt(r * 3f * _s));
            for (int i = 0; i < n; i++)
            {
                float a0 = i * Mathf.PI * 2f / n, a1 = (i + 1) * Mathf.PI * 2f / n;
                Line(cx + Mathf.Cos(a0) * r, cy + Mathf.Sin(a0) * r, cx + Mathf.Cos(a1) * r, cy + Mathf.Sin(a1) * r, c, 1);
            }
        }

        public void Text(string s, int x, int y, Color32 c, int scale = 1)
        {
            if (s == null) return;
            s = s.ToUpperInvariant();
            bool hi = _s == 2 && _fontHi != null;
            byte[] font = hi ? _fontHi : _font;
            int gw = hi ? FontHi.GW : GW, gh = hi ? FontHi.GH : GH;
            int ps = hi ? scale : scale * _s;
            int bx = x * _s, by = y * _s;
            for (int k = 0; k < s.Length; k++)
            {
                int ch = s[k] - 32;
                if (ch < 0 || ch >= 64) ch = '?' - 32;
                int baseIdx = ch * gw * gh;
                int cx = bx + k * gw * ps;
                for (int gy = 0; gy < gh; gy++)
                    for (int gx = 0; gx < gw; gx++)
                    {
                        int a = font[baseIdx + gy * gw + gx];
                        if (a < 24) continue;
                        if (ps == 1) BlendP(cx + gx, by + gy, c, a);
                        else
                            for (int sy = 0; sy < ps; sy++)
                                for (int sx = 0; sx < ps; sx++)
                                    BlendP(cx + gx * ps + sx, by + gy * ps + sy, c, a);
                    }
            }
        }

        const string FontData =
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAeP+AAAAAAAAAAHj/gAAAAAAAAAB4/4AAAAAAAAAAeP+AAAAAAAAAAHj/gAAAAAAAAABw/3gAAAAAAAAAWf9hAAAAAAAAAED/SwAAAAAAAAAAAAAAAAAA" +
            "AAAAeP+AAAAAAAAAAHj/gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABQ/5AAkP9QAAAAUP+QAJD/UAAA" +
            "AFD/kACQ/1AAAABQ/5AAkP9QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACS/hB2/y0AAAAAzNMAsO8CAAAAC/uZAOq1AAAk//////////8A" +
            "AACg+ASD/xwAAAAAzs0AsO0AAAAABPifAN2/AAAA/P////////8oAACW/A12/yYAAAAA0M8AsOsAAAAADf2VAOqxAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA9BQAAAAAAAAAAPQUAAAAAAAHi+T///9QAAAAf/9s9DF7RwAAAL//PPQUAAAAAACi/976RgIAAAAAItr////RHwAA" +
            "AAAGSvnm/7AAAAAAAAD0M//vAAAAbAMA9BT35wAAALy1I/Ri/5AAAAAjm+P/6I8JAAAAAAAA9BQAAAAAAAAAAPQUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAyq8r0aAAAAAACG1xW6rAAAAAAAuZsAdOAAAAAAAIfWFLitAAAAAQANrPO/HCd5pEMAAAAugKF6KAAAACafcR8LqPK9GgAAAAAAgtcWu6wA" +
            "AAAAALWbAHDgAAAAAACD1hW3rAAAAAAADKryvRoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGvY99A1AAAA" +
            "ADr/zw8tiQAAAABR/90BAAAAAAAACuP/YgAAAAAAAGD5/+oQAAAAADL73aT/jwDK4gCX/2ca9vsqzdUAtf9KAIz/vvSxAJX/fAAU8v//aQAo9e5AEL7/+A4A" +
            "ACy27Pja1P+bAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAcP9wAAAAAAAAAHD/cAAAAAAAAABw/3AAAAAA" +
            "AAAAcP9wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA5/oMAAAAAAAAB0fIRAAAAAAAATf+eAAAAAAAAALD/SQAAAAAAAAPx/hEAAAAA" +
            "AAAb/+4AAAAAAAAAK//gAAAAAAAAABv/7gAAAAAAAAAD8f8SAAAAAAAAALD/SwAAAAAAAABN/58AAAAAAAAAAdDzEQAAAAAAAAA5/oMAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAHz/QAAAAAAAAAAN79cDAAAAAAAAAJf/VAAAAAAAAABC/7gAAAAAAAAAC/z1BgAAAAAAAADn/yIAAAAAAAAA2f8yAAAA" +
            "AAAAAOf/IgAAAAAAAAz99QYAAAAAAABD/7gAAAAAAAAAmP9UAAAAAAAADe/WAwAAAAAAAHz/QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAIP8gAAAAAAPDfjH/Mn7DAwAALKHz//SiLAAAACyg8v/yoSwAAAPDfTD/MH3DAwAAAAAg/yAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAXP9kAAAAAAAAAFz/ZAAAAAAAAABc/2QAAAAAhP////////+IAIT/////////iAAAAABc/2QAAAAAAAAAXP9kAAAAAAAAAFz/ZAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKD/rAAAAAAAAACg/6wAAAAAAAAAu/92AAAAAAAABfTsDAAAAAAAADn/egAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AADM////1AAAAAAAzP///9QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAuP+8AAAAAAAAALj/vAAAAAAAAAC4/7wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACq6woA" +
            "AAAAAAAm/XsAAAAAAAAAn/EPAAAAAAAAHvqGAAAAAAAAAJT2FQAAAAAAABf3kAAAAAAAAACK+RwAAAAAAAAR8psAAAAAAAAAf/wkAAAAAAAADO2mAAAAAAAA" +
            "AHT+LQAAAAAAAAfmsQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABY1/nZWwAAAABA/rkPs/5DAAAAsf9SAEv/twAA" +
            "AO7/KwAj//QBAAz//1DuUP//EwAV//9N8Ev//x0ADP//GQAS//8TAADu/yoAI//0AQAAsf9RAEr/uAAAAED+uA6y/kUAAAAAWNf52l0AAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALa9r/5AAAAAAAaJRY/+QAAAAAAAAANP/kAAAAAAAAADT/5AAAAAAAAAA0/+QAAAAA" +
            "AAAANP/kAAAAAAAAADT/5AAAAAAAAAA0/+QAAAAAAAAANP/kAAAAAAAAADT/5AAAAAAAoP///////1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAANKrv78JDAAAAALZSDCba/DoAAAAAAAAAef+fAAAAAAAAAJH/tgAAAAAAAAzn/4gAAAAAAACc//UeAAAAAABh//5ZAAAA" +
            "AAAx9/91AAAAAAAS3/+LAAAAAAACuf+gAQAAAAAAJ////////8gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "ACOb6/XWfAMAAACbYBEVs/+EAAAAAAAAAFP/vgAAAAAAABOt/2cAAAAAJP//9msAAAAAAAAAHL/+YgAAAAAAAAA0/+UAAAAAAAAADf//CAAAAAAAACb/7wAA" +
            "E7RDFRez/4UAAABJuenyz2cCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB0//8oAAAAAAAr+P//KAAA" +
            "AAAFzfX3/ygAAAAAgv937P8oAAAANfvVBez/KAAACNf/PwDs/ygAAD//ogAA7P8oAABA/////////1wAAAAAAADs/ygAAAAAAAAA7P8oAAAAAAAAAOz/KAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAmP//////XAAAAJj/LAAAAAAAAACY/ywAAAAAAAAAmP8sAAAAAAAA" +
            "AJj/9PbOVwAAAAB7VhAw1v9oAAAAAAAAAEn/3wAAAAAAAAAh//0AAAAAAAAARv/dAAAArToLMNH/YwAAADu07OzBSgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgpOnyqhkAAAAW5uY/D1VyAAAAjf9fAAAAAAAAANj/GgAAAAAAAAH8/7Lt77AcAAAJ///FFGn/wgAA" +
            "Av//XwAC7/8YAADm/0kAANr/LQAArP9fAALu/w0AAD79xBNn/6MAAAAAUtD44pEMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAT////////oAAAAAAAAAKL/3QAAAAAAAAny/4gAAAAAAABX//4lAAAAAAAAsv+/AAAAAAAAEvr/WwAAAAAAAGj/7ggAAAAAAADC/5IAAAAA" +
            "AAAe/v8uAAAAAAAAeP/KAAAAAAAAANP/ZgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABYTe9+CHBgAA" +
            "AIL/hwt//4kAAAC8/y0AJf/DAAAAc/+FC4D/ewAAAACc////qAAAAABz/44Rif97AAAA6/wMAAn48QEAB//qAAAA4/8OAADm/AwACvjtAAAAf/+OEIz/gwAA" +
            "AAR42fbaewUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAuO3/jSVgAAAACf/24TxP5EAAAI/fQEAF3/swAA" +
            "Jv/hAABG/+wAABH/9AQAXf//CAAAvf9uE8T//xAAABqt7vG3/f8FAAAAAAAAE//fAAAAAAAAAFf/lAAAAGhRDzrh6hoAAAAXpvLrpyMAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALj/vAAAAAAAAAC4/7wAAAAA" +
            "AAAAuP+8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAuP+8AAAAAAAAALj/vAAAAAAAAAC4/7wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAC4/7wAAAAAAAAAuP+8AAAAAAAAALj/vAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAALj/vAAAAAAAAAC4/7wAAAAAAAAAzf+GAAAAAAAABfj0FAAAAAAAAC//igAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA8o1wAAAAAEG3U//9eAAA4n/b/6pI0AABX//isTgUAAAAAWP/1pEYDAAAAAAA8o/f/5owuAAAAAAAScdb//10A" +
            "AAAAAAAAPqVcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAFz/////////ZABc/////////2QAAAAAAAAAAAAAAAAAAAAAAAAAAABc/////////2QAXP////////9kAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFWmPwAAAAAAAABW///XcRIAAAAA" +
            "ADGP6P/3ojsAAAAAAARLqff/XwAAAAACQ6Hz/2AAACuJ5P/4pkAAAFT//9l0FAAAAABVqEEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVpzfXmmAwAAABFkSsJhv+VAAAAAAAAAGz/twAAAAAAAC7w/EsAAAAAABjl/lkAAAAAAACO/4UAAAAA" +
            "AAAAvP83AAAAAAAAAMj/LAAAAAAAAAAAAAAAAAAAAAAAyP8sAAAAAAAAAMj/LAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAADy68eyzJwAAAFb5dxEarOMOABjyggAAABb/VwB8+BQZuvPD+3kAwbgAuNUYdP98AOWaD/90AAb4fADwhCj/XQAA5nwA" +
            "4pAP/3QABfd8ALm8ALnUGHL/fABu+hYbvPXL+nwADeKlAAAAAAAAAAA27qgsCTm7DwAAAByW4PnsvCwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPv//QFAAAA" +
            "AAA3////PgAAAAAAfP/Y/4MAAAAAAMH/b//IAAAAAAv5+w/4/BAAAABK/9AAyf9RAAAAj/+aAJP/lgAAANT//////9sAABn/8QIAAe7/HwBd/7sAAAC2/2QA" +
            "ov+DAAAAff+pAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFP////vglBIAABT//wAHgP+zAAAU//8AABn/+wcA" +
            "FP//AAAY//4HABT//wAGfP+nAAAU//////+6FAAAFP//AAVJ++APABT//wAAAMX/YQAU//8AAADB/2oAFP//AARA+PkqABT////+8MJLAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACoTc99BLAAAAAr3/gg0tmAAAAFn/zwAAAAAAAACr/4cAAAAAAAAA1P9mAAAAAAAA" +
            "AOD/XgAAAAAAAADU/2YAAAAAAAAAq/+HAAAAAAAAAFr/zQAAAAAAAAACwP+ADCqXAAAAAAuG3vjRSwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAA///75687AAAAAP//LSXP/E0AAAD//ywAQ//dAQAA//8sAAj+/ykAAP//LAAA7f9NAAD//ywAAOb/WAAA//8sAADt/00A" +
            "AP//LAAI/v8oAAD//ywAQv/cAQAA//8sJM38TQAAAP///OivOwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AMT///////8MAADE/2QAAAAAAAAAxP9kAAAAAAAAAMT/ZAAAAAAAAADE/2QAAAAAAAAAxP//////nAAAAMT/ZAAAAAAAAADE/2QAAAAAAAAAxP9kAAAAAAAA" +
            "AMT/ZAAAAAAAAADE////////DAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACs////////JAAArP+AAAAAAAAA" +
            "AKz/gAAAAAAAAACs/4AAAAAAAAAArP+AAAAAAAAAAKz//////7wAAACs/4AAAAAAAAAArP+AAAAAAAAAAKz/gAAAAAAAAACs/4AAAAAAAAAArP+AAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB2g6PnHPQAAABfk+VIJMJsAAACX/5AAAAAAAAAA6v9HAAAAAAAA" +
            "FP//JgAAAAAAACD//x4AAAAAAAAU//8mGP///0gAAOr/RwAAnP9IAACY/40AAJz/SAAAGef2SAiv/0gAAAAgpuz55a4iAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP//LAAk//8IAAD//ywAJP//CAAA//8sACT//wgAAP//LAAk//8IAAD//ywAJP//CAAA/////////wgA" +
            "AP//LAAk//8IAAD//ywAJP//CAAA//8sACT//wgAAP//LAAk//8IAAD//ywAJP//CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAC8///////EAAAAAACQ/5gAAAAAAAAAkP+YAAAAAAAAAJD/mAAAAAAAAACQ/5gAAAAAAAAAkP+YAAAAAAAAAJD/mAAAAAAAAACQ/5gAAAAA" +
            "AAAAkP+YAAAAAAAAAJD/mAAAAAAAvP//////xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGz/////ZAAA" +
            "AAAAAADI/2QAAAAAAAAAyP9kAAAAAAAAAMj/ZAAAAAAAAADI/2QAAAAAAAAAyP9kAAAAAAAAAMj/ZAAAAAAAAADI/2QAAAAAAAAAzv9bAAAwmzAJPfn8KAAA" +
            "AlnE8vfSXQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJP//BAAY5/9xACT//wQEwf+lAAAk//8Ejf/PCQAA" +
            "JP//WP/sIAAAACT///T/jQAAAAAk//////ETAAAAJP//n8f/jQAAACT//wtC//geAAAk//8EAL3/oAAAJP//BAA4//0sACT//wQAALP/swAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABc/9AAAAAAAAAAXP/QAAAAAAAAAFz/0AAAAAAAAABc/9AAAAAAAAAAXP/QAAAAAAAA" +
            "AFz/0AAAAAAAAABc/9AAAAAAAAAAXP/QAAAAAAAAAFz/0AAAAAAAAABc/9AAAAAAAAAAXP///////3AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAABg//9WAFP//2gAYP//nACX//9oAGD/6+EA3Ov/aABg/6//SP+v/2gAYP9/8dD3ev9oAGD/fLb/wHT/aABg/3x3/4J0/2gA" +
            "YP98AAAAdP9oAGD/fAAAAHT/aABg/3wAAAB0/2gAYP98AAAAdP9oAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "IP//YAAAxP8kACD//8EAAMT/JAAg////JADE/yQAIP/Y94QAxP8kACD/yKbjAsT/JAAg/8hE/0fE/yQAIP/IAd+pxP8kACD/yACA+Nb/JAAg/8gAH/7//yQA" +
            "IP/IAAC8//8kACD/yAAAWf//JAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAadr53G8AAAAAZP+kDJ//bAAA" +
            "AOH/LwAr/+cCACb//gYAA/v/LQBH//IAAADr/04AUf/tAAAA5v9YAEf/8gAAAOv/TgAm//4GAAP7/y0AAeL/LwAr/+gCAABk/6QMn/9sAAAAAGrb+t1vAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA0P//+uSlIgAAAND/WAt2/+IJAADQ/1gAAvH/SwAA0P9YAADe/2MA" +
            "AND/WAAC8f9LAADQ/1gLdv/iCQAA0P//++WlIgAAAND/WAAAAAAAAADQ/1gAAAAAAAAA0P9YAAAAAAAAAND/WAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABp2vnbagAAAABk/6QMn/9kAAAA4f8vACv/4gEAJv/+BgAD+/8pAEf/8gAAAOv/TABR/+0AAADm/1gA" +
            "R//yAAAA6/9MACb//gYAA/v/NAAB4v8vACv/9AUAAGT/pAyf/5AAAAAAadv9/9UKAAAAAAAABcP/fwAAAAAAAAAWwTAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAj////63YgIAAAI//8kEbb/lQAACP//JABK/+4AAAj//yQANf//BgAI//8kAEr/7AAACP//JBG2/38AAAj//////4YAAAAI//8kT/32JAAA" +
            "CP//JACg/6oAAAj//yQAIvv/NwAI//8kAACa/8EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABXrZ9dWBEAAA" +
            "AIv/dgkcenIAAADu/xoAAAAAAAAG/v+kEgAAAAAAAM3///OKFwAAAAAv2/////E+AAAAAAZf1f//3AAAAAAAAAKG//8UAAAAAAAAGv/6BQADxFYeCn//owAA" +
            "AD+w5fvgkAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWP////////9gAAAAAJD/mAAAAAAAAACQ/5gAAAAA" +
            "AAAAkP+YAAAAAAAAAJD/mAAAAAAAAACQ/5gAAAAAAAAAkP+YAAAAAAAAAJD/mAAAAAAAAACQ/5gAAAAAAAAAkP+YAAAAAAAAAJD/mAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADj/8AAAAOj/QAA4//AAAADo/0AAOP/wAAAA6P9AADj/8AAAAOj/QAA4//AAAADo/0AA" +
            "OP/wAAAA6P9AADj/8AAAAOj/QAAz//AAAADo/zsAFP/6AwAB9f8bAAC8/3cMcP/DAAAAGqfq/OyrHQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAB2/7IAAACr/30AOv/nAAAA4f9BAAb2/x0AFv/6CgAAwf9TAEz/yAAAAIX/iACB/4wAAABI/74At/9PAAAADv3xAuv/FAAA" +
            "AADQ/0v/1wAAAAAAk/+2/5oAAAAAAFf//v9eAAAAAAAa////IgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "8O8AAAAAAOr4ANH/CQAAAAH72wCy/yEAAAAQ/74Ak/85eP+DI/+gAHP/Uqj/ujf/gwBU/2vX5/BM/2UANf+N/ID/h/9IABb/0/8a+tH/KgAA9f/bAMz//w0A" +
            "ANf/pgCU/+8AAAC4/3IAXP/SAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAG//ygEAAMT/dgAE1v9fAFj/3AYA" +
            "AEf/5RTg/1AAAAAAtP/b/70AAAAAACb6//wuAAAAAAAAvf/JAAAAAAAAN/7//0EAAAAAAcj/xP/QAgAAAFz/2AjS/2YAAAvk/0sAQ//pDgCC/7kAAACx/4oA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACw/6EAAACa/7YAL/77IAAb+f82AACt/5cAkP+0AAAALP74L/X/MwAA" +
            "AACq/+r/sQAAAAAAKv3//jAAAAAAAACt/7UAAAAAAAAAkP+YAAAAAAAAAJD/mAAAAAAAAACQ/5gAAAAAAAAAkP+YAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP////////9oAAAAAAAAj///ZwAAAAAAL/z/9B8AAAAAAcb//3IAAAAAAGX//8wDAAAAABTs//wxAAAA" +
            "AACe//+LAAAAAAA7/v/eCgAAAAAE0v//RwAAAAAAJ///pQAAAAAAACj/////////gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAOj//9AAAAAAAADo/wwAAAAAAAAA6P8MAAAAAAAAAOj/DAAAAAAAAADo/wwAAAAAAAAA6P8MAAAAAAAAAOj/DAAAAAAAAADo/wwAAAAA" +
            "AAAA6P8MAAAAAAAAAOj/DAAAAAAAAADo/wwAAAAAAAAA6P8MAAAAAAAAAOj//9AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJ6bAAAAAAAAAA" +
            "AHj+LAAAAAAAAAAO76YAAAAAAAAAAIP8JAAAAAAAAAAT9JsAAAAAAAAAAI75HAAAAAAAAAAa+JAAAAAAAAAAAJj1FQAAAAAAAAAh/IYAAAAAAAAAAKPwDwAA" +
            "AAAAAAAq/nsAAAAAAAAAAK3rCgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADI///wAAAAAAAAAAT/8AAAAAAAAAAE//AAAAAA" +
            "AAAABP/wAAAAAAAAAAT/8AAAAAAAAAAE//AAAAAAAAAABP/wAAAAAAAAAAT/8AAAAAAAAAAE//AAAAAAAAAABP/wAAAAAAAAAAT/8AAAAAAAAAAE//AAAAAA" +
            "AADI///wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABcH/xwYAAAAAAJT/+f+aAAAAAGD/wBq7/2cAADX4sggABqv5OwAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==";
    }
}
