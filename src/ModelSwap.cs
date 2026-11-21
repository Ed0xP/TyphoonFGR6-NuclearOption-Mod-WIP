using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Reflection;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using UnityEngine;

namespace TyphoonMod
{
    internal sealed class ObjGroup
    {
        public string Name;
        public string Material;
        public List<Vector3> Positions = new List<Vector3>();
        public List<Vector3> Normals = new List<Vector3>();
        public List<Vector2> UVs = new List<Vector2>();
        public bool HasUVs;
        public List<int> Triangles = new List<int>();
        public Bounds Bounds;
    }

    internal static class ObjReader
    {
        public static List<ObjGroup> Read(string path)
        {
            var groups = new List<ObjGroup>();
            var pos = new List<Vector3>();
            var nrm = new List<Vector3>();
            var tex = new List<Vector2>();
            ObjGroup cur = null;
            string mat = "body";
            Dictionary<string, int> remap = null;

            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                var p = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                switch (p[0])
                {
                    case "o":
                    case "g":
                        cur = new ObjGroup { Name = p.Length > 1 ? p[1] : "part" + groups.Count, Material = mat };
                        groups.Add(cur);
                        remap = new Dictionary<string, int>();
                        break;
                    case "usemtl":
                        mat = p.Length > 1 ? p[1] : "body";
                        if (cur != null) cur.Material = mat;
                        break;
                    case "v":
                        pos.Add(new Vector3(F(p[1]), F(p[2]), F(p[3])));
                        break;
                    case "vt":
                        tex.Add(new Vector2(F(p[1]), F(p[2])));
                        break;
                    case "vn":
                        nrm.Add(new Vector3(F(p[1]), F(p[2]), F(p[3])));
                        break;
                    case "f":
                        if (cur == null)
                        {
                            cur = new ObjGroup { Name = "part0", Material = mat };
                            groups.Add(cur);
                            remap = new Dictionary<string, int>();
                        }
                        var idx = new int[p.Length - 1];
                        for (int i = 1; i < p.Length; i++)
                        {
                            var parts = p[i].Split('/');
                            int vi = int.Parse(parts[0], CultureInfo.InvariantCulture) - 1;
                            int ti = parts.Length > 1 && parts[1].Length > 0 ? int.Parse(parts[1], CultureInfo.InvariantCulture) - 1 : -1;
                            int ni = parts.Length > 2 && parts[2].Length > 0 ? int.Parse(parts[2], CultureInfo.InvariantCulture) - 1 : -1;
                            string key = p[i];
                            int outIndex;
                            if (!remap.TryGetValue(key, out outIndex))
                            {
                                outIndex = cur.Positions.Count;
                                cur.Positions.Add(pos[vi]);
                                cur.Normals.Add(ni >= 0 ? nrm[ni] : Vector3.zero);
                                cur.UVs.Add(ti >= 0 ? tex[ti] : Vector2.zero);
                                if (ti >= 0) cur.HasUVs = true;
                                remap[key] = outIndex;
                            }
                            idx[i - 1] = outIndex;
                        }
                        for (int i = 1; i + 1 < idx.Length; i++)
                        {
                            cur.Triangles.Add(idx[0]);
                            cur.Triangles.Add(idx[i]);
                            cur.Triangles.Add(idx[i + 1]);
                        }
                        break;
                }
            }

            groups.RemoveAll(g => g.Triangles.Count == 0);
            foreach (var g in groups)
            {
                var b = new Bounds(g.Positions[0], Vector3.zero);
                foreach (var v in g.Positions) b.Encapsulate(v);
                g.Bounds = b;
            }
            return groups;
        }

        static float F(string s) => float.Parse(s, NumberStyles.Float, CultureInfo.InvariantCulture);
    }

    public sealed class TyphoonVisual : MonoBehaviour
    {
        internal bool Built;
        bool _soundsDone;
        List<Turbojet> _engines;
        EngineSoundShaper _sound;
        internal Transform Pilot;
        internal List<Renderer> TyphoonCockpit = new List<Renderer>();
        internal List<Renderer> OriginalCockpit = new List<Renderer>();
        internal float Radius = 2f;
        int _state = -1;

        internal sealed class FlameCopy { public Renderer Original; public List<Renderer> Clones = new List<Renderer>(); public List<Vector3> ScaleMuls = new List<Vector3>(); }
        internal List<FlameCopy> Flames = new List<FlameCopy>();
        internal ReheatFlame Reheat;
        internal Renderer GearLamps;
        MaterialPropertyBlock _lampBlock;
        internal readonly List<KeyValuePair<Renderer, Color>> NavLamps = new List<KeyValuePair<Renderer, Color>>();
        MaterialPropertyBlock _navBlock;
        int _navState = -1;
        int _lampState = -1, _lampWant = -1;
        float _lampAt;
        internal List<Renderer> FlameOriginals = new List<Renderer>();

        internal sealed class NavHalo { public Transform T, Host; public Renderer R; public Vector3 Local, OutRoot; public Material M; public Color Tint; }
        internal readonly List<NavHalo> Halos = new List<NavHalo>();
        void UpdateHalos(Camera cam)
        {
            if (Halos.Count == 0 || cam == null || Aircraft == null) return;
            var ct = cam.transform;
            for (int i = 0; i < Halos.Count; i++)
            {
                var h = Halos[i];
                if (h.T == null || h.Host == null || h.R == null || !h.Host.gameObject.activeInHierarchy) continue;
                Vector3 anchor = h.Host.TransformPoint(h.Local);
                Vector3 to = ct.position - anchor;
                float dist = to.magnitude;
                Vector3 dir = dist > 1e-3f ? to / dist : ct.forward;
                float face = Mathf.Clamp01((Vector3.Dot(Aircraft.transform.TransformDirection(h.OutRoot), dir) + 0.15f) / 0.45f);
                bool show = face > 0.01f && dist > 0.3f;
                if (h.R.enabled != show) h.R.enabled = show;
                if (!show) continue;
                float size = Mathf.Max(0.17f, dist * 0.0045f) * Mathf.Sqrt(face);
                h.T.position = anchor + dir * Mathf.Min(0.10f, dist * 0.3f);
                h.T.rotation = ct.rotation;
                float ps = h.T.parent != null ? Mathf.Max(1e-4f, Mathf.Abs(h.T.parent.lossyScale.x)) : 1f;
                h.T.localScale = Vector3.one * (size / ps);
                float a = Mathf.Lerp(0.55f, 1f, Mathf.InverseLerp(4f, 60f, dist)) * face;
                if (Mathf.Abs(a - h.Tint.a) > 0.01f) { h.Tint.a = a; h.M.color = h.Tint; }
            }
        }

        internal sealed class HazeCopy { public ParticleSystem Original; public List<ParticleSystem> Clones = new List<ParticleSystem>(); public float RateMul = 0.75f; }
        internal List<HazeCopy> Hazes = new List<HazeCopy>();

        void SyncHaze(HazeCopy h)
        {
            var o = h.Original;
            if (o == null) return;
            var r = o.GetComponent<ParticleSystemRenderer>();
            if (r != null && !r.forceRenderingOff) r.forceRenderingOff = true;
            var om = o.main; var oe = o.emission;
            bool playing = o.isPlaying;
            foreach (var c in h.Clones)
            {
                if (c == null) continue;
                var cm = c.main; var ce = c.emission;
                cm.startColor = om.startColor;
                cm.startSize = om.startSize;
                cm.startLifetime = om.startLifetime;
                cm.startSpeed = om.startSpeed;
                var rate = oe.rateOverTime; rate.constant *= h.RateMul; rate.constantMin *= h.RateMul; rate.constantMax *= h.RateMul;
                ce.rateOverTime = rate;
                if (playing && !c.isPlaying) c.Play(); else if (!playing && c.isPlaying) c.Stop();
            }
        }

        internal Aircraft Aircraft;

        internal sealed class Surface
        {
            public Transform Pivot;
            public Vector3 AxisLocal;
            public Vector3 AxisRoot;
            public List<Transform> Drivers = new List<Transform>();
            public List<Quaternion> Rest = new List<Quaternion>();
            public bool FullRotation;
            public Airbrake AirbrakeRef;
            public Quaternion RestRoot = Quaternion.identity;
            public bool IsStick;
            public Quaternion StickQ = Quaternion.identity;
            public bool IsThrottle;
            public string Input;
            public float AngA, AngB;

            public Mesh IrisMesh;
            Vector3[] _base, _radial, _work;
            float[] _t;
            float _open = 1.18f, _closed = 0.86f, _applied = -1f;
            public float Openness = 0.6f;

            public void SetupIris(Mesh mesh, float open, float closed)
            {
                IrisMesh = mesh; _open = open; _closed = closed;
                mesh.MarkDynamic();
                _base = mesh.vertices;
                _work = new Vector3[_base.Length];
                _radial = new Vector3[_base.Length];
                _t = new float[_base.Length];
                Vector3 ax = AxisLocal.normalized;
                float tMax = 0f;
                for (int i = 0; i < _base.Length; i++)
                {
                    float along = Vector3.Dot(_base[i], ax);
                    _radial[i] = _base[i] - ax * along;
                    _t[i] = Mathf.Max(0f, along);
                    tMax = Mathf.Max(tMax, _t[i]);
                }
                for (int i = 0; i < _t.Length; i++) _t[i] = tMax > 0 ? _t[i] / tMax : 0f;
                float rMax = 0f;
                var ring = new List<float>();
                for (int i = 0; i < _base.Length; i++) if (_t[i] > 0f) ring.Add(_radial[i].magnitude);
                ring.Sort();
                if (ring.Count > 0) rMax = ring[(int)(ring.Count * 0.98f)];
                for (int i = 0; i < _base.Length; i++)
                    if (rMax > 0f && _radial[i].magnitude > rMax * 1.3f) _t[i] = 0f;
            }

            public float ExitScale() { return IrisMesh != null ? Mathf.Lerp(_closed, _open, Openness) : 1f; }

            public void ApplyIris()
            {
                if (IrisMesh == null || Mathf.Abs(Openness - _applied) < 0.005f) return;
                _applied = Openness;
                float exitScale = Mathf.Lerp(_closed, _open, Openness);
                for (int i = 0; i < _base.Length; i++)
                    _work[i] = _base[i] + _radial[i] * ((exitScale - 1f) * _t[i]);
                IrisMesh.vertices = _work;
                IrisMesh.RecalculateBounds();
            }
        }
        internal List<Surface> Surfaces = new List<Surface>();

        internal static float AirbrakeAngle = 50f;
        internal static float NozzleVectoring = 1f;
        static readonly FieldInfo AirbrakeOpenF = typeof(Airbrake).GetField("openAmount", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        internal object AfterburnerRef;
        static FieldInfo _abAmountField;

        internal float AfterburnerAmount()
        {
            if (AfterburnerRef == null) return 0f;
            if (_abAmountField == null) _abAmountField = AfterburnerRef.GetType().GetField("afterburnerAmount");
            return _abAmountField != null ? Mathf.Clamp01((float)_abAmountField.GetValue(AfterburnerRef)) : 0f;
        }

        internal float NozzleOpenness()
        {
            foreach (var s in Surfaces) if (s.FullRotation && s.IrisMesh != null) return s.Openness;
            return TargetOpenness();
        }

        internal float AirbrakeOpen()
        {
            foreach (var s in Surfaces)
                if (s.AirbrakeRef != null && AirbrakeOpenF != null) return Mathf.Clamp01((float)AirbrakeOpenF.GetValue(s.AirbrakeRef));
            return 0f;
        }

        internal bool InteriorMode;
        internal TyphoonCockpit Cockpit;
        internal List<Renderer> Interior = new List<Renderer>();
        internal static float StickRange = 14f;

        internal Dictionary<Transform, Vector3> Pinned = new Dictionary<Transform, Vector3>();

        internal TyphoonGearRig GearRig;
        internal RotaryBay Bay;
        internal static bool BayPreview;

        internal List<HardpointStation> Stations = new List<HardpointStation>();
        internal Vector3 ModelOffset; internal float ModelScale = 1f;

        internal Action LateLightFix;
        float _lateFixStart = -1f; int _lateFixes;
        int _pinFixes;

        static readonly List<TyphoonVisual> All = new List<TyphoonVisual>();
        internal static IEnumerable<TyphoonVisual> Live => All;
        void OnEnable() { if (!All.Contains(this)) All.Add(this); }
        void OnDisable() { All.Remove(this); }
        internal static void EnforceAllPins() { for (int i = 0; i < All.Count; i++) if (All[i] != null && All[i].Pinned.Count > 0) All[i].EnforcePins(); }

        void EnforcePins()
        {
            foreach (var kv in Pinned)
            {
                var t = kv.Key;
                if (t == null) continue;
                if ((t.localPosition - kv.Value).sqrMagnitude > 1e-6f)
                {
                    t.localPosition = kv.Value;
                    if (_pinFixes++ == 0) TyphoonPlugin.Instance?.LogInfo($"Wingtip light '{t.name}' is moved back by the game every frame; holding it on the Typhoon's wingtip.");
                }
            }
        }

        internal List<Renderer> PilotRenderers = new List<Renderer>();
        internal List<Transform> PilotParts = new List<Transform>();
        internal List<Renderer> SeatRenderers = new List<Renderer>();
        Vector3 _seatHome; bool _seatHomeSet, _seatFree; float _seatT0 = -1f, _nextSeatCheck;

        void WatchSeat(bool inCockpit)
        {
            if (SeatRenderers.Count == 0 || _seatFree || Aircraft == null || Time.unscaledTime < _nextSeatCheck) return;
            _nextSeatCheck = Time.unscaledTime + 0.25f;
            var sr = SeatRenderers[0];
            if (sr == null) return;
            Vector3 lp = Aircraft.transform.InverseTransformPoint(sr.transform.position);
            if (!_seatHomeSet)
            {
                if (_seatT0 < 0f) _seatT0 = Time.unscaledTime;
                if (Time.unscaledTime - _seatT0 > 1f) { _seatHome = lp; _seatHomeSet = true; }
            }
            else if ((lp - _seatHome).sqrMagnitude > 1f)
            {
                _seatFree = true;
                foreach (var r in SeatRenderers) if (r != null) r.forceRenderingOff = false;
            }
        }
        internal Vector3 PilotShiftRoot;
        readonly Dictionary<Transform, Vector3> _pilotSet = new Dictionary<Transform, Vector3>();

        void MovePilot()
        {
            if (PilotParts.Count == 0 || PilotShiftRoot == Vector3.zero || Aircraft == null) return;
            Vector3 world = Aircraft.transform.TransformVector(PilotShiftRoot);
            foreach (var t in PilotParts)
            {
                if (t == null || t.parent == null) continue;
                Vector3 last, cur = t.localPosition;
                if (_pilotSet.TryGetValue(t, out last) && (cur - last).sqrMagnitude < 1e-8f) continue;
                t.localPosition = cur + t.parent.InverseTransformVector(world);
                _pilotSet[t] = t.localPosition;
            }
        }

        float TargetOpenness()
        {
            float ab = 0f;
            if (AfterburnerRef != null)
            {
                if (_abAmountField == null) _abAmountField = AfterburnerRef.GetType().GetField("afterburnerAmount");
                if (_abAmountField != null) ab = (float)_abAmountField.GetValue(AfterburnerRef);
            }
            if (ab > 0.02f) return Mathf.Clamp01(ab);
            float thr = 0f;
            try { var ci = Aircraft != null ? Aircraft.GetInputs() : null; if (ci != null) thr = ci.throttle; } catch { }
            return 0.65f * (1f - Mathf.Clamp01(thr / 0.8f));
        }

        static readonly FieldInfo NavLightsF = typeof(Aircraft).GetField("navLights", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        static readonly FieldInfo NavOnF = typeof(NavLights).GetField("isOn", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        float SwitchState(string name)
        {
            switch (name)
            {
                case "sw_gear": return Aircraft.gearDeployed ? 1f : 0f;
                case "sw_ign": return Aircraft.Ignition ? 1f : 0f;
                case "sw_fa": return Aircraft.flightAssist ? 1f : 0f;
                case "sw_radar": { var r = Aircraft.radar; return r != null && r.activated ? 1f : 0f; }
                case "sw_nav":
                {
                    var nl = NavLightsF?.GetValue(Aircraft) as NavLights;
                    return nl != null && NavOnF != null && (bool)NavOnF.GetValue(nl) ? 1f : 0f;
                }
            }
            return 0.5f;
        }

        void UpdateSurfaces()
        {
            if (Aircraft == null || Surfaces.Count == 0) return;
            Quaternion rootInv = Quaternion.Inverse(Aircraft.transform.rotation);
            foreach (var s in Surfaces)
            {
                if (s.Pivot == null) continue;
                if (s.Input != null)
                {
                    float v = 0.5f;
                    try
                    {
                        if (s.Input == "gearlever") v = Aircraft.gearDeployed ? 1f : 0f;
                        else if (s.Input[0] == 's') v = SwitchState(s.Input);
                        else
                        {
                            var ci = Aircraft.GetInputs();
                            float yaw = ci != null ? Mathf.Clamp(ci.yaw, -1f, 1f) : 0f;
                            v = s.Input == "pedal_l" ? 0.5f + 0.5f * yaw : 0.5f - 0.5f * yaw;
                        }
                    }
                    catch { }
                    s.Openness = Mathf.MoveTowards(s.Openness, v, Time.deltaTime * (s.Input == "gearlever" ? 3f : (s.Input[0] == 's' ? 9f : 6f)));
                    s.Pivot.localRotation = Quaternion.AngleAxis(Mathf.Lerp(s.AngA, s.AngB, s.Openness), s.AxisLocal);
                    continue;
                }
                if (s.IsThrottle)
                {
                    float thr = 0f;
                    try { var ci = Aircraft.GetInputs(); if (ci != null) thr = Mathf.Clamp01(ci.throttle); } catch { }
                    s.Openness = Mathf.MoveTowards(s.Openness, thr, Time.deltaTime * 3f);
                    s.Pivot.localRotation = Quaternion.AngleAxis(Mathf.Lerp(s.AngA, s.AngB, s.Openness), s.AxisLocal);
                    continue;
                }
                if (s.IsStick)
                {
                    Quaternion q = Quaternion.identity;
                    var d0 = s.Drivers.Count > 0 ? s.Drivers[0] : null;
                    if (d0 != null && d0.parent != null)
                    {
                        Quaternion pv = rootInv * d0.parent.rotation;
                        q = pv * d0.localRotation * Quaternion.Inverse(pv);
                        float a; Vector3 axv; q.ToAngleAxis(out a, out axv);
                        if (a > 180f) a -= 360f;
                        if (Mathf.Abs(a) > 20f) q = Quaternion.AngleAxis(Mathf.Sign(a) * 20f, axv);
                    }
                    else
                    {
                        try
                        {
                            var ci = Aircraft.GetInputs();
                            if (ci != null) q = Quaternion.Euler(ci.pitch * StickRange, 0f, -ci.roll * StickRange);
                        }
                        catch { }
                    }
                    if (s.Pivot.parent == null) continue;
                    s.StickQ = Quaternion.Slerp(s.StickQ, q, 1f - Mathf.Exp(-Time.deltaTime * 14f));
                    Quaternion pp = rootInv * s.Pivot.parent.rotation;
                    s.Pivot.localRotation = Quaternion.Inverse(pp) * s.StickQ * pp;
                    continue;
                }
                if (s.AirbrakeRef != null)
                {
                    float open = AirbrakeOpenF != null ? (float)AirbrakeOpenF.GetValue(s.AirbrakeRef) : 0f;
                    s.Pivot.localRotation = Quaternion.AngleAxis(Mathf.Clamp01(open) * AirbrakeAngle, s.AxisLocal);
                    continue;
                }
                if (s.FullRotation)
                {
                    var d0 = s.Drivers[0];
                    if (d0 == null || s.Pivot.parent == null) continue;
                    if (d0.parent == null) continue;
                    Quaternion pv = rootInv * d0.parent.rotation;
                    Quaternion dRoot = pv * d0.localRotation * Quaternion.Inverse(pv);
                    float a; Vector3 axv; dRoot.ToAngleAxis(out a, out axv);
                    if (a > 180f) a -= 360f;
                    if (Mathf.Abs(a) > 30f) continue;
                    if (NozzleVectoring < 0.999f) dRoot = Quaternion.Slerp(Quaternion.identity, dRoot, NozzleVectoring);
                    Quaternion pp = rootInv * s.Pivot.parent.rotation;
                    s.Pivot.localRotation = Quaternion.Inverse(pp) * dRoot * pp;
                    if (s.IrisMesh != null)
                    {
                        s.Openness = Mathf.MoveTowards(s.Openness, TargetOpenness(), Time.deltaTime * 0.8f);
                        s.ApplyIris();
                    }
                    continue;
                }
                float total = 0f;
                for (int i = 0; i < s.Drivers.Count; i++)
                {
                    var d = s.Drivers[i];
                    if (d == null || d.parent == null) continue;
                    Quaternion delta = d.localRotation * Quaternion.Inverse(s.Rest[i]);
                    Quaternion p = rootInv * d.parent.rotation;
                    Quaternion deltaRoot = p * delta * Quaternion.Inverse(p);
                    float ang; Vector3 ax;
                    deltaRoot.ToAngleAxis(out ang, out ax);
                    if (float.IsNaN(ax.x) || ang < 0.01f) continue;
                    if (ang > 180f) ang -= 360f;
                    total += ang * Vector3.Dot(ax, s.AxisRoot);
                }
                s.Pivot.localRotation = Quaternion.AngleAxis(Mathf.Clamp(total, -45f, 45f), s.AxisLocal);
            }
        }
        internal List<Renderer> TyphoonGearDoors = new List<Renderer>();
        internal List<Renderer> OriginalGearDoors = new List<Renderer>();
        internal List<Renderer> OriginalGear = new List<Renderer>();
        internal List<float> GearCeiling = new List<float>();
        int _gear = -1;
        int _gearErrors;

        internal List<Renderer> LiverySources = new List<Renderer>();
        internal Material Body;
        internal Color FallbackColor;
        internal string LiveryMode = "Camo";
        Texture _lastLivery;
        bool _liveryChecked;
        float _nextLiveryCheck;

        void OnDestroy()
        {
            if (Cockpit != null && CockpitCamera.Active == Cockpit) { CockpitCamera.Active = null; CockpitCamera.RestoreAll(); }
        }

        void LateUpdate()
        {
            CockpitCamera.RestoreAll();
            if (Pinned.Count > 0) EnforcePins();
            for (int i = 0; i < Stations.Count; i++)
                try { Stations[i].Tick(); }
                catch (Exception e) { if (Stations[i].ReportError()) TyphoonPlugin.Instance?.LogError($"Hardpoint '{Stations[i].Name}': {e.Message}"); }
            if (GearRig != null)
            {
                try { GearRig.Tick(Time.deltaTime, BayPreview); }
                catch (Exception e) { if (_gearErrors++ < 3) TyphoonPlugin.Instance?.LogError("Typhoon gear: " + e); }
                try { Bay?.Tick(Aircraft, Stations, GearRig, Time.deltaTime); }
                catch (Exception e) { if (_gearErrors++ < 3) TyphoonPlugin.Instance?.LogError("Weapon bay: " + e); }
            }
            if (LateLightFix != null)
            {
                if (_lateFixStart < 0f) _lateFixStart = Time.unscaledTime;
                float due = _lateFixes == 0 ? 2f : 6f;
                if (Time.unscaledTime - _lateFixStart > due)
                {
                    _lateFixes++;
                    try { LateLightFix(); } catch (Exception e) { TyphoonPlugin.Instance?.LogError("Late light fix: " + e.Message); }
                    if (_lateFixes >= 2) LateLightFix = null;
                }
            }
            CockpitView();
            if (Halos.Count > 0) UpdateHalos(Camera.main);
            UpdateSurfaces();
            TyphoonSounds.Drift();
            if (_sound != null) _sound.Update();
            if (!_soundsDone && Aircraft != null && TyphoonSounds.Loaded && Built)
            {
                _soundsDone = true;
                int n = TyphoonSounds.Apply(Aircraft);
                _engines = TyphoonSounds.Engines(Aircraft);
                _sound = new EngineSoundShaper(Aircraft);
                if (n > 0) TyphoonPlugin.Instance?.LogInfo($"Typhoon engine sounds applied ({n} sources).");
            }
            foreach (var f in Flames) SyncFlame(f);
            if (Reheat != null)
            {
                for (int i = 0; i < FlameOriginals.Count; i++)
                    if (FlameOriginals[i] != null && !FlameOriginals[i].forceRenderingOff) FlameOriginals[i].forceRenderingOff = true;
                float exitScale = 1f;
                foreach (var sf in Surfaces) if (sf.FullRotation && sf.IrisMesh != null) { exitScale = sf.ExitScale(); break; }
                Reheat.Update(AfterburnerAmount(), exitScale);
            }
            foreach (var h in Hazes) SyncHaze(h);
            if (NavLamps.Count > 0 && Aircraft != null)
            {
                int on = 0;
                try { var nl = NavLightsF?.GetValue(Aircraft) as NavLights; on = nl != null && NavOnF != null && (bool)NavOnF.GetValue(nl) ? 1 : 0; } catch { }
                if (on != _navState)
                {
                    _navState = on;
                    if (_navBlock == null) _navBlock = new MaterialPropertyBlock();
                    foreach (var kv in NavLamps)
                    {
                        if (kv.Key == null) continue;
                        _navBlock.SetColor("_EmissionColor", on == 1 ? kv.Value : new Color(kv.Value.r * 0.012f, kv.Value.g * 0.012f, kv.Value.b * 0.012f, 1f));
                        kv.Key.SetPropertyBlock(_navBlock);
                    }
                }
            }
            if (GearLamps != null && Aircraft != null)
            {
                int want = Aircraft.gearDeployed ? 1 : 0;
                if (want != _lampWant) { _lampAt = Time.time + (_lampWant != -1 ? 3.5f : 0f); _lampWant = want; }
                int ls = Time.time < _lampAt ? 2 : want;
                if (ls != _lampState)
                {
                    _lampState = ls;
                    if (_lampBlock == null) _lampBlock = new MaterialPropertyBlock();
                    _lampBlock.SetColor("_EmissionColor", ls == 1 ? new Color(0.20f, 1.9f, 0.38f, 1f) : ls == 2 ? new Color(1.9f, 0.10f, 0.06f, 1f) : new Color(0f, 0.012f, 0.003f, 1f));
                    GearLamps.SetPropertyBlock(_lampBlock);
                }
            }
            if (Aircraft != null && (TyphoonGearDoors.Count > 0 || OriginalGearDoors.Count > 0))
            {
                int gear = Aircraft.gearDeployed ? 1 : 0;
                if (gear != _gear)
                {
                    _gear = gear;
                    foreach (var r in TyphoonGearDoors) if (r != null) r.forceRenderingOff = gear == 1;
                }
            }
            UpdateGear();
            if (Body != null && LiveryMode != "Plain" && Time.unscaledTime >= _nextLiveryCheck)
            {
                _nextLiveryCheck = Time.unscaledTime + 1f;
                UpdateLivery();
            }
        }

        Vector3[] _gearRest;
        float _gearDownSince = -1f;

        float _gearUpSince = -1f; bool _gearSeen;
        internal sealed class GearExtension { public Renderer R; public Transform Hinge; public Quaternion Rest; }
        internal List<GearExtension> GearExtensions = new List<GearExtension>();

        void UpdateGear()
        {
            if (Aircraft == null) return;
            var root = Aircraft.transform;
            int n = OriginalGear.Count;
            if (n == 0) return;

            if (Aircraft.gearDeployed) { if (_gearDownSince < 0f) _gearDownSince = Time.time; }
            else _gearDownSince = -1f;
            bool parked = Aircraft.gearDeployed && Aircraft.speed < 5f;
            if (parked || (_gearDownSince > 0f && Time.time - _gearDownSince > 5f))
            {
                if (_gearRest == null || _gearRest.Length != n) _gearRest = new Vector3[n];
                for (int i = 0; i < n; i++) if (OriginalGear[i] != null) _gearRest[i] = root.InverseTransformPoint(OriginalGear[i].bounds.center);
            }

            if (!Aircraft.gearDeployed) { if (_gearUpSince < 0f) _gearUpSince = _gearSeen ? Time.time : -100f; }
            else _gearUpSince = -1f;
            _gearSeen = true;
            bool stowed = !Aircraft.gearDeployed && Time.time - _gearUpSince > 4f;
            foreach (var ext in GearExtensions)
            {
                if (ext.R == null || ext.Hinge == null) continue;
                bool show = Aircraft.gearDeployed && Quaternion.Angle(ext.Hinge.localRotation, ext.Rest) < 4f;
                if (ext.R.forceRenderingOff == show) ext.R.forceRenderingOff = !show;
            }

            for (int i = 0; i < n; i++)
            {
                var r = OriginalGear[i];
                if (r == null) continue;
                float c = GearCeiling[i];
                bool hide;
                if (float.IsNegativeInfinity(c) || stowed) hide = true;
                else
                {
                    Vector3 p = root.InverseTransformPoint(r.bounds.center);
                    if (_gearRest != null)
                    {
                        bool atRest = Aircraft.gearDeployed && (p - _gearRest[i]).sqrMagnitude < 0.15f * 0.15f
                                      || Aircraft.gearDeployed && Mathf.Abs(p.x - _gearRest[i].x) < 0.08f && Mathf.Abs(p.z - _gearRest[i].z) < 0.08f && Mathf.Abs(p.y - _gearRest[i].y) < 0.35f;
                        hide = !atRest && p.y > c;
                    }
                    else hide = p.y > c + (parked ? 0.6f : 0f);
                }
                if (r.forceRenderingOff != hide) r.forceRenderingOff = hide;
            }
        }

        static readonly Regex FarKeep = new Regex("^Typhoon_(canopy_interior|cockpit_(shell|skinliner|deck$|panel$|seat|headpad|arch$|archliner|sill(beam|wall|rail|wedge)|hud|consoles|con[lr]$|aftpanels|aftboxes|dispunit|bezels))", RegexOptions.IgnoreCase);
        bool _far;
        int _farCount;
        List<Renderer> _farHide;
        void SetFar(bool far)
        {
            _far = far;
            if (_farHide == null || _farCount != Interior.Count)
            {
                _farCount = Interior.Count;
                _farHide = new List<Renderer>();
                foreach (var r in Interior) if (r != null && !FarKeep.IsMatch(r.name)) _farHide.Add(r);
            }
            foreach (var r in _farHide) if (r != null) r.forceRenderingOff = far;
        }

        void CockpitView()
        {
            if (Pilot == null) return;
            var cam = Camera.main;
            if (cam == null)
                foreach (var c in Camera.allCameras)
                    if (cam == null || c.depth > cam.depth) cam = c;
            float camD2 = cam != null ? (cam.transform.position - Pilot.position).sqrMagnitude : float.MaxValue;
            bool inCockpit = camD2 < Radius * Radius;
            if (InteriorMode)
            {
                if (cam != null)
                {
                    bool far = _far ? camD2 > 75f * 75f : camD2 > 90f * 90f;
                    if (far != _far) SetFar(far);
                }
                if (Cockpit != null) Cockpit.Update(inCockpit, cam);
                int st = inCockpit ? 3 : 2;
                if (_state != st)
                {
                    _state = st;
                    foreach (var r in OriginalCockpit) if (r != null) r.forceRenderingOff = true;
                    foreach (var r in TyphoonCockpit) if (r != null) r.forceRenderingOff = false;
                    foreach (var r in PilotRenderers) if (r != null) r.forceRenderingOff = inCockpit;
                    foreach (var r in SeatRenderers) if (r != null) r.forceRenderingOff = !_seatFree || inCockpit;
                }
                MovePilot();
                WatchSeat(inCockpit);
                return;
            }
            int state = inCockpit ? 1 : 0;
            if (state == _state) return;
            _state = state;
            foreach (var r in TyphoonCockpit) if (r != null) r.forceRenderingOff = inCockpit;
            foreach (var r in OriginalCockpit) if (r != null) r.forceRenderingOff = !inCockpit;
        }

        static void SyncFlame(FlameCopy f)
        {
            var o = f.Original;
            if (o == null) return;
            o.forceRenderingOff = true;
            var ls = o.transform.localScale;
            for (int i = 0; i < f.Clones.Count; i++)
            {
                var c = f.Clones[i];
                if (c == null) continue;
                c.enabled = o.enabled;
                if (c.sharedMaterial != o.sharedMaterial) c.sharedMaterial = o.sharedMaterial;
                c.transform.localScale = Vector3.Scale(ls, f.ScaleMuls[i]);
            }
        }

        void UpdateLivery()
        {
            Texture tex = null;
            foreach (var r in LiverySources)
            {
                if (r == null) continue;
                var m = r.sharedMaterial;
                if (m != null && m.HasProperty("_Livery")) { tex = m.GetTexture("_Livery"); if (tex != null) break; }
            }
            if (tex == _lastLivery && _liveryChecked) return;
            _lastLivery = tex;
            _liveryChecked = true;
            LiveryPaint.Apply(Body, tex, FallbackColor, LiveryMode);
        }
    }

    internal sealed class SurfaceDef
    {
        public Vector3 A, B;
        public string[] Drivers;
        public float Ang = 15f;
        public bool HasAng;

        public static Dictionary<string, SurfaceDef> Load(string path, ManualLogSource log)
        {
            var d = new Dictionary<string, SurfaceDef>();
            if (!File.Exists(path)) return d;
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                var t = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                if (t.Length < 8) continue;
                Func<int, float> f = i => float.Parse(t[i], NumberStyles.Float, CultureInfo.InvariantCulture);
                var sdef = new SurfaceDef { A = new Vector3(f(1), f(2), f(3)), B = new Vector3(f(4), f(5), f(6)), Drivers = t[7].Split('+') };
                if (t.Length > 8) { float a9; if (float.TryParse(t[8], NumberStyles.Float, CultureInfo.InvariantCulture, out a9)) { sdef.Ang = a9; sdef.HasAng = true; } }
                d[t[0]] = sdef;
            }
            log.LogInfo($"Loaded {d.Count} control-surface definitions.");
            return d;
        }
    }

    internal static class TexturedMaterials
    {
        public static Dictionary<string, Material> Load(string path, ManualLogSource log)
        {
            var result = new Dictionary<string, Material>();
            if (!File.Exists(path)) return result;
            var lit = Shader.Find("Universal Render Pipeline/Lit");
            if (lit == null) { log.LogWarning("URP Lit shader not found; textured materials skipped."); return result; }
            string dir = Path.GetDirectoryName(path);
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                var tok = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                var kv = new Dictionary<string, string>();
                for (int i = 1; i < tok.Length; i++)
                {
                    int eq = tok[i].IndexOf('=');
                    if (eq > 0) kv[tok[i].Substring(0, eq).ToLowerInvariant()] = tok[i].Substring(eq + 1);
                }
                try { result[tok[0]] = Build(tok[0], kv, dir, lit, log); }
                catch (Exception e) { log.LogWarning($"Material '{tok[0]}' failed: {e.Message}"); }
            }
            log.LogInfo($"Loaded {result.Count} textured material(s) from {Path.GetFileName(path)}.");
            return result;
        }

        static Material Build(string name, Dictionary<string, string> kv, string dir, Shader lit, ManualLogSource log)
        {
            var m = new Material(lit) { name = "Typhoon_" + name };
            Color color = Color.white;
            string s;
            if (kv.TryGetValue("color", out s)) ColorUtility.TryParseHtmlString(s, out color);
            float alpha = kv.TryGetValue("alpha", out s) ? F(s, 1f) : 1f;
            color.a = alpha;
            Built[name] = new KeyValuePair<Material, Color>(m, color);
            float tone;
            if (Tone.TryGetValue(name, out tone) && tone != 1f) { color.r *= tone; color.g *= tone; color.b *= tone; }
            m.SetColor("_BaseColor", color);
            m.SetFloat("_Smoothness", kv.TryGetValue("smooth", out s) ? F(s, 0.5f) : 0.5f);
            m.SetFloat("_Metallic", kv.TryGetValue("metal", out s) ? F(s, 0f) : 0f);

            if (kv.TryGetValue("base", out s)) m.SetTexture("_BaseMap", LoadTex(dir, s, false));
            if (kv.TryGetValue("normal", out s))
            {
                m.SetTexture("_BumpMap", LoadTex(dir, s, true));
                m.SetFloat("_BumpScale", 1f);
                m.EnableKeyword("_NORMALMAP");
            }
            if (kv.TryGetValue("emit", out s))
            {
                float k = 1f; string ks;
                if (kv.TryGetValue("emitstrength", out ks)) k = F(ks, 1f);
                m.SetTexture("_EmissionMap", LoadTex(dir, s, false));
                m.SetColor("_EmissionColor", new Color(k, k, k, 1f));
                m.EnableKeyword("_EMISSION");
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            }
            if (kv.TryGetValue("emitcolor", out s))
            {
                Color ec; ColorUtility.TryParseHtmlString(s, out ec);
                m.SetColor("_EmissionColor", ec);
                m.EnableKeyword("_EMISSION");
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            }
            if (kv.TryGetValue("mask", out s))
            {
                m.SetTexture("_MetallicGlossMap", LoadTex(dir, s, true));
                m.SetFloat("_SmoothnessTextureChannel", 0f);
                m.EnableKeyword("_METALLICSPECGLOSSMAP");
            }
            if (alpha < 0.999f)
            {
                m.SetFloat("_Surface", 1f);
                m.SetFloat("_Blend", 0f);
                m.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.SrcAlpha);
                m.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
                m.SetFloat("_ZWrite", 0f);
                m.SetOverrideTag("RenderType", "Transparent");
                m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
            }
            else m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Geometry;
            return m;
        }

        static readonly Dictionary<string, Texture2D> Loaded = new Dictionary<string, Texture2D>();
        internal static string CacheDir;
        internal static int FromDisk, Decoded, Packed;
        internal static bool UsePacked = true;
        internal static readonly Dictionary<string, float> Tone = new Dictionary<string, float>(StringComparer.OrdinalIgnoreCase);
        static readonly Dictionary<string, KeyValuePair<Material, Color>> Built = new Dictionary<string, KeyValuePair<Material, Color>>(StringComparer.OrdinalIgnoreCase);

        internal static void SetTone(string name, float tone)
        {
            Tone[name] = tone;
            KeyValuePair<Material, Color> b;
            if (!Built.TryGetValue(name, out b) || b.Key == null) return;
            Color c = b.Value; c.r *= tone; c.g *= tone; c.b *= tone;
            b.Key.SetColor("_BaseColor", c);
        }

        internal static float CockpitSharpness = 0.3f;
        internal static float MipBias(string name)
        {
            if (string.IsNullOrEmpty(name) || !(name.StartsWith("ck") || name.StartsWith("cockpit"))) return 0f;
            return -CockpitSharpness;
        }

        internal static Texture2D LoadTex(string dir, string file, bool linear)
        {
            var path = Path.Combine(dir, file);
            string key = path + (linear ? "|L" : "|S");
            Texture2D tex;
            if (Loaded.TryGetValue(key, out tex) && tex != null) return tex;
            string pre = Path.Combine(dir, Path.GetFileNameWithoutExtension(file) + ".tex");
            if (UsePacked && File.Exists(pre))
            {
                tex = ReadTex(pre, file, linear, false);
                if (tex != null) Packed++;
            }
            if (tex == null)
            {
                tex = ReadCache(path, file, linear);
                if (tex != null) FromDisk++;
                else { tex = Decode(path, file, linear); Decoded++; }
            }
            Loaded[key] = tex;
            return tex;
        }

        static string CachePath(string path, string file, bool linear)
        {
            if (string.IsNullOrEmpty(CacheDir)) return null;
            var fi = new FileInfo(path);
            if (!fi.Exists) return null;
            return Path.Combine(CacheDir, file + "." + fi.Length.ToString("x") + "." + fi.LastWriteTimeUtc.Ticks.ToString("x") + (linear ? ".L" : ".S") + ".tex");
        }

        static Texture2D ReadCache(string path, string file, bool linear)
        {
            string cp = CachePath(path, file, linear);
            if (cp == null || !File.Exists(cp)) return null;
            return ReadTex(cp, file, linear, true);
        }

        static Texture2D ReadTex(string cp, string file, bool linear, bool isCache)
        {
            try
            {
                using (var br = new BinaryReader(File.OpenRead(cp)))
                {
                    if (br.ReadInt32() != 0x31545954) return null;
                    int w = br.ReadInt32(), h = br.ReadInt32(), fmt = br.ReadInt32(), mips = br.ReadInt32(), len = br.ReadInt32();
                    if (!SystemInfo.SupportsTextureFormat((TextureFormat)fmt))
                    {
                        TyphoonPlugin.Instance?.LogInfo($"{Path.GetFileName(cp)}: this graphics card does not take {(TextureFormat)fmt}; using the PNG.");
                        return null;
                    }
                    var data = br.ReadBytes(len);
                    if (data.Length != len) return null;
                    var tex = new Texture2D(w, h, (TextureFormat)fmt, mips, linear) { name = Path.GetFileNameWithoutExtension(file) };
                    tex.LoadRawTextureData(data);
                    tex.wrapMode = TextureWrapMode.Repeat;
                    tex.anisoLevel = isCache ? 8 : 16;
                    tex.mipMapBias = TexturedMaterials.MipBias(tex.name);
                    tex.Apply(false, true);
                    return tex;
                }
            }
            catch (Exception e)
            {
                TyphoonPlugin.Instance?.LogInfo($"{(isCache ? "Texture cache for " + file : Path.GetFileName(cp))} unreadable ({e.Message}); decoding the PNG.");
                if (isCache) try { File.Delete(cp); } catch { }
                return null;
            }
        }

        static void WriteCache(string path, string file, bool linear, Texture2D tex)
        {
            try
            {
                var cp = CachePath(path, file, linear);
                if (cp == null) return;
                Directory.CreateDirectory(CacheDir);
                foreach (var old in Directory.GetFiles(CacheDir, file + ".*" + (linear ? ".L" : ".S") + ".tex"))
                    try { File.Delete(old); } catch { }
                var data = tex.GetRawTextureData();
                using (var bw = new BinaryWriter(File.Create(cp)))
                {
                    bw.Write(0x31545954); bw.Write(tex.width); bw.Write(tex.height); bw.Write((int)tex.format); bw.Write(tex.mipmapCount);
                    bw.Write(data.Length); bw.Write(data);
                }
            }
            catch (Exception e) { TyphoonPlugin.Instance?.LogInfo($"Texture cache for {file} not written: {e.Message}"); }
        }

        static Texture2D Decode(string path, string file, bool linear)
        {
            var tex = new Texture2D(2, 2, TextureFormat.RGBA32, true, linear) { name = Path.GetFileNameWithoutExtension(file) };
            if (!ImageConversion.LoadImage(tex, File.ReadAllBytes(path), false))
                throw new IOException("could not decode " + file);
            tex.wrapMode = TextureWrapMode.Repeat;
            tex.anisoLevel = 8;
            tex.mipMapBias = TexturedMaterials.MipBias(tex.name);
            tex.Apply(true, false);
            if (tex.width >= 2048 && tex.width % 4 == 0 && tex.height % 4 == 0)
                try { tex.Compress(true); } catch { }
            WriteCache(path, file, linear, tex);
            tex.Apply(false, true);
            return tex;
        }

        internal static List<KeyValuePair<string, bool>> TextureList(string path)
        {
            var list = new List<KeyValuePair<string, bool>>();
            if (!File.Exists(path)) return list;
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                foreach (var tok in line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries))
                {
                    int eq = tok.IndexOf('=');
                    if (eq <= 0) continue;
                    string k = tok.Substring(0, eq).ToLowerInvariant(), v = tok.Substring(eq + 1);
                    if (k == "base" || k == "emit") list.Add(new KeyValuePair<string, bool>(v, false));
                    else if (k == "normal" || k == "mask") list.Add(new KeyValuePair<string, bool>(v, true));
                }
            }
            return list;
        }

        static float F(string s, float d)
        {
            float v;
            return float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out v) ? v : d;
        }
    }

    internal static class LiveryPaint
    {
        static readonly Dictionary<Texture, Texture2D> Cache = new Dictionary<Texture, Texture2D>();

        public static void Apply(Material body, Texture livery, Color fallback, string mode)
        {
            Texture2D paint = null;
            if (livery != null)
            {
                if (!Cache.TryGetValue(livery, out paint))
                {
                    var palette = Palette(livery);
                    paint = palette.Count == 0 ? null : Camo(palette, mode == "Camo");
                    Cache[livery] = paint;
                    TyphoonPlugin.Instance?.LogInfo($"Livery '{livery.name}': {palette.Count} colour(s) " +
                        string.Join(" ", palette.Select(c => "#" + ColorUtility.ToHtmlStringRGB(c)).ToArray()));
                }
            }
            if (paint != null)
            {
                body.SetTexture("_BaseMap", paint);
                body.SetColor("_BaseColor", Color.white);
            }
            else
            {
                body.SetTexture("_BaseMap", null);
                body.SetColor("_BaseColor", fallback);
            }
        }

        static List<Color> Palette(Texture tex)
        {
            const int N = 48;
            var rt = RenderTexture.GetTemporary(N, N, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var prev = RenderTexture.active;
            Graphics.Blit(tex, rt);
            RenderTexture.active = rt;
            var read = new Texture2D(N, N, TextureFormat.RGBA32, false);
            read.ReadPixels(new Rect(0, 0, N, N), 0, 0);
            read.Apply();
            RenderTexture.active = prev;
            RenderTexture.ReleaseTemporary(rt);

            var px = read.GetPixels().Where(c => { float l = Lum(c); return l > 0.04f && l < 0.97f; }).ToList();
            UnityEngine.Object.Destroy(read);
            if (px.Count < 20) return new List<Color>();

            var sorted = px.OrderBy(Lum).ToList();
            var centres = new[] { sorted[sorted.Count / 6], sorted[sorted.Count / 2], sorted[sorted.Count * 5 / 6] };
            var counts = new int[3];
            for (int it = 0; it < 8; it++)
            {
                var sum = new Vector3[3];
                counts = new int[3];
                foreach (var c in px)
                {
                    int best = 0; float bd = float.MaxValue;
                    for (int k = 0; k < 3; k++) { float d = Dist(c, centres[k]); if (d < bd) { bd = d; best = k; } }
                    sum[best] += new Vector3(c.r, c.g, c.b);
                    counts[best]++;
                }
                for (int k = 0; k < 3; k++)
                    if (counts[k] > 0) { var v = sum[k] / counts[k]; centres[k] = new Color(v.x, v.y, v.z, 1); }
            }
            var result = new List<Color>();
            for (int k = 0; k < 3; k++)
            {
                if (counts[k] < px.Count * 0.08f) continue;
                if (result.Any(c => Dist(c, centres[k]) < 0.004f)) continue;
                result.Add(centres[k]);
            }
            return result.OrderBy(Lum).ToList();
        }

        static Texture2D Camo(List<Color> palette, bool pattern)
        {
            const int S = 256;
            var tex = new Texture2D(S, S, TextureFormat.RGBA32, true) { name = "TyphoonCamo", wrapMode = TextureWrapMode.Repeat };
            var px = new Color[S * S];
            for (int y = 0; y < S; y++)
                for (int x = 0; x < S; x++)
                {
                    Color c;
                    if (!pattern || palette.Count == 1) c = palette[palette.Count / 2];
                    else
                    {
                        float n = 0.65f * Noise(x, y, 4, S) + 0.35f * Noise(x + 97, y + 31, 9, S);
                        int idx = palette.Count == 2 ? (n < 0.5f ? 0 : 1) : (n < 0.40f ? 0 : n < 0.62f ? 1 : 2);
                        c = palette[Mathf.Min(idx, palette.Count - 1)];
                    }
                    px[y * S + x] = c;
                }
            tex.SetPixels(px);
            tex.Apply(true);
            return tex;
        }

        static float Noise(int x, int y, int cells, int size)
        {
            float fx = (float)x / size * cells, fy = (float)y / size * cells;
            int x0 = Mathf.FloorToInt(fx), y0 = Mathf.FloorToInt(fy);
            float tx = Smooth(fx - x0), ty = Smooth(fy - y0);
            float a = Hash(x0, y0, cells), b = Hash(x0 + 1, y0, cells), c = Hash(x0, y0 + 1, cells), d = Hash(x0 + 1, y0 + 1, cells);
            return Mathf.Lerp(Mathf.Lerp(a, b, tx), Mathf.Lerp(c, d, tx), ty);
        }
        static float Smooth(float t) => t * t * (3 - 2 * t);
        static float Hash(int x, int y, int period)
        {
            x = ((x % period) + period) % period; y = ((y % period) + period) % period;
            uint h = (uint)(x * 374761393 + y * 668265263 + period * 982451653);
            h = (h ^ (h >> 13)) * 1274126177u;
            return (h & 0xFFFF) / 65535f;
        }
        static float Lum(Color c) => 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;
        static float Dist(Color a, Color b) { float r = a.r - b.r, g = a.g - b.g, bl = a.b - b.b; return r * r + g * g + bl * bl; }
    }

    internal sealed class ModelSwap
    {
        static readonly FieldInfo ExteriorField = typeof(Aircraft).GetField("exteriorRenderers", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo PylonOptionsField = typeof(Hardpoint).GetField("pylonOptions", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo PylonRendererField = typeof(Hardpoint).GetNestedType("HardpointPylon", BindingFlags.Public | BindingFlags.NonPublic)?.GetField("renderer", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo CockpitField = typeof(Aircraft).GetField("cockpitRenderers", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

        readonly ManualLogSource _log;
        readonly string _pluginDir;
        readonly ConfigEntry<bool> _enabled;
        readonly ConfigEntry<string> _modelFile;
        readonly ConfigEntry<bool> _hideUnlisted;
        readonly ConfigEntry<string> _keep;
        readonly ConfigEntry<float> _scale;
        readonly ConfigEntry<string> _offset;
        readonly ConfigEntry<bool> _raiseForGear, _moveHaze;
        readonly ConfigEntry<bool> _interior;
        readonly ConfigEntry<bool> _gameStick, _gameStickUpright, _hideGameSeat;
        readonly ConfigEntry<string> _gameStickTilt;
        readonly ConfigEntry<float> _gameStickTop, _gameStickScale, _gameStickYaw;
        ConfigEntry<bool> _gameStickSeat;
        readonly ConfigEntry<string> _gameStickOffset;
        readonly ConfigEntry<int> _cockpitLayer;
        CockpitDef _cockpitDef; bool _cockpitDefLoaded;
        readonly ConfigEntry<string> _bodyColor;
        readonly ConfigEntry<bool> _attachToParts;
        readonly ConfigEntry<bool> _alignCockpit;
        readonly ConfigEntry<string> _cockpitParts;
        readonly ConfigEntry<string> _liveryMode;
        readonly ConfigEntry<bool> _twinFlames;
        readonly ConfigEntry<bool> _ownReheat, _reheatLamps;
        readonly ConfigEntry<bool> _moveHardpoints;
        readonly ConfigEntry<bool> _nozzleIris;
        readonly ConfigEntry<bool> _typhoonGear;
        GearDef _gearDef; bool _gearDefLoaded;
        internal static bool IsGearOrBay(string part) => part.StartsWith("gear_", StringComparison.OrdinalIgnoreCase) || part.StartsWith("bay_", StringComparison.OrdinalIgnoreCase);
        readonly ConfigEntry<float> _irisOpen;
        readonly ConfigEntry<float> _irisClosed;
        static readonly FieldInfo AfterburnersField = typeof(JetNozzle).GetField("afterburners", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

        readonly HashSet<AircraftDefinition> _definitions = new HashSet<AircraftDefinition>();
        List<ObjGroup> _model;
        Bounds _modelBounds;
        bool _modelFailed;
        bool _wroteReport;
        float _nextTick;
        Dictionary<string, Material> _mats;
        Dictionary<string, Material> _fileMats;
        Dictionary<string, SurfaceDef> _surfaceDefs;
        static readonly FieldInfo VectoringField = typeof(Turbojet).GetField("vectoringTransforms", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo VisibleMeshField = typeof(ControlSurface).GetField("visibleMesh", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        readonly Dictionary<int, int> _attempts = new Dictionary<int, int>();
        readonly HashSet<Aircraft> _pending = new HashSet<Aircraft>();
        float _nextFullScan;
        const int MaxAttempts = 100;
        const float SettledRadius = 40f;

        public ModelSwap(ConfigFile cfg, ManualLogSource log, string pluginDir)
        {
            _log = log;
            _pluginDir = pluginDir;
            _enabled = cfg.Bind("Model", "ReplaceModel", true, "Replace the base jet's exterior with the Typhoon model.");
            _modelFile = cfg.Bind("Model", "ModelFile", "typhoon.obj", "OBJ file (next to the DLL) to use as the exterior.");
            _hideUnlisted = cfg.Bind("Model", "HideUnlistedRenderers", true,
                "The game's own list of exterior meshes is always hidden. When true, other non-cockpit meshes\n" +
                "(control surfaces etc.) are hidden too unless they match KeepRenderers.");
            _keep = cfg.Bind("Model", "KeepRenderers",
                "gear|wheel|tyre|tire|strut|hook|pylon|hardpoint|rail|launcher|missile|bomb|tank|flare|chaff|" +
                "navlight|strobe|beacon|afterburner|flame|exhaust|plume|glow|trail|smoke|fx|effect|particle|vapor|vapour",
                "Regex (case-insensitive) for extra meshes that should stay visible. Only used with HideUnlistedRenderers.\n" +
                "See BepInEx/config/TyphoonMod_renderers.txt after the first spawn for the full list.");
            _scale = cfg.Bind("Model", "ScaleMultiplier", 1.0f, "1.0 = same length as the original jet.");
            _offset = cfg.Bind("Model", "Offset", "0, 0, 0", "Extra model offset in metres: right, up, forward.");
            _raiseForGear = cfg.Bind("Model", "RaiseForGear", true,
                "Lift the Typhoon so the original main-gear mounts sit inside its wing (the Revoker's wing is higher than the Typhoon's).\n" +
                "Offset is added on top.");
            _moveHaze = cfg.Bind("Model", "TwinHeatHaze", true, "Move the engine heat shimmer to the Typhoon's nozzles, one per nozzle.");
            _interior = cfg.Bind("Cockpit", "TyphoonCockpit", true,
                "Use the Typhoon model's own cockpit (panel, stick, HUD glass, live displays) instead of the original jet's.");
            TyphoonCockpit.AlignEye = cfg.Bind("Cockpit", "AlignEye", true,
                "In cockpit view, move your viewpoint to the Typhoon's design eye point (the original jet's eye sits elsewhere).").Value;
            TyphoonCockpit.EyeOffset = ParseVector(cfg.Bind("Cockpit", "EyeOffset", "0, 0, 0",
                "Fine-tune the cockpit eye point in metres: right, up, forward.").Value);
            TyphoonCockpit.LiveDisplays = cfg.Bind("Cockpit", "LiveDisplays", true,
                "Live head-down displays: tactical screen in the centre, engine/fuel page on the left, flight page on the right.").Value;
            TyphoonCockpit.FlipTac = cfg.Bind("Cockpit", "FlipTacScreen", false, "Turn the centre (tactical) display upside down, if it shows inverted.").Value;
            TyphoonCockpit.TacCopy = cfg.Bind("Cockpit", "CentreDisplayCleanSwitch", true, "The centre display holds its last picture for a moment while the game switches between radar and target / landing camera, so it changes cleanly. Turn off if the centre display misbehaves.").Value;
            TyphoonCockpit.TacSwitchHold = Mathf.Clamp(cfg.Bind("Cockpit", "CentreDisplaySwitchTime", 0.35f, "Seconds the old picture is held while the centre display changes (0.1 - 1).").Value, 0.1f, 1f);
            TyphoonCockpit.TacArea = cfg.Bind("Cockpit", "TacScreenArea", "auto",
                "Part of the game's tactical screen shown on the centre display: x, y, width, height (0-1, from the bottom left), or auto.").Value.Trim();
            TyphoonCockpit.NightMode = cfg.Bind("Cockpit", "NightLighting", "on",
                "Cockpit lighting (backlit panel legends, and the green floodlights if FloodBrightness is above 0): on = always, auto = comes on at dusk, off. The displays dim only when it is really dark outside, whatever this says.").Value.Trim().ToLowerInvariant();
            TyphoonCockpit.FloodBrightness = cfg.Bind("Cockpit", "FloodBrightness", 0f, "Brightness of the green cockpit floodlights while the cockpit lighting is on (0 = none, 1 = full).").Value;
            TyphoonCockpit.LegendBrightness = cfg.Bind("Cockpit", "LegendBrightness", 1f, "Brightness of the backlit key and panel legends while the cockpit lighting is on (1 = default, 0 = off).").Value;
            TyphoonCockpit.DisplayNight = cfg.Bind("Cockpit", "DisplayNightBrightness", 0.35f, "Brightness of the live displays when it is dark outside, relative to day (0.35 = about a third).").Value;
            TyphoonCockpit.LeftPageKey = cfg.Bind("Cockpit", "LeftDisplayKey", KeyCode.LeftBracket, "Key that steps the left display through its pages (ENG, FUEL, HYD).").Value;
            TyphoonCockpit.RightPageKey = cfg.Bind("Cockpit", "RightDisplayKey", KeyCode.RightBracket, "Key that steps the right display through its pages (FLT, NAV, WPN).").Value;
            TyphoonCockpit.DisplaySmudges = 0f;
            TyphoonCockpit.CanopyReflections = cfg.Bind("Cockpit", "CanopyReflections", 0f, "Strength of the displays' reflections in the canopy sides at night (0 = off).").Value;
            CockpitSounds.Enabled = cfg.Bind("Sounds", "CockpitSounds", false, "Switch clicks, gear lever clunk, attention tone and missile warning tone in the cockpit.").Value;
            CockpitSounds.Volume = cfg.Bind("Sounds", "CockpitVolume", 0f, "Volume of the cockpit sounds (0..1).").Value;
            TyphoonCockpit.GlowMode = cfg.Bind("Cockpit", "LegendGlow", "overlay", "How backlit legends are drawn: overlay (unlit overlay, works in the game's build) or material (shader emission).").Value.Trim().ToLowerInvariant();
            TyphoonVisual.StickRange = cfg.Bind("Cockpit", "StickTravel", 14f, "Stick deflection in degrees at full input (used when the original stick isn't found).").Value;
            _hideGameSeat = cfg.Bind("Cockpit", "HideGameSeat", true,
                "Hide the base jet's ejection seat while the pilot sits in the Typhoon's own seat (lifted to the Typhoon's eye\n" +
                "height its top stood through the canopy). It shows again when he ejects.");
            _gameStick = cfg.Bind("Cockpit", "GameStick", true,
                "Show the base jet's own control stick in the Typhoon cockpit instead of the modelled grip. It stands on the\n" +
                "Typhoon's stick boot and moves as before. Off = the modelled Typhoon grip.");
            _gameStickSeat = cfg.Bind("Cockpit", "GameStickSeat", true,
                "With GameStick: the stick stands in a mounting cup on a short column that goes down into the pedestal's well\n" +
                "(made to the measured size of the stick's foot), instead of on the modelled boot it did not fit.");
            _gameStickTop = cfg.Bind("Cockpit", "GameStickTop", 0.27f,
                "Height of the top of the game's stick above the stick pivot, metres (the modelled grip's top is at 0.27).");
            _gameStickOffset = cfg.Bind("Cockpit", "GameStickOffset", "0, 0, 0",
                "Move the game's stick: right, up, forward in metres.");
            _gameStickScale = cfg.Bind("Cockpit", "GameStickScale", 1f, "Size of the game's stick (1 = as in the base jet).");
            _gameStickYaw = cfg.Bind("Cockpit", "GameStickYaw", 0f, "Turn the game's stick about its upright axis, degrees.");
            _gameStickUpright = cfg.Bind("Cockpit", "GameStickUpright", true,
                "Stand the game's stick upright on the boot (in the base jet it leans). Off = as it stands in the base jet.");
            _gameStickTilt = cfg.Bind("Cockpit", "GameStickTilt", "0, 0, 0",
                "Lean the game's stick after that: degrees forward, degrees to the right (third number unused).");
            _cockpitLayer = cfg.Bind("Cockpit", "InteriorLayer", -1,
                "Render layer for the Typhoon cockpit. -1 = the same layer as the original cockpit (recommended).");
            _bodyColor = cfg.Bind("Model", "BodyColor", "#7A8188", "Paint colour (HTML hex). Typhoon grey is about #7A8188.");
            _attachToParts = cfg.Bind("Model", "AttachToParts", true,
                "Parent each Typhoon part to the original part it overlaps so damage (lost wings etc.) still shows.");
            _cockpitParts = cfg.Bind("Model", "HideInCockpitView", "^canopy|^fuselage_cockpit",
                "Regex of Typhoon parts hidden while you're in cockpit view (so the original cockpit interior shows).");
            _liveryMode = cfg.Bind("Paint", "LiveryMode", "Camo",
                "Camo = camouflage in the selected livery's colours.  Solid = the livery's main colour.  Plain = always BodyColor.");
            _twinFlames = cfg.Bind("Model", "TwinAfterburners", true, "Show an afterburner flame behind each of the Typhoon's two nozzles.");
            _ownReheat = cfg.Bind("Model", "TyphoonReheat", true,
                "The Typhoon's own afterburner: a glowing throat, a smooth orange plume with shock diamonds and a lamp that lights the\n" +
                "nozzle and tail. Off = copies of the base jet's flame, as before (needs a respawn).");
            _reheatLamps = cfg.Bind("Model", "ReheatLamps", true, "Reheat lights the nozzle petals, the tail and the ground (one small lamp per nozzle; needs a respawn).");
            var rb = cfg.Bind("Model", "ReheatBrightness", 1f, "Brightness of the Typhoon's own afterburner flame (0.3 - 3).");
            var rl = cfg.Bind("Model", "ReheatLength", 1f, "Length of the Typhoon's own afterburner plume (0.4 - 2).");
            ReheatFlame.Brightness = Mathf.Clamp(rb.Value, 0.3f, 3f); rb.SettingChanged += (o_, a_) => ReheatFlame.Brightness = Mathf.Clamp(rb.Value, 0.3f, 3f);
            ReheatFlame.Length = Mathf.Clamp(rl.Value, 0.4f, 2f); rl.SettingChanged += (o_, a_) => ReheatFlame.Length = Mathf.Clamp(rl.Value, 0.4f, 2f);
            var nv = cfg.Bind("Model", "ThrustVectoringSwing", 1f,
                "How far the Typhoon's nozzles swing with the base jet's thrust vectoring: 1 = the full angle, 0 = they stay\n" +
                "straight (the real Typhoon has no thrust vectoring). Looks only; the flight model is the base jet's either way.");
            TyphoonVisual.NozzleVectoring = Mathf.Clamp01(nv.Value); nv.SettingChanged += (o_, a_) => TyphoonVisual.NozzleVectoring = Mathf.Clamp01(nv.Value);
            var rw = cfg.Bind("Model", "ReheatWidth", 1f, "Width of the Typhoon's own afterburner flame at the nozzle (0.6 - 1.6; 1 = fills the nozzle).");
            ReheatFlame.Width = Mathf.Clamp(rw.Value, 0.6f, 1.6f); rw.SettingChanged += (o_, a_) => ReheatFlame.Width = Mathf.Clamp(rw.Value, 0.6f, 1.6f);
            _moveHardpoints = cfg.Bind("Model", "AlignWeapons", true,
                "Place the weapon hardpoints where typhoon_hardpoints.txt (next to the DLL) says: wingtip rails on the outer\n" +
                "pylons, wing pylons on the middle pylons, bay missiles semi-recessed under the belly. Edit the places in the\n" +
                "hangar with the placement editor (Weapons > EditorKey). Missiles launch from the new positions.");
            _typhoonGear = cfg.Bind("Model", "TyphoonGear", true,
                "Show the Typhoon's own landing gear (legs folding inwards into the belly, nose leg folding back, doors, side stays)\n" +
                "and the centre weapon bay with its rotary launcher, driven by the base jet's gear and bay doors.\n" +
                "The base jet's gear still does the physics. Off = the base jet's gear, as before.");
            _nozzleIris = cfg.Bind("Model", "NozzleIris", true,
                "Open and close the nozzle exits with the throttle like a real EJ200: open at idle, closing towards full dry power, opening wide in reheat.");
            _irisOpen = cfg.Bind("Model", "NozzleOpenScale", 1.18f, "Exit diameter at fully open, relative to the model.");
            _irisClosed = cfg.Bind("Model", "NozzleClosedScale", 0.86f, "Exit diameter at fully closed (full dry power), relative to the model.");
            _alignCockpit = cfg.Bind("Model", "AlignToCockpit", true,
                "Slide the Typhoon fore/aft so its canopy sits over the original pilot seat.");
        }

        public void Register(AircraftDefinition definition)
        {
            if (_enabled.Value) _definitions.Add(definition);
        }

        public void Tick()
        {
            if (!_enabled.Value || _definitions.Count == 0 || _modelFailed) return;
            if (Time.unscaledTime < _nextTick) return;
            _nextTick = Time.unscaledTime + 0.1f;
            if (_preloading && Time.realtimeSinceStartup - _preloadStart > 180f)
            {
                _preloading = false;
                _log.LogWarning("Typhoon preload did not finish; loading on demand.");
            }
            if (_model == null) { if (_preloading) return; if (!LoadModel()) return; }
            if (_preloading) return;

            if (Time.unscaledTime >= _nextFullScan)
            {
                _nextFullScan = Time.unscaledTime + 2f;
                foreach (var a in UnityEngine.Object.FindObjectsOfType<Aircraft>()) if (a != null) _pending.Add(a);
            }
            if (_pending.Count == 0) return;
            foreach (var aircraft in _pending.ToList())
            {
                if (aircraft == null) { _pending.Remove(aircraft); continue; }
                if (aircraft == null) continue;
                var tv = aircraft.GetComponent<TyphoonVisual>();
                if (tv != null && tv.Built) { _pending.Remove(aircraft); continue; }
                var def = aircraft.definition as AircraftDefinition;
                if (def == null || !_definitions.Contains(def)) { _pending.Remove(aircraft); continue; }
                int id = aircraft.GetInstanceID();
                int tries;
                _attempts.TryGetValue(id, out tries);
                _attempts[id] = ++tries;
                bool done;
                try { done = Apply(aircraft, tries >= MaxAttempts); }
                catch (Exception e)
                {
                    _log.LogError($"Typhoon model swap failed on {aircraft.name}: {e}");
                    done = true;
                }
                if (done)
                {
                    _attempts.Remove(id);
                    _pending.Remove(aircraft);
                    var v = aircraft.GetComponent<TyphoonVisual>() ?? aircraft.gameObject.AddComponent<TyphoonVisual>();
                    v.Built = true;
                }
            }
        }

        bool LoadModel()
        {
            string path = Path.Combine(_pluginDir, _modelFile.Value);
            if (!File.Exists(path))
            {
                _log.LogError($"Typhoon model not found at {path}; model swap disabled.");
                _modelFailed = true;
                return false;
            }
            return SetModel(ObjReader.Read(path));
        }

        bool _preloading;
        float _preloadStart;
        internal System.Collections.IEnumerator Preload()
        {
            if (!_enabled.Value) yield break;
            _preloading = true;
            float t0 = Time.realtimeSinceStartup;
            _preloadStart = t0;
            var clock = System.Diagnostics.Stopwatch.StartNew();
            yield return null;
            string path = Path.Combine(_pluginDir, _modelFile.Value);
            if (_model == null && File.Exists(path))
            {
                List<ObjGroup> parsed = null; Exception err = null;
                var th = new System.Threading.Thread(() => { try { parsed = ObjReader.Read(path); } catch (Exception e) { err = e; } }) { IsBackground = true };
                th.Start();
                while (th.IsAlive) yield return null;
                if (parsed != null) { if (_model == null) SetModel(parsed); }
                else _log.LogWarning("Typhoon model preload failed (it loads at the first spawn instead): " + err);
            }
            float tModel = (float)clock.Elapsed.TotalSeconds;
            while (Shader.Find("Universal Render Pipeline/Lit") == null) yield return new WaitForSecondsRealtime(0.5f);
            var files = TexturedMaterials.TextureList(Path.Combine(_pluginDir, "typhoon_materials.txt"));
            try { foreach (var g in Directory.GetFiles(_pluginDir, "*_glow.png")) files.Add(new KeyValuePair<string, bool>(Path.GetFileName(g), false)); }
            catch (Exception e) { _log.LogWarning("Glow textures not preloaded: " + e.Message); }
            foreach (var f in files)
            {
                if (!File.Exists(Path.Combine(_pluginDir, f.Key)) && !File.Exists(Path.Combine(_pluginDir, Path.GetFileNameWithoutExtension(f.Key) + ".tex"))) continue;
                try { TexturedMaterials.LoadTex(_pluginDir, f.Key, f.Value); }
                catch (Exception e) { _log.LogWarning($"Preload of {f.Key} failed: {e.Message}"); }
                yield return null;
            }
            try { if (_fileMats == null) _fileMats = TexturedMaterials.Load(Path.Combine(_pluginDir, "typhoon_materials.txt"), _log); }
            catch (Exception e) { _log.LogWarning("Materials not preloaded: " + e.Message); }
            _preloading = false;
            _log.LogInfo($"Typhoon preloaded in {clock.Elapsed.TotalSeconds:0.0} s (model {tModel:0.0} s; textures: " +
                         $"{TexturedMaterials.Packed} ready-compressed, {TexturedMaterials.FromDisk} from the cache, {TexturedMaterials.Decoded} decoded{(TexturedMaterials.Decoded > 0 ? " and cached for next time" : "")}).");
        }

        bool SetModel(List<ObjGroup> parsed)
        {
            _model = parsed;
            var airframe = _model.Where(g => !IsGearOrBay(g.Name)).ToList();
            if (airframe.Count == 0) airframe = _model;
            _modelBounds = airframe[0].Bounds;
            foreach (var g in airframe) _modelBounds.Encapsulate(g.Bounds);
            _log.LogInfo($"Loaded Typhoon model: {_model.Count} parts, {_model.Sum(g => g.Triangles.Count / 3)} triangles, " +
                         $"length {_modelBounds.size.z:0.00} m.");
            return true;
        }

        sealed class OrigPart
        {
            public Renderer Renderer;
            public Bounds RootBounds;
            public string Path;
            public string Status;
            public bool Hidden => Status == "exterior" || Status == "hidden";
        }

        List<OrigPart> Inventory(Aircraft aircraft, out int exteriorCount)
        {
            Transform root = aircraft.transform;
            var exterior = new HashSet<Renderer>((ExteriorField?.GetValue(aircraft) as Renderer[]) ?? new Renderer[0]);
            var cockpit = new HashSet<Renderer>((CockpitField?.GetValue(aircraft) as Renderer[]) ?? new Renderer[0]);
            var keep = new Regex(_keep.Value, RegexOptions.IgnoreCase);
            var pylons = new HashSet<Renderer>();
            var plugs = new HashSet<Renderer>();
            if (aircraft.weaponManager != null && aircraft.weaponManager.hardpointSets != null)
                foreach (var set in aircraft.weaponManager.hardpointSets)
                    if (set != null && set.hardpoints != null)
                        foreach (var hp in set.hardpoints)
                        {
                            if (hp == null) continue;
                            if (hp.Pylon != null) pylons.Add(hp.Pylon);
                            if (hp.Plug != null) plugs.Add(hp.Plug);
                            var opts = PylonOptionsField?.GetValue(hp) as Array;
                            if (opts != null)
                                foreach (var o in opts)
                                {
                                    var rr = o == null ? null : PylonRendererField?.GetValue(o) as Renderer;
                                    if (rr != null) pylons.Add(rr);
                                }
                        }
            Matrix4x4 worldToRoot = root.worldToLocalMatrix;

            var all = new List<Renderer>();
            var seen = new HashSet<Renderer>();
            Action<IEnumerable<Renderer>> AddAll = rs => { if (rs != null) foreach (var x in rs) if (x != null && seen.Add(x)) all.Add(x); };
            AddAll(aircraft.GetComponentsInChildren<Renderer>(true));
            if (aircraft.partLookup != null)
                foreach (var up in aircraft.partLookup)
                    if (up != null) AddAll(up.GetComponentsInChildren<Renderer>(true));
            AddAll(exterior);
            AddAll(cockpit);

            var parts = new List<OrigPart>();
            foreach (var r in all)
            {
                Mesh mesh = null;
                if (r is SkinnedMeshRenderer smr) mesh = smr.sharedMesh;
                else if (r is MeshRenderer) { var mf = r.GetComponent<MeshFilter>(); if (mf != null) mesh = mf.sharedMesh; }
                if (mesh == null) continue;

                if (r.GetComponentInParent<Camera>() != null) continue;
                if (Regex.IsMatch(r.name, "^(sun|moon)$|flare|glare", RegexOptions.IgnoreCase)) continue;
                string path = PathOf(r.transform, root);
                string status;
                if (exterior.Contains(r)) status = "exterior";
                else if (cockpit.Contains(r)) status = "cockpit";
                else if (pylons.Contains(r) || IsWeapon(r.transform, root)) status = "weapon";
                else if (plugs.Contains(r)) status = "hidden";
                else if (!_hideUnlisted.Value || keep.IsMatch(path)) status = "kept";
                else status = "hidden";

                parts.Add(new OrigPart
                {
                    Renderer = r,
                    RootBounds = TransformBounds(mesh.bounds, worldToRoot * r.transform.localToWorldMatrix),
                    Path = path,
                    Status = status,
                });
            }
            exteriorCount = exterior.Count;
            return parts;
        }

        public void EarlyHide(Aircraft aircraft)
        {
            if (!_enabled.Value || _modelFailed || aircraft == null) return;
            var def = aircraft.definition as AircraftDefinition;
            if (def == null || !_definitions.Contains(def)) return;
            int n;
            var parts = Inventory(aircraft, out n);
            foreach (var p in parts)
                if (p.Hidden) p.Renderer.forceRenderingOff = true;
            if (aircraft.GetComponent<TyphoonVisual>() == null) aircraft.gameObject.AddComponent<TyphoonVisual>();
            _pending.Add(aircraft);
        }

        bool Apply(Aircraft aircraft, bool lastTry)
        {
            Transform root = aircraft.transform;
            int exteriorCount;
            var parts = Inventory(aircraft, out exteriorCount);
            var stray = parts.Where(p => p.RootBounds.center.magnitude > SettledRadius).ToList();
            if (stray.Count > 0 && !lastTry) return false;
            if (stray.Count > 0)
            {
                _log.LogWarning($"{aircraft.name}: {stray.Count} parts never settled (e.g. '{stray[0].Path}'); ignoring them.");
                parts = parts.Except(stray).ToList();
            }

            var hidden = parts.Where(p => p.Hidden).ToList();
            if (!_wroteReport) { if (!TyphoonPlugin.Locked) WriteReport(aircraft.name, parts, exteriorCount); _wroteReport = true; }
            if (hidden.Count == 0)
            {
                _log.LogWarning($"{aircraft.name}: no exterior renderers found, leaving the original model.");
                return true;
            }

            var pilotTs = (aircraft.pilots ?? new Pilot[0]).Where(x => x != null).Select(x => x.transform).ToList();
            var fitParts = hidden.Where(p => !pilotTs.Any(pt => p.Renderer.transform.IsChildOf(pt))).ToList();
            if (fitParts.Count == 0) fitParts = hidden;
            var main = fitParts.OrderByDescending(p => Volume(p.RootBounds)).First().RootBounds;
            var outliers = fitParts.Where(p => p.RootBounds.min.y < main.min.y - 0.6f || p.RootBounds.max.y > main.max.y + 2.5f
                                               || p.RootBounds.center.magnitude > 15f).ToList();
            foreach (var o in outliers) _log.LogInfo($"  Not used for fitting: '{o.Path}' (y {o.RootBounds.min.y:0.00}..{o.RootBounds.max.y:0.00}, centre {o.RootBounds.center})");
            if (outliers.Count > 0 && outliers.Count < fitParts.Count) fitParts = fitParts.Except(outliers).ToList();
            Bounds orig = fitParts[0].RootBounds;
            foreach (var p in fitParts) orig.Encapsulate(p.RootBounds);
            float scale = orig.size.z / Mathf.Max(0.01f, _modelBounds.size.z) * _scale.Value;
            _log.LogInfo($"Fit: {fitParts.Count} meshes, bounds y {orig.min.y:0.00}..{orig.max.y:0.00}, length {orig.size.z:0.00} m.");
            Vector3 offset = orig.center - _modelBounds.center * scale;

            Transform pilot = FindPilot(aircraft);
            ObjGroup canopy = _model.FirstOrDefault(g => g.Name.Equals("canopy", StringComparison.OrdinalIgnoreCase))
                           ?? _model.FirstOrDefault(g => g.Name.StartsWith("canopy", StringComparison.OrdinalIgnoreCase));
            if (_alignCockpit.Value && pilot != null && canopy != null)
            {
                Vector3 seat = root.InverseTransformPoint(pilot.position);
                float shift = seat.z - (offset.z + canopy.Bounds.center.z * scale);
                if (Mathf.Abs(shift) < orig.size.z * 0.25f) offset.z += shift;
                _log.LogInfo($"Canopy aligned to '{pilot.name}' (shift {shift:0.00} m).");
            }
            if (!_gearDefLoaded)
            {
                _gearDefLoaded = true;
                if (_model.Any(g => g.Name.StartsWith("gear_", StringComparison.OrdinalIgnoreCase)))
                    _gearDef = GearDef.Load(Path.Combine(_pluginDir, "typhoon_gear.txt"), _log);
            }
            var wheelBottoms = BaseWheelBottoms(aircraft);
            bool typhoonGear = _typhoonGear.Value && _gearDef != null && !float.IsNaN(_gearDef.GroundMain) && wheelBottoms.ContainsKey("main");
            if (typhoonGear)
            {
                float y = wheelBottoms["main"] - _gearDef.GroundMain * scale;
                _log.LogInfo($"Model height set from the wheels: main wheels at {wheelBottoms["main"]:0.00} m ({y - offset.y:+0.00;-0.00} m).");
                offset.y = y;
            }
            else if (_raiseForGear.Value)
            {
                float raise = GearRaise(parts, root, offset, scale, aircraft.gearDeployed);
                if (!float.IsNaN(raise)) { offset.y += raise; _log.LogInfo($"Model raised {raise:0.00} m to cover the main-gear mounts."); }
            }
            offset += ParseVector(_offset.Value);
            Matrix4x4 modelToRoot = Matrix4x4.TRS(offset, Quaternion.identity, Vector3.one * scale);

            var template = hidden
                .Where(p => p.Status == "hidden" && p.Renderer.sharedMaterial != null && p.Renderer.sharedMaterial.renderQueue < 2450)
                .OrderByDescending(p => Volume(p.RootBounds))
                .Select(p => p.Renderer.sharedMaterial).FirstOrDefault()
                ?? hidden[0].Renderer.sharedMaterial;
            Color body;
            if (!ColorUtility.TryParseHtmlString(_bodyColor.Value, out body)) body = new Color(0.48f, 0.51f, 0.53f);
            if (_mats == null)
            {
                LogShader(template);
                _mats = new Dictionary<string, Material>
                {
                    ["body"] = MakeMaterial(template, body, 0.35f, 0f),
                    ["glass"] = MakeMaterial(template, new Color(0.05f, 0.07f, 0.10f), 0.9f, 0f),
                    ["dark"] = MakeMaterial(template, new Color(0.03f, 0.03f, 0.035f), 0.1f, 0f),
                    ["metal"] = MakeMaterial(template, new Color(0.28f, 0.27f, 0.26f), 0.6f, 0.8f),
                };
            }
            if (_fileMats == null) _fileMats = TexturedMaterials.Load(Path.Combine(_pluginDir, "typhoon_materials.txt"), _log);
            foreach (var kv in _fileMats) _mats[kv.Key] = kv.Value;

            var mats = new Dictionary<string, Material>(_mats);
            mats["body"] = new Material(_mats["body"]) { name = "Typhoon_body_" + aircraft.GetInstanceID() };

            foreach (var p in hidden) p.Renderer.forceRenderingOff = true;

            var drivers = new Dictionary<string, Transform>();
            var restRot = new Dictionary<string, Quaternion>();
            CollectControlSurfaces(aircraft, drivers, restRot);
            var animated = new HashSet<Transform>(drivers.Values);
            var staticHidden = hidden.Where(p => !IsUnder(p.Renderer.transform, animated)).ToList();
            if (_surfaceDefs == null) _surfaceDefs = SurfaceDef.Load(Path.Combine(_pluginDir, "typhoon_surfaces.txt"), _log);
            var visual = aircraft.GetComponent<TyphoonVisual>() ?? aircraft.gameObject.AddComponent<TyphoonVisual>();
            visual.Aircraft = aircraft;
            visual.Surfaces.Clear();
            if (AfterburnersField != null)
                foreach (var jn in aircraft.GetComponentsInChildren<JetNozzle>(true)
                                           .Concat((aircraft.partLookup ?? new List<UnitPart>()).Where(u => u != null)
                                                   .SelectMany(u => u.GetComponentsInChildren<JetNozzle>(true))))
                {
                    var abs = AfterburnersField.GetValue(jn) as Array;
                    if (abs != null && abs.Length > 0 && abs.GetValue(0) != null) { visual.AfterburnerRef = abs.GetValue(0); break; }
                }

            var added = new List<Renderer>();
            var builtParts = new Dictionary<string, GameObject>(StringComparer.OrdinalIgnoreCase);
            var cockpitParts = new List<Renderer>();
            var cockpitRegex = new Regex(_cockpitParts.Value, RegexOptions.IgnoreCase);
            foreach (var g in _model)
            {
                Bounds gb = TransformBounds(g.Bounds, modelToRoot);
                Transform parent = _attachToParts.Value ? PickParent(gb, staticHidden, root) : root;
                Matrix4x4 toParent = parent.worldToLocalMatrix * root.localToWorldMatrix * modelToRoot;

                var go = new GameObject("Typhoon_" + g.Name);
                builtParts[g.Name] = go;
                go.layer = parent.gameObject.layer;
                Matrix4x4 meshMatrix = toParent;
                TyphoonVisual.Surface newSurf = null;
                SurfaceDef sd;
                if (_surfaceDefs.TryGetValue(g.Name, out sd))
                {
                    Vector3 pA = toParent.MultiplyPoint3x4(sd.A);
                    var pivot = new GameObject("Typhoon_" + g.Name + "_hinge");
                    pivot.layer = go.layer;
                    pivot.transform.SetParent(parent, false);
                    pivot.transform.localPosition = pA;
                    pivot.transform.localRotation = Quaternion.identity;
                    pivot.transform.localScale = Vector3.one;
                    go.transform.SetParent(pivot.transform, false);
                    meshMatrix = Matrix4x4.Translate(-pA) * toParent;
                    var surf = new TyphoonVisual.Surface
                    {
                        Pivot = pivot.transform,
                        AxisLocal = toParent.MultiplyVector(sd.B - sd.A).normalized,
                        AxisRoot = modelToRoot.MultiplyVector(sd.B - sd.A).normalized,
                        FullRotation = sd.Drivers.Length == 1 && sd.Drivers[0] == "vectoring",
                    };
                    newSurf = surf;
                    foreach (var dn in sd.Drivers)
                    {
                        Transform dt; Quaternion rest;
                        if (!drivers.TryGetValue(dn, out dt)) continue;
                        if (!restRot.TryGetValue(dn, out rest)) rest = dt.localRotation;
                        surf.Drivers.Add(dt); surf.Rest.Add(rest);
                    }
                    if (sd.Drivers.Length == 1 && sd.Drivers[0].StartsWith("sw_"))
                    {
                        surf.Input = sd.Drivers[0];
                        surf.AngA = -sd.Ang; surf.AngB = sd.Ang;
                        surf.Openness = 0.5f;
                        visual.Surfaces.Add(surf);
                    }
                    else if (sd.Drivers.Length == 1 && (sd.Drivers[0] == "pedal_l" || sd.Drivers[0] == "pedal_r" || sd.Drivers[0] == "gearlever"))
                    {
                        surf.Input = sd.Drivers[0];
                        bool lever = surf.Input == "gearlever";
                        surf.AngA = lever ? -24f : -7f; surf.AngB = lever ? 24f : 7f;
                        surf.Openness = lever ? 1f : 0.5f;
                        visual.Surfaces.Add(surf);
                    }
                    else if (sd.Drivers.Length == 1 && sd.Drivers[0] == "throttle")
                    {
                        surf.IsThrottle = true;
                        surf.AngA = sd.HasAng ? -sd.Ang : -8f; surf.AngB = sd.HasAng ? sd.Ang : 12f;
                        visual.Surfaces.Add(surf);
                    }
                    else if (sd.Drivers.Length == 1 && sd.Drivers[0] == "stick")
                    {
                        surf.IsStick = true;
                        var js = TyphoonCockpit.FindJoystick(aircraft);
                        if (js != null) { surf.Drivers.Add(js); surf.Rest.Add(Quaternion.identity); }
                        visual.Surfaces.Add(surf);
                        _log.LogInfo(js != null ? "Cockpit stick linked to the game's stick." : "Cockpit stick follows the pilot's inputs.");
                    }
                    else if (sd.Drivers.Length == 1 && sd.Drivers[0] == "airbrake")
                    {
                        var abc = aircraft.GetComponentsInChildren<Airbrake>(true).FirstOrDefault();
                        if (abc == null && aircraft.partLookup != null)
                            abc = aircraft.partLookup.Where(u => u != null).SelectMany(u => u.GetComponentsInChildren<Airbrake>(true)).FirstOrDefault();
                        if (abc != null) { surf.AirbrakeRef = abc; visual.Surfaces.Add(surf); _log.LogInfo("Airbrake linked."); }
                        else _log.LogWarning("No Airbrake component found; the airbrake stays shut.");
                    }
                    else if (surf.Drivers.Count > 0) visual.Surfaces.Add(surf);
                    else _log.LogWarning($"No driver found for '{g.Name}' ({string.Join("+", sd.Drivers)}); it stays fixed.");
                }
                else go.transform.SetParent(parent, false);
                go.transform.localPosition = Vector3.zero;
                go.transform.localRotation = Quaternion.identity;
                go.transform.localScale = Vector3.one;

                bool iris = newSurf != null && newSurf.FullRotation && !newSurf.IsStick && _nozzleIris.Value;
                var builtMesh = iris ? BuildMesh(g, meshMatrix) : SharedMesh(g, meshMatrix);
                if (iris && g.Name.Equals("airbrake", StringComparison.OrdinalIgnoreCase)) MakeDoubleSided(builtMesh);
                go.AddComponent<MeshFilter>().sharedMesh = builtMesh;
                if (newSurf != null && newSurf.FullRotation && !newSurf.IsStick && _nozzleIris.Value) newSurf.SetupIris(builtMesh, _irisOpen.Value, _irisClosed.Value);
                var mr = go.AddComponent<MeshRenderer>();
                Material m;
                mr.sharedMaterial = mats.TryGetValue(g.Material, out m) ? m : mats["body"];
                added.Add(mr);
                if (cockpitRegex.IsMatch(g.Name)) cockpitParts.Add(mr);
            }

            GameObject lampGo;
            if (builtParts.TryGetValue("cockpit_gearlamps", out lampGo) && lampGo != null) visual.GearLamps = lampGo.GetComponent<Renderer>();
            foreach (var nlp in new[] { new KeyValuePair<string, Color>("navlamp_L", new Color(2.4f, 0.16f, 0.08f, 1f)),
                                        new KeyValuePair<string, Color>("navlamp_R", new Color(0.14f, 2.3f, 0.55f, 1f)),
                                        new KeyValuePair<string, Color>("formlight", new Color(0.62f, 0.95f, 0.36f, 1f)) })
            {
                GameObject lg;
                if (builtParts.TryGetValue(nlp.Key, out lg) && lg != null && lg.GetComponent<Renderer>() != null)
                    visual.NavLamps.Add(new KeyValuePair<Renderer, Color>(lg.GetComponent<Renderer>(), nlp.Value));
            }

            visual.Pilot = pilot != null ? pilot : root;
            visual.TyphoonCockpit = cockpitParts;
            visual.OriginalCockpit = parts.Where(p => p.Status == "cockpit").Select(p => p.Renderer).ToList();
            visual.Radius = 2.0f;

            if (!_cockpitDefLoaded) { _cockpitDefLoaded = true; _cockpitDef = CockpitDef.Load(Path.Combine(_pluginDir, "typhoon_cockpit.txt"), _log); }
            visual.InteriorMode = false;
            if (_interior.Value && _cockpitDef != null)
                try { SetupInterior(aircraft, root, modelToRoot, visual, added, pilot); }
                catch (Exception e) { _log.LogWarning("Typhoon cockpit setup failed, using the original cockpit: " + e); visual.InteriorMode = false; }

            visual.Aircraft = aircraft;
            TyphoonGearRig gearRig = null;
            if (typhoonGear)
                try
                {
                    var closed = added.FirstOrDefault(r => r.name.Equals("Typhoon_geardoors", StringComparison.OrdinalIgnoreCase));
                    gearRig = TyphoonGearRig.Build(_gearDef, aircraft, root, offset, scale, builtParts, closed, wheelBottoms, _log);
                    HideBaseGear(parts, root, offset, scale, wheelBottoms);
                }
                catch (Exception e) { _log.LogWarning("Typhoon gear setup failed, using the base jet's gear: " + e); gearRig = null; }
            visual.GearRig = gearRig;
            visual.Bay = gearRig != null ? new RotaryBay() : null;
            if (gearRig == null)
            {
            foreach (var r in added.Where(r => r.name.StartsWith("Typhoon_gear_", StringComparison.OrdinalIgnoreCase))) r.forceRenderingOff = true;
            visual.TyphoonGearDoors = added.Where(r => r.name.IndexOf("geardoor", StringComparison.OrdinalIgnoreCase) >= 0).ToList();
            visual.OriginalGearDoors = parts.Where(p => p.Status == "kept" && p.Path.IndexOf("geardoor", StringComparison.OrdinalIgnoreCase) >= 0)
                                            .Select(p => p.Renderer).ToList();
            foreach (var p in parts.Where(p => p.Status == "kept"
                                              && Regex.IsMatch(p.Path, "gear|wheel|chock|strut", RegexOptions.IgnoreCase)))
            {
                bool door = p.Path.IndexOf("geardoor", StringComparison.OrdinalIgnoreCase) >= 0;
                Vector3 q = (p.RootBounds.center - offset) / scale;
                float sy = LowestSurface(q.x, q.z);
                bool wingDoorEarly = door;
                float topY = HighestSurface(q.x, q.z);
                string leaf = p.Path.Substring(p.Path.LastIndexOf('/') + 1).ToLowerInvariant();
                bool brace = leaf.Contains("arm") || leaf.Contains("door") || leaf.Contains("hinge") || leaf.Contains("mount");
                float topMin = TopOver(p.RootBounds, offset, scale);
                bool throughTop = brace && !float.IsNaN(topMin) && p.RootBounds.max.y > topMin * scale + offset.y + 0.01f;
                if (wingDoorEarly || throughTop)
                {
                    visual.OriginalGear.Add(p.Renderer);
                    visual.GearCeiling.Add(float.NegativeInfinity);
                    continue;
                }
                if (float.IsNaN(sy)) continue;
                visual.OriginalGear.Add(p.Renderer);
                float ceiling = sy * scale + offset.y - 0.05f;
                bool wingDoor = door && p.Path.IndexOf("wing", StringComparison.OrdinalIgnoreCase) >= 0;
                visual.GearCeiling.Add(wingDoor ? float.NegativeInfinity : ceiling);
            }

            try { ExtendNoseGear(aircraft, root, offset, scale, parts, visual); }
            catch (Exception e) { _log.LogWarning("Nose gear extension failed: " + e.Message); }
            }

            visual.Body = mats["body"];
            visual.FallbackColor = body;
            visual.LiveryMode = _liveryMode.Value;
            visual.LiverySources = hidden.Select(p => p.Renderer).ToList();

            if (_twinFlames.Value)
                try { SetupFlames(aircraft, root, parts, modelToRoot, visual); }
                catch (Exception e) { _log.LogWarning("Twin afterburner setup failed: " + e.Message); }

            visual.ModelOffset = offset; visual.ModelScale = scale;
            if (_moveHardpoints.Value)
                try { BindHardpoints(aircraft, root, offset, scale, visual); }
                catch (Exception e) { _log.LogWarning("Hardpoint placement failed: " + e); }

            try { MoveNavLights(aircraft, root, offset, scale); FixStrayLights(aircraft, root, offset, scale, false); }
            catch (Exception e) { _log.LogWarning("Nav light alignment failed: " + e.Message); }
            if (visual.Surfaces.Count > 0) _log.LogInfo($"{visual.Surfaces.Count} moving control surfaces linked.");

            _log.LogInfo($"Typhoon model applied to {aircraft.name} (scale {scale:0.###}, {hidden.Count} original meshes hidden).");
            return true;
        }

        static readonly Regex InteriorParts = new Regex("^Typhoon_(canopy_interior|cockpit_)", RegexOptions.IgnoreCase);

        void SetupInterior(Aircraft aircraft, Transform root, Matrix4x4 modelToRoot, TyphoonVisual visual, List<Renderer> added, Transform pilot)
        {
            if (_gameStick.Value)
                try { SetupGameStick(aircraft, root, modelToRoot, visual, added); }
                catch (Exception e) { _log.LogWarning("Game stick: could not be set up, keeping the modelled grip: " + e.Message); }
            var interior = added.Where(r => r != null && InteriorParts.IsMatch(r.name)).ToList();
            Renderer shell = null;
            foreach (var want in new[] { "canopy_interior", "cockpit_shellrest", "cockpit_shelltub", "cockpit_shell" })
            {
                shell = interior.FirstOrDefault(r => r.name.IndexOf(want, StringComparison.OrdinalIgnoreCase) >= 0);
                if (shell != null) break;
            }
            if (shell == null) shell = interior.FirstOrDefault(r => r.transform.parent != null && !r.transform.parent.name.StartsWith("Typhoon_"));
            if (shell == null) { _log.LogWarning("Typhoon cockpit: the model has no cockpit parts (canopy_interior / cockpit_*)."); return; }
            int layer = _cockpitLayer.Value;
            if (layer < 0)
            {
                var orig = visual.OriginalCockpit.Where(r => r != null).GroupBy(r => r.gameObject.layer).OrderByDescending(g => g.Count()).FirstOrDefault();
                layer = orig != null ? orig.Key : shell.gameObject.layer;
            }
            int exteriorLayer = shell.gameObject.layer;
            var layerObjects = new List<GameObject>();
            foreach (var r in interior)
            {
                for (var t = r.transform; t != null && t.name.StartsWith("Typhoon_"); t = t.parent) layerObjects.Add(t.gameObject);
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                visual.Interior.Add(r);
            }
            SetupPilot(aircraft, root, modelToRoot, visual);
            visual.Cockpit = TyphoonCockpit.Setup(aircraft, visual, _cockpitDef, modelToRoot, shell.transform.parent, exteriorLayer, pilot, _log);
            layerObjects.AddRange(visual.Interior.Where(r => r != null && r.name.StartsWith("Typhoon_mfd")).Select(r => r.gameObject));
            visual.Cockpit.LayerObjects = layerObjects.Distinct().ToList();
            visual.Cockpit.CockpitLayer = layer;
            visual.Cockpit.ExteriorLayer = exteriorLayer;
            visual.InteriorMode = true;
            visual.TyphoonCockpit = new List<Renderer>();
            CockpitCamera.Hook();
            _log.LogInfo($"Typhoon cockpit interior: layer {layer} ({LayerMask.LayerToName(layer)}) in cockpit view, {exteriorLayer} ({LayerMask.LayerToName(exteriorLayer)}) outside; {interior.Count} parts.");
        }

        void SetupGameStick(Aircraft aircraft, Transform root, Matrix4x4 modelToRoot, TyphoonVisual visual, List<Renderer> added)
        {
            var gripR = added.FirstOrDefault(r => r != null && r.name.Equals("Typhoon_cockpit_stickgrip", StringComparison.OrdinalIgnoreCase));
            if (gripR == null) { _log.LogInfo("Game stick: the model has no cockpit_stickgrip, nothing to replace."); return; }
            Transform pivot = gripR.transform.parent;
            if (pivot == null || !pivot.name.EndsWith("_hinge")) { _log.LogWarning("Game stick: cockpit_stickgrip has no hinge in typhoon_surfaces.txt; keeping the modelled grip."); return; }
            Transform js = TyphoonCockpit.FindJoystick(aircraft);
            if (js == null) { _log.LogWarning("Game stick: the base jet's stick was not found; keeping the modelled grip."); return; }

            var pilotTs = aircraft.pilots != null ? aircraft.pilots.Where(p => p != null).Select(p => p.transform).ToList() : new List<Transform>();
            var all = js.GetComponentsInChildren<Renderer>(true)
                        .Where(r => r != null && !(r is ParticleSystemRenderer) && !pilotTs.Any(pt => r.transform.IsChildOf(pt))
                                    && !r.name.StartsWith("Typhoon_") && (r is MeshRenderer || r is SkinnedMeshRenderer)).ToList();
            var src = all.Where(r => r.enabled && r.gameObject.activeInHierarchy).ToList();
            if (src.Count == 0) src = all;
            if (src.Count == 0) { _log.LogWarning($"Game stick: '{js.name}' has no meshes; keeping the modelled grip."); return; }

            Quaternion restRot = js.parent != null ? js.parent.rotation : js.rotation;
            Matrix4x4 frame = Matrix4x4.TRS(js.position, js.rotation, Vector3.one).inverse;
            float s = Mathf.Clamp(_gameStickScale.Value, 0.2f, 3f);
            float k = modelToRoot.MultiplyVector(Vector3.up).magnitude;
            Vector3 up = root.up, right = root.right, fwd = root.forward;

            var holder = new GameObject("Typhoon_cockpit_gamestick");
            holder.layer = gripR.gameObject.layer;
            holder.transform.SetParent(pivot, false);
            var pls = pivot.lossyScale;
            holder.transform.localScale = new Vector3(s / Mathf.Max(1e-4f, Mathf.Abs(pls.x)), s / Mathf.Max(1e-4f, Mathf.Abs(pls.y)), s / Mathf.Max(1e-4f, Mathf.Abs(pls.z)));
            holder.transform.rotation = Quaternion.AngleAxis(_gameStickYaw.Value, up) * restRot;
            holder.transform.position = pivot.position;

            int n = 0;
            var names = new List<string>();
            var clones = new List<KeyValuePair<Transform, Mesh>>();
            foreach (var r in src)
            {
                Mesh mesh = null;
                Matrix4x4 rel;
                var smr = r as SkinnedMeshRenderer;
                if (smr != null)
                {
                    if (smr.sharedMesh == null) continue;
                    mesh = new Mesh { name = smr.sharedMesh.name + "_baked" };
                    smr.BakeMesh(mesh);
                    rel = frame * Matrix4x4.TRS(r.transform.position, r.transform.rotation, Vector3.one);
                }
                else
                {
                    var mf = r.GetComponent<MeshFilter>();
                    if (mf == null || mf.sharedMesh == null) continue;
                    mesh = mf.sharedMesh;
                    rel = frame * r.transform.localToWorldMatrix;
                }
                var go = new GameObject("Typhoon_cockpit_gamestick_" + n);
                go.layer = holder.layer;
                go.transform.SetParent(holder.transform, false);
                go.transform.localPosition = rel.GetColumn(3);
                go.transform.localRotation = rel.rotation;
                go.transform.localScale = rel.lossyScale;
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var mr = go.AddComponent<MeshRenderer>();
                mr.sharedMaterials = r.sharedMaterials;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                mr.receiveShadows = r.receiveShadows;
                added.Add(mr);
                names.Add(r.name);
                clones.Add(new KeyValuePair<Transform, Mesh>(go.transform, mesh));
                n++;
            }

            var local = new List<KeyValuePair<Transform, Vector3[]>>();
            bool exact = n > 0;
            foreach (var c in clones)
            {
                var v = MeshPositions(c.Value);
                if (v == null) { exact = false; break; }
                if (v.Length > 6000) { int st = v.Length / 6000 + 1; v = v.Where((q, ix) => ix % st == 0).ToArray(); }
                local.Add(new KeyValuePair<Transform, Vector3[]>(c.Key, v));
            }
            if (!exact)
            {
                local.Clear();
                foreach (var c in clones)
                {
                    var b = c.Value.bounds;
                    var cs = new Vector3[8];
                    for (int q = 0; q < 8; q++)
                        cs[q] = b.center + Vector3.Scale(b.extents, new Vector3((q & 1) == 0 ? -1f : 1f, (q & 2) == 0 ? -1f : 1f, (q & 4) == 0 ? -1f : 1f));
                    local.Add(new KeyValuePair<Transform, Vector3[]>(c.Key, cs));
                }
            }
            Func<List<Vector3>> world = () =>
            {
                var w = new List<Vector3>();
                foreach (var kv in local) foreach (var q in kv.Value) w.Add(kv.Key.TransformPoint(q) - pivot.position);
                return w;
            };
            var pts = world();
            float hi = float.NegativeInfinity, lo = float.PositiveInfinity;
            foreach (var w in pts) { float h = Vector3.Dot(w, up); hi = Mathf.Max(hi, h); lo = Mathf.Min(lo, h); }
            if (n == 0 || pts.Count == 0 || float.IsInfinity(hi) || float.IsNaN(hi) || hi - lo > 1.5f)
            {
                foreach (var mr in holder.GetComponentsInChildren<Renderer>(true)) added.Remove(mr);
                UnityEngine.Object.Destroy(holder);
                _log.LogWarning($"Game stick: no usable meshes ({n} found, {lo:0.00} to {hi:0.00} m); keeping the modelled grip.");
                return;
            }

            string how = "left as it stands in the base jet";
            float lean = 0f;
            if (_gameStickUpright.Value)
            {
                Vector3 axis = Vector3.zero;
                if (exact) axis = PrincipalAxis(pts);
                else
                {
                    var big = clones.OrderByDescending(c => c.Value.bounds.size.sqrMagnitude).First();
                    var e = big.Value.bounds.extents;
                    var ls = big.Key.lossyScale;
                    float ex = e.x * Mathf.Abs(ls.x), ey = e.y * Mathf.Abs(ls.y), ez = e.z * Mathf.Abs(ls.z);
                    float mx = Mathf.Max(ex, Mathf.Max(ey, ez)), md = ex + ey + ez - mx - Mathf.Min(ex, Mathf.Min(ey, ez));
                    if (mx > 1.4f * md) axis = big.Key.TransformDirection(ex >= mx ? Vector3.right : ey >= mx ? Vector3.up : Vector3.forward).normalized;
                }
                if (axis != Vector3.zero)
                {
                    if (Vector3.Dot(axis, up) < 0f) axis = -axis;
                    lean = Vector3.Angle(axis, up);
                    if (lean > 1.5f && lean < 55f)
                    {
                        holder.transform.rotation = Quaternion.FromToRotation(axis, up) * holder.transform.rotation;
                        how = $"stood upright (its own axis leaned {lean:0} deg: {Vector3.Dot(axis, right):+0.00;-0.00} right, {Vector3.Dot(axis, fwd):+0.00;-0.00} forward; measured from {(exact ? "its points" : "its box")})";
                    }
                    else how = lean <= 1.5f ? "already upright" : $"not straightened (axis {lean:0} deg off upright looks wrong)";
                }
                else how = "could not be measured, left as it stands in the base jet";
            }
            Vector3 tilt = ParseVector(_gameStickTilt.Value);
            if (tilt.x != 0f || tilt.y != 0f)
                holder.transform.rotation = Quaternion.AngleAxis(tilt.x, right) * Quaternion.AngleAxis(-tilt.y, fwd) * holder.transform.rotation;

            pts = world();
            hi = float.NegativeInfinity; lo = float.PositiveInfinity;
            float wide = 0f;
            foreach (var w in pts)
            {
                float h = Vector3.Dot(w, up); hi = Mathf.Max(hi, h); lo = Mathf.Min(lo, h);
                wide = Mathf.Max(wide, Mathf.Max(Mathf.Abs(Vector3.Dot(w, right)), Mathf.Abs(Vector3.Dot(w, fwd))));
            }
            Vector3 centre = Vector3.zero;
            if (exact)
            {
                float cut = lo + 0.2f * (hi - lo);
                Vector3 sum = Vector3.zero; int cnt = 0;
                foreach (var w in pts) if (Vector3.Dot(w, up) <= cut) { sum += w; cnt++; }
                if (cnt > 0)
                {
                    sum /= cnt;
                    centre = -(right * Vector3.Dot(sum, right) + fwd * Vector3.Dot(sum, fwd));
                    if (centre.magnitude > 0.06f) centre = centre.normalized * 0.06f;
                }
            }

            float lift = Mathf.Min(_gameStickTop.Value * k - hi, 0.055f * k - lo);
            Vector3 off = ParseVector(_gameStickOffset.Value);
            holder.transform.position = pivot.position + centre + up * (lift + off.y) + right * off.x + fwd * off.z;

            gripR.gameObject.SetActive(false);
            string seat = "";
            if (_gameStickSeat.Value)
                try { seat = BuildStickSeat(pivot, holder, world(), exact, up, right, fwd, k, gripR, added); }
                catch (Exception e) { _log.LogWarning("Game stick seat: " + e.Message); }
            _log.LogInfo($"Game stick: '{js.name}' shown in the Typhoon cockpit, {n} mesh(es) ({string.Join(", ", names.Take(6))}), {how}; " +
                         $"it now reaches {lo:0.000} to {hi:0.000} m about its pivot, {wide:0.000} m to the side; moved {lift:0.000} m up and " +
                         $"{centre.magnitude:0.000} m sideways to stand on the Typhoon's boot. " +
                         seat + (TyphoonPlugin.Locked ? "" : "Cockpit/GameStickTilt, GameStickTop, GameStickOffset, GameStickScale, GameStickYaw adjust it; GameStick = false brings the modelled grip back."));
        }

        string BuildStickSeat(Transform pivot, GameObject holder, List<Vector3> pts, bool exact, Vector3 up, Vector3 right, Vector3 fwd,
                              float k, Renderer gripR, List<Renderer> added)
        {
            float hi = float.NegativeInfinity, lo = float.PositiveInfinity;
            foreach (var w in pts) { float h = Vector3.Dot(w, up); hi = Mathf.Max(hi, h); lo = Mathf.Min(lo, h); }
            float cut = lo + 0.125f * (hi - lo);
            Vector3 c = Vector3.zero; int cnt = 0;
            foreach (var w in pts) if (Vector3.Dot(w, up) <= cut) { c += w; cnt++; }
            if (cnt == 0) return "";
            c /= cnt; c -= up * Vector3.Dot(c, up);
            float rb = 0.045f * k;
            if (exact)
            {
                var rs = new List<float>();
                foreach (var w in pts)
                    if (Vector3.Dot(w, up) <= cut) { var d = w - c; d -= up * Vector3.Dot(d, up); rs.Add(d.magnitude); }
                rs.Sort();
                rb = rs[Mathf.Clamp(Mathf.RoundToInt(0.94f * (rs.Count - 1)), 0, rs.Count - 1)];
            }
            float rbRaw = rb;
            rb = Mathf.Clamp(rb, 0.028f * k, 0.062f * k);

            var boot = added.FirstOrDefault(r => r != null && r.name.Equals("Typhoon_cockpit_stick", StringComparison.OrdinalIgnoreCase));
            if (boot != null) boot.gameObject.SetActive(false);

            var metal = MakeMaterial(gripR.sharedMaterial, new Color(0.105f, 0.110f, 0.118f, 1f), 0.46f, 0.60f);
            var rubber = MakeMaterial(gripR.sharedMaterial, new Color(0.034f, 0.035f, 0.037f, 1f), 0.27f, 0f);
            metal.name = "Typhoon_stickseat"; rubber.name = "Typhoon_stickboot";
            Quaternion rot = Quaternion.LookRotation(fwd, up);

            const float FloorC = -0.0126f, Slope = 0.60f, FloorHalf = 0.0410f;
            float r0 = Mathf.Min(FloorHalf - 0.0015f, 0.0395f) * k;
            float r1 = Mathf.Min(rb * 0.86f, 0.037f * k);
            float hTop = lo + 0.003f * k;
            if (hTop < 0.012f * k) hTop = 0.012f * k;

            Action<GameObject, Transform> place = (go, par) =>
            {
                go.layer = holder.layer;
                go.transform.SetParent(par, false);
                go.transform.position = pivot.position + c;
                go.transform.rotation = rot;
                var ls = par.lossyScale;
                go.transform.localScale = new Vector3(1f / Mathf.Max(1e-4f, Mathf.Abs(ls.x)), 1f / Mathf.Max(1e-4f, Mathf.Abs(ls.y)), 1f / Mathf.Max(1e-4f, Mathf.Abs(ls.z)));
            };

            const int Seg = 44, Rings = 41, Ribs = 5;
            var vs = new List<Vector3>(); var bw = new List<BoneWeight>(); var tris = new List<int>();
            for (int i = 0; i < Rings; i++)
            {
                float t = i / (float)(Rings - 1);
                float rib = 0.5f * (1f - Mathf.Cos(2f * Mathf.PI * Ribs * t));
                float r = Mathf.Lerp(r0, r1, t) + 0.0034f * k * rib * Mathf.Sin(Mathf.PI * Mathf.Clamp01(t * 1.15f));
                float wgt = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.12f, 1f, t));
                for (int j = 0; j <= Seg; j++)
                {
                    float a = Mathf.PI * 0.5f + j * 2f * Mathf.PI / Seg;
                    float cs = Mathf.Cos(a), sn = Mathf.Sin(a);
                    float hb = FloorC * k + Slope * (r0 * sn) + 0.0006f * k;
                    vs.Add(new Vector3(r * cs, Mathf.Lerp(hb, hTop, t), r * sn));
                    bw.Add(new BoneWeight { boneIndex0 = 0, weight0 = 1f - wgt, boneIndex1 = 1, weight1 = wgt });
                }
            }
            for (int i = 0; i + 1 < Rings; i++)
                for (int j = 0; j < Seg; j++)
                {
                    int p0 = i * (Seg + 1) + j, p1 = p0 + 1, p2 = p0 + Seg + 1, p3 = p2 + 1;
                    tris.Add(p0); tris.Add(p2); tris.Add(p1); tris.Add(p1); tris.Add(p2); tris.Add(p3);
                }
            var mesh = new Mesh { name = "Typhoon_cockpit_stickboot" };
            mesh.SetVertices(vs); mesh.SetTriangles(tris, 0); mesh.RecalculateNormals();
            { var nn = mesh.normals; if (Vector3.Dot(nn[Seg / 4], new Vector3(vs[Seg / 4].x, 0f, vs[Seg / 4].z)) < 0f) { for (int q = 0; q + 2 < tris.Count; q += 3) { int tmp = tris[q + 1]; tris[q + 1] = tris[q + 2]; tris[q + 2] = tmp; } mesh.SetTriangles(tris, 0); mesh.RecalculateNormals(); } }
            {
                var nn = mesh.normals;
                for (int i = 0; i < Rings; i++) { int a0 = i * (Seg + 1), a1 = a0 + Seg; Vector3 m = (nn[a0] + nn[a1]).normalized; nn[a0] = m; nn[a1] = m; }
                mesh.normals = nn;
            }
            mesh.RecalculateBounds();
            var bgo = new GameObject("Typhoon_cockpit_stickboot");
            Transform still = pivot.parent != null ? pivot.parent : pivot;
            place(bgo, still);
            string how;
            if (pivot.parent != null)
            {
                mesh.boneWeights = bw.ToArray();
                mesh.bindposes = new[] { still.worldToLocalMatrix * bgo.transform.localToWorldMatrix, pivot.worldToLocalMatrix * bgo.transform.localToWorldMatrix };
                var smr = bgo.AddComponent<SkinnedMeshRenderer>();
                smr.sharedMesh = mesh;
                smr.bones = new[] { still, pivot };
                smr.rootBone = still;
                smr.localBounds = new Bounds(new Vector3(0f, 0.01f * k, 0f), new Vector3(0.20f, 0.20f, 0.20f) * k);
                smr.updateWhenOffscreen = false;
                smr.sharedMaterial = rubber;
                smr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                added.Add(smr);
                how = "its foot fixed in the well, its top moving with the stick";
            }
            else
            {
                bgo.AddComponent<MeshFilter>().sharedMesh = mesh;
                var mr0 = bgo.AddComponent<MeshRenderer>();
                mr0.sharedMaterial = rubber;
                mr0.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                added.Add(mr0);
                how = "moving with the stick as one piece (the pivot has no parent)";
            }

            {
                float rr = r1 + 0.0030f * k;
                var prof = new List<Vector2>
                {
                    new Vector2(rr - 0.0012f * k, hTop - 0.0105f * k), new Vector2(rr, hTop - 0.0090f * k), new Vector2(rr, hTop - 0.0010f * k),
                    new Vector2(rr - 0.0012f * k, hTop + 0.0005f * k), new Vector2(rr - 0.0060f * k, hTop + 0.0005f * k),
                };
                var go = new GameObject("Typhoon_cockpit_stickseat");
                place(go, pivot);
                go.AddComponent<MeshFilter>().sharedMesh = Lathe(prof, 44, "Typhoon_cockpit_stickseat");
                var mr = go.AddComponent<MeshRenderer>();
                mr.sharedMaterial = metal;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                added.Add(mr);
            }
            return $"Seat: foot radius {rbRaw:0.000} m{(exact ? "" : " (assumed)")}; rubber boot {r0:0.000} m at the well's floor to {r1:0.000} m at {hTop:0.000} m over the pivot, {how}; the modelled boot is {(boot != null ? "hidden" : "not in the model")}. ";
        }

        static Mesh Lathe(List<Vector2> prof, int seg, string name)
        {
            var vs = new List<Vector3>(); var ns = new List<Vector3>(); var tris = new List<int>();
            for (int i = 0; i + 1 < prof.Count; i++)
            {
                Vector2 a = prof[i], b = prof[i + 1];
                Vector2 d = (b - a); if (d.sqrMagnitude < 1e-12f) continue;
                d.Normalize();
                Vector2 nrm = new Vector2(d.y, -d.x);
                int b0 = vs.Count;
                for (int j = 0; j <= seg; j++)
                {
                    float t = j * 2f * Mathf.PI / seg, cs = Mathf.Cos(t), sn = Mathf.Sin(t);
                    vs.Add(new Vector3(a.x * cs, a.y, a.x * sn)); ns.Add(new Vector3(nrm.x * cs, nrm.y, nrm.x * sn));
                    vs.Add(new Vector3(b.x * cs, b.y, b.x * sn)); ns.Add(new Vector3(nrm.x * cs, nrm.y, nrm.x * sn));
                }
                for (int j = 0; j < seg; j++)
                {
                    int p0 = b0 + 2 * j, p1 = p0 + 1, p2 = p0 + 2, p3 = p0 + 3;
                    Vector3 fn = Vector3.Cross(vs[p1] - vs[p0], vs[p2] - vs[p0]);
                    if (Vector3.Dot(fn, ns[p0] + ns[p2]) >= 0f) { tris.Add(p0); tris.Add(p1); tris.Add(p2); tris.Add(p2); tris.Add(p1); tris.Add(p3); }
                    else { tris.Add(p0); tris.Add(p2); tris.Add(p1); tris.Add(p2); tris.Add(p3); tris.Add(p1); }
                }
            }
            var m = new Mesh { name = name };
            m.SetVertices(vs); m.SetNormals(ns); m.SetTriangles(tris, 0); m.RecalculateBounds();
            return m;
        }

        static Vector3[] MeshPositions(Mesh m)
        {
            if (m == null) return null;
            try
            {
                if (m.isReadable) { var v = m.vertices; if (v != null && v.Length > 2) return v; }
            }
            catch { }
            try
            {
                var P = UnityEngine.Rendering.VertexAttribute.Position;
                if (!m.HasVertexAttribute(P)) return null;
                int stream = m.GetVertexAttributeStream(P);
                var fmt = m.GetVertexAttributeFormat(P);
                int dim = m.GetVertexAttributeDimension(P), off = m.GetVertexAttributeOffset(P);
                bool f32 = fmt == UnityEngine.Rendering.VertexAttributeFormat.Float32, f16 = fmt == UnityEngine.Rendering.VertexAttributeFormat.Float16;
                if (stream < 0 || dim < 3 || !(f32 || f16)) return null;
                byte[] data;
                int stride, count;
                var gb = m.GetVertexBuffer(stream);
                if (gb == null) return null;
                try
                {
                    stride = gb.stride; count = gb.count;
                    if (stride <= 0 || count < 3 || (long)stride * count > 64L * 1024 * 1024) return null;
                    data = new byte[stride * count];
                    gb.GetData(data);
                }
                finally { gb.Dispose(); }
                var res = new Vector3[count];
                var bnd = m.bounds; bnd.Expand(bnd.size.magnitude * 0.05f + 1e-4f);
                int inside = 0;
                for (int i = 0; i < count; i++)
                {
                    int o = i * stride + off;
                    Vector3 q = f32 ? new Vector3(BitConverter.ToSingle(data, o), BitConverter.ToSingle(data, o + 4), BitConverter.ToSingle(data, o + 8))
                                    : new Vector3(Mathf.HalfToFloat(BitConverter.ToUInt16(data, o)), Mathf.HalfToFloat(BitConverter.ToUInt16(data, o + 2)), Mathf.HalfToFloat(BitConverter.ToUInt16(data, o + 4)));
                    if (float.IsNaN(q.x) || float.IsNaN(q.y) || float.IsNaN(q.z)) return null;
                    if (bnd.Contains(q)) inside++;
                    res[i] = q;
                }
                if (inside < count * 0.98f) return null;
                Vector3 mn = res[0], mx = res[0];
                foreach (var q in res) { mn = Vector3.Min(mn, q); mx = Vector3.Max(mx, q); }
                if ((mx - mn).magnitude < 0.25f * m.bounds.size.magnitude) return null;
                return res;
            }
            catch { return null; }
        }

        static Vector3 PrincipalAxis(List<Vector3> pts)
        {
            if (pts == null || pts.Count < 8) return Vector3.zero;
            Vector3 c = Vector3.zero;
            foreach (var q in pts) c += q;
            c /= pts.Count;
            double xx = 0, xy = 0, xz = 0, yy = 0, yz = 0, zz = 0;
            foreach (var q in pts)
            {
                double x = q.x - c.x, y = q.y - c.y, z = q.z - c.z;
                xx += x * x; xy += x * y; xz += x * z; yy += y * y; yz += y * z; zz += z * z;
            }
            double vx = 0.31, vy = 0.82, vz = 0.48;
            for (int it = 0; it < 60; it++)
            {
                double nx = xx * vx + xy * vy + xz * vz, ny = xy * vx + yy * vy + yz * vz, nz = xz * vx + yz * vy + zz * vz;
                double ln = Math.Sqrt(nx * nx + ny * ny + nz * nz);
                if (ln < 1e-20) return Vector3.zero;
                vx = nx / ln; vy = ny / ln; vz = nz / ln;
            }
            double lam = vx * (xx * vx + xy * vy + xz * vz) + vy * (xy * vx + yy * vy + yz * vz) + vz * (xz * vx + yz * vy + zz * vz);
            if (lam < 0.55 * (xx + yy + zz)) return Vector3.zero;
            return new Vector3((float)vx, (float)vy, (float)vz).normalized;
        }

        void SetupPilot(Aircraft aircraft, Transform root, Matrix4x4 modelToRoot, TyphoonVisual visual)
        {
            if (aircraft.pilots == null) return;
            foreach (var p in aircraft.pilots)
            {
                if (p == null) continue;
                var pt = p.transform;
                var rs = pt.GetComponentsInChildren<Renderer>(true).Where(r => !(r is ParticleSystemRenderer)
                         && !Regex.IsMatch(r.name, "^(sun|moon)$|flare|glare", RegexOptions.IgnoreCase) && r.GetComponentInParent<Camera>() == null).ToList();
                if (_hideGameSeat.Value)
                {
                    var seat = rs.Where(r => r.name.IndexOf("seat", StringComparison.OrdinalIgnoreCase) >= 0).ToList();
                    if (seat.Count > 0 && seat.Count < rs.Count)
                    {
                        visual.SeatRenderers.AddRange(seat);
                        foreach (var r in seat) r.forceRenderingOff = true;
                        _log.LogInfo($"Pilot figure: the base jet's seat ({string.Join(", ", seat.Select(r => r.name))}) is hidden while he sits in the Typhoon's seat.");
                    }
                }
                visual.PilotRenderers.AddRange(rs.Where(r => !visual.SeatRenderers.Contains(r)));
                Transform head = pt.GetComponentsInChildren<Transform>(true)
                                   .FirstOrDefault(t => t.name.IndexOf("head", StringComparison.OrdinalIgnoreCase) >= 0
                                                        && t.name.IndexOf("rest", StringComparison.OrdinalIgnoreCase) < 0);
                Vector3 eyeNow;
                if (head != null) eyeNow = root.InverseTransformPoint(head.position) + new Vector3(0f, 0.06f, 0.09f);
                else if (rs.Count > 0)
                {
                    Bounds b = rs[0].bounds; foreach (var r in rs) b.Encapsulate(r.bounds);
                    Vector3 top = root.InverseTransformPoint(b.center); top.y = root.InverseTransformPoint(b.max).y - 0.12f;
                    eyeNow = top + new Vector3(0f, 0f, 0.09f);
                }
                else continue;
                Vector3 eyeT = modelToRoot.MultiplyPoint3x4(_cockpitDef.Eye) + TyphoonCockpit.EyeOffset;
                Vector3 shift = eyeT - eyeNow;
                if (shift.magnitude > 1.2f) { _log.LogWarning($"Pilot figure: shift {shift} looks wrong, not moving it."); continue; }
                visual.PilotShiftRoot = shift;
                foreach (Transform child in pt)
                    if (child.GetComponentsInChildren<Renderer>(true).Any(r => rs.Contains(r))) visual.PilotParts.Add(child);
                _log.LogInfo($"Pilot figure: {rs.Count} meshes ({string.Join(", ", rs.Take(4).Select(r => r.name))}), head '{(head != null ? head.name : "-")}', " +
                             $"moved {shift.x:0.00}, {shift.y:0.00}, {shift.z:0.00} m into the Typhoon seat.");
                break;
            }
            visual.OriginalCockpit = visual.OriginalCockpit.Where(r => !visual.PilotRenderers.Contains(r) && !visual.SeatRenderers.Contains(r)).ToList();
        }

        void SetupFlames(Aircraft aircraft, Transform root, List<OrigPart> parts, Matrix4x4 modelToRoot, TyphoonVisual visual)
        {
            string nozzlePrefix = _model.Any(g => g.Name.StartsWith("petals_", StringComparison.OrdinalIgnoreCase)) ? "petals_" : "nozzle_";
            var nozzles = _model.Where(g => g.Name.StartsWith(nozzlePrefix, StringComparison.OrdinalIgnoreCase) && !g.Name.EndsWith("_core"))
                                .Select(g => TransformBounds(NozzleExit(g), modelToRoot)).ToList();
            if (nozzles.Count < 2 || AfterburnersField == null) return;
            var meshBounds = parts.ToDictionary(p => p.Renderer, p => p.RootBounds);
            var jets = new HashSet<JetNozzle>(aircraft.GetComponentsInChildren<JetNozzle>(true));
            if (aircraft.partLookup != null)
                foreach (var up in aircraft.partLookup) if (up != null) foreach (var j in up.GetComponentsInChildren<JetNozzle>(true)) jets.Add(j);

            int made = 0;
            if (_ownReheat.Value)
            {
                foreach (var jet in jets)
                {
                    var abs0 = AfterburnersField.GetValue(jet) as Array;
                    if (abs0 == null) continue;
                    foreach (var ab in abs0)
                    {
                        if (ab == null) continue;
                        foreach (var fn in new[] { "flameRenderer", "nozzleGlowRenderer" })
                        {
                            var r0 = ab.GetType().GetField(fn, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)?.GetValue(ab) as Renderer;
                            if (r0 != null && !visual.FlameOriginals.Contains(r0)) visual.FlameOriginals.Add(r0);
                        }
                    }
                }
                var frame = Quaternion.LookRotation(modelToRoot.MultiplyVector(Vector3.forward), modelToRoot.MultiplyVector(Vector3.up));
                ReheatFlame.Lamps = _reheatLamps.Value;
                ReheatFlame.TexDir = _pluginDir;
                visual.Reheat = ReheatFlame.Build(root, nozzles, frame, wp =>
                {
                    var pet = visual.Surfaces.Where(sf => sf.FullRotation && !sf.IsStick && !sf.IsThrottle && sf.Pivot != null)
                                             .OrderBy(sf => (sf.Pivot.position - wp).sqrMagnitude).FirstOrDefault();
                    return pet != null ? pet.Pivot : null;
                });
                if (visual.Reheat != null) _log.LogInfo($"Reheat: the Typhoon's own flame on {nozzles.Count} nozzles ({visual.FlameOriginals.Count} game flame parts hidden).");
                else { visual.FlameOriginals.Clear(); _log.LogWarning("Reheat: could not build the Typhoon's own flame; using the game's."); }
            }
            foreach (var jet in jets)
            {
                if (visual.Reheat != null) break;
                var abs = AfterburnersField.GetValue(jet) as Array;
                if (abs == null) continue;
                foreach (var ab in abs)
                {
                    if (ab == null) continue;
                    var t = ab.GetType();
                    var flame = t.GetField("flameRenderer", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)?.GetValue(ab) as Renderer;
                    var glow = t.GetField("nozzleGlowRenderer", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)?.GetValue(ab) as Renderer;
                    Bounds refB;
                    if (!(glow != null && meshBounds.TryGetValue(glow, out refB)) && !(flame != null && meshBounds.TryGetValue(flame, out refB))) continue;
                    float refDia = Mathf.Max(0.05f, Mathf.Max(refB.size.x, refB.size.y));
                    foreach (var r in new[] { flame, glow })
                    {
                        if (r == null) continue;
                        bool isGlow = r == glow;
                        var copy = new TyphoonVisual.FlameCopy { Original = r };
                        foreach (var nb in nozzles)
                        {
                            float ratio = Mathf.Clamp(Mathf.Max(nb.size.x, nb.size.y) / refDia, 0.3f, 1.5f);
                            float dz = isGlow ? (nb.center.z + 0.08f) - refB.center.z : nb.center.z - refB.min.z;
                            if (isGlow) ratio *= 0.85f;
                            Vector3 delta = new Vector3(nb.center.x - refB.center.x, nb.center.y - refB.center.y, dz);
                            var clone = CloneRenderer(r, root, delta);
                            if (clone == null) continue;
                            Vector3 ls0 = r.transform.localScale;
                            clone.transform.localScale = ls0 * ratio;
                            var pet = visual.Surfaces.Where(sf => sf.FullRotation && !sf.IsStick && !sf.IsThrottle && sf.Pivot != null)
                                                     .OrderBy(sf => (sf.Pivot.position - clone.transform.position).sqrMagnitude).FirstOrDefault();
                            if (pet != null) clone.transform.SetParent(pet.Pivot, true);
                            Vector3 l1 = clone.transform.localScale;
                            copy.Clones.Add(clone);
                            copy.ScaleMuls.Add(new Vector3(Div(l1.x, ls0.x), Div(l1.y, ls0.y), Div(l1.z, ls0.z)));
                        }
                        if (copy.Clones.Count > 0) { visual.Flames.Add(copy); made += copy.Clones.Count; }
                    }
                }
            }
            if (made > 0) _log.LogInfo($"Twin afterburners: {made} flame/glow copies placed behind the Typhoon nozzles.");
            if (_moveHaze.Value)
                try { SetupHaze(jets, root, nozzles, visual); }
                catch (Exception e) { _log.LogWarning("Heat haze setup failed: " + e.Message); }
        }

        static readonly FieldInfo HeatHazeField = typeof(JetNozzle).GetField("heatHaze", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

        void SetupHaze(IEnumerable<JetNozzle> jets, Transform root, List<Bounds> nozzles, TyphoonVisual visual)
        {
            if (HeatHazeField == null) return;
            int made = 0;
            var holder = new GameObject("Typhoon_haze_tmp"); holder.SetActive(false);
            try
            {
                foreach (var jet in jets)
                {
                    object hz = HeatHazeField.GetValue(jet);
                    if (hz == null) continue;
                    var sys = hz.GetType().GetField("system", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)?.GetValue(hz) as ParticleSystem;
                    if (sys == null || visual.Hazes.Any(h => h.Original == sys)) continue;
                    var copy = new TyphoonVisual.HazeCopy { Original = sys, RateMul = nozzles.Count > 1 ? 0.75f : 1f };
                    foreach (var nb in nozzles)
                    {
                        var go = UnityEngine.Object.Instantiate(sys.gameObject, holder.transform, false);
                        go.name = "Typhoon_heatHaze";
                        foreach (Transform child in go.transform.Cast<Transform>().ToList()) UnityEngine.Object.DestroyImmediate(child.gameObject);
                        foreach (var b in go.GetComponents<Component>())
                            if (!(b is Transform) && !(b is ParticleSystem) && !(b is ParticleSystemRenderer)) UnityEngine.Object.DestroyImmediate(b);
                        Vector3 world = root.TransformPoint(nb.center);
                        var pet = visual.Surfaces.Where(sf => sf.FullRotation && !sf.IsStick && !sf.IsThrottle && sf.Pivot != null)
                                                 .OrderBy(sf => (sf.Pivot.position - world).sqrMagnitude).FirstOrDefault();
                        Transform parent = pet != null ? pet.Pivot : root;
                        go.transform.SetParent(parent, false);
                        go.transform.position = world;
                        go.transform.rotation = sys.transform.rotation;
                        go.transform.localScale = sys.transform.lossyScale;
                        go.layer = sys.gameObject.layer;
                        go.SetActive(true);
                        var ps = go.GetComponent<ParticleSystem>();
                        if (ps != null) { ps.Clear(); copy.Clones.Add(ps); made++; }
                    }
                    if (copy.Clones.Count > 0) visual.Hazes.Add(copy);
                }
            }
            finally { UnityEngine.Object.Destroy(holder); }
            if (made > 0) _log.LogInfo($"Heat haze: {made} copies placed on the Typhoon nozzles.");
        }

        static float _gearTopRaise = float.NaN;
        bool _wingtipReported;

        float TopOver(Bounds b, Vector3 offset, float scale)
        {
            float best = float.NaN;
            for (int i = 0; i <= 2; i++)
                for (int j = 0; j <= 2; j++)
                {
                    float x = Mathf.Lerp(b.min.x, b.max.x, i * 0.5f), z = Mathf.Lerp(b.min.z, b.max.z, j * 0.5f);
                    Vector3 q = (new Vector3(x, 0f, z) - offset) / scale;
                    float h = HighestSurface(q.x, q.z);
                    if (!float.IsNaN(h) && (float.IsNaN(best) || h < best)) best = h;
                }
            return best;
        }

        float GearRaise(List<OrigPart> parts, Transform root, Vector3 offset, float scale, bool gearDown)
        {
            var hinges = new HashSet<Transform>();
            foreach (var p in parts)
            {
                if (p.Path.IndexOf("gear", StringComparison.OrdinalIgnoreCase) < 0) continue;
                for (var t = p.Renderer.transform; t != null && t != root; t = t.parent)
                    if (t.name.StartsWith("gearHinge", StringComparison.OrdinalIgnoreCase) || t.name.StartsWith("gearMount", StringComparison.OrdinalIgnoreCase))
                    { hinges.Add(t); }
            }
            float need = float.NaN;
            foreach (var h in hinges)
            {
                Vector3 hp = root.InverseTransformPoint(h.position);
                if (Mathf.Abs(hp.x) < 0.6f) continue;
                Vector3 q = (hp - offset) / scale;
                float lo = LowestSurface(q.x, q.z), hi = HighestSurface(q.x, q.z);
                if (float.IsNaN(lo)) { _log.LogInfo($"Gear hinge '{h.name}' at {hp} has no Typhoon skin above it."); continue; }
                float loY = lo * scale + offset.y, hiY = hi * scale + offset.y;
                float target = Mathf.Max(0.06f, 0.35f * (hiY - loY));
                float r = hp.y + target - loY;
                _log.LogInfo($"Gear hinge '{h.name}' y={hp.y:0.00}, Typhoon skin {loY:0.00}..{hiY:0.00} -> raise {r:0.00}");
                if (float.IsNaN(need) || r > need) need = r;
            }
            if (gearDown)
            {
                float top = float.NaN;
                foreach (var p in parts)
                {
                    if (p.Path.IndexOf("gear", StringComparison.OrdinalIgnoreCase) < 0 || p.Path.IndexOf("door", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                    var b = p.RootBounds;
                    if (Mathf.Abs(b.center.x) < 0.6f) continue;
                    string leaf = p.Path.Substring(p.Path.LastIndexOf('/') + 1).ToLowerInvariant();
                    if (leaf.Contains("arm") || leaf.Contains("hinge") || leaf.Contains("mount") || leaf.Contains("chock")) continue;
                    float hi = TopOver(b, offset, scale);
                    if (float.IsNaN(hi)) continue;
                    float r = b.max.y + 0.03f - (hi * scale + offset.y);
                    if (r > 0f) _log.LogInfo($"Gear part '{p.Path}' top {b.max.y:0.00} above the Typhoon's skin {hi * scale + offset.y:0.00}: raise {r:0.00}");
                    if (float.IsNaN(top) || r > top) top = r;
                }
                if (!float.IsNaN(top)) _gearTopRaise = top;
            }
            if (!float.IsNaN(_gearTopRaise) && (float.IsNaN(need) || _gearTopRaise > need)) need = _gearTopRaise;
            if (float.IsNaN(need)) return float.NaN;
            return Mathf.Clamp(need, 0f, 0.8f);
        }

        static float Div(float a, float b) => Mathf.Abs(b) < 1e-6f ? a : a / b;

        static Bounds NozzleExit(ObjGroup g)
        {
            var pts = g.Positions.Where(v => Mathf.Abs(v.x) > 0.15f).ToList();
            if (pts.Count < 8) return g.Bounds;
            float zmin = pts.Min(v => v.z);
            var ring = pts.Where(v => v.z < zmin + 0.1f).ToList();
            var b = new Bounds(ring[0], Vector3.zero);
            foreach (var v in ring) b.Encapsulate(v);
            b.center = new Vector3(b.center.x, b.center.y, zmin);
            b.size = new Vector3(b.size.x, b.size.y, 0f);
            return b;
        }

        static Renderer CloneRenderer(Renderer r, Transform root, Vector3 rootDelta)
        {
            var mf = r.GetComponent<MeshFilter>();
            if (mf == null || mf.sharedMesh == null) return null;
            var go = new GameObject(r.name + "_typhoon");
            go.layer = r.gameObject.layer;
            go.transform.SetParent(r.transform.parent, false);
            go.transform.localRotation = r.transform.localRotation;
            go.transform.localScale = r.transform.localScale;
            go.transform.position = r.transform.position + root.TransformVector(rootDelta);
            go.AddComponent<MeshFilter>().sharedMesh = mf.sharedMesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterials = r.sharedMaterials;
            mr.shadowCastingMode = r.shadowCastingMode;
            mr.enabled = r.enabled;
            return mr;
        }

        void BindHardpoints(Aircraft aircraft, Transform root, Vector3 offset, float scale, TyphoonVisual visual)
        {
            if (aircraft.weaponManager == null || aircraft.weaponManager.hardpointSets == null || visual == null) return;
            HardpointLayout.EnsureLoaded();
            visual.Stations.Clear();
            var seen = new HashSet<Transform>();
            foreach (var set in aircraft.weaponManager.hardpointSets)
            {
                if (set == null || set.hardpoints == null) continue;
                foreach (var hp in set.hardpoints)
                {
                    var t = hp?.transform;
                    if (t == null || t.parent == null || !seen.Add(t)) continue;
                    var st = new HardpointStation(hp, set.name, root, offset, scale);
                    visual.Stations.Add(st);
                    st.Apply(true);
                }
            }
            int placed = visual.Stations.Count(s => HardpointLayout.Station(s.Name) != null);
            _log.LogInfo($"{visual.Stations.Count} hardpoints, {placed} placed from {Path.GetFileName(HardpointLayout.FilePath)}" +
                         (placed < visual.Stations.Count ? " (the rest stay where the base jet has them" + (TyphoonPlugin.Locked ? ")." : "; press " + TyphoonEditor.KeyName + " in the hangar to place them).") : "."));
        }

        float LowestSurface(float x, float z) { return SurfaceAt(x, z, false); }
        float HighestSurface(float x, float z) { return SurfaceAt(x, z, true); }

        float SurfaceAt(float x, float z, bool highest, bool all = false)
        {
            float best = float.NaN;
            foreach (var g in _model)
            {
                string n = g.Name.ToLowerInvariant();
                bool body = n.StartsWith("wing_") || n.StartsWith("fuselage") || n.StartsWith("intake") || n.StartsWith("canard") || n.StartsWith("flaperon");
                if (all) body |= n.StartsWith("nozzle") || n.StartsWith("petals") || n.StartsWith("geardoor");
                if (!body) continue;
                if (x < g.Bounds.min.x || x > g.Bounds.max.x || z < g.Bounds.min.z || z > g.Bounds.max.z) continue;
                var P = g.Positions; var T = g.Triangles;
                for (int i = 0; i < T.Count; i += 3)
                {
                    Vector3 a = P[T[i]], b = P[T[i + 1]], c = P[T[i + 2]];
                    float d = (b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z);
                    if (Mathf.Abs(d) < 1e-9f) continue;
                    float w1 = ((b.z - c.z) * (x - c.x) + (c.x - b.x) * (z - c.z)) / d;
                    float w2 = ((c.z - a.z) * (x - c.x) + (a.x - c.x) * (z - c.z)) / d;
                    float w3 = 1 - w1 - w2;
                    if (w1 < 0 || w2 < 0 || w3 < 0) continue;
                    float y = w1 * a.y + w2 * b.y + w3 * c.y;
                    if (float.IsNaN(best) || (highest ? y > best : y < best)) best = y;
                }
            }
            return best;
        }

        void CollectControlSurfaces(Aircraft aircraft, Dictionary<string, Transform> drivers, Dictionary<string, Quaternion> rest)
        {
            if (VisibleMeshField == null) { _log.LogWarning("ControlSurface.visibleMesh not found; surfaces stay fixed."); return; }
            var comps = new HashSet<ControlSurface>(aircraft.GetComponentsInChildren<ControlSurface>(true));
            if (aircraft.partLookup != null)
                foreach (var up in aircraft.partLookup) if (up != null) foreach (var c in up.GetComponentsInChildren<ControlSurface>(true)) comps.Add(c);
            foreach (var c in comps)
            {
                var vm = VisibleMeshField.GetValue(c) as GameObject;
                if (vm != null && !drivers.ContainsKey(vm.name)) drivers[vm.name] = vm.transform;
            }
            var jets = new HashSet<Turbojet>(aircraft.GetComponentsInChildren<Turbojet>(true));
            if (aircraft.partLookup != null)
                foreach (var up in aircraft.partLookup) if (up != null) foreach (var j in up.GetComponentsInChildren<Turbojet>(true)) jets.Add(j);
            string vecName = null;
            foreach (var j in jets)
            {
                var vt = VectoringField?.GetValue(j) as Transform[];
                if (vt != null && vt.Length > 0 && vt[0] != null) { drivers["vectoring"] = vt[0]; break; }
            }
            if (drivers.ContainsKey("vectoring")) _log.LogInfo($"Thrust vectoring driven by '{drivers["vectoring"].name}'.");
            else _log.LogWarning("No thrust-vectoring transform found; nozzles stay fixed.");

            var def = aircraft.definition as AircraftDefinition;
            if (def != null && def.unitPrefab != null)
                foreach (var c in def.unitPrefab.GetComponentsInChildren<ControlSurface>(true))
                {
                    var vm = VisibleMeshField.GetValue(c) as GameObject;
                    if (vm != null && !rest.ContainsKey(vm.name)) rest[vm.name] = vm.transform.localRotation;
                }
            if (vecName != null && def != null && def.unitPrefab != null)
                foreach (var t in def.unitPrefab.GetComponentsInChildren<Transform>(true))
                    if (t.name == vecName) { rest["vectoring"] = t.localRotation; break; }
        }

        static bool IsUnder(Transform t, HashSet<Transform> set)
        {
            for (var x = t; x != null; x = x.parent) if (set.Contains(x)) return true;
            return false;
        }

        static readonly FieldInfo NavLightsField = typeof(NavLights).GetField("navLights", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

        void FixStrayLights(Aircraft aircraft, Transform root, Vector3 offset, float scale, bool late)
        {
            var visual = aircraft.GetComponent<TyphoonVisual>();
            if (visual == null) return;
            if (!late) visual.LateLightFix = () => FixStrayLights(aircraft, root, offset, scale, true);
            CockpitCamera.Hook();
            var pods = _model.Where(g => g.Name.StartsWith("pod_", StringComparison.OrdinalIgnoreCase)).ToList();
            if (pods.Count == 0) return;
            float span = pods.Max(g => Mathf.Max(Mathf.Abs(g.Bounds.min.x), Mathf.Abs(g.Bounds.max.x))) * scale;
            var roots = new List<Transform> { aircraft.transform };
            if (aircraft.partLookup != null) roots.AddRange(aircraft.partLookup.Where(u => u != null).Select(u => u.transform));
            var cands = new HashSet<Transform>();
            foreach (var r in roots.Distinct())
            {
                foreach (var rd in r.GetComponentsInChildren<Renderer>(true))
                {
                    if (rd.name.StartsWith("Typhoon_") || rd.forceRenderingOff) continue;
                    if (rd.bounds.size.magnitude > 3f) continue;
                    if (Regex.IsMatch(rd.name, "trail|vapou?r|contrail|smoke|vortex", RegexOptions.IgnoreCase)) continue;
                    cands.Add(rd.transform);
                }
                foreach (var l in r.GetComponentsInChildren<Light>(true)) cands.Add(l.transform);
            }
            int moved = 0;
            foreach (var t in cands)
            {
                if (t == null || IsWeapon(t, root)) continue;
                if (t.GetComponentInParent<Camera>() != null) continue;
                Vector3 p = root.InverseTransformPoint(t.position);
                float ax = Mathf.Abs(p.x);
                if (late && ax > span + 0.05f && ax <= span + 3f)
                    _log.LogInfo($"  Outside the wingspan after spawn: '{PathOf(t, root)}' [{string.Join(",", t.GetComponents<Component>().Select(c => c.GetType().Name))}] at x {p.x:0.00}");
                if (ax < span + 0.12f || ax > span + 3f) continue;
                if (cands.Any(o => o != t && t.IsChildOf(o) && Mathf.Abs(root.InverseTransformPoint(o.position).x) > span + 0.12f)) continue;
                var pod = pods.FirstOrDefault(g => Mathf.Sign(g.Bounds.center.x) == Mathf.Sign(p.x));
                if (pod == null) continue;
                Bounds pb = TransformBounds(pod.Bounds, Matrix4x4.TRS(offset, Quaternion.identity, Vector3.one * scale));
                var target = new Vector3(Mathf.Sign(p.x) * (span + 0.02f), pb.center.y, Mathf.Clamp(p.z, pb.min.z + 0.2f, pb.max.z - 0.2f));
                Vector3 delta = root.TransformPoint(target) - t.position;
                if (delta.magnitude > 3f) continue;
                t.position += delta;
                moved++;
                if (t.parent != null) visual.Pinned[t] = t.localPosition;
                _log.LogInfo($"  Light '{t.name}' ({t.GetComponents<Component>().Length} components) moved {delta.magnitude:0.00} m onto the wingtip pod.");
            }
            if (moved > 0) _log.LogInfo($"Moved {moved} stray wingtip lights onto the Typhoon{(late ? " (late pass)" : "")}.");
            if (late && !_wingtipReported && false)
            {
                _wingtipReported = true;
                var mtr = Matrix4x4.TRS(offset, Quaternion.identity, Vector3.one * scale);
                foreach (var pod in pods)
                {
                    Bounds pb = TransformBounds(pod.Bounds, mtr);
                    pb.Expand(new Vector3(3f, 2f, 3f));
                    foreach (var r in roots.Distinct())
                        foreach (var rd in r.GetComponentsInChildren<Renderer>(true))
                        {
                            if (rd.name.StartsWith("Typhoon_") || IsWeapon(rd.transform, root)) continue;
                            Vector3 lp = root.InverseTransformPoint(rd.bounds.center);
                            if (!pb.Contains(lp)) continue;
                            _log.LogInfo($"  Near wingtip {pod.Name}: '{PathOf(rd.transform, root)}' {rd.GetType().Name} on={rd.enabled && rd.gameObject.activeInHierarchy && !rd.forceRenderingOff} " +
                                         $"mat '{(rd.sharedMaterial != null ? rd.sharedMaterial.name : "-")}' at {lp.x:0.00},{lp.y:0.00},{lp.z:0.00} size {rd.bounds.size.magnitude:0.00}");
                        }
                }
            }
        }

        void MoveNavLights(Aircraft aircraft, Transform root, Vector3 offset, float scale)
        {
            var mgr = aircraft.GetComponentInChildren<NavLights>(true);
            var arr = mgr != null && NavLightsField != null ? NavLightsField.GetValue(mgr) as Array : null;
            if (arr == null) return;
            var pods = _model.Where(g => g.Name.StartsWith("pod_", StringComparison.OrdinalIgnoreCase)).ToList();
            var fin = _model.FirstOrDefault(g => g.Name.Equals("fin", StringComparison.OrdinalIgnoreCase));
            int moved = 0;
            foreach (var nl in arr)
            {
                if (nl == null) continue;
                var t = nl.GetType();
                var rend = t.GetField("renderer", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)?.GetValue(nl) as Renderer;
                var objs = t.GetField("objects", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)?.GetValue(nl) as GameObject[];
                Transform anchor = rend != null ? rend.transform : (objs != null && objs.Length > 0 && objs[0] != null ? objs[0].transform : null);
                if (anchor == null) continue;

                Vector3 cur = rend != null ? rend.bounds.center : anchor.position;
                Vector3 q = (root.InverseTransformPoint(cur) - offset) / scale;
                Vector3 target;
                var pod = pods.Where(g => Mathf.Sign(g.Bounds.center.x) == Mathf.Sign(q.x)).FirstOrDefault();
                bool ownLamp = false;
                if (Mathf.Abs(q.x) > 2.5f && pod != null)
                {
                    target = new Vector3(q.x > 0 ? pod.Bounds.max.x : pod.Bounds.min.x, pod.Bounds.center.y, pod.Bounds.center.z + 0.3f);
                    var lamp = _model.FirstOrDefault(g => g.Name.StartsWith("navlamp_", StringComparison.OrdinalIgnoreCase) && !g.Name.EndsWith("base", StringComparison.OrdinalIgnoreCase)
                                                          && Mathf.Sign(g.Bounds.center.x) == Mathf.Sign(q.x));
                    if (lamp != null)
                    {
                        ownLamp = true;
                        target = lamp.Bounds.center + new Vector3(Mathf.Sign(q.x) * 0.5f * lamp.Bounds.size.x, 0f, 0f);
                    }
                }
                else if (q.y > 1.2f && fin != null)
                    target = new Vector3(0f, fin.Bounds.max.y - 0.15f, fin.Bounds.min.z + 0.25f);
                else continue;

                Vector3 delta = root.TransformPoint(target * scale + offset) - cur;
                if (delta.magnitude > 6f) continue;
                var set = new List<Transform> { anchor };
                if (objs != null) foreach (var o in objs) if (o != null && !set.Contains(o.transform)) set.Add(o.transform);
                var top = set.Where(x => !set.Any(y => y != x && x.IsChildOf(y))).ToList();
                var vis = aircraft.GetComponent<TyphoonVisual>();
                foreach (var x in top) { x.position += delta; if (vis != null && x.parent != null) vis.Pinned[x] = x.localPosition; }
                moved++;
                if (ownLamp)
                {
                    Vector3 lampW = root.TransformPoint(target * scale + offset);
                    Vector3 outRoot = new Vector3(Mathf.Sign(q.x), 0f, 0f);
                    Vector3 outW = root.TransformDirection(outRoot);
                    int hid = 0, lights = 0;
                    var what = new List<string>();
                    var holders = new List<Transform>();
                    if (objs != null) foreach (var o in objs) if (o != null && !holders.Contains(o.transform)) holders.Add(o.transform);
                    var movers = new List<Transform>(holders);
                    foreach (var hd in holders) foreach (var l in hd.GetComponentsInChildren<Light>(true)) if (!movers.Contains(l.transform)) movers.Add(l.transform);
                    Func<Transform, int> depth = tr => { int n_ = 0; for (var p_ = tr.parent; p_ != null; p_ = p_.parent) n_++; return n_; };
                    foreach (var x in movers.OrderBy(depth)) { x.position = lampW + outW * 0.08f; if (vis != null && x.parent != null) vis.Pinned[x] = x.localPosition; }
                    if (rend != null && !rend.forceRenderingOff) { rend.forceRenderingOff = true; hid++; }
                    foreach (var hd in holders)
                    {
                        foreach (var lr in hd.GetComponentsInChildren<Renderer>(true))
                        {
                            if (lr.name.StartsWith("Typhoon_")) continue;
                            if (!lr.forceRenderingOff) { lr.forceRenderingOff = true; hid++; }
                        }
                        foreach (var l in hd.GetComponentsInChildren<Light>(true))
                        {
                            if (TamedLights.Add(l.GetInstanceID())) { l.intensity *= 0.4f; l.range = Mathf.Min(l.range, 3f); }
                            lights++;
                        }
                        foreach (var b in hd.GetComponentsInChildren<Behaviour>(true))
                            if (b != null && b.GetType().Name.IndexOf("Flare", StringComparison.OrdinalIgnoreCase) >= 0) b.enabled = false;
                        what.Add(hd.name + " [" + string.Join(",", hd.GetComponentsInChildren<Component>(true).Select(c => c != null ? c.GetType().Name : "?").Where(n_ => n_ != "Transform").Distinct()) + "]");
                    }
                    Transform host = objs != null ? objs.Where(o => o != null).Select(o => o.transform).FirstOrDefault() : null;
                    bool halo = false;
                    if (host != null && vis != null)
                        try { halo = BuildHalo(vis, host, lampW + outW * 0.012f, outRoot, q.x < 0f); }
                        catch (Exception e) { _log.LogWarning("Nav light halo: " + e.Message); }
                    _log.LogInfo($"  Nav light '{anchor.name}': the Typhoon's own lamp is used; {hid} drawn part(s) of the base jet's unit hidden, {lights} light source(s) turned down{(halo ? ", own halo" : ", no halo")}. Unit: {string.Join("; ", what)}");
                }
                _log.LogInfo($"  Nav light '{anchor.name}' moved {delta.magnitude:0.00} m");
            }
            if (moved > 0) _log.LogInfo($"Moved {moved} nav lights onto the Typhoon.");
        }

        static readonly HashSet<int> TamedLights = new HashSet<int>();
        static Mesh _haloMesh;
        static Texture2D _haloTex;
        bool BuildHalo(TyphoonVisual vis, Transform host, Vector3 lampWorld, Vector3 outRoot, bool red)
        {
            var sh = Shader.Find("Sprites/Default");
            if (sh == null) return false;
            if (_haloTex == null)
            {
                const int N = 96;
                _haloTex = new Texture2D(N, N, TextureFormat.RGBA32, true, true) { name = "Typhoon_navhalo", wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear };
                var px = new Color32[N * N];
                for (int y = 0; y < N; y++)
                    for (int x = 0; x < N; x++)
                    {
                        float r = Mathf.Sqrt((x + 0.5f - N * 0.5f) * (x + 0.5f - N * 0.5f) + (y + 0.5f - N * 0.5f) * (y + 0.5f - N * 0.5f)) / (N * 0.5f);
                        float a = 0.95f * Mathf.Exp(-(r / 0.11f) * (r / 0.11f)) + 0.30f * Mathf.Exp(-(r / 0.40f) * (r / 0.40f));
                        a *= 1f - Mathf.SmoothStep(0.80f, 1f, r);
                        px[y * N + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(255f * Mathf.Clamp01(a)));
                    }
                _haloTex.SetPixels32(px); _haloTex.Apply(true, true);
            }
            if (_haloMesh == null)
            {
                _haloMesh = new Mesh { name = "Typhoon_navhalo" };
                _haloMesh.vertices = new[] { new Vector3(-0.5f, -0.5f, 0f), new Vector3(0.5f, -0.5f, 0f), new Vector3(0.5f, 0.5f, 0f), new Vector3(-0.5f, 0.5f, 0f) };
                _haloMesh.uv = new[] { new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(0f, 1f) };
                _haloMesh.triangles = new[] { 0, 2, 1, 0, 3, 2 };
                _haloMesh.RecalculateBounds();
            }
            var go = new GameObject("Typhoon_navhalo_" + (red ? "L" : "R"));
            go.transform.SetParent(host, false);
            go.transform.position = lampWorld;
            foreach (var kv in vis.NavLamps) if (kv.Key != null) { go.layer = kv.Key.gameObject.layer; break; }
            go.AddComponent<MeshFilter>().sharedMesh = _haloMesh;
            var mr = go.AddComponent<MeshRenderer>();
            var m = new Material(sh) { name = "Typhoon_navhalo", mainTexture = _haloTex, renderQueue = 3100 };
            var tint = red ? new Color(1.9f, 0.20f, 0.12f, 0.6f) : new Color(0.16f, 1.8f, 0.55f, 0.6f);
            m.color = tint;
            mr.sharedMaterial = m;
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off; mr.receiveShadows = false;
            mr.lightProbeUsage = UnityEngine.Rendering.LightProbeUsage.Off; mr.reflectionProbeUsage = UnityEngine.Rendering.ReflectionProbeUsage.Off;
            mr.enabled = false;
            vis.Halos.Add(new TyphoonVisual.NavHalo { T = go.transform, Host = host, R = mr, Local = host.InverseTransformPoint(lampWorld), OutRoot = outRoot, M = m, Tint = tint });
            return true;
        }

        Dictionary<string, float> BaseWheelBottoms(Aircraft aircraft)
        {
            var res = new Dictionary<string, float>();
            var ground = new Dictionary<string, float>();
            _wheelPoints.Clear();
            var def = aircraft.definition as AircraftDefinition;
            var prefab = def != null ? def.unitPrefab : null;
            if (prefab == null) return res;
            foreach (var lg in prefab.GetComponentsInChildren<LandingGear>(true))
            {
                var wheels = TyphoonGearRig.WheelsF?.GetValue(lg) as Transform[];
                float rad = 0f;
                try { rad = Convert.ToSingle(TyphoonGearRig.RadiusF.GetValue(lg)); } catch { }
                Transform w = wheels != null && wheels.Length > 0 && wheels[0] != null ? wheels[0] : lg.transform;
                Vector3 p = prefab.transform.InverseTransformPoint(w.position);
                string key = Mathf.Abs(p.x) < 0.5f ? "nose" : "main";
                float b = p.y - rad;
                float old;
                res[key] = res.TryGetValue(key, out old) ? Mathf.Min(old, b) : b;
                _wheelPoints[key == "nose" ? "nose" : (p.x < 0 ? "main_L" : "main_R")] = new Vector3(p.x, b, p.z);
                try
                {
                    var cast = TyphoonGearRig.CastF?.GetValue(lg) as Transform;
                    float trav = Convert.ToSingle(TyphoonGearRig.TravelF.GetValue(lg));
                    if (cast != null && trav > 0.01f)
                    {
                        float g = prefab.transform.InverseTransformPoint(cast.position - cast.up * trav).y;
                        float og;
                        ground[key] = ground.TryGetValue(key, out og) ? Mathf.Min(og, g) : g;
                    }
                }
                catch { }
            }
            if (res.Count > 0)
                _log.LogInfo("Base jet's wheels touch down at " + string.Join(", ", res.Select(kv => $"{kv.Key} {kv.Value:0.00}")) + " m as posed" +
                             (ground.Count > 0 ? "; with the legs fully out at " + string.Join(", ", ground.Select(kv => $"{kv.Key} {kv.Value:0.00}")) + " m (the pose is " +
                                                 string.Join(", ", ground.Where(kv => res.ContainsKey(kv.Key)).Select(kv => $"{kv.Key} {(res[kv.Key] - kv.Value) * 100f:0} cm")) + " compressed)." : "."));
            foreach (var kv in ground) res[kv.Key + "_ground"] = kv.Value;
            return res;
        }
        readonly Dictionary<string, Vector3> _wheelPoints = new Dictionary<string, Vector3>();

        void HideBaseGear(List<OrigPart> parts, Transform root, Vector3 offset, float scale, Dictionary<string, float> bottoms)
        {
            int hidden = 0, chocks = 0;
            foreach (var p in parts)
            {
                if (p.Status != "kept") continue;
                if (p.Path.IndexOf("chock", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    var u = _gearDef.Units;
                    Vector3 rp = p.RootBounds.center;
                    string key = Mathf.Abs(rp.x) < 0.5f ? "nose" : (rp.x < 0 ? "main_L" : "main_R");
                    var unit = u.FirstOrDefault(x => x.Name.Equals(key, StringComparison.OrdinalIgnoreCase));
                    Vector3 rev;
                    if (unit == null || !_wheelPoints.TryGetValue(key, out rev)) continue;
                    Vector3 ty = offset + (unit.WheelCentre - Vector3.up * unit.WheelRadius) * scale;
                    Vector3 delta = ty - rev;
                    var t = p.Renderer.transform;
                    float sc = t.parent != null ? Mathf.Max(1e-3f, t.parent.lossyScale.x / Mathf.Max(1e-3f, root.lossyScale.x)) : 1f;
                    t.localPosition += delta / sc;
                    chocks++;
                    continue;
                }
                if (Regex.IsMatch(p.Path, "gear|wheel|strut|bumpstop|tyre|tire", RegexOptions.IgnoreCase))
                {
                    p.Renderer.forceRenderingOff = true;
                    hidden++;
                }
            }
            _log.LogInfo($"Base jet's gear hidden ({hidden} meshes, the physics stays); {chocks} wheel chocks moved under the Typhoon's wheels.");
        }

        static Transform PickParent(Bounds part, List<OrigPart> hidden, Transform root)
        {
            OrigPart best = null;
            Vector3 c = part.center;
            foreach (var p in hidden)
            {
                var b = p.RootBounds;
                if (c.x < b.min.x - 0.2f || c.x > b.max.x + 0.2f || c.z < b.min.z - 0.2f || c.z > b.max.z + 0.2f) continue;
                if (best == null || Volume(p.RootBounds) > Volume(best.RootBounds)) best = p;
            }
            return best != null ? best.Renderer.transform : root;
        }

        static bool IsWeapon(Transform t, Transform root)
        {
            for (var x = t; x != null && x != root; x = x.parent)
                if (x.GetComponent<Weapon>() != null || x.GetComponent<Missile>() != null || x.GetComponent<ColorableMount>() != null)
                    return true;
            return false;
        }

        static Transform FindPilot(Aircraft aircraft)
        {
            if (aircraft.pilots != null)
                foreach (var p in aircraft.pilots)
                    if (p != null) return p.transform;
            return aircraft.cockpit != null ? aircraft.cockpit.transform : null;
        }

        static void MakeDoubleSided(Mesh m)
        {
            var v = m.vertices; var nr = m.normals; var uv = m.uv; var t = m.triangles;
            int n = v.Length;
            var v2 = new Vector3[n * 2]; var n2 = new Vector3[n * 2]; var uv2 = new Vector2[uv.Length == n ? n * 2 : 0];
            for (int i = 0; i < n; i++)
            {
                v2[i] = v[i]; v2[i + n] = v[i];
                n2[i] = nr.Length == n ? nr[i] : Vector3.up; n2[i + n] = -n2[i];
                if (uv2.Length > 0) { uv2[i] = uv[i]; uv2[i + n] = uv[i]; }
            }
            var t2 = new int[t.Length * 2];
            for (int i = 0; i < t.Length; i += 3)
            {
                t2[i] = t[i]; t2[i + 1] = t[i + 1]; t2[i + 2] = t[i + 2];
                int j = t.Length + i;
                t2[j] = t[i] + n; t2[j + 1] = t[i + 2] + n; t2[j + 2] = t[i + 1] + n;
            }
            if (n * 2 > 65000) m.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            m.vertices = v2; m.normals = n2; if (uv2.Length > 0) m.uv = uv2; m.triangles = t2;
            m.RecalculateBounds();
            try { m.RecalculateTangents(); } catch { }
        }

        void ExtendNoseGear(Aircraft aircraft, Transform root, Vector3 offset, float scale, List<OrigPart> parts, TyphoonVisual visual)
        {
            if (!aircraft.gearDeployed) return;
            Transform hinge = null; Renderer leg = null;
            foreach (var p in parts)
            {
                if (p.Path.IndexOf("gear", StringComparison.OrdinalIgnoreCase) < 0) continue;
                for (var t = p.Renderer.transform; t != null && t != root; t = t.parent)
                    if (t.name.StartsWith("gearHinge", StringComparison.OrdinalIgnoreCase) && Mathf.Abs(root.InverseTransformPoint(t.position).x) < 0.6f)
                    { hinge = t; if (leg == null || p.Renderer.transform.parent == t) leg = p.Renderer; break; }
            }
            if (hinge == null) { _log.LogInfo("Nose gear: no hinge found."); return; }
            Vector3 hp = root.InverseTransformPoint(hinge.position);
            if (leg != null) { var lb = leg.bounds; Vector3 top = root.InverseTransformPoint(new Vector3(lb.center.x, lb.max.y, lb.center.z)); hp = new Vector3(hp.x, Mathf.Max(hp.y, top.y - 0.05f), root.InverseTransformPoint(lb.center).z); }
            Vector3 q = (hp - offset) / scale;
            float belly = LowestSurface(q.x, q.z);
            if (float.IsNaN(belly)) { _log.LogInfo("Nose gear: no Typhoon skin above the leg."); return; }
            float bellyY = belly * scale + offset.y;
            float gap = bellyY - hp.y;
            _log.LogInfo($"Nose gear: leg top {hp.y:0.00}, Typhoon belly {bellyY:0.00}, gap {gap:0.00} m.");
            if (gap < 0.03f || gap > 1.2f) return;
            var go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            go.name = "Typhoon_nosegear_extension";
            var col = go.GetComponent<Collider>(); if (col != null) UnityEngine.Object.Destroy(col);
            go.layer = hinge.gameObject.layer;
            float len = gap + 0.12f, dia = 0.11f;
            go.transform.SetParent(root, false);
            go.transform.localPosition = new Vector3(hp.x, hp.y + len * 0.5f - 0.04f, hp.z);
            go.transform.localRotation = Quaternion.identity;
            go.transform.localScale = new Vector3(dia, len * 0.5f, dia);
            go.transform.SetParent(hinge, true);
            var r = go.GetComponent<MeshRenderer>();
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
            Material m = leg != null ? leg.sharedMaterial : null;
            if (m == null && _mats != null) _mats.TryGetValue("metal", out m);
            if (m != null) r.sharedMaterial = m;
            visual.GearExtensions.Add(new TyphoonVisual.GearExtension { R = r, Hinge = hinge, Rest = hinge.localRotation });
        }

        static readonly Dictionary<string, KeyValuePair<Matrix4x4, Mesh>> MeshCache = new Dictionary<string, KeyValuePair<Matrix4x4, Mesh>>();

        static Mesh SharedMesh(ObjGroup g, Matrix4x4 m)
        {
            KeyValuePair<Matrix4x4, Mesh> e;
            if (MeshCache.TryGetValue(g.Name, out e) && e.Value != null)
            {
                bool same = true;
                for (int i = 0; i < 16 && same; i++) same = Mathf.Abs(e.Key[i] - m[i]) < 1e-5f;
                if (same) return e.Value;
            }
            var mesh = BuildMesh(g, m);
            if (g.Name.Equals("airbrake", StringComparison.OrdinalIgnoreCase)) MakeDoubleSided(mesh);
            MeshCache[g.Name] = new KeyValuePair<Matrix4x4, Mesh>(m, mesh);
            return mesh;
        }

        internal static Mesh BuildMesh(ObjGroup g, Matrix4x4 m)
        {
            Matrix4x4 nm = m.inverse.transpose;
            var verts = new Vector3[g.Positions.Count];
            var norms = new Vector3[g.Normals.Count];
            for (int i = 0; i < verts.Length; i++)
            {
                verts[i] = m.MultiplyPoint3x4(g.Positions[i]);
                norms[i] = nm.MultiplyVector(g.Normals[i]).normalized;
            }
            var tris = g.Triangles.ToArray();
            if (m.determinant < 0)
                for (int i = 0; i < tris.Length; i += 3) { int t = tris[i + 1]; tris[i + 1] = tris[i + 2]; tris[i + 2] = t; }
            var mesh = new Mesh { name = "Typhoon_" + g.Name };
            if (verts.Length > 65000) mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            mesh.vertices = verts;
            mesh.normals = norms;
            var uv = new Vector2[verts.Length];
            for (int i = 0; i < uv.Length; i++)
            {
                if (g.HasUVs) { uv[i] = g.UVs[i]; continue; }
                Vector3 pm = g.Positions[i], n = g.Normals[i];
                float ax = Mathf.Abs(n.x), ay = Mathf.Abs(n.y), az = Mathf.Abs(n.z);
                Vector2 t = ay >= ax && ay >= az ? new Vector2(pm.x, pm.z) : ax >= az ? new Vector2(pm.z, pm.y) : new Vector2(pm.x, pm.y);
                uv[i] = t / 6f;
            }
            mesh.uv = uv;
            mesh.triangles = tris;
            if (g.HasUVs) mesh.RecalculateTangents();
            mesh.RecalculateBounds();
            return mesh;
        }

        static Material MakeMaterial(Material template, Color color, float smoothness, float metallic)
        {
            var lit = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Universal Render Pipeline/Simple Lit");
            if (lit != null)
            {
                var u = new Material(lit);
                if (u.HasProperty("_BaseMap")) u.SetTexture("_BaseMap", null);
                if (u.HasProperty("_BaseColor")) u.SetColor("_BaseColor", color);
                if (u.HasProperty("_Color")) u.SetColor("_Color", color);
                if (u.HasProperty("_Smoothness")) u.SetFloat("_Smoothness", smoothness);
                if (u.HasProperty("_Metallic")) u.SetFloat("_Metallic", metallic);
                if (u.HasProperty("_Surface")) u.SetFloat("_Surface", 0f);
                u.renderQueue = 2000;
                u.name = "Typhoon_" + ColorUtility.ToHtmlStringRGB(color);
                return u;
            }
            var m = template != null ? new Material(template) : new Material(Shader.Find("Standard"));
            var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false) { name = "TyphoonPaint" };
            tex.SetPixels(new[] { color, color, color, color });
            tex.Apply();
            foreach (var t in new[] { "_Livery", "_MainTex", "_BaseMap", "_BaseColorMap" })
                if (m.HasProperty(t)) m.SetTexture(t, tex);
            foreach (var c in new[] { "_Color", "_BaseColor", "_MainColor", "_Tint" })
                if (m.HasProperty(c)) m.SetColor(c, color);
            if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", smoothness);
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", smoothness);
            if (m.HasProperty("_Metallic")) m.SetFloat("_Metallic", metallic);
            m.name = "Typhoon_" + ColorUtility.ToHtmlStringRGB(color);
            return m;
        }

        void LogShader(Material template)
        {
            var lit = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Universal Render Pipeline/Simple Lit");
            _log.LogInfo($"Paint shader: {(lit != null ? lit.name : "none found, cloning " + (template != null ? template.shader.name : "?"))}");
            if (template == null || template.shader == null) return;
            var sh = template.shader;
            var names = new List<string>();
            for (int i = 0; i < sh.GetPropertyCount(); i++) names.Add(sh.GetPropertyName(i));
            _log.LogInfo($"Original airframe shader '{sh.name}': {string.Join(", ", names.ToArray())}");
        }

        void WriteReport(string aircraftName, List<OrigPart> parts, int exteriorCount)
        {
            var sb = new StringBuilder();
            sb.AppendLine($"# Meshes on '{aircraftName}' ({exteriorCount} in the game's exterior list).");
            sb.AppendLine("# exterior/hidden = replaced by the Typhoon.  cockpit/weapon/kept = left visible.");
            sb.AppendLine("# size is in metres (x right, y up, z forward).\n");
            foreach (var p in parts.OrderBy(p => p.Status).ThenBy(p => p.Path))
                sb.AppendLine($"{p.Status,-8}  size={p.RootBounds.size.x:0.0}x{p.RootBounds.size.y:0.0}x{p.RootBounds.size.z:0.0}  {p.Path}");
            string path = System.IO.Path.Combine(Paths.ConfigPath, "TyphoonMod_renderers.txt");
            File.WriteAllText(path, sb.ToString());
            _log.LogInfo($"Mesh report written to {path}");
        }

        static string PathOf(Transform t, Transform root)
        {
            var names = new List<string>();
            for (var x = t; x != null && x != root; x = x.parent) names.Add(x.name);
            names.Reverse();
            return string.Join("/", names.ToArray());
        }

        static Bounds TransformBounds(Bounds b, Matrix4x4 m)
        {
            Vector3 c = b.center, e = b.extents;
            var result = new Bounds(m.MultiplyPoint3x4(c), Vector3.zero);
            for (int i = 0; i < 8; i++)
            {
                var corner = c + new Vector3((i & 1) == 0 ? -e.x : e.x, (i & 2) == 0 ? -e.y : e.y, (i & 4) == 0 ? -e.z : e.z);
                result.Encapsulate(m.MultiplyPoint3x4(corner));
            }
            return result;
        }

        static float Volume(Bounds b) => b.size.x * b.size.y * b.size.z + 1e-6f;

        static Vector3 ParseVector(string s)
        {
            var p = (s ?? "").Split(',');
            float x = 0, y = 0, z = 0;
            if (p.Length == 3)
            {
                float.TryParse(p[0].Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out x);
                float.TryParse(p[1].Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out y);
                float.TryParse(p[2].Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out z);
            }
            return new Vector3(x, y, z);
        }
    }
}
